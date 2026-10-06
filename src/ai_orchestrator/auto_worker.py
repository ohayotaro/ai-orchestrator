"""Operator-opted-in management of short-lived, separate worker processes."""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Mapping

from .jobs import JobQueue
from .models import OrchestratorError
from .project import Project, confined
from .worker import WORKER_MARKER, worker_lock

# Deliberate process boundary: construct a new environment rather than copy the
# conversational host's session, hooks, loaders, Python imports or shell state.
# HOME preserves normal CLI authentication. Values are never written to logs.
FORWARDED_ENV = frozenset({
    "HOME", "USER", "LOGNAME", "PATH", "LANG", "LC_ALL", "LC_CTYPE", "TMPDIR",
    "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "CODEX_HOME", "CLAUDE_CONFIG_DIR",
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN",
    "OPENAI_BASE_URL", "ANTHROPIC_BASE_URL",
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "all_proxy", "no_proxy",
    "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "NODE_EXTRA_CA_CERTS",
})


def worker_environment(source: Mapping[str, str]) -> dict[str, str]:
    env = {key: value for key, value in source.items() if key in FORWARDED_ENV}
    env.setdefault("HOME", str(Path.home()))
    env.setdefault("PATH", os.defpath)
    env.update({"PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1", "GIT_TERMINAL_PROMPT": "0"})
    return env


def worker_active(project: Project) -> bool:
    try:
        with worker_lock(project):
            return False
    except OrchestratorError as exc:
        if "already owns" in str(exc):
            return True
        raise


class AutoWorker:
    """One manager per MCP connection; project worker_lock serializes hosts.

    Starts monitoring only after an explicit queueing action. Read tools and
    MCP initialization alone never dispatch an old job. No failed job is replayed.
    """
    def __init__(self, root: Path, *, interval: float = 0.5):
        if os.environ.get(WORKER_MARKER):
            raise OrchestratorError("an internal worker cannot auto-spawn another worker")
        self.project = Project(root)
        from .safety import assert_ready
        from .build_identity import report
        assert_ready(self.project)
        self.env = worker_environment(os.environ)
        self.env["AI_ORCHESTRATOR_EXPECTED_BUILD"] = report()["loaded_build"]
        self.interval = interval
        self.stop = threading.Event()
        self.thread: threading.Thread | None = None
        self.child: subprocess.Popen | None = None
        self.mutex = threading.Lock()
        self.last_error: str | None = None
        self.last_log: str | None = None
        self.starts: list[float] = []
        self.disabled = False

    def kick(self) -> None:
        from .safety import assert_ready
        assert_ready(self.project)
        with self.mutex:
            if self.disabled:
                return
            if self.thread is None:
                self.thread = threading.Thread(target=self._loop, name="orchestrator-auto-worker", daemon=True)
                self.thread.start()

    def status(self) -> dict:
        with self.mutex:
            return {"mode": "automatic", "manager_started": self.thread is not None,
                    "last_error": self.last_error, "log": self.last_log,
                    "retry_blocked": self.disabled}

    def _tick(self) -> None:
        from .safety import assert_ready
        assert_ready(self.project)
        if self.child is not None:
            code = self.child.poll()
            if code is None:
                return
            self.child.wait()  # reap our child, including exits caused by another manager winning the lock
            self.child = None
            if code == 0:
                self.starts.clear()  # healthy idle exits are not crash-loop failures
        with JobQueueContext(self.project) as queue:
            pending = queue.db.execute("SELECT 1 FROM jobs WHERE status IN ('queued','running') LIMIT 1").fetchone()
        if not pending or worker_active(self.project):
            return
        now = time.monotonic()
        self.starts = [stamp for stamp in self.starts if now - stamp < 60]
        if len(self.starts) >= 3:
            self.disabled = True
            self.last_error = "Auto-worker startup repeated three times within a minute; inspect logs and reconnect after fixing the runtime. No jobs were replayed."
            return
        log = confined(self.project.root, f".orchestrator/runtime/auto-worker-{uuid.uuid4().hex}.log")
        log.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(log, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as stream:
                self.child = subprocess.Popen(
                    [os.path.abspath(sys.executable), "-I", "-m", "ai_orchestrator", "--project", str(self.project.root),
                     "worker", "--poll-interval", "0.25", "--idle-seconds", "2"],
                    cwd=self.project.root, env=self.env, stdin=subprocess.DEVNULL,
                    stdout=stream, stderr=stream, start_new_session=True, close_fds=True,
                )
            self.last_log = str(log.relative_to(self.project.root))
            self.starts.append(now)
            self.last_error = None
        except OSError:
            self.disabled = True
            self.last_error = "Could not launch the installed Python worker; inspect installation and permissions"
            raise

    def _loop(self) -> None:
        while not self.stop.is_set():
            try:
                with self.mutex:
                    if self.disabled:
                        return
                    self._tick()
            except Exception as exc:
                with self.mutex:
                    self.last_error = str(exc)[:1000]
                    self.disabled = True
                return
            self.stop.wait(self.interval)

    def close(self) -> None:
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=6)
        # Durable dispatched work is not cancelled on a host disconnect. The
        # detached worker drains its queue and exits after its bounded idle time.
        if self.child is not None and self.child.poll() is not None:
            self.child.wait()


class JobQueueContext:
    def __init__(self, project: Project):
        self.project = project
    def __enter__(self) -> JobQueue:
        self.queue = JobQueue(self.project)
        return self.queue
    def __exit__(self, *_):
        self.queue.close()
