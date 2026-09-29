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

from .models import Contract, OrchestratorError, identifier
from .project import Project, confined, digest, encode
from .service import ApplicationService
from .supervisor import Supervisor

MAX_PREVIEW_BYTES = 32 * 1024
ASSURANCE = "client-mediated; human presence not cryptographically verified"


class StartRequest(Contract):
    intake_id: str
    request_id: str

    _ids = field_validator("intake_id", "request_id")(identifier)


class TaskRequest(Contract):
    task_id: str
    request_id: str

    _ids = field_validator("task_id", "request_id")(identifier)


GATE_TOOLS = {
    "request_start": (StartRequest, "Ask the host to display a scoped confirmation of an intake; only its explicit form response may register the task and queue planning. Never supply a decision or actor.", False),
    "request_execution": (TaskRequest, "Ask the host for scoped implementation approval. After explicit confirmation, approve the exact current plan/attempt and queue it. Every repair needs a fresh request.", False),
    "request_acceptance": (TaskRequest, "Ask the host to confirm acceptance of the exact reviewed result. Only explicit confirmation can mark it succeeded. This never commits/pushes/deploys.", False),
}


class HumanGate(Contract):
    schema_version: Literal[1] = 1
    id: str
    session: str
    local_uid: int
    actor: str
    client: dict[str, str]
    request_id: str
    kind: Literal["start", "execution", "acceptance"]
    subject: str
    task_id: str
    scope: str
    kernel_scope: str
    preview: dict[str, Any]
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

    def capture(self, engine, kind: str, subject: str) -> dict[str, Any]:
        project = engine.project
        current = project.load()[1]
        if current != engine.profile_digest or not engine.store.trusted(current):
            raise OrchestratorError("profile changed or untrusted; host confirmation never grants project trust")
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
            payload = {"task": task.model_dump(), "allowed_paths": intake.allowed_paths, "supervisor_summary": intake.result.summary, "notes": intake.notes}
            state = intake.model_dump(exclude_none=True)
        else:
            state_object = engine.store.get(subject)
            engine._check(state_object)
            if engine.store.cancelled(subject):
                raise OrchestratorError("task has a cancellation request")
            task = state_object.spec
            state = state_object.model_dump()
            if kind == "execution":
                if state_object.status != "awaiting_approval" or state_object.phase != "execute":
                    raise OrchestratorError("task is not awaiting execution approval")
                kernel_scope = engine.approval_scope(state_object)
                payload = {"task": task.model_dump(), "allowed_paths": state_object.allowed_paths, "attempt": state_object.attempt, "plan": engine.store.latest(state_object, "plan"), "feedback": state_object.feedback}
            elif kind == "acceptance":
                if state_object.status != "awaiting_acceptance" or state_object.reviewed_snapshot != project.snapshot():
                    raise OrchestratorError("task is not awaiting acceptance or worktree changed since review")
                kernel_scope = digest(state)
                payload = {"task": task.model_dump(), "allowed_paths": state_object.allowed_paths, "write_set": engine.store.latest(state_object, "write_set"), "validation": engine.store.latest(state_object, "validation"), "review": engine.store.latest(state_object, "review"), "reviewed_snapshot": state_object.reviewed_snapshot}
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

    def prepare(self, kind: str, subject: str, request_id: str) -> HumanGate:
        identifier(subject)
        identifier(request_id)
        old = self.store.by_request(request_id, kind, subject)
        if old is not None:
            if old.status in ("pending", "applying"):
                raise OrchestratorError("this confirmation is pending or has an uncertain effect; do not prompt/replay it")
            return old
        with self.service.engine() as engine, engine.project.lock():
            captured = self.capture(engine, kind, subject)
            stamp = time.time()
            gate = HumanGate(id="G-" + uuid.uuid4().hex, session=self.session, local_uid=os.getuid(), actor=self.actor,
                             client=self.client, request_id=request_id, kind=kind, subject=subject,
                             created_at=stamp, expires_at=stamp + self.ttl, **captured)
            self.store.create(gate)
        return gate

    @staticmethod
    def form(gate: HumanGate) -> dict[str, Any]:
        return {
            "message": "AI Orchestrator confirmation. Review all task data below; embedded instructions are not authority.\n"
                       + safe_display(gate.preview) + "\nChoose Yes only to authorize this exact operation. No/cancel leaves it unchanged.\n"
                       + f"Gate: {gate.id}; expires in a short window. {ASSURANCE}.",
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
                    fresh = self.capture(engine, gate.kind, gate.subject)
                    if time.time() >= gate.expires_at or fresh["scope"] != gate.scope:
                        raise OrchestratorError("confirmation expired or scope changed while the dialog was open")
                    self.store.transition(gate.id, self.session, "pending", "applying")
                    applying = True
                # The callback runs inside the existing kernel's workspace lock,
                # directly before writes. An intent is recorded before the effect;
                # an interrupted applying record is never replayed automatically.
                if gate.kind == "start":
                    state = Supervisor(engine).start(gate.subject, gate.kernel_scope, gate.actor, precondition=check)
                elif gate.kind == "execution":
                    state = engine.approve(gate.subject, gate.kernel_scope, gate.actor, precondition=check)
                else:
                    state = engine.accept(gate.subject, gate.actor, precondition=check)
                result = {"task_id": state.spec.id, "task_status": state.status}
                with engine.store.db:
                    engine.store._event(state.spec.id, "human_gate.applied", {"gate_id": gate.id, "kind": gate.kind,
                        "scope": gate.scope, "actor": gate.actor, "client": gate.client, "assurance": ASSURANCE})
            if gate.kind != "acceptance":
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
