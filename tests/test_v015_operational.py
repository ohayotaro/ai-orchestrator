"""v0.15 operational hardening regressions."""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import yaml

from ai_orchestrator.engine import Engine
from ai_orchestrator.human_gates import GateStore
from ai_orchestrator.jobs import JobQueue
from ai_orchestrator.models import (
    EvidenceRef,
    LearningProvenance,
    LearningSupport,
    OrchestratorError,
    Proposal,
    TaskSpec,
    TaskState,
)
from ai_orchestrator.persistence import persistence_compatibility_report
from ai_orchestrator.operational import (
    apply_retention,
    create_backup,
    diagnose_runtime,
    inspect_backup,
    restore_backup,
    retention_plan,
)
from ai_orchestrator.project import Project, atomic_write
from ai_orchestrator.store import Store


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _future_cutoff() -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat()


def test_runtime_diagnostics_are_physically_read_only(workspace):
    project = Project(workspace)
    store = Store(project)
    store.close()
    gates = GateStore(project)
    gates.close()
    jobs = JobQueue(project)
    jobs.close()

    paths = [
        workspace / ".orchestrator/runtime/state.sqlite3",
        workspace / ".orchestrator/runtime/gates.sqlite3",
        workspace / ".orchestrator/runtime/jobs.sqlite3",
    ]
    before = {path: (_sha(path), path.stat().st_mtime_ns) for path in paths}

    report = diagnose_runtime(workspace)

    after = {path: (_sha(path), path.stat().st_mtime_ns) for path in paths}
    assert after == before
    assert report["runtime:state"]["ok"] is True
    assert report["runtime:jobs"]["ok"] is True
    assert report["runtime:gates"]["ok"] is True
    assert report["runtime:workspaces"]["ok"] is True


def test_runtime_diagnostics_detect_unknown_task_state_without_rewrite(workspace):
    project = Project(workspace)
    store = Store(project)
    try:
        raw = (
            '{"schema_version":99,"spec":{"id":"future-task","goal":"x",'
            '"acceptance":["x"],"risk":"T0","validators":[],"external_effects":false},'
            '"profile_digest":"'
            + ("0" * 64)
            + '"}'
        )
        with store.db:
            store.db.execute(
                "INSERT INTO tasks(id,data) VALUES (?,?)", ("future-task", raw)
            )
    finally:
        store.close()

    path = workspace / ".orchestrator/runtime/state.sqlite3"
    before = _sha(path)
    report = diagnose_runtime(workspace)
    after = _sha(path)

    assert before == after
    assert report["runtime:state"]["ok"] is False
    assert report["runtime:state"]["integrity_ok"] is False
    assert "future-task" in report["runtime:state"]["persisted_state_errors"][0]

    connection = sqlite3.connect(path)
    try:
        assert connection.execute(
            "SELECT data FROM tasks WHERE id='future-task'"
        ).fetchone()[0] == raw
    finally:
        connection.close()


def test_full_backup_restore_is_scope_bound_and_restores_authority(workspace, tmp_path):
    accepted = workspace / ".orchestrator/knowledge/accepted/operator-note.md"
    accepted.write_text("# operator note\n\noriginal authority\n", encoding="utf-8")
    engine = Engine(workspace)
    try:
        engine.trust("backup-test")
        original_digest = engine.profile_digest
    finally:
        engine.close()

    original_config = (workspace / ".orchestrator/config.yaml").read_bytes()
    original_context = accepted.read_bytes()
    archive = tmp_path / "full-backup.zip"
    created = create_backup(workspace, archive, mode="full")
    inspected = inspect_backup(archive)

    assert inspected["verified"] is True
    assert inspected["scope"] == created["scope"]
    assert inspected["manifest"]["source_profile_digest"] == original_digest

    with pytest.raises(OrchestratorError, match="scope changed"):
        restore_backup(
            workspace,
            archive,
            scope="0" * 64,
            actor="operator",
            replace=True,
            acknowledge_authority_restore=True,
        )
    with pytest.raises(OrchestratorError, match="ack-authority-restore"):
        restore_backup(
            workspace,
            archive,
            scope=created["scope"],
            actor="operator",
            replace=True,
        )

    config = yaml.safe_load((workspace / ".orchestrator/config.yaml").read_text())
    config["name"] = "mutated-after-backup"
    (workspace / ".orchestrator/config.yaml").write_text(
        yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
    )
    accepted.write_text("# operator note\n\nmutated authority\n", encoding="utf-8")

    restored = restore_backup(
        workspace,
        archive,
        scope=created["scope"],
        actor="operator",
        replace=True,
        acknowledge_authority_restore=True,
    )

    assert restored["restored"] is True
    assert restored["mode"] == "full"
    assert restored["current_profile_digest"] == original_digest
    assert restored["profile_matches_backup"] is True
    assert (workspace / ".orchestrator/config.yaml").read_bytes() == original_config
    assert accepted.read_bytes() == original_context
    assert (workspace / ".orchestrator/runtime/maintenance.jsonl").is_file()

    check = Engine(workspace)
    try:
        assert check.store.trusted(check.profile_digest) is True
    finally:
        check.close()


def test_restore_over_unreadable_current_state_requires_extra_ack(workspace, tmp_path):
    engine = Engine(workspace)
    try:
        engine.trust("backup-test")
    finally:
        engine.close()

    archive = tmp_path / "pre-corruption-full.zip"
    created = create_backup(workspace, archive, mode="full")

    path = workspace / ".orchestrator/runtime/state.sqlite3"
    connection = sqlite3.connect(path)
    try:
        raw = (
            '{"schema_version":99,"spec":{"id":"future-row","goal":"x",'
            '"acceptance":["x"],"risk":"T0","validators":[],"external_effects":false},'
            '"profile_digest":"'
            + ("0" * 64)
            + '"}'
        )
        with connection:
            connection.execute(
                "INSERT INTO tasks(id,data) VALUES (?,?)", ("future-row", raw)
            )
    finally:
        connection.close()

    assert diagnose_runtime(workspace)["runtime:state"]["integrity_ok"] is False

    with pytest.raises(OrchestratorError, match="ack-unreadable-current-state"):
        restore_backup(
            workspace,
            archive,
            scope=created["scope"],
            actor="operator",
            replace=True,
            acknowledge_authority_restore=True,
        )

    restored = restore_backup(
        workspace,
        archive,
        scope=created["scope"],
        actor="operator",
        replace=True,
        acknowledge_authority_restore=True,
        acknowledge_unreadable_current_state=True,
    )
    assert restored["restored"] is True
    assert restored["current_profile_trusted"] is True
    assert diagnose_runtime(workspace)["runtime:state"]["integrity_ok"] is True

    check = sqlite3.connect(path)
    try:
        assert check.execute(
            "SELECT 1 FROM tasks WHERE id='future-row'"
        ).fetchone() is None
    finally:
        check.close()


def test_runtime_only_restore_never_replaces_current_project_authority(workspace, tmp_path):
    engine = Engine(workspace)
    try:
        engine.trust("backup-test")
        source_digest = engine.profile_digest
    finally:
        engine.close()

    archive = tmp_path / "runtime-backup.zip"
    created = create_backup(workspace, archive, mode="runtime")

    accepted = workspace / ".orchestrator/knowledge/accepted/new-authority.md"
    accepted.write_text("# new authority\n\nkeep this after runtime restore\n", encoding="utf-8")
    current_digest = Project(workspace).load()[1]
    assert current_digest != source_digest

    restored = restore_backup(
        workspace,
        archive,
        scope=created["scope"],
        actor="operator",
        replace=True,
    )

    assert accepted.is_file()
    assert restored["current_profile_digest"] == current_digest
    assert restored["profile_matches_backup"] is False
    assert restored["retrust_required"] is True


def test_retention_is_explicit_and_preserves_canonical_and_learning_evidence(workspace):
    project = Project(workspace)
    profile_digest = project.load()[1]
    store = Store(project)
    try:
        state = TaskState(
            schema_version=8,
            spec=TaskSpec(
                id="retained-task",
                goal="retain canonical evidence",
                acceptance=["evidence remains readable"],
                risk="T0",
            ),
            profile_digest=profile_digest,
            status="succeeded",
            phase="accept",
        )
        referenced = store.artifact(state, "fixture", {"value": "referenced"})
        store.save(state, "fixture.created", create=True)
        state_events_before = store.event_count()
    finally:
        store.close()

    orphan_id = uuid.uuid4().hex
    orphan = workspace / f".orchestrator/runtime/orphan/0-note-{orphan_id}.json"
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_text('{"orphan":true}\n', encoding="utf-8")

    protected_id = uuid.uuid4().hex
    protected = workspace / f".orchestrator/runtime/orphan/0-review-{protected_id}.json"
    protected.write_text('{"protected":true}\n', encoding="utf-8")
    protected_raw = protected.read_bytes()
    evidence_ref = EvidenceRef(
        source="artifact",
        id="A-" + protected_id,
        sha256=hashlib.sha256(protected_raw).hexdigest(),
        owner_id="historical-owner",
        kind="review",
    )
    candidate = Proposal(
        schema_version=2,
        id="P-retention-protected",
        kind="knowledge",
        statement="Retain evidence referenced by Project Learning.",
        evidence=["artifact:" + evidence_ref.id],
        evidence_refs=[evidence_ref],
        support=LearningSupport(
            independent_task_ids=["retained-task"],
            independent_task_count=1,
            evidence_count=1,
        ),
        provenance=LearningProvenance(
            canonical_key="retention-protection",
            evidence_digest="1" * 64,
        ),
        canonical_key="retention-protection",
    )
    atomic_write(
        workspace / ".orchestrator/knowledge/candidates/P-retention-protected.json",
        candidate.model_dump_json(indent=2) + "\n",
    )

    stale = workspace / ".orchestrator/runtime/worktrees/stale-task/attempt-1"
    stale.mkdir(parents=True)
    (stale / "disposable.txt").write_text("discard", encoding="utf-8")

    queue = JobQueue(project)
    try:
        job = queue.enqueue(
            "run",
            {"task_id": "retained-task"},
            "retention-terminal-request",
            profile_digest,
            project.snapshot(),
        )
        running = queue.claim()
        assert running is not None and running.id == job.id
        running.status = "succeeded"
        running.result = {"status": "succeeded"}
        queue.finish(running)
        terminal_job_id = job.id
    finally:
        queue.close()

    cutoff = _future_cutoff()
    plan = retention_plan(workspace, cutoff=cutoff)

    assert ".orchestrator/runtime/worktrees/stale-task" in plan["worktrees"]
    assert terminal_job_id in plan["terminal_jobs"]
    assert orphan.relative_to(workspace).as_posix() in plan["orphan_artifacts"]
    assert protected.relative_to(workspace).as_posix() not in plan["orphan_artifacts"]
    assert referenced.path not in plan["orphan_artifacts"]
    assert plan["authority"].startswith("read-only")
    assert orphan.is_file() and stale.exists()

    result = apply_retention(
        workspace,
        cutoff=cutoff,
        scope=plan["scope"],
        actor="operator",
    )

    assert result["automatic_repair"] is False
    assert not orphan.exists()
    assert protected.exists()
    assert not (workspace / ".orchestrator/runtime/worktrees/stale-task").exists()
    assert (workspace / referenced.path).is_file()

    store = Store(project)
    try:
        assert store.get("retained-task").status == "succeeded"
        assert store.event_count() == state_events_before
        assert store.read_artifact(referenced) == {"value": "referenced"}
    finally:
        store.close()

    queue = JobQueue(project)
    try:
        assert queue.db.execute(
            "SELECT 1 FROM jobs WHERE id=?", (terminal_job_id,)
        ).fetchone() is None
    finally:
        queue.close()

    assert (workspace / ".orchestrator/runtime/maintenance.jsonl").is_file()


def test_retention_scope_must_be_replanned_when_inputs_change(workspace):
    cutoff = _future_cutoff()
    plan = retention_plan(workspace, cutoff=cutoff)

    stale = workspace / ".orchestrator/runtime/worktrees/new-stale/attempt-1"
    stale.mkdir(parents=True)

    with pytest.raises(OrchestratorError, match="retention plan changed"):
        apply_retention(
            workspace,
            cutoff=cutoff,
            scope=plan["scope"],
            actor="operator",
        )
    assert stale.exists()

def test_operational_contracts_are_published_without_execution_schema_bumps():
    report = persistence_compatibility_report()
    assert report["databases"]["runtime_state"]["write_version"] == 2
    assert report["databases"]["human_gate"]["write_version"] == 1
    assert report["databases"]["jobs"]["write_version"] == 1
    assert report["contracts"]["task_state"]["write_version"] == 8
    assert report["contracts"]["intake_state"]["write_version"] == 5
    assert report["contracts"]["backup_manifest"]["write_version"] == 1
    assert report["contracts"]["maintenance_event"]["write_version"] == 1
    assert report["contracts"]["retention_plan"]["write_version"] == 1

