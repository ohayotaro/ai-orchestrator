"""DV-04C native probe tests; use fake executables only, never Devin."""
from __future__ import annotations

from pathlib import Path
import sys

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import dv04c_native as probe


def fake_binary(tmp_path: Path, *, mode: str = "valid") -> str:
    binary = tmp_path / "fake-native-cli"
    if mode == "valid":
        output = '{"probe_id":"DV04C-READ-ONLY","ack":"OK"}'
    elif mode == "invalid":
        output = "narrative response, not JSON"
    elif mode == "tamper":
        output = '{"probe_id":"DV04C-READ-ONLY","ack":"OK"}'
    else:
        raise ValueError(mode)
    help_text = (
        '--print --prompt-file --sandbox --config --permission-mode '
        '--respect-workspace-trust\nModes: "auto" "accept-edits" "smart" "dangerous"'
    )
    script = (
        f"#!{sys.executable}\n"
        "import pathlib, sys\n"
        f"if '--version' in sys.argv: print({probe.REVIEWED!r})\n"
        f"elif '--help' in sys.argv: print({help_text!r})\n"
        "else:\n"
        + ("  pathlib.Path('marker.txt').write_text('modified')\n"
           "  pathlib.Path('../outside-workspace-sentinel.txt').write_text('modified')\n"
           if mode == "tamper" else "")
        + f"  print({output!r})\n"
    )
    binary.write_text(script, encoding="utf-8")
    binary.chmod(0o700)
    return str(binary)


def test_default_metadata_probe_never_invokes_model(tmp_path):
    fake = fake_binary(tmp_path)
    report = probe.experiment(fake, live=False)
    assert report["status"] == "READY_FOR_EXPLICIT_OPERATOR_CONSENT"
    assert report["native_calls_attempted"] == 0
    assert not report["adapter_execute_enabled"]
    assert not report["cost_ceiling_enforceable"]


def test_wrong_version_fails_closed_before_paid_call(tmp_path):
    fake = tmp_path / "fake-native-cli"
    fake.write_text(f"#!{sys.executable}\nprint('devin unknown version')\n")
    fake.chmod(0o700)
    report = probe.experiment(str(fake), live=True)
    assert report["status"] == "BLOCKED_CLI_CONTRACT"
    assert report["native_calls_attempted"] == 0


def test_fake_native_in_memory_result_is_not_schema_attestation(tmp_path):
    fake = fake_binary(tmp_path)
    report = probe.experiment(fake, live=True, timeout_seconds=15)
    assert report["status"] == "REVIEW_NATIVE_RESULT"
    assert report["native_calls_attempted"] == 1
    assert report["process"]["prompt_json_conformant"]
    assert report["process"]["native_schema_enforcement_attested"] is False
    assert report["write_isolation_attested"] is False
    assert report["workspace_marker_unchanged"]
    assert report["outside_sentinel_unchanged"]


def test_fake_native_failure_does_not_promote_output_to_success(tmp_path):
    fake = fake_binary(tmp_path, mode="invalid")
    report = probe.experiment(fake, live=True, timeout_seconds=15)
    assert report["native_calls_attempted"] == 1
    assert report["process"]["prompt_json_conformant"] is False
    assert not report["process"]["native_schema_enforcement_attested"]


def test_scratch_outside_write_and_inside_write_are_detected(tmp_path):
    fake = fake_binary(tmp_path, mode="tamper")
    report = probe.experiment(fake, live=True, timeout_seconds=15)
    assert report["status"] == "STOP_FIXTURE_MODIFIED"
    assert not report["workspace_marker_unchanged"]
    assert not report["outside_sentinel_unchanged"]
    assert "outside-workspace-sentinel.txt" in report["fixture_files_changed"]


@pytest.mark.parametrize("raw", [
    b"", (chr(96)*3 + 'json\n{}\n' + chr(96)*3).encode(),
    b'{"probe_id":"DV04C-READ-ONLY","ack":"OK","ack":"OK"}',
    b'{"probe_id":"DV04C-READ-ONLY","ack":"OK"} trailing',
    b'{"probe_id":"DV04C-READ-ONLY","ack":"OK","n":NaN}',
    b'{"probe_id":"BAD","ack":"OK"}',
])
def test_strict_prompt_protocol_rejects_unqualified_results(raw):
    assert probe.strict_prompt_json(raw) is False


def test_exact_response_parses_but_no_native_claim():
    assert probe.strict_prompt_json(b'{"probe_id":"DV04C-READ-ONLY","ack":"OK"}') is True


def test_env_does_not_forward_secrets_or_permission_bypass(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", "/owner-home-dont-inherit")
    monkeypatch.setenv("DEVIN_PERMISSION_MODE", "dangerous")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-do-not-inherit")
    env = probe.child_env(tmp_path)
    assert env["HOME"] == str(tmp_path)
    assert env["XDG_CONFIG_HOME"] == str(tmp_path / ".config")
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert "DEVIN_PERMISSION_MODE" not in env
    assert "ANTHROPIC_API_KEY" not in env


def test_modes_only_are_detected_from_declared_list():
    assert "auto" in probe.modes('Modes: "auto" "accept-edits"')
    assert "auto" not in probe.modes('mode is auto')


def test_bounded_local_process_terminates_on_deadline(tmp_path):
    fake = tmp_path / "fake-sleeper"
    fake.write_text(f"#!{sys.executable}\nimport time\ntime.sleep(5)\n")
    fake.chmod(0o700)
    result = probe.bounded_call([str(fake)], cwd=tmp_path, env=probe.child_env(tmp_path),
                                timeout_seconds=0.2)
    assert result["process_status"] == "timeout"
    assert not result["prompt_json_conformant"]
