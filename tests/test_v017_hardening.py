"""Release-candidate regressions derived from the retained design audit."""
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from ai_orchestrator.models import OrchestratorError, TaskSpec, TaskState, EvidenceRef
from ai_orchestrator.contracts import IntakeState
from ai_orchestrator.project import Project
from ai_orchestrator.store import Store
from ai_orchestrator.jobs import JobQueue
from ai_orchestrator.operational import diagnose_runtime, retention_plan, apply_retention
from ai_orchestrator.service import ApplicationService
from ai_orchestrator import learning
from conftest import spec


def cutoff():
    return (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()


def test_cancel_is_idempotent_visible_and_rejects_direct_approval(engine):
    e, reasoning, engineering = engine
    state = e.create(spec('cancel-rc'))
    state = e.run(state.spec.id)
    e.store.request_cancel(state.spec.id)
    count = e.store.event_count()
    e.store.request_cancel(state.spec.id)
    assert e.store.event_count() == count
    view = ApplicationService.task_view(e, state.spec.id)
    assert view['cancellation']['requested']
    assert not view['cancellation']['terminal']
    assert 'approval_scope' not in view
    with pytest.raises(OrchestratorError, match='cancel'):
        e.approve(state.spec.id, e.approval_scope(state), 'operator')
    assert len(reasoning.requests) == 1 and not engineering.requests


def test_shared_artifact_conflict_blocks_diagnosis_and_cleanup(workspace):
    project = Project(workspace)
    store = Store(project)
    state = TaskState(spec=spec('shared-rc', risk='T0'), profile_digest=project.load()[1])
    artifact = store.artifact(state, 'fixture', {'value': 1})
    store.save(state, 'fixture.created', create=True)
    intake = IntakeState(id='I-shared', task_id='shared-intake', request='test',
                         profile_digest=project.load()[1], workspace_snapshot=project.snapshot(),
                         status='failed', artifact=artifact.model_copy(update={'sha256': '0'*64}))
    store.save_intake(intake, 'fixture.intake', create=True)
    store.close()
    report = diagnose_runtime(workspace)['runtime:state']
    assert not report['integrity_ok']
    assert report['reference_conflicts']
    with pytest.raises(OrchestratorError):
        retention_plan(workspace, cutoff=cutoff())


def test_nested_accepted_evidence_is_a_root(workspace):
    project = Project(workspace)
    store = Store(project)
    artifact = store.write_artifact('historical-owner', 1, 'fixture', {'value': 1})
    store.close()
    metadata = dict(proposal_id='P-nested', canonical_key='nested-root', polarity='positive', supersedes=[],
                    evidence_refs=[EvidenceRef(source='artifact', id=artifact.id, sha256=artifact.sha256,
                                              kind=artifact.kind, owner_id=artifact.owner_id).model_dump()])
    path = workspace / '.orchestrator/knowledge/accepted/nested/P-nested.md'
    path.parent.mkdir()
    path.write_text(learning.LEARNING_METADATA_PREFIX+json.dumps(metadata)+learning.LEARNING_METADATA_SUFFIX+'\n# test\n')
    plan = retention_plan(workspace, cutoff=cutoff())
    assert artifact.path not in plan['orphan_artifacts']
    assert plan['protected_evidence_ids'] >= 1


def test_retired_request_never_becomes_new_job(workspace):
    project = Project(workspace)
    queue = JobQueue(project)
    args = {'request': 'test', 'advisory': True}
    job = queue.enqueue('ask', args, 'req-retired', project.load()[1], project.snapshot())
    claimed = queue.claim()
    claimed.status = 'succeeded'
    queue.finish(claimed)
    queue.close()
    plan = retention_plan(workspace, cutoff=cutoff())
    apply_retention(workspace, cutoff=plan['cutoff'], scope=plan['scope'], actor='operator')
    queue = JobQueue(project)
    try:
        with pytest.raises(OrchestratorError, match='request_retired'):
            queue.enqueue('ask', args, 'req-retired', project.load()[1], project.snapshot())
        assert queue.db.execute('select count(*) from jobs').fetchone()[0] == 0
        assert queue.db.execute('select count(*) from request_receipts').fetchone()[0] == 1
    finally:
        queue.close()


def test_idle_finalization_is_atomic_and_has_no_provider_or_file_effect(engine, monkeypatch):
    from ai_orchestrator.cancellation import view, finalize
    e, reasoning, engineering = engine
    state = e.create(spec('finalize-idle'))
    e.store.request_cancel(state.spec.id)
    before = e.project.manifest()
    current = view(e.project, state.spec.id)
    assert current['finalization_eligible'], current
    with pytest.raises(OrchestratorError, match='scope changed'):
        finalize(e.project.root, state.spec.id, scope='0'*64, actor='operator')
    original_event = Store._event
    def fail(self, task_id, kind, payload):
        if kind == 'task.cancelled': raise RuntimeError('transaction injection')
        original_event(self, task_id, kind, payload)
    monkeypatch.setattr(Store, '_event', fail)
    count = e.store.event_count()
    with pytest.raises(RuntimeError, match='transaction injection'):
        finalize(e.project.root, state.spec.id, scope=current['finalization_scope'], actor='operator')
    assert e.store.get(state.spec.id).status == 'ready'
    assert e.store.event_count() == count
    monkeypatch.setattr(Store, '_event', original_event)
    result = finalize(e.project.root, state.spec.id, scope=current['finalization_scope'], actor='operator')
    assert result['status'] == 'cancelled'
    assert e.store.get(state.spec.id).provider_permission_grants == {}
    assert state.spec.id not in e.store.active_task_ids()
    count = e.store.event_count()
    again = finalize(e.project.root, state.spec.id, scope=current['finalization_scope'], actor='operator')
    assert again['already_finalized'] and e.store.event_count() == count
    assert e.project.manifest() == before
    assert not reasoning.requests and not engineering.requests


@pytest.mark.parametrize('marker',['CLAUDECODE','AI_ORCHESTRATOR_INTERNAL_WORKER','CODEX_THREAD_ID'])
def test_finalization_refuses_marked_context(engine, monkeypatch, marker):
    from ai_orchestrator.cancellation import view, finalize
    e, _, _ = engine
    state = e.create(spec('marked-idle'))
    e.store.request_cancel(state.spec.id)
    current = view(e.project, state.spec.id)
    monkeypatch.setenv(marker,'1')
    with pytest.raises(OrchestratorError, match='operator-only'):
        finalize(e.project.root, state.spec.id, scope=current['finalization_scope'], actor='operator')
    assert e.store.get(state.spec.id).status == 'ready'


@pytest.mark.parametrize('blocker',['running','node','checkpoint','worktree','job'])
def test_finalization_refuses_uncertain_or_busy_targets(engine, blocker):
    from ai_orchestrator.cancellation import view
    from ai_orchestrator.models import WorkflowNodeState
    e, _, _ = engine
    state = e.create(spec('busy-idle'))
    e.store.request_cancel(state.spec.id)
    if blocker == 'running':
        state.status = 'running'; e.store.save(state, 'fixture.running')
    if blocker == 'node':
        state.workflow_nodes = {'test':WorkflowNodeState(status='running')}; e.store.save(state, 'fixture.node')
    if blocker == 'checkpoint':
        e.store.save(state, 'call.started', {'role':'implementer'})
    if blocker == 'worktree':
        (e.project.runtime/'worktrees'/state.spec.id/'attempt-1').mkdir(parents=True)
    if blocker == 'job':
        queue = JobQueue(e.project)
        queue.enqueue('run', {'task_id':state.spec.id}, 'busy-queue', e.profile_digest, e.project.snapshot())
        queue.close()
    result = view(e.project,state.spec.id)
    assert not result['finalization_eligible'], result
    assert result['blocked_by']


def test_legacy_and_identical_shared_references_are_compatible(workspace):
    project=Project(workspace);store=Store(project)
    state=TaskState(spec=spec('legacy-shared',risk='T0'),profile_digest=project.load()[1])
    artifact=store.artifact(state,'fixture',{'value':1}); store.save(state,'fixture',create=True)
    raw=artifact.model_dump();raw['schema_version']=1
    for key in ('id','created_at','owner_id'):raw.pop(key)
    from ai_orchestrator.models import Artifact
    intake=IntakeState(id='I-legacy-shared',task_id='future',request='test',profile_digest=project.load()[1],
                       workspace_snapshot=project.snapshot(),artifact=Artifact.model_validate(raw),status='failed')
    store.save_intake(intake,'fixture',create=True);store.close()
    assert diagnose_runtime(workspace)['runtime:state']['integrity_ok']


@pytest.mark.parametrize('action',['ask','run','explore','exploration_propose'])
def test_retired_receipt_actions_and_changed_arguments(workspace, action):
    from ai_orchestrator.receipts import RequestRetired
    project=Project(workspace);queue=JobQueue(project)
    args={'task_id':'x','request':'test'}
    job=queue.enqueue(action,args,'req-action',project.load()[1],project.snapshot())
    running=queue.claim();running.status='succeeded';queue.finish(running);queue.close()
    plan=retention_plan(workspace,cutoff=cutoff())
    apply_retention(workspace,cutoff=plan['cutoff'],scope=plan['scope'],actor='operator')
    queue=JobQueue(project)
    try:
        with pytest.raises(RequestRetired) as caught:
            queue.enqueue(action,args,'req-action',project.load()[1],project.snapshot())
        assert caught.value.details['original_job_id']==job.id
        assert not caught.value.details['automatic_replay']
        with pytest.raises(OrchestratorError,match='different arguments'):
            queue.enqueue(action,{'changed':True},'req-action',project.load()[1],project.snapshot())
    finally: queue.close()


def test_standalone_validator_check_has_no_task_state_reference(engine):
    e, reasoning, engineering=engine
    assert e.check_validator('check')['ok']
    assert not reasoning.requests and not engineering.requests


def test_fresh_intake_crosses_operator_start_after_cleanup(workspace):
    from ai_orchestrator.engine import Engine
    from ai_orchestrator.supervisor import Supervisor
    from test_v02_supervisor import IntakeAdapter
    providers={'claude':IntakeAdapter('anthropic'),'codex':IntakeAdapter('openai')}
    e=Engine(workspace,providers);e.trust('operator');s=Supervisor(e)
    intake=s.ask('A fresh bounded result',task_id='fresh-cleanup')
    before=s.scope(intake);artifact=intake.artifact
    orphan=e.store.write_artifact('orphan-owner',1,'fixture',{'value':'unreferenced'})
    plan=retention_plan(workspace,cutoff=cutoff())
    assert orphan.path in plan['orphan_artifacts'] and artifact.path not in plan['orphan_artifacts']
    applied=apply_retention(workspace,cutoff=plan['cutoff'],scope=plan['scope'],actor='operator')
    assert applied['orphan_artifacts_removed']==[orphan.path]
    assert s.scope(e.store.get_intake(intake.id))==before
    # Explicit operator entry, not a fabricated host confirmation. No provider is
    # called by start itself; the subprocess wire suite covers real gate messages.
    task=s.start(intake.id,before,'operator')
    assert task.intake_id==intake.id and len(providers['claude'].requests)==1
    e.close()


def test_frozen_context_keeps_evidence_after_current_markdown_is_removed(engine):
    from ai_orchestrator.models import ContextInfluence,ContextInfluenceEntry
    e,_,_=engine
    historical=e.store.write_artifact('historic',1,'review',{'value':'historical evidence'})
    state=e.create(spec('frozen-learning'))
    ref=EvidenceRef(source='artifact',id=historical.id,sha256=historical.sha256,owner_id=historical.owner_id,kind=historical.kind)
    state.context_influence=ContextInfluence(query_sha256='a'*64,budget_bytes=1024,selected_bytes=10,universe_items=1,excluded_items=0,
      entries=[ContextInfluenceEntry(path='.orchestrator/knowledge/accepted/removed.md',sha256='b'*64,bytes=10,kind='knowledge',score=1,evidence_refs=[ref])])
    e.store.save(state,'fixture.frozen_context')
    assert not (e.project.root/state.context_influence.entries[0].path).exists()
    plan=retention_plan(e.project.root,cutoff=cutoff())
    assert historical.path not in plan['orphan_artifacts']


def test_cancel_can_record_intent_while_another_controller_holds_project_lock(engine):
    import subprocess,sys
    e,_,_=engine;state=e.create(spec('cancel-during-provider'))
    # The child opens the existing Store while a cooperating controller holds the
    # project lock, matching a cancellation during a long-running provider call.
    code='from pathlib import Path; from ai_orchestrator.store import Store; from ai_orchestrator.project import Project; s=Store(Project(Path('+repr(str(e.project.root))+'))); s.request_cancel("cancel-during-provider");s.close()'
    with e.project.lock():
        child=subprocess.run([sys.executable,'-I','-c',code],capture_output=True,text=True,timeout=10)
        assert child.returncode==0,child.stderr
    assert e.store.cancelled(state.spec.id)
