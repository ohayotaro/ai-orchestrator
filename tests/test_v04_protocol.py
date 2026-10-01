"""Full-duplex gate correlation, native Yes/No behavior and legacy negotiation."""
import io
import time

import pytest

from ai_orchestrator.mcp_server import StdioServer
from ai_orchestrator.service import ApplicationService
from test_v04_gates import gate_setup, run_queued


class RecordingWorker:
    def __init__(self):
        self.kicks = 0
        self.closed = False
    def kick(self):
        self.kicks += 1
    def status(self):
        return {"mode": "test", "kicks": self.kicks}
    def close(self):
        self.closed = True


def rpc(method, params=None, id=1):
    return {"jsonrpc": "2.0", "id": id, "method": method, "params": params or {}}


def initialize(server, capabilities=None, protocol="2025-06-18"):
    answer = server.handle(rpc("initialize", {"protocolVersion": protocol, "capabilities": capabilities if capabilities is not None else {"elicitation": {}}, "clientInfo": {"name": "test", "version": "1"}}))
    server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
    return answer


def tool(server, name, arguments, id=10):
    return server.handle(rpc("tools/call", {"name": name, "arguments": arguments}, id))


def confirm(server, prompt, action="accept", content=None):
    return server.handle({"jsonrpc": "2.0", "id": prompt["id"], "result": {"action": action, "content": {"decision": "yes"} if content is None else content}})


@pytest.fixture
def server_setup(gate_setup):
    engine, intake, broker, providers = gate_setup
    manager = RecordingWorker()
    server = StdioServer(broker.service, single_terminal=True, auto_worker=manager)
    initialize(server)
    yield server, manager, intake, engine, broker, providers
    server.close()


def test_native_start_response_is_not_model_tool_permission(server_setup):
    server, manager, intake, engine, _, _ = server_setup
    prompt = tool(server, "request_start", {"intake_id": intake.id, "request_id": "native-1"}, id="caller-1")
    assert prompt["method"] == "elicitation/create"
    assert prompt["params"]["requestedSchema"]["properties"]["decision"]["enum"] == ["yes","no"]
    assert engine.store.db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0
    result = confirm(server, prompt)
    assert result["id"] == "caller-1"
    assert result["result"]["structuredContent"]["gate_status"] == "applied"
    assert manager.kicks == 1
    assert engine.store.get("host-task").status == "ready"
    assert server.handle({"jsonrpc": "2.0", "id": prompt["id"], "result": {"action": "accept", "content": {"decision": "yes"}}}) is None
    assert manager.kicks == 1


def test_native_whole_flow_has_three_independent_confirmations(server_setup):
    server, manager, intake, engine, broker, providers = server_setup
    prompt = tool(server, "request_start", {"intake_id": intake.id, "request_id": "native-1"})
    confirm(server, prompt)
    run_queued(broker, providers)
    prompt = tool(server, "request_execution", {"task_id": "host-task", "request_id": "native-2"})
    assert "implementation attempt" in prompt["params"]["message"]
    confirm(server, prompt)
    run_queued(broker, providers)
    prompt = tool(server, "request_acceptance", {"task_id": "host-task", "request_id": "native-3"})
    assert "validation" in prompt["params"]["message"] and "reviewed_snapshot" in prompt["params"]["message"]
    assert engine.store.get("host-task").status == "awaiting_acceptance"
    confirm(server, prompt)
    assert engine.store.get("host-task").status == "succeeded"
    assert manager.kicks == 2


@pytest.mark.parametrize("caps,protocol", [({}, "2025-06-18"), ({"elicitation": {"url": {}}}, "2025-06-18"), ({"elicitation": {}}, "2024-11-05"), ({"elicitation": None}, "2025-06-18")])
def test_unsupported_forms_fail_closed_without_prompt(gate_setup, caps, protocol):
    engine, intake, broker, _ = gate_setup
    manager = RecordingWorker()
    server = StdioServer(broker.service, single_terminal=True, auto_worker=manager)
    try:
        initialize(server, caps, protocol)
        answer = tool(server, "request_start", {"intake_id": intake.id, "request_id": "native-1"})
        assert answer["result"]["isError"] is True
        assert "does not advertise" in answer["result"]["content"][0]["text"]
        assert engine.store.get_intake(intake.id).status == "proposed"
        assert manager.kicks == 0
    finally:
        server.close()


def test_form_only_capability_supported(gate_setup):
    _, intake, broker, _ = gate_setup
    server = StdioServer(broker.service, single_terminal=True, auto_worker=RecordingWorker())
    try:
        initialize(server, {"elicitation": {"form": {}}})
        assert tool(server, "request_start", {"intake_id": intake.id, "request_id": "native-1"})["method"] == "elicitation/create"
    finally:
        server.close()


@pytest.mark.parametrize("action,content,expected", [("decline", {}, "declined"), ("cancel", {}, "cancelled"), ("accept", {"decision": "no"}, "declined"), ("accept", {"confirm": "true"}, "failed")])
def test_native_denial_no_side_effects(server_setup, action, content, expected):
    server, manager, intake, engine, _, _ = server_setup
    prompt = tool(server, "request_start", {"intake_id": intake.id, "request_id": "native-1"})
    result = confirm(server, prompt, action, content)
    assert result["result"]["structuredContent"]["gate_status"] == expected
    assert manager.kicks == 0
    assert engine.store.db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0


def test_unrelated_response_does_not_authorize(server_setup):
    server, _, intake, engine, _, _ = server_setup
    tool(server, "request_start", {"intake_id": intake.id, "request_id": "native-1"})
    assert server.handle({"jsonrpc": "2.0", "id": "model-chosen-id", "result": {"action": "accept", "content": {"decision": "yes"}}}) is None
    assert server.pending is not None
    assert engine.store.db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0


def test_ping_and_read_tools_work_while_confirmation_pending(server_setup):
    server, _, intake, _, _, _ = server_setup
    tool(server, "request_start", {"intake_id": intake.id, "request_id": "native-1"})
    assert server.handle(rpc("ping", id=2))["result"] == {}
    assert tool(server, "inspect_project", {}, id=3)["result"]["structuredContent"]["host_confirmation"]["form_supported"] is True
    assert tool(server, "request_start", {"intake_id": intake.id, "request_id": "native-2"}, id=4)["result"]["isError"] is True


def test_cancellation_of_origin_request_invalidates_form(server_setup):
    server, _, intake, engine, _, _ = server_setup
    prompt = tool(server, "request_start", {"intake_id": intake.id, "request_id": "native-1"}, id="origin")
    result = server.handle({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": "origin"}})
    assert result["id"] == "origin"
    assert result["result"]["structuredContent"]["gate_status"] == "cancelled"
    assert confirm(server, prompt) is None
    assert engine.store.db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0


def test_deadline_invalidates_even_without_host_reply(server_setup):
    server, _, intake, _, _, _ = server_setup
    prompt = tool(server, "request_start", {"intake_id": intake.id, "request_id": "native-1"})
    server.pending.deadline = time.monotonic() - 1
    result = server.expire()
    assert result["result"]["structuredContent"]["gate_status"] == "expired"
    assert confirm(server, prompt) is None


def test_host_disconnect_cancels_pending_gate(server_setup):
    server, manager, intake, engine, _, _ = server_setup
    tool(server, "request_start", {"intake_id": intake.id, "request_id": "native-1"})
    gate_id = server.pending.gate.id
    from ai_orchestrator.human_gates import GateStore
    server.close()
    store = GateStore(engine.project)
    try:
        assert store.get(gate_id).status == "cancelled"
    finally:
        store.close()
    assert manager.closed


@pytest.mark.parametrize("field", ["actor", "approved", "scope", "decision", "confirm"])
def test_tool_data_cannot_answer_form(server_setup, field):
    server, _, intake, engine, _, _ = server_setup
    answer = tool(server, "request_start", {"intake_id": intake.id, "request_id": "native-1", field: True})
    assert answer["error"]["code"] == -32602
    assert server.pending is None
    assert engine.store.get_intake(intake.id).status == "proposed"


def test_normal_tool_allow_meta_is_not_gate_authority(server_setup):
    server, _, intake, engine, _, _ = server_setup
    result = server.handle(rpc("tools/call", {"name": "request_start", "arguments": {"intake_id": intake.id, "request_id": "native-1"}, "_meta": {"approved": True, "human": True}}))
    assert result["method"] == "elicitation/create"
    assert engine.store.get_intake(intake.id).status == "proposed"


def test_legacy_serve_has_no_native_authority_tools(gate_setup):
    _, intake, broker, _ = gate_setup
    server = StdioServer(broker.service)
    initialize(server)
    tools = server.handle(rpc("tools/list"))["result"]["tools"]
    assert len(tools) == 9
    assert tool(server, "request_start", {"intake_id": intake.id, "request_id": "request-1"})["error"]["code"] == -32602
    assert server.auto_worker is None


def test_single_terminal_advertises_bounded_authority_tools(server_setup):
    server, _, _, _, _, _ = server_setup
    names = {item["name"] for item in server.handle(rpc("tools/list"))["result"]["tools"]}
    assert "preview_provider_change" in names
    assert "request_provider_change" in names
    assert "request_provider_permission" in names


def test_other_session_expiry_does_not_crash_transport(server_setup):
    server, _, intake, _, _, _ = server_setup
    # Prepare without answering, then simulate another session's expiry cleanup.
    tool(server, "request_start", {"intake_id": intake.id, "request_id": "expiry-race"}, id=90)
    pending = server.pending
    server.broker.store.transition(pending.gate.id, server.session, 'pending', 'expired')
    server.pending.deadline = 0
    final = server.expire()
    assert final['result']['isError']
    assert final['result']['structuredContent']['gate_status'] == 'stale'
