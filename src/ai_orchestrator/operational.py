"""v0.15 operational diagnostics, backup/restore, and bounded retention.

Maintenance mutations are operator-only CLI actions.  Agent-facing services may
inspect diagnostics but never call restore/cleanup helpers.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import time
import uuid
import zipfile

import yaml
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import quote

from . import __version__
from .contracts import IntakeState
from .jobs import Job
from .models import EvidenceRef, OrchestratorError, TaskState
from .persistence import (
    HUMAN_GATE_DB_READABLE_VERSIONS,
    JOB_DB_READABLE_VERSIONS,
    RUNTIME_DB_READABLE_VERSIONS,
    decode_versioned_model_json,
    normalize_control_evidence,
    validate_database_version,
)
from .project import Project, confined, digest, encode

BACKUP_SCHEMA_VERSION = 1
MAINTENANCE_EVENT_SCHEMA_VERSION = 1
RETENTION_SCHEMA_VERSION = 1
MAX_DIAGNOSTIC_ROWS = 50000
MAX_BACKUP_FILES = 100000
MAX_BACKUP_BYTES = 2 * 1024 * 1024 * 1024
MAX_BACKUP_MANIFEST_BYTES = 64 * 1024 * 1024
IO_CHUNK_BYTES = 1024 * 1024
DEFAULT_RETENTION_DAYS = 30

_DB_SPECS = {
    "state": ("state.sqlite3", "runtime", RUNTIME_DB_READABLE_VERSIONS),
    "jobs": ("jobs.sqlite3", "job", JOB_DB_READABLE_VERSIONS),
    "gates": ("gates.sqlite3", "human-gate", HUMAN_GATE_DB_READABLE_VERSIONS),
}
_TERMINAL_TASKS = {"succeeded", "blocked", "failed", "cancelled", "abandoned"}
_TERMINAL_JOBS = {"succeeded", "failed", "cancelled", "interrupted"}
_TERMINAL_GATES = {"applied", "declined", "cancelled", "expired", "failed"}
_EPHEMERAL_RUNTIME_NAMES = {"workspace.lock", "worker.lock", "cancellation.lock"}
_SQLITE_SIDECARS = ("-wal", "-shm", "-journal")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(IO_CHUNK_BYTES)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def _maintenance_actor(actor: str) -> str:
    value = actor.strip()
    if (
        not value
        or len(value) > 256
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise OrchestratorError(
            "maintenance actor must be nonblank bounded printable text"
        )
    return value


def _validate_maintenance_identity(action: str, actor: str, scope: str) -> str:
    if action not in ("restore", "cleanup"):
        raise OrchestratorError("unsupported maintenance action")
    value = _maintenance_actor(actor)
    if not _is_sha256(scope):
        raise OrchestratorError("maintenance scope must be an exact sha256 digest")
    return value


def cutoff_from_days(days: int) -> str:
    if not 1 <= days <= 36500:
        raise OrchestratorError("retention days must be between 1 and 36500")
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def parse_cutoff(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OrchestratorError("retention cutoff must be ISO-8601 with timezone") from exc
    if parsed.tzinfo is None:
        raise OrchestratorError("retention cutoff must include a timezone")
    return parsed.astimezone(timezone.utc)


def _readonly_connection(path: Path) -> sqlite3.Connection:
    uri = "file:" + quote(str(path.resolve()), safe="/") + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True, timeout=2)
    connection.execute("PRAGMA query_only=ON")
    return connection


def _quick_database_report(path: Path, label: str, readable: tuple[int, ...]) -> dict[str, Any]:
    if not path.exists():
        return {
            "ok": True,
            "integrity_ok": True,
            "present": False,
            "path": str(path),
            "guidance": "database has not been created yet",
        }
    report: dict[str, Any] = {
        "ok": True,
        "integrity_ok": True,
        "present": True,
        "path": str(path),
    }
    try:
        connection = _readonly_connection(path)
        try:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            report["user_version"] = version
            validate_database_version(label, version, readable)
            quick = [row[0] for row in connection.execute("PRAGMA quick_check").fetchall()]
            report["quick_check"] = quick[:20]
            if quick != ["ok"]:
                report["ok"] = report["integrity_ok"] = False
                report["error"] = "SQLite quick_check failed"
            foreign = connection.execute("PRAGMA foreign_key_check").fetchmany(20)
            if foreign:
                report["ok"] = report["integrity_ok"] = False
                report["foreign_key_violations"] = [list(row) for row in foreign]
        finally:
            connection.close()
    except (sqlite3.DatabaseError, OSError, OrchestratorError) as exc:
        report["ok"] = report["integrity_ok"] = False
        report["error"] = str(exc)
    return report


def _read_task_states(path: Path) -> tuple[list[TaskState], list[str]]:
    if not path.exists():
        return [], []
    values: list[TaskState] = []
    errors: list[str] = []
    connection: sqlite3.Connection | None = None
    try:
        connection = _readonly_connection(path)
        rows = connection.execute("SELECT id,data FROM tasks ORDER BY id").fetchall()
        if len(rows) > MAX_DIAGNOSTIC_ROWS:
            return [], [f"task row count exceeds diagnostic bound ({MAX_DIAGNOSTIC_ROWS})"]
        for task_id, data in rows:
            try:
                state = decode_versioned_model_json(data, rule_key="task_state", model=TaskState)
                if state.spec.id != task_id:
                    raise OrchestratorError("task row ID does not match embedded TaskSpec ID")
                values.append(state)
            except (ValueError, OrchestratorError) as exc:
                errors.append(f"{task_id}: {exc}")
    except (sqlite3.DatabaseError, OSError, OrchestratorError) as exc:
        errors.append(str(exc))
    finally:
        if connection is not None:
            connection.close()
    return values, errors


def _read_intake_states(path: Path) -> tuple[list[IntakeState], list[str]]:
    if not path.exists():
        return [], []
    values: list[IntakeState] = []
    errors: list[str] = []
    connection: sqlite3.Connection | None = None
    try:
        connection = _readonly_connection(path)
        rows = connection.execute("SELECT id,data FROM intakes ORDER BY id").fetchall()
        if len(rows) > MAX_DIAGNOSTIC_ROWS:
            return [], [f"intake row count exceeds diagnostic bound ({MAX_DIAGNOSTIC_ROWS})"]
        for intake_id, data in rows:
            try:
                intake = decode_versioned_model_json(
                    data, rule_key="intake_state", model=IntakeState
                )
                if intake.id != intake_id:
                    raise OrchestratorError(
                        "intake row ID does not match embedded IntakeState ID"
                    )
                values.append(intake)
            except (ValueError, OrchestratorError) as exc:
                errors.append(f"{intake_id}: {exc}")
    except (sqlite3.DatabaseError, OSError, OrchestratorError) as exc:
        errors.append(str(exc))
    finally:
        if connection is not None:
            connection.close()
    return values, errors


def _read_exploration_states(path: Path):
    from .exploration import ExplorationState
    values, errors = [], []
    if not path.exists():
        return values, errors
    connection = None
    try:
        connection = _readonly_connection(path)
        exists = connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='explorations'").fetchone()
        if not exists:
            if connection.execute("PRAGMA user_version").fetchone()[0] >= 3:
                errors.append("runtime v3 is missing exploration state")
            return values, errors
        rows = connection.execute("SELECT id,data FROM explorations ORDER BY id").fetchmany(MAX_DIAGNOSTIC_ROWS + 1)
        if len(rows) > MAX_DIAGNOSTIC_ROWS:
            return [], ["exploration row count exceeds diagnostic bound"]
        for session_id, data in rows:
            try:
                state = decode_versioned_model_json(data, rule_key="exploration_state", model=ExplorationState)
                if state.id != session_id:
                    raise OrchestratorError("exploration row ID mismatch")
                values.append(state)
            except (ValueError, OrchestratorError) as exc:
                errors.append(f"{session_id}: {exc}")
    except (sqlite3.DatabaseError, OSError, OrchestratorError) as exc:
        errors.append(str(exc))
    finally:
        if connection is not None:
            connection.close()
    return values, errors


def _state_report(project: Project) -> dict[str, Any]:
    path = confined(project.root, ".orchestrator/runtime/state.sqlite3")
    report = _quick_database_report(path, "runtime", RUNTIME_DB_READABLE_VERSIONS)
    if not report["present"] or not report["integrity_ok"]:
        return report
    states, errors = _read_task_states(path)
    intakes, intake_errors = _read_intake_states(path)
    errors.extend(intake_errors)
    explorations, exploration_errors = _read_exploration_states(path)
    errors.extend(exploration_errors)
    from .evidence import inventory
    refs = inventory(project)
    errors.extend(refs["errors"])
    referenced = refs["paths"]
    artifact_ids = refs["ids"]
    missing, corrupt = refs["missing"], refs["corrupt"]
    if refs["conflicts"]:
        errors.append("conflicting artifact reference metadata")
    report["reference_conflicts"] = refs["conflicts"][:50]
    report["evidence_inventory_sha256"] = refs["fingerprint"]

    report.update(
        task_count=len(states),
        intake_count=len(intakes),
        exploration_count=len(explorations),
        unfinished_explorations=sorted(s.id for s in explorations if s.status in ("running", "proposing")),
        running_tasks=sorted(state.spec.id for state in states if state.status == "running"),
        active_tasks=sorted(
            state.spec.id for state in states if state.status not in _TERMINAL_TASKS
        ),
        referenced_artifacts=len(referenced),
        artifact_ids=len(artifact_ids),
        missing_artifacts=missing[:50],
        corrupt_artifacts=corrupt[:50],
        persisted_state_errors=errors[:50],
    )
    if errors or missing or corrupt:
        report["ok"] = report["integrity_ok"] = False
        report["guidance"] = (
            "do not rewrite runtime state; inspect the named rows/artifacts and restore "
            "from a verified v0.15 backup if required"
        )
    return report


def _lock_active(path: Path) -> bool | None:
    if os.name != "posix":
        return None
    if not path.exists():
        return False
    try:
        with path.open("r+") as stream:
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
                return False
    except OSError:
        return None


def _jobs_report(project: Project) -> dict[str, Any]:
    path = confined(project.root, ".orchestrator/runtime/jobs.sqlite3")
    report = _quick_database_report(path, "job", JOB_DB_READABLE_VERSIONS)
    worker_active = _lock_active(confined(project.root, ".orchestrator/runtime/worker.lock"))
    report["worker_active"] = worker_active
    if not report["present"] or not report["integrity_ok"]:
        return report
    errors: list[str] = []
    stale: list[str] = []
    expired: list[str] = []
    counts: dict[str, int] = {}
    try:
        connection = _readonly_connection(path)
        try:
            from .receipts import read_all
            report["request_receipts"] = len(read_all(connection))
            rows = connection.execute("SELECT id,status,data FROM jobs ORDER BY rowid").fetchall()
            if len(rows) > MAX_DIAGNOSTIC_ROWS:
                errors.append(f"job row count exceeds diagnostic bound ({MAX_DIAGNOSTIC_ROWS})")
            else:
                now = time.time()
                for job_id, status, data in rows:
                    try:
                        job = Job.model_validate_json(data)
                        if job.id != job_id or job.status != status:
                            raise OrchestratorError("job columns do not match encoded Job")
                        counts[status] = counts.get(status, 0) + 1
                        if status == "queued" and job.expires_at <= now:
                            expired.append(job_id)
                        if status == "running" and worker_active is False:
                            stale.append(job_id)
                    except (ValueError, OrchestratorError) as exc:
                        errors.append(f"{job_id}: {exc}")
        finally:
            connection.close()
    except (sqlite3.DatabaseError, OSError, OrchestratorError) as exc:
        errors.append(str(exc))
    report.update(counts=counts, stale_running=stale[:50], expired_queued=expired[:50], errors=errors[:50])
    if errors:
        report["ok"] = report["integrity_ok"] = False
    elif stale or expired:
        report["ok"] = False
        report["guidance"] = (
            "stale/expired jobs are not replayed automatically; start an operator worker "
            "to classify stale running jobs, or cancel/submit a fresh request as appropriate"
        )
    return report


def _gates_report(project: Project) -> dict[str, Any]:
    path = confined(project.root, ".orchestrator/runtime/gates.sqlite3")
    report = _quick_database_report(path, "human-gate", HUMAN_GATE_DB_READABLE_VERSIONS)
    controller_active = _lock_active(confined(project.root, ".orchestrator/runtime/workspace.lock"))
    report["controller_active"] = controller_active
    if not report["present"] or not report["integrity_ok"]:
        return report
    from .human_gates import HumanGate

    errors: list[str] = []
    expired: list[str] = []
    uncertain: list[str] = []
    counts: dict[str, int] = {}
    try:
        connection = _readonly_connection(path)
        try:
            rows = connection.execute(
                "SELECT id,status,expires_at,data FROM gates ORDER BY rowid"
            ).fetchall()
            if len(rows) > MAX_DIAGNOSTIC_ROWS:
                errors.append(f"gate row count exceeds diagnostic bound ({MAX_DIAGNOSTIC_ROWS})")
            else:
                now = time.time()
                for gate_id, status, expires_at, data in rows:
                    try:
                        gate = decode_versioned_model_json(
                            data, rule_key="human_gate", model=HumanGate
                        )
                        if gate.id != gate_id or gate.status != status:
                            raise OrchestratorError("gate columns do not match encoded HumanGate")
                        counts[status] = counts.get(status, 0) + 1
                        if status == "pending" and expires_at <= now:
                            expired.append(gate_id)
                        if status == "applying" and controller_active is False:
                            uncertain.append(gate_id)
                    except (ValueError, OrchestratorError) as exc:
                        errors.append(f"{gate_id}: {exc}")
        finally:
            connection.close()
    except (sqlite3.DatabaseError, OSError, OrchestratorError) as exc:
        errors.append(str(exc))
    report.update(
        counts=counts,
        expired_pending=expired[:50],
        effect_uncertain_applying=uncertain[:50],
        errors=errors[:50],
    )
    if errors:
        report["ok"] = report["integrity_ok"] = False
    elif expired or uncertain:
        report["ok"] = False
        report["guidance"] = (
            "pending gates may expire but never authorize by timeout; an applying gate is "
            "effect-uncertain and must not be replayed. Inspect with 'orchestrator gate'."
        )
    return report


def _worktree_report(project: Project) -> dict[str, Any]:
    base = confined(project.root, ".orchestrator/runtime/worktrees")
    state_path = confined(project.root, ".orchestrator/runtime/state.sqlite3")
    states, errors = _read_task_states(state_path)
    status = {state.spec.id: state.status for state in states}
    stale: list[str] = []
    active: list[str] = []
    malformed: list[str] = []
    if base.exists():
        for task_dir in sorted(base.iterdir()):
            if not task_dir.is_dir() or task_dir.is_symlink():
                malformed.append(str(task_dir))
                continue
            task_id = task_dir.name
            value = status.get(task_id)
            if value == "running":
                active.append(str(task_dir))
            else:
                stale.append(str(task_dir))
    return {
        "ok": not errors and not malformed and not stale,
        "integrity_ok": not errors and not malformed,
        "path": str(base),
        "active": active[:50],
        "stale": stale[:50],
        "malformed": malformed[:50],
        "state_errors": errors[:50],
        "guidance": (
            "stale disposable worktrees can be removed only through an explicit retention "
            "cleanup scope; running-task worktrees belong to conservative recovery"
            if stale
            else "no stale disposable worktrees detected"
        ),
    }


def _maintenance_log_report(project: Project) -> dict[str, Any]:
    path = confined(project.root, ".orchestrator/runtime/maintenance.jsonl")
    if not path.exists():
        return {
            "ok": True,
            "integrity_ok": True,
            "present": False,
            "events": 0,
            "path": str(path),
        }
    errors: list[str] = []
    events = 0
    try:
        with path.open("r", encoding="utf-8") as stream:
            for index, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                events += 1
                if events > MAX_DIAGNOSTIC_ROWS:
                    errors.append(
                        f"maintenance event count exceeds diagnostic bound ({MAX_DIAGNOSTIC_ROWS})"
                    )
                    break
                if len(line.encode("utf-8")) > 64 * 1024:
                    errors.append(f"line {index}: maintenance event exceeds 64 KiB")
                    continue
                try:
                    item = json.loads(line)
                    if not isinstance(item, dict):
                        raise ValueError("maintenance event must be an object")
                    if item.get("schema_version") != MAINTENANCE_EVENT_SCHEMA_VERSION:
                        raise ValueError("unsupported maintenance event schema")
                    if item.get("action") not in ("restore", "cleanup"):
                        raise ValueError("unsupported maintenance action")
                    actor = item.get("actor")
                    if not isinstance(actor, str):
                        raise ValueError("maintenance actor must be text")
                    _maintenance_actor(actor)
                    if not _is_sha256(item.get("scope")):
                        raise ValueError("maintenance scope is invalid")
                    event_id = item.get("id")
                    if (
                        not isinstance(event_id, str)
                        or not event_id.startswith("M-")
                        or len(event_id) != 34
                    ):
                        raise ValueError("maintenance event ID is invalid")
                    created = datetime.fromisoformat(
                        str(item.get("created_at", "")).replace("Z", "+00:00")
                    )
                    if created.tzinfo is None:
                        raise ValueError(
                            "maintenance event timestamp must include timezone"
                        )
                    if not isinstance(item.get("details"), dict):
                        raise ValueError("maintenance event details must be an object")
                except (
                    json.JSONDecodeError,
                    ValueError,
                    OrchestratorError,
                ) as exc:
                    errors.append(f"line {index}: {exc}")
    except (OSError, UnicodeDecodeError) as exc:
        errors.append(str(exc))
    return {
        "ok": not errors,
        "integrity_ok": not errors,
        "present": True,
        "events": events,
        "errors": errors[:50],
        "path": str(path),
    }

def diagnose_runtime(root: Path) -> dict[str, Any]:
    project = Project(root.resolve())
    from .maintenance import inspect as inspect_maintenance
    reports = {
        "runtime:journal": inspect_maintenance(project),
        "runtime:state": _state_report(project),
        "runtime:jobs": _jobs_report(project),
        "runtime:gates": _gates_report(project),
        "runtime:workspaces": _worktree_report(project),
        "runtime:maintenance": _maintenance_log_report(project),
    }
    return reports


def _append_maintenance(
    project: Project,
    *,
    action: str,
    actor: str,
    scope: str,
    details: dict[str, Any],
) -> dict[str, Any]:
    actor = _validate_maintenance_identity(action, actor, scope)
    event = {
        "schema_version": MAINTENANCE_EVENT_SCHEMA_VERSION,
        "id": "M-" + uuid.uuid4().hex,
        "action": action,
        "actor": actor,
        "scope": scope,
        "created_at": utc_now(),
        "details": details,
    }
    line = encode(event) + "\n"
    if len(line.encode("utf-8")) > 64 * 1024:
        raise OrchestratorError("maintenance audit event exceeds 64 KiB")
    path = confined(project.root, ".orchestrator/runtime/maintenance.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(line)
        stream.flush()
        os.fsync(stream.fileno())
    from .maintenance import sync_directory
    sync_directory(path.parent)
    return event


def _runtime_excluded(relative: str) -> bool:
    prefix = ".orchestrator/runtime/"
    if not relative.startswith(prefix):
        return False
    tail = relative[len(prefix):]
    if tail == "maintenance-journal" or tail.startswith("maintenance-journal/"):
        return True
    if tail == "worktrees" or tail.startswith("worktrees/"):
        return True
    if tail in _EPHEMERAL_RUNTIME_NAMES:
        return True
    if any(tail.endswith(suffix) for suffix in _SQLITE_SIDECARS):
        return True
    return False


def _iter_managed_files(project: Project, mode: str) -> list[Path]:
    if mode not in ("runtime", "full"):
        raise OrchestratorError("backup mode must be 'runtime' or 'full'")
    base = project.runtime if mode == "runtime" else project.control
    if not base.exists():
        return []
    values: list[Path] = []
    for path in sorted(base.rglob("*")):
        relative = path.relative_to(project.root).as_posix()
        confined(project.root, relative)
        if _runtime_excluded(relative):
            continue
        if path.is_symlink():
            raise OrchestratorError(f"backup refuses symlinked control/runtime path: {relative}")
        if path.is_file():
            values.append(path)
            if len(values) > MAX_BACKUP_FILES:
                raise OrchestratorError("backup file count exceeds safety bound")
    return values


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        from .maintenance import sync_directory
        sync_directory(path.parent)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def _atomic_copy_stream(
    path: Path,
    source: Any,
    *,
    expected_bytes: int | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    copied = 0
    try:
        with temporary.open("xb") as destination:
            while True:
                chunk = source.read(IO_CHUNK_BYTES)
                if not chunk:
                    break
                copied += len(chunk)
                if copied > MAX_BACKUP_BYTES:
                    raise OrchestratorError("backup member exceeds safety bound")
                destination.write(chunk)
            destination.flush()
            os.fsync(destination.fileno())
        if expected_bytes is not None and copied != expected_bytes:
            raise OrchestratorError("backup member size changed while staging")
        os.replace(temporary, path)
        from .maintenance import sync_directory
        sync_directory(path.parent)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


def _atomic_copy_file(source: Path, destination: Path) -> None:
    with source.open("rb") as stream:
        _atomic_copy_stream(
            destination,
            stream,
            expected_bytes=source.stat().st_size,
        )


def _snapshot_sqlite(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    src = _readonly_connection(source)
    dst = sqlite3.connect(destination)
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def _copy_snapshot_file(source: Path, destination: Path) -> None:
    if source.name in {spec[0] for spec in _DB_SPECS.values()} and source.parent.name == "runtime":
        _snapshot_sqlite(source, destination)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination, follow_symlinks=False)


def _trusted_profile(path: Path) -> str | None:
    if not path.exists():
        return None
    try:
        connection = _readonly_connection(path)
        try:
            row = connection.execute(
                "SELECT value FROM metadata WHERE key='trusted_profile'"
            ).fetchone()
            return row[0] if row else None
        finally:
            connection.close()
    except sqlite3.DatabaseError:
        return None


def create_backup(
    root: Path,
    output: Path,
    *,
    mode: str,
    replace: bool = False,
) -> dict[str, Any]:
    project = Project(root.resolve())
    output = output.expanduser().resolve()
    control = project.control.resolve()
    if output == control or control in output.parents:
        raise OrchestratorError("backup output must be outside .orchestrator")
    if output.exists() and not replace:
        raise OrchestratorError("backup output already exists; pass --replace explicitly")
    from .worker import worker_lock

    from .maintenance import cancellation_boundary
    with worker_lock(project), project.lock(), cancellation_boundary(project, exclusive=True), tempfile.TemporaryDirectory(
        prefix="ai-orchestrator-backup-"
    ) as temporary:
        _profile, profile_digest, _context = project.load()
        stage = Path(temporary)
        source_files = _iter_managed_files(project, mode)
        staged: list[tuple[str, Path]] = []
        total = 0
        for source in source_files:
            relative = source.relative_to(project.root).as_posix()
            destination = stage / relative
            _copy_snapshot_file(source, destination)
            size = destination.stat().st_size
            total += size
            if total > MAX_BACKUP_BYTES:
                raise OrchestratorError("backup exceeds 2 GiB safety bound")
            staged.append((relative, destination))

        files = [
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
            for relative, path in staged
        ]
        manifest = {
            "schema_version": BACKUP_SCHEMA_VERSION,
            "kind": "ai-orchestrator-backup",
            "mode": mode,
            "created_at": utc_now(),
            "source_version": __version__,
            "source_profile_digest": profile_digest,
            "source_trusted_profile": _trusted_profile(
                stage / ".orchestrator/runtime/state.sqlite3"
            ),
            "file_count": len(files),
            "total_bytes": sum(item["bytes"] for item in files),
            "files": files,
            "excluded": [
                ".orchestrator/runtime/worktrees/",
                ".orchestrator/runtime/workspace.lock",
                ".orchestrator/runtime/worker.lock",
            ".orchestrator/runtime/cancellation.lock",
                "SQLite WAL/SHM/journal sidecars (folded into database snapshots)",
            ],
        }
        scope = digest(manifest)
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary_output = output.with_name(output.name + ".tmp-" + uuid.uuid4().hex)
        try:
            with zipfile.ZipFile(
                temporary_output, "w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                archive.writestr("manifest.json", encode(manifest) + "\n")
                for relative, path in staged:
                    archive.write(path, relative)
            os.replace(temporary_output, output)
        finally:
            with contextlib.suppress(FileNotFoundError):
                temporary_output.unlink()
    return {
        "path": str(output),
        "mode": mode,
        "scope": scope,
        "manifest": manifest,
        "authority": (
            "full backup contains project authority and runtime trust state"
            if mode == "full"
            else "runtime evidence only; current project authority is not included"
        ),
    }


def _safe_member_name(name: str) -> str:
    if "\\" in name:
        raise OrchestratorError("backup contains a non-portable path")
    candidate = Path(name)
    if candidate.is_absolute() or name.startswith("/") or any(part in ("", ".", "..") for part in candidate.parts):
        raise OrchestratorError("backup contains an unsafe path")
    return candidate.as_posix()


def inspect_backup(path: Path) -> dict[str, Any]:
    path = path.expanduser().resolve()
    if not path.is_file():
        raise OrchestratorError("backup archive does not exist")
    try:
        with zipfile.ZipFile(path, "r") as archive:
            members = archive.infolist()
            names = [_safe_member_name(item.filename) for item in members]
            if len(names) != len(set(names)):
                raise OrchestratorError("backup contains duplicate paths")
            if "manifest.json" not in names:
                raise OrchestratorError("backup manifest is missing")
            if len(names) > MAX_BACKUP_FILES + 1:
                raise OrchestratorError("backup file count exceeds safety bound")

            manifest_info = archive.getinfo("manifest.json")
            if manifest_info.file_size > MAX_BACKUP_MANIFEST_BYTES:
                raise OrchestratorError("backup manifest exceeds safety bound")
            manifest = json.loads(archive.read(manifest_info).decode("utf-8"))
            if not isinstance(manifest, dict):
                raise OrchestratorError("backup manifest must be a JSON object")
            expected_manifest_keys = {
                "schema_version",
                "kind",
                "mode",
                "created_at",
                "source_version",
                "source_profile_digest",
                "source_trusted_profile",
                "file_count",
                "total_bytes",
                "files",
                "excluded",
            }
            if set(manifest) != expected_manifest_keys:
                raise OrchestratorError(
                    "backup manifest v1 has unknown or missing fields"
                )
            if (
                manifest.get("schema_version") != BACKUP_SCHEMA_VERSION
                or manifest.get("kind") != "ai-orchestrator-backup"
            ):
                raise OrchestratorError("unsupported backup manifest")
            mode = manifest.get("mode")
            if mode not in ("runtime", "full"):
                raise OrchestratorError("backup manifest has invalid mode")
            if not isinstance(manifest.get("source_version"), str) or not (
                1 <= len(manifest["source_version"]) <= 100
            ):
                raise OrchestratorError("backup source version is invalid")
            if not _is_sha256(manifest.get("source_profile_digest")):
                raise OrchestratorError("backup source profile digest is invalid")
            trusted_profile = manifest.get("source_trusted_profile")
            if trusted_profile is not None and not _is_sha256(trusted_profile):
                raise OrchestratorError("backup trusted-profile digest is invalid")
            try:
                created_at = datetime.fromisoformat(
                    str(manifest.get("created_at", "")).replace("Z", "+00:00")
                )
            except ValueError as exc:
                raise OrchestratorError("backup creation timestamp is invalid") from exc
            if created_at.tzinfo is None:
                raise OrchestratorError("backup creation timestamp must include timezone")

            excluded = manifest.get("excluded")
            if (
                not isinstance(excluded, list)
                or len(excluded) > 16
                or any(
                    not isinstance(item, str) or not item or len(item) > 512
                    for item in excluded
                )
            ):
                raise OrchestratorError("backup exclusion metadata is invalid")

            file_count = manifest.get("file_count")
            total_bytes = manifest.get("total_bytes")
            files = manifest.get("files")
            if type(file_count) is not int or not 0 <= file_count <= MAX_BACKUP_FILES:
                raise OrchestratorError("backup manifest file count is invalid")
            if type(total_bytes) is not int or not 0 <= total_bytes <= MAX_BACKUP_BYTES:
                raise OrchestratorError("backup manifest total byte count is invalid")
            if not isinstance(files, list) or len(files) != file_count:
                raise OrchestratorError("backup manifest file count is inconsistent")

            expected_names = {"manifest.json"}
            total = 0
            for item in files:
                if not isinstance(item, dict) or set(item) != {
                    "path",
                    "bytes",
                    "sha256",
                }:
                    raise OrchestratorError("backup manifest file entry is invalid")
                if not isinstance(item.get("path"), str):
                    raise OrchestratorError("backup manifest path is invalid")
                relative = _safe_member_name(item["path"])
                if relative in expected_names:
                    raise OrchestratorError("backup manifest contains duplicate file entries")
                if not relative.startswith(".orchestrator/"):
                    raise OrchestratorError("backup may contain only .orchestrator paths")
                if mode == "runtime" and not relative.startswith(
                    ".orchestrator/runtime/"
                ):
                    raise OrchestratorError(
                        "runtime backup contains project-authority paths"
                    )
                if _runtime_excluded(relative):
                    raise OrchestratorError(
                        "backup contains disposable/ephemeral runtime state"
                    )
                declared_bytes = item.get("bytes")
                declared_sha = item.get("sha256")
                if (
                    type(declared_bytes) is not int
                    or declared_bytes < 0
                    or declared_bytes > MAX_BACKUP_BYTES
                    or not _is_sha256(declared_sha)
                ):
                    raise OrchestratorError(
                        f"backup manifest metadata is invalid: {relative}"
                    )
                total += declared_bytes
                if total > MAX_BACKUP_BYTES:
                    raise OrchestratorError("backup exceeds 2 GiB safety bound")

                expected_names.add(relative)
                info = archive.getinfo(relative)
                if info.is_dir() or info.file_size != declared_bytes:
                    raise OrchestratorError(f"backup size mismatch: {relative}")
                hasher = hashlib.sha256()
                actual_bytes = 0
                with archive.open(info, "r") as stream:
                    while True:
                        chunk = stream.read(IO_CHUNK_BYTES)
                        if not chunk:
                            break
                        actual_bytes += len(chunk)
                        if actual_bytes > declared_bytes:
                            raise OrchestratorError(
                                f"backup member exceeded declared size: {relative}"
                            )
                        hasher.update(chunk)
                if actual_bytes != declared_bytes:
                    raise OrchestratorError(f"backup size mismatch: {relative}")
                if hasher.hexdigest() != declared_sha:
                    raise OrchestratorError(f"backup hash mismatch: {relative}")

            if set(names) != expected_names:
                raise OrchestratorError("backup archive contains unmanifested files")
            if total != total_bytes:
                raise OrchestratorError("backup total byte count is inconsistent")
    except (
        zipfile.BadZipFile,
        KeyError,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ) as exc:
        raise OrchestratorError("backup archive is malformed") from exc
    return {
        "path": str(path),
        "mode": manifest["mode"],
        "scope": digest(manifest),
        "manifest": manifest,
        "verified": True,
    }

def _runtime_activity(
    project: Project,
    *,
    readable: dict[str, bool] | None = None,
) -> dict[str, list[str]]:
    activity = {"tasks": [], "jobs": [], "gates": [], "explorations": []}
    readable = readable or {"state": True, "jobs": True, "gates": True}

    if readable.get("state", True):
        state_path = confined(project.root, ".orchestrator/runtime/state.sqlite3")
        states, errors = _read_task_states(state_path)
        if errors:
            raise OrchestratorError(
                "cannot determine task quiescence from inconsistent runtime state"
            )
        sessions, errors = _read_exploration_states(state_path)
        if errors:
            raise OrchestratorError("cannot determine exploration quiescence from inconsistent state")
        activity["explorations"] = sorted(s.id for s in sessions if s.status in ("running", "proposing"))
        activity["tasks"] = sorted(
            state.spec.id for state in states if state.status == "running"
        )

    jobs_path = confined(project.root, ".orchestrator/runtime/jobs.sqlite3")
    if readable.get("jobs", True) and jobs_path.exists():
        connection = _readonly_connection(jobs_path)
        try:
            for job_id, _status in connection.execute(
                "SELECT id,status FROM jobs "
                "WHERE status IN ('queued','running') ORDER BY id"
            ).fetchall():
                activity["jobs"].append(job_id)
        finally:
            connection.close()

    gates_path = confined(project.root, ".orchestrator/runtime/gates.sqlite3")
    if readable.get("gates", True) and gates_path.exists():
        connection = _readonly_connection(gates_path)
        try:
            for gate_id, _status in connection.execute(
                "SELECT id,status FROM gates "
                "WHERE status IN ('pending','applying') ORDER BY id"
            ).fetchall():
                activity["gates"].append(gate_id)
        finally:
            connection.close()
    return activity

def _assert_quiescent(
    project: Project,
    *,
    readable: dict[str, bool] | None = None,
) -> None:
    activity = _runtime_activity(project, readable=readable)
    if any(activity.values()):
        raise OrchestratorError(
            "maintenance requires a quiescent project; running tasks, queued/running "
            "jobs, or pending/applying HumanGates must be resolved first: "
            + encode(activity)
        )


def _assert_restore_worktrees_clear(project: Project) -> None:
    root = confined(project.root, ".orchestrator/runtime/worktrees")
    if root.is_symlink():
        raise OrchestratorError(
            "restore refuses a symlinked disposable-worktree root"
        )
    if not root.exists():
        return
    entries = sorted(path.name for path in root.iterdir())
    if entries:
        raise OrchestratorError(
            "restore requires disposable worktrees to be recovered/cleaned first: "
            + ", ".join(entries[:20])
        )


def _remove_runtime_sidecars(project: Project) -> None:
    for filename, _label, _readable in _DB_SPECS.values():
        for suffix in _SQLITE_SIDECARS:
            with contextlib.suppress(FileNotFoundError):
                confined(
                    project.root, f".orchestrator/runtime/{filename}{suffix}"
                ).unlink()


def _remove_managed_files(project: Project, mode: str) -> None:
    for path in reversed(_iter_managed_files(project, mode)):
        with contextlib.suppress(FileNotFoundError):
            path.unlink()
            from .maintenance import sync_directory, checkpoint
            sync_directory(path.parent)
            checkpoint("after_file_remove")
    _remove_runtime_sidecars(project)
    if mode in ("runtime", "full"):
        worktrees = confined(project.root, ".orchestrator/runtime/worktrees")
        if worktrees.exists():
            shutil.rmtree(worktrees)


def _restore_stage(stage: Path, project: Project, manifest: dict[str, Any]) -> None:
    for item in manifest["files"]:
        relative = item["path"]
        source = stage / relative
        destination = confined(project.root, relative)
        _atomic_copy_file(source, destination)
        from .maintenance import sync_directory, checkpoint
        sync_directory(destination.parent)
        checkpoint("after_file_replace")


def _stage_archive(path: Path, destination: Path, manifest: dict[str, Any]) -> None:
    with zipfile.ZipFile(path, "r") as archive:
        for item in manifest["files"]:
            relative = item["path"]
            target = destination / relative
            with archive.open(relative, "r") as source:
                _atomic_copy_stream(
                    target,
                    source,
                    expected_bytes=item["bytes"],
                )


def _iter_rollback_files(project: Project, mode: str) -> list[Path]:
    if mode not in ("runtime", "full"):
        raise OrchestratorError("restore mode must be 'runtime' or 'full'")
    base = project.runtime if mode == "runtime" else project.control
    if not base.exists():
        return []
    values: list[Path] = []
    for path in sorted(base.rglob("*")):
        relative = path.relative_to(project.root).as_posix()
        confined(project.root, relative)
        if relative.startswith(".orchestrator/runtime/maintenance-journal"):
            continue
        if relative.startswith(".orchestrator/runtime/worktrees/"):
            continue
        if relative in (
            ".orchestrator/runtime/workspace.lock",
            ".orchestrator/runtime/worker.lock",
            ".orchestrator/runtime/cancellation.lock",
        ):
            continue
        if path.is_symlink():
            raise OrchestratorError(
                f"restore rollback staging refuses symlinked control/runtime path: {relative}"
            )
        if path.is_file():
            values.append(path)
            if len(values) > MAX_BACKUP_FILES:
                raise OrchestratorError(
                    "restore rollback file count exceeds safety bound"
                )
    return values


def _stage_current(project: Project, mode: str, destination: Path) -> None:
    # Rollback staging is a raw byte-for-byte snapshot made while both
    # maintenance locks are held. Unlike a portable backup it includes SQLite
    # sidecars so even a currently malformed database can be restored exactly
    # if the requested restore fails.
    total = 0
    for source in _iter_rollback_files(project, mode):
        relative = source.relative_to(project.root).as_posix()
        size = source.stat().st_size
        total += size
        if total > MAX_BACKUP_BYTES:
            raise OrchestratorError("restore rollback snapshot exceeds 2 GiB safety bound")
        destination_path = destination / relative
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination_path, follow_symlinks=False)


def _structural_runtime_ok(project: Project) -> tuple[bool, dict[str, Any]]:
    reports = diagnose_runtime(project.root)
    structural = all(
        reports[key].get("integrity_ok", False)
        for key in ("runtime:state", "runtime:jobs", "runtime:gates", "runtime:maintenance")
    )
    return structural, reports


def restore_backup(
    root: Path, archive_path: Path, *, scope: str, actor: str, replace: bool,
    acknowledge_authority_restore: bool = False,
    acknowledge_unreadable_current_state: bool = False,
    acknowledge_incomplete_operation: str | None = None,
) -> dict[str, Any]:
    from . import maintenance, receipts
    from .safety import operator_only
    from .build_identity import assert_current
    from .worker import worker_lock
    operator_only(); assert_current()
    if not replace:
        raise OrchestratorError("restore requires explicit --replace acknowledgement")
    actor = _validate_maintenance_identity("restore", actor, scope)
    inspected = inspect_backup(archive_path)
    if inspected["scope"] != scope:
        raise OrchestratorError("backup scope changed; inspect the archive again before restore")
    mode = inspected["mode"]
    if mode == "full" and not acknowledge_authority_restore:
        raise OrchestratorError("full restore requires --ack-authority-restore")
    project = Project(root.resolve())
    had_control = project.control.exists()
    with worker_lock(project), project.lock(maintenance=True), maintenance.cancellation_boundary(project, exclusive=True):
        pending = maintenance.inspect(project)
        if pending["pending"]:
            if pending["reconciliation_scope"] != acknowledge_incomplete_operation:
                raise OrchestratorError("maintenance_pending: inspect and acknowledge the exact incomplete operation")
        elif acknowledge_incomplete_operation is not None:
            raise OrchestratorError("no incomplete operation matches this acknowledgement")
        unreadable = []
        try:
            project.load()
        except (OSError, ValueError, OrchestratorError, yaml.YAMLError):
            if mode != "full":
                raise OrchestratorError("runtime restore requires readable current project authority")
            if had_control:
                unreadable.append("project_authority")
                if not acknowledge_unreadable_current_state:
                    raise OrchestratorError("current project authority is unreadable; --ack-unreadable-current-state required")
        reports = diagnose_runtime(project.root)
        readable = {key: reports["runtime:"+key].get("integrity_ok", False) for key in ("state","jobs","gates")}
        unreadable += [key for key, ok in readable.items() if not ok]
        if not reports["runtime:maintenance"]["integrity_ok"]: unreadable.append("maintenance")
        if unreadable and not acknowledge_unreadable_current_state:
            raise OrchestratorError("current runtime state is inconsistent; --ack-unreadable-current-state required")
        if not pending["pending"]:
            _assert_quiescent(project, readable=readable)
            _assert_restore_worktrees_clear(project)
        else:
            # Recovery may replace a partially restored job/gate DB. Worker/project
            # locks and the persistent barrier, not those partially replaced rows,
            # are the proof that no cooperating execution is active.
            prior = maintenance._read(project) if pending.get("valid") else None
            allowed = set((prior or {}).get("targets", {}).get("worktrees", []))
            worktrees = confined(project.root, '.orchestrator/runtime/worktrees')
            if worktrees.exists():
                for path in worktrees.iterdir():
                    if path.relative_to(project.root).as_posix() not in allowed:
                        raise OrchestratorError("recovery restore refuses an unrecorded worktree; conservative recovery required")
        current_receipts = {}
        current_tombstones = set()
        jobpath = confined(project.root, '.orchestrator/runtime/jobs.sqlite3')
        if jobpath.exists() and readable["jobs"]:
            connection = _readonly_connection(jobpath)
            try:
                current_tombstones = set(receipts.read_all(connection))
                current_receipts = receipts.collect(connection, include_jobs=True)
            finally: connection.close()
        coverage = ('current-and-archive' if jobpath.exists() and readable['jobs'] else
                    'archive-only; current request history unreadable' if jobpath.exists() else
                    'archive-only; no current jobs database')
        # Freeze and validate before publishing an intent. Negative archive/scope
        # tests must not leave a destructive operation marker behind.
        with tempfile.TemporaryDirectory(prefix='orchestrator-restore-preflight-') as temp:
            frozen_path = Path(temp)/'frozen.zip'
            _atomic_copy_file(Path(inspected['path']), frozen_path)
            frozen = inspect_backup(frozen_path)
            if frozen['scope'] != scope:
                raise OrchestratorError('backup changed after inspection')
            stage = Path(temp)/'incoming'
            _stage_archive(frozen_path, stage, frozen['manifest'])
            revocations = _prepare_restored_runtime(Project(stage), current_receipts, current_tombstones)
            handle = maintenance.begin(project, action='restore', actor=actor, scope=scope,
                mode=mode, acknowledge_incomplete=acknowledge_incomplete_operation)
            opdir = maintenance.directory(project, handle)
            incoming, rollback = opdir/'incoming', opdir/'before'
            try:
                shutil.copytree(stage, incoming)
                _atomic_copy_file(frozen_path, opdir/'archive.zip')
                _stage_current(project, mode, rollback)
                maintenance.sync_tree(opdir)
                handle['rollback_ready'] = True
                maintenance.applying(project, handle)
                _remove_managed_files(project, mode)
                _restore_stage(incoming, project, _file_manifest(incoming))
                maintenance.checkpoint('after_db_commit')
                structural, _ = _structural_runtime_ok(project)
                if not structural:
                    raise OrchestratorError('restored runtime failed structural integrity checks')
                current_digest = project.load()[1]
                if mode == 'full' and current_digest != frozen['manifest']['source_profile_digest']:
                    raise OrchestratorError('full restore profile digest does not match the verified backup')
                maintenance.verified(project, handle)
                maintenance.checkpoint('before_audit')
                event = _append_maintenance(project, action='restore', actor=actor, scope=scope,
                    details={'operation_id':handle['operation_id'], 'mode':mode,
                             'archive':Path(inspected['path']).name,
                             'source_version':frozen['manifest']['source_version'],
                             'source_profile_digest':frozen['manifest']['source_profile_digest'],
                             'source_trusted_profile':frozen['manifest']['source_trusted_profile'],
                             'authority_restore':mode=='full', 'authorization_revocations':revocations,
                             'request_receipt_coverage':coverage,
                             'unreadable_current_state_acknowledged':bool(unreadable),
                             'unreadable_current_components':unreadable,
                             'superseded_incomplete_operation':pending['pending'],
                             'automatic_replay':False})
                maintenance.finish(project, handle, event)
            except Exception:
                # Restore rollback is part of this exact authorized operation,
                # not a replay on restart. A second failure leaves the marker.
                if handle.get('rollback_ready'):
                    maintenance.checkpoint('before_rollback')
                    _remove_managed_files(project, mode)
                    _restore_stage(rollback, project, _file_manifest(rollback, include_sidecars=True))
                    maintenance.checkpoint('after_rollback')
                if maintenance.snapshot(project, mode) == handle['before']:
                    handle['phase'] = 'rolled_back'
                    maintenance._save(project, handle)
                    event = _append_maintenance(project, action='restore', actor=actor, scope=scope,
                        details={'operation_id':handle['operation_id'], 'outcome':'rolled_back',
                                 'automatic_replay':False})
                    # A recovery rollback restores the prior incomplete state;
                    # it must remain blocked, never clear the predecessor barrier.
                    if not pending['pending']: maintenance.finish(project, handle, event)
                raise
        current_digest = project.load()[1]
        trusted = _trusted_profile(confined(project.root, '.orchestrator/runtime/state.sqlite3'))
        return {'restored':True,'mode':mode,'scope':scope, 'current_profile_digest':current_digest,
                'source_profile_digest':frozen['manifest']['source_profile_digest'],
                'profile_matches_backup':current_digest==frozen['manifest']['source_profile_digest'],
                'restored_trusted_profile':trusted, 'current_profile_trusted':trusted==current_digest,
                'retrust_required':trusted!=current_digest, 'maintenance_event':event,
                'request_receipt_coverage':coverage, 'automatic_replay':False}


def _file_manifest(root: Path, *, include_sidecars=False) -> dict:
    return {'files':[{'path':path.relative_to(root).as_posix()} for path in sorted(root.rglob('*'))
                     if path.is_file() and (include_sidecars or not _runtime_excluded(path.relative_to(root).as_posix()))]}


def _prepare_restored_runtime(project: Project, known: dict, tombstones: set[str] | None = None) -> dict:
    """Stage explicit no-replay invalidation before any target replacement."""
    from . import receipts
    from .jobs import JobQueue, Job
    tombstones = set(known) if tombstones is None else tombstones
    revoked = {'queued_running_jobs':0, 'nonterminal_gates':0, 'execution_approvals':0, 'permission_grants':0}
    jobpath = confined(project.root, '.orchestrator/runtime/jobs.sqlite3')
    if jobpath.exists() or known:
        queue = JobQueue(project)
        try:
            with queue.db:
                queue.db.execute('BEGIN IMMEDIATE')
                archived = receipts.collect(queue.db, include_jobs=True)
                for request_id, ref in known.items():
                    if request_id in archived: receipts.compatible(ref, archived[request_id])
                    retained = queue.db.execute('SELECT status FROM jobs WHERE request_id=?', (request_id,)).fetchone()
                    if request_id in tombstones or retained is None or retained[0] not in receipts.TERMINAL:
                        receipts.insert(queue.db, ref)
                for job_id, data in queue.db.execute("SELECT id,data FROM jobs WHERE status IN ('queued','running')").fetchall():
                    job = Job.model_validate_json(data)
                    job.status = 'interrupted'
                    job.error = 'Restored pending work is not replayed; inspect history and make an explicit new request.'
                    queue.db.execute("UPDATE jobs SET status='interrupted',data=? WHERE id=?", (job.model_dump_json(), job_id))
                    row = queue.db.execute('SELECT id,request_id,fingerprint,action,status,data FROM jobs WHERE id=?', (job_id,)).fetchone()
                    receipts.insert(queue.db, receipts.from_job_row(row))
                    queue._event(job_id, 'restore.interrupted')
                    revoked['queued_running_jobs'] += 1
        finally: queue.close()
    gatespath = confined(project.root, '.orchestrator/runtime/gates.sqlite3')
    if gatespath.exists():
        from .human_gates import HumanGate
        conn = sqlite3.connect(gatespath)
        try:
            with conn:
                for gate_id, data in conn.execute("SELECT id,data FROM gates WHERE status IN ('pending','applying')").fetchall():
                    gate = decode_versioned_model_json(data, rule_key='human_gate', model=HumanGate)
                    gate.status = 'uncertain' if gate.status == 'applying' else 'cancelled'
                    gate.error = 'Restored gate is non-replayable; prior remote effect may be uncertain.'
                    conn.execute('UPDATE gates SET status=?,data=? WHERE id=?', (gate.status,gate.model_dump_json(),gate_id))
                    conn.execute('INSERT INTO gate_events(gate_id,status,created_at) VALUES (?,?,?)', (gate_id,gate.status,time.time()))
                    revoked['nonterminal_gates'] += 1
        finally: conn.close()
    statepath = confined(project.root, '.orchestrator/runtime/state.sqlite3')
    if statepath.exists():
        conn = sqlite3.connect(statepath)
        try:
            with conn:
                revoked['execution_approvals'] = conn.execute('DELETE FROM approvals').rowcount
                for task_id, data in conn.execute('SELECT id,data FROM tasks').fetchall():
                    task = decode_versioned_model_json(data, rule_key='task_state', model=TaskState)
                    if task.provider_permission_grants and task.status not in _TERMINAL_TASKS:
                        revoked['permission_grants'] += len(task.provider_permission_grants)
                        task.provider_permission_grants = {}
                        conn.execute('UPDATE tasks SET data=? WHERE id=?', (task.model_dump_json(),task_id))
        finally: conn.close()
    return revoked


def _protected_evidence_ids(project: Project) -> tuple[set[str], bool]:
    from .evidence import inventory
    refs = inventory(project)
    if refs["errors"] or refs["conflicts"] or refs["missing"] or refs["corrupt"]:
        raise OrchestratorError("incomplete evidence inventory")
    return set(refs["protected_evidence_ids"]), refs["legacy_untyped"]

def _artifact_id_from_path(path: Path) -> str | None:
    stem = path.stem
    suffix = stem.rsplit("-", 1)[-1]
    if len(suffix) == 32 and all(char in "0123456789abcdef" for char in suffix):
        return "A-" + suffix
    return None


def _worktree_marker(path: Path) -> str:
    entries = 0
    total_bytes = 0
    latest_mtime_ns = path.stat().st_mtime_ns
    for base, directories, filenames in os.walk(path, followlinks=False):
        parent = Path(base)
        for name in [*directories, *filenames]:
            child = parent / name
            entries += 1
            if entries > MAX_BACKUP_FILES:
                raise OrchestratorError(
                    "retention worktree inventory exceeds safety bound"
                )
            stat = child.lstat()
            latest_mtime_ns = max(latest_mtime_ns, stat.st_mtime_ns)
            if child.is_file() and not child.is_symlink():
                total_bytes += stat.st_size
    return digest(
        {
            "entries": entries,
            "bytes": total_bytes,
            "latest_mtime_ns": latest_mtime_ns,
        }
    )


def retention_plan(root: Path, *, cutoff: str) -> dict[str, Any]:
    project = Project(root.resolve())
    project.load()
    cutoff_dt = parse_cutoff(cutoff)
    cutoff_ts = cutoff_dt.timestamp()

    diagnostics = diagnose_runtime(project.root)
    structural_keys = (
        "runtime:state",
        "runtime:jobs",
        "runtime:gates",
        "runtime:maintenance",
    )
    if not all(diagnostics[key].get("integrity_ok", False) for key in structural_keys):
        raise OrchestratorError(
            "retention planning requires structurally readable runtime state; "
            "run doctor and repair/restore the reported inconsistency first"
        )

    state_path = confined(project.root, ".orchestrator/runtime/state.sqlite3")
    states, state_errors = _read_task_states(state_path)
    intakes, intake_errors = _read_intake_states(state_path)
    if state_errors or intake_errors:
        raise OrchestratorError(
            "retention planning requires readable task and intake state"
        )
    status = {state.spec.id: state.status for state in states}
    referenced_paths = {
        artifact.path for state in states for artifact in state.artifacts
    }
    referenced_paths.update(
        intake.artifact.path
        for intake in intakes
        if intake.artifact is not None
    )
    sessions, errors = _read_exploration_states(state_path)
    if errors:
        raise OrchestratorError("retention planning requires readable exploration state")
    referenced_paths.update(artifact.path for session in sessions for artifact in session.artifacts)
    referenced_paths.update(intake.exploration.transition_artifact.path for intake in intakes if intake.exploration is not None)
    from .evidence import inventory, orphan_shape
    refs = inventory(project)
    if refs["errors"] or refs["conflicts"] or refs["missing"] or refs["corrupt"]:
        raise OrchestratorError("retention requires a complete consistent evidence inventory")
    referenced_paths.update(refs["paths"])
    protected_ids = set(refs["protected_evidence_ids"])
    legacy_untyped_evidence = refs["legacy_untyped"]

    worktrees: list[str] = []
    worktree_markers: dict[str, str] = {}
    worktree_root = confined(project.root, ".orchestrator/runtime/worktrees")
    if worktree_root.exists():
        for task_dir in sorted(worktree_root.iterdir()):
            if not task_dir.is_dir() or task_dir.is_symlink():
                continue
            if status.get(task_dir.name) == "running":
                continue
            if task_dir.stat().st_mtime <= cutoff_ts:
                relative = task_dir.relative_to(project.root).as_posix()
                worktrees.append(relative)
                worktree_markers[relative] = _worktree_marker(task_dir)

    jobs: list[str] = []
    job_digests: dict[str, str] = {}
    jobs_path = confined(project.root, ".orchestrator/runtime/jobs.sqlite3")
    if jobs_path.exists():
        connection = _readonly_connection(jobs_path)
        try:
            rows = connection.execute(
                """
                SELECT j.id,j.status,j.data,COALESCE(MAX(e.created_at),0)
                FROM jobs j LEFT JOIN job_events e ON e.job_id=j.id
                GROUP BY j.id,j.status,j.data ORDER BY j.id
                """
            ).fetchall()
            for job_id, job_status, data, terminal_at in rows:
                try:
                    job = Job.model_validate_json(data)
                except ValueError as exc:
                    raise OrchestratorError(
                        f"retention cannot validate job state: {job_id}"
                    ) from exc
                if job.id != job_id or job.status != job_status:
                    raise OrchestratorError(
                        f"retention job columns do not match encoded state: {job_id}"
                    )
                if job_status in _TERMINAL_JOBS and float(terminal_at) <= cutoff_ts:
                    jobs.append(job_id)
                    job_digests[job_id] = hashlib.sha256(
                        data.encode("utf-8")
                    ).hexdigest()
        finally:
            connection.close()

    orphan_artifacts: list[str] = []
    orphan_hashes: dict[str, str] = {}
    runtime = project.runtime
    artifact_candidates = 0
    if runtime.exists() and not legacy_untyped_evidence:
        for path in sorted(runtime.rglob("*.json")):
            relative = path.relative_to(project.root).as_posix()
            if _runtime_excluded(relative) or relative in referenced_paths:
                continue
            artifact_id = _artifact_id_from_path(path)
            # Legacy/unrecognized JSON does not have stable Artifact v2 identity
            # and is therefore retained conservatively.
            if artifact_id is None or not orphan_shape(project, path):
                continue
            artifact_candidates += 1
            if artifact_candidates > MAX_BACKUP_FILES:
                raise OrchestratorError(
                    "retention artifact inventory exceeds safety bound"
                )
            if artifact_id in protected_ids:
                continue
            if path.stat().st_mtime <= cutoff_ts:
                orphan_artifacts.append(relative)
                orphan_hashes[relative] = _sha256_file(path)

    plan_core = {
        "schema_version": RETENTION_SCHEMA_VERSION,
        "cutoff": cutoff_dt.isoformat(),
        "evidence_inventory_sha256": refs["fingerprint"],
        "worktrees": worktrees,
        "worktree_markers": worktree_markers,
        "terminal_jobs": jobs,
        "terminal_job_sha256": job_digests,
        "orphan_artifacts": orphan_artifacts,
        "orphan_artifact_sha256": orphan_hashes,
        "protected_evidence_ids": len(protected_ids),
        "legacy_untyped_learning_evidence": legacy_untyped_evidence,
        "policy": {
            "task_rows": "retain",
            "intake_rows": "retain",
            "exploration_rows_and_artifacts": "retain, including abandoned sessions and proposal provenance",
            "runtime_events": "retain",
            "human_gate_ledger": "retain",
            "referenced_artifacts": "retain (TaskState and IntakeState)",
            "accepted/promoted Project Learning evidence": "retain",
            "candidate evidence": "retain",
            "legacy/unidentified runtime JSON": "retain",
            "legacy untyped Project Learning evidence": (
                "retain all orphan artifacts; do not guess evidence identity"
                if legacy_untyped_evidence
                else "none detected"
            ),
            "disposable_worktrees": "delete only when no running task owns them",
            "job_records": "retire terminal payloads; durable request receipts retained",
            "orphan_artifacts": (
                "delete only stable Artifact-v2-shaped files when unreferenced "
                "and older than cutoff"
            ),
        },
    }
    return {
        **plan_core,
        "scope": digest(plan_core),
        "authority": "read-only plan; no files or rows were changed",
    }


def apply_retention(root: Path, *, cutoff: str, scope: str, actor: str) -> dict[str, Any]:
    from . import maintenance, receipts
    from .safety import operator_only
    from .worker import worker_lock
    operator_only()
    actor = _validate_maintenance_identity('cleanup', actor, scope)
    project = Project(root.resolve())
    with worker_lock(project), project.lock(), maintenance.cancellation_boundary(project, exclusive=True):
        plan = retention_plan(project.root, cutoff=cutoff)
        _assert_quiescent(project)
        if plan['scope'] != scope:
            raise OrchestratorError('retention plan changed; inspect the new plan before deleting anything')
        handle = maintenance.begin(project, action='cleanup', scope=scope, actor=actor,
            mode='runtime', targets={'worktrees':plan['worktrees'],'orphan_artifacts':plan['orphan_artifacts'],
                                     'terminal_jobs':plan['terminal_jobs']})
        # Retain full plan/hash evidence even on interruption. Disposable deletions
        # are not automatically undone or retried on restart.
        maintenance._write(maintenance.directory(project, handle)/'plan.json', plan)
        maintenance.applying(project, handle)
        removed_worktrees, removed_artifacts = [], []
        for relative in plan['worktrees']:
            path = confined(project.root, relative)
            if path.exists():
                shutil.rmtree(path)
                maintenance.sync_directory(path.parent)
                removed_worktrees.append(relative)
                maintenance.checkpoint('after_worktree_delete')
        for relative in plan['orphan_artifacts']:
            path = confined(project.root, relative)
            if path.is_file():
                path.unlink()
                maintenance.sync_directory(path.parent)
                removed_artifacts.append(relative)
                maintenance.checkpoint('after_artifact_delete')
        deleted_jobs = 0
        jobpath = confined(project.root, '.orchestrator/runtime/jobs.sqlite3')
        if plan['terminal_jobs']:
            conn = sqlite3.connect(jobpath, timeout=5)
            try:
                with conn:
                    conn.execute('BEGIN IMMEDIATE')
                    conn.execute('PRAGMA user_version=2')
                    deleted_jobs = receipts.retire(conn, plan['terminal_jobs'])
                maintenance.checkpoint('after_db_commit')
            finally: conn.close()
        structural, reports = _structural_runtime_ok(project)
        if not structural:
            raise OrchestratorError('cleanup postconditions failed; maintenance remains blocked')
        maintenance.verified(project, handle)
        maintenance.checkpoint('before_audit')
        event = _append_maintenance(project, action='cleanup', actor=actor, scope=scope,
            details={'operation_id':handle['operation_id'], 'cutoff':plan['cutoff'],
                     'worktrees_removed':len(removed_worktrees), 'terminal_jobs_removed':deleted_jobs,
                     'orphan_artifacts_removed':len(removed_artifacts),'canonical_history_retained':True,
                     'request_receipts_retained':True,'automatic_replay':False})
        maintenance.finish(project, handle, event)
    return {'scope':scope,'cutoff':plan['cutoff'],'worktrees_removed':removed_worktrees,
            'terminal_jobs_removed':deleted_jobs,'orphan_artifacts_removed':removed_artifacts,
            'maintenance_event':event,'automatic_repair':False}
