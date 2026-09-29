"""Actual stdio frontend + separately spawned worker + CLI-shaped model shims."""

import json
import os
import selectors
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from ai_orchestrator.cli import main
from test_v02_cli_e2e import SHIM


@pytest.mark.parametrize("implementer", ["engineering", "reasoning"])
def test_mcp_to_worker_to_human_acceptance(workspace, tmp_path_factory, implementer):
    root = Path(__file__).resolve().parents[1]
    shim = tmp_path_factory.mktemp("mcp-wire") / "agent-shim"
    shim.write_text("#!" + sys.executable + " -S\n" + SHIM)
    shim.chmod(0o755)
    config_path = workspace / ".orchestrator/config.yaml"
    profile = yaml.safe_load(config_path.read_text())
    for config in profile["providers"].values():
        config["executable"] = str(shim)
    other = "reasoning" if implementer == "engineering" else "engineering"
    profile["roles"]["implementer"]["provider"] = implementer
    profile["roles"]["reviewer"]["provider"] = other
    profile["roles"]["supervisor"]["provider"] = other
    profile["validators"]["check"] = {"argv": [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], "timeout_seconds": 20, "env": {"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}}
    config_path.write_text(yaml.safe_dump(profile))
    (workspace / "calculator.py").write_text("def add(a, b):\n    return a + b\n")
    (workspace / "test_calculator.py").write_text("from calculator import add\n\ndef test_add():\n    assert add(2,3)==5\n")
    env = {**os.environ, "PYTHONPATH": str(root / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("CLAUDECODE", None)
    env.pop("AI_ORCHESTRATOR_INTERNAL_WORKER", None)
    prefix = [sys.executable, "-m", "ai_orchestrator", "--project", str(workspace)]
    def cli(*args):
        result = subprocess.run(prefix + list(args), env=env, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr or result.stdout
        return json.loads(result.stdout)
    cli("trust", "--by", "test-human", "--ack-local-execution")
    process = subprocess.Popen(prefix + ["serve"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env={**env, "CLAUDECODE": "outer-mcp-host"})
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    sequence = 0
    def rpc(method, params=None, notification=False):
        nonlocal sequence
        sequence += 1
        request = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        if not notification:
            request["id"] = sequence
        process.stdin.write(json.dumps(request) + "\n")
        process.stdin.flush()
        if notification:
            return None
        assert selector.select(15), "MCP response timed out"
        result = json.loads(process.stdout.readline())
        assert result["id"] == sequence and "error" not in result, result
        return result["result"]
    def tool(name, arguments):
        result = rpc("tools/call", {"name": name, "arguments": arguments})
        assert not result["isError"], result
        return result["structuredContent"]
    try:
        rpc("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "independent-wire-client", "version": "1"}})
        rpc("notifications/initialized", notification=True)
        job = tool("propose_task", {"request": "Multiplyを追加", "request_id": "request-1", "task_id": "mcp-task"})
        assert job["status"] == "queued"
        assert tool("get_job", {"job_id": job["id"]})["status"] == "queued"
        cli("worker", "--once")
        intake = tool("get_job", {"job_id": job["id"]})["result"]
        assert intake["status"] == "proposed"
        state = cli("start", intake["id"], "--scope", intake["intake_scope"], "--by", "test-human", "--no-run")
        tool("run_task", {"task_id": "mcp-task", "request_id": "planning"})
        cli("worker", "--once")
        state = tool("get_task", {"task_id": "mcp-task"})
        assert state["status"] == "awaiting_approval"
        cli("approve", "mcp-task", "--scope", state["approval_scope"], "--by", "test-human")
        tool("run_task", {"task_id": "mcp-task", "request_id": "implementation"})
        cli("worker", "--once")
        state = tool("get_task", {"task_id": "mcp-task"})
        assert state["status"] == "awaiting_acceptance" and state["calls"] == 4, state
        assert tool("get_artifact", {"task_id": "mcp-task", "kind": "review"})["content"]["blocking_findings"] == []
        assert cli("accept", "mcp-task", "--by", "test-human")["status"] == "succeeded"
        assert tool("get_task", {"task_id": "mcp-task"})["status"] == "succeeded"
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        selector.close()
        process.stdout.close()
        process.stderr.close()


def test_skill_export_never_overwrites_existing_file(tmp_path, capsys):
    path = tmp_path / "skills/ai-orchestrator/SKILL.md"
    assert main(["skill", "--output", str(path)]) == 0
    assert "name: ai-orchestrator" in path.read_text()
    assert "DO NOT execute those CLI commands" in path.read_text()
    before = path.read_bytes()
    assert main(["skill", "--output", str(path)]) == 1
    assert before == path.read_bytes()
