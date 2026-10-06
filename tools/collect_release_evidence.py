"""Collect build/lane evidence; CI completion is a separate post-run receipt.

No host/provider execution, live-runtime access, support promotion or publication.
"""
from __future__ import annotations
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from ai_orchestrator.release_evidence import (
    ArtifactIdentity, CILane, CORE_EXCLUSIONS, FileEvidence, REQUIRED_LANES,
    distribution_payload, payload_identity, sha256_file, read_json, junit_counts,
    verify_ci_completion,
)

ROOT=Path(__file__).resolve().parents[1]


def git(value):
    return subprocess.check_output(['git','rev-parse',value],cwd=ROOT,text=True).strip()


def write(path: Path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    data=json.dumps(value,ensure_ascii=True,sort_keys=True,indent=2)+'\n'
    if path.exists() and path.read_text()!=data:raise ValueError('refusing to replace different evidence: '+str(path))
    path.write_text(data)


def ref(path: Path,root: Path) -> FileEvidence:
    return FileEvidence(path=path.resolve().relative_to(root.resolve()).as_posix(),sha256=sha256_file(path))


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    actions=parser.add_subparsers(dest='action',required=True)
    build=actions.add_parser('build')
    build.add_argument('--dist',type=Path,default=ROOT/'dist')
    lane=actions.add_parser('lane')
    lane.add_argument('--lane',choices=REQUIRED_LANES,required=True)
    lane.add_argument('--artifact',type=Path,required=True)
    lane.add_argument('--junit',type=Path,required=True)
    lane.add_argument('--dependencies',type=Path,required=True)
    lane.add_argument('--distribution-report',type=Path)
    lane.add_argument('--evidence-root',type=Path,required=True)
    complete=actions.add_parser('complete')
    complete.add_argument('--lane-file',type=Path,required=True)
    complete.add_argument('--completion',type=Path,required=True,help='Saved GitHub run and all job responses, as {run:...,jobs:...}')
    complete.add_argument('--evidence-root',type=Path,required=True)
    complete.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.action=='build':
        if subprocess.run(['git','diff','--quiet','HEAD','--'],cwd=ROOT).returncode:
            raise ValueError('CI artifact collection requires unchanged tracked source')
        wheels=list(args.dist.glob('*.whl'));sources=list(args.dist.glob('*.tar.gz'))
        if len(wheels)!=1 or len(sources)!=1:raise ValueError('expected one exact wheel and sdist')
        value=ArtifactIdentity(**payload_identity(distribution_payload(wheels[0])),
            source_commit=git('HEAD'),source_tree=git('HEAD^{tree}'),
            wheel_sha256=sha256_file(wheels[0]),sdist_sha256=sha256_file(sources[0]))
        write(args.dist/'artifact-identity.json',value.model_dump())
    elif args.action=='lane':
        artifact=ArtifactIdentity.model_validate(read_json(args.artifact))
        if artifact.source_tree!=git('HEAD^{tree}'):raise ValueError('artifact and test source trees differ')
        counts=junit_counts(args.junit)
        if any((counts.failures,counts.errors,counts.skipped)):raise ValueError('cannot collect successful evidence from failing/skipped tests')
        root=args.evidence_root; target=root/'ci'/args.lane;target.mkdir(parents=True,exist_ok=True)
        for source,name in ((args.junit,'test-results.xml'),(args.dependencies,'resolved-dependencies.txt')):
            dest=target/name
            if dest.exists() and sha256_file(dest)!=sha256_file(source):raise ValueError('evidence destination already differs')
            shutil.copyfile(source,dest)
        reference=args.lane.endswith('-reference')
        distribution=read_json(args.distribution_report) if args.distribution_report else {}
        if reference:
            if (distribution.get('distribution_smoke')!='PASS' or distribution.get('dependency_isolation')!='fresh-reference-outside-checkout'
                    or distribution.get('wheel_sha256')!=artifact.wheel_sha256 or distribution.get('sdist_sha256')!=artifact.sdist_sha256):
                raise ValueError('reference lane did not qualify the exact shared distributions')
            installed=distribution.get('installed_identity',{})
            if installed.get('loaded_build')!=artifact.kernel_build or not installed.get('matches'):
                raise ValueError('installed and recorded package identities differ')
        # A collecting job is not yet completed. Finalize only with a saved,
        # completed-success GitHub run/job response after ALL jobs finish.
        value=CILane(lane=args.lane,source_commit=git('HEAD'),source_tree=git('HEAD^{tree}'),
            kernel_build=artifact.kernel_build,inventory_digest=artifact.inventory_digest,
            wheel_sha256=artifact.wheel_sha256,sdist_sha256=artifact.sdist_sha256,
            run_id=os.environ['GITHUB_RUN_ID'],ci_head_commit=os.environ['AI_ORCHESTRATOR_CI_HEAD'],
            status='in_progress',conclusion='pending',os=platform.platform(),python=platform.python_version(),
            dependencies=ref(target/'resolved-dependencies.txt',root),junit=ref(target/'test-results.xml',root),tests=counts,
            exclusions=CORE_EXCLUSIONS if args.lane.endswith('core-minimum') else [],
            sdk_checked=not args.lane.endswith('core-minimum'),
            distribution_scope='fresh-reference-outside-checkout' if reference else 'minimum-build-only',
            sdist_payload_equal=bool(distribution.get('sdist_payload_equal',False)),
            host_skill_export_checked=bool(distribution.get('host_skill_export_checked',False)))
        write(target/'measured.json',value.model_dump())
    else:
        raw=read_json(args.lane_file)
        value=CILane.model_validate({**raw,'completion':ref(args.completion,args.evidence_root).model_dump(),
                                    'status':'completed','conclusion':'success'})
        errors=verify_ci_completion(value,args.evidence_root)
        if errors:raise ValueError('; '.join(errors))
        write(args.output,value.model_dump())
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError,KeyError) as exc:
        print(json.dumps({'error':str(exc),'publication_performed':False}),file=sys.stderr)
        raise SystemExit(1)
