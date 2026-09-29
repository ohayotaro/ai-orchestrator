"""Operator-owned local worker, separate from any conversational agent session."""

from __future__ import annotations

import contextlib
import os
import signal
import threading
import time
from pathlib import Path
from typing import Callable, Iterator

from .engine import Engine
from .jobs import JobQueue
from .models import OrchestratorError
from .process import redact
from .project import Project, confined
from .providers import ProviderAdapter
from .service import ApplicationService, AskInput, RunInput
from .supervisor import Supervisor

WORKER_MARKER = "AI_ORCHESTRATOR_INTERNAL_WORKER"


@contextlib.contextmanager
def worker_lock(project: Project) -> Iterator[None]:
    if os.name != "posix":
        raise OrchestratorError("worker requires POSIX process locking")
    import fcntl

    project.runtime.mkdir(parents=True, exist_ok=True)
    path = confined(project.root, ".orchestrator/runtime/worker.lock")
    with path.open("a+") as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise OrchestratorError("a worker already owns this project") from exc
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def process_one(queue: JobQueue, *, registry: dict[str, ProviderAdapter] | None = None, stop: Callable[[], bool] = lambda: False) -> dict | None:
    """Caller owns worker_lock. A claim is consumed at most once, never replayed."""
    import time

    job = queue.claim()
    if job is None:
        return None
    cancelled = lambda: stop() or queue.cancelled(job.id)
    engine = None
    try:
        if cancelled():
            raise OrchestratorError("job cancelled before execution")
        if time.time() >= job.expires_at:
            raise OrchestratorError("queued job expired; inspect state and submit a new request_id")
        engine = Engine(queue.project.root, registry, cancel_check=cancelled)
        if engine.profile_digest != job.profile_digest:
            raise OrchestratorError("profile changed since queueing; no model was called")
        if job.action == "ask":
            params = AskInput.model_validate({**job.arguments, "request_id": job.request_id})
            intake = Supervisor(engine).ask(params.request, task_id=params.task_id, advisory=params.advisory, reply_to=params.reply_to, expected_workspace=job.workspace_snapshot)
            job.result = Supervisor(engine).describe(intake.id)
        else:
            params = RunInput.model_validate({**job.arguments, "request_id": job.request_id})
            ApplicationService.check_run(engine, params.task_id)
            state = engine.run(params.task_id, expected_workspace=job.workspace_snapshot)
            job.result = ApplicationService.task_view(engine, state.spec.id)
        outcome = job.result.get("status")
        job.status = "cancelled" if outcome == "cancelled" or cancelled() else "failed" if outcome in ("failed", "blocked") else "succeeded"
        if job.status == "failed":
            job.error = redact(str(job.result.get("error") or "operation blocked/failed; inspect the result"))
        if job.status == "cancelled" and job.action == "run":
            engine.store.request_cancel(job.arguments["task_id"])
    except (Exception, KeyboardInterrupt) as exc:
        job.status = "cancelled" if isinstance(exc, KeyboardInterrupt) or cancelled() else "failed"
        job.error = redact(str(exc))[:4000]
    finally:
        if engine is not None:
            engine.close()
    queue.finish(job)
    return queue.get(job.id).model_dump()


def run_worker(root: Path, *, once: bool = False, poll_interval: float = 1.0, idle_seconds: float | None = None) -> dict:
    if os.environ.get("CLAUDECODE") or os.environ.get(WORKER_MARKER):
        raise OrchestratorError("start worker manually in a separate normal terminal, not inside an agent/worker; session guards are not cleared")
    if not 0.1 <= poll_interval <= 60:
        raise OrchestratorError("poll interval must be between 0.1 and 60 seconds")
    if idle_seconds is not None and not 0.1 <= idle_seconds <= 60:
        raise OrchestratorError("idle-seconds must be between 0.1 and 60")
    project = Project(root)
    project.load()
    stop = threading.Event()
    previous = {}
    processed = 0
    with worker_lock(project):
        queue = JobQueue(project)
        try:
            # The worker lock proves another cooperating worker cannot still own these.
            interrupted = queue.interrupt_stale()
            if threading.current_thread() is threading.main_thread():
                for sig in (signal.SIGINT, signal.SIGTERM):
                    previous[sig] = signal.signal(sig, lambda *_: stop.set())
            os.environ[WORKER_MARKER] = "1"
            idle_since = time.monotonic()
            while not stop.is_set():
                result = process_one(queue, stop=stop.is_set)
                if result is not None:
                    processed += 1
                    idle_since = time.monotonic()
                if once:
                    return {"processed": processed, "interrupted_jobs": interrupted, "job": result}
                if result is None:
                    if idle_seconds is not None and time.monotonic() - idle_since >= idle_seconds:
                        return {"processed": processed, "interrupted_jobs": interrupted, "idle_exit": True}
                    stop.wait(poll_interval)
            return {"processed": processed, "interrupted_jobs": interrupted, "stopped": True}
        finally:
            os.environ.pop(WORKER_MARKER, None)
            for sig, handler in previous.items():
                signal.signal(sig, handler)
            queue.close()
