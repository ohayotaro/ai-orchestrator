"""Evidence-backed proposals. No candidate is active and no code is auto-generated."""

from __future__ import annotations

import uuid
from pathlib import Path

from .models import OrchestratorError, Proposal, identifier
from .project import Project, atomic_write, confined, digest, read_text


def propose(root: Path, kind: str, statement: str, evidence: list[str]) -> Proposal:
    project = Project(root)
    project.load()
    with project.lock():
        proposal = Proposal(id="P-" + uuid.uuid4().hex[:12], kind=kind, statement=statement, evidence=evidence)
        path = confined(project.root, f".orchestrator/knowledge/candidates/{proposal.id}.json")
        atomic_write(path, proposal.model_dump_json(indent=2) + "\n")
        return proposal


def load_proposal(root: Path, proposal_id: str) -> Proposal:
    identifier(proposal_id)
    project = Project(root)
    path = confined(project.root, f".orchestrator/knowledge/candidates/{proposal_id}.json")
    return Proposal.model_validate_json(read_text(path))


def promote(root: Path, proposal_id: str, scope: str, actor: str) -> Proposal:
    project = Project(root)
    with project.lock():
        proposal = load_proposal(root, proposal_id)
        if not actor.strip() or proposal.status != "candidate":
            raise OrchestratorError("promotion requires an actor and a candidate proposal")
        if digest(proposal.model_dump()) != scope:
            raise OrchestratorError("proposal changed; inspect its current content before approving")
        directory = {"knowledge": "knowledge/accepted", "policy": "policies", "skill": "skills"}[proposal.kind]
        target = confined(project.root, f".orchestrator/{directory}/{proposal.id}.md")
        if target.exists():
            raise OrchestratorError("promotion target already exists; inspect interrupted promotion manually")
        text = f"# {proposal.id}\n\n{proposal.statement}\n\n## Evidence references (not automatically verified)\n\n" + "\n".join(f"- {ref}" for ref in proposal.evidence) + f"\n\nApproved by: {actor}\nProposal digest: {scope}\n"
        # Write the approved artifact first; an interruption cannot silently overwrite it.
        atomic_write(target, text)
        proposal.status, proposal.approved_by = "approved", actor
        candidate = confined(project.root, f".orchestrator/knowledge/candidates/{proposal.id}.json")
        atomic_write(candidate, proposal.model_dump_json(indent=2) + "\n")
        return proposal
