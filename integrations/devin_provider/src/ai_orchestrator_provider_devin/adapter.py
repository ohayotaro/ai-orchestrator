"""Devin CLI Provider SDK prototype: real dispatch is deliberately disabled.

The isolated protocol harness is exercised only with offline fake executables.
Neither CLI --print nor sandbox alone supplies the native authority and
final-result assurances required for unattended implementation.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ai_orchestrator.models import Contract, OrchestratorError, ProviderConfig
from ai_orchestrator.provider_sdk import ProviderExecutionError, RunRequest, RuntimeOptionsDescriptor, UsageDescriptor
from ai_orchestrator.runtime_options import RuntimeValueDescriptor

REVIEWED_CLI_VERSION = "devin 3000.11.3 (9c803229faa4)"
REQUIRED_HELP_FLAGS = (
    "--print", "--prompt-file", "--permission-mode", "--sandbox",
    "--model", "--config", "--respect-workspace-trust",
)
MAX_OUTPUT_BYTES = 1024 * 1024
MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/+:-]{0,127}\Z")
# Observed in the owner's exact 3000.11.3 --help. Neither option is an
# authorization from ai-orchestrator. In particular "auto" does not grant
# unattended workspace edits, and this adapter remains disabled.
FIXTURE_PERMISSION_MODE = "auto"


def _advertised_permission_modes(help_text: str) -> frozenset[str]:
    """Read only quoted values in the CLI's 'Modes:' help line.

    Avoid accepting a flag name or incidental prose as proof of an available
    permission mode. Version-specific gaps fail closed.
    """
    for line in help_text.splitlines():
        if re.match(r"^\s*Modes:\s*", line):
            return frozenset(re.findall(r'"([a-z][a-z-]*)"', line))
    return frozenset()


@dataclass(frozen=True)
class _Result:
    returncode: int
    stdout: str


def _diagnostic(category: str, code: str) -> dict[str, str]:
    return {"failure_category": category, "stage": code}


def _resolve_executable(config: ProviderConfig) -> str:
    executable = config.executable or "devin"
    path = shutil.which(executable)
    if not path or not Path(path).is_file() or not os.access(path, os.X_OK):
        raise OrchestratorError("Devin CLI executable is not available")
    return str(Path(path).resolve())


def _minimal_subprocess_env() -> dict[str, str]:
    """No inherited API tokens, native permission overrides or agent guards.

    This is a defense in depth for the fixture runner, not a claim that HOME
    configuration, Keychain, remote model or native permissions are isolated.
    """
    allowed = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT")
    result = {name: os.environ[name] for name in allowed if name in os.environ}
    result["GIT_TERMINAL_PROMPT"] = "0"
    result["PYTHONNOUSERSITE"] = "1"
    return result


def _run_bounded(argv: list[str], cwd: Path, *, timeout: float, cancel: Callable[[], bool]) -> _Result:
    """Bounded POSIX child with process-group cancellation, no shell or output logs."""
    if os.name != "posix" or timeout <= 0 or cancel():
        raise ProviderExecutionError("Devin process preflight refused", _diagnostic("configuration", "preflight"))
    started = time.monotonic()
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        try:
            proc = subprocess.Popen(
                argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                start_new_session=True, env=_minimal_subprocess_env(),
            )
        except OSError as exc:
            raise ProviderExecutionError("Devin process could not start", _diagnostic("provider_process", "spawn")) from exc
        issue: str | None = None
        try:
            while proc.poll() is None:
                if cancel():
                    issue = "cancelled"
                    break
                if time.monotonic() - started >= timeout:
                    issue = "timeout"
                    break
                if os.fstat(stdout.fileno()).st_size + os.fstat(stderr.fileno()).st_size > MAX_OUTPUT_BYTES:
                    issue = "output_limit"
                    break
                time.sleep(0.02)
        finally:
            # The child may have exited while descendants remain in its group.
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except PermissionError as exc:
                raise ProviderExecutionError("Devin process termination denied", _diagnostic("provider_process", "kill_denied")) from exc
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired as exc:
                raise ProviderExecutionError("Devin process termination uncertain", _diagnostic("provider_process", "kill_uncertain")) from exc
        if issue:
            raise ProviderExecutionError("Devin process did not complete", _diagnostic("provider_process", issue))
        if os.fstat(stdout.fileno()).st_size + os.fstat(stderr.fileno()).st_size > MAX_OUTPUT_BYTES:
            raise ProviderExecutionError("Devin process exceeded output bounds", _diagnostic("protocol", "output_limit"))
        stdout.seek(0)
        return _Result(proc.returncode, stdout.read(MAX_OUTPUT_BYTES).decode("utf-8", errors="replace"))


class ProtocolHarness:
    """Synthetic fixture harness, NOT the installed adapter execution method.

    A prompt asking for JSON is not a native structured-output guarantee. Tests
    may demonstrate strict rejection, but do not qualify a real Devin CLI.
    """

    def argv(self, request: RunRequest, *, binary: str, prompt: Path, config: Path) -> list[str]:
        if request.phase != "execute":
            raise ProviderExecutionError("Devin candidate is implementation-only", _diagnostic("configuration", "role"))
        if request.config.effort is not None or request.runtime_options:
            raise ProviderExecutionError("Devin effort/runtime flags are not qualified", _diagnostic("configuration", "runtime_options"))
        if request.provider_permissions:
            raise ProviderExecutionError("Devin broad provider grants are unsupported", _diagnostic("permission", "grants"))
        if request.config.model and not MODEL_ID.fullmatch(request.config.model):
            raise ProviderExecutionError("Devin model selector is not a safe identifier", _diagnostic("configuration", "model"))
        args = [
            binary, "--print", "--prompt-file", str(prompt), "--config", str(config),
            # The exact 3000.11.3 help lists "auto", not "autonomous".
            # This mode may require interactive approval for edits. The
            # protocol harness remains fixture-only; do not enable execute.
            "--sandbox", "--permission-mode", FIXTURE_PERMISSION_MODE, "--respect-workspace-trust", "true",
        ]
        if request.config.model:
            args += ["--model", request.config.model]
        return args

    @staticmethod
    def parse(raw: str, model: type[Contract]) -> Contract:
        try:
            # The entire stdout must be one JSON object matching the exact
            # requested result contract: no fences, chatter or partial salvage.
            def unique_keys(pairs):
                data = {}
                for key, value in pairs:
                    if key in data:
                        raise ValueError("duplicate JSON key")
                    data[key] = value
                return data

            def reject_constant(value):
                raise ValueError("non-finite JSON constant")

            payload = json.loads(raw, object_pairs_hook=unique_keys, parse_constant=reject_constant)
            if not isinstance(payload, dict):
                raise ValueError("non-object")
            return model.model_validate(payload)
        except (ValueError, TypeError) as exc:
            raise ProviderExecutionError("Devin candidate result failed strict validation", _diagnostic("protocol", "result")) from exc

    def run_fixture(self, request: RunRequest, *, binary: str, runner: Callable[..., _Result] = _run_bounded) -> Contract:
        """Offline fake-CLI fixture only; never called by Adapter.execute."""
        workspace = request.workspace.resolve(strict=True)
        if not workspace.is_dir():
            raise ProviderExecutionError("Devin candidate workspace is invalid", _diagnostic("configuration", "workspace"))
        if runner is _run_bounded:
            # The synthetic process test must never accidentally invoke the
            # real, potentially billable Devin CLI. An injected fake runner
            # executes no process here; it is not a security boundary.
            fixture = Path(binary)
            if (not fixture.is_absolute() or fixture.is_symlink() or
                    fixture.name != "fake-devin" or
                    not fixture.is_file() or not fixture.resolve().is_relative_to(workspace)):
                raise ProviderExecutionError(
                    "Devin fixture executable is not an in-workspace fake",
                    _diagnostic("configuration", "fixture_binary"),
                )
        if request.cancel():
            raise ProviderExecutionError("Devin candidate was cancelled before invocation", _diagnostic("provider_process", "cancelled"))
        with tempfile.TemporaryDirectory(prefix="orchestrator-devin-fixture-") as directory:
            base = Path(directory)
            prompt = base / "prompt.txt"
            prompt.write_text(request.prompt, encoding="utf-8")
            prompt.chmod(0o600)
            policy = base / "config.json"
            policy.write_text(json.dumps({
                "permissions": {"allow": [], "deny": ["mcp__*"], "ask": []},
                "read_config_from": {"cursor": False, "windsurf": False, "claude": False},
                "subagents_enabled": False,
            }), encoding="utf-8")
            policy.chmod(0o600)
            argv = self.argv(request, binary=binary, prompt=prompt, config=policy)
            outcome = runner(argv, workspace, timeout=request.timeout, cancel=request.cancel)
        if request.cancel():
            raise ProviderExecutionError("Devin candidate cancelled after process completion", _diagnostic("provider_process", "cancelled"))
        if outcome.returncode:
            raise ProviderExecutionError("Devin candidate process reported failure", _diagnostic("provider_process", "nonzero"))
        response = self.parse(outcome.stdout, request.result_model)
        if request.cancel():
            raise ProviderExecutionError("Devin candidate cancelled before accepting result", _diagnostic("provider_process", "cancelled"))
        return response


class Adapter:
    """Pinned SDK plugin metadata and a fail-closed activation boundary.

    Deliberately advertises no role capabilities until the actual Devin CLI
    earns a native permission/scope/result qualification on the owner machine.
    """

    provider_sdk_version = 1
    api_version = 2
    family = "cognition"
    capabilities = frozenset()
    semantic_capabilities = frozenset()

    def doctor(self, config: ProviderConfig, workspace: Path) -> dict[str, str]:
        executable = _resolve_executable(config)
        try:
            version = subprocess.run([executable, "--version"], cwd=workspace,
                                     capture_output=True, timeout=10, text=True, env=_minimal_subprocess_env())
            help_result = subprocess.run([executable, "--help"], cwd=workspace,
                                         capture_output=True, timeout=10, text=True, env=_minimal_subprocess_env())
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise OrchestratorError("Devin CLI metadata probe failed") from exc
        if version.returncode or version.stdout.strip() != REVIEWED_CLI_VERSION:
            raise OrchestratorError("Devin CLI version differs from reviewed 3000.11.3")
        help_text = help_result.stdout + help_result.stderr
        if help_result.returncode or any(flag not in help_text for flag in REQUIRED_HELP_FLAGS):
            raise OrchestratorError("Devin CLI lacks required reviewed flags")
        if FIXTURE_PERMISSION_MODE not in _advertised_permission_modes(help_text):
            raise OrchestratorError("Devin CLI does not advertise the reviewed auto permission mode")
        return {"version": REVIEWED_CLI_VERSION, "family": self.family,
                "authentication": "not_checked", "execution": "blocked_pending_native_qualification"}

    def describe_runtime_options(self, config: ProviderConfig, workspace: Path) -> RuntimeOptionsDescriptor:
        return RuntimeOptionsDescriptor(
            model=RuntimeValueDescriptor(mode="passthrough"),
            effort=RuntimeValueDescriptor(mode="unsupported"),
            limitations=["Model aliases are not resolved IDs; headless effort selection unverified."],
        )

    def describe_usage(self, config: ProviderConfig, workspace: Path) -> UsageDescriptor:
        return UsageDescriptor(limitations=["Devin CLI --print has no qualified token/cost schema."])

    def role_compatibility(self, role: str) -> dict[str, object]:
        return {"status": "unverified", "role": role, "adapter": "devin",
                "requires_native_scoped_permissions": True,
                "orchestrator_attests_permissions_sufficient": False,
                "limitations": ["No role is enabled until native permission, workspace isolation and final-result protocols are owner-live qualified."]}

    def execute(self, request: RunRequest) -> Contract:
        # Not an environment flag or a hidden test-only bypass. Activation must
        # be a reviewed adapter version after real owner-local evidence.
        raise ProviderExecutionError("Devin provider execution is not yet qualified", _diagnostic("configuration", "unqualified"))
