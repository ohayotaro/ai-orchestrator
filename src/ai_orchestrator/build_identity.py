"""Content-free loaded-build identity; editable-source drift never starts new work."""
from __future__ import annotations
import hashlib
import os
import time
from pathlib import Path
from . import __version__

_PACKAGE = Path(__file__).resolve().parent
_STARTED_AT = time.time()

def source_digest() -> str:
    checksum = hashlib.sha256()
    for path in sorted([*_PACKAGE.glob('*.py'), *_PACKAGE.joinpath('assets').glob('*')]):
        if path.is_file():
            checksum.update(path.relative_to(_PACKAGE).as_posix().encode())
            checksum.update(b'\0')
            checksum.update(path.read_bytes())
    return checksum.hexdigest()

_LOADED_DIGEST = source_digest()

def report(host_skills: list[Path] | None = None) -> dict:
    try:
        disk = source_digest()
    except OSError:
        disk = None
    def file_digest(name):
        path = _PACKAGE / 'assets' / name
        return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    skills = []
    packaged_skill = file_digest('SKILL.md')
    for supplied in host_skills or []:
        path = Path(supplied).expanduser()
        try:
            if not path.is_file() or path.stat().st_size > 1024 * 1024:
                raise OSError('host Skill is missing or exceeds the size bound')
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            skills.append({'path': str(path), 'sha256': actual, 'matches_packaged': actual == packaged_skill})
        except OSError as exc:
            skills.append({'path': str(path), 'sha256': None, 'matches_packaged': False, 'error': str(exc)})
    return {'host_skills': skills, 'host_skills_checked': bool(host_skills), 'schema_version': 1, 'package_version': __version__,
            'loaded_build': _LOADED_DIGEST, 'disk_build': disk,
            'matches': disk == _LOADED_DIGEST, 'process_started_at': _STARTED_AT,
            'process_id': os.getpid(), 'skill_sha256': file_digest('SKILL.md'),
            'contract_inventory_sha256': file_digest('contracts.json')}

def assert_current() -> None:
    from .models import OrchestratorError
    try:
        matches = source_digest() == _LOADED_DIGEST
    except OSError:
        matches = False
    if not matches:
        raise OrchestratorError('loaded_build_mismatch: restart the controller/worker before new work; no automatic replay')
    expected = os.environ.get('AI_ORCHESTRATOR_EXPECTED_BUILD')
    if expected and expected != _LOADED_DIGEST:
        raise OrchestratorError('loaded_build_mismatch: worker and parent controller builds differ')
