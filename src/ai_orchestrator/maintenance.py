"""Durable incomplete-operation barriers, not automatic repair or replay.

Intent/recovery material lives outside the archive replacement universe. Public
reads can explain a blocked operation; only an exact-scope operator reconcile or
acknowledged recovery restore may resolve it. Fault seams have no public switch.
"""
from __future__ import annotations
import contextlib
import hashlib
import fcntl
import json
import os
import time
import uuid
from pathlib import Path
from typing import Literal, Any
from pydantic import Field
from .models import Contract, OrchestratorError
from .project import Project, confined, atomic_write, digest, encode

REL = '.orchestrator/runtime/maintenance-journal'
FORMAT = {'schema_version':1, 'kind':'operator-maintenance-journal'}
MAX_RECORD = 16 * 1024 * 1024
PHASES = {'preparing','applying','data_verified','rolled_back','completed'}


class MaintenanceIntent(Contract):
    schema_version: Literal[1] = 1
    operation_id: str = Field(pattern=r'^M-[a-f0-9]{32}$')
    action: Literal['restore','cleanup']
    scope: str = Field(pattern=r'^[a-f0-9]{64}$')
    actor: str = Field(min_length=1, max_length=256)
    mode: Literal['runtime','full']
    phase: Literal['preparing','applying','data_verified','rolled_back','completed']
    created_at: float = Field(ge=0, allow_inf_nan=False)
    before: dict[str, Any]
    after: dict[str, Any] | None
    targets: dict[str, list[str]]
    supersedes: dict[str, Any] | None
    rollback_ready: bool = False
    completion_event_id: str | None = None


@contextlib.contextmanager
def cancellation_boundary(project: Project, *, exclusive: bool = False):
    path = confined(project.root, '.orchestrator/runtime/cancellation.lock')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+') as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def sync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
    try: os.fsync(fd)
    finally: os.close(fd)


def checkpoint(phase: str) -> None:
    """No-op injection seam replaced only by tests in disposable subprocesses."""


def _root(project):
    return confined(project.root, REL)


def _write(path, value):
    atomic_write(path, encode(value) + '\n')
    sync_directory(path.parent)


def _read(project):
    root = _root(project)
    if not root.exists(): return None
    format_path = confined(project.root, REL+'/format.json')
    if not root.is_dir() or not format_path.is_file():
        raise OrchestratorError('maintenance journal collision/unrecognized format; no automatic repair')
    if format_path.stat().st_size > 1024:
        raise OrchestratorError('maintenance journal format exceeds safety bound')
    fmt = json.loads(format_path.read_text())
    if not isinstance(fmt, dict) or type(fmt.get('schema_version')) is not int or fmt != FORMAT:
        raise OrchestratorError('unknown maintenance journal format')
    path = confined(project.root, REL+'/active.json')
    if not path.exists(): return None
    if path.stat().st_size > MAX_RECORD:
        raise OrchestratorError('maintenance intent exceeds safety bound')
    envelope = json.loads(path.read_text())
    if not isinstance(envelope, dict) or set(envelope) != {'record', 'sha256'} or not isinstance(envelope.get('record'), dict):
        raise OrchestratorError('invalid maintenance intent envelope')
    record = envelope['record']
    if envelope['sha256'] != digest(record):
        raise OrchestratorError('maintenance intent integrity mismatch')
    if type(record.get('schema_version')) is not int or record['schema_version'] != 1:
        raise OrchestratorError('unknown maintenance intent version')
    if record.get('phase') not in PHASES or record.get('action') not in ('restore','cleanup') or record.get('mode') not in ('runtime','full'):
        raise OrchestratorError('invalid maintenance operation/phase')
    operation_id = record.get('operation_id','')
    if len(operation_id) != 34 or not operation_id.startswith('M-') or any(c not in '0123456789abcdef' for c in operation_id[2:]):
        raise OrchestratorError('invalid maintenance identity')
    MaintenanceIntent.model_validate(record)
    return record


def assert_clear(project):
    try:
        record = _read(project)
    except (OSError, ValueError, KeyError, TypeError, OrchestratorError) as exc:
        raise OrchestratorError('maintenance_pending: invalid journal; inspect before any new work') from exc
    if record is not None:
        raise OrchestratorError('maintenance_pending: inspect and reconcile the incomplete operator operation')


def _sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''): h.update(chunk)
    return h.hexdigest()


def _sqlite_snapshot(path):
    from .operational import _readonly_connection
    db = _readonly_connection(path)
    try:
        rows = db.execute("SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()
        h = hashlib.sha256()
        h.update(encode([db.execute('PRAGMA user_version').fetchone()[0], rows]).encode())
        for name, sql in rows:
            name = '"'+name.replace('"','""')+'"'
            columns = [row[1] for row in db.execute(f'PRAGMA table_info({name})')]
            order = ','.join('"'+c.replace('"','""')+'"' for c in columns)
            for row in db.execute(f'SELECT * FROM {name} ORDER BY {order}'):
                values = [{'blob':v.hex()} if isinstance(v,bytes) else v for v in row]
                h.update(encode(values).encode());h.update(b'\n')
        return {'kind':'sqlite-logical', 'sha256':h.hexdigest()}
    finally: db.close()


def snapshot(project: Project, mode: str) -> dict:
    """Canonical logical DB + file inventory, excluding locks/journal/audit append.

    Corrupt DB bytes can be retained as rollback evidence without interpreting
    them. Such a rollback never grants authority; normal readers still reject it.
    """
    from .operational import _iter_managed_files
    import sqlite3
    out = {}
    for path in _iter_managed_files(project, mode):
        relative = path.relative_to(project.root).as_posix()
        if relative == '.orchestrator/runtime/maintenance.jsonl': continue
        if path.parent == project.runtime and path.name in ('state.sqlite3','jobs.sqlite3','gates.sqlite3'):
            try: out[relative] = _sqlite_snapshot(path)
            except (sqlite3.Error, OSError, ValueError):
                out[relative] = {'kind':'unreadable-sqlite', 'sha256':_sha(path)}
                for suffix in ('-wal','-shm','-journal'):
                    sidecar = path.with_name(path.name+suffix)
                    if sidecar.exists(): out[relative+suffix] = {'sha256':_sha(sidecar)}
        else:
            out[relative] = {'kind':'file','sha256':_sha(path),'bytes':path.stat().st_size}
    # Worktree identity is also part of reconciliation scope, even though
    # portable backups intentionally omit these disposable directories.
    base = confined(project.root, '.orchestrator/runtime/worktrees')
    if base.exists():
        count = 0
        for path in sorted(base.rglob('*')):
            count += 1
            if count > 100000:
                raise OrchestratorError('maintenance worktree inventory exceeds safety bound')
            relative = path.relative_to(project.root).as_posix()
            if path.is_symlink():
                out[relative] = {'kind':'symlink','target_sha256':hashlib.sha256(os.readlink(path).encode()).hexdigest()}
            elif path.is_file():
                out[relative] = {'kind':'file','sha256':_sha(path),'bytes':path.stat().st_size}
            elif path.is_dir():
                out[relative] = {'kind':'directory'}
            else:
                raise OrchestratorError('special file in maintenance worktree inventory')
    return out


def _save(project, record):
    root = _root(project)
    envelope = {'record':record,'sha256':digest(record)}
    if len(encode(envelope).encode()) > MAX_RECORD:
        raise OrchestratorError('maintenance record exceeds safety bound')
    directory = confined(project.root, REL+'/operations/'+record['operation_id'])
    directory.mkdir(parents=True, exist_ok=True)
    _write(directory/'intent.json', envelope)
    _write(root/'active.json', envelope)


def inspect(project: Project) -> dict:
    try:
        record = _read(project)
        if record is None:
            return {'schema_version':1,'ok':True,'pending':False,'reconciliation_scope':None,
                    'automatic_repair':False}
        current = snapshot(project, record['mode'])
        unchanged = current == record.get('before')
        applied = record.get('after') is not None and current == record['after']
        basis = {'record':record,'current':current}
        return {'schema_version':1,'ok':False,'pending':True,'valid':True,
                'operation_id':record['operation_id'],'action':record['action'],'phase':record['phase'],
                'before_matches':unchanged,'after_matches':applied,
                'reconcilable':unchanged or applied,
                'reconciliation_scope':digest(basis),'automatic_repair':False}
    except (OSError, ValueError, KeyError, TypeError, OrchestratorError) as exc:
        # Still content-free; preserve raw invalid marker, do not rewrite it on read.
        contents = {}
        # lstat/readlink do not follow an invalid control symlink. An invalid
        # journal must still be diagnosable, never an excuse to load its target.
        root = project.root / REL
        for name in ('format.json','active.json'):
            try:
                path = confined(project.root, REL+'/'+name)
                if path.is_file() and path.stat().st_size <= MAX_RECORD:
                    contents[name] = _sha(path)
                elif path.exists():
                    contents[name] = {'invalid_type_or_size': True}
            except (OSError, OrchestratorError):
                contents[name] = {'unreadable_or_symlink': True}
        if root.is_symlink():
            contents['root_link'] = hashlib.sha256(os.readlink(root).encode()).hexdigest()
        return {'schema_version':1,'ok':False,'pending':True,'valid':False,'reconcilable':False,
                'error':str(exc),'reconciliation_scope':digest(contents),'automatic_repair':False}


def begin(project, *, action, scope, actor, mode, acknowledge_incomplete=None, targets=None):
    from .operational import _validate_maintenance_identity
    actor = _validate_maintenance_identity(action, actor, scope)
    old = inspect(project)
    if old['pending'] and acknowledge_incomplete != old['reconciliation_scope']:
        raise OrchestratorError('maintenance_pending: recovery restore requires --ack-incomplete-operation with current scope')
    root = _root(project)
    if root.exists() and not (root/'format.json').is_file():
        raise OrchestratorError('maintenance journal collision; refusing to replace unrelated files')
    before = snapshot(project, mode)
    record = {'schema_version':1, 'operation_id':'M-'+uuid.uuid4().hex, 'action':action,
              'scope':scope,'actor':actor,'mode':mode,'phase':'preparing','created_at':time.time(),
              'before':before,'after':None,'targets':targets or {},'supersedes':old if old['pending'] else None}
    root.mkdir(parents=True, exist_ok=True)
    if not (root/'format.json').exists():
        _write(root/'format.json', FORMAT)
        sync_directory(root.parent)
    directory = confined(project.root, REL+'/operations/'+record['operation_id'])
    directory.mkdir(parents=True)
    sync_directory(directory.parent)
    if (root/'active.json').exists():
        # Preserve the previous marker and all its recovery material indefinitely.
        old_bytes = (root/'active.json').read_bytes()
        path = directory/'superseded-active.json'
        with path.open('xb') as stream:
            stream.write(old_bytes);stream.flush();os.fsync(stream.fileno())
    _save(project, record)
    checkpoint('after_intent')
    return record


def directory(project, record):
    return confined(project.root, REL+'/operations/'+record['operation_id'])


def applying(project, record):
    record['phase'] = 'applying'
    _save(project, record)
    checkpoint('before_mutation')


def verified(project, record):
    record['after'] = snapshot(project, record['mode'])
    record['phase'] = 'data_verified'
    _save(project, record)
    checkpoint('after_data')


def finish(project, record, event):
    record['phase'] = 'completed'; record['completion_event_id'] = event['id']
    _save(project, record)
    checkpoint('after_audit')
    _root(project).joinpath('active.json').unlink()
    sync_directory(_root(project))
    checkpoint('after_clear')


def reconcile(root: Path, *, scope: str, actor: str) -> dict:
    from .safety import operator_only
    from .worker import worker_lock
    from .operational import _append_maintenance, _maintenance_log_report
    operator_only()
    project = Project(root)
    with worker_lock(project), project.lock(maintenance=True):
        report = inspect(project)
        if not report['pending']:
            return {'schema_version':1,'reconciled':False,'already_clear':True}
        if scope != report['reconciliation_scope']:
            raise OrchestratorError('maintenance reconciliation scope changed')
        if not report.get('valid') or not report['reconcilable']:
            raise OrchestratorError('mixed/incomplete maintenance state; explicit verified recovery restore required')
        if not _maintenance_log_report(project)['integrity_ok']:
            raise OrchestratorError('maintenance audit is inconsistent; explicit recovery restore required')
        record = _read(project)
        event = _append_maintenance(project, action=record['action'], actor=actor, scope=scope,
                    details={'operation_id':record['operation_id'],'outcome':'reconciled',
                             'before_matches':report['before_matches'],'after_matches':report['after_matches'],
                             'additional_deletions':False,'automatic_replay':False})
        finish(project, record, event)
        return {'schema_version':1,'reconciled':True,'maintenance_event':event,'automatic_replay':False}


def sync_tree(root: Path) -> None:
    """Persist staged recovery material and directory entries before mutation."""
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise OrchestratorError('symlink in maintenance recovery material')
        if path.is_file():
            with path.open('rb') as stream:
                os.fsync(stream.fileno())
    for path in sorted((p for p in root.rglob('*') if p.is_dir()), reverse=True):
        sync_directory(path)
    sync_directory(root)
