import json
import os
import sys
import time
from pathlib import Path

import pytest

from ai_orchestrator.models import AgentResult, OrchestratorError, ProviderConfig
from ai_orchestrator.process import ProcessResult, redact, run_process, validator_environment
from ai_orchestrator.providers import AgyAdapter, ClaudeAdapter, CodexAdapter, RunRequest, default_registry


def request(tmp_path, phase="review", command=None):
    return RunRequest(phase, "PRIVATE_PROMPT_NOT_IN_ARGV", tmp_path, ProviderConfig(adapter="fixture", executable=command), 5, lambda: False)




def test_default_registry_includes_antigravity_adapter():
    registry = default_registry()
    assert isinstance(registry["agy"], AgyAdapter)
    assert registry["agy"].family == "google"
    assert "code_edit" in registry["agy"].semantic_capabilities
    assert "native_sandbox" in registry["agy"].capabilities


def test_agy_argv_uses_stdin_stream_json_and_sandbox(tmp_path):
    adapter = AgyAdapter()
    args = adapter.command_line(request(tmp_path, "execute"), tmp_path / "schema.json")
    assert args[args.index("--input-format") + 1] == "stream-json"
    assert args[args.index("--output-format") + 1] == "stream-json"
    assert "--sandbox" in args
    assert "--mode=accept-edits" in args
    assert "--dangerously-skip-permissions" not in args
    assert "PRIVATE_PROMPT_NOT_IN_ARGV" not in " ".join(args)


def test_agy_non_execute_uses_plan_mode(tmp_path):
    args = AgyAdapter().command_line(request(tmp_path, "review"), tmp_path / "schema.json")
    assert "--mode=plan" in args
    assert "--mode=accept-edits" not in args


def test_agy_adapter_parses_terminal_structured_output(tmp_path, monkeypatch):
    expected = AgentResult(outcome="approved", summary="agy verified", findings=[], evidence=[])
    seen = {}
    envelope = {
        "event": "result",
        "result": {
            "status": "SUCCESS",
            "response": expected.model_dump_json(),
            "structured_output": expected.model_dump(),
        },
    }
    def fake_process(argv, **kwargs):
        seen.update(kwargs)
        return ProcessResult(0, json.dumps({"event": "init", "init": {}}) + "\n" + json.dumps(envelope) + "\n", "", 0.1)
    monkeypatch.setattr("ai_orchestrator.providers.run_process", fake_process)
    adapter = AgyAdapter()
    monkeypatch.setattr(adapter, "executable", lambda config: sys.executable)
    assert adapter.execute(request(tmp_path)) == expected
    sent = json.loads(seen["input_text"])
    assert sent == {"event": "user", "message": {"content": "PRIVATE_PROMPT_NOT_IN_ARGV"}}


@pytest.mark.parametrize(
    "returncode,status,structured",
    [
        (0, "ERROR", None),
        (0, "SUCCESS", None),
        (1, "ERROR", {"outcome": "approved", "summary": "bad", "findings": [], "evidence": []}),
    ],
)
def test_agy_fails_closed_on_terminal_errors(tmp_path, monkeypatch, returncode, status, structured):
    payload = {"status": status, "response": ""}
    if structured is not None:
        payload["structured_output"] = structured
    stdout = json.dumps({"event": "result", "result": payload}) + "\n"
    monkeypatch.setattr(
        "ai_orchestrator.providers.run_process",
        lambda *a, **kw: ProcessResult(returncode, stdout, "", 0.1),
    )
    adapter = AgyAdapter()
    monkeypatch.setattr(adapter, "executable", lambda config: sys.executable)
    with pytest.raises(OrchestratorError):
        adapter.execute(request(tmp_path))


def test_agy_rejects_missing_or_malformed_result_event():
    with pytest.raises(OrchestratorError, match="no terminal result"):
        AgyAdapter._result_envelope(json.dumps({"event": "init", "init": {}}))
    with pytest.raises(OrchestratorError, match="malformed"):
        AgyAdapter._result_envelope("{not-json}")

def test_codex_argv_is_explicit_readonly_and_fresh(tmp_path):
    adapter = CodexAdapter()
    args = adapter.command_line(request(tmp_path), tmp_path / "schema", tmp_path / "result")
    assert args[args.index("--sandbox") + 1] == "read-only"
    assert "--ephemeral" in args and args[-1] == "-"
    assert 'approval_policy="never"' in args
    assert "sandbox_workspace_write.network_access=false" in args
    assert "PRIVATE_PROMPT_NOT_IN_ARGV" not in " ".join(args)
    assert "--yolo" not in args and "--full-auto" not in args
    assert "resume" not in args


def test_codex_only_execution_gets_write_sandbox(tmp_path):
    args = CodexAdapter().command_line(request(tmp_path, "execute"), Path("schema"), Path("out"))
    assert args[args.index("--sandbox") + 1] == "workspace-write"


def test_claude_tool_policy_not_misrepresented_as_os_sandbox(tmp_path):
    adapter = ClaudeAdapter()
    args = adapter.command_line(request(tmp_path), Path("mcp"))
    assert args[args.index("--tools") + 1] == "Read,Glob,Grep"
    assert args[args.index("--permission-mode") + 1] == "dontAsk"
    assert "--no-session-persistence" in args
    assert "--strict-mcp-config" in args
    assert "--dangerously-skip-permissions" not in args
    assert "native_sandbox" not in adapter.capabilities
    assert "shell" not in adapter.capabilities


def test_codex_adapter_parses_real_shaped_output(tmp_path, monkeypatch):
    expected = AgentResult(outcome="approved", summary="verified", findings=[], evidence=[])
    seen = {}
    def fake_process(argv, **kwargs):
        seen.update(kwargs)
        Path(argv[argv.index("--output-last-message") + 1]).write_text(expected.model_dump_json())
        return ProcessResult(0, "", "", 0.1)
    monkeypatch.setattr("ai_orchestrator.providers.run_process", fake_process)
    adapter = CodexAdapter()
    monkeypatch.setattr(adapter, "executable", lambda config: sys.executable)
    assert adapter.execute(request(tmp_path)) == expected
    assert seen["input_text"] == "PRIVATE_PROMPT_NOT_IN_ARGV"


@pytest.mark.parametrize("envelope", [{"is_error": True}, {"result": "APPROVED"}, {"structured_output": {}, "permission_denials": ["Bash"]}])
def test_claude_fails_closed_on_bad_envelopes(tmp_path, monkeypatch, envelope):
    monkeypatch.delenv("CLAUDECODE", raising=False)
    monkeypatch.setattr("ai_orchestrator.providers.run_process", lambda *a, **kw: ProcessResult(0, json.dumps(envelope), "", 0.1))
    adapter = ClaudeAdapter()
    monkeypatch.setattr(adapter, "executable", lambda config: sys.executable)
    with pytest.raises(OrchestratorError):
        adapter.execute(request(tmp_path))


def test_claude_structured_result_success(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDECODE", raising=False)
    expected = AgentResult(outcome="approved", summary="ok", findings=[], evidence=[])
    envelope = {"is_error": False, "structured_output": expected.model_dump()}
    monkeypatch.setattr("ai_orchestrator.providers.run_process", lambda *a, **kw: ProcessResult(0, json.dumps(envelope), "", 0.1))
    adapter = ClaudeAdapter()
    monkeypatch.setattr(adapter, "executable", lambda config: sys.executable)
    assert adapter.execute(request(tmp_path)) == expected


def test_process_stdin_and_exitcode(tmp_path):
    result = run_process([sys.executable, "-c", "import sys; print(sys.stdin.read()); sys.exit(7)"], cwd=tmp_path, input_text="hello", timeout=5)
    assert result.returncode == 7
    assert result.stdout.strip() == "hello"


def test_process_timeout(tmp_path):
    with pytest.raises(OrchestratorError, match="timed out"):
        run_process([sys.executable, "-c", "import time; time.sleep(5)"], cwd=tmp_path, timeout=0.1)


def test_process_cancel(tmp_path):
    with pytest.raises(OrchestratorError, match="cancelled"):
        run_process([sys.executable, "-c", "import time; time.sleep(5)"], cwd=tmp_path, cancel=lambda: True)


def test_output_limit(tmp_path):
    with pytest.raises(OrchestratorError, match="output exceeded"):
        run_process([sys.executable, "-c", "print('x' * 100000)"], cwd=tmp_path, output_limit=512)


def test_descendant_cleanup(tmp_path):
    marker = tmp_path / "orphan"
    child = f"import time,pathlib; time.sleep(.5); pathlib.Path({str(marker)!r}).write_text('bad')"
    parent = "import subprocess,sys; subprocess.Popen([sys.executable, '-c', " + repr(child) + "])"
    run_process([sys.executable, "-c", parent], cwd=tmp_path, timeout=5)
    time.sleep(0.6)
    assert not marker.exists()


def test_validator_environment_does_not_inherit_credentials(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    monkeypatch.setenv("GITHUB_TOKEN", "secret")
    monkeypatch.setenv("PYTHONPATH", "/untrusted")
    env = validator_environment("/temporary-home")
    assert "OPENAI_API_KEY" not in env and "ANTHROPIC_API_KEY" not in env
    assert "GITHUB_TOKEN" not in env and "PYTHONPATH" not in env
    assert env["HOME"] == "/temporary-home"


def test_common_secret_redaction():
    assert "my-secret" not in redact("token=my-secret")
    assert "sk-" not in redact("sk-12345678901234567890")


def test_already_cancelled_command_never_spawns(tmp_path):
    target = tmp_path / "should-not-exist"
    script = f"from pathlib import Path; Path({str(target)!r}).write_text('bad')"
    with pytest.raises(OrchestratorError, match="cancelled"):
        run_process([sys.executable, "-c", script], cwd=tmp_path, cancel=lambda: True)
    assert not target.exists()


def test_prompt_not_interpreted_as_shell(tmp_path):
    text = "$(touch PWNED); && | ; `echo injected`"
    result = run_process([sys.executable, "-c", "import sys; print(sys.stdin.read())"], cwd=tmp_path, input_text=text)
    assert result.stdout.strip() == text
    assert not (tmp_path / "PWNED").exists()
