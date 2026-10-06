"""Offline release qualification records, independent of runtime authority.

This module reads explicitly supplied evidence. It never probes providers,
opens project runtime databases, grants permission, repairs state or publishes.
Owner live records are attestations, not cryptographic proof of human clicks.
"""
from __future__ import annotations

import hashlib
import json
import re
import stat
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Sha256 = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]
GitSha = Annotated[str, Field(pattern=r'^[a-f0-9]{40}$')]
Label = Annotated[str, Field(min_length=1, max_length=256)]
SupportStatus = Literal['supported','conditional','known-incompatible','unverified']
Result = Literal['PASS','FAIL','NOT TESTED','NOT APPLICABLE']
PROBE_REPETITIONS = {
    'fresh_write':2, 'start_refusal':2, 'cancel_finalize':2,
    'cancelled_provider_permission_prepare':1, 'untouched_submission':1,
    'explicit_no':1, 'cancel':1, 'explicit_yes':1, 'timeout':1,
    'stale_response':1, 'duplicate_response':1,
}
REQUIRED_LANES = (
    'linux-3.11-reference','linux-3.12-reference','linux-3.13-reference',
    'macos-3.13-reference','linux-3.11-minimum','linux-3.11-core-minimum',
)
CORE_EXCLUSIONS = [
    'tests/test_v03_sdk_interop.py',
    'tests/test_v04_wire.py::test_official_sdk_native_elicitation_decline',
]


class Record(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

    @model_validator(mode='before')
    @classmethod
    def exact_version_type(cls, value):
        if isinstance(value,dict) and 'schema_version' in value and type(value['schema_version']) is not int:
            raise ValueError('schema_version must be an integer, never bool/coerced text')
        return value


class FileEvidence(Record):
    path: Label
    sha256: Sha256
    redacted: bool = False

    @model_validator(mode='after')
    def confined_relative_name(self):
        path=PurePosixPath(self.path)
        if path.is_absolute() or any(p in ('','..','.') for p in self.path.split('/')) or '\\' in self.path:
            raise ValueError('evidence path must be normalized and relative')
        return self


class ArtifactIdentity(Record):
    package_version: Label
    source_commit: GitSha
    source_tree: GitSha
    kernel_build: Sha256
    inventory_digest: Sha256
    canonicalizer: Label
    packaged_skill_sha256: Sha256
    wheel_sha256: Sha256
    sdist_sha256: Sha256


class AxisSupport(Record):
    status: SupportStatus
    operations: list[Label]
    limitations: list[Label] = Field(default_factory=list)


class Host(Record):
    name: Label
    version: Label
    protocol: Label
    form_supported: bool
    skill_sha256: Sha256
    transport: AxisSupport


class ProviderRole(Record):
    role: Literal['reasoning/planning/review','implementation']
    adapter: Label
    cli_version: Label
    model_mode: Literal['explicit','adapter_default']
    model: str | None
    effort_mode: Literal['explicit','adapter_default']
    effort: str | None
    execution: AxisSupport

    @model_validator(mode='after')
    def explicit_values_present(self):
        for key in ('model','effort'):
            if getattr(self,key+'_mode')=='explicit' and not getattr(self,key):
                raise ValueError('explicit runtime selection requires its value')
        return self


class Deployment(Record):
    id: Label
    artifact: ArtifactIdentity
    host: Host
    os: Label
    python: Label
    providers: list[ProviderRole]
    native_permission_assumptions: Label
    anomalies: list[Label] = Field(default_factory=list)
    anomaly_disposition: FileEvidence | None = None
    probes: list[FileEvidence] = Field(default_factory=list)

    def configuration_digest(self) -> str:
        # Support labels cannot change execution identity. Exact host/provider
        # versions, options, OS, permissions and checked Skill always do.
        value=self.model_dump(exclude={'id','artifact','anomalies','anomaly_disposition','probes'})
        value['host'].pop('transport')
        for role in value['providers']: role.pop('execution')
        return json_digest(value)


class SupportMatrix(Record):
    schema_version: Literal[2] = 2
    kernel_version: Label
    target_version: Literal['1.0.0'] = '1.0.0'
    historical_evidence: list[FileEvidence]
    deployments: list[Deployment]

    @model_validator(mode='after')
    def unique_deployments(self):
        if len({d.id for d in self.deployments}) != len(self.deployments):
            raise ValueError('duplicate deployment ID')
        return self


class ProbeRecord(Record):
    schema_version: Literal[1] = 1
    id: Label
    kind: Label
    result: Result
    source: Literal['owner-live','automated']
    artifact: ArtifactIdentity
    configuration_sha256: Sha256
    fixture_id: Label
    gate_ids: list[Label]
    evidence_date: Annotated[str,Field(pattern=r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})$')]
    observer: Label
    notes: list[Label]
    provider_calls_delta: Annotated[int,Field(ge=0)]
    validator_calls_delta: Annotated[int,Field(ge=0)]
    file_changes_delta: Annotated[int,Field(ge=0)]
    new_gate_rows: Annotated[int,Field(ge=0)]
    authorization_granted: bool
    task_status: str | None
    validator_passed: bool | None
    selected_decision: Literal['yes','no','cancel','untouched','not-applicable']
    wire_decision: Literal['yes','no','cancel','absent','not-applicable']


class TestCounts(Record):
    tests: Annotated[int,Field(ge=1)]
    failures: Annotated[int,Field(ge=0)]
    errors: Annotated[int,Field(ge=0)]
    skipped: Annotated[int,Field(ge=0)]


class CILane(Record):
    schema_version: Literal[1] = 1
    lane: Label
    source_commit: GitSha
    source_tree: GitSha
    kernel_build: Sha256
    inventory_digest: Sha256
    wheel_sha256: Sha256
    sdist_sha256: Sha256
    run_id: Label
    ci_head_commit: GitSha
    completion: FileEvidence | None = None
    status: Literal['completed','in_progress','queued']
    conclusion: Literal['success','failure','pending']
    os: Label
    python: Label
    dependencies: FileEvidence
    junit: FileEvidence
    tests: TestCounts
    exclusions: list[str]
    sdk_checked: bool
    distribution_scope: Literal['fresh-reference-outside-checkout','minimum-build-only','ambient-offline']
    sdist_payload_equal: bool
    host_skill_export_checked: bool


class PublicationDecision(Record):
    status: Literal['pending','approved','rejected'] = 'pending'
    actor: str | None = None
    evidence_payload_sha256: Sha256 | None = None
    distribution_terms: str | None = None
    channel: str | None = None


class ReleaseManifest(Record):
    schema_version: Literal[1] = 1
    artifact: ArtifactIdentity
    wheel: FileEvidence
    sdist: FileEvidence
    matrix: FileEvidence
    lanes: list[FileEvidence]
    documentation: list[FileEvidence]
    archive_record: FileEvidence | None = None
    decision: PublicationDecision = Field(default_factory=PublicationDecision)

    def approval_scope(self) -> str:
        return json_digest(self.model_dump(exclude={'decision'}))


def json_digest(value) -> str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=True,allow_nan=False,
                                     separators=(',',':')).encode('utf-8')).hexdigest()


def sha256_file(path: Path) -> str:
    checksum=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):checksum.update(block)
    return checksum.hexdigest()


def read_json(path: Path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size>4*1024*1024:
        raise ValueError('evidence JSON must be a bounded regular file')
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate evidence JSON key')
            result[key]=value
        return result
    def nonfinite(value):raise ValueError('non-finite evidence JSON')
    return json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=unique,parse_constant=nonfinite)


def verify_file(root: Path, evidence: FileEvidence) -> Path:
    root=root.resolve()
    path=root
    for component in PurePosixPath(evidence.path).parts:
        path=path/component
        if path.is_symlink():raise ValueError('evidence symlinks are unsupported')
    if not path.is_file() or not stat.S_ISREG(path.stat().st_mode) or path.stat().st_size>256*1024*1024:
        raise ValueError('evidence must be a bounded regular file')
    if sha256_file(path)!=evidence.sha256:raise ValueError('evidence digest mismatch: '+evidence.path)
    return path


def _probe_errors(probe: ProbeRecord) -> list[str]:
    failures=[]
    if probe.source!='owner-live' or probe.result!='PASS':failures.append('not an owner-live PASS')
    if probe.kind not in PROBE_REPETITIONS:failures.append('unknown required probe kind')
    if probe.kind=='fresh_write':
        if not (probe.task_status=='succeeded' and probe.validator_passed is True and
                probe.provider_calls_delta>0 and probe.validator_calls_delta>0 and probe.file_changes_delta>0 and probe.authorization_granted):
            failures.append('fresh write lacks measured execution/acceptance evidence')
        if len(set(probe.gate_ids))<3:failures.append('fresh write requires three independent gates')
    elif probe.kind=='cancel_finalize':
        if probe.authorization_granted:failures.append('finalization granted execution authority')
        if probe.task_status!='cancelled':failures.append('cancel intent is not terminal cancellation')
        if any((probe.provider_calls_delta,probe.validator_calls_delta,probe.file_changes_delta)):
            failures.append('idle finalization has new effects')
    elif probe.kind=='cancelled_provider_permission_prepare':
        if any((probe.new_gate_rows,probe.provider_calls_delta,probe.validator_calls_delta,probe.file_changes_delta)) or probe.authorization_granted:
            failures.append('cancelled permission preparation has a row/authority/effect')
    elif probe.kind not in ('explicit_yes','duplicate_response'):
        if probe.authorization_granted or any((probe.provider_calls_delta,probe.validator_calls_delta,probe.file_changes_delta)):
            failures.append('negative probe has authority or effects')
    if probe.kind in ('start_refusal','explicit_no'):
        if probe.selected_decision!='no' or probe.wire_decision!='no':failures.append('No intent/wire not demonstrated')
    if probe.kind=='cancel' and (probe.selected_decision!='cancel' or probe.wire_decision not in ('cancel','absent')):
        failures.append('cancel intent/wire not demonstrated')
    if probe.kind=='fresh_write' and (probe.selected_decision!='yes' or probe.wire_decision!='yes'):
        failures.append('fresh write affirmative evidence absent')
    if probe.kind=='untouched_submission':
        if probe.selected_decision!='untouched' or probe.wire_decision=='yes':failures.append('untouched submission authorized')
    if probe.kind=='explicit_yes':
        if probe.selected_decision!='yes' or probe.wire_decision!='yes' or not probe.authorization_granted:
            failures.append('explicit affirmative path not demonstrated')
    if probe.kind=='duplicate_response':
        if probe.authorization_granted or any((probe.new_gate_rows,probe.provider_calls_delta,probe.validator_calls_delta,probe.file_changes_delta)):
            failures.append('duplicate response had an additional effect')
    if probe.kind in ('fresh_write','start_refusal','explicit_no','explicit_yes','cancel','timeout','stale_response','untouched_submission','duplicate_response') and not probe.gate_ids:
        failures.append('form probe has no gate identity')
    return failures


def qualify_deployment(deployment: Deployment, artifact: ArtifactIdentity, root: Path) -> list[str]:
    errors=[]
    if deployment.artifact!=artifact:errors.append('deployment artifact differs from final artifact')
    host=deployment.host
    if host.name!='Claude Code' or host.transport.status!='supported' or not host.form_supported or host.protocol!='2025-06-18':
        errors.append('required supported Claude Code form baseline absent')
    if host.skill_sha256!=artifact.packaged_skill_sha256:errors.append('host Skill differs from packaged Skill')
    if not set(PROBE_REPETITIONS)<=set(host.transport.operations):errors.append('host operation support scope incomplete')
    roles={r.role:r for r in deployment.providers}
    if len(roles)!=len(deployment.providers) or set(roles)!= {'reasoning/planning/review','implementation'}:
        errors.append('required independent provider roles absent/duplicate')
    else:
        for name,adapter in (('reasoning/planning/review','claude'),('implementation','codex')):
            role=roles[name]
            if role.adapter!=adapter or role.execution.status!='supported' or 'fresh_write' not in role.execution.operations:
                errors.append('required provider-role execution not supported: '+name)
    if host.name=='Claude Code' and host.version=='2.1.284' and not deployment.anomalies:
        errors.append('historical conditional host anomaly omitted; evidence-backed disposition required')
    if deployment.anomalies:
        if deployment.anomaly_disposition is None:errors.append('unresolved host anomaly')
        else:
            disposition=read_json(verify_file(root,deployment.anomaly_disposition))
            if (disposition.get('configuration_sha256')!=deployment.configuration_digest()
                    or disposition.get('anomalies')!=deployment.anomalies
                    or disposition.get('disposition')!='resolved-with-evidence'
                    or not disposition.get('explanation') or not disposition.get('evidence')):
                errors.append('anomaly disposition is not evidence/configuration bound')
            else:
                for raw in disposition['evidence']:verify_file(root,FileEvidence.model_validate(raw))
    seen_ids=set(); seen_cases=set(); counts={k:0 for k in PROBE_REPETITIONS}
    for reference in deployment.probes:
        probe=ProbeRecord.model_validate(read_json(verify_file(root,reference)))
        if probe.id in seen_ids or (probe.kind,probe.fixture_id) in seen_cases:
            errors.append('duplicate live probe/fixture: '+probe.id);continue
        seen_ids.add(probe.id);seen_cases.add((probe.kind,probe.fixture_id))
        local=_probe_errors(probe)
        if probe.artifact!=artifact or probe.configuration_sha256!=deployment.configuration_digest():
            local.append('live probe artifact/configuration mismatch')
        if local:errors.extend(probe.id+': '+e for e in local)
        elif probe.kind in counts:counts[probe.kind]+=1
    for kind,number in PROBE_REPETITIONS.items():
        if counts[kind]<number:errors.append(f'{kind}: {counts[kind]}/{number} valid fresh runs')
    return errors


def junit_counts(path: Path) -> TestCounts:
    import xml.etree.ElementTree as ET
    if not path.is_file() or path.stat().st_size>16*1024*1024:raise ValueError('invalid bounded JUnit report')
    raw=path.read_bytes()
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():raise ValueError('JUnit DTD/entities unsupported')
    tree=ET.fromstring(raw); suites=[tree] if tree.tag=='testsuite' else list(tree.iter('testsuite'))
    leaf=[s for s in suites if not s.findall('testsuite')]
    values={key:sum(int(s.attrib.get(key,'0')) for s in leaf) for key in ('tests','failures','errors','skipped')}
    cases=list(tree.iter('testcase'))
    measured={'tests':len(cases), **{key:sum(case.find(tag) is not None for case in cases)
              for key,tag in (('failures','failure'),('errors','error'),('skipped','skipped'))}}
    if values!=measured:raise ValueError('JUnit counters disagree with testcase evidence')
    return TestCounts(**measured)


def evaluate_release(manifest: ReleaseManifest, root: Path, *, require_approval=True) -> dict:
    """Fail closed on missing, invalid, partial, reused or mismatched evidence."""
    errors=[]; artifact=manifest.artifact
    if artifact.package_version!='1.0.0':errors.append('final 1.0.0 artifact is not prepared')
    if artifact.canonicalizer!='json-schema-positions-v2':errors.append('unexpected canonicalizer identity')
    references=[manifest.wheel,manifest.sdist,manifest.matrix,*manifest.lanes,*manifest.documentation]
    seen={}
    for reference in references:
        if reference.path in seen and seen[reference.path]!=reference.sha256:
            raise ValueError('conflicting metadata for shared evidence path')
        seen[reference.path]=reference.sha256
        verify_file(root,reference)
    if manifest.wheel.sha256!=artifact.wheel_sha256 or manifest.sdist.sha256!=artifact.sdist_sha256:
        errors.append('distribution files differ from artifact identity')
    errors.extend(verify_distribution_identity(root,manifest))
    matrix=SupportMatrix.model_validate(read_json(verify_file(root,manifest.matrix)))
    if matrix.kernel_version!=artifact.package_version:errors.append('support matrix package mismatch')
    for reference in matrix.historical_evidence:verify_file(root,reference)
    references.extend(matrix.historical_evidence)
    for deployment in matrix.deployments:
        references.extend(deployment.probes)
        if deployment.anomaly_disposition:
            references.append(deployment.anomaly_disposition)
            disposition=read_json(verify_file(root,deployment.anomaly_disposition))
            references.extend(FileEvidence.model_validate(raw) for raw in disposition.get('evidence',[]))
    deployments={d.id:qualify_deployment(d,artifact,root) for d in matrix.deployments}
    if not deployments or all(deployments.values()):errors.append('no supported final-artifact end-to-end deployment')
    lanes={}
    for reference in manifest.lanes:
        lane=CILane.model_validate(read_json(verify_file(root,reference)))
        if lane.lane in lanes:errors.append('duplicate CI lane: '+lane.lane)
        lanes[lane.lane]=lane
        if lane.lane not in REQUIRED_LANES:errors.append('unknown CI lane: '+lane.lane)
        if lane.status!='completed' or lane.conclusion!='success':errors.append('CI incomplete/failed: '+lane.lane)
        for key in ('source_tree','kernel_build','inventory_digest','wheel_sha256','sdist_sha256'):
            if getattr(lane,key)!=getattr(artifact,key):errors.append('CI identity mismatch '+lane.lane+': '+key)
        # A tested synthetic merge commit may differ from the final record
        # commit; exact source tree + package/artifact identities must match.
        references.extend([lane.dependencies,lane.junit])
        if lane.completion:
            references.append(lane.completion)
        errors.extend(verify_ci_completion(lane,root))
        verify_file(root,lane.dependencies)
        measured=junit_counts(verify_file(root,lane.junit))
        if measured!=lane.tests or any((measured.failures,measured.errors,measured.skipped)):
            errors.append('CI test evidence inconsistent/failing/skipped: '+lane.lane)
        platform, _, version_and_scope = lane.lane.partition('-')
        version = version_and_scope.split('-')[0]
        if not lane.python.startswith(version+'.') or not lane.os.lower().startswith('linux' if platform=='linux' else ('darwin','macos')):
            errors.append('CI platform/interpreter does not match lane: '+lane.lane)
        core=lane.lane=='linux-3.11-core-minimum'
        if sorted(lane.exclusions)!=sorted(CORE_EXCLUSIONS if core else []):errors.append('unexpected CI exclusion: '+lane.lane)
        if lane.sdk_checked==core:errors.append('SDK scope mismatch: '+lane.lane)
        if lane.lane.endswith('-reference') and (lane.distribution_scope!='fresh-reference-outside-checkout'
                or not lane.sdist_payload_equal or not lane.host_skill_export_checked):
            errors.append('clean distribution qualification missing: '+lane.lane)
    for name in REQUIRED_LANES:
        if name not in lanes:errors.append('missing CI lane: '+name)
    # Preserve every transitive evidence byte in the durable archive, not only
    # top-level hashes. A shared path with conflicting metadata is never deduped.
    unique={}
    for reference in references:
        if reference.path in unique and unique[reference.path]!=reference:
            raise ValueError('conflicting transitive evidence metadata')
        verify_file(root,reference); unique[reference.path]=reference
    references=list(unique.values())
    if len(manifest.documentation)<3:errors.append('release/upgrade/rollback documentation missing')
    if manifest.archive_record is None:errors.append('durable controlled archive receipt missing')
    else:
        archive=read_json(verify_file(root,manifest.archive_record))
        if type(archive.get('schema_version')) is not int or archive.get('schema_version')!=1 or not archive.get('location') or archive.get('retention')!='release-lifetime':
            errors.append('durable archive receipt incomplete')
        elif archive.get('artifact')!=artifact.model_dump():errors.append('archive artifact mismatch')
        elif sorted(archive.get('files',[]),key=lambda v:v.get('path',''))!=sorted([r.model_dump() for r in references],key=lambda v:v['path']):
            errors.append('archive receipt does not cover complete release payload')
    scope=manifest.approval_scope(); decision=manifest.decision
    if require_approval and (decision.status!='approved' or not decision.actor or
            decision.evidence_payload_sha256!=scope or not decision.distribution_terms or not decision.channel):
        errors.append('explicit scoped owner publication decision/terms/channel missing')
    return {'schema_version':1,'result':'BLOCKED' if errors else 'READY',
            'publication_performed':False,'automatic_replay':False,'approval_scope':scope,
            'blocking_reasons':errors,'deployments':deployments,
            'assurance':'offline evidence consistency and owner attestations; not human-presence attestation'}


def verify_ci_completion(lane: CILane, root: Path) -> list[str]:
    if lane.completion is None:return ['CI run completion evidence missing: '+lane.lane]
    record=read_json(verify_file(root,lane.completion))
    run=record.get('run',{})
    jobs=record.get('jobs',{}).get('jobs',[])
    if (str(run.get('id'))!=lane.run_id or run.get('head_sha')!=lane.ci_head_commit
            or run.get('status')!='completed' or run.get('conclusion')!='success'):
        return ['CI run completion does not match: '+lane.lane]
    matches=[job for job in jobs if job.get('name')=='test ('+lane.lane+')']
    builders=[job for job in jobs if job.get('name')=='build-distribution']
    if (len(matches)!=1 or len(builders)!=1 or any(str(j.get('run_id'))!=lane.run_id or j.get('head_sha')!=lane.ci_head_commit or j.get('status')!='completed' or j.get('conclusion')!='success'
            for j in [*matches,*builders])):
        return ['CI lane/build job completion missing or failed: '+lane.lane]
    return []


def distribution_payload(wheel: Path) -> dict[str, bytes]:
    import zipfile
    with zipfile.ZipFile(wheel) as archive:
        names=archive.namelist()
        if len(set(names))!=len(names):raise ValueError('duplicate wheel member')
        total=0;result={}
        for item in archive.infolist():
            path=PurePosixPath(item.filename)
            if path.is_absolute() or '..' in path.parts or stat.S_ISLNK(item.external_attr>>16):
                raise ValueError('unsafe wheel member')
            total+=item.file_size
            if total>256*1024*1024:raise ValueError('wheel payload too large')
            if item.filename.startswith('ai_orchestrator/') and not item.is_dir():
                result[item.filename.removeprefix('ai_orchestrator/')]=archive.read(item)
        return result


def payload_identity(payload: dict[str, bytes]) -> dict:
    from .project import digest
    checksum=hashlib.sha256()
    selected=sorted(name for name in payload if ('/' not in name and name.endswith('.py'))
                    or (name.startswith('assets/') and name.count('/')==1))
    for name in selected:
        checksum.update(name.encode());checksum.update(b'\0');checksum.update(payload[name])
    inventory=json.loads(payload['assets/contracts.json'])
    version=re.search(r'__version__\s*=\s*["\']([^"\']+)',payload['__init__.py'].decode())
    if not version:raise ValueError('wheel package version missing')
    return {'package_version':version.group(1),'kernel_build':checksum.hexdigest(),
            'inventory_digest':digest(inventory),'canonicalizer':inventory['canonicalizer'],
            'packaged_skill_sha256':hashlib.sha256(payload['assets/SKILL.md']).hexdigest()}


def verify_distribution_identity(root: Path, manifest: ReleaseManifest) -> list[str]:
    import tarfile
    import email.parser
    import zipfile
    wheel=verify_file(root,manifest.wheel); sdist=verify_file(root,manifest.sdist)
    payload=distribution_payload(wheel); actual=payload_identity(payload)
    errors=['wheel metadata mismatch: '+key for key,value in actual.items() if value!=getattr(manifest.artifact,key)]
    with zipfile.ZipFile(wheel) as archive:
        entries=[n for n in archive.namelist() if n.endswith('.dist-info/METADATA')]
        if len(entries)!=1:raise ValueError('wheel metadata is missing/ambiguous')
        metadata=email.parser.BytesParser().parsebytes(archive.read(entries[0]))
        if metadata['Name']!='ai-orchestrator-kernel' or metadata['Version']!=manifest.artifact.package_version:
            errors.append('wheel distribution name/version mismatch')
    source_payload={}; names=set(); total=0
    with tarfile.open(sdist,'r:gz') as archive:
        for item in archive:
            path=PurePosixPath(item.name)
            if item.name in names or path.is_absolute() or '..' in path.parts or not (item.isdir() or item.isfile()):
                raise ValueError('unsafe/duplicate sdist member')
            names.add(item.name);total+=item.size
            if total>256*1024*1024:raise ValueError('sdist payload too large')
            if item.isfile() and len(path.parts)>3 and path.parts[1:3]==('src','ai_orchestrator'):
                stream=archive.extractfile(item)
                if stream is None:raise ValueError('missing sdist member body')
                source_payload['/'.join(path.parts[3:])]=stream.read()
    if source_payload!=payload:errors.append('sdist and wheel package payloads differ')
    return errors
