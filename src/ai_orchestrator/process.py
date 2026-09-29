"""Bounded, cancellable POSIX processes. No shell and no prompts in argv."""

from __future__ import annotations

import os
import re
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .models import OrchestratorError

OUTPUT_LIMIT = 2 * 1024 * 1024


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: str
    stderr: str
    duration: float


def redact(text: str) -> str:
    text = re.sub(r"(?i)\b(api[_-]?key|token|password|secret)\b\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]", text)
    text = re.sub(r"\b(?:sk|ghp|github_pat)[-_][A-Za-z0-9_-]{12,}\b", "[REDACTED]", text)
    return text


def validator_environment(home: str) -> dict[str, str]:
    # Validators never inherit model/API credentials. This is not a filesystem sandbox.
    env = {key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT") if key in os.environ}
    env.update({"HOME": home, "USERPROFILE": home, "GIT_TERMINAL_PROMPT": "0", "CI": "1", "PYTHONNOUSERSITE": "1"})
    return env


def stop_process_group(process: subprocess.Popen[bytes]) -> None:
    """Reap exited parents before signalling; fail closed on genuine denial."""
    # macOS can reject a signal to a group containing only an unreaped zombie.
    # Reaping first avoids masking an existing timeout/output-limit exception.
    process.poll()
    denied: PermissionError | None = None
    for attempt in range(2):
        try:
            os.killpg(process.pid, signal.SIGKILL)
            break
        except ProcessLookupError:
            break
        except PermissionError as exc:
            if attempt == 0 and process.poll() is not None:
                # The parent may have exited between poll() and killpg().
                # Retry after reaping, but never ignore a second denial.
                continue
            denied = exc
            break
    if process.poll() is None:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        except PermissionError as exc:
            denied = exc
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired as exc:
        raise OrchestratorError("process did not terminate; inspect remaining processes manually") from exc
    if denied is not None:
        raise OrchestratorError("process-group termination was denied; inspect remaining processes manually") from denied


def run_process(argv: list[str], *, cwd: Path, input_text: str = "", timeout: float = 600, cancel: Callable[[], bool] = lambda: False, env: dict[str, str] | None = None, output_limit: int = OUTPUT_LIMIT) -> ProcessResult:
    if os.name != "posix":
        raise OrchestratorError("POSIX is required for process-group cancellation")
    if timeout <= 0:
        raise OrchestratorError("execution time budget exhausted")
    if cancel():
        raise OrchestratorError("execution cancelled")
    start = time.monotonic()
    with tempfile.TemporaryFile() as source, tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        source.write(input_text.encode())
        source.seek(0)
        try:
            process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=source, stdout=stdout, stderr=stderr, start_new_session=True)
        except OSError as exc:
            raise OrchestratorError(f"could not start executable: {argv[0]}") from exc
        try:
            while True:
                if cancel():
                    raise OrchestratorError("execution cancelled")
                if time.monotonic() - start >= timeout:
                    raise OrchestratorError("execution timed out; no automatic retry")
                if os.fstat(stdout.fileno()).st_size + os.fstat(stderr.fileno()).st_size > output_limit:
                    raise OrchestratorError("process output exceeded the configured limit")
                if process.poll() is not None:
                    break
                time.sleep(0.05)
        finally:
            # Also kill descendants left behind by an otherwise completed parent.
            stop_process_group(process)
        if os.fstat(stdout.fileno()).st_size + os.fstat(stderr.fileno()).st_size > output_limit:
            raise OrchestratorError("process output exceeded the configured limit")
        stdout.seek(0)
        stderr.seek(0)
        return ProcessResult(process.returncode, stdout.read(output_limit).decode(errors="replace"), stderr.read(output_limit).decode(errors="replace"), time.monotonic() - start)
