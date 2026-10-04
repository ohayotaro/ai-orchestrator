"""Evidence-backed proposals and explicit operator governance."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from .models import OrchestratorError, Proposal, identifier
from .project import Project, atomic_write, confined, digest, read_text
from .store import Store


def propose(root: Path, kind: str, statement: str, evidence: list[str]) -> Proposal:
    project = Project(root)
    project.load()
    if kind == "workflow":
        raise OrchestratorError("manual workflow candidates use the task-scoped workflow-save evidence path")
    with project.lock():
        proposal = Proposal(id="P-" + uuid.uuid4().hex[:12], kind=kind, statement=statement, evidence=evidence)
        path = confined(project.root, f".orchestrator/knowledge/candidates/{proposal.id}.json")
        atomic_write(path, proposal.model_dump_json(indent=2) + "\n")
        return proposal


def load_proposal(root: Path, proposal_id: str) -> Proposal:
    identifier(proposal_id)
    project = Project(root)
    path = confined(project.root, f".orchestrator/knowledge/candidates/{proposal_id}.json")
    return Proposal.model_validate_json(read_text(path, limit=1024 * 1024))


def _scope(proposal: Proposal) -> str:
    return digest(proposal.model_dump())


def promote(root: Path, proposal_id: str, scope: str, actor: str) -> Proposal:
    project = Project(root)
    with project.lock():
        proposal = load_proposal(root, proposal_id)
        if not actor.strip() or proposal.status != "candidate":
            raise OrchestratorError("promotion requires an actor and a candidate proposal")
        if _scope(proposal) != scope:
            raise OrchestratorError("proposal changed; inspect its current content before approving")

        if proposal.schema_version >= 2:
            from .learning import LEARNING_METADATA_PREFIX, LEARNING_METADATA_SUFFIX, verify_proposal_evidence
            store = Store(project)
            try:
                verify_proposal_evidence(store, proposal)
            finally:
                store.close()
            metadata = {
                "proposal_id": proposal.id,
                "canonical_key": proposal.canonical_key,
                "polarity": proposal.provenance.polarity if proposal.provenance else "neutral",
                "supersedes": proposal.supersedes,
                "contradictions": proposal.contradictions,
                "evidence_refs": [item.model_dump() for item in proposal.evidence_refs],
                "proposal_digest": scope,
            }
            header = LEARNING_METADATA_PREFIX + json.dumps(metadata, sort_keys=True, separators=(",", ":")) + LEARNING_METADATA_SUFFIX + "\n"
            evidence_title = "## Controller-verified evidence references"
            evidence_lines = "\n".join(
                f"- {item.source}:{item.id} sha256={item.sha256}"
                for item in proposal.evidence_refs
            )
            support = proposal.support.model_dump_json(indent=2) if proposal.support else "{}"
            workflow_note = (
                "\n\nThis accepted item is a recommendation only. It does not install or trust a workflow; "
                "use the separate workflow-save authority path for reusable workflow templates."
                if proposal.kind == "workflow" else ""
            )
            text = (
                f"{header}# {proposal.id}\n\n{proposal.statement}\n\n"
                f"{evidence_title}\n\n{evidence_lines}\n\n## Support metadata\n\n```json\n{support}\n```"
                f"{workflow_note}\n\nApproved by: {actor}\nProposal digest: {scope}\n"
            )
        else:
            text = (
                f"# {proposal.id}\n\n{proposal.statement}\n\n"
                "## Evidence references (not automatically verified)\n\n"
                + "\n".join(f"- {ref}" for ref in proposal.evidence)
                + f"\n\nApproved by: {actor}\nProposal digest: {scope}\n"
            )

        directory = {
            "knowledge": "knowledge/accepted",
            "policy": "policies",
            "skill": "skills",
            "workflow": "knowledge/accepted",
        }[proposal.kind]
        target = confined(project.root, f".orchestrator/{directory}/{proposal.id}.md")
        if target.exists():
            raise OrchestratorError("promotion target already exists; inspect interrupted promotion manually")
        atomic_write(target, text)
        proposal.status, proposal.approved_by = "approved", actor
        candidate = confined(project.root, f".orchestrator/knowledge/candidates/{proposal.id}.json")
        atomic_write(candidate, proposal.model_dump_json(indent=2) + "\n")
        return proposal


def reject(root: Path, proposal_id: str, scope: str, actor: str, reason: str) -> Proposal:
    project = Project(root)
    with project.lock():
        proposal = load_proposal(root, proposal_id)
        if proposal.status != "candidate" or not actor.strip() or not reason.strip():
            raise OrchestratorError("rejection requires a candidate, actor and reason")
        if _scope(proposal) != scope:
            raise OrchestratorError("proposal changed; inspect its current content before rejecting")
        proposal.status = "rejected"
        proposal.rejected_by = actor
        proposal.rejection_reason = reason.strip()[:4000]
        path = confined(project.root, f".orchestrator/knowledge/candidates/{proposal.id}.json")
        atomic_write(path, proposal.model_dump_json(indent=2) + "\n")
        return proposal


def revise(root: Path, proposal_id: str, scope: str, actor: str, statement: str) -> Proposal:
    project = Project(root)
    with project.lock():
        original = load_proposal(root, proposal_id)
        if original.status != "candidate" or not actor.strip() or not statement.strip():
            raise OrchestratorError("revision requires a candidate, actor and nonblank statement")
        if _scope(original) != scope:
            raise OrchestratorError("proposal changed; inspect its current content before revising")
        revised = original.model_copy(deep=True)
        revised.id = "P-" + uuid.uuid4().hex[:12]
        revised.statement = statement.strip()
        revised.revised_from = original.id
        revised.supersedes = sorted(set([*revised.supersedes, original.id]))
        revised.contradictions = []
        revised.status = "candidate"
        revised.approved_by = None
        revised.rejected_by = None
        revised.rejection_reason = None
        path = confined(project.root, f".orchestrator/knowledge/candidates/{revised.id}.json")
        atomic_write(path, revised.model_dump_json(indent=2) + "\n")
        original.status = "rejected"
        original.rejected_by = actor
        original.rejection_reason = f"superseded by operator revision {revised.id}"
        old = confined(project.root, f".orchestrator/knowledge/candidates/{original.id}.json")
        atomic_write(old, original.model_dump_json(indent=2) + "\n")
        return revised
