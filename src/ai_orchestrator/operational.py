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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import quote

from . import __version__
from .contracts import IntakeState
from .jobs import Job
from .models import OrchestratorError, TaskState
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
DEFAULT_RETENTION_DAYS = 30

_DB_SPECS = {
    "state": ("state.sqlite3", "runtime", RUNTIME_DB_READABLE_VERSIONS),
    "jobs": ("jobs.sqlite3", "job", JOB_DB_READABLE_VERSIONS),
    "gates": ("gates.sqlite3", "human-gate", HUMAN_GATE_DB_READABLE_VERSIONS),
}
_TERMINAL_TASKS = {"succeeded", "blocked", "failed", "cancelled", "abandoned"}
_TERMINAL_JOBS = {"succeeded", "failed", "cancelled", "interrupted"}
_TERMINAL_GATES = {"applied", "declined", "cancelled", "expired", "failed"}
_EPHEMERAL_RUNTIME_NAMES = {"workspace.lock", "worker.lock"}
_SQLITE_SIDECARS = ("-wal", "-shm", "-journal")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    connection = _readonly_connection(path)
    try:
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
    finally:
        connection.close()
    return values, errors


def _state_report(project: Project) -> dict[str, Any]:
    path = confined(project.root, ".orchestrator/runtime/state.sqlite3")
    report = _quick_database_report(path, "runtime", RUNTIME_DB_READABLE_VERSIONS)
    if not report["present"] or not report["integrity_ok"]:
        return report
    states, errors = _read_task_states(path)
    referenced: set[str] = set()
    artifact_ids: set[str] = set()
    missing: list[str] = []
    corrupt: list[str] = []
    intakes = 0
    try:
        connection = _readonly_connection(path)
        try:
            intake_rows = connection.execute("SELECT id,data FROM intakes ORDER BY id").fetchall()
            intakes = len(intake_rows)
            if len(intake_rows) > MAX_DIAGNOSTIC_ROWS:
                errors.append(f"intake row count exceeds diagnostic bound ({MAX_DIAGNOSTIC_ROWS})")
            else:
                for intake_id, data in intake_rows:
                    try:
                        intake = decode_versioned_model_json(
                            data, rule_key="intake_state", model=IntakeState
                        )
                        if intake.id != intake_id:
                            raise OrchestratorError(
                                "intake row ID does not match embedded IntakeState ID"
                            )
                    except (ValueError, OrchestratorError) as exc:
                        errors.append(f"{intake_id}: {exc}")
        finally:
            connection.close()
    except (sqlite3.DatabaseError, OSError) as exc:
        errors.append(str(exc))

    for state in states:
        for artifact in state.artifacts:
            referenced.add(artifact.path)
            if artifact.id:
                artifact_ids.add(artifact.id)
            try:
                artifact_path = confined(project.root, artifact.path)
                if not artifact_path.is_file():
                    missing.append(artifact.path)
                    continue
                raw = artifact_path.read_bytes()
                if hashlib.sha256(raw).hexdigest() != artifact.sha256:
                    corrupt.append(artifact.path)
                    continue
                normalize_control_evidence(artifact.kind, json.loads(raw.decode("utf-8")))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError, OrchestratorError) as exc:
                corrupt.append(f"{artifact.path}: {exc}")

    report.update(
        task_count=len(states),
        intake_count=intakes,
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
    except (sqlite3.DatabaseError, OSError) as exc:
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
    except (sqlite3.DatabaseError, OSError) as exc:
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
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            events += 1
            try:
                item = json.loads(line)
                if item.get("schema_version") != MAINTENANCE_EVENT_SCHEMA_VERSION:
                    raise ValueError("unsupported maintenance event schema")
                if not item.get("id") or not item.get("action") or not item.get("actor"):
                    raise ValueError("maintenance event is missing required identity")
            except (json.JSONDecodeError, ValueError) as exc:
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
    reports = {
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
    if not actor.strip():
        raise OrchestratorError("maintenance operation requires a nonblank operator actor")
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
    return event


def _runtime_excluded(relative: str) -> bool:
    prefix = ".orchestrator/runtime/"
    if not relative.startswith(prefix):
        return False
    tail = relative[len(prefix):]
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
    finally:
        with contextlib.suppress(FileNotFoundError):
            temporary.unlink()


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
    _profile, profile_digest, _context = project.load()
    output = output.expanduser().resolve()
    control = project.control.resolve()
    if output == control or control in output.parents:
        raise OrchestratorError("backup output must be outside .orchestrator")
    if output.exists() and not replace:
        raise OrchestratorError("backup output already exists; pass --replace explicitly")
    from .worker import worker_lock

    with worker_lock(project), project.lock(), tempfile.TemporaryDirectory(
        prefix="ai-orchestrator-backup-"
    ) as temporary:
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
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
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
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
            if manifest.get("schema_version") != BACKUP_SCHEMA_VERSION or manifest.get("kind") != "ai-orchestrator-backup":
                raise OrchestratorError("unsupported backup manifest")
            mode = manifest.get("mode")
            if mode not in ("runtime", "full"):
                raise OrchestratorError("backup manifest has invalid mode")
            files = manifest.get("files")
            if not isinstance(files, list) or len(files) != manifest.get("file_count"):
                raise OrchestratorError("backup manifest file count is inconsistent")
            expected_names = {"manifest.json"}
            total = 0
            for item in files:
                if not isinstance(item, dict):
                    raise OrchestratorError("backup manifest file entry is invalid")
                relative = _safe_member_name(str(item.get("path", "")))
                if not relative.startswith(".orchestrator/"):
                    raise OrchestratorError("backup may contain only .orchestrator paths")
                if mode == "runtime" and not relative.startswith(".orchestrator/runtime/"):
                    raise OrchestratorError("runtime backup contains project-authority paths")
                if _runtime_excluded(relative):
                    raise OrchestratorError("backup contains disposable/ephemeral runtime state")
                expected_names.add(relative)
                info = archive.getinfo(relative)
                if info.file_size != item.get("bytes"):
                    raise OrchestratorError(f"backup size mismatch: {relative}")
                raw = archive.read(relative)
                total += len(raw)
                if total > MAX_BACKUP_BYTES:
                    raise OrchestratorError("backup exceeds 2 GiB safety bound")
                if hashlib.sha256(raw).hexdigest() != item.get("sha256"):
                    raise OrchestratorError(f"backup hash mismatch: {relative}")
            if set(names) != expected_names:
                raise OrchestratorError("backup archive contains unmanifested files")
            if total != manifest.get("total_bytes"):
                raise OrchestratorError("backup total byte count is inconsistent")
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise OrchestratorError("backup archive is malformed") from exc
    return {
        "path": str(path),
        "mode": manifest["mode"],
        "scope": digest(manifest),
        "manifest": manifest,
        "verified": True,
    }


def _runtime_activity(project: Project) -> dict[str, list[str]]:
    activity = {"tasks": [], "jobs": [], "gates": []}
    state_path = confined(project.root, ".orchestrator/runtime/state.sqlite3")
    states, errors = _read_task_states(state_path)
    if errors:
        raise OrchestratorError("cannot perform maintenance while task state is inconsistent")
    activity["tasks"] = sorted(state.spec.id for state in states if state.status == "running")

    jobs_path = confined(project.root, ".orchestrator/runtime/jobs.sqlite3")
    if jobs_path.exists():
        connection = _readonly_connection(jobs_path)
        try:
            for job_id, status in connection.execute(
                "SELECT id,status FROM jobs WHERE status IN ('queued','running') ORDER BY id"
            ).fetchall():
                activity["jobs"].append(job_id)
        finally:
            connection.close()

    gates_path = confined(project.root, ".orchestrator/runtime/gates.sqlite3")
    if gates_path.exists():
        connection = _readonly_connection(gates_path)
        try:
            for gate_id, status in connection.execute(
                "SELECT id,status FROM gates WHERE status IN ('pending','applying') ORDER BY id"
            ).fetchall():
                activity["gates"].append(gate_id)
        finally:
            connection.close()
    return activity


def _assert_quiescent(project: Project) -> None:
    activity = _runtime_activity(project)
    if any(activity.values()):
        raise OrchestratorError(
            "maintenance requires a quiescent project; running tasks, queued/running "
            "jobs, or pending/applying HumanGates must be resolved first: "
            + encode(activity)
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
        _atomic_write_bytes(destination, source.read_bytes())


def _stage_archive(path: Path, destination: Path, manifest: dict[str, Any]) -> None:
    with zipfile.ZipFile(path, "r") as archive:
        for item in manifest["files"]:
            relative = item["path"]
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write_bytes(target, archive.read(relative))


def _stage_current(project: Project, mode: str, destination: Path) -> None:
    for source in _iter_managed_files(project, mode):
        relative = source.relative_to(project.root).as_posix()
        _copy_snapshot_file(source, destination / relative)


def _structural_runtime_ok(project: Project) -> tuple[bool, dict[str, Any]]:
    reports = diagnose_runtime(project.root)
    structural = all(
        reports[key].get("integrity_ok", False)
        for key in ("runtime:state", "runtime:jobs", "runtime:gates", "runtime:maintenance")
    )
    return structural, reports


def restore_backup(
    root: Path,
    archive_path: Path,
    *,
    scope: str,
    actor: str,
    replace: bool,
    acknowledge_authority_restore: bool = False,
) -> dict[str, Any]:
    if not replace:
        raise OrchestratorError("restore requires explicit --replace acknowledgement")
    inspected = inspect_backup(archive_path)
    if inspected["scope"] != scope:
        raise OrchestratorError("backup scope changed; inspect the archive again before restore")
    mode = inspected["mode"]
    if mode == "full" and not acknowledge_authority_restore:
        raise OrchestratorError(
            "full restore can reinstate config/context/trusted-profile authority; "
            "pass --ack-authority-restore explicitly"
        )
    project = Project(root.resolve())
    project.load()
    from .worker import worker_lock

    rolled_back = False
    with worker_lock(project), project.lock():
        _assert_quiescent(project)
        with tempfile.TemporaryDirectory(prefix="ai-orchestrator-restore-") as temporary:
            root_tmp = Path(temporary)
            archive_stage = root_tmp / "archive"
            rollback_stage = root_tmp / "rollback"
            _stage_archive(Path(inspected["path"]), archive_stage, inspected["manifest"])
            _stage_current(project, mode, rollback_stage)
            try:
                _remove_managed_files(project, mode)
                _restore_stage(archive_stage, project, inspected["manifest"])
                structural, reports = _structural_runtime_ok(project)
                if not structural:
                    raise OrchestratorError("restored runtime failed structural integrity checks")
                restored_profile_digest = None
                if mode == "full":
                    _profile, restored_profile_digest, _context = project.load()
                    if restored_profile_digest != inspected["manifest"]["source_profile_digest"]:
                        raise OrchestratorError(
                            "full restore profile digest does not match the verified backup"
                        )
            except Exception:
                rolled_back = True
                _remove_managed_files(project, mode)
                _restore_stage(rollback_stage, project, {
                    "files": [
                        {
                            "path": path.relative_to(rollback_stage).as_posix(),
                        }
                        for path in sorted(rollback_stage.rglob("*"))
                        if path.is_file()
                    ]
                })
                raise

        event = _append_maintenance(
            project,
            action="restore",
            actor=actor,
            scope=scope,
            details={
                "mode": mode,
                "archive": Path(inspected["path"]).name,
                "source_version": inspected["manifest"]["source_version"],
                "source_profile_digest": inspected["manifest"]["source_profile_digest"],
                "authority_restore": mode == "full",
                "rollback_used": rolled_back,
            },
        )
    current_digest = project.load()[1]
    return {
        "restored": True,
        "mode": mode,
        "scope": scope,
        "current_profile_digest": current_digest,
        "source_profile_digest": inspected["manifest"]["source_profile_digest"],
        "profile_matches_backup": current_digest == inspected["manifest"]["source_profile_digest"],
        "retrust_required": (
            mode == "runtime"
            and current_digest != inspected["manifest"]["source_profile_digest"]
        ),
        "maintenance_event": event,
    }


def _protected_evidence_ids(project: Project) -> set[str]:
    protected: set[str] = set()
    accepted = confined(project.root, ".orchestrator/knowledge/accepted")
    candidates = confined(project.root, ".orchestrator/knowledge/candidates")
    from . import learning, knowledge

    if accepted.exists():
        for path in accepted.glob("*.md"):
            try:
                metadata = learning.accepted_learning_metadata(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, OrchestratorError):
                continue
            if metadata:
                for raw in metadata.get("evidence_refs") or []:
                    if isinstance(raw, dict) and raw.get("id"):
                        protected.add(str(raw["id"]))
    if candidates.exists():
        for path in candidates.glob("*.json"):
            try:
                proposal = knowledge.load_proposal(project.root, path.stem)
            except (OSError, OrchestratorError, ValueError):
                continue
            protected.update(ref.id for ref in proposal.evidence_refs)
    return protected


def _artifact_id_from_path(path: Path) -> str | None:
    stem = path.stem
    suffix = stem.rsplit("-", 1)[-1]
    if len(suffix) == 32 and all(char in "0123456789abcdef" for char in suffix):
        return "A-" + suffix
    return None


def retention_plan(root: Path, *, cutoff: str) -> dict[str, Any]:
    project = Project(root.resolve())
    project.load()
    cutoff_dt = parse_cutoff(cutoff)
    cutoff_ts = cutoff_dt.timestamp()
    state_path = confined(project.root, ".orchestrator/runtime/state.sqlite3")
    states, state_errors = _read_task_states(state_path)
    if state_errors:
        raise OrchestratorError("retention planning requires readable task state")
    status = {state.spec.id: state.status for state in states}
    referenced_paths = {
        artifact.path for state in states for artifact in state.artifacts
    }
    protected_ids = _protected_evidence_ids(project)

    worktrees: list[str] = []
    worktree_root = confined(project.root, ".orchestrator/runtime/worktrees")
    if worktree_root.exists():
        for task_dir in sorted(worktree_root.iterdir()):
            if not task_dir.is_dir() or task_dir.is_symlink():
                continue
            if status.get(task_dir.name) == "running":
                continue
            if task_dir.stat().st_mtime <= cutoff_ts:
                worktrees.append(task_dir.relative_to(project.root).as_posix())

    jobs: list[str] = []
    jobs_path = confined(project.root, ".orchestrator/runtime/jobs.sqlite3")
    if jobs_path.exists():
        connection = _readonly_connection(jobs_path)
        try:
            rows = connection.execute(
                """
                SELECT j.id,j.status,COALESCE(MAX(e.created_at),0)
                FROM jobs j LEFT JOIN job_events e ON e.job_id=j.id
                GROUP BY j.id,j.status ORDER BY j.id
                """
            ).fetchall()
            for job_id, job_status, terminal_at in rows:
                if job_status in _TERMINAL_JOBS and float(terminal_at) <= cutoff_ts:
                    jobs.append(job_id)
        finally:
            connection.close()

    orphan_artifacts: list[str] = []
    runtime = project.runtime
    if runtime.exists():
        for path in sorted(runtime.rglob("*.json")):
            relative = path.relative_to(project.root).as_posix()
            if _runtime_excluded(relative) or relative in referenced_paths:
                continue
            artifact_id = _artifact_id_from_path(path)
            if artifact_id and artifact_id in protected_ids:
                continue
            if path.stat().st_mtime <= cutoff_ts:
                orphan_artifacts.append(relative)

    plan_core = {
        "schema_version": RETENTION_SCHEMA_VERSION,
        "cutoff": cutoff_dt.isoformat(),
        "worktrees": worktrees,
        "terminal_jobs": jobs,
        "orphan_artifacts": orphan_artifacts,
        "protected_evidence_ids": len(protected_ids),
        "policy": {
            "task_rows": "retain",
            "intake_rows": "retain",
            "runtime_events": "retain",
            "human_gate_ledger": "retain",
            "referenced_artifacts": "retain",
            "accepted/promoted Project Learning evidence": "retain",
            "candidate evidence": "retain",
            "disposable_worktrees": "delete only when no running task owns them",
            "job_records": "delete terminal rows/events older than cutoff",
            "orphan_artifacts": "delete only when unreferenced and older than cutoff",
        },
    }
    return {
        **plan_core,
        "scope": digest(plan_core),
        "authority": "read-only plan; no files or rows were changed",
    }


def apply_retention(
    root: Path,
    *,
    cutoff: str,
    scope: str,
    actor: str,
) -> dict[str, Any]:
    project = Project(root.resolve())
    project.load()
    from .worker import worker_lock

    with worker_lock(project), project.lock():
        _assert_quiescent(project)
        plan = retention_plan(project.root, cutoff=cutoff)
        if plan["scope"] != scope:
            raise OrchestratorError(
                "retention plan changed; inspect the new plan before deleting anything"
            )
        removed_worktrees: list[str] = []
        for relative in plan["worktrees"]:
            path = confined(project.root, relative)
            if path.exists():
                shutil.rmtree(path)
                removed_worktrees.append(relative)
        removed_artifacts: list[str] = []
        for relative in plan["orphan_artifacts"]:
            path = confined(project.root, relative)
            if path.is_file():
                path.unlink()
                removed_artifacts.append(relative)
        deleted_jobs = 0
        jobs_path = confined(project.root, ".orchestrator/runtime/jobs.sqlite3")
        if plan["terminal_jobs"] and jobs_path.exists():
            connection = sqlite3.connect(jobs_path, timeout=5)
            try:
                with connection:
                    placeholders = ",".join("?" for _ in plan["terminal_jobs"])
                    connection.execute(
                        f"DELETE FROM job_events WHERE job_id IN ({placeholders})",
                        plan["terminal_jobs"],
                    )
                    cursor = connection.execute(
                        f"DELETE FROM jobs WHERE id IN ({placeholders}) AND status IN ('succeeded','failed','cancelled','interrupted')",
                        plan["terminal_jobs"],
                    )
                    deleted_jobs = cursor.rowcount
            finally:
                connection.close()
        event = _append_maintenance(
            project,
            action="cleanup",
            actor=actor,
            scope=scope,
            details={
                "cutoff": plan["cutoff"],
                "worktrees_removed": len(removed_worktrees),
                "terminal_jobs_removed": deleted_jobs,
                "orphan_artifacts_removed": len(removed_artifacts),
                "canonical_history_retained": True,
            },
        )
    return {
        "scope": scope,
        "cutoff": plan["cutoff"],
        "worktrees_removed": removed_worktrees,
        "terminal_jobs_removed": deleted_jobs,
        "orphan_artifacts_removed": removed_artifacts,
        "maintenance_event": event,
        "automatic_repair": False,
    }
