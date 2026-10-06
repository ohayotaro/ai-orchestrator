"""Build both distributions and smoke-test an installed wheel outside the checkout.

CI uses a genuinely fresh environment with resolved reference dependencies.
--offline reuses ambient dependencies solely for local installation-path checks;
it is not minimum/reference dependency qualification.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import venv

ROOT=Path(__file__).resolve().parents[1]


def run(args, *, cwd, capture=False):
    result=subprocess.run([str(x) for x in args],cwd=cwd,text=True,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.PIPE if capture else None,timeout=240)
    if result.returncode:
        if capture:
            print(result.stdout or '', file=sys.stderr)
            print(result.stderr or '', file=sys.stderr)
        result.check_returncode()
    return result.stdout if capture else None


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--offline',action='store_true')
    parser.add_argument('--wheel',type=Path)
    parser.add_argument('--sdist',type=Path)
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    version=tomllib.loads((ROOT/'pyproject.toml').read_text())['project']['version']
    if bool(args.wheel) != bool(args.sdist):
        parser.error('--wheel and --sdist must be supplied together')
    if args.wheel:
        wheels=[args.wheel.resolve()];source=args.sdist.resolve()
        if not wheels[0].name.startswith(f'ai_orchestrator_kernel-{version}-') or source.name!=f'ai_orchestrator_kernel-{version}.tar.gz':
            raise RuntimeError('supplied distribution version differs from tested source')
    else:
        output=ROOT/'dist';output.mkdir(exist_ok=True)
        run([sys.executable,'-c','from setuptools.build_meta import build_sdist,build_wheel; build_sdist("dist"); build_wheel("dist")'],cwd=ROOT)
        wheels=sorted(output.glob(f'ai_orchestrator_kernel-{version}-*.whl'))
        source=output/f'ai_orchestrator_kernel-{version}.tar.gz'
    if len(wheels)!=1 or not source.is_file():raise RuntimeError('Expected one versioned wheel and sdist')
    with tempfile.TemporaryDirectory(prefix='orchestrator-installed-qualification-') as tmp:
        temp=Path(tmp); env=temp/'venv'; outside=temp/'outside';outside.mkdir()
        venv.EnvBuilder(with_pip=True,system_site_packages=args.offline).create(env)
        if args.offline:
            import sysconfig
            local_site=next((env/'lib').glob('python*/site-packages'))
            (local_site/'offline-reference-dependencies.pth').write_text(sysconfig.get_path('purelib')+'\n')
        python=env/'bin/python';cli=env/'bin/orchestrator'
        install=[python,'-m','pip','install']
        if args.offline:
            install+=['--no-deps','--ignore-installed',wheels[0]]
        else:
            install+=['-c',ROOT/'requirements/rc-reference.txt',str(wheels[0])+'[dev,interop]']
        run(install,cwd=outside)
        run([python,'-m','pip','freeze'],cwd=outside)
        identity=json.loads(run([cli,'identity'],cwd=outside,capture=True))
        assert identity['package_version']==version and identity['matches']
        assert identity['contract_inventory_sha256'] and identity['skill_sha256']
        run([python,'-I','-c',
             'import sys;from pathlib import Path;import ai_orchestrator;import ai_orchestrator.worker;'
             'from ai_orchestrator.contract_inventory import generate,report;'
             'p=Path(ai_orchestrator.__file__).resolve();assert p.is_relative_to(Path(sys.prefix)),p;'
             'assert generate()=={k:v for k,v in report().items() if k!="inventory_digest"};print(p)'],cwd=outside)
        exported=outside/'SKILL.md';run([cli,'skill','--output',exported],cwd=outside)
        checked=json.loads(run([cli,'identity','--skill',exported],cwd=outside,capture=True))
        assert checked['host_skills'][0]['matches_packaged']
        project=outside/'project';project.mkdir()
        run(['git','init','-q'],cwd=project)
        run([cli,'--project',project,'init','--name','installed-smoke'],cwd=outside)
        run([cli,'--project',project,'worker','--once'],cwd=outside)
        run([cli,'--project',project,'doctor','--operational-only'],cwd=outside)
        run([cli,'--project',project,'persistence'],cwd=outside)
        # Build a wheel from the sdist without reaching back into the checkout.
        extracted=temp/'sdist';extracted.mkdir()
        with tarfile.open(source) as archive:
            for item in archive.getmembers():
                if item.issym() or item.islnk() or Path(item.name).is_absolute() or '..' in Path(item.name).parts:
                    raise RuntimeError('unsafe source distribution member')
            archive.extractall(extracted)
        sroot=next(extracted.iterdir())
        run([sys.executable,'-c','from setuptools.build_meta import build_wheel;build_wheel("dist")'],cwd=sroot)
        # Stable source/Skill/contract bytes must match both distribution paths.
        import zipfile,hashlib
        def payload(wheel):
            with zipfile.ZipFile(wheel) as z:
                return {n:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if n.startswith('ai_orchestrator/')}
        assert payload(wheels[0])==payload(next((sroot/'dist').glob('*.whl')))
    from ai_orchestrator.release_evidence import sha256_file
    report={'distribution_smoke':'PASS','outside_checkout':True,
            'wheel_sha256':sha256_file(wheels[0]),'sdist_sha256':sha256_file(source),
            'sdist_payload_equal':True,'host_skill_export_checked':True,
            'dependency_isolation':'ambient-offline' if args.offline else 'fresh-reference-outside-checkout',
            'installed_identity':identity}
    if args.report:
        args.report.write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    print(json.dumps(report))



if __name__=='__main__':main()
