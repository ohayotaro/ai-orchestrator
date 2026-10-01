"""v0.8.7 explicit binding lifecycle cleanup."""
from __future__ import annotations

import pytest

from ai_orchestrator import authority
from ai_orchestrator.engine import Engine
from ai_orchestrator.human_gates import BindingCleanupRequest, HumanGateBroker, ProfileChangeRequest
from ai_orchestrator.models import OrchestratorError
from ai_orchestrator.service import ApplicationService
from ai_orchestrator.supervisor import Supervisor
from conftest import FakeAdapter, approve_and_run, spec
from test_v04_gates import IntakeAdapter
from test_v04_protocol import RecordingWorker, confirm as rpc_confirm, initialize, tool


def registry():
    return {
        "claude": IntakeAdapter("anthropic"),
        "codex": IntakeAdapter("openai"),
        "agy": IntakeAdapter("google"),
    }


def setup_blockers(workspace):
    providers = registry()
    engine = Engine(workspace, providers)
    engine.trust("operator")
    task = engine.create(spec("unfinished-task"))
    task = engine.run(task.spec.id)
    assert task.status == "awaiting_approval"
    intake = Supervisor(engine).ask("Add a different result", task_id="unfinished-intake-task")
    assert intake.status == "proposed"
    return engine, providers, task, intake


def confirm(broker, gate):
    return broker.resolve(gate, {"action": "accept", "content": {"decision": "yes"}})


def test_cleanup_preview_is_exact_and_does_not_mutate(workspace):
    engine, _, task, intake = setup_blockers(workspace)
    try:
        before = engine.project.snapshot()
        preview = authority.binding_cleanup_preview(
            engine, [task.spec.id], [intake.id]
        )
        assert preview["task_ids"] == ["unfinished-task"]
        assert preview["intake_ids"] == [intake.id]
        assert preview["tasks"][0]["status"] == "awaiting_approval"
        assert preview["intakes"][0]["status"] == "proposed"
        assert preview["workspace_rollback"] is False
        assert "does not delete history" in preview["effect"]
        assert engine.store.get(task.spec.id).status == "awaiting_approval"
        assert engine.store.get_intake(intake.id).status == "proposed"
        assert engine.project.snapshot() == before
    finally:
        engine.close()


def test_binding_cleanup_humangate_terminalizes_without_rollback(workspace):
    engine, _, task, intake = setup_blockers(workspace)
    # Model/user worktree data is deliberately present before cleanup. Binding
    # cleanup must not pretend to restore any file baseline.
    (workspace / "input.txt").write_text("existing uncommitted workspace change\n")
    before = (workspace / "input.txt").read_text()
    engine.close()

    broker = HumanGateBroker(
        ApplicationService(workspace), "cleanup-session", {"name": "test", "version": "1"}
    )
    try:
        gate = broker.prepare_binding_cleanup(
            BindingCleanupRequest(
                task_ids=[task.spec.id],
                intake_ids=[intake.id],
                request_id="cleanup-1",
            )
        )
        assert gate.kind == "binding_cleanup"
        assert "does NOT roll back" in gate.preview["operation"]
        message = broker.form(gate)["message"]
        assert "Abandon task(s): unfinished-task" in message
        assert f"Withdraw intake(s): {intake.id}" in message
        assert "Workspace rollback: NO" in message
        assert "Provider change: NOT included" in message
        assert len(message.splitlines()) < 16
        result = confirm(broker, gate)
        assert result["gate_status"] == "applied"
        assert result["result"]["abandoned_tasks"] == [task.spec.id]
        assert result["result"]["withdrawn_intakes"] == [intake.id]
        assert result["result"]["workspace_rollback"] is False
    finally:
        broker.close()

    check = Engine(workspace, registry())
    try:
        assert check.store.get(task.spec.id).status == "abandoned"
        assert check.store.get_intake(intake.id).status == "withdrawn"
        assert (workspace / "input.txt").read_text() == before
        assert task.spec.id not in check.store.active_task_ids()
        assert intake.id not in check.store.active_intake_ids()
        kinds = [event["kind"] for event in check.store.events()]
        assert "task.abandoned" in kinds
        assert "intake.withdrawn" in kinds
        assert "binding_cleanup.applied" in kinds
    finally:
        check.close()


def test_cleanup_decline_is_noop(workspace):
    engine, _, task, intake = setup_blockers(workspace)
    engine.close()
    broker = HumanGateBroker(
        ApplicationService(workspace), "cleanup-session", {"name": "test", "version": "1"}
    )
    try:
        gate = broker.prepare_binding_cleanup(
            BindingCleanupRequest(
                task_ids=[task.spec.id], intake_ids=[intake.id], request_id="cleanup-decline"
            )
        )
        result = broker.resolve(
            gate, {"action": "accept", "content": {"decision": "no"}}
        )
        assert result["gate_status"] == "declined"
    finally:
        broker.close()
    check = Engine(workspace, registry())
    try:
        assert check.store.get(task.spec.id).status == "awaiting_approval"
        assert check.store.get_intake(intake.id).status == "proposed"
    finally:
        check.close()


def test_cleanup_then_provider_change_can_complete(workspace):
    engine, _, task, intake = setup_blockers(workspace)
    preview = authority.provider_change_preview(engine, "engineering", "agy")
    assert preview["ready"] is False
    assert preview["blocked_by"]["task_ids"] == [task.spec.id]
    assert preview["blocked_by"]["intake_ids"] == [intake.id]
    engine.close()

    broker = HumanGateBroker(
        ApplicationService(workspace), "cleanup-session", {"name": "test", "version": "1"}
    )
    try:
        cleanup = broker.prepare_binding_cleanup(
            BindingCleanupRequest(
                task_ids=[task.spec.id], intake_ids=[intake.id], request_id="cleanup-before-provider"
            )
        )
        assert confirm(broker, cleanup)["gate_status"] == "applied"

        provider_preview = broker.service.invoke(
            "preview_provider_change", {"provider": "engineering", "adapter": "agy"}
        )
        assert provider_preview["ready"] is True
        assert provider_preview["blocked_by"] == {"task_ids": [], "intake_ids": []}

        change = broker.prepare_provider_change(
            ProfileChangeRequest(
                provider="engineering", adapter="agy", request_id="provider-after-cleanup"
            )
        )
        applied = confirm(broker, change)
        assert applied["gate_status"] == "applied"
        assert applied["result"]["adapter"] == "agy"
    finally:
        broker.close()

    final = Engine(workspace)
    try:
        assert final.profile.providers["engineering"].adapter == "agy"
        assert final.store.trusted(final.profile_digest)
    finally:
        final.close()


def test_binding_cleanup_rejects_running_or_terminal_targets(workspace):
    providers = registry()
    engine = Engine(workspace, providers)
    try:
        engine.trust("operator")
        running = engine.create(spec("running-task"))
        running.status = "running"
        engine.store.save(running, "test.running")
        with pytest.raises(OrchestratorError, match="running task"):
            authority.binding_cleanup_preview(engine, [running.spec.id], [])

        terminal = engine.create(spec("terminal-task"))
        terminal.status = "failed"
        engine.store.save(terminal, "test.failed")
        with pytest.raises(OrchestratorError, match="already terminal"):
            authority.binding_cleanup_preview(engine, [terminal.spec.id], [])
    finally:
        engine.close()


def test_binding_cleanup_mcp_flow_is_separate_from_provider_change(workspace):
    engine, _, task, intake = setup_blockers(workspace)
    engine.close()
    from ai_orchestrator.mcp_server import StdioServer

    manager = RecordingWorker()
    server = StdioServer(
        ApplicationService(workspace), single_terminal=True, auto_worker=manager
    )
    try:
        initialize(server)
        preview = tool(
            server,
            "preview_binding_cleanup",
            {"task_ids": [task.spec.id], "intake_ids": [intake.id]},
            id="cleanup-preview",
        )
        assert preview["result"]["structuredContent"]["workspace_rollback"] is False
        prompt = tool(
            server,
            "request_binding_cleanup",
            {
                "task_ids": [task.spec.id],
                "intake_ids": [intake.id],
                "request_id": "cleanup-mcp",
            },
            id="cleanup-call",
        )
        assert prompt["method"] == "elicitation/create"
        final = rpc_confirm(server, prompt)
        assert final["result"]["structuredContent"]["gate_status"] == "applied"
        assert manager.kicks == 0
    finally:
        server.close()


def test_plain_approved_review_never_enters_rework(workspace):
    reasoning = FakeAdapter("anthropic")
    engineering = FakeAdapter("openai")
    engine = Engine(workspace, {"claude": reasoning, "codex": engineering})
    try:
        engine.trust("operator")
        state = engine.create(spec("approved-review"))
        state.allowed_paths = ["result.txt"]
        engine.store.save(state, "test.allowed_paths")
        state = approve_and_run(engine, state.spec.id)
        assert state.status == "awaiting_acceptance"
        assert state.attempt == 1
        assert state.feedback == ""
        assert not any(
            event["kind"] in ("workflow.rework", "rework.requested")
            for event in engine.store.events(state.spec.id)
        )
    finally:
        engine.close()
