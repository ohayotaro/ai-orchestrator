"""Provider adapters. Safety differences remain visible in capabilities."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from .models import AgentResult, Contract, OrchestratorError, ProviderConfig
from .process import run_process
from .project import encode, read_text


@dataclass(frozen=True)
class RunRequest:
    phase: str
    prompt: str
    workspace: Path
    config: ProviderConfig
    timeout: float
    cancel: Callable[[], bool]
    result_model: type[Contract] = AgentResult


class ProviderExecutionError(OrchestratorError):
    """Provider failure with safe, non-content diagnostics for audit events."""

    def __init__(self, message: str, diagnostics: dict[str, object] | None = None):
        super().__init__(message)
        self.diagnostics = diagnostics or {}


class ProviderAdapter(Protocol):
    # Adapter v1 exposed only runtime capabilities. v2 adds semantic capabilities.
    api_version: int
    family: str
    capabilities: frozenset[str]
    semantic_capabilities: frozenset[str]

    def doctor(self, config: ProviderConfig, workspace: Path) -> dict[str, str]: ...
    def execute(self, request: RunRequest) -> Contract: ...


class CLIAdapter:
    api_version = 2
    command = ""
    family = ""
    help_flags: tuple[str, ...] = ()
    capabilities = frozenset({"read_files", "write_files", "fresh_session", "structured_output"})
    semantic_capabilities = frozenset({"repository_analysis", "planning", "code_edit", "test_authoring", "review", "supervision"})

    def executable(self, config: ProviderConfig) -> str:
        name = config.executable or self.command
        path = shutil.which(name)
        if not path:
            raise OrchestratorError(f"{self.command} executable not found; install/authenticate it separately")
        return str(Path(path).resolve())

    def doctor(self, config: ProviderConfig, workspace: Path) -> dict[str, str]:
        executable = self.executable(config)
        version = run_process([executable, "--version"], cwd=workspace, timeout=15)
        help_args = [executable, "exec", "--help"] if self.command == "codex" else [executable, "--help"]
        help_result = run_process(help_args, cwd=workspace, timeout=15)
        if version.returncode or help_result.returncode:
            raise OrchestratorError(f"{self.command} version/help probe failed")
        # CLIs are inconsistent about which stream receives help text.
        # Antigravity 1.2.x writes --help to stderr even on success; probe the
        # complete diagnostic output rather than assuming stdout.
        help_text = help_result.stdout + "\n" + help_result.stderr
        missing = [flag for flag in self.help_flags if flag not in help_text]
        if missing:
            raise OrchestratorError(f"{self.command} CLI lacks required flags: {', '.join(missing)}")
        return {"executable": executable, "version": version.stdout.strip(), "family": self.family, "authentication": "not checked"}


class CodexAdapter(CLIAdapter):
    command = "codex"
    family = "openai"
    capabilities = CLIAdapter.capabilities | {"shell", "native_sandbox"}
    help_flags = ("--output-schema", "--output-last-message", "--sandbox", "--ephemeral")

    def command_line(self, request: RunRequest, schema: Path, output: Path) -> list[str]:
        args = [request.config.executable or self.command, "exec", "--ephemeral", "--sandbox", "workspace-write" if request.phase == "execute" else "read-only", "-c", 'approval_policy="never"', "-c", 'web_search="disabled"', "-c", "sandbox_workspace_write.network_access=false", "--output-schema", str(schema), "--output-last-message", str(output), "--color", "never"]
        if request.config.model:
            args += ["--model", request.config.model]
        if request.config.effort:
            args += ["-c", "model_reasoning_effort=" + json.dumps(request.config.effort)]
        return args + ["-"]

    def execute(self, request: RunRequest) -> Contract:
        with tempfile.TemporaryDirectory(prefix="orchestrator-codex-") as directory:
            schema, output = Path(directory) / "schema.json", Path(directory) / "result.json"
            schema.write_text(encode(request.result_model.model_json_schema()), encoding="utf-8")
            argv = self.command_line(request, schema, output)
            argv[0] = self.executable(request.config)
            result = run_process(argv, cwd=request.workspace, input_text=request.prompt, timeout=request.timeout, cancel=request.cancel)
            if result.returncode != 0 or not output.is_file():
                raise OrchestratorError(f"Codex failed (exit {result.returncode}); inspect CLI authentication/configuration, then create a new task")
            return request.result_model.model_validate_json(read_text(output))


class AgyAdapter(CLIAdapter):
    """Google Antigravity CLI headless adapter.

    Prompts use stream-json stdin so task content never appears in argv. The
    terminal result must be SUCCESS and contain schema-validated structured
    output; AGY is known to sometimes exit zero with an ERROR envelope, so the
    envelope status is authoritative.
    """

    command = "agy"
    family = "google"
    capabilities = CLIAdapter.capabilities | {"native_sandbox"}
    help_flags = ("--input-format", "--output-format", "--json-schema", "--sandbox", "--print-timeout", "--mode")

    def command_line(self, request: RunRequest, schema: Path) -> list[str]:
        timeout_seconds = max(1, int(request.timeout))
        args = [
            request.config.executable or self.command,
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--json-schema", str(schema),
            "--sandbox",
            "--mode=accept-edits" if request.phase == "execute" else "--mode=plan",
            "--print-timeout", f"{timeout_seconds}s",
        ]
        if request.config.model:
            args += ["--model", request.config.model]
        if request.config.effort:
            args += ["--effort", request.config.effort]
        return args

    @staticmethod
    def _result_envelope(stdout: str) -> dict:
        terminal: dict | None = None
        for line in stdout.splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise OrchestratorError("Antigravity returned malformed stream-json output") from exc
            if not isinstance(event, dict):
                raise OrchestratorError("Antigravity returned malformed stream-json event")
            if event.get("event") == "result":
                payload = event.get("result")
                if not isinstance(payload, dict):
                    raise OrchestratorError("Antigravity returned malformed terminal result")
                terminal = payload
        if terminal is None:
            raise OrchestratorError("Antigravity returned no terminal result event")
        return terminal

    @staticmethod
    def _safe_diagnostics(result, envelope: dict) -> dict[str, object]:
        response = envelope.get("response")
        structured = envelope.get("structured_output")
        denied = envelope.get("denied_actions")
        diagnostics: dict[str, object] = {
            "provider": "agy",
            "process_returncode": result.returncode,
            "terminal_status": envelope.get("status"),
            "terminal_keys": sorted(str(key) for key in envelope),
            "structured_output_type": type(structured).__name__,
            "response_type": type(response).__name__,
            "denied_action_count": len(denied) if isinstance(denied, list) else 0,
        }
        if isinstance(denied, list):
            actions = []
            for item in denied:
                if isinstance(item, dict) and isinstance(item.get("action"), str):
                    actions.append(item["action"])
            diagnostics["denied_action_types"] = sorted(set(actions))
        if isinstance(structured, dict):
            diagnostics["structured_output_keys"] = sorted(str(key) for key in structured)
        if isinstance(response, str):
            diagnostics["response_bytes"] = len(response.encode("utf-8", "replace"))
            try:
                decoded = json.loads(response)
            except json.JSONDecodeError:
                diagnostics["response_json_type"] = "invalid"
            else:
                diagnostics["response_json_type"] = type(decoded).__name__
                if isinstance(decoded, dict):
                    diagnostics["response_json_keys"] = sorted(str(key) for key in decoded)
        return diagnostics

    def execute(self, request: RunRequest) -> Contract:
        with tempfile.TemporaryDirectory(prefix="orchestrator-agy-") as directory:
            schema = Path(directory) / "schema.json"
            schema.write_text(encode(request.result_model.model_json_schema()), encoding="utf-8")
            argv = self.command_line(request, schema)
            argv[0] = self.executable(request.config)
            input_text = encode({"event": "user", "message": {"content": request.prompt}}) + "\n"
            result = run_process(
                argv, cwd=request.workspace, input_text=input_text,
                timeout=request.timeout, cancel=request.cancel,
            )
            envelope = self._result_envelope(result.stdout)
            diagnostics = self._safe_diagnostics(result, envelope)
            if result.returncode != 0 or envelope.get("status") != "SUCCESS":
                raise ProviderExecutionError(
                    f"Antigravity failed (exit {result.returncode}, status {envelope.get('status', 'missing')}); "
                    "inspect CLI authentication/quota/permissions, then create a new task",
                    diagnostics,
                )
            denied = envelope.get("denied_actions")
            if isinstance(denied, list) and denied:
                actions = sorted({
                    item.get("action") for item in denied
                    if isinstance(item, dict) and isinstance(item.get("action"), str)
                })
                detail = ", ".join(actions) if actions else "one or more tools"
                raise ProviderExecutionError(
                    "Antigravity headless execution was permission-denied for "
                    f"{detail}; status=SUCCESS does not mean the requested work completed. "
                    "Do not use --dangerously-skip-permissions. Configure the provider's "
                    "native scoped permission policy explicitly or select another writable provider.",
                    diagnostics,
                )

            structured = envelope.get("structured_output")
            if isinstance(structured, dict):
                try:
                    return request.result_model.model_validate(structured)
                except Exception as exc:
                    raise ProviderExecutionError(
                        "Antigravity structured_output did not match the requested result contract",
                        diagnostics,
                    ) from exc

            # AGY 1.2.14 has been observed in live headless execution to omit
            # structured_output even with --json-schema. Its response may still
            # contain the requested JSON object plus AGY presentation metadata
            # (toolAction/toolSummary), as confirmed by a live protocol probe.
            # Ignore only those known provider-owned presentation keys.
            response = envelope.get("response")
            if isinstance(response, str):
                try:
                    decoded = json.loads(response)
                except json.JSONDecodeError:
                    decoded = None
                if isinstance(decoded, dict):
                    model_fields = set(request.result_model.model_fields)
                    extras = set(decoded) - model_fields
                    if extras <= {"toolAction", "toolSummary"}:
                        candidate = {key: decoded[key] for key in model_fields if key in decoded}
                        try:
                            return request.result_model.model_validate(candidate)
                        except Exception as exc:
                            raise ProviderExecutionError(
                                "Antigravity omitted structured_output and projected response JSON did not match the requested contract",
                                diagnostics,
                            ) from exc
                    try:
                        return request.result_model.model_validate(decoded)
                    except Exception as exc:
                        raise ProviderExecutionError(
                            "Antigravity omitted structured_output and response JSON did not match the requested contract",
                            diagnostics,
                        ) from exc
            raise ProviderExecutionError(
                "Antigravity returned SUCCESS without a schema-valid structured_output or JSON response",
                diagnostics,
            )


class ClaudeAdapter(CLIAdapter):
    command = "claude"
    family = "anthropic"
    # File tools only: shell is deliberately not advertised, even for implementation.
    help_flags = ("--json-schema", "--no-session-persistence", "--permission-mode", "--tools", "--strict-mcp-config", "--setting-sources", "--disable-slash-commands")

    def command_line(self, request: RunRequest, mcp: Path) -> list[str]:
        tools = "Read,Glob,Grep,Edit,Write" if request.phase == "execute" else "Read,Glob,Grep"
        settings = {"disableAllHooks": True, "autoMemoryEnabled": False}
        args = [request.config.executable or self.command, "-p", "--output-format", "json", "--json-schema", encode(request.result_model.model_json_schema()), "--no-session-persistence", "--permission-mode", "dontAsk", "--tools", tools, "--allowedTools", tools, "--disallowedTools", "mcp__*", "--strict-mcp-config", "--mcp-config", str(mcp), "--setting-sources", "", "--settings", encode(settings), "--disable-slash-commands"]
        if request.config.model:
            args += ["--model", request.config.model]
        if request.config.effort:
            args += ["--effort", request.config.effort]
        return args

    def execute(self, request: RunRequest) -> Contract:
        with tempfile.TemporaryDirectory(prefix="orchestrator-claude-") as directory:
            mcp = Path(directory) / "mcp.json"
            mcp.write_text('{"mcpServers":{}}', encoding="utf-8")
            argv = self.command_line(request, mcp)
            argv[0] = self.executable(request.config)
            # Prevent accidental recursive controller invocation from an existing Claude session.
            if os.environ.get("CLAUDECODE"):
                raise OrchestratorError("run the controller from a separate terminal, outside Claude Code")
            result = run_process(argv, cwd=request.workspace, input_text=request.prompt, timeout=request.timeout, cancel=request.cancel)
            if result.returncode:
                raise OrchestratorError(f"Claude failed (exit {result.returncode}); inspect CLI authentication/configuration")
            envelope = json.loads(result.stdout)
            if not isinstance(envelope, dict) or envelope.get("is_error") or envelope.get("permission_denials"):
                raise OrchestratorError("Claude returned an error or denied tool request")
            if "structured_output" not in envelope:
                raise OrchestratorError("Claude returned no structured output; incompatible CLI or model")
            return request.result_model.model_validate(envelope["structured_output"])


def default_registry() -> dict[str, ProviderAdapter]:
    return {"codex": CodexAdapter(), "claude": ClaudeAdapter(), "agy": AgyAdapter()}
