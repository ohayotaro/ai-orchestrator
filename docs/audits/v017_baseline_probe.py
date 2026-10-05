"""Observe the audited 0.16.0 baseline; never touch the owner's runtime.

Run with the checkout's development Python. These are defect observations,
not release acceptance tests. All repositories are temporary and all providers
are in-process FakeAdapters. New jobs in the idempotency probe are not run.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

import yaml
from conftest import FakeAdapter
from ai_orchestrator import __version__, learning
from ai_orchestrator.contracts import IntakeState
from ai_orchestrator.engine import Engine
from ai_orchestrator.jobs import JobQueue
from ai_orchestrator.models import EvidenceRef, OrchestratorError, TaskSpec, TaskState
from ai_orchestrator.operational import apply_retention, diagnose_runtime, retention_plan
from ai_orchestrator.project import Project, initialize
from ai_orchestrator.service import ApplicationService
from ai_orchestrator.store import Store


def setup(root: Path) -> Project:
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / "input.txt").write_text("payload\n", encoding="utf-8")
    initialize(root, "audit")
    config = root / ".orchestrator/config.yaml"
    raw = yaml.safe_load(config.read_text(encoding="utf-8"))
    raw["validators"] = {"check": {
        "argv": [sys.executable, "-c", "print('validated')"],
        "timeout_seconds": 5,
    }}
    config.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return Project(root)


def observe() -> dict:
    if __version__ != "0.16.0":
        raise SystemExit("This audit reproducer is scoped to the 0.16.0 baseline")
    out = {}
    with tempfile.TemporaryDirectory(prefix="v017-design-audit-") as temporary:
        base = Path(temporary)
        project = setup(base / "cancel")
        adapters = {"claude": FakeAdapter("anthropic"), "codex": FakeAdapter("openai")}
        engine = Engine(project.root, adapters)
        try:
            engine.trust("audit")
            state = engine.create(TaskSpec(
                id="cancel-probe", goal="synthetic audit", acceptance=["test"],
                risk="T2", validators=["check"],
            ))
            state = engine.run(state.spec.id)
            calls = sum(len(adapter.requests) for adapter in adapters.values())
            engine.store.request_cancel(state.spec.id)
            view = ApplicationService.task_view(engine, state.spec.id)
            scope = engine.approval_scope(engine.store.get(state.spec.id))
            engine.approve(state.spec.id, scope, "audit")
            events = engine.store.event_count()
            engine.store.request_cancel(state.spec.id)
            out["cancel"] = {
                "status": view["status"],
                "flag": engine.store.cancelled(state.spec.id),
                "flag_visible_in_task_view": "cancel_requested" in view,
                "still_active_binding": state.spec.id in engine.store.active_task_ids(),
                "direct_approval_recorded_after_cancel": engine.store.approved(state.spec.id, scope),
                "repeated_cancel_added_events": engine.store.event_count() - events,
                "additional_provider_calls": sum(len(a.requests) for a in adapters.values()) - calls,
            }
        finally:
            engine.close()

        project = setup(base / "metadata")
        store = Store(project)
        try:
            state = TaskState(
                spec=TaskSpec(id="metadata-task", goal="audit", acceptance=["test"], risk="T0"),
                profile_digest=project.load()[1],
            )
            artifact = store.artifact(state, "fixture", {"evidence": True})
            store.save(state, "audit.created", create=True)
            conflicting = artifact.model_copy(update={"sha256": "0" * 64})
            intake = IntakeState(
                id="I-metadata", task_id="metadata-intake", request="audit",
                profile_digest=project.load()[1], workspace_snapshot=project.snapshot(),
                artifact=conflicting, status="failed",
            )
            store.save_intake(intake, "audit.intake", create=True)
            rejected = False
            try:
                store.read_artifact(conflicting)
            except OrchestratorError:
                rejected = True
        finally:
            store.close()
        out["conflicting_metadata"] = {
            "doctor_integrity_ok": diagnose_runtime(project.root)["runtime:state"]["integrity_ok"],
            "intake_artifact_reader_rejected": rejected,
        }

        project = setup(base / "nested-root")
        store = Store(project)
        try:
            artifact = store.write_artifact("historical-owner", 1, "fixture", {"evidence": True})
        finally:
            store.close()
        metadata = {
            "proposal_id": "P-nested", "canonical_key": "nested-evidence",
            "polarity": "positive", "supersedes": [],
            "evidence_refs": [EvidenceRef(
                source="artifact", id=artifact.id, sha256=artifact.sha256,
                owner_id=artifact.owner_id, kind=artifact.kind,
            ).model_dump()],
        }
        relative = ".orchestrator/knowledge/accepted/nested/P-nested.md"
        markdown = project.root / relative
        markdown.parent.mkdir()
        markdown.write_text(
            learning.LEARNING_METADATA_PREFIX + json.dumps(metadata)
            + learning.LEARNING_METADATA_SUFFIX + "\n# accepted nested evidence\n",
            encoding="utf-8",
        )
        cutoff = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        plan = retention_plan(project.root, cutoff=cutoff)
        out["nested_learning_root"] = {
            "loaded_by_project": relative in project.load()[2],
            "protected_evidence_ids": plan["protected_evidence_ids"],
            "referenced_artifact_listed_as_orphan": artifact.path in plan["orphan_artifacts"],
            "cleanup_executed": False,
        }

        project = setup(base / "idempotence")
        queue = JobQueue(project)
        arguments = {"request": "audit only", "advisory": True}
        request_id = "audit-retired-request"
        try:
            first = queue.enqueue("ask", arguments, request_id, project.load()[1], project.snapshot())
            running = queue.claim()
            assert running is not None
            running.status, running.result = "succeeded", {"status": "proposed"}
            queue.finish(running)
        finally:
            queue.close()
        plan = retention_plan(project.root, cutoff=cutoff)
        applied = apply_retention(project.root, cutoff=cutoff, scope=plan["scope"], actor="audit")
        queue = JobQueue(project)
        try:
            old = queue.existing(request_id, "ask", arguments)
            second = queue.enqueue("ask", arguments, request_id, project.load()[1], project.snapshot())
        finally:
            queue.close()
        out["retired_request"] = {
            "terminal_jobs_removed": applied["terminal_jobs_removed"],
            "existing_request_lost": old is None,
            "same_request_created_new_job": first.id != second.id,
            "new_job_status": second.status,
            "provider_dispatched": False,
        }
    return out


if __name__ == "__main__":
    print(json.dumps(observe(), ensure_ascii=False, indent=2))
