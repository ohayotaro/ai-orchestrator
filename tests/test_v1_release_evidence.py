"""Synthetic offline evidence tests. No fixture is actual owner/live evidence."""
from __future__ import annotations

import copy
import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest
from pydantic import ValidationError
from ai_orchestrator import release_evidence as e


def write(root, name, data):
    path=root/name; path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(data if isinstance(data,bytes) else json.dumps(data,sort_keys=True).encode())
    return e.FileEvidence(path=name,sha256=e.sha256_file(path))


@pytest.fixture
def evidence_bundle(tmp_path):
    """Self-contained fake records to test verification, never real qualification."""
    root=tmp_path
    payload={'__init__.py':b'__version__ = "1.0.0"\n',
             'assets/contracts.json':b'{"schema_version":2,"canonicalizer":"json-schema-positions-v2"}',
             'assets/SKILL.md':b'Test fixture only. Not a deployed skill.\n'}
    wheel=root/'candidate.whl'
    with zipfile.ZipFile(wheel,'w') as out:
        for name,data in payload.items():out.writestr('ai_orchestrator/'+name,data)
        out.writestr('ai_orchestrator_kernel-1.0.0.dist-info/METADATA',
                     'Name: ai-orchestrator-kernel\nVersion: 1.0.0\n')
    sdist=root/'candidate.tar.gz'
    with tarfile.open(sdist,'w:gz') as out:
        for name,data in payload.items():
            item=tarfile.TarInfo('fixture/src/ai_orchestrator/'+name);item.size=len(data)
            out.addfile(item,io.BytesIO(data))
    artifact=e.ArtifactIdentity(**e.payload_identity(payload),source_commit='a'*40,source_tree='b'*40,
                               wheel_sha256=e.sha256_file(wheel),sdist_sha256=e.sha256_file(sdist))
    supported=e.AxisSupport(status='supported',operations=list(e.PROBE_REPETITIONS))
    host=e.Host(name='Claude Code',version='synthetic-fixture',protocol='2025-06-18',form_supported=True,
                skill_sha256=artifact.packaged_skill_sha256,transport=supported)
    roles=[e.ProviderRole(role=role,adapter=adapter,cli_version='synthetic-fixture',model_mode='adapter_default',
                          model=None,effort_mode='adapter_default',effort=None,execution=supported)
           for role,adapter in [('reasoning/planning/review','claude'),('implementation','codex')]]
    deployment=e.Deployment(id='synthetic-test-only',artifact=artifact,host=host,os='macOS synthetic',python='3.13.5',
                            providers=roles,native_permission_assumptions='Synthetic tests only; no actual permission or host.')
    references=[]
    for kind,n in e.PROBE_REPETITIONS.items():
        for index in range(n):
            ident=f'{kind}-{index}'
            yes=kind in ('fresh_write','explicit_yes'); no=kind in ('start_refusal','explicit_no')
            probe=e.ProbeRecord(id=ident,kind=kind,result='PASS',source='owner-live',artifact=artifact,
                 configuration_sha256=deployment.configuration_digest(),fixture_id=ident,gate_ids=[ident+'-'+str(n) for n in range(3)],
                 evidence_date='2026-10-06T05:00:00Z',observer='synthetic-test-only',notes=['Not actual live evidence'],
                 provider_calls_delta=int(kind=='fresh_write'),validator_calls_delta=int(kind=='fresh_write'),
                 file_changes_delta=int(kind=='fresh_write'),new_gate_rows=0,authorization_granted=yes,
                 task_status='succeeded' if kind=='fresh_write' else 'cancelled' if kind=='cancel_finalize' else None,
                 validator_passed=True if kind=='fresh_write' else None,
                 selected_decision='yes' if yes else 'no' if no else 'cancel' if kind=='cancel' else 'untouched' if kind=='untouched_submission' else 'not-applicable',
                 wire_decision='yes' if yes else 'no' if no else 'cancel' if kind=='cancel' else 'absent')
            references.append(write(root,'probes/'+ident+'.json',probe.model_dump()))
    deployment.probes=references[:]
    matrix=e.SupportMatrix(kernel_version='1.0.0',historical_evidence=[],deployments=[deployment])
    matrix_ref=write(root,'matrix.json',matrix.model_dump()); references.append(matrix_ref)
    deps=write(root,'dependencies.txt',b'fixture-only==0\n');references.append(deps)
    junit=write(root,'tests.xml',b'<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="synthetic"/></testsuite></testsuites>');references.append(junit)
    run={'id':1,'head_sha':'a'*40,'status':'completed','conclusion':'success'}
    jobs=[dict(run_id=1,head_sha='a'*40,name=name,status='completed',conclusion='success')
          for name in ['build-distribution',*['test ('+n+')' for n in e.REQUIRED_LANES]]]
    completion=write(root,'ci-completion.json',{'run':run,'jobs':{'jobs':jobs}});references.append(completion)
    lanes=[]
    for name in e.REQUIRED_LANES:
        core=name.endswith('core-minimum');reference=name.endswith('reference')
        lane=e.CILane(lane=name,source_commit=artifact.source_commit,source_tree=artifact.source_tree,
             kernel_build=artifact.kernel_build,inventory_digest=artifact.inventory_digest,
             wheel_sha256=artifact.wheel_sha256,sdist_sha256=artifact.sdist_sha256,run_id='1',ci_head_commit='a'*40,
             completion=completion,status='completed',conclusion='success',os='Darwin synthetic' if name.startswith('macos') else 'Linux synthetic',
             python=name.split('-')[1]+'.5',dependencies=deps,junit=junit,tests=e.TestCounts(tests=1,failures=0,errors=0,skipped=0),
             exclusions=e.CORE_EXCLUSIONS if core else [],sdk_checked=not core,
             distribution_scope='fresh-reference-outside-checkout' if reference else 'minimum-build-only',
             sdist_payload_equal=reference,host_skill_export_checked=reference)
        record=write(root,'lanes/'+name+'.json',lane.model_dump());lanes.append(record);references.append(record)
    docs=[write(root,name+'.md',b'Synthetic test fixture only\n') for name in ('release','upgrade','rollback')]
    references.extend(docs)
    w=e.FileEvidence(path=wheel.name,sha256=artifact.wheel_sha256); s=e.FileEvidence(path=sdist.name,sha256=artifact.sdist_sha256)
    references.extend([w,s])
    archive=write(root,'archive.json',{'schema_version':1,'location':'synthetic-controlled-test-archive',
        'retention':'release-lifetime','artifact':artifact.model_dump(),'files':[r.model_dump() for r in references]})
    manifest=e.ReleaseManifest(artifact=artifact,wheel=w,sdist=s,matrix=matrix_ref,lanes=lanes,documentation=docs,archive_record=archive)
    manifest.decision=e.PublicationDecision(status='approved',actor='synthetic-test-only',evidence_payload_sha256=manifest.approval_scope(),
                                          distribution_terms='test fixture only',channel='no actual publication')
    return root,manifest,matrix


def test_complete_synthetic_evidence_is_ready_but_never_publishes(evidence_bundle,monkeypatch):
    root,manifest,_=evidence_bundle
    from ai_orchestrator.engine import Engine
    monkeypatch.setattr(Engine,'__init__',lambda *a,**k:pytest.fail('runtime opened'))
    report=e.evaluate_release(manifest,root)
    assert report['result']=='READY',report
    assert report['publication_performed'] is False and report['automatic_replay'] is False
    before={p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    assert e.evaluate_release(manifest,root)==report
    assert before=={p.relative_to(root):p.read_bytes() for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('bad',[True,'2',3,0])
def test_matrix_version_is_exact(bad):
    with pytest.raises(ValidationError):e.SupportMatrix(schema_version=bad,kernel_version='x',historical_evidence=[],deployments=[])


@pytest.mark.parametrize('path',['../foreign','/absolute','a/../b','a//b','a/./b','a\\b'])
def test_evidence_paths_are_confined(path):
    with pytest.raises(ValidationError):e.FileEvidence(path=path,sha256='a'*64)


def test_evidence_parser_rejects_duplicate_nonfinite_and_symlink(tmp_path):
    for text in ['{"schema_version":1,"schema_version":2}','{"x":NaN}']:
        path=tmp_path/'bad.json';path.write_text(text)
        with pytest.raises(ValueError):e.read_json(path)
    target=tmp_path/'target';target.write_text('{}');link=tmp_path/'link';link.symlink_to(target)
    with pytest.raises(ValueError):e.read_json(link)
    with pytest.raises(ValueError):e.verify_file(tmp_path,e.FileEvidence(path='link',sha256=e.sha256_file(target)))


@pytest.mark.parametrize('mutation',[
    'conditional-host','unverified-provider','missing-probe','duplicate-probe','wrong-config',
    'wrong-build','automated-not-live','negative-effects','cancel-not-terminal',
    'no-wire-mismatch','fresh-no-validator','fresh-no-write','no-checked-skill','legacy-anomaly-omitted',
])
def test_deployment_negative_boundaries(evidence_bundle,mutation):
    root,manifest,matrix=evidence_bundle; d=matrix.deployments[0].model_copy(deep=True)
    if mutation=='conditional-host':d.host.transport.status='conditional'
    elif mutation=='unverified-provider':d.providers[0].execution.status='unverified'
    elif mutation=='missing-probe':d.probes=[]
    elif mutation=='duplicate-probe':d.probes.append(d.probes[0])
    elif mutation=='no-checked-skill':d.host.skill_sha256='0'*64
    elif mutation=='legacy-anomaly-omitted':d.host.version='2.1.284'
    else:
        index=next(i for i,r in enumerate(d.probes) if ('cancel_finalize' in r.path if mutation=='cancel-not-terminal'
                       else 'start_refusal' in r.path if mutation in ('negative-effects','no-wire-mismatch') else 'fresh_write' in r.path))
        p=e.ProbeRecord.model_validate(e.read_json(e.verify_file(root,d.probes[index])))
        if mutation=='wrong-config':p.configuration_sha256='0'*64
        elif mutation=='wrong-build':p.artifact.kernel_build='0'*64
        elif mutation=='automated-not-live':p.source='automated'
        elif mutation=='negative-effects':p.provider_calls_delta=1
        elif mutation=='cancel-not-terminal':p.task_status='awaiting_approval'
        elif mutation=='no-wire-mismatch':p.wire_decision='yes'
        elif mutation=='fresh-no-validator':p.validator_passed=False
        elif mutation=='fresh-no-write':p.file_changes_delta=0
        d.probes[index]=write(root,'mutated-probe.json',p.model_dump())
    assert e.qualify_deployment(d,manifest.artifact,root)


@pytest.mark.parametrize('mutation',['queued','wrong-tree','wrong-interpreter','ambient','skipped-sdk','missing-completion','wrong-job-head','missing-lane'])
def test_release_ci_gates_cannot_be_waived(evidence_bundle,mutation):
    root,m,_=evidence_bundle
    if mutation=='missing-lane':m.lanes.pop()
    else:
        lane=e.CILane.model_validate(e.read_json(e.verify_file(root,m.lanes[0])))
        if mutation=='queued':lane.status='queued'
        elif mutation=='wrong-tree':lane.source_tree='0'*40
        elif mutation=='wrong-interpreter':lane.python='3.9.0'
        elif mutation=='ambient':lane.distribution_scope='ambient-offline'
        elif mutation=='skipped-sdk':lane.sdk_checked=False
        elif mutation=='missing-completion':lane.completion=None
        else:
            completion=e.read_json(e.verify_file(root,lane.completion));completion['jobs']['jobs'][0]['head_sha']='0'*40
            lane.completion=write(root,'wrong-completion.json',completion)
        m.lanes[0]=write(root,'modified-lane.json',lane.model_dump())
    report=e.evaluate_release(m,root,require_approval=False)
    assert report['result']=='BLOCKED'
    assert any('CI ' in reason or 'distribution' in reason or 'SDK ' in reason for reason in report['blocking_reasons'])


def test_junit_declared_totals_cannot_hide_failure_or_skips(tmp_path):
    for body in ['<testcase><failure/></testcase>','<testcase><skipped/></testcase>','']:
        path=tmp_path/'tests.xml';path.write_text('<testsuite tests="1" failures="0" errors="0" skipped="0">'+body+'</testsuite>')
        with pytest.raises(ValueError):e.junit_counts(path)


@pytest.mark.parametrize('mutation',['no-archive','no-terms','pending-decision','stale-scope','wrong-wheel','incomplete-archive'])
def test_release_artifact_archive_and_publication_gates(evidence_bundle,mutation):
    root,m,_=evidence_bundle
    if mutation=='no-archive':m.archive_record=None
    elif mutation=='no-terms':m.decision.distribution_terms=None
    elif mutation=='pending-decision':m.decision.status='pending'
    elif mutation=='stale-scope':m.decision.evidence_payload_sha256='0'*64
    elif mutation=='wrong-wheel':m.artifact.kernel_build='0'*64
    else:
        archive=e.read_json(e.verify_file(root,m.archive_record));archive['files'].pop()
        m.archive_record=write(root,'incomplete-archive.json',archive)
    assert e.evaluate_release(m,root)['result']=='BLOCKED'


def test_mutated_bytes_and_shared_metadata_conflicts_fail_closed(evidence_bundle):
    root,m,_=evidence_bundle
    m.documentation.append(e.FileEvidence(path=m.documentation[0].path,sha256='0'*64))
    with pytest.raises(ValueError,match='conflicting'):e.evaluate_release(m,root)
    m.documentation.pop();(root/m.documentation[0].path).write_bytes(b'changed')
    with pytest.raises(ValueError,match='digest mismatch'):e.evaluate_release(m,root)


def test_qualification_only_omits_decision_not_technical_gates(evidence_bundle):
    root,m,_=evidence_bundle;m.decision=e.PublicationDecision()
    assert e.evaluate_release(m,root)['result']=='BLOCKED'
    assert e.evaluate_release(m,root,require_approval=False)['result']=='READY'
    m.lanes.pop()
    assert e.evaluate_release(m,root,require_approval=False)['result']=='BLOCKED'
