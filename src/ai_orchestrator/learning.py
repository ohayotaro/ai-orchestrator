"""Deterministic Project Learning over controller-owned historical evidence.

Candidates are observations/recommendations only. They never mutate profile
authority, grant providers/permissions/effects, or become prompt context until
an operator explicitly promotes them and re-trusts the resulting profile.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .models import (
    ContextInfluence,
    ContextInfluenceEntry,
    EvidenceRef,
    LearningProvenance,
    LearningSupport,
    OrchestratorError,
    Proposal,
)
from .persistence import decode_versioned_model_json
from .project import Project, atomic_write, confined, digest, encode
from .store import Store

DISTILLATION_VERSION = 1
CONTEXT_SELECTOR_VERSION = 1
CONTEXT_SELECTION_BYTES = 24 * 1024
MAX_CANDIDATE_EVIDENCE_REFS = 32
MAX_SUPPORT_TASK_IDS = 32
LEARNING_METADATA_PREFIX = "<!-- ai-orchestrator-learning-v1 "
LEARNING_METADATA_SUFFIX = " -->"


def _context_kind(path: str) -> str:
    if "/policies/" in path:
        return "policy"
    if "/skills/" in path:
        return "skill"
    return "knowledge"


def _tokens(value: str) -> set[str]:
    return {
        item.casefold()
        for item in re.findall(r"[\w.-]+", value, flags=re.UNICODE)
        if len(item) >= 2
    }


def _learning_metadata(text: str) -> dict[str, Any] | None:
    first = text.splitlines()[0] if text else ""
    if not first.startswith(LEARNING_METADATA_PREFIX) or not first.endswith(LEARNING_METADATA_SUFFIX):
        return None
    raw = first[len(LEARNING_METADATA_PREFIX):-len(LEARNING_METADATA_SUFFIX)]
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def select_context(
    context: dict[str, str],
    query: str,
    *,
    budget_bytes: int = CONTEXT_SELECTION_BYTES,
) -> tuple[dict[str, str], ContextInfluence]:
    """Select deterministic, bounded accepted context for one intake/task."""
    if budget_bytes < 1024 or budget_bytes > 65536:
        raise OrchestratorError("context selection budget must be between 1 KiB and 64 KiB")
    query_tokens = _tokens(query)
    items: list[dict[str, Any]] = []
    superseded_ids: set[str] = set()
    canonical_polarities: dict[str, set[str]] = defaultdict(set)

    for path, text in sorted(context.items()):
        raw = text.encode()
        metadata = _learning_metadata(text)
        if metadata:
            superseded_ids.update(
                item for item in metadata.get("supersedes", [])
                if isinstance(item, str)
            )
            canonical = metadata.get("canonical_key")
            polarity = metadata.get("polarity")
            if isinstance(canonical, str) and isinstance(polarity, str):
                canonical_polarities[canonical].add(polarity)
        evidence_refs: list[EvidenceRef] = []
        if metadata and isinstance(metadata.get("evidence_refs"), list):
            for value in metadata["evidence_refs"]:
                try:
                    evidence_refs.append(EvidenceRef.model_validate(value))
                except Exception:
                    evidence_refs = []
                    break
        items.append({
            "path": path,
            "text": text,
            "raw_bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "kind": _context_kind(path),
            "metadata": metadata,
            "evidence_refs": evidence_refs,
        })

    conflicting = {
        key for key, polarities in canonical_polarities.items()
        if "positive" in polarities and "negative" in polarities
    }
    seen_content: set[str] = set()
    eligible: list[dict[str, Any]] = []
    excluded = 0
    for item in items:
        metadata = item["metadata"] or {}
        proposal_id = metadata.get("proposal_id")
        canonical = metadata.get("canonical_key")
        if isinstance(proposal_id, str) and proposal_id in superseded_ids:
            excluded += 1
            continue
        if isinstance(canonical, str) and canonical in conflicting:
            # Conflicting accepted learning remains durable provenance but is not
            # silently injected into model context until an operator supersedes it.
            excluded += 1
            continue
        if item["sha256"] in seen_content:
            excluded += 1
            continue
        seen_content.add(item["sha256"])
        kind_base = {"policy": 3000, "skill": 2000, "knowledge": 1000}[item["kind"]]
        overlap = len(query_tokens & (_tokens(item["path"]) | _tokens(item["text"][:12000])))
        item["score"] = kind_base + overlap * 100
        eligible.append(item)

    kind_order = {"policy": 0, "skill": 1, "knowledge": 2}
    eligible.sort(
        key=lambda item: (
            kind_order[item["kind"]],
            -item["score"],
            item["path"],
        )
    )
    selected: dict[str, str] = {}
    entries: list[ContextInfluenceEntry] = []
    used = 0
    for item in eligible:
        if used + item["raw_bytes"] > budget_bytes:
            excluded += 1
            continue
        selected[item["path"]] = item["text"]
        used += item["raw_bytes"]
        entries.append(ContextInfluenceEntry(
            path=item["path"],
            sha256=item["sha256"],
            bytes=item["raw_bytes"],
            kind=item["kind"],
            score=item["score"],
            evidence_refs=item["evidence_refs"],
        ))

    manifest = ContextInfluence(
        query_sha256=hashlib.sha256(query.encode()).hexdigest(),
        budget_bytes=budget_bytes,
        selected_bytes=used,
        universe_items=len(items),
        excluded_items=excluded,
        entries=entries,
    )
    return selected, manifest


def context_from_influence(context: dict[str, str], influence: ContextInfluence) -> dict[str, str]:
    selected: dict[str, str] = {}
    for entry in influence.entries:
        text = context.get(entry.path)
        if text is None:
            raise OrchestratorError("accepted project context changed since influence selection")
        raw = text.encode()
        if len(raw) != entry.bytes or hashlib.sha256(raw).hexdigest() != entry.sha256:
            raise OrchestratorError("accepted project context changed since influence selection")
        selected[entry.path] = text
    if sum(len(value.encode()) for value in selected.values()) != influence.selected_bytes:
        raise OrchestratorError("context influence manifest byte count is inconsistent")
    return selected


def _artifact_ref(artifact) -> EvidenceRef | None:
    if artifact.schema_version < 2 or artifact.id is None or artifact.owner_id is None:
        return None
    return EvidenceRef(
        source="artifact",
        id=artifact.id,
        owner_id=artifact.owner_id,
        kind=artifact.kind,
        sha256=artifact.sha256,
    )


def _task_ref(state) -> EvidenceRef:
    return EvidenceRef(
        source="task",
        id=state.spec.id,
        owner_id=state.spec.id,
        kind="task_state",
        sha256=digest(state.model_dump()),
    )


def _event_ref(event: dict[str, Any]) -> EvidenceRef:
    return EvidenceRef(
        source="event",
        id=event["event_id"],
        owner_id=event.get("task_id"),
        kind=event["kind"],
        sha256=digest(event),
    )


def resolve_evidence_ref(store: Store, reference: EvidenceRef) -> dict[str, Any]:
    """Resolve and hash-check one controller-owned evidence reference."""
    if reference.source == "task":
        state = store.get(reference.id)
        if digest(state.model_dump()) != reference.sha256:
            raise OrchestratorError(f"task evidence changed: {reference.id}")
        return {"source": "task", "state": state.model_dump()}
    if reference.source == "intake":
        intake = store.get_intake(reference.id)
        if digest(intake.model_dump()) != reference.sha256:
            raise OrchestratorError(f"intake evidence changed: {reference.id}")
        return {"source": "intake", "state": intake.model_dump()}
    if reference.source == "event":
        matches = [item for item in store.events() if item["event_id"] == reference.id]
        if len(matches) != 1 or digest(matches[0]) != reference.sha256:
            raise OrchestratorError(f"event evidence changed or missing: {reference.id}")
        return {"source": "event", "event": matches[0]}
    if reference.source == "artifact":
        if reference.owner_id is None:
            raise OrchestratorError("artifact evidence requires owner_id")
        artifacts = []
        try:
            state = store.get(reference.owner_id)
            artifacts.extend(state.artifacts)
        except OrchestratorError:
            try:
                intake = store.get_intake(reference.owner_id)
            except OrchestratorError as exc:
                raise OrchestratorError(f"artifact evidence owner is missing: {reference.owner_id}") from exc
            if intake.artifact is not None:
                artifacts.append(intake.artifact)
        matches = [item for item in artifacts if item.id == reference.id]
        if len(matches) != 1:
            raise OrchestratorError(f"artifact evidence is missing or ambiguous: {reference.id}")
        artifact = matches[0]
        if artifact.sha256 != reference.sha256 or (reference.kind and artifact.kind != reference.kind):
            raise OrchestratorError(f"artifact evidence metadata changed: {reference.id}")
        return {"source": "artifact", "artifact": artifact.model_dump(), "content": store.read_artifact(artifact)}
    raise OrchestratorError("unknown evidence reference source")


def verify_proposal_evidence(store: Store, proposal: Proposal) -> None:
    if proposal.schema_version < 2:
        return
    for reference in proposal.evidence_refs:
        resolve_evidence_ref(store, reference)


def _latest_artifact(state, kind: str):
    for artifact in reversed(state.artifacts):
        if artifact.kind == kind:
            return artifact
    return None


def _all_artifacts(state, kind: str):
    return [artifact for artifact in state.artifacts if artifact.kind == kind]


def _dedupe_refs(refs: list[EvidenceRef]) -> list[EvidenceRef]:
    values: dict[tuple[str, str], EvidenceRef] = {}
    for ref in refs:
        values[(ref.source, ref.id)] = ref
    return [values[key] for key in sorted(values)]


def _proposal(
    *,
    kind: str,
    statement: str,
    statement_type: str,
    canonical_key: str,
    polarity: str,
    task_ids: set[str],
    evidence_refs: list[EvidenceRef],
    validations: int,
    reviews: int,
) -> Proposal:
    all_refs = _dedupe_refs(evidence_refs)
    all_task_ids = sorted(task_ids)
    evidence_digest = digest([item.model_dump() for item in all_refs])
    seed = {
        "kind": kind,
        "statement": statement,
        "statement_type": statement_type,
        "canonical_key": canonical_key,
        "polarity": polarity,
        "task_ids": all_task_ids,
        "evidence_digest": evidence_digest,
    }
    proposal_id = "P-L" + digest(seed)[:12]
    refs = all_refs[:MAX_CANDIDATE_EVIDENCE_REFS]
    sampled_task_ids = all_task_ids[:MAX_SUPPORT_TASK_IDS]
    return Proposal(
        schema_version=2,
        id=proposal_id,
        kind=kind,
        statement=statement,
        statement_type=statement_type,
        evidence=[f"{item.source}:{item.id}:{item.sha256[:12]}" for item in refs],
        evidence_refs=refs,
        support=LearningSupport(
            independent_task_ids=sampled_task_ids,
            independent_task_count=len(all_task_ids),
            evidence_count=len(all_refs),
            corroborating_validations=validations,
            corroborating_reviews=reviews,
        ),
        provenance=LearningProvenance(
            canonical_key=canonical_key,
            polarity=polarity,
            evidence_digest=evidence_digest,
        ),
        canonical_key=canonical_key,
    )


def load_candidates(project: Project) -> list[Proposal]:
    base = confined(project.root, ".orchestrator/knowledge/candidates")
    if not base.exists():
        return []
    result: list[Proposal] = []
    for path in sorted(base.glob("*.json")):
        if path.is_symlink() or path.stat().st_size > 1024 * 1024:
            raise OrchestratorError("learning candidate must be a bounded regular JSON file")
        result.append(
            decode_versioned_model_json(
                path.read_text(encoding="utf-8"),
                rule_key="project_learning_candidate",
                model=Proposal,
            )
        )
    return result


def _apply_relationships(generated: list[Proposal], existing: list[Proposal]) -> None:
    all_values = [*existing, *generated]
    for proposal in generated:
        if proposal.schema_version < 2 or proposal.provenance is None:
            continue
        refs = {(item.source, item.id) for item in proposal.evidence_refs}
        supersedes: set[str] = set()
        contradictions: set[str] = set()
        for other in all_values:
            if other.id == proposal.id or other.schema_version < 2 or other.provenance is None:
                continue
            if other.canonical_key != proposal.canonical_key:
                continue
            if other.provenance.polarity != proposal.provenance.polarity:
                contradictions.add(other.id)
                continue
            other_refs = {(item.source, item.id) for item in other.evidence_refs}
            if other_refs < refs or (
                other.support is not None
                and proposal.support is not None
                and other.support.evidence_count < proposal.support.evidence_count
            ):
                supersedes.add(other.id)
        proposal.supersedes = sorted(supersedes)
        proposal.contradictions = sorted(contradictions)
        if proposal.support is not None:
            proposal.support.contradiction_count = len(proposal.contradictions)


def distill(root: Path, store: Store | None = None) -> dict[str, Any]:
    """Generate deterministic non-authoritative candidates from durable evidence."""
    project = Project(root)
    project.load()
    owned_store = store is None
    store = store or Store(project)
    try:
        existing = load_candidates(project)
        events = store.events()
        events_by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for event in events:
            if isinstance(event.get("task_id"), str):
                events_by_task[event["task_id"]].append(event)

        path_signals: dict[str, list[dict[str, Any]]] = defaultdict(list)
        observation_signals: dict[str, list[dict[str, Any]]] = defaultdict(list)
        workflow_signals: dict[str, list[dict[str, Any]]] = defaultdict(list)
        provider_signals: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        validator_pass: dict[str, list[dict[str, Any]]] = defaultdict(list)
        validator_fail: dict[str, list[dict[str, Any]]] = defaultdict(list)
        recovery_signals: dict[str, list[dict[str, Any]]] = defaultdict(list)
        usage_signals: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        budget_signals: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        artifact_counts: dict[str, int] = defaultdict(int)

        for task_id in store.task_ids():
            state = store.get(task_id)
            task_reference = _task_ref(state)
            task_events = events_by_task.get(task_id, [])
            accepted_events = [event for event in task_events if event["kind"] == "task.accepted"]
            accepted_refs = [_event_ref(accepted_events[-1])] if accepted_events else []

            for artifact in state.artifacts:
                artifact_counts[artifact.kind] += 1
            for artifact in _all_artifacts(state, "validation"):
                ref = _artifact_ref(artifact)
                if ref is None:
                    continue
                value = store.read_artifact(artifact)
                if not isinstance(value, dict):
                    continue
                checks = value.get("checks")
                if not isinstance(checks, list):
                    checks = [value] if isinstance(value.get("name"), str) else []
                for check in checks:
                    if not isinstance(check, dict) or not isinstance(check.get("name"), str):
                        continue
                    signal = {"task_id": task_id, "refs": [task_reference, ref], "state": state}
                    if check.get("exit_code") == 0 and not check.get("error"):
                        validator_pass[check["name"]].append(signal)
                    else:
                        validator_fail[check["name"]].append(signal)

            for event in task_events:
                if event["kind"].startswith("recovery."):
                    recovery_signals[event["kind"]].append({
                        "task_id": task_id,
                        "refs": [task_reference, _event_ref(event)],
                    })

            usage_artifact = _latest_artifact(state, "usage")
            if usage_artifact is not None:
                value = store.read_artifact(usage_artifact)
                ref = _artifact_ref(usage_artifact)
                summary = value.get("summary") if isinstance(value, dict) else None
                if isinstance(summary, dict) and ref is not None:
                    for metric in (
                        "input_tokens", "output_tokens", "reasoning_tokens",
                        "total_tokens", "provider_elapsed_seconds", "cost",
                    ):
                        metric_value = summary.get(metric)
                        status = metric_value.get("status") if isinstance(metric_value, dict) else None
                        if status in ("known", "unknown", "unsupported"):
                            usage_signals[(metric, status)].append({
                                "task_id": task_id,
                                "refs": [task_reference, ref],
                            })

            budget_artifact = _latest_artifact(state, "budget")
            if budget_artifact is not None:
                value = store.read_artifact(budget_artifact)
                ref = _artifact_ref(budget_artifact)
                blockers = value.get("blockers") if isinstance(value, dict) else None
                if isinstance(blockers, list) and ref is not None:
                    seen_budget: set[tuple[str, str]] = set()
                    for blocker in blockers:
                        if not isinstance(blocker, dict):
                            continue
                        dimension, status = blocker.get("dimension"), blocker.get("status")
                        if not isinstance(dimension, str) or not isinstance(status, str):
                            continue
                        key = (dimension, status)
                        if key in seen_budget:
                            continue
                        seen_budget.add(key)
                        budget_signals[key].append({
                            "task_id": task_id,
                            "refs": [task_reference, ref],
                        })

            if state.status != "succeeded":
                continue
            write_artifact = _latest_artifact(state, "write_set")
            validation_artifact = _latest_artifact(state, "validation")
            review_artifact = _latest_artifact(state, "review")
            write_value = store.read_artifact(write_artifact) if write_artifact else None
            validation_value = store.read_artifact(validation_artifact) if validation_artifact else None
            review_value = store.read_artifact(review_artifact) if review_artifact else None
            final_validation_ok = (
                isinstance(validation_value, dict)
                and isinstance(validation_value.get("checks"), list)
                and bool(validation_value["checks"])
                and all(
                    isinstance(item, dict) and item.get("exit_code") == 0 and not item.get("error")
                    for item in validation_value["checks"]
                )
            )
            final_review_ok = isinstance(review_value, dict) and review_value.get("outcome") == "approved"
            refs = [task_reference, *accepted_refs]
            for artifact in (write_artifact, validation_artifact, review_artifact):
                ref = _artifact_ref(artifact) if artifact is not None else None
                if ref is not None:
                    refs.append(ref)

            if final_validation_ok and final_review_ok and isinstance(write_value, dict):
                for path in sorted(set(write_value.get("changed_paths") or [])):
                    if isinstance(path, str):
                        path_signals[path].append({"task_id": task_id, "refs": list(refs)})
                if isinstance(review_value.get("observations"), list):
                    for observation in review_value["observations"]:
                        if not isinstance(observation, str):
                            continue
                        compact = " ".join(observation.split()).strip()
                        if not compact or len(compact) > 500:
                            continue
                        key = hashlib.sha256(compact.casefold().encode()).hexdigest()
                        observation_signals[key].append({
                            "task_id": task_id, "refs": list(refs), "observation": compact
                        })
                if state.workflow_selection_source == "supervisor_proposed" and state.workflow_digest:
                    workflow_signals[state.workflow_digest].append({
                        "task_id": task_id, "refs": list(refs), "workflow_id": state.workflow_id or "task-scoped"
                    })

            provenance_artifact = _latest_artifact(state, "provider_provenance")
            if provenance_artifact is not None:
                value = store.read_artifact(provenance_artifact)
                ref = _artifact_ref(provenance_artifact)
                if isinstance(value, dict) and ref is not None and isinstance(value.get("records"), list):
                    seen: set[tuple[str, str]] = set()
                    for record in value["records"]:
                        if not isinstance(record, dict):
                            continue
                        role, family = record.get("role"), record.get("family")
                        if isinstance(role, str) and isinstance(family, str) and (role, family) not in seen:
                            seen.add((role, family))
                            provider_signals[(role, family)].append({
                                "task_id": task_id, "refs": [task_reference, ref, *accepted_refs]
                            })

        generated: list[Proposal] = []
        for path, signals in sorted(path_signals.items()):
            task_ids = {item["task_id"] for item in signals}
            if len(task_ids) < 2:
                continue
            refs = [ref for item in signals for ref in item["refs"]]
            generated.append(_proposal(
                kind="knowledge",
                statement=f"Across {len(task_ids)} independently accepted tasks, `{path}` was changed with final controller validation passing and independent review approval.",
                statement_type="observation",
                canonical_key=f"validated-path:{path}",
                polarity="positive",
                task_ids=task_ids,
                evidence_refs=refs,
                validations=len(task_ids),
                reviews=len(task_ids),
            ))

        for key, signals in sorted(observation_signals.items()):
            task_ids = {item["task_id"] for item in signals}
            if len(task_ids) < 2:
                continue
            observation = sorted({item["observation"] for item in signals})[0]
            refs = [ref for item in signals for ref in item["refs"]]
            generated.append(_proposal(
                kind="knowledge",
                statement=f"Independent accepted-task reviews repeatedly recorded this non-blocking observation: {observation}",
                statement_type="observation",
                canonical_key=f"review-observation:{key}",
                polarity="neutral",
                task_ids=task_ids,
                evidence_refs=refs,
                validations=len(task_ids),
                reviews=len(task_ids),
            ))

        for key, signals in sorted(observation_signals.items()):
            task_ids = {item["task_id"] for item in signals}
            if len(task_ids) < 3:
                continue
            observation = sorted({item["observation"] for item in signals})[0]
            refs = [ref for item in signals for ref in item["refs"]]
            generated.append(_proposal(
                kind="skill",
                statement=(
                    f"Across {len(task_ids)} independently accepted tasks, reviewers repeatedly recorded: "
                    f"{observation} Consider whether this should become reusable project guidance."
                ),
                statement_type="recommendation",
                canonical_key=f"skill-review-observation:{key}",
                polarity="neutral",
                task_ids=task_ids,
                evidence_refs=refs,
                validations=len(task_ids),
                reviews=len(task_ids),
            ))

        for workflow_digest, signals in sorted(workflow_signals.items()):
            task_ids = {item["task_id"] for item in signals}
            if len(task_ids) < 2:
                continue
            refs = [ref for item in signals for ref in item["refs"]]
            workflow_id = sorted({item["workflow_id"] for item in signals})[0]
            generated.append(_proposal(
                kind="workflow",
                statement=(
                    f"Task-scoped workflow `{workflow_id}` ({workflow_digest[:12]}) completed successfully "
                    f"across {len(task_ids)} accepted tasks. Consider an explicit workflow-save review before reuse."
                ),
                statement_type="recommendation",
                canonical_key=f"workflow:{workflow_digest}",
                polarity="positive",
                task_ids=task_ids,
                evidence_refs=refs,
                validations=len(task_ids),
                reviews=len(task_ids),
            ))

        for (role, family), signals in sorted(provider_signals.items()):
            task_ids = {item["task_id"] for item in signals}
            if len(task_ids) < 3:
                continue
            refs = [ref for item in signals for ref in item["refs"]]
            generated.append(_proposal(
                kind="knowledge",
                statement=(
                    f"Controller provenance shows successful accepted tasks repeatedly dispatched role "
                    f"`{role}` through provider family `{family}` across {len(task_ids)} tasks. "
                    "This observation does not grant or select a provider."
                ),
                statement_type="observation",
                canonical_key=f"provider-history:{role}:{family}",
                polarity="neutral",
                task_ids=task_ids,
                evidence_refs=refs,
                validations=0,
                reviews=0,
            ))

        validator_names = sorted(set(validator_pass) | set(validator_fail))
        for name in validator_names:
            for polarity, values in (("positive", validator_pass[name]), ("negative", validator_fail[name])):
                task_ids = {item["task_id"] for item in values}
                if len(task_ids) < 2:
                    continue
                refs = [ref for item in values for ref in item["refs"]]
                outcome = "passed" if polarity == "positive" else "failed or reported an integrity/error condition"
                generated.append(_proposal(
                    kind="knowledge",
                    statement=f"Controller validator `{name}` {outcome} across {len(task_ids)} independent task records.",
                    statement_type="observation",
                    canonical_key=f"validator-history:{name}",
                    polarity=polarity,
                    task_ids=task_ids,
                    evidence_refs=refs,
                    validations=len(task_ids),
                    reviews=0,
                ))

        for kind, signals in sorted(recovery_signals.items()):
            task_ids = {item["task_id"] for item in signals}
            if len(task_ids) < 2:
                continue
            refs = [ref for item in signals for ref in item["refs"]]
            generated.append(_proposal(
                kind="knowledge",
                statement=f"Controller recovery outcome `{kind}` occurred across {len(task_ids)} independent tasks.",
                statement_type="observation",
                canonical_key=f"recovery-history:{kind}",
                polarity="neutral",
                task_ids=task_ids,
                evidence_refs=refs,
                validations=0,
                reviews=0,
            ))

        for (metric, status), signals in sorted(usage_signals.items()):
            task_ids = {item["task_id"] for item in signals}
            if len(task_ids) < 3:
                continue
            refs = [ref for item in signals for ref in item["refs"]]
            generated.append(_proposal(
                kind="knowledge",
                statement=(
                    f"Controller usage evidence reports `{metric}` telemetry as `{status}` across "
                    f"{len(task_ids)} independent task records. Missing telemetry must not be inferred or zero-filled."
                ),
                statement_type="observation",
                canonical_key=f"usage-telemetry:{metric}",
                polarity="positive" if status == "known" else "negative",
                task_ids=task_ids,
                evidence_refs=refs,
                validations=0,
                reviews=0,
            ))

        for (dimension, status), signals in sorted(budget_signals.items()):
            task_ids = {item["task_id"] for item in signals}
            if len(task_ids) < 2:
                continue
            refs = [ref for item in signals for ref in item["refs"]]
            generated.append(_proposal(
                kind="policy",
                statement=(
                    f"Controller budget evidence repeatedly reported `{dimension}:{status}` across "
                    f"{len(task_ids)} independent tasks. Consider an explicit operator review of the relevant "
                    "budget/telemetry policy; this candidate does not change any limit."
                ),
                statement_type="recommendation",
                canonical_key=f"budget-pattern:{dimension}:{status}",
                polarity="neutral",
                task_ids=task_ids,
                evidence_refs=refs,
                validations=0,
                reviews=0,
            ))

        _apply_relationships(generated, existing)
        existing_by_id = {item.id: item for item in existing}
        created: list[str] = []
        retained: list[str] = []
        rejected_suppressed: list[str] = []
        for proposal in sorted(generated, key=lambda item: item.id):
            current = existing_by_id.get(proposal.id)
            if current is not None:
                retained.append(current.id)
                if current.status == "rejected":
                    rejected_suppressed.append(current.id)
                continue
            path = confined(project.root, f".orchestrator/knowledge/candidates/{proposal.id}.json")
            atomic_write(path, proposal.model_dump_json(indent=2) + "\n")
            created.append(proposal.id)

        return {
            "schema_version": 1,
            "distillation_version": DISTILLATION_VERSION,
            "task_count": len(store.task_ids()),
            "event_count": len(events),
            "artifact_counts": dict(sorted(artifact_counts.items())),
            "candidate_patterns": len(generated),
            "created": created,
            "retained": retained,
            "rejected_suppressed": rejected_suppressed,
            "authority": "candidates are non-authoritative until explicit operator promotion and required profile re-trust",
        }
    finally:
        if owned_store:
            store.close()


def report(project: Project, store: Store, context: dict[str, str]) -> dict[str, Any]:
    candidates = load_candidates(project)
    statuses: dict[str, int] = defaultdict(int)
    kinds: dict[str, int] = defaultdict(int)
    for candidate in candidates:
        statuses[candidate.status] += 1
        kinds[candidate.kind] += 1
    total_bytes = sum(len(value.encode()) for value in context.values())
    return {
        "schema_version": 1,
        "distillation_version": DISTILLATION_VERSION,
        "context_selector_version": CONTEXT_SELECTOR_VERSION,
        "selection_budget_bytes": CONTEXT_SELECTION_BYTES,
        "accepted_context_universe": {
            "items": len(context),
            "bytes": total_bytes,
            "active_prompt_limit_bytes": 65536,
        },
        "candidates": {
            "total": len(candidates),
            "by_status": dict(sorted(statuses.items())),
            "by_kind": dict(sorted(kinds.items())),
        },
        "durable_evidence": {
            "tasks": len(store.task_ids()),
            "intakes": len(store.intake_ids()),
            "events": store.event_count(),
        },
        "governance": {
            "candidate_generation_grants_authority": False,
            "promotion_requires_operator": True,
            "accepted_context_requires_profile_trust": True,
            "rejected_exact_evidence_reappears": False,
            "context_selection": "deterministic bounded selection; superseded/contradictory accepted learning is excluded",
        },
    }
