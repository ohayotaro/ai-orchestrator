"""Read-only Devin CLI/provider configuration risk inventory.

Never prints configuration bodies, permission rules, credentials, environment
variables, session history, or tool responses. Reports observed *metadata*
only; the effective native security boundary remains unverified.
No Devin -p, auth, cloud, MCP, sandbox execution, profile trust or mutations.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

MAX_CONFIG_BYTES = 1024 * 1024
EXPECTED_VERSION = "devin 3000.11.3 (9c803229faa4)"
REQUIRED_HELP_FLAGS = (
    "--print", "--prompt-file", "--config", "--sandbox",
    "--permission-mode", "--model", "--respect-workspace-trust",
)
IMPORT_SOURCES = (
    "agents_standard", "cursor", "windsurf", "claude",
    "copilot", "opencode", "vscode", "zed",
)
CONFIG_PATHS = (
    ("user", ".config/devin/config.json"),
    ("user_mcp", ".config/devin/mcp_config.json"),
    ("project", ".devin/config.json"),
    ("project_local", ".devin/config.local.json"),
    ("project_mcp", ".devin/mcp_config.json"),
    ("project_local_mcp", ".devin/mcp_config.local.json"),
)

class UnsafeConfig(ValueError):
    pass


def _jsonc_without_comments(value: str) -> str:
    """Remove JSONC comments outside strings, retaining line separators."""
    output: list[str] = []
    i = 0
    inside = False
    escaped = False
    while i < len(value):
        char = value[i]
        if inside:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                inside = False
            i += 1
            continue
        if char == '"':
            inside = True
            output.append(char)
            i += 1
            continue
        if char == "/" and i + 1 < len(value) and value[i + 1] == "/":
            i += 2
            while i < len(value) and value[i] not in "\r\n":
                i += 1
            continue
        if char == "/" and i + 1 < len(value) and value[i + 1] == "*":
            i += 2
            while i + 1 < len(value) and value[i:i+2] != "*/":
                if value[i] in "\r\n":
                    output.append(value[i])
                i += 1
            if i + 1 >= len(value):
                raise UnsafeConfig("unterminated_comment")
            i += 2
            continue
        output.append(char)
        i += 1
    if inside:
        raise UnsafeConfig("unterminated_string")
    return "".join(output)


def _remove_trailing_commas(value: str) -> str:
    output: list[str] = []
    i = 0
    inside = False
    escaped = False
    while i < len(value):
        char = value[i]
        if inside:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                inside = False
            i += 1
            continue
        if char == '"':
            inside = True
            output.append(char)
        elif char == ",":
            j = i + 1
            while j < len(value) and value[j].isspace():
                j += 1
            if j >= len(value) or value[j] not in "]}":
                output.append(char)
        else:
            output.append(char)
        i += 1
    return "".join(output)


def _parse_jsonc(value: str) -> dict:
    def unique_pairs(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise UnsafeConfig("duplicate_key")
            result[key] = item
        return result

    def reject_constant(_):
        raise UnsafeConfig("nonfinite_json")

    try:
        result = json.loads(
            _remove_trailing_commas(_jsonc_without_comments(value.lstrip("\ufeff"))),
            object_pairs_hook=unique_pairs, parse_constant=reject_constant,
        )
    except (ValueError, UnicodeError) as exc:
        raise UnsafeConfig("invalid_or_ambiguous_jsonc") from exc
    if not isinstance(result, dict):
        raise UnsafeConfig("non_object_config")
    return result


def _count_container(value) -> int:
    return len(value) if isinstance(value, (list, dict)) else int(value is not None)


def _summary(label: str, path: Path) -> dict:
    row: dict = {"source": label, "present": False}
    if path.is_symlink():
        return {**row, "present": True, "status": "symlink_not_read"}
    if not path.exists():
        return {**row, "status": "absent"}
    try:
        metadata = path.stat()
        if not stat.S_ISREG(metadata.st_mode):
            return {**row, "present": True, "status": "not_regular"}
        if metadata.st_size > MAX_CONFIG_BYTES:
            return {**row, "present": True, "status": "oversized"}
        raw = path.read_bytes()
        config = _parse_jsonc(raw.decode("utf-8"))
    except (OSError, UnicodeError, UnsafeConfig):
        return {**row, "present": True, "status": "unreadable_or_invalid"}

    # Never record raw config or strings from it, including tool names,
    # server URLs, executable paths, permission patterns, or hook commands.
    row.update({"present": True, "status": "parsed", "bytes": len(raw)})
    permissions = config.get("permissions", {})
    if isinstance(permissions, dict):
        row["permissions"] = {
            name + "_count": _count_container(permissions.get(name, []))
            for name in ("allow", "deny", "ask")
        }
    else:
        row["permissions"] = {"malformed": True}
    row["hooks_present"] = bool(config.get("hooks"))
    row["mcp_servers_count"] = _count_container(config.get("mcpServers", {}))
    imports = config.get("read_config_from", {})
    if isinstance(imports, dict):
        row["imports_not_explicitly_disabled"] = [
            source for source in IMPORT_SOURCES if imports.get(source) is not False
        ]
    else:
        row["imports_not_explicitly_disabled"] = list(IMPORT_SOURCES)
        row["imports_invalid"] = True

    if label == "user":
        row["subagents_disabled_explicitly"] = config.get("subagents_enabled") is False
        row["auto_update_disabled_explicitly"] = config.get("auto_update") is False
        sandbox = config.get("sandbox", {})
        if isinstance(sandbox, dict):
            row["sandbox_exclusions_present"] = bool(
                isinstance(sandbox.get("excluded"), dict) and any(
                    sandbox["excluded"].get(key) for key in ("allow", "ask")
                )
            )
            row["network_filter_unverified"] = True
        else:
            row["sandbox_exclusions_present"] = None
            row["network_filter_unverified"] = True
    return row


def _metadata_env() -> dict[str, str]:
    """Only pass minimal OS path/locale variables to read-only help probes.

    This does not change the operator's environment or prove native
    configuration isolation; it only avoids forwarding DEVIN_* overrides or
    credential-shaped environment variables to metadata subprocesses.
    """
    allowed = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT")
    return {
        **{key: os.environ[key] for key in allowed if key in os.environ},
        "GIT_TERMINAL_PROMPT": "0",
        "PYTHONNOUSERSITE": "1",
    }


def _permission_modes_from_help(help_text: str) -> frozenset[str]:
    """Parse explicitly quoted options on a 'Modes:' CLI help line."""
    for line in help_text.splitlines():
        if re.match(r"^\s*Modes:\s*", line):
            return frozenset(re.findall(r'"([a-z][a-z-]*)"', line))
    return frozenset()


def _cli_summary(binary: str | None) -> dict:
    if not binary:
        return {"status": "missing", "matches_reviewed_version": False}
    try:
        for command in ("--version", "--help"):
            result = subprocess.run(
                [binary, command], capture_output=True, timeout=8, check=False,
                env=_metadata_env()
            )
            if result.returncode != 0 or len(result.stdout) + len(result.stderr) > 256 * 1024:
                return {"status": "probe_failed", "matches_reviewed_version": False}
            if command == "--version":
                version = result.stdout.decode("utf-8", errors="replace").strip()
            else:
                help_text = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "probe_failed", "matches_reviewed_version": False}
    modes = _permission_modes_from_help(help_text)
    return {
        "status": "inspected",
        "matches_reviewed_version": version == EXPECTED_VERSION,
        "required_flags_present": all(flag in help_text for flag in REQUIRED_HELP_FLAGS),
        "auto_mode_listed_in_help": "auto" in modes,
        # Historical diagnostic retained, but absence is no longer a blocker
        # because the fixture does not request this unsupported mode.
        "autonomous_listed_in_help": "autonomous" in modes,
        "advertised_safe_mode_names": sorted(modes & {"auto", "accept-edits"}),
        "unexpected_permission_mode_advertised": bool(
            modes - {"auto", "accept-edits", "smart", "dangerous"}
        ),
    }


def inspect(project: Path, *, home: Path, binary: str | None) -> dict:
    if not project.is_dir():
        raise ValueError("project must be an existing directory")
    base = project.resolve()
    workspace_git = (base / ".git").exists() and not (base / ".git").is_symlink()
    rows = [_summary(label, (home if label.startswith("user") else base) / relative)
            for label, relative in CONFIG_PATHS]
    present = {row["source"]: row for row in rows}
    extra = {
        "devin_hook_files_present": (base / ".devin/hooks.v1.json").exists(),
        "project_rule_files_present": any(
            (base / p).exists() for p in ("AGENTS.md", "AGENTS.local.md", ".agents", ".claude", ".cursor", ".windsurf")
        ),
        "orchestrator_state_present": (base / ".orchestrator").exists(),
    }
    reasons: list[str] = []
    if not workspace_git:
        reasons.append("workspace_git_not_confirmed")
    if extra["orchestrator_state_present"]:
        reasons.append("nonfresh_orchestrator_fixture")
    if extra["devin_hook_files_present"]:
        reasons.append("project_hooks_present")
    if extra["project_rule_files_present"]:
        reasons.append("external_project_context_present")
    if any(row["status"] not in ("absent", "parsed") for row in rows):
        reasons.append("configuration_unreadable_or_ambiguous")
    if any(row.get("hooks_present") for row in rows):
        reasons.append("configured_hooks_present")
    if any(row.get("mcp_servers_count", 0) for row in rows):
        reasons.append("mcp_servers_present")
    if any(row.get("permissions", {}).get("allow_count", 0) for row in rows):
        reasons.append("persistent_permission_grants_present")
    if any(row.get("imports_not_explicitly_disabled") for row in rows):
        reasons.append("configuration_imports_not_disabled")
    if present["user"].get("subagents_disabled_explicitly") is not True:
        reasons.append("subagents_not_explicitly_disabled")
    if present["user"].get("sandbox_exclusions_present") is not False:
        reasons.append("sandbox_exclusions_not_attested_absent")
    known_env_overrides = (
        "DEVIN_PERMISSION_MODE", "DEVIN_SANDBOX", "DEVIN_MODEL",
        "DEVIN_CONFIG", "CLAUDECODE",
    )
    present_env_overrides = [
        key for key in known_env_overrides if key in os.environ
    ]
    if present_env_overrides:
        reasons.append("agent_environment_overrides_present")
    cli = _cli_summary(binary)
    if not cli.get("matches_reviewed_version") or not cli.get("required_flags_present"):
        reasons.append("cli_contract_unmatched_or_unreadable")
    if not cli.get("auto_mode_listed_in_help"):
        reasons.append("reviewed_auto_mode_not_confirmed_by_exact_help")
    if cli.get("unexpected_permission_mode_advertised"):
        reasons.append("unreviewed_permission_mode_advertised")
    # These cannot be established by local static inspection.
    reasons.extend([
        "effective_native_config_isolation_unverified",
        "effective_team_and_session_policy_unverified",
        "direct_edit_write_scope_unverified",
        "network_filter_not_qualified",
        "headless_trust_and_terminal_result_unverified",
    ])
    return {
        "schema_version": 1,
        "kind": "devin_provider_read_only_preflight",
        "assurance": "metadata_only_not_effective_permission_attestation",
        "status": "REVIEW_REQUIRED",
        "os": platform.system(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "workspace_git_present": workspace_git,
        "cli": cli,
        "environment_override_names_present": present_env_overrides,
        "configuration": rows,
        "extra_sources": extra,
        "reasons": sorted(set(reasons)),
        "provider_calls": 0,
        "task_or_gate_mutations": 0,
        "execution_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--no-cli-probe", action="store_true")
    args = parser.parse_args()
    binary = None if args.no_cli_probe else shutil.which("devin")
    try:
        result = inspect(args.project, home=Path.home(), binary=binary)
    except (OSError, ValueError) as exc:
        result = {"schema_version": 1, "kind": "devin_provider_read_only_preflight",
                  "status": "BLOCKED", "error_type": type(exc).__name__,
                  "execution_authorized": False}
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2))
    return 0 if result["status"] == "REVIEW_REQUIRED" else 1


if __name__ == "__main__":
    sys.exit(main())
