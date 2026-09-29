"""Provider adapters. Safety differences remain visible in capabilities."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from .models import AgentResult, OrchestratorError, ProviderConfig
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


class ProviderAdapter(Protocol):
    family: str
    capabilities: frozenset[str]

    def doctor(self, config: ProviderConfig, workspace: Path) -> dict[str, str]: ...
    def execute(self, request: RunRequest) -> AgentResult: ...


class CLIAdapter:
    command = ""
    family = ""
    help_flags: tuple[str, ...] = ()
    capabilities = frozenset({"read_files", "write_files", "fresh_session", "structured_output"})

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
        missing = [flag for flag in self.help_flags if flag not in help_result.stdout]
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

    def execute(self, request: RunRequest) -> AgentResult:
        with tempfile.TemporaryDirectory(prefix="orchestrator-codex-") as directory:
            schema, output = Path(directory) / "schema.json", Path(directory) / "result.json"
            schema.write_text(encode(AgentResult.model_json_schema()), encoding="utf-8")
            argv = self.command_line(request, schema, output)
            argv[0] = self.executable(request.config)
            result = run_process(argv, cwd=request.workspace, input_text=request.prompt, timeout=request.timeout, cancel=request.cancel)
            if result.returncode != 0 or not output.is_file():
                raise OrchestratorError(f"Codex failed (exit {result.returncode}); inspect CLI authentication/configuration, then create a new task")
            return AgentResult.model_validate_json(read_text(output))


class ClaudeAdapter(CLIAdapter):
    command = "claude"
    family = "anthropic"
    # File tools only: shell is deliberately not advertised, even for implementation.
    help_flags = ("--json-schema", "--no-session-persistence", "--permission-mode", "--tools", "--strict-mcp-config", "--setting-sources", "--disable-slash-commands")

    def command_line(self, request: RunRequest, mcp: Path) -> list[str]:
        tools = "Read,Glob,Grep,Edit,Write" if request.phase == "execute" else "Read,Glob,Grep"
        settings = {"disableAllHooks": True, "autoMemoryEnabled": False}
        args = [request.config.executable or self.command, "-p", "--output-format", "json", "--json-schema", encode(AgentResult.model_json_schema()), "--no-session-persistence", "--permission-mode", "dontAsk", "--tools", tools, "--allowedTools", tools, "--disallowedTools", "mcp__*", "--strict-mcp-config", "--mcp-config", str(mcp), "--setting-sources", "", "--settings", encode(settings), "--disable-slash-commands"]
        if request.config.model:
            args += ["--model", request.config.model]
        if request.config.effort:
            args += ["--effort", request.config.effort]
        return args

    def execute(self, request: RunRequest) -> AgentResult:
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
            return AgentResult.model_validate(envelope["structured_output"])


def default_registry() -> dict[str, ProviderAdapter]:
    return {"codex": CodexAdapter(), "claude": ClaudeAdapter()}
