"""v0.8.6 bounded authority-control: provider changes and task-scoped broad permission."""
from __future__ import annotations

import yaml
import pytest

from ai_orchestrator.engine import Engine
from ai_orchestrator.human_gates import HumanGateBroker, ProfileChangeRequest, ProviderPermissionRequest
from ai_orchestrator.models import OrchestratorError
from ai_orchestrator.project import Project
from ai_orchestrator.service import ApplicationService
from ai_orchestrator.supervisor import Supervisor
from ai_orchestrator.worker import process_one
from conftest import FakeAdapter, spec
from test_v04_gates import IntakeAdapter
from test_v04_protocol import RecordingWorker, confirm as rpc_confirm, initialize, tool


class PermissionAdapter(FakeAdapter):
    def __init__(self, family: str):
        super().__init__(family)
        self.execute_permissions: list[frozenset[str]] = []

    def execute(self, request):
        if request.phase == "execute":
            self.execute_permissions.append(request.provider_permissions)
        return super().execute(request)


def edit_profile(workspace, mutate):
    path = workspace / ".orchestrator/config.yaml"
    data = yaml.safe_load(path.read_text())
    mutate(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def confirm(broker, gate):
    return broker.resolve(gate, {"action": "accept", "content": {"decision": "yes"}})


def test_provider_change_preview_and_humangate_apply_and_trust(workspace):
    engine = Engine(workspace)
    try:
        engine.trust("operator")
        old_digest = engine.profile_digest
    finally:
        engine.close()

    service = ApplicationService(workspace)
    preview = service.invoke(
        "preview_provider_change",
        {"provider": "engineering", "adapter": "agy"},
    )
    assert preview["change"]["before"]["adapter"] == "codex"
    assert preview["change"]["after"]["adapter"] == "agy"
    assert preview["change"]["current_profile_digest"] == old_digest
    assert preview["change"]["proposed_profile_digest"] != old_digest

    broker = HumanGateBroker(service, "authority-session", {"name": "test", "version": "1"})
    try:
        gate = broker.prepare_provider_change(
            ProfileChangeRequest(provider="engineering", adapter="agy", request_id="provider-change-1")
        )
        assert gate.kind == "profile_change"
        assert "trust only the resulting profile digest" in gate.preview["operation"]
        result = confirm(broker, gate)
        assert result["gate_status"] == "applied"
        applied = result["result"]
        assert applied["provider"] == "engineering"
        assert applied["adapter"] == "agy"
        assert applied["previous_profile_digest"] == old_digest
        assert applied["trusted_profile"] == preview["change"]["proposed_profile_digest"]
    finally:
        broker.close()

    updated = Engine(workspace)
    try:
        assert updated.profile.providers["engineering"].adapter == "agy"
        assert updated.store.trusted(updated.profile_digest)
        assert not updated.store.trusted(old_digest)
        kinds = [event["kind"] for event in updated.store.events() if event["task_id"] is None]
        assert "profile_change.intent" in kinds
        assert "profile_change.applied" in kinds
        assert "profile.trusted" in kinds
    finally:
        updated.close()


def test_provider_change_resets_adapter_specific_overrides(workspace):
    edit_profile(
        workspace,
        lambda data: data["providers"]["engineering"].update(
            executable="/tmp/vendor-specific-cli",
            model="vendor-model",
            effort="high",
        ),
    )
    engine = Engine(workspace)
    try:
        engine.trust("operator")
    finally:
        engine.close()

    service = ApplicationService(workspace)
    preview = service.invoke(
        "preview_provider_change",
        {"provider": "engineering", "adapter": "agy"},
    )
    assert preview["change"]["reset_adapter_specific_fields"] == ["effort", "executable", "model"]

    broker = HumanGateBroker(service, "authority-session", {"name": "test", "version": "1"})
    try:
        result = confirm(
            broker,
            broker.prepare_provider_change(
                ProfileChangeRequest(provider="engineering", adapter="agy", request_id="provider-change-2")
            ),
        )
        assert result["gate_status"] == "applied"
    finally:
        broker.close()

    raw = yaml.safe_load((workspace / ".orchestrator/config.yaml").read_text())
    slot = raw["providers"]["engineering"]
    assert slot["adapter"] == "agy"
    assert "executable" not in slot and "model" not in slot and "effort" not in slot


def test_provider_change_decline_is_noop(workspace):
    engine = Engine(workspace)
    try:
        engine.trust("operator")
        old_digest = engine.profile_digest
    finally:
        engine.close()
    broker = HumanGateBroker(ApplicationService(workspace), "authority-session", {"name": "test", "version": "1"})
    try:
        gate = broker.prepare_provider_change(
            ProfileChangeRequest(provider="engineering", adapter="agy", request_id="provider-change-decline")
        )
        result = broker.resolve(gate, {"action": "accept", "content": {"decision": "no"}})
        assert result["gate_status"] == "declined"
    finally:
        broker.close()
    check = Engine(workspace)
    try:
        assert check.profile.providers["engineering"].adapter == "codex"
        assert check.profile_digest == old_digest
        assert check.store.trusted(old_digest)
    finally:
        check.close()


def test_provider_change_preview_reports_active_task_blocker(workspace):
    registry = {"claude": FakeAdapter("anthropic"), "codex": FakeAdapter("openai"), "agy": FakeAdapter("google")}
    engine = Engine(workspace, registry)
    try:
        engine.trust("operator")
        engine.create(spec("active-task"))
        from ai_orchestrator.authority import provider_change_preview
        preview = provider_change_preview(engine, "engineering", "agy")
        assert preview["ready"] is False
        assert preview["blocked_by"] == {"task_ids": ["active-task"], "intake_ids": []}
    finally:
        engine.close()


def test_provider_change_preview_reports_unconsumed_intake_blocker(workspace):
    providers = {
        "claude": IntakeAdapter("anthropic"),
        "codex": IntakeAdapter("openai"),
        "agy": IntakeAdapter("google"),
    }
    engine = Engine(workspace, providers)
    try:
        engine.trust("operator")
        intake = Supervisor(engine).ask("Add a result", task_id="pending-intake")
        assert intake.status == "proposed"
        from ai_orchestrator.authority import provider_change_preview
        preview = provider_change_preview(engine, "engineering", "agy")
        assert preview["ready"] is False
        assert preview["blocked_by"] == {"task_ids": [], "intake_ids": [intake.id]}
    finally:
        engine.close()


def test_provider_change_works_through_single_terminal_mcp(workspace):
    engine = Engine(workspace)
    try:
        engine.trust("operator")
    finally:
        engine.close()
    manager = RecordingWorker()
    from ai_orchestrator.mcp_server import StdioServer
    server = StdioServer(ApplicationService(workspace), single_terminal=True, auto_worker=manager)
    try:
        initialize(server)
        preview = tool(
            server,
            "preview_provider_change",
            {"provider": "engineering", "adapter": "agy"},
            id="preview-provider",
        )
        assert preview["result"]["structuredContent"]["change"]["after"]["adapter"] == "agy"
        prompt = tool(
            server,
            "request_provider_change",
            {"provider": "engineering", "adapter": "agy", "request_id": "mcp-provider-change"},
            id="provider-change-call",
        )
        assert prompt["method"] == "elicitation/create"
        final = rpc_confirm(server, prompt)
        payload = final["result"]["structuredContent"]
        assert payload["gate_status"] == "applied"
        assert payload["result"]["adapter"] == "agy"
        assert manager.kicks == 0
    finally:
        server.close()
    check = Engine(workspace)
    try:
        assert check.profile.providers["engineering"].adapter == "agy"
        assert check.store.trusted(check.profile_digest)
    finally:
        check.close()


def agy_task_setup(workspace):
    edit_profile(workspace, lambda data: data["providers"]["engineering"].update(adapter="agy"))
    reasoning = PermissionAdapter("anthropic")
    engineering = PermissionAdapter("google")
    registry = {"claude": reasoning, "agy": engineering}
    engine = Engine(workspace, registry)
    engine.trust("operator")
    state = engine.create(spec("agy-permission-task"))
    state.allowed_paths = ["result.txt"]
    engine.store.save(state, "test.allowed_paths")
    state = engine.run(state.spec.id)
    assert state.status == "awaiting_approval", state.error
    return engine, registry, engineering


def test_execution_approval_alone_does_not_enable_agy_dangerous_permission(workspace):
    engine, _, engineering = agy_task_setup(workspace)
    try:
        state = engine.store.get("agy-permission-task")
        engine.approve(state.spec.id, engine.approval_scope(state), "operator")
        state = engine.run(state.spec.id)
        assert state.status == "awaiting_acceptance", state.error
        assert engineering.execute_permissions == [frozenset()]
    finally:
        engine.close()


def test_dedicated_permission_gate_then_execution_passes_flag_only_for_attempt(workspace):
    engine, registry, engineering = agy_task_setup(workspace)
    broker = HumanGateBroker(ApplicationService(workspace), "authority-session", {"name": "test", "version": "1"})
    try:
        permission_gate = broker.prepare_provider_permission(
            ProviderPermissionRequest(
                task_id="agy-permission-task",
                request_id="agy-permission-1",
                permission="agy_dangerously_skip_permissions",
            )
        )
        assert permission_gate.kind == "provider_permission"
        assert "auto-approves all AGY-native tool permission requests" in permission_gate.preview["operation"]
        permission_result = confirm(broker, permission_gate)
        assert permission_result["gate_status"] == "applied"
        assert permission_result["result"]["task_status"] == "awaiting_approval"
        assert "next_action" in permission_result["result"]

        state = engine.store.get("agy-permission-task")
        grant = state.provider_permission_grants["agy_dangerously_skip_permissions"]
        assert grant.attempt == 1
        assert grant.nodes == ["implement"]

        execution_gate = broker.prepare("execution", state.spec.id, "execution-after-permission")
        execution_result = confirm(broker, execution_gate)
        assert execution_result["gate_status"] == "applied"

        with broker.service.queue() as queue:
            processed = process_one(queue, registry=registry)
            assert processed and processed["status"] == "succeeded", processed

        state = engine.store.get("agy-permission-task")
        assert state.status == "awaiting_acceptance", state.error
        assert engineering.execute_permissions == [
            frozenset({"agy_dangerously_skip_permissions"})
        ]
    finally:
        broker.close()
        engine.close()


def test_provider_permission_grant_becomes_stale_if_worktree_changes(workspace):
    engine, _, _ = agy_task_setup(workspace)
    broker = HumanGateBroker(ApplicationService(workspace), "authority-session", {"name": "test", "version": "1"})
    try:
        gate = broker.prepare_provider_permission(
            ProviderPermissionRequest(
                task_id="agy-permission-task",
                request_id="agy-permission-stale",
                permission="agy_dangerously_skip_permissions",
            )
        )
        assert confirm(broker, gate)["gate_status"] == "applied"
        (workspace / "input.txt").write_text("changed after provider-permission confirmation\n")
        with pytest.raises(OrchestratorError, match="grant .* is stale"):
            broker.prepare("execution", "agy-permission-task", "execution-stale")
    finally:
        broker.close()
        engine.close()


def test_provider_permission_gate_rejects_non_agy_execution(workspace):
    registry = {"claude": FakeAdapter("anthropic"), "codex": FakeAdapter("openai")}
    engine = Engine(workspace, registry)
    try:
        engine.trust("operator")
        state = engine.create(spec("codex-task"))
        state.allowed_paths = ["result.txt"]
        engine.store.save(state, "test.allowed_paths")
        assert engine.run(state.spec.id).status == "awaiting_approval"
    finally:
        engine.close()

    broker = HumanGateBroker(ApplicationService(workspace), "authority-session", {"name": "test", "version": "1"})
    try:
        with pytest.raises(OrchestratorError, match="no Antigravity"):
            broker.prepare_provider_permission(
                ProviderPermissionRequest(
                    task_id="codex-task",
                    request_id="bad-permission",
                    permission="agy_dangerously_skip_permissions",
                )
            )
    finally:
        broker.close()
