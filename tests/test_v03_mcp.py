"""MCP transport tests use actual JSON-RPC bytes; no billable provider calls."""

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ai_orchestrator.engine import Engine
from ai_orchestrator.mcp_server import MAX_MESSAGE_BYTES, StdioServer, serve
from ai_orchestrator.models import OrchestratorError
from ai_orchestrator.service import ApplicationService, TOOLS
from ai_orchestrator.worker import WORKER_MARKER


def message(method, params=None, request_id=1):
    result = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if request_id is not None:
        result["id"] = request_id
    return result


def initialize(server, version="2025-06-18"):
    result = server.handle(message("initialize", {"protocolVersion": version, "capabilities": {}, "clientInfo": {"name": "test-client", "version": "1"}}))
    assert server.handle(message("notifications/initialized", request_id=None)) is None
    return result


@pytest.fixture
def server(workspace):
    return StdioServer(ApplicationService(workspace))


def test_initialize_and_list_advertises_only_implemented_tools(server):
    result = initialize(server)
    assert result["result"]["protocolVersion"] == "2025-06-18"
    assert result["result"]["capabilities"] == {"tools": {"listChanged": False}}
    listed = server.handle(message("tools/list"))["result"]["tools"]
    assert {t["name"] for t in listed} == set(TOOLS)
    assert not {"trust", "start_task", "approve_execution", "accept_task"} & set(TOOLS)
    assert all(t["inputSchema"]["additionalProperties"] is False for t in listed)
    assert "user said yes" not in json.dumps([t["inputSchema"] for t in listed])


@pytest.mark.parametrize("version,expected", [("2024-11-05", "2024-11-05"), ("2025-03-26", "2025-03-26"), ("2099-01-01", "2025-06-18")])
def test_protocol_negotiation(server, version, expected):
    assert initialize(server, version)["result"]["protocolVersion"] == expected


def test_preinitialize_unknown_methods_bad_arguments(server):
    assert server.handle(message("tools/list"))["error"]["code"] == -32600
    assert server.handle(message("ping"))["result"] == {}
    initialize(server)
    assert server.handle(message("resources/list"))["error"]["code"] == -32601
    assert server.handle(message("tools/call", {"name": "approve_execution", "arguments": {}}))["error"]["code"] == -32602
    assert server.handle(message("tools/call", {"name": "inspect_project", "arguments": {"project": "/etc"}}))["error"]["code"] == -32602
    assert server.handle(message("tools/list", {"cursor": "unknown"}))["error"]["code"] == -32602


def test_unknown_job_is_a_tool_error_not_protocol_error(server):
    initialize(server)
    result = server.handle(message("tools/call", {"name": "get_job", "arguments": {"job_id": "J-unknown"}}))
    assert result["result"]["isError"] is True
    assert "unknown job" in result["result"]["content"][0]["text"]


def test_metadata_is_allowed_but_never_authority(server):
    initialize(server)
    result = server.handle(message("tools/call", {"name": "inspect_project", "arguments": {}, "_meta": {"progressToken": 1, "approved": True}}))
    assert result["result"]["structuredContent"]["trusted"] is False


@pytest.mark.parametrize("payload", [[], {}, {"jsonrpc": "2.0", "id": None, "method": "ping"}, {"jsonrpc": "2.0", "id": True, "method": "ping"}])
def test_invalid_requests(server, payload):
    assert server.handle(payload)["error"]["code"] == -32600


@pytest.mark.parametrize("line", [b"bad\n", b'[]\n', b'{"x":NaN}\n', b'{"x":1,"x":2}\n', b'\xff\n'])
def test_wire_parse_errors_are_jsonrpc(server, line):
    output = io.BytesIO()
    server.serve(io.BytesIO(line), output)
    response = json.loads(output.getvalue())
    assert response["jsonrpc"] == "2.0" and "error" in response


def test_oversize_closes_connection(server):
    output = io.BytesIO()
    server.serve(io.BytesIO(b"x" * (MAX_MESSAGE_BYTES + 1)), output)
    assert "exceeds" in json.loads(output.getvalue())["error"]["message"]


def test_notifications_do_not_write_stdout(server):
    output = io.BytesIO()
    source = io.BytesIO((json.dumps(message("notifications/cancelled", {"requestId": 1}, request_id=None)) + "\n").encode())
    server.serve(source, output)
    assert output.getvalue() == b""


def test_stdio_subprocess_launch_from_agent_context_never_starts_model(workspace):
    root = Path(__file__).resolve().parents[1]
    env = {**os.environ, "PYTHONPATH": str(root / "src"), "CLAUDECODE": "outer-client-session"}
    messages = [message("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "client", "version": "1"}}), message("notifications/initialized", request_id=None), message("tools/list", request_id=2), message("tools/call", {"name": "inspect_project", "arguments": {}}, request_id=3)]
    result = subprocess.run([sys.executable, "-m", "ai_orchestrator", "--project", str(workspace), "serve"], input="\n".join(json.dumps(m) for m in messages) + "\n", capture_output=True, text=True, env=env, timeout=15)
    assert result.returncode == 0, result.stderr
    responses = [json.loads(line) for line in result.stdout.splitlines()]
    assert [r["id"] for r in responses] == [1, 2, 3]
    assert responses[2]["result"]["structuredContent"]["project"] == str(workspace)


def test_recursive_worker_mcp_launch_is_rejected(workspace, monkeypatch):
    monkeypatch.setenv(WORKER_MARKER, "1")
    with pytest.raises(OrchestratorError, match="recursive"):
        serve(workspace)
