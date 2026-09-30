"""Host confirmation must be scoped, single-use, separate from model arguments."""
from __future__ import annotations

import json
import os
import time

import pytest
from pydantic import ValidationError

from ai_orchestrator.contracts import SupervisorResult, TaskDraft
from ai_orchestrator.engine import Engine
from ai_orchestrator.human_gates import GATE_TOOLS, GateStore, HumanGateBroker, safe_display
from ai_orchestrator.models import OrchestratorError
from ai_orchestrator.service import ApplicationService
from ai_orchestrator.supervisor import Supervisor
from ai_orchestrator.worker import process_one
from conftest import FakeAdapter, spec


class IntakeAdapter(FakeAdapter):
    def execute(self, request):
        if request.phase == "supervise":
            self.requests.append(request)
            return request.result_model(outcome="proposed", summary="Add a result", task={"goal":"Add a result","acceptance":["Result exists","Checks pass"],"risk":"T2","validators":["check"],"external_effects":False,"allowed_paths":["result.txt"],"capabilities":{},"workflow_ref":None}, questions=[])
        return super().execute(request)


@pytest.fixture
def gate_setup(workspace):
    providers = {"claude": IntakeAdapter("anthropic"), "codex": IntakeAdapter("openai")}
    engine = Engine(workspace, providers)
    engine.trust("operator")
    intake = Supervisor(engine).ask("Add a result", task_id="host-task")
    assert intake.status == "proposed"
    broker = HumanGateBroker(ApplicationService(workspace), "session-1", {"name": "test-host", "version": "1"})
    yield engine, intake, broker, providers
    broker.close()
    engine.close()


def confirmed(broker, kind, subject, key):
    gate = broker.prepare(kind, subject, key)
    return broker.resolve(gate, {"action": "accept", "content": {"decision": "yes"}})


def run_queued(broker, providers):
    with broker.service.queue() as queue:
        result = process_one(queue, registry=providers)
        assert result and result["status"] == "succeeded", result
        return result["result"]


def test_full_host_flow_keeps_three_separate_gates(gate_setup):
    engine, intake, broker, providers = gate_setup
    started = confirmed(broker, "start", intake.id, "start-1")
    assert started["gate_status"] == "applied"
    assert engine.store.get("host-task").status == "ready"
    assert engine.store.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 0
    state = run_queued(broker, providers)
    assert state["status"] == "awaiting_approval"
    execution = confirmed(broker, "execution", "host-task", "execution-1")
    assert execution["gate_status"] == "applied"
    state = run_queued(broker, providers)
    assert state["status"] == "awaiting_acceptance"
    accepted = confirmed(broker, "acceptance", "host-task", "accept-1")
    assert accepted["gate_status"] == "applied"
    assert engine.store.get("host-task").status == "succeeded"
    assert engine.store.get("host-task").calls == 4
    events = engine.store.events("host-task")
    assert sum(event["kind"] == "human_gate.applied" for event in events) == 3
    assert "human presence not" in accepted["assurance"]


@pytest.mark.parametrize("response,status", [
    ({"action": "decline"}, "declined"), ({"action": "cancel"}, "cancelled"),
    ({"action": "accept", "content": {"decision": "no"}}, "declined"),
    ({"action": "accept"}, "failed"),
    ({"action": "accept", "content": {"decision": True}}, "failed"),
    ({"action": "accept", "content": {"decision": 1}}, "failed"),
    ({"action": "accept", "content": {"decision": "yes", "actor": "human"}}, "failed"),
    ({"action": "approved", "content": {"decision": "yes"}}, "failed"),
    (True, "failed"),
])
def test_nonconfirmations_never_register_or_authorize(gate_setup, response, status):
    engine, intake, broker, _ = gate_setup
    gate = broker.prepare("start", intake.id, "start-1")
    assert broker.resolve(gate, response)["gate_status"] == status
    assert engine.store.db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0
    assert engine.store.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 0


@pytest.mark.parametrize("change", ["source", "profile", "task-control", "protected"])
def test_scope_changes_while_form_open_do_not_authorize(gate_setup, change):
    engine, intake, broker, _ = gate_setup
    gate = broker.prepare("start", intake.id, "start-1")
    relative = {"source": "input.txt", "profile": ".orchestrator/policies/new.md", "task-control": ".orchestrator/tasks/other.json", "protected": ".env"}[change]
    (engine.project.root / relative).write_text("changed")
    result = broker.resolve(gate, {"action": "accept", "content": {"decision": "yes"}})
    assert result["gate_status"] == "stale"
    assert engine.store.db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0


def test_expired_confirmation_is_not_approval(gate_setup, monkeypatch):
    engine, intake, broker, _ = gate_setup
    gate = broker.prepare("start", intake.id, "start-1")
    monkeypatch.setattr(time, "time", lambda: gate.expires_at + 1)
    result = broker.resolve(gate, {"action": "accept", "content": {"decision": "yes"}})
    assert result["gate_status"] == "expired"
    assert engine.store.get_intake(intake.id).status == "proposed"


def test_idempotent_retry_does_not_reprompt_or_reapply(gate_setup):
    engine, intake, broker, _ = gate_setup
    first = confirmed(broker, "start", intake.id, "start-1")
    old = broker.prepare("start", intake.id, "start-1")
    assert old.status == "applied" and old.id == first["gate_id"]
    assert engine.store.db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 1
    with pytest.raises(OrchestratorError, match="different operation"):
        broker.prepare("execution", "host-task", "start-1")


def test_gate_cannot_be_consumed_by_another_session(gate_setup):
    engine, intake, broker, _ = gate_setup
    gate = broker.prepare("start", intake.id, "start-1")
    with pytest.raises(OrchestratorError, match="owned"):
        broker.store.transition(gate.id, "another-session", "pending", "applying")
    assert broker.store.get(gate.id).status == "pending"


def test_parallel_host_cannot_prompt_for_same_pending_subject(gate_setup):
    _, intake, broker, _ = gate_setup
    broker.prepare("start", intake.id, "start-1")
    other = HumanGateBroker(broker.service, "session-2", {"name": "other", "version": "1"})
    try:
        with pytest.raises(OrchestratorError, match="already exists"):
            other.prepare("start", intake.id, "start-2")
    finally:
        other.close()


def test_interrupted_applying_intent_never_replays(gate_setup):
    _, intake, broker, _ = gate_setup
    gate = broker.prepare("start", intake.id, "start-1")
    broker.store.transition(gate.id, broker.session, "pending", "applying")
    with pytest.raises(OrchestratorError, match="uncertain"):
        broker.prepare("start", intake.id, "start-1")


def test_queue_failure_does_not_repeat_or_lie_about_registration(gate_setup, monkeypatch):
    engine, intake, broker, _ = gate_setup
    monkeypatch.setattr(broker.service, "invoke", lambda *args: (_ for _ in ()).throw(OrchestratorError("queue full")))
    result = confirmed(broker, "start", intake.id, "start-1")
    assert result["gate_status"] == "applied"
    assert "queue full" in result["result"]["scheduling_error"]
    assert engine.store.get("host-task").status == "ready"


def test_cancellation_after_execution_prompt_blocks_authority(gate_setup):
    engine, intake, broker, providers = gate_setup
    confirmed(broker, "start", intake.id, "start-1")
    run_queued(broker, providers)
    gate = broker.prepare("execution", "host-task", "execution-1")
    engine.store.request_cancel("host-task")
    result = broker.resolve(gate, {"action": "accept", "content": {"decision": "yes"}})
    assert result["gate_status"] == "stale"
    assert engine.store.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 0


def test_acceptance_rechecks_reviewed_worktree(gate_setup):
    engine, intake, broker, providers = gate_setup
    confirmed(broker, "start", intake.id, "start-1")
    run_queued(broker, providers)
    confirmed(broker, "execution", "host-task", "execution-1")
    run_queued(broker, providers)
    gate = broker.prepare("acceptance", "host-task", "accept-1")
    (engine.project.root / "result.txt").write_text("changed after review")
    assert broker.resolve(gate, {"action": "accept", "content": {"decision": "yes"}})["gate_status"] == "stale"
    assert engine.store.get("host-task").status == "awaiting_acceptance"


def test_precondition_is_inside_workspace_lock(gate_setup):
    engine, intake, broker, _ = gate_setup
    def callback():
        with engine.project.lock():
            raise AssertionError("should never acquire nested workspace lock")
    with pytest.raises(OrchestratorError, match="another controller"):
        Supervisor(engine).start(intake.id, Supervisor(engine).scope(intake), "operator", precondition=callback)
    assert engine.store.get_intake(intake.id).status == "proposed"


@pytest.mark.parametrize("tool", list(GATE_TOOLS))
@pytest.mark.parametrize("injected", ["approved", "decision", "confirm", "actor", "scope", "project"])
def test_model_cannot_supply_authority_fields(tool, injected):
    model = GATE_TOOLS[tool][0]
    data = {"request_id": "request-1", "intake_id" if tool == "request_start" else "task_id": "target", injected: True}
    with pytest.raises(ValidationError):
        model.model_validate(data)


def test_display_preserves_japanese_and_escapes_controls():
    text = safe_display({"goal": "日本語\u202e\x1b[2J"})
    assert "日本語" in text and "\u202e" not in text and "\x1b" not in text
    assert "\\u202e" in text and "\\u001b" in text


def test_huge_preview_does_not_approve_unseen_truncated_content(gate_setup):
    engine, intake, broker, _ = gate_setup
    intake.task.acceptance = ["詳細" * 15000]
    engine.store.save_intake(intake, "test.large")
    with pytest.raises(OrchestratorError, match="preview exceeds"):
        broker.prepare("start", intake.id, "start-1")


def test_cli_legacy_gate_flow_keeps_working(engine):
    controller, _, _ = engine
    controller.create(spec())
    state = controller.run("task-1")
    assert state.status == "awaiting_approval"
    controller.approve("task-1", controller.approval_scope(state), "legacy-operator")
    assert controller.run("task-1").status == "awaiting_acceptance"
    assert controller.accept("task-1", "legacy-operator").status == "succeeded"
