"""SQLite is canonical; artifacts are immutable and events commit with task state."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .contracts import IntakeState
from .models import Artifact, OrchestratorError, TaskState, identifier
from .persistence import (
    EVENT_SCHEMA_VERSION,
    RUNTIME_DB_READABLE_VERSIONS,
    RUNTIME_DB_VERSION,
    decode_versioned_model_json,
    normalize_control_evidence,
    validate_database_version,
)
from .project import Project, atomic_write, confined, encode, read_text


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, project: Project, cancel_check: Callable[[], bool] = lambda: False):
        self.cancel_check = cancel_check
        self.project = project
        project.runtime.mkdir(parents=True, exist_ok=True)
        path = confined(project.root, ".orchestrator/runtime/state.sqlite3")
        for suffix in ("-wal", "-shm", "-journal"):
            confined(project.root, f".orchestrator/runtime/state.sqlite3{suffix}")
        self.db = sqlite3.connect(path, timeout=5)
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        try:
            validate_database_version("runtime", version, RUNTIME_DB_READABLE_VERSIONS)
        except OrchestratorError:
            self.db.close()
            raise
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, data TEXT NOT NULL, cancel_requested INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, kind TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS approvals (task_id TEXT NOT NULL, scope TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(task_id, scope));
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS intakes (id TEXT PRIMARY KEY, data TEXT NOT NULL);
        """)
        if version < RUNTIME_DB_VERSION:
            self.db.execute(f"PRAGMA user_version={RUNTIME_DB_VERSION}")

    def close(self) -> None:
        self.db.close()

    def get(self, task_id: str) -> TaskState:
        identifier(task_id)
        row = self.db.execute("SELECT data FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise OrchestratorError(f"unknown task: {task_id}")
        return decode_versioned_model_json(
            row[0], rule_key="task_state", model=TaskState
        )

    def save(
        self,
        state: TaskState,
        kind: str,
        payload: dict[str, Any] | None = None,
        *,
        create: bool = False,
        clear_approvals: bool = False,
    ) -> None:
        """Persist task state and its transition event in one transaction.

        Recovery may revoke approvals in the same transaction as the recovered
        state. This prevents a crash between "make runnable again" and
        "invalidate old authority" from leaving a replayable approval behind.
        """
        with self.db:
            if create:
                try:
                    self.db.execute("INSERT INTO tasks(id, data) VALUES (?, ?)", (state.spec.id, state.model_dump_json()))
                except sqlite3.IntegrityError as exc:
                    raise OrchestratorError(f"task already exists: {state.spec.id}") from exc
            else:
                cursor = self.db.execute(
                    "UPDATE tasks SET data=? WHERE id=?",
                    (state.model_dump_json(), state.spec.id),
                )
                if cursor.rowcount != 1:
                    raise OrchestratorError(f"task disappeared during durable state update: {state.spec.id}")
            if clear_approvals:
                cursor = self.db.execute("DELETE FROM approvals WHERE task_id=?", (state.spec.id,))
                self._event(
                    state.spec.id,
                    "execution.approvals_revoked",
                    {"count": cursor.rowcount, "reason": kind},
                )
            self._event(state.spec.id, kind, payload or {"status": state.status, "phase": state.phase})

    def _event(self, task_id: str | None, kind: str, payload: dict[str, Any]) -> None:
        self.db.execute("INSERT INTO events(task_id, kind, payload, created_at) VALUES (?, ?, ?, ?)", (task_id, kind, encode(payload), now()))

    def events(self, task_id: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT sequence,task_id,kind,payload,created_at FROM events"
        rows = self.db.execute(sql + (" WHERE task_id=?" if task_id else "") + " ORDER BY sequence", (task_id,) if task_id else ())
        return [
            {
                "schema_version": EVENT_SCHEMA_VERSION,
                "event_id": f"E-{seq}",
                "source": "runtime_event_log",
                "sequence": seq,
                "task_id": task,
                "kind": kind,
                "payload": json.loads(payload),
                "created_at": created,
            }
            for seq, task, kind, payload, created in rows
        ]

    def trust(self, profile_digest: str, actor: str) -> None:
        if not actor.strip():
            raise OrchestratorError("an approval actor is required")
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES ('trusted_profile',?)", (profile_digest,))
            self._event(None, "profile.trusted", {"digest": profile_digest, "actor": actor})

    def trusted(self, profile_digest: str) -> bool:
        row = self.db.execute("SELECT value FROM metadata WHERE key='trusted_profile'").fetchone()
        return bool(row and row[0] == profile_digest)

    def approve(self, state: TaskState, scope: str, actor: str) -> None:
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO approvals VALUES (?,?,?,?)", (state.spec.id, scope, actor, now()))
            self._event(state.spec.id, "execution.approved", {"scope": scope, "actor": actor})

    def approved(self, task_id: str, scope: str) -> bool:
        return self.db.execute("SELECT 1 FROM approvals WHERE task_id=? AND scope=?", (task_id, scope)).fetchone() is not None

    def cancelled(self, task_id: str) -> bool:
        if self.cancel_check():
            return True
        row = self.db.execute("SELECT cancel_requested FROM tasks WHERE id=?", (task_id,)).fetchone()
        return bool(row and row[0])

    def task_ids(self) -> list[str]:
        return [row[0] for row in self.db.execute("SELECT id FROM tasks ORDER BY id").fetchall()]

    def intake_ids(self) -> list[str]:
        return [row[0] for row in self.db.execute("SELECT id FROM intakes ORDER BY id").fetchall()]

    def active_intake_ids(self) -> list[str]:
        rows = self.db.execute("SELECT id,data FROM intakes ORDER BY id").fetchall()
        active: list[str] = []
        for intake_id, data in rows:
            intake = decode_versioned_model_json(
                data, rule_key="intake_state", model=IntakeState
            )
            if intake.status in ("running", "proposed", "needs_clarification"):
                active.append(intake_id)
        return active

    def active_task_ids(self) -> list[str]:
        rows = self.db.execute("SELECT id,data FROM tasks ORDER BY id").fetchall()
        active: list[str] = []
        for task_id, data in rows:
            state = decode_versioned_model_json(
                data, rule_key="task_state", model=TaskState
            )
            if state.status not in ("succeeded", "blocked", "failed", "cancelled", "abandoned"):
                active.append(task_id)
        return active

    def authorize_provider_permission(
        self, state: TaskState, scope: str, actor: str, permission: str
    ) -> None:
        if not actor.strip():
            raise OrchestratorError("an approval actor is required")
        with self.db:
            self.db.execute(
                "UPDATE tasks SET data=? WHERE id=?",
                (state.model_dump_json(), state.spec.id),
            )
            self.db.execute(
                "INSERT OR REPLACE INTO approvals VALUES (?,?,?,?)",
                (state.spec.id, scope, actor, now()),
            )
            self._event(
                state.spec.id,
                "provider_permission.approved",
                {"scope": scope, "actor": actor, "permission": permission, "attempt": state.attempt},
            )

    def cleanup_bindings(
        self, task_ids: list[str], intake_ids: list[str], actor: str, reason: str
    ) -> dict[str, list[str]]:
        if not actor.strip():
            raise OrchestratorError("an approval actor is required")
        tasks = [self.get(task_id) for task_id in task_ids]
        intakes = [self.get_intake(intake_id) for intake_id in intake_ids]
        for state in tasks:
            if state.status == "running":
                raise OrchestratorError(
                    f"running task cannot be abandoned: {state.spec.id}; stop/recover active execution first"
                )
            if state.status in ("succeeded", "blocked", "failed", "cancelled", "abandoned"):
                raise OrchestratorError(f"task is already terminal: {state.spec.id} ({state.status})")
        for intake in intakes:
            if intake.status == "running":
                raise OrchestratorError(
                    f"running intake cannot be withdrawn: {intake.id}; wait for Supervisor execution to finish"
                )
            if intake.status not in ("proposed", "needs_clarification"):
                raise OrchestratorError(
                    f"intake cannot be withdrawn: {intake.id} ({intake.status})"
                )

        with self.db:
            for state in tasks:
                state.status = "abandoned"
                state.provider_permission_grants = {}
                state.error = reason[:4000]
                self.db.execute(
                    "UPDATE tasks SET data=? WHERE id=?",
                    (state.model_dump_json(), state.spec.id),
                )
                self._event(
                    state.spec.id,
                    "task.abandoned",
                    {
                        "actor": actor,
                        "reason": reason[:2000],
                        "phase": state.phase,
                        "attempt": state.attempt,
                        "workspace_rollback": False,
                    },
                )
            for intake in intakes:
                intake.status = "withdrawn"
                intake.error = reason[:4000]
                self.db.execute(
                    "UPDATE intakes SET data=? WHERE id=?",
                    (intake.model_dump_json(), intake.id),
                )
                self._event(
                    None,
                    "intake.withdrawn",
                    {
                        "intake_id": intake.id,
                        "actor": actor,
                        "reason": reason[:2000],
                    },
                )
            self._event(
                None,
                "binding_cleanup.applied",
                {
                    "task_ids": task_ids,
                    "intake_ids": intake_ids,
                    "actor": actor,
                    "workspace_rollback": False,
                },
            )
        return {"task_ids": task_ids, "intake_ids": intake_ids}

    def request_cancel(self, task_id: str) -> None:
        state = self.get(task_id)
        if state.status == "succeeded":
            raise OrchestratorError("a completed task cannot be cancelled")
        with self.db:
            self.db.execute("UPDATE tasks SET cancel_requested=1 WHERE id=?", (task_id,))
            self._event(task_id, "cancel.requested", {})

    def artifact(self, state: TaskState, kind: str, value: Any) -> Artifact:
        artifact = self.write_artifact(state.spec.id, state.attempt, kind, value)
        state.artifacts.append(artifact)
        return artifact

    def write_artifact(self, owner: str, attempt: int, kind: str, value: Any) -> Artifact:
        identifier(owner)
        identifier(kind)
        artifact_id = "A-" + uuid.uuid4().hex
        relative = f".orchestrator/runtime/{owner}/{attempt}-{kind}-{artifact_id[2:]}.json"
        path = confined(self.project.root, relative)
        text = encode(value) + "\n"
        atomic_write(path, text)
        return Artifact(
            schema_version=2,
            id=artifact_id,
            owner_id=owner,
            created_at=now(),
            kind=kind,
            path=relative,
            sha256=hashlib.sha256(text.encode()).hexdigest(),
            attempt=attempt,
        )

    def read_artifact(self, artifact: Artifact) -> Any:
        path = confined(self.project.root, artifact.path)
        text = read_text(path, limit=1024 * 1024)
        if hashlib.sha256(text.encode()).hexdigest() != artifact.sha256:
            raise OrchestratorError(f"artifact integrity check failed: {artifact.path}")
        return normalize_control_evidence(artifact.kind, json.loads(text))

    def verify(self, state: TaskState) -> None:
        for artifact in state.artifacts:
            self.read_artifact(artifact)

    def latest(self, state: TaskState, kind: str) -> Any:
        for artifact in reversed(state.artifacts):
            if artifact.kind == kind:
                return self.read_artifact(artifact)
        return None


    def get_intake(self, intake_id: str) -> IntakeState:
        identifier(intake_id)
        row = self.db.execute("SELECT data FROM intakes WHERE id=?", (intake_id,)).fetchone()
        if row is None:
            raise OrchestratorError(f"unknown intake: {intake_id}")
        return decode_versioned_model_json(
            row[0], rule_key="intake_state", model=IntakeState
        )

    def save_intake(self, intake: IntakeState, kind: str, *, create: bool = False) -> None:
        with self.db:
            if create:
                self.db.execute("INSERT INTO intakes(id,data) VALUES (?,?)", (intake.id, intake.model_dump_json()))
            else:
                self.db.execute("UPDATE intakes SET data=? WHERE id=?", (intake.model_dump_json(), intake.id))
            self._event(None, kind, {"intake_id": intake.id, "status": intake.status, "calls": intake.calls})

    def create_from_intake(self, state: TaskState, intake: IntakeState, actor: str, scope: str) -> None:
        # The project lock serializes controllers; this transaction binds consumption
        # and task registration even if the process is interrupted afterwards.
        with self.db:
            try:
                self.db.execute("INSERT INTO tasks(id,data) VALUES (?,?)", (state.spec.id, state.model_dump_json()))
            except sqlite3.IntegrityError as exc:
                raise OrchestratorError(f"task already exists: {state.spec.id}") from exc
            intake.status = "consumed"
            self.db.execute("UPDATE intakes SET data=? WHERE id=?", (intake.model_dump_json(), intake.id))
            self._event(state.spec.id, "task.created", {
                "intake_id": intake.id, "risk": state.spec.risk,
                "profile_digest": state.profile_digest,
                "workflow_id": state.workflow_id,
                "workflow_digest": state.workflow_digest,
                "workflow_selection_source": state.workflow_selection_source,
            })
            self._event(state.spec.id, "intake.confirmed", {"intake_id": intake.id, "actor": actor, "scope": scope})
