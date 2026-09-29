"""Dispatch boundaries, durable state, conservative recovery and cancellation."""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
import yaml
from pydantic import ValidationError

from ai_orchestrator.engine import Engine
from ai_orchestrator.jobs import JobQueue
from ai_orchestrator.models import OrchestratorError
from ai_orchestrator.project import Project
from ai_orchestrator.service import ApplicationService
from ai_orchestrator.supervisor import Supervisor
from ai_orchestrator.worker import WORKER_MARKER, process_one, run_worker, worker_lock
from conftest import spec
from test_v02_supervisor import IntakeAdapter


@pytest.fixture
def service(workspace):
    engine = Engine(workspace)
    engine.trust("operator")
    engine.close()
    return ApplicationService(workspace)


def request(service, request_id="request-1", **kwargs):
    return service.invoke("propose_task", {"request": "Add a result", "request_id": request_id, "task_id": "job-task", **kwargs})


def registry():
    return {"claude": IntakeAdapter("anthropic"), "codex": IntakeAdapter("openai")}


def test_proposal_only_queues_without_a_model_call_or_task(service):
    job = request(service)
    assert job["status"] == "queued"
    with service.engine() as engine:
        assert engine.store.db.execute("SELECT count(*) FROM tasks").fetchone()[0] == 0
        assert engine.store.db.execute("SELECT count(*) FROM intakes").fetchone()[0] == 0
        assert engine.store.db.execute("SELECT count(*) FROM approvals").fetchone()[0] == 0


def test_end_to_end_dispatch_requires_separate_human_gates(service):
    providers = registry()
    queued = request(service)
    with service.queue() as queue, worker_lock(queue.project):
        done = process_one(queue, registry=providers)
        assert done["status"] == "succeeded", done
        intake = done["result"]
        assert intake["status"] == "proposed"
        assert service.invoke("get_job", {"job_id": queued["id"]})["result"]["id"] == intake["id"]
        with service.engine() as engine:
            state = Supervisor(engine).start(intake["id"], intake["intake_scope"], "human")
            assert state.calls == 1
        service.invoke("run_task", {"task_id": "job-task", "request_id": "plan-1"})
        planned = process_one(queue, registry=providers)
        assert planned["result"]["status"] == "awaiting_approval"
        assert planned["result"]["calls"] == 2
        with pytest.raises(OrchestratorError, match="human execution approval"):
            service.invoke("run_task", {"task_id": "job-task", "request_id": "unapproved-1"})
        with service.engine() as engine:
            engine.approve("job-task", planned["result"]["approval_scope"], "human")
        service.invoke("run_task", {"task_id": "job-task", "request_id": "execute-1"})
        reviewed = process_one(queue, registry=providers)
        assert reviewed["result"]["status"] == "awaiting_acceptance", reviewed
        assert reviewed["result"]["calls"] == 4
        artifact = service.invoke("get_artifact", {"task_id": "job-task", "kind": "review"})
        assert artifact["content"]["blocking_findings"] == []
        with service.engine() as engine:
            assert engine.accept("job-task", "human").status == "succeeded"


def test_idempotent_request_even_after_completion(service):
    first = request(service)
    assert request(service)["id"] == first["id"]
    with service.queue() as queue:
        process_one(queue, registry=registry())
    again = request(service)
    assert again["id"] == first["id"] and again["status"] == "succeeded"
    with pytest.raises(OrchestratorError, match="different arguments"):
        request(service, request="Different goal")


def test_duplicate_pending_task_different_id_is_rejected(service):
    request(service)
    with pytest.raises(OrchestratorError, match="already queued"):
        request(service, request_id="request-2")


@pytest.mark.parametrize("field,value", [("project", "/etc"), ("approved", True), ("scope", "fake"), ("actor", "human"), ("argv", ["sh"]), ("advisory", "false"), ("task_id", "../evil"), ("request", " ")])
def test_input_cannot_supply_authority_or_paths(service, field, value):
    with pytest.raises(ValidationError):
        request(service, **{field: value})


@pytest.mark.parametrize("tool", ["trust", "start", "start_task", "approve_execution", "accept_task", "register_validator", "shell", "fetch"])
def test_authority_tools_are_not_exposed(service, tool):
    with pytest.raises(OrchestratorError, match="unauthorized"):
        service.invoke(tool, {})


def test_untrusted_project_cannot_queue(workspace):
    service = ApplicationService(workspace)
    with pytest.raises(OrchestratorError, match="untrusted"):
        request(service)


@pytest.mark.parametrize("change", ["profile", "worktree"])
def test_changed_queue_binding_never_calls_a_model(service, change):
    request(service)
    if change == "profile":
        (service.root / ".orchestrator/policies/new.md").write_text("Changed policy")
    else:
        (service.root / "input.txt").write_text("changed")
    providers = registry()
    with service.queue() as queue:
        result = process_one(queue, registry=providers)
    assert result["status"] == "failed"
    assert "changed" in result["error"]
    assert all(not provider.requests for provider in providers.values())


def test_queued_cancellation_never_calls_provider(service):
    job = request(service)
    result = service.invoke("cancel_job", {"job_id": job["id"]})
    assert result["status"] == "cancelled"
    with service.queue() as queue:
        assert process_one(queue, registry=registry()) is None


def test_active_supervisor_cancellation_reaches_process_predicate(service):
    job = request(service)
    providers = registry()
    original = providers["claude"].execute
    def execute(req):
        service.invoke("cancel_job", {"job_id": job["id"]})
        assert req.cancel()
        raise OrchestratorError("cancelled")
    providers["claude"].execute = execute
    with service.queue() as queue:
        result = process_one(queue, registry=providers)
    assert result["status"] == "cancelled"
    assert result["result"]["status"] == "cancelled"
    with service.engine() as engine:
        assert engine.store.db.execute("SELECT count(*) FROM tasks").fetchone()[0] == 0


def test_expired_job_is_not_executed(service, monkeypatch):
    job = request(service)
    monkeypatch.setattr(time, "time", lambda: job["expires_at"] + 1)
    providers = registry()
    with service.queue() as queue:
        result = process_one(queue, registry=providers)
    assert result["status"] == "failed" and "expired" in result["error"]
    assert not providers["claude"].requests


def test_interrupted_claim_never_replays(service):
    job = request(service)
    with service.queue() as queue:
        assert queue.claim().id == job["id"]
    with service.queue() as queue, worker_lock(queue.project):
        assert queue.interrupt_stale() == 1
        assert queue.get(job["id"]).status == "interrupted"
        assert process_one(queue, registry=registry()) is None


def test_claim_atomic_across_connections(service):
    request(service)
    def claim():
        with service.queue() as queue:
            job = queue.claim()
            return job.id if job else None
    with ThreadPoolExecutor(max_workers=4) as pool:
        claims = list(pool.map(lambda _: claim(), range(4)))
    assert sum(value is not None for value in claims) == 1


def test_pending_limit_and_terminal_immutability(service, monkeypatch):
    monkeypatch.setattr("ai_orchestrator.jobs.MAX_PENDING", 1)
    job = request(service)
    with pytest.raises(OrchestratorError, match="full"):
        request(service, "request-2", task_id="other")
    with service.queue() as queue:
        claimed = queue.claim()
        claimed.status = "failed"
        queue.finish(claimed)
        with pytest.raises(OrchestratorError, match="terminal"):
            queue.finish(claimed)
        assert queue.cancel(job["id"]).status == "failed"


def test_worker_exclusive_and_session_guard(service, monkeypatch):
    monkeypatch.delenv("CLAUDECODE", raising=False)
    monkeypatch.delenv(WORKER_MARKER, raising=False)
    with worker_lock(Project(service.root)):
        with pytest.raises(OrchestratorError, match="already owns"):
            run_worker(service.root, once=True)
    monkeypatch.setenv("CLAUDECODE", "parent-session")
    with pytest.raises(OrchestratorError, match="separate normal terminal"):
        run_worker(service.root, once=True)
    assert os.environ["CLAUDECODE"] == "parent-session"


def test_inspect_is_nonexecuting_and_project_scoped(service):
    result = service.invoke("inspect_project", {})
    assert result["project"] == str(service.root)
    assert result["validators"]["validator:check"]["execution"] == "not checked"
    assert "approve" in result["operator_only"]
    with pytest.raises(ValidationError):
        service.invoke("inspect_project", {"project": "/tmp/other"})


def test_ungated_legacy_task_cannot_be_dispatched(service):
    path = service.root / ".orchestrator/config.yaml"
    profile = yaml.safe_load(path.read_text())
    profile["policy"]["require_execution_approval"] = False
    path.write_text(yaml.safe_dump(profile))
    with service.engine() as engine:
        engine.trust("human")
        engine.create(spec())
    with pytest.raises(OrchestratorError, match="requires human execution gates"):
        service.invoke("run_task", {"task_id": "task-1", "request_id": "ungated"})


def test_existing_profile_digest_is_not_rewritten(service):
    before = Project(service.root).load()[1]
    request(service)
    with service.queue() as queue:
        process_one(queue, registry=registry())
    assert Project(service.root).load()[1] == before
