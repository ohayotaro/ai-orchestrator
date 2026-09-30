"""Evidence-backed promotion of task-scoped workflows into trusted project templates.

Agents may propose task-scoped DAGs, but only an operator can persist one into
config.yaml. Promotion is intentionally separate from task start/approval and
invalidates the trusted profile digest until the operator re-trusts it.
"""

from __future__ import annotations

from typing import Any

import yaml

from .models import OrchestratorError, Profile, WorkflowProvenance, WorkflowSpec, identifier
from .project import atomic_write, confined, digest, load_yaml
from .workflow import compile_workflow


def _candidate(engine: Any, intake_id: str, template_id: str, *, replace: bool) -> dict[str, Any]:
    identifier(intake_id)
    template_id = identifier(template_id)
    intake = engine.store.get_intake(intake_id)
    if intake.workflow_spec is None or intake.workflow_source != "supervisor_proposed":
        raise OrchestratorError("intake has no Supervisor-authored task-scoped workflow to save")
    state = engine.store.get(intake.task_id)
    engine._check(state)
    if state.intake_id != intake.id or state.workflow_spec is None:
        raise OrchestratorError("task does not carry the intake's task-scoped workflow")
    if state.status != "succeeded" or state.reviewed_snapshot is None:
        raise OrchestratorError("workflow templates may be saved only after successful reviewed acceptance")
    compiled_source = engine.workflow_for_state(state)
    if compiled_source.digest != intake.workflow_digest:
        raise OrchestratorError("task/intake workflow provenance disagrees; do not save it")

    existing = engine.profile.workflows.get(template_id)
    if template_id in engine.workflow_registry and existing is None:
        raise OrchestratorError("built-in workflow IDs cannot be replaced by saved templates")
    if existing is not None and not replace:
        raise OrchestratorError("project workflow already exists; inspect it and use --replace for an explicit revision")
    if existing is None and replace:
        raise OrchestratorError("--replace requires an existing project workflow template")

    parent_digest = None
    version = 1
    if existing is not None:
        parent_digest = engine.workflow_for_ref(template_id).digest
        version = existing.template_version + 1

    # Rename the task-scoped proposal for reusable registry identity. Provenance
    # and the operator identity are attached only during the actual save.
    reusable = state.workflow_spec.model_copy(update={
        "id": template_id,
        "template_version": version,
        "provenance": None,
    })
    compiled_target = compile_workflow(
        reusable, cross_provider_review=engine.profile.policy.cross_provider_review,
    )
    payload = {
        "schema_version": 1,
        "intake_id": intake.id,
        "task_id": state.spec.id,
        "task_status": state.status,
        "reviewed_snapshot": state.reviewed_snapshot,
        "source_workflow_id": state.workflow_id,
        "source_workflow_digest": compiled_source.digest,
        "template_id": template_id,
        "template_version": version,
        "template_digest": compiled_target.digest,
        "parent_template_digest": parent_digest,
        "replace": replace,
        "profile_digest": engine.profile_digest,
        "workflow": reusable.model_dump(),
        "authority_change": "project profile mutation; re-trust required after save",
    }
    return payload


def candidate(engine: Any, intake_id: str, template_id: str, *, replace: bool = False) -> dict[str, Any]:
    payload = _candidate(engine, intake_id, template_id, replace=replace)
    return {**payload, "scope": digest(payload)}


def save(engine: Any, intake_id: str, template_id: str, scope: str, actor: str, *,
         replace: bool = False) -> dict[str, Any]:
    if not actor.strip():
        raise OrchestratorError("workflow template save requires an operator actor")
    with engine.project.lock():
        current = engine.project.load()[1]
        if current != engine.profile_digest or not engine.store.trusted(current):
            raise OrchestratorError("profile changed or is untrusted; inspect/re-trust before saving a workflow template")
        payload = _candidate(engine, intake_id, template_id, replace=replace)
        if scope != digest(payload):
            raise OrchestratorError("workflow template candidate changed; inspect the exact current candidate before saving")

        source = WorkflowSpec.model_validate(payload["workflow"])
        provenance = WorkflowProvenance(
            source="supervisor_evidence",
            intake_id=payload["intake_id"],
            task_id=payload["task_id"],
            source_workflow_digest=payload["source_workflow_digest"],
            reviewed_snapshot=payload["reviewed_snapshot"],
            saved_by=actor,
            parent_template_digest=payload["parent_template_digest"],
        )
        persisted = source.model_copy(update={"provenance": provenance})
        compile_workflow(persisted, cross_provider_review=engine.profile.policy.cross_provider_review)

        config_path = confined(engine.project.root, ".orchestrator/config.yaml")
        raw = load_yaml(config_path)
        workflows = raw.setdefault("workflows", {})
        if not isinstance(workflows, dict):
            raise OrchestratorError("project workflow configuration is not a mapping")
        workflows[payload["template_id"]] = persisted.model_dump(exclude_none=True)
        Profile.model_validate(raw)  # Validate the complete future authority before writing.
        atomic_write(config_path, yaml.safe_dump(raw, sort_keys=False))
        _, new_digest, _ = engine.project.load()
        return {
            **payload,
            "workflow": persisted.model_dump(),
            "saved_by": actor,
            "previous_profile_digest": engine.profile_digest,
            "new_profile_digest": new_digest,
            "profile_retrust_required": new_digest != engine.profile_digest,
        }
