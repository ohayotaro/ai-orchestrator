"""Candidate schema, wire, installation identity and historical hash contracts."""
from __future__ import annotations
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from ai_orchestrator import build_identity, contract_inventory, maintenance
from ai_orchestrator.cancellation import view
from ai_orchestrator.cli import main, parser
from ai_orchestrator.contracts import IntakeState
from ai_orchestrator.engine import Engine
from ai_orchestrator.human_gates import HumanGate, HumanGateBroker, GATE_TOOLS
from ai_orchestrator.jobs import JobQueue
from ai_orchestrator.models import Artifact, OrchestratorError, TaskState
from ai_orchestrator.persistence import decode_versioned_model_json, validate_database_version
from ai_orchestrator.project import Project, digest
from ai_orchestrator.service import ApplicationService, TOOLS
from ai_orchestrator.store import Store

GOLDEN=json.loads((Path(__file__).parent/'fixtures/rc/legacy_hashes.json').read_text())['cases']


def test_packaged_candidate_inventory_matches_exact_public_surface():
    expected=json.loads(contract_inventory.ASSET.read_text())
    assert contract_inventory.generate()==expected
    assert set(item['name'] for item in expected['mcp_tools'])==set(TOOLS)|set(GATE_TOOLS)
    assert expected['v1_release_declared'] is False
    assert {'cancel','maintenance inspect','maintenance reconcile','identity','contracts'} <= {item['name'] for item in expected['cli_commands']}
    assert not {'cancel_finalize','maintenance_reconcile','restore','cleanup'} & set(TOOLS)
    assert expected['persistence']['databases']['jobs']['write_version']==2


@pytest.mark.parametrize('case',GOLDEN,ids=lambda x:x['contract']+'-'+str(x['input']['schema_version']))
def test_supported_legacy_reader_shapes_keep_baseline_hashes(case):
    models={'task_state':TaskState,'intake_state':IntakeState,'artifact':Artifact}
    raw=json.dumps(case['input'])
    state=decode_versioned_model_json(raw,rule_key=case['contract'],model=models[case['contract']])
    assert digest(state.model_dump())==case['canonical_sha256']
    if case['contract']=='task_state' and state.schema_version<9:
        assert 'exploration' not in state.model_dump()
    if case['contract']=='intake_state' and state.schema_version<6:
        assert 'exploration' not in state.model_dump()
    assert raw==json.dumps(case['input'])


@pytest.mark.parametrize('bad',[0,99,True,'1'])
def test_receipt_reader_rejects_unknown_or_coerced_version(bad):
    from ai_orchestrator.receipts import decode
    raw=dict(schema_version=bad,request_id='req',job_id='J-test',fingerprint='a'*64,action='ask',outcome='succeeded',retired_at=1)
    with pytest.raises(OrchestratorError):decode(('req','J-test','a'*64,json.dumps(raw)))


def test_jobs_v2_missing_receipts_is_not_silently_repaired(workspace):
    p=Project(workspace);q=JobQueue(p)
    with q.db:q.db.execute('DROP TABLE request_receipts')
    q.close();before=(p.runtime/'jobs.sqlite3').read_bytes()
    with pytest.raises(OrchestratorError,match='schema is incomplete|missing request_receipts'):JobQueue(p)
    assert (p.runtime/'jobs.sqlite3').read_bytes()==before
    with pytest.raises(OrchestratorError):validate_database_version('legacy jobs',2,(0,1))


def test_loaded_source_drift_blocks_before_provider_loading(workspace,monkeypatch):
    import ai_orchestrator.engine as module
    monkeypatch.setattr(build_identity,'source_digest',lambda:'0'*64)
    monkeypatch.setattr(module,'load_provider_registry',lambda *a,**k:pytest.fail('provider plugin loaded'))
    with pytest.raises(OrchestratorError,match='loaded_build_mismatch'):Engine(workspace)
    result=ApplicationService(workspace).invoke('inspect_project',{})
    assert result['installation']['matches'] is False


def test_expected_worker_build_mismatch_blocks_claim(workspace,monkeypatch):
    from ai_orchestrator.worker import process_one
    q=JobQueue(Project(workspace));p=q.project
    job=q.enqueue('ask',{'request':'fixture'},'build-mismatch',p.load()[1],p.snapshot())
    monkeypatch.setenv('AI_ORCHESTRATOR_EXPECTED_BUILD','0'*64)
    with pytest.raises(OrchestratorError,match='loaded_build_mismatch'):process_one(q)
    assert q.get(job.id).status=='queued'
    q.close()


def test_identity_is_provider_free_and_explicit_skill_drift_is_read_only(workspace,tmp_path,capsys):
    copied=tmp_path/'SKILL.md';copied.write_text('older installed skill\n')
    before=copied.read_bytes()
    assert main(['--project',str(workspace),'identity','--skill',str(copied)])==0
    result=json.loads(capsys.readouterr().out)
    assert result['matches'] and result['host_skills_checked']
    assert result['host_skills'][0]['matches_packaged'] is False
    assert copied.read_bytes()==before
    assert main(['--project',str(workspace),'contracts'])==0
    assert json.loads(capsys.readouterr().out)['inventory_digest']


@pytest.mark.parametrize('kind',['start','execution','acceptance','profile_change','profile_change_set','binding_cleanup','provider_permission'])
def test_no_first_gate_keeps_one_required_strict_choice(kind):
    gate=HumanGate(id='G-fixture',session='session',local_uid=os.getuid(),actor='operator',client={},
                   request_id='request',kind=kind,subject='task',scope='s',kernel_scope='k',preview={},created_at=1,expires_at=2)
    form=HumanGateBroker.form(gate);schema=form['requestedSchema'];field=schema['properties']['decision']
    assert set(schema['properties'])=={'decision'} and schema['required']==['decision']
    assert field['enum']==['no','yes'] and field['type']=='string'
    assert 'default' not in field and kind in field['title']


def test_maintenance_format_symlink_is_refused_without_following_authority(workspace,tmp_path):
    p=Project(workspace);root=p.runtime/'maintenance-journal';root.mkdir(parents=True)
    target=tmp_path/'foreign.json';target.write_text(json.dumps(maintenance.FORMAT));(root/'format.json').symlink_to(target)
    with pytest.raises(OrchestratorError,match='maintenance_pending'):Store(p)
    assert target.read_text()==json.dumps(maintenance.FORMAT)
