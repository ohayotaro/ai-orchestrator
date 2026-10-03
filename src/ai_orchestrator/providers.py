"""Provider adapters. Safety differences remain visible in capabilities."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

from .models import AgentResult, Contract, OrchestratorError, ProviderConfig
from .process import run_process
from .project import encode, read_text
from .runtime_options import RuntimeOptionsDescriptor, RuntimeValueDescriptor
from .usage import UsageDescriptor


@dataclass(frozen=True)
class RunRequest:
    phase: str
    prompt: str
    workspace: Path
    config: ProviderConfig
    timeout: float
    cancel: Callable[[], bool]
    result_model: type[Contract] = AgentResult
    provider_permissions: frozenset[str] = frozenset()
    runtime_options: dict[str, str] = field(default_factory=dict)
    telemetry_sink: Callable[[dict[str, object]], None] | None = None
    usage_sink: Callable[[dict[str, object]], None] | None = None


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
    def describe_runtime_options(self, config: ProviderConfig, workspace: Path) -> RuntimeOptionsDescriptor: ...
    def describe_usage(self, config: ProviderConfig, workspace: Path) -> UsageDescriptor: ...
    def execute(self, request: RunRequest) -> Contract: ...


class CLIAdapter:
    api_version = 2
    command = ""
    family = ""
    help_flags: tuple[str, ...] = ()
    capabilities = frozenset({"read_files", "write_files", "fresh_session", "structured_output"})
    semantic_capabilities = frozenset({"repository_analysis", "planning", "code_edit", "test_authoring", "review", "supervision"})
    model_selection_mode = "unsupported"
    effort_selection_mode = "unsupported"
    runtime_option_limitations: tuple[str, ...] = ()

    def describe_usage(self, config: ProviderConfig, workspace: Path) -> UsageDescriptor:
        return UsageDescriptor(
            limitations=[
                "Antigravity stream-json does not currently expose a stable, adapter-attested usage schema; explicit counters are recorded opportunistically but strict token/cost budgets fail closed."
            ]
        )

    @staticmethod
    def _usage_from_envelope(envelope: dict) -> dict[str, object]:
        raw = envelope.get("usage")
        tokens: dict[str, int] = {}
        if isinstance(raw, dict):
            source_map = {
                "input_tokens": "input_tokens",
                "output_tokens": "output_tokens",
                "reasoning_tokens": "reasoning_tokens",
                "cache_read_tokens": "cache_read_tokens",
                "cache_write_tokens": "cache_write_tokens",
                "total_tokens": "total_tokens",
            }
            for source, target in source_map.items():
                value = raw.get(source)
                if type(value) is int and value >= 0:
                    tokens[target] = value
        usage: dict[str, object] = {}
        if tokens:
            usage["tokens"] = tokens
        duration = envelope.get("duration_api_ms")
        if isinstance(duration, (int, float)) and not isinstance(duration, bool) and duration >= 0:
            usage["provider_elapsed_seconds"] = float(duration) / 1000.0
        cost = envelope.get("total_cost_usd")
        if isinstance(cost, (int, float, str)) and not isinstance(cost, bool):
            usage["cost"] = {"amount": str(cost), "currency": "USD"}
        return usage

    def role_compatibility(self, role: str) -> dict[str, object]:
        return {
            "status": "supported",
            "role": role,
            "adapter": self.command,
            "requires_native_scoped_permissions": False,
            "orchestrator_attests_permissions_sufficient": True,
            "limitations": [],
        }

    def describe_usage(self, config: ProviderConfig, workspace: Path) -> UsageDescriptor:
        return UsageDescriptor(
            limitations=[
                f"{self.command or 'adapter'} does not advertise reliable structured usage telemetry"
            ]
        )

    def describe_runtime_options(self, config: ProviderConfig, workspace: Path) -> RuntimeOptionsDescriptor:
        def domain(kind: str, mode: str) -> RuntimeValueDescriptor:
            limitations = []
            if mode == "passthrough":
                limitations.append(
                    f"{self.command} exposes explicit {kind} selection but does not provide a complete reliable catalog; "
                    "the provider runtime validates the provider-local value"
                )
            return RuntimeValueDescriptor(mode=mode, limitations=limitations)

        return RuntimeOptionsDescriptor(
            model=domain("model", self.model_selection_mode),
            effort=domain("effort", self.effort_selection_mode),
            limitations=list(self.runtime_option_limitations),
        )

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
    model_selection_mode = "passthrough"
    effort_selection_mode = "passthrough"
    runtime_option_limitations = (
        "Codex model identifiers and reasoning-effort values are provider/model dependent; the adapter records pass-through provenance instead of fabricating a catalog.",
    )
    help_flags = ("--output-schema", "--output-last-message", "--sandbox", "--ephemeral", "--json")

    def describe_usage(self, config: ProviderConfig, workspace: Path) -> UsageDescriptor:
        return UsageDescriptor(
            input_tokens="reported",
            output_tokens="reported",
            reasoning_tokens="reported",
            cache_read_tokens="reported",
            cache_write_tokens="reported",
            total_tokens="unsupported",
            provider_elapsed_seconds="unsupported",
            provider_cost="unsupported",
            limitations=[
                "Codex exec JSONL reports token counters on turn.completed; total cost and provider elapsed are not attributed unless the provider adds explicit fields."
            ],
        )

    @staticmethod
    def _usage_from_jsonl(stdout: str) -> dict[str, object]:
        usage: dict[str, object] | None = None
        for line in stdout.splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict) or event.get("type") != "turn.completed":
                continue
            candidate = event.get("usage")
            if isinstance(candidate, dict):
                usage = candidate
        if usage is None:
            return {}
        source_map = {
            "input_tokens": "input_tokens",
            "output_tokens": "output_tokens",
            "reasoning_output_tokens": "reasoning_tokens",
            "cached_input_tokens": "cache_read_tokens",
            "cache_write_input_tokens": "cache_write_tokens",
            "total_tokens": "total_tokens",
        }
        tokens: dict[str, int] = {}
        for source, target in source_map.items():
            value = usage.get(source)
            if type(value) is int and value >= 0:
                tokens[target] = value
        return {"tokens": tokens} if tokens else {}

    def command_line(self, request: RunRequest, schema: Path, output: Path) -> list[str]:
        args = [request.config.executable or self.command, "exec", "--ephemeral", "--json", "--sandbox", "workspace-write" if request.phase == "execute" else "read-only", "-c", 'approval_policy="never"', "-c", 'web_search="disabled"', "-c", "sandbox_workspace_write.network_access=false", "--output-schema", str(schema), "--output-last-message", str(output), "--color", "never"]
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
            if request.usage_sink is not None:
                request.usage_sink(self._usage_from_jsonl(result.stdout))
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
    model_selection_mode = "passthrough"
    effort_selection_mode = "passthrough"
    runtime_option_limitations = (
        "Antigravity model and effort catalogs are not assumed complete; configured values are passed through and attributed to this adapter contract.",
    )
    help_flags = ("--input-format", "--output-format", "--json-schema", "--sandbox", "--print-timeout", "--mode")

    def role_compatibility(self, role: str) -> dict[str, object]:
        if role in ("supervisor", "planner", "reviewer"):
            return {
                "status": "conditional_native_permissions",
                "role": role,
                "adapter": self.command,
                "requires_native_scoped_permissions": True,
                "orchestrator_attests_permissions_sufficient": False,
                "limitations": [
                    "Antigravity headless plan/read-only sessions may choose run_command or other native tools that require AGY-scoped permission.",
                    "Orchestrator does not modify or attest the sufficiency of the user's AGY native permission policy.",
                    "Permission denial fails closed; do not auto-enable --dangerously-skip-permissions or rewrite the task prompt to bypass native permission policy.",
                ],
            }
        report = super().role_compatibility(role)
        if role == "implementer":
            report["orchestrator_attests_permissions_sufficient"] = False
            report["limitations"] = [
                "AGY native permission policy may still deny implementation tools; denial fails closed.",
                "Any Orchestrator broad-permission grant remains separate explicit task/attempt-scoped authority.",
            ]
        return report

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
        if "agy_dangerously_skip_permissions" in request.provider_permissions:
            args += ["--dangerously-skip-permissions"]
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
    def _safe_tool_telemetry(stdout: str) -> dict[str, object]:
        """Extract content-free AGY tool audit data from stream-json.

        Tool parameters, paths, commands, prompts, outputs and response text are
        intentionally ignored. Only tool names and terminal step states/counts
        are retained.
        """
        calls: dict[tuple[int, str], str] = {}
        for line in stdout.splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict) or event.get("event") != "step_update":
                continue
            update = event.get("step_update")
            if not isinstance(update, dict) or update.get("step_type") != "tool":
                continue
            name = update.get("tool_name")
            index = update.get("step_index")
            state = update.get("state")
            if not isinstance(name, str) or not isinstance(index, int) or not isinstance(state, str):
                continue
            # AGY emits ACTIVE then DONE/ERROR for the same step. Retain only
            # the latest state and aggregate below; step indexes are not stored.
            calls[(index, name)] = state

        aggregate: dict[str, dict[str, int]] = {}
        for (_, name), state in calls.items():
            counts = aggregate.setdefault(name, {"DONE": 0, "ERROR": 0, "OTHER": 0})
            bucket = state if state in ("DONE", "ERROR") else "OTHER"
            counts[bucket] += 1
        tools = [
            {
                "name": name,
                "calls": sum(counts.values()),
                "done": counts["DONE"],
                "error": counts["ERROR"],
                "other": counts["OTHER"],
            }
            for name, counts in sorted(aggregate.items())
        ]
        return {
            "provider": "agy",
            "tools": tools,
            "tool_names": [item["name"] for item in tools],
            "tool_call_count": sum(item["calls"] for item in tools),
        }

    @staticmethod
    def _safe_label(value: object) -> str | None:
        """Return only bounded identifier-like provider metadata.

        Free-form provider text may contain commands, paths or secrets and is
        therefore intentionally omitted from diagnostics.
        """
        if not isinstance(value, str) or not value or len(value) > 120:
            return None
        if not re.fullmatch(r"[A-Za-z0-9_.:-]+", value):
            return None
        return value

    @staticmethod
    def _safe_command_shape(value: object) -> dict[str, object]:
        """Summarize command shape without retaining argv, paths or arguments."""
        text: str | None = None
        first: str | None = None
        if isinstance(value, str):
            text = value
            try:
                parts = shlex.split(value, posix=True)
            except ValueError:
                parts = []
            if parts:
                first = parts[0]
        elif isinstance(value, list) and value and isinstance(value[0], str):
            first = value[0]
        summary: dict[str, object] = {}
        if first:
            executable = Path(first).name
            if executable and re.fullmatch(r"[A-Za-z0-9_.+-]{1,120}", executable):
                summary["executable"] = executable
        if text is not None:
            summary.update({
                "contains_pipe": "|" in text,
                "contains_redirection": any(token in text for token in (">", "<")),
                "contains_command_chain": any(token in text for token in ("&&", "||", ";")),
                "contains_subshell": "$(" in text or chr(96) in text,
            })
        return summary

    @classmethod
    def _safe_denied_actions(cls, denied: object) -> list[dict[str, object]]:
        """Extract minimal permission-denial facts without raw action payloads."""
        if not isinstance(denied, list):
            return []
        summaries: list[dict[str, object]] = []
        for item in denied[:32]:
            if not isinstance(item, dict):
                continue
            summary: dict[str, object] = {}
            action = cls._safe_label(item.get("action"))
            if action is not None:
                summary["action_type"] = action
            for source_key, target_key in (
                ("tool_name", "tool_name"),
                ("tool", "tool_name"),
                ("permission", "permission"),
                ("rule", "rule"),
                ("policy", "policy"),
                ("reason_code", "reason_code"),
            ):
                label = cls._safe_label(item.get(source_key))
                if label is not None and target_key not in summary:
                    summary[target_key] = label
            # "reason" is always treated as free-form provider content even
            # when it happens to look identifier-like. Only an explicit
            # reason_code field may be retained above.
            has_reason = isinstance(item.get("reason"), str)

            command_value = item.get("command")
            if command_value is None:
                command_value = item.get("cmd")
            if command_value is None:
                command_value = item.get("argv")
            command_shape = cls._safe_command_shape(command_value)
            if command_shape:
                summary["command"] = command_shape

            summary["has_freeform_reason"] = has_reason
            summary["has_details"] = any(
                key in item for key in ("details", "description", "message")
            )
            summaries.append(summary or {"action_type": "unknown"})
        return summaries

    @staticmethod
    def _safe_diagnostics(result, envelope: dict, request: RunRequest | None = None) -> dict[str, object]:
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
            summaries = AgyAdapter._safe_denied_actions(denied)
            diagnostics["denied_actions"] = summaries
            diagnostics["denied_action_types"] = sorted({
                str(item["action_type"]) for item in summaries if item.get("action_type")
            })
        diagnostics["dangerous_skip_permissions_requested"] = bool(
            request is not None
            and "agy_dangerously_skip_permissions" in request.provider_permissions
        )
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
            telemetry = self._safe_tool_telemetry(result.stdout)
            if request.telemetry_sink is not None:
                request.telemetry_sink(telemetry)
            envelope = self._result_envelope(result.stdout)
            if request.usage_sink is not None:
                request.usage_sink(self._usage_from_envelope(envelope))
            diagnostics = self._safe_diagnostics(result, envelope, request)
            diagnostics["tool_names"] = telemetry["tool_names"]
            diagnostics["tool_call_count"] = telemetry["tool_call_count"]
            if result.returncode != 0 or envelope.get("status") != "SUCCESS":
                raise ProviderExecutionError(
                    f"Antigravity failed (exit {result.returncode}, status {envelope.get('status', 'missing')}); "
                    "inspect CLI authentication/quota/permissions, then create a new task",
                    diagnostics,
                )
            denied = envelope.get("denied_actions")
            if isinstance(denied, list) and denied:
                summaries = diagnostics.get("denied_actions")
                labels: list[str] = []
                if isinstance(summaries, list):
                    for item in summaries:
                        if not isinstance(item, dict):
                            continue
                        label = str(item.get("action_type") or "action")
                        command = item.get("command")
                        if isinstance(command, dict) and command.get("executable"):
                            label += f"(executable={command['executable']})"
                        labels.append(label)
                detail = ", ".join(labels) if labels else "one or more tools"
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
    model_selection_mode = "passthrough"
    effort_selection_mode = "passthrough"
    runtime_option_limitations = (
        "Claude model and effort catalogs are provider/model dependent; the adapter records pass-through provenance instead of maintaining a kernel-global list.",
    )
    help_flags = ("--json-schema", "--no-session-persistence", "--permission-mode", "--tools", "--strict-mcp-config", "--setting-sources", "--disable-slash-commands")

    def describe_usage(self, config: ProviderConfig, workspace: Path) -> UsageDescriptor:
        return UsageDescriptor(
            input_tokens="reported",
            output_tokens="reported",
            reasoning_tokens="unsupported",
            cache_read_tokens="reported",
            cache_write_tokens="reported",
            total_tokens="unsupported",
            provider_elapsed_seconds="reported",
            provider_cost="reported",
            limitations=[
                "Claude JSON output exposes API duration/cost and token counters but does not expose hidden reasoning tokens as a separately attestable counter."
            ],
        )

    @staticmethod
    def _usage_from_envelope(envelope: dict) -> dict[str, object]:
        raw = envelope.get("usage")
        tokens: dict[str, int] = {}
        if isinstance(raw, dict):
            source_map = {
                "input_tokens": "input_tokens",
                "output_tokens": "output_tokens",
                "cache_read_input_tokens": "cache_read_tokens",
                "cache_creation_input_tokens": "cache_write_tokens",
                "total_tokens": "total_tokens",
            }
            for source, target in source_map.items():
                value = raw.get(source)
                if type(value) is int and value >= 0:
                    tokens[target] = value
        usage: dict[str, object] = {}
        if tokens:
            usage["tokens"] = tokens
        duration = envelope.get("duration_api_ms")
        if isinstance(duration, (int, float)) and not isinstance(duration, bool) and duration >= 0:
            usage["provider_elapsed_seconds"] = float(duration) / 1000.0
        cost = envelope.get("total_cost_usd")
        if isinstance(cost, (int, float, str)) and not isinstance(cost, bool):
            usage["cost"] = {"amount": str(cost), "currency": "USD"}
        return usage

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
            if isinstance(envelope, dict) and request.usage_sink is not None:
                request.usage_sink(self._usage_from_envelope(envelope))
            if not isinstance(envelope, dict) or envelope.get("is_error") or envelope.get("permission_denials"):
                raise OrchestratorError("Claude returned an error or denied tool request")
            if "structured_output" not in envelope:
                raise OrchestratorError("Claude returned no structured output; incompatible CLI or model")
            return request.result_model.model_validate(envelope["structured_output"])


def default_registry() -> dict[str, ProviderAdapter]:
    return {"codex": CodexAdapter(), "claude": ClaudeAdapter(), "agy": AgyAdapter()}
