from __future__ import annotations

import json

import pytest
import yaml

from ai_orchestrator.cli import parser
from ai_orchestrator.engine import Engine
from ai_orchestrator.models import ProviderConfig
from ai_orchestrator.process import ProcessResult
from ai_orchestrator.providers import AgyAdapter, ProviderExecutionError, RunRequest
from ai_orchestrator.supervisor import Supervisor
from conftest import FakeAdapter


def test_serve_defaults_to_single_terminal_and_legacy_is_explicit_opt_out():
    assert parser().parse_args(["serve"]).single_terminal is True
    assert parser().parse_args(["serve", "--single-terminal"]).single_terminal is True
    assert parser().parse_args(["serve", "--legacy-terminal"]).single_terminal is False
    with pytest.raises(SystemExit):
        parser().parse_args(["serve", "--single-terminal", "--legacy-terminal"])


def test_agy_permission_denial_diagnostics_are_safe_and_actionable(monkeypatch, tmp_path):
    adapter = AgyAdapter()
    monkeypatch.setattr(adapter, "executable", lambda config: "agy")
    stdout = "\n".join([
        json.dumps({
            "event": "step_update",
            "step_update": {
                "step_type": "tool",
                "tool_name": "run_command",
                "step_index": 1,
                "state": "ERROR",
            },
        }),
        json.dumps({
            "event": "result",
            "result": {
                "status": "SUCCESS",
                "denied_actions": [{
                    "action": "command",
                    "command": "ps aux | grep token=TOPSECRET",
                    "permission": "shell.read",
                    "rule": "ask_before_command",
                    "reason": "user approval required for token=TOPSECRET",
                    "message": "raw provider message with TOPSECRET",
                }],
            },
        }),
    ])
    monkeypatch.setattr(
        "ai_orchestrator.providers.run_process",
        lambda *args, **kwargs: ProcessResult(0, stdout, "", 0.01),
    )
    request = RunRequest(
        "supervise",
        "private prompt content",
        tmp_path,
        ProviderConfig(adapter="agy"),
        10,
        lambda: False,
    )

    with pytest.raises(ProviderExecutionError, match=r"command\(executable=ps\)") as caught:
        adapter.execute(request)

    diagnostics = caught.value.diagnostics
    assert diagnostics["provider"] == "agy"
    assert diagnostics["dangerous_skip_permissions_requested"] is False
    assert diagnostics["denied_action_types"] == ["command"]
    denied = diagnostics["denied_actions"][0]
    assert denied["action_type"] == "command"
    assert denied["permission"] == "shell.read"
    assert denied["rule"] == "ask_before_command"
    assert denied["has_freeform_reason"] is True
    assert denied["has_details"] is True
    assert denied["command"] == {
        "executable": "ps",
        "contains_pipe": True,
        "contains_redirection": False,
        "contains_command_chain": False,
        "contains_subshell": False,
    }

    serialized = json.dumps(diagnostics, sort_keys=True)
    assert "TOPSECRET" not in serialized
    assert "ps aux" not in serialized
    assert "grep" not in serialized
    assert "private prompt content" not in serialized
    assert "--dangerously-skip-permissions" not in serialized


class DenyingSupervisorAdapter(FakeAdapter):
    def doctor(self, config, workspace):
        return {"version": "fixture", "family": self.family}

    def execute(self, request):
        raise ProviderExecutionError(
            "synthetic permission denial",
            {
                "provider": "agy",
                "denied_action_count": 1,
                "denied_action_types": ["command"],
                "denied_actions": [{
                    "action_type": "command",
                    "command": {
                        "executable": "ps",
                        "contains_pipe": True,
                        "contains_redirection": False,
                        "contains_command_chain": False,
                        "contains_subshell": False,
                    },
                }],
                "dangerous_skip_permissions_requested": False,
            },
        )


def test_failed_supervisor_exposes_safe_provider_diagnostics_through_intake(workspace):
    config = workspace / ".orchestrator/config.yaml"
    profile = yaml.safe_load(config.read_text())
    profile["providers"]["reasoning"]["adapter"] = "agy"
    config.write_text(yaml.safe_dump(profile))

    engine = Engine(
        workspace,
        {
            "agy": DenyingSupervisorAdapter("google"),
            "codex": FakeAdapter("openai"),
        },
    )
    try:
        engine.trust("operator")
        intake = Supervisor(engine).ask("Create a bounded proposal", task_id="agy-denied-intake")
        assert intake.status == "failed"
        assert intake.provider_failure_diagnostics["provider"] == "agy"
        assert intake.provider_failure_diagnostics["denied_actions"][0]["command"]["executable"] == "ps"
        assert intake.provider_failure_diagnostics["dangerous_skip_permissions_requested"] is False

        dispatch = intake.supervisor_dispatch_provenance
        assert dispatch["provider"] == "reasoning"
        assert dispatch["adapter"] == "agy"
        assert dispatch["workspace"]["mode"] == "read_only_disposable"
        assert dispatch["workspace"]["outside_project"] is True
        assert dispatch["workspace"]["control_dir_materialized"] is False
        assert dispatch["workspace"]["cleaned"] is True

        described = Supervisor(engine).describe(intake.id)
        assert described["provider_failure_diagnostics"] == intake.provider_failure_diagnostics
        assert "ps aux" not in json.dumps(described)
    finally:
        engine.close()
