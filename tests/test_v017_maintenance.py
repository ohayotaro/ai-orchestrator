"""Actual subprocess SIGKILL tests on disposable fixtures, never owner runtime."""
from __future__ import annotations
import json
import os
import signal
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from ai_orchestrator import maintenance, operational
from ai_orchestrator.engine import Engine
from ai_orchestrator.jobs import JobQueue
from ai_orchestrator.human_gates import GateStore
from ai_orchestrator.models import OrchestratorError
from ai_orchestrator.project import Project
from ai_orchestrator.store import Store
from ai_orchestrator.receipts import RequestRetired
from test_v017_hardening import cutoff


def prepare(workspace):
    project=Project(workspace)
    store=Store(project);store.close()
    queue=JobQueue(project)
    job=queue.enqueue('ask',{'request':'fixture','advisory':True},'maintenance-job',project.load()[1],project.snapshot())
    claimed=queue.claim();claimed.status='succeeded';queue.finish(claimed);queue.close()
    return project, job


def inject(workspace, action, phase, archive=None, scope=None, cutoff_value=None, rollback=False):
    code='''
import os, signal
from pathlib import Path
from ai_orchestrator import maintenance, operational
phase = PHASE
maintenance.checkpoint = lambda value: os.kill(os.getpid(), signal.SIGKILL) if value == phase else None
if ROLLBACK:
    operational._structural_runtime_ok = lambda project: (False,{})
root = Path(ROOT)
if ACTION == 'restore':
    operational.restore_backup(root,Path(ARCHIVE),scope=SCOPE,actor='operator',replace=True,acknowledge_authority_restore=True)
else:
    operational.apply_retention(root,cutoff=CUTOFF,scope=SCOPE,actor='operator')
'''
    for key,value in {'PHASE':phase,'ROLLBACK':rollback,'ROOT':str(workspace),'ACTION':action,
                      'ARCHIVE':str(archive),'SCOPE':scope,'CUTOFF':cutoff_value}.items():
        code=code.replace(key,repr(value))
    child=subprocess.run([sys.executable,'-I','-c',code],capture_output=True,text=True,timeout=30)
    assert child.returncode == -signal.SIGKILL, child.stderr


@pytest.mark.parametrize('phase',[
    'after_intent','before_mutation','after_file_remove','after_file_replace',
    'after_db_commit','after_data','before_audit','after_audit','after_clear',
])
def test_restore_process_loss_is_coherent_or_blocked(workspace, tmp_path_factory, phase):
    project,_=prepare(workspace)
    archive=tmp_path_factory.mktemp('archives')/'full.zip'
    backup=operational.create_backup(workspace,archive,mode='full')
    config=workspace/'.orchestrator/config.yaml'
    raw=yaml.safe_load(config.read_text());raw['name']='deliberate-drift';config.write_text(yaml.safe_dump(raw))
    inject(workspace,'restore',phase,archive=archive,scope=backup['scope'])
    state=maintenance.inspect(project)
    if phase == 'after_clear':
        assert not state['pending']
        assert project.load()[1]==backup['manifest']['source_profile_digest']
        return
    assert state['pending'] and state['valid'],state
    for constructor in (lambda:Store(project),lambda:JobQueue(project),lambda:GateStore(project),lambda:Engine(workspace)):
        with pytest.raises(OrchestratorError,match='maintenance_pending'):
            constructor()
    report=operational.diagnose_runtime(workspace)
    assert report['runtime:journal']['pending']
    assert operational.inspect_backup(archive)['verified']
    if state['reconcilable']:
        before=maintenance.snapshot(project,'full')
        with pytest.raises(OrchestratorError,match='scope changed'):
            maintenance.reconcile(workspace,scope='0'*64,actor='operator')
        result=maintenance.reconcile(workspace,scope=state['reconciliation_scope'],actor='operator')
        assert result['reconciled']
        assert maintenance.snapshot(project,'full') == before
        assert not maintenance.inspect(project)['pending']
    else:
        with pytest.raises(OrchestratorError,match='mixed/incomplete'):
            maintenance.reconcile(workspace,scope=state['reconciliation_scope'],actor='operator')
        result=operational.restore_backup(workspace,archive,scope=backup['scope'],actor='operator',replace=True,
                   acknowledge_authority_restore=True,acknowledge_unreadable_current_state=True,
                   acknowledge_incomplete_operation=state['reconciliation_scope'])
        assert result['restored']
        assert not maintenance.inspect(project)['pending']
        # The predecessor marker and recovery material were retained, not erased.
        assert list((project.runtime/'maintenance-journal/operations').glob('*/superseded-active.json'))


@pytest.mark.parametrize('phase',['after_intent','before_mutation','after_worktree_delete','after_artifact_delete',
                                 'after_db_commit','after_data','before_audit','after_audit','after_clear'])
def test_cleanup_process_loss_never_replays_or_conceals_partial_state(workspace, phase):
    project,job=prepare(workspace)
    orphan=project.runtime/'orphan'/('0-fixture-'+'b'*32+'.json')
    orphan.parent.mkdir();orphan.write_text('{"orphan":true}\n')
    stale=project.runtime/'worktrees'/'old-task';stale.mkdir(parents=True);(stale/'payload').write_text('stale')
    plan=operational.retention_plan(workspace,cutoff=cutoff())
    inject(workspace,'cleanup',phase,scope=plan['scope'],cutoff_value=plan['cutoff'])
    state=maintenance.inspect(project)
    if phase=='after_clear':
        assert not state['pending']
    else:
        assert state['pending'],state
        with pytest.raises(OrchestratorError,match='maintenance_pending'):Engine(workspace)
        if state['reconcilable']:
            before=maintenance.snapshot(project,'runtime')
            maintenance.reconcile(workspace,scope=state['reconciliation_scope'],actor='operator')
            assert maintenance.snapshot(project,'runtime')==before
    # Whichever side of the SQLite commit the kill hit, request identity survives.
    conn=sqlite3.connect(project.runtime/'jobs.sqlite3')
    try:
        live=conn.execute('SELECT id FROM jobs WHERE request_id=?',(job.request_id,)).fetchone()
        receipt=conn.execute('SELECT job_id FROM request_receipts WHERE request_id=?',(job.request_id,)).fetchone()
        assert live or receipt
    finally:conn.close()


@pytest.mark.parametrize('phase',['before_rollback','after_rollback'])
def test_restore_rollback_interruption_remains_marked(workspace,tmp_path_factory,phase):
    project,_=prepare(workspace)
    archive=tmp_path_factory.mktemp('rollback-archive')/'full.zip'
    backup=operational.create_backup(workspace,archive,mode='full')
    config=workspace/'.orchestrator/config.yaml';raw=yaml.safe_load(config.read_text());raw['name']='drift';config.write_text(yaml.safe_dump(raw))
    inject(workspace,'restore',phase,archive=archive,scope=backup['scope'],rollback=True)
    state=maintenance.inspect(project)
    assert state['pending']
    assert state['before_matches'] is (phase=='after_rollback')


def test_completion_audit_failure_does_not_report_success(workspace,monkeypatch):
    project,_=prepare(workspace)
    plan=operational.retention_plan(workspace,cutoff=cutoff())
    monkeypatch.setattr(operational,'_append_maintenance',lambda *a,**k:(_ for _ in ()).throw(OSError('audit failed')))
    with pytest.raises(OSError,match='audit failed'):
        operational.apply_retention(workspace,cutoff=plan['cutoff'],scope=plan['scope'],actor='operator')
    assert maintenance.inspect(project)['pending']
    with pytest.raises(OrchestratorError,match='maintenance_pending'):
        JobQueue(project)


def test_invalid_journal_blocks_before_provider_plugin_loading(workspace,monkeypatch):
    project,_=prepare(workspace)
    plan=operational.retention_plan(workspace,cutoff=cutoff())
    maintenance.begin(project,action='cleanup',scope=plan['scope'],actor='operator',mode='runtime')
    path=project.runtime/'maintenance-journal/active.json';path.write_text('{broken')
    import ai_orchestrator.engine as module
    monkeypatch.setattr(module,'load_provider_registry',lambda *a,**k:pytest.fail('plugin loader must not run'))
    with pytest.raises(OrchestratorError,match='maintenance_pending'):Engine(workspace)
    assert not maintenance.inspect(project)['valid']


def test_live_connection_refuses_replaced_database(workspace,tmp_path_factory):
    project,_=prepare(workspace)
    archive=tmp_path_factory.mktemp('replaced-archive')/'full.zip'
    backup=operational.create_backup(workspace,archive,mode='full')
    store=Store(project)
    operational.restore_backup(workspace,archive,scope=backup['scope'],actor='operator',replace=True,acknowledge_authority_restore=True)
    try:
        with pytest.raises(OrchestratorError,match='storage_replaced'):
            store.trusted(project.load()[1])
    finally:store.close()


def test_restore_keeps_receipts_absent_from_old_backup(workspace,tmp_path_factory):
    project,_=prepare(workspace)
    archive=tmp_path_factory.mktemp('receipt-archive')/'full.zip'
    backup=operational.create_backup(workspace,archive,mode='full')
    queue=JobQueue(project)
    args={'request':'after backup'}
    job=queue.enqueue('ask',args,'after-backup',project.load()[1],project.snapshot())
    claimed=queue.claim();claimed.status='succeeded';queue.finish(claimed);queue.close()
    plan=operational.retention_plan(workspace,cutoff=cutoff())
    operational.apply_retention(workspace,cutoff=plan['cutoff'],scope=plan['scope'],actor='operator')
    operational.restore_backup(workspace,archive,scope=backup['scope'],actor='operator',replace=True,acknowledge_authority_restore=True)
    queue=JobQueue(project)
    try:
        with pytest.raises(RequestRetired):queue.enqueue('ask',args,'after-backup',project.load()[1],project.snapshot())
    finally:queue.close()


def test_retirement_receipt_and_payload_deletion_are_one_transaction(workspace):
    project,job=prepare(workspace)
    code=f'''
import os,signal,sqlite3
from ai_orchestrator import receipts
conn=sqlite3.connect({str(project.runtime/'jobs.sqlite3')!r})
receipts.checkpoint=lambda phase: os.kill(os.getpid(),signal.SIGKILL)
with conn:
    conn.execute('BEGIN IMMEDIATE')
    receipts.retire(conn,[{job.id!r}])
'''
    child=subprocess.run([sys.executable,'-I','-c',code],capture_output=True,timeout=15)
    assert child.returncode==-signal.SIGKILL
    queue=JobQueue(project)
    try:
        assert queue.get(job.id).status=='succeeded'
        assert queue.db.execute('SELECT count(*) FROM request_receipts').fetchone()[0]==0
    finally:queue.close()


def test_restore_keeps_terminal_task_historical_grant_metadata(engine,tmp_path):
    from ai_orchestrator.models import ProviderPermissionGrant
    from conftest import spec
    e,_,_=engine
    task=e.create(spec('terminal-history'))
    task.provider_permission_grants={'agy_dangerously_skip_permissions':ProviderPermissionGrant(
        permission='agy_dangerously_skip_permissions',scope='a'*64,attempt=1,profile_digest=e.profile_digest,
        execution_scope='b'*64,workspace_snapshot=e.project.snapshot(),nodes=['implement'],actor='operator')}
    task.status='succeeded';task.phase='accept';e.store.save(task,'fixture.terminal')
    raw=e.store.get(task.spec.id).model_dump_json()
    backup=operational.create_backup(e.project.root,tmp_path/'history.zip',mode='full')
    operational.restore_backup(e.project.root,tmp_path/'history.zip',scope=backup['scope'],actor='operator',replace=True,
                               acknowledge_authority_restore=True)
    s=Store(e.project)
    try:assert s.get(task.spec.id).model_dump_json()==raw
    finally:s.close()


def test_pending_archive_never_queues_work_on_fresh_restore(workspace,tmp_path):
    project,_=prepare(workspace)
    queue=JobQueue(project)
    pending=queue.enqueue('ask',{'request':'not dispatched'},'pending-source',project.load()[1],project.snapshot())
    queue.close()
    from ai_orchestrator.human_gates import HumanGate
    gate=HumanGate(id='G-pending',session='old-session',local_uid=os.getuid(),actor='operator',client={},
                   request_id='pending-gate',kind='start',subject='I-unused',scope='s',kernel_scope='k',
                   preview={},created_at=1,expires_at=9999999999)
    gates=GateStore(project);gates.create(gate);gates.close()
    backup=operational.create_backup(workspace,tmp_path/'pending.zip',mode='full')
    fresh=tmp_path/'fresh';fresh.mkdir()
    restored=operational.restore_backup(fresh,tmp_path/'pending.zip',scope=backup['scope'],actor='operator',replace=True,
                                        acknowledge_authority_restore=True)
    assert restored['request_receipt_coverage'].startswith('archive-only')
    q=JobQueue(Project(fresh))
    assert q.claim() is None and q.get(pending.id).status=='interrupted'
    with pytest.raises(RequestRetired):q.existing(pending.request_id,'ask',pending.arguments)
    q.close();g=GateStore(Project(fresh));assert g.get(gate.id).status=='cancelled';g.close()


def test_finalization_sigkill_rolls_back_status_and_event_atomically(engine):
    from ai_orchestrator.cancellation import view
    from conftest import spec
    e,_,_=engine;state=e.create(spec('finalize-crash'));e.store.request_cancel(state.spec.id)
    scope=view(e.project,state.spec.id)['finalization_scope'];before=e.store.event_count()
    code='''
import os,signal
from pathlib import Path
from ai_orchestrator.store import Store
from ai_orchestrator.cancellation import finalize
original=Store._event
def kill(self,task_id,kind,payload):
    if kind=='task.cancelled':os.kill(os.getpid(),signal.SIGKILL)
    return original(self,task_id,kind,payload)
Store._event=kill
finalize(Path(ROOT),'finalize-crash',scope=SCOPE,actor='operator')
'''.replace('ROOT',repr(str(e.project.root))).replace('SCOPE',repr(scope))
    child=subprocess.run([sys.executable,'-I','-c',code],capture_output=True,text=True,timeout=20)
    assert child.returncode==-signal.SIGKILL,child.stderr
    assert e.store.get(state.spec.id).status=='ready' and e.store.cancelled(state.spec.id)
    assert e.store.event_count()==before
