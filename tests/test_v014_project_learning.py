from __future__ import annotations

import json

import pytest

from ai_orchestrator import knowledge, learning
from ai_orchestrator.engine import Engine
from ai_orchestrator.models import OrchestratorError, TaskSpec, TaskState
from ai_orchestrator.project import Project, digest


class LocalAdapter:
    api_version = 2
    family = "fixture"
    capabilities = frozenset({"read_files", "write_files", "fresh_session", "structured_output", "shell"})
    semantic_capabilities = frozenset({"repository_analysis", "planning", "code_edit", "test_authoring", "review", "supervision"})

    def doctor(self, config, workspace):
        return {"version": "fixture", "family": self.family}

    def execute(self, request):
        raise AssertionError("v0.14 context tests do not dispatch providers")


def _task(
    engine: Engine,
    task_id: str,
    *,
    path: str = "shared.py",
    validation_exit: int = 0,
    status: str = "succeeded",
    observation: str = "shared project convention confirmed",
) -> TaskState:
    state = TaskState(
        schema_version=8,
        spec=TaskSpec(
            id=task_id,
            goal=f"change {path}",
            acceptance=["controller evidence is preserved"],
            risk="T2",
            validators=["check"],
        ),
        profile_digest=engine.profile_digest,
        status=status,
        phase="accept" if status == "succeeded" else "validate",
        attempt=1,
    )
    engine.store.artifact(
        state,
        "write_set",
        {
            "enforced": True,
            "allowed_paths": [path],
            "changed_paths": [path],
            "violations": [],
            "before_snapshot": "0" * 64,
            "after_snapshot": "1" * 64,
        },
    )
    engine.store.artifact(
        state,
        "validation",
        {
            "checks": [
                {
                    "name": "check",
                    "exit_code": validation_exit,
                    "error": None if validation_exit == 0 else "synthetic failure",
                }
            ],
            "snapshot": "1" * 64,
        },
    )
    if status == "succeeded":
        engine.store.artifact(
            state,
            "review",
            {
                "outcome": "approved",
                "summary": "approved",
                "blocking_findings": [],
                "observations": [observation],
                "evidence": [path],
            },
        )
        engine.store.artifact(
            state,
            "acceptance",
            {"actor": "operator", "snapshot": "1" * 64, "accepted_at": "2026-10-05T00:00:00Z"},
        )
        event = "task.accepted"
    else:
        event = "task.failed"
    engine.store.save(state, event, create=True)
    return state


def _candidate(project: Project, canonical_key: str):
    values = [
        item for item in learning.load_candidates(project)
        if item.canonical_key == canonical_key and item.status == "candidate"
    ]
    assert values
    return max(
        values,
        key=lambda item: (
            item.support.independent_task_count if item.support is not None else 0,
            item.support.evidence_count if item.support is not None else 0,
            item.id,
        ),
    )


def test_distillation_is_deterministic_and_rejected_evidence_does_not_reappear(engine):
    instance, _, _ = engine
    _task(instance, "learn-one")
    _task(instance, "learn-two")

    first = learning.distill(instance.project.root, instance.store)
    candidate = _candidate(instance.project, "validated-path:shared.py")
    assert candidate.schema_version == 2
    assert candidate.support.independent_task_ids == ["learn-one", "learn-two"]
    assert candidate.support.independent_task_count == 2
    assert candidate.support.corroborating_validations == 2
    assert candidate.support.corroborating_reviews == 2
    assert {ref.source for ref in candidate.evidence_refs} >= {"task", "artifact", "event"}

    again = learning.distill(instance.project.root, instance.store)
    assert candidate.id in again["retained"]
    assert candidate.id not in again["created"]

    scope = digest(candidate.model_dump())
    rejected = knowledge.reject(instance.project.root, candidate.id, scope, "operator", "not a reusable convention")
    assert rejected.status == "rejected"

    same_evidence = learning.distill(instance.project.root, instance.store)
    assert candidate.id in same_evidence["rejected_suppressed"]
    assert candidate.id not in same_evidence["created"]

    _task(instance, "learn-three")
    new_evidence = learning.distill(instance.project.root, instance.store)
    replacement = _candidate(instance.project, "validated-path:shared.py")
    assert replacement.id != candidate.id
    assert candidate.id in replacement.supersedes
    assert replacement.id in new_evidence["created"]
    assert replacement.support.independent_task_ids == ["learn-one", "learn-three", "learn-two"]
    assert replacement.support.independent_task_count == 3


def test_validator_history_surfaces_contradictions_without_granting_authority(engine):
    instance, _, _ = engine
    _task(instance, "pass-one", validation_exit=0)
    _task(instance, "pass-two", validation_exit=0)
    _task(instance, "fail-one", validation_exit=1, status="failed")
    _task(instance, "fail-two", validation_exit=1, status="failed")

    learning.distill(instance.project.root, instance.store)
    values = [
        item for item in learning.load_candidates(instance.project)
        if item.canonical_key == "validator-history:check"
    ]
    assert {item.provenance.polarity for item in values} == {"positive", "negative"}
    positive = next(item for item in values if item.provenance.polarity == "positive")
    negative = next(item for item in values if item.provenance.polarity == "negative")
    assert negative.id in positive.contradictions
    assert positive.id in negative.contradictions
    assert positive.support.contradiction_count == 1
    assert negative.support.contradiction_count == 1
    assert not (instance.project.root / ".orchestrator/knowledge/accepted" / f"{positive.id}.md").exists()


def test_promotion_verifies_typed_evidence_and_selected_context_carries_influence(engine):
    instance, _, _ = engine
    _task(instance, "promote-one", path="alpha.py", observation="alpha convention")
    _task(instance, "promote-two", path="alpha.py", observation="alpha convention")
    learning.distill(instance.project.root, instance.store)
    candidate = _candidate(instance.project, "validated-path:alpha.py")

    promoted = knowledge.promote(
        instance.project.root,
        candidate.id,
        digest(candidate.model_dump()),
        "operator",
    )
    assert promoted.status == "approved"

    profile, new_digest, universe = instance.project.load()
    assert new_digest != instance.profile_digest
    selected, influence = learning.select_context(universe, "please update alpha.py")
    accepted_path = f".orchestrator/knowledge/accepted/{candidate.id}.md"
    assert accepted_path in selected
    entry = next(item for item in influence.entries if item.path == accepted_path)
    assert entry.evidence_refs
    assert entry.kind == "knowledge"


def test_promotion_fails_closed_when_controller_evidence_hash_changes(engine):
    instance, _, _ = engine
    state = _task(instance, "tamper-one", path="tamper.py")
    _task(instance, "tamper-two", path="tamper.py")
    learning.distill(instance.project.root, instance.store)
    candidate = _candidate(instance.project, "validated-path:tamper.py")
    scope = digest(candidate.model_dump())

    target_ref = next(
        ref for ref in candidate.evidence_refs
        if ref.source == "artifact" and ref.owner_id == state.spec.id
    )
    artifact = next(item for item in state.artifacts if item.id == target_ref.id)
    path = instance.project.root / artifact.path
    path.write_text(path.read_text() + " ")

    with pytest.raises(OrchestratorError, match="artifact integrity check failed"):
        knowledge.promote(instance.project.root, candidate.id, scope, "operator")
    assert not (instance.project.root / ".orchestrator/knowledge/accepted" / f"{candidate.id}.md").exists()


def test_accepted_context_universe_can_exceed_prompt_budget_and_selection_is_bounded(workspace):
    accepted = workspace / ".orchestrator/knowledge/accepted"
    accepted.mkdir(parents=True, exist_ok=True)
    for index in range(5):
        (accepted / f"K-{index}.md").write_text(
            f"# item {index}\n\nalpha topic {index}\n" + ("x" * 18000)
        )

    project = Project(workspace)
    _, _, universe = project.load()
    assert sum(len(value.encode()) for value in universe.values()) > 64 * 1024

    selected, influence = learning.select_context(universe, "alpha")
    assert influence.selected_bytes <= learning.CONTEXT_SELECTION_BYTES
    assert sum(len(value.encode()) for value in selected.values()) == influence.selected_bytes
    assert influence.universe_items == 6
    assert influence.excluded_items >= 4


def test_new_task_persists_context_influence_and_prompt_uses_only_selected_context(workspace):
    accepted = workspace / ".orchestrator/knowledge/accepted"
    accepted.mkdir(parents=True, exist_ok=True)
    (accepted / "alpha.md").write_text("# alpha\n\nalpha-specific project convention\n")
    (accepted / "beta.md").write_text("# beta\n\nbeta-specific project convention\n")

    adapter = LocalAdapter()
    instance = Engine(workspace, {"claude": adapter, "codex": adapter})
    try:
        instance.trust("operator")
        state = instance.create(
            TaskSpec(
                id="context-task",
                goal="update alpha behavior",
                acceptance=["alpha convention remains satisfied"],
                risk="T2",
                validators=["check"],
            )
        )
        assert state.schema_version == 8
        assert state.context_influence is not None
        artifact = instance.store.latest(state, "context_influence")
        assert artifact["query_sha256"] == state.context_influence.query_sha256

        payload = json.loads(instance._prompt(state, "planner"))
        assert payload["context_influence"]["query_sha256"] == state.context_influence.query_sha256
        assert set(payload["project_context"]) == {item.path for item in state.context_influence.entries}
    finally:
        instance.close()


def test_conflicting_accepted_learning_is_preserved_but_not_injected(workspace):
    accepted = workspace / ".orchestrator/knowledge/accepted"
    accepted.mkdir(parents=True, exist_ok=True)
    base = {
        "canonical_key": "validator-history:check",
        "supersedes": [],
        "contradictions": [],
        "evidence_refs": [],
        "proposal_digest": "0" * 64,
    }
    for proposal_id, polarity in (("P-positive", "positive"), ("P-negative", "negative")):
        metadata = {**base, "proposal_id": proposal_id, "polarity": polarity}
        line = learning.LEARNING_METADATA_PREFIX + json.dumps(
            metadata, sort_keys=True, separators=(",", ":")
        ) + learning.LEARNING_METADATA_SUFFIX
        (accepted / f"{proposal_id}.md").write_text(f"{line}\n# {proposal_id}\n\nconflicting learning\n")

    project = Project(workspace)
    _, _, universe = project.load()
    selected, influence = learning.select_context(universe, "validator check")
    assert ".orchestrator/knowledge/accepted/P-positive.md" not in selected
    assert ".orchestrator/knowledge/accepted/P-negative.md" not in selected
    assert ".orchestrator/policies/baseline.md" in selected
    assert influence.universe_items == 3
    assert influence.excluded_items == 2


def test_distillation_covers_skill_usage_and_budget_candidate_kinds(engine):
    instance, _, _ = engine
    states = [
        _task(instance, f"learning-kind-{index}", observation="keep the shared helper small")
        for index in range(3)
    ]
    for state in states:
        instance.store.artifact(
            state,
            "usage",
            {
                "schema_version": 1,
                "records": [],
                "summary": {
                    "input_tokens": {"status": "unknown", "value": None, "source": None},
                    "output_tokens": {"status": "unknown", "value": None, "source": None},
                    "reasoning_tokens": {"status": "unsupported", "value": None, "source": None},
                    "total_tokens": {"status": "unknown", "value": None, "source": None},
                    "provider_elapsed_seconds": {"status": "unsupported", "value": None, "source": None},
                    "cost": {"status": "unsupported", "amount": None, "currency": None, "source": "unavailable", "pricing": None},
                },
            },
        )
    for state in states:
        instance.store.save(state, "learning.fixture_usage")

    for state in states[:2]:
        instance.store.artifact(
            state,
            "budget",
            {
                "schema_version": 1,
                "blockers": [
                    {
                        "dimension": "total_tokens",
                        "status": "unprovable",
                        "limit": 1000,
                        "observed": None,
                    }
                ],
                "can_dispatch": False,
            },
        )
        instance.store.save(state, "learning.fixture_artifacts")

    learning.distill(instance.project.root, instance.store)
    candidates = learning.load_candidates(instance.project)
    skill = [item for item in candidates if item.kind == "skill"]
    policy = [item for item in candidates if item.kind == "policy"]
    usage = [
        item for item in candidates
        if item.kind == "knowledge" and item.canonical_key == "usage-telemetry:input_tokens"
    ]
    assert skill and skill[0].statement_type == "recommendation"
    assert policy and policy[0].canonical_key == "budget-pattern:total_tokens:unprovable"
    assert usage and usage[0].provenance.polarity == "negative"
    assert all(item.status == "candidate" for item in [*skill, *policy, *usage])


def test_learning_candidate_evidence_is_bounded_but_full_support_changes_identity(engine):
    instance, _, _ = engine
    for index in range(12):
        _task(instance, f"bounded-{index:02d}", path="bounded.py")
    learning.distill(instance.project.root, instance.store)
    candidate = _candidate(instance.project, "validated-path:bounded.py")
    assert len(candidate.evidence_refs) <= learning.MAX_CANDIDATE_EVIDENCE_REFS
    assert len(candidate.support.independent_task_ids) <= learning.MAX_SUPPORT_TASK_IDS
    assert candidate.support.independent_task_count == 12
    assert candidate.support.evidence_count > len(candidate.evidence_refs)

    old_id = candidate.id
    _task(instance, "bounded-12", path="bounded.py")
    learning.distill(instance.project.root, instance.store)
    newer = _candidate(instance.project, "validated-path:bounded.py")
    assert newer.id != old_id
    assert old_id in newer.supersedes
    assert newer.support.independent_task_count == 13


def test_context_selection_prioritizes_project_policy_before_relevance(workspace):
    policies = workspace / ".orchestrator/policies"
    knowledge_dir = workspace / ".orchestrator/knowledge/accepted"
    policies.mkdir(parents=True, exist_ok=True)
    knowledge_dir.mkdir(parents=True, exist_ok=True)
    (policies / "guardrail.md").write_text("# policy\n\nmandatory project guardrail\n")
    (knowledge_dir / "alpha.md").write_text(
        "# alpha\n\n" + ("alpha " * 5000)
    )

    project = Project(workspace)
    _, _, universe = project.load()
    selected, influence = learning.select_context(universe, "alpha", budget_bytes=4096)
    assert ".orchestrator/policies/guardrail.md" in selected
    assert influence.entries[0].kind == "policy"


def test_project_learning_candidate_unknown_version_fails_closed(workspace):
    candidates = workspace / ".orchestrator/knowledge/candidates"
    candidates.mkdir(parents=True, exist_ok=True)
    path = candidates / "P-future.json"
    path.write_text('{"schema_version":99}\n')
    with pytest.raises(OrchestratorError, match="unsupported persisted ProjectLearningCandidate schema_version=99"):
        knowledge.load_proposal(workspace, "P-future")
    assert path.read_text() == '{"schema_version":99}\n'


def test_context_influence_artifact_unknown_version_fails_closed(engine):
    instance, _, _ = engine
    artifact = instance.store.write_artifact(
        "context-fixture", 0, "context_influence", {"schema_version": 2}
    )
    with pytest.raises(OrchestratorError, match="unsupported persisted ContextInfluence schema_version=2"):
        instance.store.read_artifact(artifact)


def test_legacy_v1_rejected_candidate_remains_readable(workspace):
    candidates = workspace / ".orchestrator/knowledge/candidates"
    candidates.mkdir(parents=True, exist_ok=True)
    path = candidates / "P-legacy.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": "P-legacy",
                "kind": "knowledge",
                "statement": "legacy rejected observation",
                "evidence": ["task:old"],
                "status": "rejected",
                "approved_by": None,
            }
        )
        + "\n"
    )
    proposal = knowledge.load_proposal(workspace, "P-legacy")
    assert proposal.schema_version == 1
    assert proposal.status == "rejected"
    assert proposal.rejected_by is None
