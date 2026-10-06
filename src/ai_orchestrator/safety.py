"""Shared mutation and dispatch checks for cooperating trusted-local controllers."""
from __future__ import annotations
import functools
import os
from .models import OrchestratorError


def operator_only() -> None:
    if any(os.environ.get(key) for key in ('CLAUDECODE', 'AI_ORCHESTRATOR_INTERNAL_WORKER', 'CODEX_THREAD_ID')):
        raise OrchestratorError('operation is operator-only; use a separate normal terminal')


def assert_ready(project) -> None:
    from .build_identity import assert_current
    from .maintenance import assert_clear
    assert_current()
    assert_clear(project)


def dispatch_guard(engine, task_id: str | None = None) -> None:
    assert_ready(engine.project)
    if task_id is not None and engine.store.cancelled(task_id):
        raise OrchestratorError('execution cancelled: task has a cancellation request')


def serialized(method):
    """Use the same re-entrant project boundary for queue, gate and state writes."""
    @functools.wraps(method)
    def wrapped(self, *args, **kwargs):
        with self.project.lock(_nested=True, _wait=True):
            assert_storage_current(self)
            return method(self, *args, **kwargs)
    return wrapped


def thread_dispatch_guard(project, task_id):
    """Parallel provider threads never use the controller's SQLite connection."""
    from .operational import _readonly_connection
    from .project import confined
    assert_ready(project)
    db = _readonly_connection(confined(project.root, '.orchestrator/runtime/state.sqlite3'))
    try:
        row = db.execute('SELECT cancel_requested FROM tasks WHERE id=?', (task_id,)).fetchone()
        if row is None or row[0]:
            raise OrchestratorError('execution cancelled before provider dispatch')
    finally:
        db.close()


def bind_storage(instance, path):
    stat = path.stat()
    instance._database_path = path
    instance._database_identity = (stat.st_dev, stat.st_ino)


def assert_storage_current(instance):
    path = getattr(instance, '_database_path', None)
    if path is None:
        return
    try:
        stat = path.stat()
        if (stat.st_dev, stat.st_ino) == instance._database_identity:
            return
    except OSError:
        pass
    raise OrchestratorError('storage_replaced: reopen the controller/queue after maintenance')


def storage_constructor(method):
    """Current-version opens need no project lock (cooperative cancellation must
    remain available while run holds it). Schema creation/migration does. Both
    paths share the short cancellation/maintenance exclusion boundary.
    """
    @functools.wraps(method)
    def guarded(self, project, *args, **kwargs):
        from .maintenance import cancellation_boundary
        from .operational import _readonly_connection
        from .project import confined
        from .persistence import RUNTIME_DB_VERSION, JOB_DB_VERSION, HUMAN_GATE_DB_VERSION
        import contextlib
        import sqlite3
        specs = {
            'Store': ('state.sqlite3', RUNTIME_DB_VERSION, {'tasks','intakes','events','approvals','metadata','explorations'}),
            'JobQueue': ('jobs.sqlite3', JOB_DB_VERSION, {'jobs','job_events','request_receipts'}),
            'GateStore': ('gates.sqlite3', HUMAN_GATE_DB_VERSION, {'gates','gate_events'}),
        }
        filename, current, expected = specs[type(self).__name__]
        path = confined(project.root, '.orchestrator/runtime/' + filename)
        needs_migration = True
        if path.exists():
            db = _readonly_connection(path)
            try:
                version = db.execute('PRAGMA user_version').fetchone()[0]
                if version == current:
                    actual = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    if not expected <= actual:
                        raise OrchestratorError('current database schema is incomplete; refusing implicit repair')
                    needs_migration = False
            finally:
                db.close()
        lock = project.lock(_nested=True, _wait=True) if needs_migration else contextlib.nullcontext()
        with lock, cancellation_boundary(project):
            assert_ready(project)
            return method(self, project, *args, **kwargs)
    return guarded


def cancellation_mutation(method):
    """Keep cooperative cancel available during provider calls but serialize it
    against backup/restore/cleanup. Ordinary project writes use project.lock.
    """
    @functools.wraps(method)
    def guarded(self, *args, **kwargs):
        from .maintenance import cancellation_boundary
        with cancellation_boundary(self.project):
            assert_ready(self.project)
            assert_storage_current(self)
            return method(self, *args, **kwargs)
    return guarded
