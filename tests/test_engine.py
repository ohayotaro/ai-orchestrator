import json

import pytest
import yaml

from ai_orchestrator.engine import Engine
from ai_orchestrator.models import OrchestratorError
from ai_orchestrator.project import digest
from conftest import FakeAdapter, approve_and_run, spec


def test_complete_workflow_and_fresh_review(engine):
    controller, reasoning, engineering = engine
    controller.create(spec())
    state = approve_and_run(controller)
    assert state.status == "awaiting_acceptance", state.error
    assert state.calls == 3
    reviewer = reasoning.requests[-1]
    payload = json.loads(reviewer.prompt)
    assert "IMPLEMENTER_TRANSCRIPT_MARKER" not in reviewer.prompt
    assert "plan" not in payload
    assert payload["validation"]["checks"][0]["exit_code"] == 0
    assert engineering.requests[0].phase == "execute"
    state = controller.accept("task-1", "operator")
    assert state.status == "succeeded"
    assert controller.run("task-1").calls == 3
    events = controller.store.events("task-1")
    assert [event["sequence"] for event in events] == sorted(event["sequence"] for event in events)
    assert events[-1]["kind"] == "task.accepted"
    assert {artifact.kind for artifact in state.artifacts} == {"plan", "execute", "validation", "review", "acceptance"}


def test_t0_never_implements_or_runs_validators(engine):
    controller, reasoning, engineering = engine
    controller.create(spec(risk="T0"))
    state = controller.run("task-1")
    assert state.status == "awaiting_acceptance"
    assert not engineering.requests
    assert state.calls == 1
    assert controller.accept("task-1", "operator").status == "succeeded"


def test_t3_gate_cannot_be_disabled(workspace):
    path = workspace / ".orchestrator/config.yaml"
    profile = yaml.safe_load(path.read_text())
    profile["policy"]["require_execution_approval"] = False
    path.write_text(yaml.safe_dump(profile))
    controller = Engine(workspace, {"claude": FakeAdapter("anthropic"), "codex": FakeAdapter("openai")})
    try:
        controller.trust("operator")
        controller.create(spec(risk="T3"))
        assert controller.run("task-1").status == "awaiting_approval"
    finally:
        controller.close()


def test_approval_cannot_be_reused_after_workspace_change(engine):
    controller, _, engineering = engine
    controller.create(spec())
    state = controller.run("task-1")
    scope = controller.approval_scope(state)
    (controller.project.root / "input.txt").write_text("changed")
    with pytest.raises(OrchestratorError, match="scope changed"):
        controller.approve("task-1", scope, "operator")
    assert not engineering.requests


def test_acceptance_rejects_changed_worktree(engine):
    controller, _, _ = engine
    controller.create(spec())
    approve_and_run(controller)
    (controller.project.root / "result.txt").write_text("changed after review")
    with pytest.raises(OrchestratorError, match="changed since review"):
        controller.accept("task-1", "operator")


def test_active_profile_change_invalidates_task(engine):
    controller, _, _ = engine
    controller.create(spec())
    (controller.project.control / "policies" / "new.md").write_text("New policy")
    state = controller.run("task-1")
    assert state.status == "blocked"
    assert "profile changed" in state.error


def test_candidates_do_not_change_profile_digest(engine):
    controller, _, _ = engine
    from ai_orchestrator.knowledge import propose
    before = controller.project.load()[1]
    propose(controller.project.root, "policy", "Potential rule", ["task:earlier"])
    assert before == controller.project.load()[1]


def test_cross_provider_checks_families_not_aliases(engine):
    controller, reasoning, engineering = engine
    reasoning.family = engineering.family
    controller.create(spec())
    state = controller.run("task-1")
    assert state.status == "blocked"
    assert "provider families" in state.error
    assert not reasoning.requests


def test_missing_capability_fails_closed(engine):
    controller, _, engineering = engine
    engineering.capabilities = frozenset({"fresh_session"})
    controller.create(spec())
    assert controller.run("task-1").status == "blocked"
    assert not engineering.requests


def test_external_effects_stay_blocked(engine):
    controller, reasoning, _ = engine
    controller.create(spec(external_effects=True))
    state = controller.run("task-1")
    assert state.status == "blocked"
    assert not reasoning.requests


def test_review_rejection_requires_new_scoped_approval(engine):
    controller, reasoning, _ = engine
    reasoning.reject_reviews = 1
    controller.create(spec())
    state = approve_and_run(controller)
    assert state.status == "awaiting_approval"
    assert state.attempt == 2
    controller.approve("task-1", controller.approval_scope(state), "operator")
    state = controller.run("task-1")
    assert state.status == "awaiting_acceptance"
    assert state.calls == 5


def test_review_loop_is_bounded(engine):
    controller, reasoning, _ = engine
    reasoning.reject_reviews = 99
    controller.create(spec())
    state = controller.run("task-1")
    for _ in range(3):
        assert state.status == "awaiting_approval"
        controller.approve("task-1", controller.approval_scope(state), "operator")
        state = controller.run("task-1")
    assert state.status == "failed"
    assert "retry limit" in state.error
    assert state.attempt == 3


def test_read_only_mutation_is_detected_not_silently_rolled_back(engine):
    controller, reasoning, _ = engine
    reasoning.mutate_review = True
    controller.create(spec())
    state = approve_and_run(controller)
    assert state.status == "failed"
    assert "read-only" in state.error
    assert (controller.project.root / "unexpected.txt").exists()


def test_protected_mutation_stops_workflow(engine):
    controller, _, engineering = engine
    engineering.mutate_protected = True
    controller.create(spec())
    state = approve_and_run(controller)
    assert state.status == "failed"
    assert "protected files changed" in state.error


def test_provider_failure_not_replayed(engine):
    controller, _, engineering = engine
    engineering.explode = True
    controller.create(spec())
    state = approve_and_run(controller)
    assert state.status == "failed"
    with pytest.raises(OrchestratorError, match="not rerun"):
        controller.run("task-1")
    assert len(engineering.requests) == 1


def test_tampered_artifact_blocks_acceptance(engine):
    controller, _, _ = engine
    controller.create(spec())
    state = approve_and_run(controller)
    path = controller.project.root / state.artifacts[-1].path
    path.write_text('{"outcome":"approved"}')
    with pytest.raises(OrchestratorError, match="integrity"):
        controller.accept("task-1", "operator")


def test_interrupted_run_is_not_automatically_replayed(engine):
    controller, _, _ = engine
    state = controller.create(spec())
    state.status = "running"
    controller.store.save(state, "test.interrupted")
    with pytest.raises(OrchestratorError, match="interrupted"):
        controller.run("task-1")
    assert controller.recover("task-1").status == "failed"


def test_cancel_before_run_prevents_model_calls(engine):
    controller, reasoning, engineering = engine
    controller.create(spec())
    controller.store.request_cancel("task-1")
    state = controller.run("task-1")
    assert state.status == "cancelled"
    assert not reasoning.requests and not engineering.requests


def test_workspace_lock_blocks_concurrent_controller(engine):
    controller, _, _ = engine
    with controller.project.lock():
        with pytest.raises(OrchestratorError, match="another controller"):
            controller.create(spec())


def test_untrusted_profile_never_executes(engine):
    controller, reasoning, _ = engine
    controller.store.trust("different-digest", "operator")
    controller.create(spec())
    assert controller.run("task-1").status == "blocked"
    assert not reasoning.requests


def test_duplicate_task_never_overwrites(engine):
    controller, _, _ = engine
    first = controller.create(spec())
    with pytest.raises(OrchestratorError, match="already exists"):
        controller.create(spec())
    assert controller.store.get("task-1").spec == first.spec


def test_validation_failure_never_reaches_review(workspace):
    import sys
    path = workspace / ".orchestrator/config.yaml"
    profile = yaml.safe_load(path.read_text())
    profile["policy"]["max_attempts"] = 1
    profile["validators"]["check"]["argv"] = [sys.executable, "-c", "raise SystemExit(1)"]
    path.write_text(yaml.safe_dump(profile))
    reasoning, engineering = FakeAdapter("anthropic"), FakeAdapter("openai")
    controller = Engine(workspace, {"claude": reasoning, "codex": engineering})
    try:
        controller.trust("operator")
        controller.create(spec())
        state = approve_and_run(controller)
        assert state.status == "failed"
        assert all(req.phase != "review" for req in reasoning.requests)
        evidence = controller.store.latest(state, "validation")
        assert evidence["checks"][0]["exit_code"] == 1
    finally:
        controller.close()


def test_agent_call_budget_is_enforced(workspace):
    path = workspace / ".orchestrator/config.yaml"
    profile = yaml.safe_load(path.read_text())
    profile["policy"]["max_agent_calls"] = 2
    path.write_text(yaml.safe_dump(profile))
    controller = Engine(workspace, {"claude": FakeAdapter("anthropic"), "codex": FakeAdapter("openai")})
    try:
        controller.trust("operator")
        controller.create(spec())
        state = approve_and_run(controller)
        assert state.status == "failed"
        assert "budget" in state.error
        assert state.calls == 2
    finally:
        controller.close()


def test_validator_mutation_is_not_accepted(workspace):
    import sys
    path = workspace / ".orchestrator/config.yaml"
    profile = yaml.safe_load(path.read_text())
    profile["validators"]["check"]["argv"] = [sys.executable, "-c", "from pathlib import Path; Path('input.txt').write_text('mutated')"]
    path.write_text(yaml.safe_dump(profile))
    controller = Engine(workspace, {"claude": FakeAdapter("anthropic"), "codex": FakeAdapter("openai")})
    try:
        controller.trust("operator")
        controller.create(spec())
        state = approve_and_run(controller)
        assert state.status == "failed"
        assert "validator modified" in state.error
    finally:
        controller.close()


def test_task_timeout_is_persisted_on_failure(engine):
    controller, _, engineering = engine
    engineering.explode = True
    controller.create(spec())
    state = approve_and_run(controller)
    assert state.elapsed_seconds > 0
    assert controller.store.get("task-1").elapsed_seconds == state.elapsed_seconds


def test_pending_cancellation_prevents_accept(engine):
    controller, _, _ = engine
    controller.create(spec())
    approve_and_run(controller)
    controller.store.request_cancel("task-1")
    with pytest.raises(OrchestratorError, match="cancellation"):
        controller.accept("task-1", "operator")


def test_approved_review_may_include_nonblocking_findings(engine):
    controller, reasoning, _ = engine
    original_execute = reasoning.execute

    def execute(request):
        result = original_execute(request)
        if request.phase == "review":
            return type(result)(
                outcome="approved",
                summary="Acceptance criteria satisfied; one informational note remains.",
                blocking_findings=[],
                observations=["Non-blocking observation about validator configuration."],
                evidence=["result.txt"],
            )
        return result

    reasoning.execute = execute
    controller.create(spec())
    state = approve_and_run(controller)
    assert state.status == "awaiting_acceptance", state.model_dump()
    assert state.phase == "accept"
    assert state.attempt == 1
    assert state.calls == 3
    review = controller.store.latest(state, "review")
    assert review["outcome"] == "approved"
    assert review["observations"] == ["Non-blocking observation about validator configuration."]
    assert review["blocking_findings"] == []
