"""DV-04B reproducible synthetic HOME, permissions and write-scope negatives."""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

TOOLS = pathlib.Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import dv04b_fixture


def test_synthetic_boundary_detects_escape_and_never_authorizes(monkeypatch):
    monkeypatch.setenv("DEVIN_PERMISSION_MODE", "dangerous")
    monkeypatch.setenv("DV04B_TEST_SECRET", "not-a-real-token")
    monkeypatch.setenv("TWINE_PASSWORD", "not-a-real-token")
    result = dv04b_fixture.run()
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["result"] == "PASS_SYNTHETIC_DETECTION_ONLY"
    assert not result["execution_authorized"]
    assert result["provider_calls"] == 0
    assert result["task_or_gate_mutations"] == 0
    assert all(result["checks"].values())
    assert len(result["still_unverified"]) >= 7
    assert "not-a-real-token" not in json.dumps(result)


def test_fake_environment_does_not_inherit_global_user_or_agent_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", "/different-global-home")
    monkeypatch.setenv("DEVIN_SANDBOX", "false")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "fake-secret")
    env = dv04b_fixture.fixture_child_env(tmp_path)
    assert env["HOME"] == str(tmp_path)
    assert env["XDG_CONFIG_HOME"].startswith(str(tmp_path))
    assert env["TMPDIR"].startswith(str(tmp_path))
    assert all(name not in env for name in (
        "DEVIN_SANDBOX", "DEVIN_PERMISSION_MODE", "ANTHROPIC_API_KEY", "TWINE_PASSWORD"))
    assert "PATH" in env


def test_unknown_native_guarantees_are_never_promoted():
    result = dv04b_fixture.run()
    assert "native_network_egress" in result["still_unverified"]
    assert "native_schema_bound_terminal_result" in result["still_unverified"]
    assert "native_direct_edit_write_scope" in result["still_unverified"]
    assert "no Devin process" in result["sandbox_claim"]


def test_probe_does_not_leave_artifacts_outside_temporary_scope(tmp_path, monkeypatch):
    # Internal scratch is not the owner's workspace and is removed by context.
    original = dv04b_fixture.tempfile.TemporaryDirectory
    names = []

    def track(*args, **kwargs):
        ctx = original(*args, **kwargs)
        names.append(ctx.name)
        return ctx

    monkeypatch.setattr(dv04b_fixture.tempfile, "TemporaryDirectory", track)
    result = dv04b_fixture.run()
    assert result["status"] == "REVIEW_REQUIRED"
    assert len(names) == 1
    assert not pathlib.Path(names[0]).exists()
