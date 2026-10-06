"""Cancellation intent is not terminal state or proof of remote cancellation."""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path
from typing import Literal
from pydantic import Field
from .models import Contract, OrchestratorError, TaskState, identifier
from .persistence import decode_versioned_model_json
from .project import Project, confined, digest

TERMINAL = {'succeeded', 'failed', 'blocked', 'cancelled', 'abandoned'}
IDLE = {'ready', 'awaiting_approval', 'awaiting_acceptance'}


class CancellationView(Contract):
    schema_version: Literal[1] = 1
    requested: bool
    terminal: bool
    finalization_eligible: bool
    blocked_by: list[str]
    finalization_scope: str | None = Field(pattern=r'^[a-f0-9]{64}$')
    automatic_replay: Literal[False] = False
    remote_cancellation_attested: Literal[False] = False


def _contains(value, targets):
    if isinstance(value, dict):
        return any(_contains(item, targets) for item in value.values())
    if isinstance(value, list):
        return any(_contains(item, targets) for item in value)
    return isinstance(value, str) and value in targets


def view(project: Project, task_id: str) -> dict:
    """Read only: scope is advisory until re-evaluated under exclusive locks."""
    from .operational import _readonly_connection, _quick_database_report
    from .persistence import RUNTIME_DB_READABLE_VERSIONS, JOB_DB_READABLE_VERSIONS, HUMAN_GATE_DB_READABLE_VERSIONS
    identifier(task_id)
    path = confined(project.root, '.orchestrator/runtime/state.sqlite3')
    report = _quick_database_report(path, 'runtime', RUNTIME_DB_READABLE_VERSIONS)
    if not report['present'] or not report['integrity_ok']:
        raise OrchestratorError('cancellation view requires readable runtime state')
    db = _readonly_connection(path)
    try:
        row = db.execute('SELECT data,cancel_requested FROM tasks WHERE id=?', (task_id,)).fetchone()
        if row is None:
            raise OrchestratorError(f'unknown task: {task_id}')
        state = decode_versioned_model_json(row[0], rule_key='task_state', model=TaskState)
        if state.spec.id != task_id:
            raise OrchestratorError('task row identity mismatch')
        events = db.execute('SELECT sequence,kind,payload FROM events WHERE task_id=? ORDER BY sequence', (task_id,)).fetchall()
        approvals = db.execute('SELECT scope,actor,created_at FROM approvals WHERE task_id=? ORDER BY scope', (task_id,)).fetchall()
    finally:
        db.close()
    blocked = []
    if not row[1]: blocked.append('cancellation_not_requested')
    if state.status not in IDLE: blocked.append('task_not_idle')
    if any(node.status == 'running' for node in (state.workflow_nodes or {}).values()):
        blocked.append('running_workflow_node')
    outstanding = set()
    for seq, kind, raw in events:
        data = json.loads(raw)
        key = data.get('node') or data.get('role') or '*'
        if kind == 'call.started': outstanding.add(('call', key))
        elif kind == 'call.finished': outstanding.discard(('call', key))
        elif kind in ('workflow.parallel.preparing', 'workflow.guarded_write.preparing'):
            outstanding.add(('batch', kind.rsplit('.', 1)[0]))
        elif kind in ('workflow.parallel.finished', 'workflow.guarded_write.finished'):
            outstanding.discard(('batch', kind.rsplit('.', 1)[0]))
        elif kind.startswith('recovery.'):
            # A completed conservative recovery invalidated prior reservations.
            outstanding.clear()
    if outstanding: blocked.append('unresolved_effect_checkpoint')
    worktrees = confined(project.root, f'.orchestrator/runtime/worktrees/{task_id}')
    if worktrees.exists(): blocked.append('task_owned_worktree')
    observations = {}
    targets = {task_id, state.intake_id} - {None}
    for label, filename, versions, table, statuses in (
        ('jobs', 'jobs.sqlite3', JOB_DB_READABLE_VERSIONS, 'jobs', ('queued','running')),
        ('gates', 'gates.sqlite3', HUMAN_GATE_DB_READABLE_VERSIONS, 'gates', ('pending','applying','uncertain')),
    ):
        other = confined(project.root, '.orchestrator/runtime/' + filename)
        check = _quick_database_report(other, label, versions)
        if not check['integrity_ok']:
            blocked.append(label + '_unreadable'); continue
        if not other.exists():
            observations[label] = []; continue
        conn = _readonly_connection(other)
        try:
            relevant = []
            for rid, status, raw in conn.execute(f'SELECT id,status,data FROM {table}'):
                data = json.loads(raw)
                if data.get('id') != rid or data.get('status') != status:
                    raise OrchestratorError(label + ' columns disagree with payload')
                if _contains(data, targets):
                    relevant.append([rid, status, digest(data)])
                    if status in statuses: blocked.append(label + ':' + rid)
            observations[label] = sorted(relevant)
        except (ValueError, sqlite3.Error, OrchestratorError):
            blocked.append(label + '_unreadable')
        finally:
            conn.close()
    # No plugin loading, validators or worktree Git commands are needed here.
    from .evidence import inventory
    inv = inventory(project)
    if inv['errors'] or inv['conflicts'] or inv['missing'] or inv['corrupt']:
        blocked.append('evidence_integrity')
    scope = digest({'schema_version':1, 'task_id':task_id, 'state':state.model_dump(),
                    'requested':bool(row[1]), 'events':events, 'approvals':approvals,
                    'observations':observations, 'evidence':inv['fingerprint'],
                    'blocked_by': sorted(set(blocked))})
    return {'schema_version':1, 'requested':bool(row[1]), 'terminal':state.status in TERMINAL,
            'finalization_eligible':not blocked, 'blocked_by': sorted(set(blocked)),
            'finalization_scope':scope if not blocked else None,
            'automatic_replay':False, 'remote_cancellation_attested':False}


def finalize(root: Path, task_id: str, *, scope: str, actor: str) -> dict:
    from .safety import operator_only
    from .worker import worker_lock
    from .store import Store
    operator_only()
    if not actor.strip() or len(actor) > 256 or any(ord(c) < 32 for c in actor):
        raise OrchestratorError('bounded printable operator actor required')
    if len(scope) != 64 or any(c not in '0123456789abcdef' for c in scope):
        raise OrchestratorError('exact finalization scope required')
    project = Project(root)
    with worker_lock(project), project.lock():
        store = Store(project)
        try:
            state = store.get(task_id)
            if state.status == 'cancelled' and store.cancelled(task_id):
                return {'task_id':task_id, 'status':'cancelled', 'already_finalized':True,
                        'automatic_replay':False}
            current = view(project, task_id)
            if not current['finalization_eligible']:
                raise OrchestratorError('cancellation finalization blocked: ' + ', '.join(current['blocked_by']))
            if scope != current['finalization_scope']:
                raise OrchestratorError('cancellation finalization scope changed; inspect again')
            state.status = 'cancelled'
            state.provider_permission_grants = {}
            state.error = 'Cancelled by explicit operator finalization; no execution or rollback.'
            # Store.save commits the state, approval revocation and event together.
            store.save(state, 'task.cancelled', {'actor':actor, 'scope':scope, 'finalized':True,
                       'workspace_rollback':False, 'automatic_replay':False}, clear_approvals=True)
            return {'task_id':task_id, 'status':state.status, 'already_finalized':False,
                    'automatic_replay':False, 'cancellation':view(project, task_id)}
        finally:
            store.close()
