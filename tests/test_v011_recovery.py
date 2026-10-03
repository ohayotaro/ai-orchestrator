"""v0.11 conservative recovery and durability crash-injection regressions."""
from __future__ import annotations

import pytest

from ai_orchestrator.human_gates import HumanGate, HumanGateBroker
from ai_orchestrator.providers import ProviderExecutionError, _classify_cli_failure
from ai_orchestrator.workspaces import WorkspaceManager
from conftest import spec


def _approved_scoped_task(controller, task_id: str):
    state = controller.create(spec(task_id))
    # Supervisor-created write tasks always carry exact allowed_paths. Set the
    # same contract explicitly here so the built-in shared workflow is executed
    # through the guarded private-worktree path.
    state.allowed_paths = ["result.txt"]
    controller.store.save(state, "test.allowed_paths")
    state = controller.run(task_id)
    assert state.status == "awaiting_approval"
    old_scope = controller.approval_scope(state)
    controller.approve(task_id, old_scope, "test-operator")
    return state, old_scope


def test_pre_dispatch_interruption_can_recover_only_with_fresh_approval(engine, monkeypatch):
    controller, _reasoning, _engineering = engine
    task_id = "recover-before-dispatch"
    approved, old_scope = _approved_scoped_task(controller, task_id)
    calls_before_execute = approved.calls

    real_save = controller.store.save

    def crash_before_dispatch(state, kind, payload=None, *, create=False, clear_approvals=False):
        # call.started reservations are durable by this point, but the batch's
        # provider-dispatch marker is not. SystemExit models a hard interruption
        # because normal workflow Exception handlers deliberately do not consume it.
        if kind == "workflow.guarded_write.started":
            raise SystemExit("synthetic hard crash before provider dispatch")
        return real_save(
            state, kind, payload, create=create, clear_approvals=clear_approvals
        )

    with monkeypatch.context() as scoped:
        scoped.setattr(controller.store, "save", crash_before_dispatch)
        with pytest.raises(SystemExit, match="before provider dispatch"):
            controller.run(task_id)

    interrupted = controller.store.get(task_id)
    assert interrupted.status == "running"
    assert interrupted.calls == calls_before_execute + 1

    diagnosis = controller.recovery_status(task_id)
    assert diagnosis["classification"] == "safe_pre_effect_retry"
    assert diagnosis["retry_safe"] is True
    assert diagnosis["requires_execution_reapproval"] is True
    assert diagnosis["automatic_replay"] is False
    assert diagnosis["evidence"]["provider_dispatch_started"] is False
    assert diagnosis["evidence"]["reserved_calls"] == 1

    recovered = controller.recover(task_id)
    assert recovered.status == "awaiting_approval"
    assert recovered.phase == "execute"
    assert recovered.calls == calls_before_execute
    assert recovered.workflow_nodes["implement"].status == "pending"
    assert not controller.store.approved(task_id, old_scope)

    recovery_artifact = controller.store.latest(recovered, "recovery")
    assert recovery_artifact["classification"] == "safe_pre_effect_retry"
    assert recovery_artifact["automatic_replay"] is False

    fresh_scope = controller.approval_scope(recovered)
    assert fresh_scope != old_scope
    controller.approve(task_id, fresh_scope, "test-operator")
    completed = controller.run(task_id)
    assert completed.status == "awaiting_acceptance", completed.error


def test_provider_dispatch_interruption_is_not_replayed(engine, monkeypatch):
    controller, _reasoning, engineering = engine
    task_id = "recover-after-dispatch"
    _approved, old_scope = _approved_scoped_task(controller, task_id)

    def crash_in_provider(_request):
        raise SystemExit("synthetic provider process loss")

    with monkeypatch.context() as scoped:
        scoped.setattr(engineering, "execute", crash_in_provider)
        with pytest.raises(SystemExit, match="provider process loss"):
            controller.run(task_id)

    interrupted = controller.store.get(task_id)
    assert interrupted.status == "running"
    diagnosis = controller.recovery_status(task_id)
    assert diagnosis["classification"] == "uncertain_effect"
    assert diagnosis["retry_safe"] is False
    assert diagnosis["automatic_replay"] is False
    assert diagnosis["evidence"]["provider_dispatch_started"] is True
    assert "duplicate cost or effects" in diagnosis["reason"]

    recovered = controller.recover(task_id)
    assert recovered.status == "failed"
    assert recovered.workflow_nodes["implement"].status == "failed"
    assert not controller.store.approved(task_id, old_scope)
    assert not (controller.project.root / "result.txt").exists()


def test_interruption_after_root_integration_never_rolls_back_or_replays(engine, monkeypatch):
    controller, _reasoning, _engineering = engine
    task_id = "recover-during-integration"
    _approved, _old_scope = _approved_scoped_task(controller, task_id)

    real_save = controller.store.save

    def crash_after_apply(state, kind, payload=None, *, create=False, clear_approvals=False):
        # apply_integrated() has already changed the root worktree when this
        # durable acknowledgement is attempted.
        if kind == "workspace.integrated":
            raise SystemExit("synthetic crash after root integration")
        return real_save(
            state, kind, payload, create=create, clear_approvals=clear_approvals
        )

    with monkeypatch.context() as scoped:
        scoped.setattr(controller.store, "save", crash_after_apply)
        with pytest.raises(SystemExit, match="after root integration"):
            controller.run(task_id)

    assert (controller.project.root / "result.txt").read_text() == "implemented\n"
    diagnosis = controller.recovery_status(task_id)
    assert diagnosis["classification"] == "uncertain_effect"
    assert diagnosis["retry_safe"] is False
    assert diagnosis["evidence"]["integration_started"] is True

    recovered = controller.recover(task_id)
    assert recovered.status == "failed"
    assert "was not rolled back" in recovered.error
    # Recovery cleans private worktrees only. It does not guess whether the
    # aggregate root effect should be reverted.
    assert (controller.project.root / "result.txt").read_text() == "implemented\n"
    artifact = controller.store.latest(recovered, "recovery")
    assert artifact["classification"] == "uncertain_effect"
    assert artifact["automatic_replay"] is False


def test_workspace_cleanup_is_idempotent_after_recovery(engine):
    controller, _reasoning, _engineering = engine
    # Explicitly exercise cleanup's no-op durability property: repeated cleanup
    # of an absent task workspace must not touch the project worktree.
    before = controller.project.snapshot()
    assert WorkspaceManager.cleanup_task(controller.project, "never-started") == []
    assert WorkspaceManager.cleanup_task(controller.project, "never-started") == []
    assert controller.project.snapshot() == before


def test_provider_failure_taxonomy_is_content_free():
    assert _classify_cli_failure("HTTP 429 rate limit exceeded") == "quota"
    assert _classify_cli_failure("authentication required: please sign in") == "authentication"
    assert _classify_cli_failure("permission denied") == "permission"
    assert _classify_cli_failure("invalid config value") == "configuration"
    assert _classify_cli_failure("provider exited unexpectedly") == "provider_process"

    error = ProviderExecutionError(
        "structured output did not match the requested result contract",
        {"provider": "fixture", "process_returncode": 0},
    )
    assert error.diagnostics == {
        "provider": "fixture",
        "process_returncode": 0,
        "failure_category": "protocol",
    }


def test_applying_human_gate_is_reported_as_uncertain_and_non_replayable():
    gate = HumanGate(
        id="G-test",
        session="session",
        local_uid=1,
        actor="operator",
        client={"name": "fixture"},
        request_id="request",
        kind="execution",
        subject="task-1",
        task_id="task-1",
        scope="display-scope",
        kernel_scope="kernel-scope",
        preview={},
        authority_request=None,
        created_at=1.0,
        expires_at=9999999999.0,
        status="applying",
    )
    view = HumanGateBroker.describe(gate)
    assert view["durability"]["effect_state"] == "uncertain"
    assert view["durability"]["automatic_replay"] is False
    assert view["durability"]["request_reuse_allowed"] is False
