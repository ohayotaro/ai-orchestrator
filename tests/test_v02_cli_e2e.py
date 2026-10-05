"""Offline wire E2E: real subprocesses/CLI parsing/pytest, NOT real model calls."""

import json
import sys
from pathlib import Path

import pytest
import yaml

from ai_orchestrator.cli import main

SHIM = r'''
import json
import pathlib
import sys

args = sys.argv[1:]
if "--version" in args:
    print("offline-wire-fixture 1.0")
    raise SystemExit(0)
if "--help" in args:
    print("--output-schema --output-last-message --sandbox --ephemeral --json-schema --no-session-persistence --permission-mode --tools --strict-mcp-config --setting-sources --disable-slash-commands")
    raise SystemExit(0)
request = json.loads(sys.stdin.read())
if "--json-schema" in args:
    schema = json.loads(args[args.index("--json-schema") + 1])
    assert args[args.index("--permission-mode") + 1] == "dontAsk"
    assert "--no-session-persistence" in args
    tools = args[args.index("--tools") + 1]
    assert tools == ("Read,Glob,Grep,Edit,Write" if schema["title"] == "ImplementationResult" else "Read,Glob,Grep")
else:
    schema = json.loads(pathlib.Path(args[args.index("--output-schema") + 1]).read_text())
    assert "--ephemeral" in args
    assert args[args.index("--sandbox") + 1] == ("workspace-write" if schema["title"] == "ImplementationResult" else "read-only")
assert schema["additionalProperties"] is False
assert set(schema["required"]) == set(schema["properties"])
role = schema["title"]
if role == "SupervisorResult":
    assert request["role"] == "supervisor"
    result = {"outcome": "proposed", "summary": "Add a multiply function", "task": {"goal": "Add multiply(a,b) and its tests", "acceptance": ["multiply(2,3) returns 6", "Existing add test passes"], "risk": "T2", "validators": ["check"], "external_effects": False, "allowed_paths": ["calculator.py", "test_calculator.py"], "capabilities": {}, "workflow_ref": None}, "questions": []}
elif role == "PlanResult":
    result = {"outcome": "completed", "summary": "Implement then validate", "steps": ["Add multiply", "Add tests"], "uncertainties": [], "evidence": ["calculator.py"]}
elif role == "ImplementationResult":
    pathlib.Path("calculator.py").write_text("def add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n")
    pathlib.Path("test_calculator.py").write_text("from calculator import add, multiply\n\ndef test_add():\n    assert add(2, 3) == 5\n\ndef test_multiply():\n    assert multiply(2, 3) == 6\n")
    result = {"outcome": "completed", "summary": "Added multiplication", "changes": ["calculator.py", "test_calculator.py"], "uncertainties": [], "evidence": ["calculator.py"]}
elif role == "ReviewResult":
    assert "plan" not in request
    assert request["validation"]["checks"][0]["exit_code"] == 0
    assert "2 passed" in request["validation"]["checks"][0]["stdout_tail"]
    result = {"outcome": "approved", "summary": "Acceptance criteria met", "blocking_findings": [], "observations": ["Non-blocking test coverage note"], "evidence": ["calculator.py", "test_calculator.py"]}
else:
    raise RuntimeError(role)
if "--json-schema" in args:
    print(json.dumps({"is_error": False, "structured_output": result}))
else:
    pathlib.Path(args[args.index("--output-last-message") + 1]).write_text(json.dumps(result))
'''


@pytest.mark.parametrize("implementer", ["engineering", "reasoning"])
def test_ask_to_succeeded_through_real_cli_processes(workspace, tmp_path_factory, capsys, monkeypatch, implementer):
    monkeypatch.delenv("CLAUDECODE", raising=False)
    directory = tmp_path_factory.mktemp("wire-cli")
    shim = directory / "agent-shim"
    shim.write_text("#!" + sys.executable + " -S\n" + SHIM)
    shim.chmod(0o755)
    path = workspace / ".orchestrator/config.yaml"
    data = yaml.safe_load(path.read_text())
    for provider in data["providers"].values():
        provider["executable"] = str(shim)
    data["roles"]["implementer"]["provider"] = implementer
    data["roles"]["reviewer"]["provider"] = "reasoning" if implementer == "engineering" else "engineering"
    data["roles"]["supervisor"]["provider"] = "reasoning" if implementer == "engineering" else "engineering"
    data["validators"]["check"] = {"argv": [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], "timeout_seconds": 20, "env": {"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}}
    path.write_text(yaml.safe_dump(data))
    (workspace / "calculator.py").write_text("def add(a,b):\n    return a+b\n")
    (workspace / "test_calculator.py").write_text("from calculator import add\n\ndef test_add():\n    assert add(2,3)==5\n")
    prefix = ["--project", str(workspace)]
    def invoke(*args):
        code = main(prefix + list(args))
        captured = capsys.readouterr()
        assert code == 0, captured.err or captured.out
        return json.loads(captured.out)
    invoke("trust", "--by", "wire-test", "--ack-local-execution")
    assert all(row["ok"] for row in invoke("doctor").values())
    proposal = invoke("ask", "multiplyを追加してテストしてください", "--task-id", "wire-task")
    assert proposal["status"] == "proposed"
    state = invoke("start", proposal["id"], "--scope", proposal["intake_scope"], "--by", "wire-test")
    assert state["status"] == "awaiting_approval"
    invoke("approve", "wire-task", "--scope", state["approval_scope"], "--by", "wire-test")
    state = invoke("run", "wire-task")
    assert state["status"] == "awaiting_acceptance", state
    assert state["calls"] == 4
    assert state["attempt"] == 1
    state = invoke("accept", "wire-task", "--by", "wire-test")
    assert state["status"] == "succeeded"
    assert {a["kind"] for a in state["artifacts"]} == {"supervisor", "plan", "write_set", "execute", "validation", "review", "acceptance", "provider_provenance", "usage", "budget", "context_influence"}
    assert not list(workspace.rglob("*.pyc"))
    assert not (workspace / ".pytest_cache").exists()
