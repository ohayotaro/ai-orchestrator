"""Scoped host-mediated confirmation. No model-callable approve(bool) endpoint.

Form elicitation is a client-mediated channel, not authenticated proof that a
human clicked. It is enabled only by the operator's --single-terminal opt-in.
"""
from __future__ import annotations

import json
import os
import pwd
import sqlite3
import time
import unicodedata
import uuid
from typing import Any, Literal

from pydantic import Field, field_validator

from . import authority
from .models import Contract, OrchestratorError, identifier
from .project import Project, confined, digest, encode
from .service import ApplicationService
from .supervisor import Supervisor

MAX_PREVIEW_BYTES = 32 * 1024
MAX_COMPACT_BINDINGS = 12
ASSURANCE = "client-mediated; human presence not cryptographically verified"


class StartRequest(Contract):
    intake_id: str
    request_id: str

    _ids = field_validator("intake_id", "request_id")(identifier)


class TaskRequest(Contract):
    task_id: str
    request_id: str

    _ids = field_validator("task_id", "request_id")(identifier)


class ProfileChangeRequest(Contract):
    provider: str
    adapter: str
    request_id: str

    _ids = field_validator("provider", "adapter", "request_id")(identifier)


class ProviderPermissionRequest(Contract):
    task_id: str
    request_id: str
    permission: Literal["agy_dangerously_skip_permissions"]

    _ids = field_validator("task_id", "request_id")(identifier)


class BindingCleanupRequest(Contract):
    task_ids: list[str] = Field(default_factory=list, max_length=100)
    intake_ids: list[str] = Field(default_factory=list, max_length=100)
    request_id: str

    _request = field_validator("request_id")(identifier)

    @field_validator("task_ids", "intake_ids")
    @classmethod
    def valid_ids(cls, values: list[str]) -> list[str]:
        normalized = [identifier(value) for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("binding cleanup IDs must be unique")
        return normalized


GATE_TOOLS = {
    "request_start": (StartRequest, "Ask the host to display a scoped confirmation of an intake; only its explicit form response may register the task and queue planning. Never supply a decision or actor.", False),
    "request_execution": (TaskRequest, "Ask the host for scoped implementation approval. After explicit confirmation, approve the exact current plan/attempt and queue it. Every repair needs a fresh request.", False),
    "request_acceptance": (TaskRequest, "Ask the host to confirm acceptance of the exact reviewed result. Only explicit confirmation can mark it succeeded. This never commits/pushes/deploys.", False),
    "request_provider_change": (ProfileChangeRequest, "Ask the host to confirm one exact persistent provider-adapter change. On Yes, the controller atomically edits only that provider slot, resets adapter-specific executable/model/effort overrides, validates the resulting profile, and trusts only its resulting digest.", False),
    "request_binding_cleanup": (BindingCleanupRequest, "Ask the host to abandon exact unfinished tasks and withdraw exact unconsumed intakes. This terminalizes bindings only; it never deletes history or rolls back workspace files.", False),
    "request_provider_permission": (ProviderPermissionRequest, "Ask the host for a separate high-risk provider permission gate. The only supported permission is AGY --dangerously-skip-permissions for this exact task attempt; it does not approve execution itself.", False),
}


class HumanGate(Contract):
    schema_version: Literal[1] = 1
    id: str
    session: str
    local_uid: int
    actor: str
    client: dict[str, str]
    request_id: str
    kind: Literal["start", "execution", "acceptance", "profile_change", "binding_cleanup", "provider_permission"]
    subject: str
    task_id: str | None = None
    scope: str
    kernel_scope: str
    preview: dict[str, Any]
    authority_request: dict[str, Any] | None = None
    created_at: float
    expires_at: float
    status: Literal["pending", "applying", "applied", "declined", "cancelled", "expired", "stale", "failed", "uncertain"] = "pending"
    result: dict[str, Any] | None = None
    error: str | None = None


def safe_display(value: dict[str, Any]) -> str:
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    # JSON already escapes C0 characters in strings; also escape bidi/format
    # controls while keeping ordinary Japanese text readable in native forms.
    return "".join(f"\\u{ord(c):04x}" if unicodedata.category(c) == "Cf" else c for c in text)


def _clean_inline(value: Any, limit: int = 180) -> str:
    text = str(value).replace("\r", " ").replace("\n", " ")
    text = " ".join(text.split())
    text = "".join(
        f"\\u{ord(c):04x}" if unicodedata.category(c) in ("Cf", "Cc") else c
        for c in text
    )
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _csv(values: Any, *, limit: int = 6) -> str:
    if not isinstance(values, list) or not values:
        return "-"
    cleaned = [_clean_inline(value, 80) for value in values[:limit]]
    if len(values) > limit:
        cleaned.append(f"+{len(values) - limit} more")
    return ", ".join(cleaned)


def compact_gate_summary(gate: "HumanGate") -> str:
    """Human-readable, bounded confirmation summary.

    The authoritative preview remains stored in gate.preview and bound into the
    scope. This summary is display-only and intentionally omits verbose evidence.
    """
    p = gate.preview
    lines = [f"Operation: {_clean_inline(p.get('operation', gate.kind), 220)}"]

    if gate.kind == "provider_permission":
        ctx = p.get("provider_permission") or {}
        nodes = ctx.get("nodes") or []
        node_names = [item.get("node") for item in nodes if isinstance(item, dict) and item.get("node")]
        providers = [
            f"{item.get('provider')}/{item.get('adapter')}"
            for item in nodes if isinstance(item, dict) and item.get("adapter")
        ]
        lines += [
            f"Task: {_clean_inline(gate.task_id or gate.subject)}",
            f"Attempt: {ctx.get('attempt', '-')}",
            "Permission: AGY --dangerously-skip-permissions",
            f"Provider node(s): {_csv(node_names)}",
            f"Provider: {_csv(providers)}",
            "Effect: all AGY-native tool permission prompts are auto-approved for this scoped provider session.",
            "Still enforced: AGY sandbox; guarded private worktree; allowed_paths/write ownership; validators; review.",
            "Execution approval: NOT included — a separate execution confirmation is still required.",
        ]
    elif gate.kind == "profile_change":
        change = p.get("change") or {}
        before = change.get("before") or {}
        after = change.get("after") or {}
        lines += [
            f"Provider slot: {_clean_inline(change.get('provider', gate.subject))}",
            f"Adapter: {_clean_inline(before.get('adapter', '-'))} -> {_clean_inline(after.get('adapter', change.get('adapter', '-')))}",
            f"Reset vendor-specific fields: {_csv(change.get('reset_adapter_specific_fields') or [])}",
            f"New trusted profile: {_clean_inline(change.get('proposed_profile_digest', '-'), 72)}",
            "Task effect: no task is executed or accepted by this confirmation.",
        ]
    elif gate.kind == "binding_cleanup":
        lines += [
            f"Abandon task(s): {_csv(p.get('task_ids') or [])}",
            f"Withdraw intake(s): {_csv(p.get('intake_ids') or [])}",
            "Workspace rollback: NO",
            "History/artifacts/task files: retained",
            "Provider change: NOT included — it requires a separate confirmation.",
        ]
    elif gate.kind == "start":
        task = p.get("task") or {}
        workflow_nodes = (p.get("workflow") or {}).get("nodes") or []
        node_names = [
            item.get("id") for item in workflow_nodes
            if isinstance(item, dict) and item.get("id")
        ]
        ownership = [
            str(item.get("id")) + ":" + ",".join(item.get("write_paths") or [])
            for item in workflow_nodes
            if isinstance(item, dict) and item.get("write_paths")
        ]
        lines += [
            f"Task: {_clean_inline(task.get('id', gate.task_id or gate.subject))}",
            f"Goal: {_clean_inline(task.get('goal', '-'))}",
            f"Risk: {_clean_inline(task.get('risk', '-'))}",
            f"Allowed paths: {_csv(p.get('allowed_paths') or [])}",
            f"Validators: {_csv(list((p.get('validators') or {}).keys()))}",
            f"Workflow: {_clean_inline(p.get('workflow_ref', '-'))} ({_clean_inline(p.get('workflow_source', '-'))})",
            f"Workflow nodes: {_csv(node_names)}",
            f"Write ownership: {_csv(ownership)}",
            "Effect: register task and queue planning only; implementation still requires a separate confirmation.",
        ]
    elif gate.kind == "execution":
        task = p.get("task") or {}
        resolutions = p.get("provider_resolutions") or {}
        implementer = resolutions.get("implementer") if isinstance(resolutions, dict) else None
        provider_text = "-"
        if isinstance(implementer, dict):
            provider_text = "/".join(
                str(value) for value in (
                    implementer.get("provider"), implementer.get("adapter"), implementer.get("family")
                ) if value
            ) or "-"
        # v0.8.9 capture adds this explicit display-only field; fall back to none.
        grants = p.get("provider_permissions") or []
        lines += [
            f"Task: {_clean_inline(task.get('id', gate.task_id or gate.subject))}",
            f"Attempt: {p.get('attempt', '-')}",
            f"Goal: {_clean_inline(task.get('goal', '-'))}",
            f"Allowed paths: {_csv(p.get('allowed_paths') or [])}",
            f"Implementer: {_clean_inline(provider_text)}",
            f"Provider permission override(s): {_csv(grants)}",
            f"Validators: {_csv(list((p.get('validators') or {}).keys()))}",
            "Effect: authorize this exact implementation attempt and queue execution to the next gate.",
        ]
    elif gate.kind == "acceptance":
        task = p.get("task") or {}
        write_set = p.get("write_set") or {}
        validation = p.get("validation") or {}
        review = p.get("review") or {}
        lines += [
            f"Task: {_clean_inline(task.get('id', gate.task_id or gate.subject))}",
            f"Goal: {_clean_inline(task.get('goal', '-'))}",
            f"Changed paths: {_csv(write_set.get('changed_paths') if isinstance(write_set, dict) else [])}",
            f"Validation passed: {validation.get('passed', '-') if isinstance(validation, dict) else '-'}",
            f"Review outcome: {_clean_inline(review.get('outcome', '-') if isinstance(review, dict) else '-')}",
            "Effect: mark this exact reviewed worktree complete.",
            "Not authorized: commit, push, deployment, publication, or other external action.",
        ]
    else:
        lines += [f"Subject: {_clean_inline(gate.subject)}"]

    lines += [
        f"Scope: {gate.scope}",
        f"Gate: {gate.id}",
        f"Assurance: {ASSURANCE}",
    ]
    return "\n".join(lines)


class GateStore:
    def __init__(self, project: Project):
        project.runtime.mkdir(parents=True, exist_ok=True)
        path = confined(project.root, ".orchestrator/runtime/gates.sqlite3")
        for suffix in ("-wal", "-shm", "-journal"):
            confined(project.root, f".orchestrator/runtime/gates.sqlite3{suffix}")
        self.db = sqlite3.connect(path, timeout=5)
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            self.db.close()
            raise OrchestratorError("unsupported human-gate database version")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS gates (
                id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL,
                kind TEXT NOT NULL, subject TEXT NOT NULL, status TEXT NOT NULL,
                expires_at REAL NOT NULL, data TEXT NOT NULL
            );
            CREATE UNIQUE INDEX IF NOT EXISTS active_subject_gate ON gates(kind,subject)
                WHERE status IN ('pending','applying');
            CREATE TABLE IF NOT EXISTS gate_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                gate_id TEXT NOT NULL, status TEXT NOT NULL, created_at REAL NOT NULL
            );
            PRAGMA user_version=1;
        """)

    def close(self) -> None:
        self.db.close()

    def get(self, gate_id: str) -> HumanGate:
        identifier(gate_id)
        row = self.db.execute("SELECT data FROM gates WHERE id=?", (gate_id,)).fetchone()
        if row is None:
            raise OrchestratorError("unknown human gate")
        return HumanGate.model_validate_json(row[0])

    def by_request(self, request_id: str, kind: str, subject: str) -> HumanGate | None:
        identifier(request_id)
        row = self.db.execute("SELECT id FROM gates WHERE request_id=?", (request_id,)).fetchone()
        if row is None:
            return None
        gate = self.get(row[0])
        if (gate.kind, gate.subject) != (kind, subject):
            raise OrchestratorError("gate request_id was already used for a different operation")
        return gate

    def _save(self, gate: HumanGate, previous: str) -> None:
        cursor = self.db.execute("UPDATE gates SET status=?,data=? WHERE id=? AND status=?", (gate.status, gate.model_dump_json(), gate.id, previous))
        if cursor.rowcount != 1:
            raise OrchestratorError("gate was already consumed or changed; no replay is allowed")
        self.db.execute("INSERT INTO gate_events(gate_id,status,created_at) VALUES (?,?,?)", (gate.id, gate.status, time.time()))

    def create(self, gate: HumanGate) -> None:
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            for (gate_id,) in self.db.execute("SELECT id FROM gates WHERE status='pending' AND expires_at<=?", (time.time(),)).fetchall():
                old = self.get(gate_id)
                old.status = "expired"
                self._save(old, "pending")
            try:
                self.db.execute("INSERT INTO gates VALUES (?,?,?,?,?,?,?)", (gate.id, gate.request_id, gate.kind, gate.subject, gate.status, gate.expires_at, gate.model_dump_json()))
            except sqlite3.IntegrityError as exc:
                raise OrchestratorError("a gate already exists for this request/subject; inspect it rather than prompting twice") from exc
            self.db.execute("INSERT INTO gate_events(gate_id,status,created_at) VALUES (?,'pending',?)", (gate.id, time.time()))

    def transition(self, gate_id: str, session: str, previous: str, status: str, *, result: dict[str, Any] | None = None, error: str | None = None) -> HumanGate:
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            gate = self.get(gate_id)
            if gate.session != session or gate.local_uid != os.getuid() or gate.status != previous:
                raise OrchestratorError("gate is not owned by this session or is no longer pending")
            gate.status, gate.result, gate.error = status, result, error
            self._save(gate, previous)
        return gate


class HumanGateBroker:
    def __init__(self, service: ApplicationService, session: str, client: dict[str, str], *, ttl: float = 120):
        if not 0.1 <= ttl <= 600:
            raise OrchestratorError("gate timeout must be between 0.1 and 600 seconds")
        self.service = service
        self.session = session
        self.ttl = ttl
        self.client = {key: str(client.get(key, ""))[:128] for key in ("name", "version")}
        self.actor = "host-elicitation:" + pwd.getpwuid(os.getuid()).pw_name
        self.store = GateStore(Project(service.root))

    def close(self) -> None:
        self.store.close()

    def capture(
        self, engine, kind: str, subject: str,
        authority_request: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        project = engine.project
        current = project.load()[1]
        if current != engine.profile_digest or not engine.store.trusted(current):
            raise OrchestratorError("profile changed or untrusted; host confirmation never grants project trust")

        if kind == "binding_cleanup":
            request = BindingCleanupRequest.model_validate(authority_request or {})
            if len(request.task_ids) + len(request.intake_ids) > MAX_COMPACT_BINDINGS:
                raise OrchestratorError(
                    f"binding cleanup confirmation is limited to {MAX_COMPACT_BINDINGS} exact IDs so all targets remain visible; split the cleanup into smaller confirmations"
                )
            proposed = authority.binding_cleanup_preview(
                engine, request.task_ids, request.intake_ids
            )
            kernel_scope = proposed["scope"]
            state = {"authority_request": request.model_dump(), "cleanup": proposed}
            scope = digest({
                "kind": kind, "subject": subject, "state": state, "kernel_scope": kernel_scope,
                "profile": current, "workspace": project.snapshot(),
                "protected": project.protected_snapshot(engine.profile),
                "controls": project.control_snapshot(),
            })
            preview = {
                "operation": (
                    "Terminalize only these exact unfinished bindings. Tasks become abandoned; "
                    "intakes become withdrawn. This does NOT roll back or delete existing workspace changes, "
                    "task files, artifacts, or audit history."
                ),
                "project": str(project.root),
                "subject": subject,
                "scope": scope,
                **proposed,
            }
            if len(safe_display(preview).encode()) > MAX_PREVIEW_BYTES:
                raise OrchestratorError("confirmation preview exceeds 32 KiB; no binding cleanup was prepared")
            return {"task_id": None, "kernel_scope": kernel_scope, "scope": scope, "preview": preview}

        if kind == "profile_change":
            request = ProfileChangeRequest.model_validate(authority_request or {})
            proposed = authority.provider_change_preview(engine, request.provider, request.adapter)
            if not proposed["ready"]:
                blockers = proposed["blocked_by"]
                raise OrchestratorError(
                    "provider change is blocked by unfinished bindings; use preview_binding_cleanup "
                    "and request_binding_cleanup first: "
                    f"tasks={','.join(blockers['task_ids']) or '-'}; "
                    f"intakes={','.join(blockers['intake_ids']) or '-'}"
                )
            change = proposed["change"]
            kernel_scope = change["proposed_profile_digest"]
            state = {"authority_request": request.model_dump(), "change": change}
            scope = digest({
                "kind": kind, "subject": subject, "state": state, "kernel_scope": kernel_scope,
                "profile": current, "workspace": project.snapshot(),
                "protected": project.protected_snapshot(engine.profile),
                "controls": project.control_snapshot(),
            })
            preview = {
                "operation": (
                    "Persist this exact provider-adapter change and trust only the resulting profile digest. "
                    "This is project authority, not a task execution approval."
                ),
                "project": str(project.root),
                "subject": subject,
                "scope": scope,
                **proposed,
            }
            if len(safe_display(preview).encode()) > MAX_PREVIEW_BYTES:
                raise OrchestratorError("confirmation preview exceeds 32 KiB; no authority change was prepared")
            return {"task_id": None, "kernel_scope": kernel_scope, "scope": scope, "preview": preview}

        if kind == "provider_permission":
            request = ProviderPermissionRequest.model_validate(authority_request or {})
            state_object = engine.store.get(request.task_id)
            if state_object.spec.external_effects:
                raise OrchestratorError("external-effect work cannot be authorized by this gate")
            context = engine.provider_permission_context(state_object, request.permission)
            kernel_scope = context["scope"]
            state = state_object.model_dump()
            scope = digest({
                "kind": kind, "subject": subject, "state": state, "kernel_scope": kernel_scope,
                "profile": current, "workspace": project.snapshot(),
                "protected": project.protected_snapshot(engine.profile),
                "controls": project.control_snapshot(),
            })
            preview = {
                "operation": (
                    "Authorize AGY --dangerously-skip-permissions for only this exact task attempt/provider session. "
                    "This auto-approves all AGY-native tool permission requests for the scoped session and is separate "
                    "from execution approval."
                ),
                "project": str(project.root),
                "subject": subject,
                "scope": scope,
                "task": state_object.spec.model_dump(),
                "plan": engine.store.latest(state_object, "plan"),
                "provider_permission": context,
                "next_gate": "A separate request_execution confirmation is still required after this permission is applied.",
            }
            if len(safe_display(preview).encode()) > MAX_PREVIEW_BYTES:
                raise OrchestratorError("confirmation preview exceeds 32 KiB; no provider permission was prepared")
            return {"task_id": state_object.spec.id, "kernel_scope": kernel_scope, "scope": scope, "preview": preview}
        if kind == "start":
            intake = engine.store.get_intake(subject)
            supervisor = Supervisor(engine)
            supervisor._check_profile(intake.profile_digest)
            if intake.status != "proposed" or intake.task is None:
                raise OrchestratorError("intake is not an unconsumed proposal")
            kernel_scope = supervisor.scope(intake)
            if intake.workspace_snapshot != project.snapshot():
                raise OrchestratorError("worktree changed since intake")
            task = intake.task
            selected_workflow = intake.workflow_ref or engine.profile.workflow
            if intake.workflow_spec is not None:
                compiled = engine.compile_proposed_workflow(intake.workflow_spec)
                workflow_report = compiled.report()
                workflow_report["source"] = "task_scoped_supervisor_proposal"
                workflow_persistence = "task_scoped_only; not installed in project profile"
            else:
                workflow_report = engine.workflow_report(selected_workflow)
                workflow_persistence = "trusted_registry"
            payload = {"task": task.model_dump(), "allowed_paths": intake.allowed_paths,
                       "capability_requirements": intake.capability_requirements,
                       "workflow_ref": selected_workflow,
                       "workflow_source": intake.workflow_source or "profile_default",
                       "workflow_persistence": workflow_persistence,
                       "workflow": workflow_report,
                       "supervisor_summary": intake.result.summary, "notes": intake.notes}
            state = intake.model_dump()
            if state.get("allowed_paths") is None:
                state.pop("allowed_paths", None)
        else:
            state_object = engine.store.get(subject)
            engine._check(state_object)
            if engine.store.cancelled(subject):
                raise OrchestratorError("task has a cancellation request")
            task = state_object.spec
            state = state_object.model_dump()
            if state.get("allowed_paths") is None:
                state.pop("allowed_paths", None)
            if kind == "execution":
                if state_object.status != "awaiting_approval" or state_object.phase != "execute":
                    raise OrchestratorError("task is not awaiting execution approval")
                engine.validate_provider_permission_grants(state_object)
                kernel_scope = engine.approval_scope(state_object)
                payload = {"task": task.model_dump(), "allowed_paths": state_object.allowed_paths,
                           "capability_requirements": state_object.capability_requirements,
                           "provider_resolutions": state_object.provider_resolutions,
                           "provider_permissions": sorted(state_object.provider_permission_grants),
                           "attempt": state_object.attempt, "plan": engine.store.latest(state_object, "plan"),
                           "feedback": state_object.feedback,
                           **({"workflow": engine.workflow_gate_context(state_object)} if state_object.schema_version >= 4 else {})}
            elif kind == "acceptance":
                if state_object.status != "awaiting_acceptance" or state_object.reviewed_snapshot != project.snapshot():
                    raise OrchestratorError("task is not awaiting acceptance or worktree changed since review")
                kernel_scope = digest(state)
                payload = {"task": task.model_dump(), "allowed_paths": state_object.allowed_paths,
                           "capability_requirements": state_object.capability_requirements,
                           "provider_resolutions": state_object.provider_resolutions,
                           "write_set": engine.store.latest(state_object, "write_set"),
                           "validation": engine.store.latest(state_object, "validation"),
                           "review": engine.store.latest(state_object, "review"),
                           "reviewed_snapshot": state_object.reviewed_snapshot,
                           **({"workflow": engine.workflow_gate_context(state_object)} if state_object.schema_version >= 4 else {})}
            else:
                raise OrchestratorError("unknown gate kind")
        if task.external_effects:
            raise OrchestratorError("external-effect work cannot be authorized by this gate")
        # Exact state and all current controls, not just the model's summary.
        scope = digest({"kind": kind, "subject": subject, "state": state, "kernel_scope": kernel_scope,
                        "profile": current, "workspace": project.snapshot(),
                        "protected": project.protected_snapshot(engine.profile), "controls": project.control_snapshot()})
        descriptions = {
            "start": "Register this task and queue planning only. Implementation needs a separate confirmation.",
            "execution": "Authorize this exact implementation attempt and registered validators; queue execution to the next gate. Model/API usage may incur cost.",
            "acceptance": "Accept this exact reviewed worktree as complete. No commit, push, deployment or external action is authorized.",
        }
        preview = {"operation": descriptions[kind], "project": str(project.root), "subject": subject,
                   "scope": scope, "validators": {name: engine.profile.validators[name].model_dump() for name in task.validators}, **payload}
        if len(safe_display(preview).encode()) > MAX_PREVIEW_BYTES:
            raise OrchestratorError("confirmation preview exceeds 32 KiB; use the operator CLI after inspecting full artifacts, not a truncated host form")
        return {"task_id": task.id, "kernel_scope": kernel_scope, "scope": scope, "preview": preview}

    def prepare(
        self, kind: str, subject: str, request_id: str,
        authority_request: dict[str, Any] | None = None,
    ) -> HumanGate:
        identifier(subject)
        identifier(request_id)
        old = self.store.by_request(request_id, kind, subject)
        if old is not None:
            if old.status in ("pending", "applying"):
                raise OrchestratorError("this confirmation is pending or has an uncertain effect; do not prompt/replay it")
            return old
        with self.service.engine() as engine, engine.project.lock():
            captured = self.capture(engine, kind, subject, authority_request)
            stamp = time.time()
            gate = HumanGate(id="G-" + uuid.uuid4().hex, session=self.session, local_uid=os.getuid(), actor=self.actor,
                             client=self.client, request_id=request_id, kind=kind, subject=subject,
                             authority_request=authority_request,
                             created_at=stamp, expires_at=stamp + self.ttl, **captured)
            self.store.create(gate)
        return gate

    def prepare_binding_cleanup(self, request: BindingCleanupRequest) -> HumanGate:
        subject = "BC-" + digest({
            "task_ids": sorted(request.task_ids),
            "intake_ids": sorted(request.intake_ids),
        })[:32]
        return self.prepare(
            "binding_cleanup", subject, request.request_id,
            request.model_dump(),
        )

    def prepare_provider_change(self, request: ProfileChangeRequest) -> HumanGate:
        subject = "PC-" + digest({"provider": request.provider, "adapter": request.adapter})[:32]
        return self.prepare(
            "profile_change", subject, request.request_id,
            request.model_dump(),
        )

    def prepare_provider_permission(self, request: ProviderPermissionRequest) -> HumanGate:
        return self.prepare(
            "provider_permission", request.task_id, request.request_id,
            request.model_dump(),
        )

    @staticmethod
    def form(gate: HumanGate) -> dict[str, Any]:
        summary = compact_gate_summary(gate)
        return {
            "message": "AI Orchestrator confirmation. Review this bounded summary; the full exact state remains scope-bound in the controller.\n"
                       + summary + "\nChoose Yes only to authorize this exact operation. No/cancel leaves it unchanged.",
            "requestedSchema": {"type": "object", "properties": {
                "decision": {"type": "string", "title": "Authorize this exact operation?", "description": "Choose Yes to authorize this exact scope; choose No to decline.", "enum": ["yes", "no"], "enumNames": ["Yes — authorize", "No — decline"]}
            }, "required": ["decision"]},
        }

    @staticmethod
    def describe(gate: HumanGate) -> dict[str, Any]:
        return {"gate_id": gate.id, "kind": gate.kind, "subject": gate.subject, "gate_status": gate.status,
                "scope": gate.scope, "assurance": ASSURANCE, "result": gate.result, "error": gate.error}

    def abort(self, gate: HumanGate, status: str, message: str) -> dict[str, Any]:
        updated = self.store.transition(gate.id, self.session, "pending", status, error=message)
        return self.describe(updated)

    def resolve(self, gate: HumanGate, response: Any) -> dict[str, Any]:
        # Called only by the transport's matching server-request response path.
        # No tool accepts this response, a decision, actor, or a gate token.
        if time.time() >= gate.expires_at:
            return self.abort(gate, "expired", "Confirmation expired; nothing was authorized")
        if not isinstance(response, dict) or response.get("action") not in ("accept", "decline", "cancel"):
            return self.abort(gate, "failed", "Invalid elicitation response; nothing was authorized")
        if response["action"] != "accept":
            status = "declined" if response["action"] == "decline" else "cancelled"
            return self.abort(gate, status, "Host declined/cancelled; no automatic retry or fallback approval")
        content = response.get("content")
        if not isinstance(content, dict) or set(content) != {"decision"} or content["decision"] not in ("yes", "no"):
            return self.abort(gate, "failed", "An explicit Yes/No decision is required; nothing was authorized")
        if content["decision"] != "yes":
            return self.abort(gate, "declined", "No was selected; nothing was authorized")
        applying = False
        try:
            with self.service.engine() as engine:
                def check() -> None:
                    nonlocal applying
                    fresh = self.capture(engine, gate.kind, gate.subject, gate.authority_request)
                    if time.time() >= gate.expires_at or fresh["scope"] != gate.scope:
                        raise OrchestratorError("confirmation expired or scope changed while the dialog was open")
                    self.store.transition(gate.id, self.session, "pending", "applying")
                    applying = True
                # The callback runs inside the existing kernel's workspace lock,
                # directly before writes. An intent is recorded before the effect;
                # an interrupted applying record is never replayed automatically.
                if gate.kind == "start":
                    state = Supervisor(engine).start(gate.subject, gate.kernel_scope, gate.actor, precondition=check)
                    result = {"task_id": state.spec.id, "task_status": state.status}
                    event_task_id = state.spec.id
                elif gate.kind == "execution":
                    state = engine.approve(gate.subject, gate.kernel_scope, gate.actor, precondition=check)
                    result = {"task_id": state.spec.id, "task_status": state.status}
                    event_task_id = state.spec.id
                elif gate.kind == "acceptance":
                    state = engine.accept(gate.subject, gate.actor, precondition=check)
                    result = {"task_id": state.spec.id, "task_status": state.status}
                    event_task_id = state.spec.id
                elif gate.kind == "provider_permission":
                    request = ProviderPermissionRequest.model_validate(gate.authority_request or {})
                    state = engine.authorize_provider_permission(
                        request.task_id, request.permission, gate.kernel_scope, gate.actor,
                        precondition=check,
                    )
                    result = {
                        "task_id": state.spec.id,
                        "task_status": state.status,
                        "permission": request.permission,
                        "next_action": "Request execution confirmation for the now-expanded exact execution scope.",
                    }
                    event_task_id = state.spec.id
                elif gate.kind == "binding_cleanup":
                    request = BindingCleanupRequest.model_validate(gate.authority_request or {})
                    with engine.project.lock():
                        check()
                        result = authority.apply_binding_cleanup(
                            engine,
                            request.task_ids,
                            request.intake_ids,
                            gate.kernel_scope,
                            gate.actor,
                        )
                    event_task_id = None
                elif gate.kind == "profile_change":
                    request = ProfileChangeRequest.model_validate(gate.authority_request or {})
                    with engine.project.lock():
                        check()
                        result = authority.apply_provider_change(
                            engine,
                            request.provider,
                            request.adapter,
                            gate.preview["change"]["current_profile_digest"],
                            gate.kernel_scope,
                            gate.actor,
                        )
                    event_task_id = None
                else:
                    raise OrchestratorError("unknown gate kind")
                with engine.store.db:
                    engine.store._event(event_task_id, "human_gate.applied", {"gate_id": gate.id, "kind": gate.kind,
                        "scope": gate.scope, "actor": gate.actor, "client": gate.client, "assurance": ASSURANCE})
            if gate.kind in ("start", "execution"):
                try:
                    job = self.service.invoke("run_task", {"task_id": state.spec.id, "request_id": "gate-" + gate.id})
                    result["job_id"] = job["id"]
                except Exception as exc:
                    # Authorization/registration already happened; a queue failure
                    # is not a reason to silently repeat it or lie about rollback.
                    result["scheduling_error"] = str(exc)[:2000]
                    result["next_action"] = "Inspect get_task, then run_task if still eligible; no new confirmation is implied"
            done = self.store.transition(gate.id, self.session, "applying", "applied", result=result)
            return self.describe(done)
        except Exception as exc:
            status = "uncertain" if applying else "stale"
            updated = self.store.transition(gate.id, self.session, "applying" if applying else "pending", status, error=str(exc)[:2000])
            return self.describe(updated)
