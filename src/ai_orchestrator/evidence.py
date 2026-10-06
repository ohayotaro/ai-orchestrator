"""One non-mutating canonical evidence inventory for diagnostics and retention.

Every reference is checked before file I/O is deduplicated. Historical references
are roots even when their current accepted Markdown no longer exists.
"""
from __future__ import annotations
import hashlib
import json
import re
import yaml
from collections import defaultdict
from .models import Artifact, ContextInfluence, EvidenceRef, OrchestratorError
from .persistence import normalize_control_evidence, _reject_constant, decode_versioned_model_json
from .project import Project, confined, digest, read_text

MAX_ENTRIES = 100000
ARTIFACT_NAME = re.compile(r'^(\d+)-([\w.-]+)-([0-9a-f]{32})\.json$')


def _typed_refs(value, owner, output):
    """Only typed metadata containers, never infer identities from prose."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key == 'evidence_refs':
                if not isinstance(item, list):
                    raise OrchestratorError('typed evidence_refs must be a list')
                for raw in item:
                    if not isinstance(raw, dict) or type(raw.get('schema_version', 1)) is not int or raw.get('schema_version', 1) != 1:
                        raise OrchestratorError('unknown typed evidence reference version')
                    output.append((owner, EvidenceRef.model_validate(raw)))
            else:
                _typed_refs(item, owner, output)
    elif isinstance(value, list):
        for item in value:
            _typed_refs(item, owner, output)


def inventory(project: Project) -> dict:
    from .operational import _read_task_states, _read_intake_states, _read_exploration_states
    from . import learning, knowledge
    from .supervisor import Supervisor
    state_path = confined(project.root, '.orchestrator/runtime/state.sqlite3')
    tasks, errors = _read_task_states(state_path)
    intakes, more = _read_intake_states(state_path); errors.extend(more)
    sessions, more = _read_exploration_states(state_path); errors.extend(more)
    references = []
    typed = []
    conflicts, missing, corrupt = [], [], []
    legacy = False
    # Record all owners, not just the first/last metadata under a shared path.
    for owner, state in [(s.spec.id, s) for s in tasks] + [(s.id, s) for s in intakes] + [(s.id, s) for s in sessions]:
        for artifact in getattr(state, 'artifacts', []):
            references.append((owner, artifact))
        if getattr(state, 'artifact', None) is not None:
            references.append((owner, state.artifact))
        provenance = getattr(state, 'exploration', None) or getattr(state, 'pending_transition', None)
        if provenance is not None:
            references.append((owner, provenance.transition_artifact))
        try:
            _typed_refs(state.model_dump(), owner, typed)
        except (ValueError, OrchestratorError) as exc:
            errors.append(f'{owner}: invalid frozen evidence: {exc}')
    # Project.load is the canonical recursive, bounded, symlink-refusing universe.
    try:
        if confined(project.root, '.orchestrator/config.yaml').exists():
            context = project.load()[2]
            for path, text in context.items():
                metadata = learning._learning_metadata(text)
                if metadata is not None:
                    _typed_refs(metadata, path, typed)
                elif '## Evidence references (not automatically verified)' in text:
                    legacy = True
        candidates = confined(project.root, '.orchestrator/knowledge/candidates')
        if candidates.exists():
            for path in sorted(candidates.rglob('*.json')):
                confined(project.root, path.relative_to(project.root).as_posix())
                # Nested candidates have no public loader ID: validate directly.
                from .models import Proposal
                proposal = decode_versioned_model_json(read_text(path, limit=1024*1024),
                    rule_key='project_learning_candidate', model=Proposal)
                if proposal.schema_version == 1 and proposal.evidence:
                    legacy = True
                _typed_refs(proposal.model_dump(), str(path.relative_to(project.root)), typed)
    except (ValueError, OSError, OrchestratorError, yaml.YAMLError) as exc:
        errors.append(f'learning roots: {exc}')
    by_path = defaultdict(list)
    by_id = defaultdict(list)
    for owner, ref in references:
        by_path[ref.path].append((owner, ref))
        if ref.id: by_id[ref.id].append((owner, ref))
    for path, entries in by_path.items():
        expected = {}
        for owner, ref in entries:
            data = ref.model_dump()
            for key in ('sha256','kind','attempt','id','owner_id','created_at'):
                if key not in data or data[key] is None:
                    continue  # v1 absence is not contradictory v2 metadata.
                if key in expected and expected[key][1] != data[key]:
                    conflicts.append({'path':path, 'field':key, 'owners':[expected[key][0],owner]})
                else:
                    expected[key] = (owner, data[key])
    for aid, entries in by_id.items():
        if len({ref.path for _, ref in entries}) > 1:
            conflicts.append({'artifact_id':aid,'field':'path','owners':sorted({o for o,_ in entries})})
    values = {}
    file_hashes = {}
    # Canonical payloads can themselves hold older ContextInfluence manifests.
    for path, entries in by_path.items():
        try:
            target = confined(project.root, path)
            if not target.is_file():
                missing.append(path); continue
            raw = read_text(target, limit=1024*1024)
            sha = hashlib.sha256(raw.encode()).hexdigest()
            file_hashes[path] = sha
            if any(sha != ref.sha256 for _,ref in entries):
                corrupt.append(path); continue
            value = json.loads(raw, parse_constant=_reject_constant)
            for _, ref in entries:
                normalize_control_evidence(ref.kind, value)
            values[path] = value
            if any(ref.kind in ('context_influence','supervisor','exploration_turn','exploration_transition') for _,ref in entries):
                _typed_refs(value, path, typed)
        except (OSError, ValueError, OrchestratorError) as exc:
            corrupt.append(f'{path}: {exc}')
    # Compare semantic bindings only where the versioned source carries them.
    for intake in intakes:
        if intake.artifact and intake.result is not None and intake.artifact.path in values:
            if values[intake.artifact.path] != Supervisor._artifact_value(intake):
                corrupt.append(f'{intake.id}: Supervisor artifact disagrees with IntakeState')
        provenance = intake.exploration
        if provenance is not None:
            _check_transition(provenance, values, corrupt, intake.id)
    for state in tasks:
        if state.exploration is not None:
            _check_transition(state.exploration, values, corrupt, state.spec.id)
    for state in sessions:
        if state.current is not None:
            if not state.turn_artifacts or values.get(state.turn_artifacts[-1].path, {}).get('result') != state.current.model_dump():
                corrupt.append(f'{state.id}: understanding disagrees with its last immutable turn')
        for artifact in state.artifacts:
            value = values.get(artifact.path)
            if value is not None and (not isinstance(value, dict) or value.get('session_id') != state.id):
                corrupt.append(f'{state.id}: exploration artifact source mismatch')
        if state.pending_transition is not None:
            _check_transition(state.pending_transition, values, corrupt, state.id)
    protected_ids = {ref.id for _,ref in typed}
    # Resolve stable artifact IDs not already rooted in rows (e.g. historical
    # accepted influence after the Markdown is removed). Ambiguous paths fail.
    unresolved = {ref.id for _,ref in typed if ref.source == 'artifact'} - set(by_id)
    candidates = defaultdict(list)
    if unresolved:
        for count, path in enumerate(project.runtime.rglob('*.json'), 1):
            if count > MAX_ENTRIES:
                errors.append('evidence path inventory exceeds safety bound'); break
            relative = path.relative_to(project.root).as_posix()
            if 'maintenance-journal' in path.parts or 'worktrees' in path.parts: continue
            match = ARTIFACT_NAME.fullmatch(path.name)
            if match and 'A-'+match[3] in unresolved:
                try:
                    confined(project.root, relative)
                    candidates['A-'+match[3]].append(relative)
                except OrchestratorError as exc:
                    errors.append(str(exc))
    rooted = set(by_path)
    for owner, ref in typed:
        if ref.source != 'artifact':
            # Task/intake hashes describe frozen mutable snapshots, not necessarily
            # their current state. Absence is still corruption; events are immutable.
            if ref.source == 'task' and ref.id not in {s.spec.id for s in tasks}:
                errors.append(f'{owner}: missing canonical task evidence {ref.id}')
            elif ref.source == 'intake' and ref.id not in {s.id for s in intakes}:
                errors.append(f'{owner}: missing canonical intake evidence {ref.id}')
            elif ref.source == 'event':
                from .operational import _readonly_connection
                try:
                    seq = int(ref.id.removeprefix('E-'))
                    db = _readonly_connection(state_path)
                    try:
                        row = db.execute('SELECT sequence,task_id,kind,payload,created_at FROM events WHERE sequence=?', (seq,)).fetchone()
                    finally:
                        db.close()
                    if row is None:
                        errors.append(f'{owner}: missing canonical event evidence {ref.id}')
                    # Event encoding is verified by the canonical learning reader
                    # when promoted; no alternate guessed hash encoding is invented.
                except (OSError, ValueError) as exc:
                    errors.append(f'{owner}: unreadable canonical event evidence: {exc}')
            continue
        paths = {artifact.path for _,artifact in by_id.get(ref.id, [])} | set(candidates.get(ref.id, []))
        if len(paths) != 1:
            errors.append(f'{owner}: cannot resolve unique evidence artifact {ref.id}')
            continue
        path = next(iter(paths)); rooted.add(path)
        try:
            target = confined(project.root, path)
            if path not in file_hashes:
                raw = read_text(target, limit=1024*1024)
                file_hashes[path] = hashlib.sha256(raw.encode()).hexdigest()
                json.loads(raw, parse_constant=_reject_constant)
            if file_hashes[path] != ref.sha256:
                corrupt.append(f'{owner}: evidence hash mismatch for {ref.id}')
            for metadata_owner, artifact in by_id.get(ref.id, []):
                for key in ('kind','owner_id'):
                    if getattr(ref,key) is not None and getattr(ref,key) != getattr(artifact,key):
                        conflicts.append({'artifact_id':ref.id,'field':key,'owners':[owner,metadata_owner]})
        except (OSError, ValueError, OrchestratorError) as exc:
            errors.append(f'{owner}: unreadable typed evidence {ref.id}: {exc}')
    summary = {'paths':sorted(rooted), 'ids':sorted(protected_ids | set(by_id)),
               'metadata':sorted((owner,ref.path,digest(ref.model_dump())) for owner,ref in references),
               'files':dict(sorted(file_hashes.items())), 'legacy_untyped':legacy}
    return {**summary, 'fingerprint':digest(summary), 'errors':errors,
            'conflicts':conflicts,'missing':sorted(set(missing)), 'corrupt':sorted(set(corrupt)),
            'protected_evidence_ids':sorted(protected_ids)}


def _check_transition(ref, values, corrupt, owner):
    value = values.get(ref.transition_artifact.path)
    if value is None: return
    if not isinstance(value, dict) or (
        value.get('session_id'), value.get('revision'), value.get('source_snapshot')) != (
            ref.session_id, ref.revision, ref.source_snapshot):
        corrupt.append(f'{owner}: exploration transition provenance mismatch')
        return
    context = value.get('context')
    if not isinstance(context,dict) or context.get('session_id') != ref.session_id or context.get('revision') != ref.revision:
        corrupt.append(f'{owner}: exploration selected context mismatch')


def orphan_shape(project: Project, path) -> bool:
    """Name alone is insufficient: restrict layout and require bounded strict JSON.

    A successful complete reference inventory, exact content hash/age scope and
    quiescent locked recheck are additionally required by retention_plan/apply.
    Unknown schemas and legacy/unrecognized payloads are retained conservatively.
    """
    relative = path.relative_to(project.runtime)
    if len(relative.parts) != 2 or not ARTIFACT_NAME.fullmatch(path.name):
        return False
    confined(project.root, path.relative_to(project.root).as_posix())
    try:
        value = json.loads(read_text(path, limit=1024*1024), parse_constant=_reject_constant)
        return isinstance(value, dict) and bool(value) and (
            'schema_version' not in value or type(value['schema_version']) is int and value['schema_version'] == 1)
    except (OSError, ValueError, OrchestratorError):
        return False
