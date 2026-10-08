"""Non-billable negative tests for the redacted read-only Devin preflight."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS))
import inspect_devin as preflight


def test_jsonc_preserves_comment_like_literals_and_trailing_commas():
    value = preflight._parse_jsonc(
        '{//comment\n"endpoint":"https://private.example/x//y",'
        '"description":"/* keep */", /* omitted */'
        '"permissions":{"allow":["Read(**)",],},}'
    )
    assert value["endpoint"] == "https://private.example/x//y"
    assert value["description"] == "/* keep */"
    assert value["permissions"]["allow"] == ["Read(**)"]


@pytest.mark.parametrize("body", [
    '{"x":1,"x":2}',
    '{"x":NaN}',
    '{"x":Infinity}',
    '{"x":1, /* unterminated',
    '{"x":"not closed}',
    '["not a config object"]',
])
def test_ambiguous_jsonc_refuses_without_salvage(body):
    with pytest.raises(preflight.UnsafeConfig):
        preflight._parse_jsonc(body)


def test_inspection_never_exports_secret_values_or_raw_rules(tmp_path):
    home = tmp_path / "home"
    project = tmp_path / "proj"
    home.mkdir()
    project.mkdir()
    (project / ".git").mkdir()
    config = home / ".config/devin/config.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({
        "permissions": {"allow": ["Exec(transfer--PRIVATE-PASSCODE--to-remote)"], "deny": [], "ask": []},
        "secrets": {"pypi_token": "SECRET-DO-NOT-PRINT-123"},
        "read_config_from": {"claude": True},
        "subagents_enabled": True,
        "hooks": [{"command": "SECRET-DO-NOT-PRINT-456"}],
        "sandbox": {"excluded": {"allow": ["Exec(git push PRIVATE-SECRET)"]}},
    }))
    before = config.read_bytes()
    result = preflight.inspect(project, home=home, binary=None)
    output = json.dumps(result, sort_keys=True)
    assert result["status"] == "REVIEW_REQUIRED"
    assert "persistent_permission_grants_present" in result["reasons"]
    assert "configured_hooks_present" in result["reasons"]
    assert "configuration_imports_not_disabled" in result["reasons"]
    assert "subagents_not_explicitly_disabled" in result["reasons"]
    assert "sandbox_exclusions_not_attested_absent" in result["reasons"] or result["configuration"][0]["sandbox_exclusions_present"]
    assert "SECRET-DO-NOT-PRINT" not in output
    assert "PRIVATE-PASSCODE" not in output
    assert "PRIVATE-SECRET" not in output
    assert "https://" not in output
    assert config.read_bytes() == before


def test_symlink_never_opened_and_directory_not_modified(tmp_path):
    home = tmp_path / "home"
    project = tmp_path / "proj"
    home.mkdir()
    project.mkdir()
    (project / ".git").mkdir()
    external = tmp_path / "secret"
    external.write_text('{"private_key":"NO-MATERIALIZE"}')
    path = project / ".devin/config.json"
    path.parent.mkdir(parents=True)
    path.symlink_to(external)
    before = external.read_bytes()
    result = preflight.inspect(project, home=home, binary=None)
    row = next(x for x in result["configuration"] if x["source"] == "project")
    assert row["status"] == "symlink_not_read"
    assert "configuration_unreadable_or_ambiguous" in result["reasons"]
    assert "NO-MATERIALIZE" not in json.dumps(result)
    assert external.read_bytes() == before


def test_missing_project_refuses_without_creation(tmp_path):
    project = tmp_path / "missing"
    with pytest.raises(ValueError, match="existing directory"):
        preflight.inspect(project, home=tmp_path, binary=None)
    assert not project.exists()


def test_default_imports_are_conservatively_unqualified(tmp_path):
    home = tmp_path / "home"
    project = tmp_path / "proj"
    home.mkdir()
    project.mkdir()
    (project / ".git").mkdir()
    user_config = home / ".config/devin/config.json"
    user_config.parent.mkdir(parents=True)
    user_config.write_text('{"permissions":{"allow":[],"deny":[],"ask":[]}}')
    result = preflight.inspect(project, home=home, binary=None)
    row = next(x for x in result["configuration"] if x["source"] == "user")
    assert "agents_standard" in row["imports_not_explicitly_disabled"]
    assert "configuration_imports_not_disabled" in result["reasons"]
    assert "network_filter_not_qualified" in result["reasons"]


def test_help_version_disagreement_is_review_required(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / ".git").mkdir()
    fake = tmp_path / "devin-fake"
    fake.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "--version" ]; then echo "devin 3000.11.3 (9c803229faa4)"; exit 0; fi\n'
        'echo "--print --prompt-file --config --sandbox --permission-mode --model --respect-workspace-trust";\n'
    )
    fake.chmod(0o755)
    result = preflight.inspect(project, home=tmp_path, binary=str(fake))
    assert result["cli"]["matches_reviewed_version"]
    assert result["cli"]["required_flags_present"]
    assert not result["cli"]["autonomous_listed_in_help"]
    assert "autonomous_mode_not_confirmed_by_exact_help" in result["reasons"]


def test_cli_probe_has_no_prompt_or_user_data(tmp_path):
    fake = tmp_path / "devin-fake"
    fake.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "--version" ]; then echo "devin 3000.11.3 (9c803229faa4)"; exit 0; fi\n'
        'echo "--print --prompt-file --config --sandbox --permission-mode --model --respect-workspace-trust autonomous";\n'
    )
    fake.chmod(0o755)
    result = preflight._cli_summary(str(fake))
    assert result["matches_reviewed_version"]
    assert result["autonomous_listed_in_help"]


def test_oversized_config_is_not_read(tmp_path):
    big = tmp_path / "config.json"
    big.write_bytes(b"x" * (preflight.MAX_CONFIG_BYTES + 1))
    report = preflight._summary("project", big)
    assert report["status"] == "oversized"
    assert "x" * 30 not in json.dumps(report)
