"""Bounded authority changes proposed by agents and applied only after HumanGate."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

import yaml

from .capabilities import CapabilityResolver
from .models import OrchestratorError, Profile, identifier
from .project import Project, atomic_write, confined, digest, load_yaml
from .workflow import workflow_registry


def _config_path(project: Project):
    return confined(project.root, ".orchestrator/config.yaml")


def _assert_current_trusted(engine) -> str:
    current = engine.project.load()[1]
    if current != engine.profile_digest or not engine.store.trusted(current):
        raise OrchestratorError(
            "profile changed or untrusted; authority change requires the currently trusted profile"
        )
    return current


def _validate_proposed_profile(engine, profile: Profile) -> dict[str, Any]:
    """Validate persistent provider authority without pre-solving task runtime policy.

    v0.9.1 review independence may be satisfied by task/node-scoped explicit model
    choices after Provider Resolution. Adapter changes also reset vendor-specific
    model/effort fields. Therefore a profile change must validate that every role
    can resolve to a capable provider, but it must not reject a same-family
    implementer/reviewer pair before the task's Model Variant Resolution exists.
    Runtime preflight remains the fail-closed enforcement point.
    """
    workflow_registry(profile)
    resolver = CapabilityResolver(profile, engine.registry)
    roles: dict[str, Any] = {}
    compatibility: dict[str, Any] = {}
    for role in ("supervisor", "planner", "implementer", "reviewer"):
        if role != "supervisor" and role not in profile.roles:
            continue
        resolution = resolver.resolve(role)
        roles[role] = resolution.model_dump()
        adapter = engine.registry.get(resolution.adapter)
        role_compatibility = getattr(adapter, "role_compatibility", None) if adapter is not None else None
        compatibility[role] = (
            role_compatibility(role)
            if callable(role_compatibility)
            else {
                "status": "supported",
                "role": role,
                "adapter": resolution.adapter,
                "requires_native_scoped_permissions": False,
                "orchestrator_attests_permissions_sufficient": True,
                "limitations": [],
            }
        )
    return {
        "roles": roles,
        "providers": resolver.report()["providers"],
        "role_compatibility": compatibility,
        "review_independence": (
            "task_preflight: different provider family or explicit distinct model IDs"
            if profile.policy.cross_provider_review
            else "disabled"
        ),
    }


def binding_cleanup_preview(
    engine, task_ids: list[str], intake_ids: list[str]
) -> dict[str, Any]:
    _assert_current_trusted(engine)
    if not task_ids and not intake_ids:
        raise OrchestratorError("binding cleanup requires at least one task or intake")
    task_ids = [identifier(value) for value in task_ids]
    intake_ids = [identifier(value) for value in intake_ids]
    if len(task_ids) != len(set(task_ids)) or len(intake_ids) != len(set(intake_ids)):
        raise OrchestratorError("binding cleanup IDs must be unique")

    tasks: list[dict[str, Any]] = []
    for task_id in sorted(task_ids):
        state = engine.store.get(task_id)
        if state.status == "running":
            raise OrchestratorError(
                f"running task cannot be abandoned: {task_id}; stop/recover active execution first"
            )
        if state.status in ("succeeded", "blocked", "failed", "cancelled", "abandoned"):
            raise OrchestratorError(f"task is already terminal: {task_id} ({state.status})")
        tasks.append({
            "task_id": task_id,
            "status": state.status,
            "phase": state.phase,
            "attempt": state.attempt,
            "profile_digest": state.profile_digest,
            "intake_id": state.intake_id,
            "artifact_kinds": [artifact.kind for artifact in state.artifacts],
            "reviewed_snapshot": state.reviewed_snapshot,
            "has_provider_permission_grants": bool(state.provider_permission_grants),
            "state_digest": digest(state.model_dump()),
        })

    intakes: list[dict[str, Any]] = []
    for intake_id in sorted(intake_ids):
        intake = engine.store.get_intake(intake_id)
        if intake.status == "running":
            raise OrchestratorError(
                f"running intake cannot be withdrawn: {intake_id}; wait for Supervisor execution to finish"
            )
        if intake.status not in ("proposed", "needs_clarification"):
            raise OrchestratorError(
                f"intake cannot be withdrawn: {intake_id} ({intake.status})"
            )
        intakes.append({
            "intake_id": intake_id,
            "task_id": intake.task_id,
            "status": intake.status,
            "round": intake.round,
            "profile_digest": intake.profile_digest,
            "workspace_snapshot": intake.workspace_snapshot,
            "state_digest": digest(intake.model_dump()),
        })

    payload = {
        "kind": "binding_cleanup",
        "tasks": tasks,
        "intakes": intakes,
        "workspace_snapshot": engine.project.snapshot(),
        "current_profile_digest": engine.profile_digest,
        "workspace_rollback": False,
    }
    cleanup_id = "BC-" + digest(payload)[:32]
    return {
        "cleanup_id": cleanup_id,
        "task_ids": [item["task_id"] for item in tasks],
        "intake_ids": [item["intake_id"] for item in intakes],
        "tasks": tasks,
        "intakes": intakes,
        "scope": digest(payload),
        "effect": (
            "Selected unfinished tasks become abandoned and selected unconsumed intakes become withdrawn. "
            "This does not delete history, artifacts, task files, or roll back any existing workspace changes."
        ),
        "workspace_rollback": False,
    }


def apply_binding_cleanup(
    engine,
    task_ids: list[str],
    intake_ids: list[str],
    expected_scope: str,
    actor: str,
) -> dict[str, Any]:
    preview = binding_cleanup_preview(engine, task_ids, intake_ids)
    if preview["scope"] != expected_scope:
        raise OrchestratorError("binding-cleanup scope changed; request a fresh confirmation")
    result = engine.store.cleanup_bindings(
        preview["task_ids"],
        preview["intake_ids"],
        actor,
        "Abandoned/withdrawn by host-confirmed binding cleanup. Existing workspace changes were not rolled back.",
    )
    return {
        "cleanup_id": preview["cleanup_id"],
        "abandoned_tasks": result["task_ids"],
        "withdrawn_intakes": result["intake_ids"],
        "workspace_rollback": False,
    }


def provider_change_set_preview(engine, changes: dict[str, str]) -> dict[str, Any]:
    current = _assert_current_trusted(engine)
    if not changes:
        raise OrchestratorError("provider change-set requires at least one provider adapter change")
    if len(changes) > 16:
        raise OrchestratorError("provider change-set exceeds 16 provider slots")

    normalized: dict[str, str] = {}
    for provider, adapter in changes.items():
        provider_id = identifier(provider)
        adapter_id = identifier(adapter)
        if provider_id in normalized:
            raise OrchestratorError(f"duplicate provider slot in change-set: {provider_id}")
        normalized[provider_id] = adapter_id

    active_tasks = engine.store.active_task_ids()
    active_intakes = engine.store.active_intake_ids()
    path = _config_path(engine.project)
    raw = load_yaml(path)
    if not isinstance(raw, dict) or not isinstance(raw.get("providers"), dict):
        raise OrchestratorError("project config has no provider map")
    proposed_raw = deepcopy(raw)

    records: list[dict[str, Any]] = []
    for provider, adapter in sorted(normalized.items()):
        if provider not in engine.profile.providers:
            raise OrchestratorError(f"unknown provider slot: {provider}")
        if adapter not in engine.registry:
            raise OrchestratorError(f"adapter is not installed: {adapter}")
        before = engine.profile.providers[provider]
        if before.adapter == adapter:
            raise OrchestratorError(f"provider {provider} already uses adapter {adapter}")

        slot = proposed_raw["providers"].get(provider)
        if not isinstance(slot, dict):
            raise OrchestratorError(f"provider config is malformed: {provider}")
        slot["adapter"] = adapter
        reset_fields: list[str] = []
        for key in ("executable", "model", "effort"):
            if key in slot and slot[key] is not None:
                reset_fields.append(key)
            slot.pop(key, None)
        records.append({
            "provider": provider,
            "adapter": adapter,
            "before": before.model_dump(),
            "reset_adapter_specific_fields": sorted(reset_fields),
        })

    # Validate only the final, atomic profile. This deliberately does not
    # validate intermediate per-slot states, so policy-valid swaps are possible.
    proposed = Profile.model_validate(proposed_raw)
    report = _validate_proposed_profile(engine, proposed)
    proposed_digest = Project.fingerprint(proposed, engine.context)
    if proposed_digest == current:
        raise OrchestratorError("provider change-set did not alter profile authority")

    for record in records:
        record["after"] = proposed.providers[record["provider"]].model_dump()

    authority = {
        "kind": "provider_adapter_change_set",
        "changes": records,
        "current_profile_digest": current,
        "proposed_profile_digest": proposed_digest,
    }
    change_id = "PCS-" + digest(authority)[:32]
    return {
        "change_id": change_id,
        "change_set": authority,
        "changes": records,
        "resolution_after": report,
        "ready": not (active_tasks or active_intakes),
        "blocked_by": {"task_ids": active_tasks, "intake_ids": active_intakes},
        "trust_effect": "HumanGate approval atomically applies the exact provider change-set and trusts only the resulting profile digest.",
        "task_effect": (
            "Provider authority changes require no active task/intake bindings. "
            "Binding cleanup remains a separate HumanGate and never rolls back workspace changes."
        ),
    }


def apply_provider_change_set(
    engine,
    changes: dict[str, str],
    expected_current_digest: str,
    expected_proposed_digest: str,
    actor: str,
) -> dict[str, Any]:
    if not actor.strip():
        raise OrchestratorError("an approval actor is required")
    preview = provider_change_set_preview(engine, changes)
    if not preview["ready"]:
        blockers = preview["blocked_by"]
        raise OrchestratorError(
            "provider authority cannot change while task/intake bindings are active: "
            f"tasks={','.join(blockers['task_ids']) or '-'}; "
            f"intakes={','.join(blockers['intake_ids']) or '-'}"
        )
    change_set = preview["change_set"]
    if (
        change_set["current_profile_digest"] != expected_current_digest
        or change_set["proposed_profile_digest"] != expected_proposed_digest
    ):
        raise OrchestratorError("provider change-set scope changed; request a fresh confirmation")

    path = _config_path(engine.project)
    old_text = path.read_text(encoding="utf-8")
    raw = load_yaml(path)
    proposed_raw = deepcopy(raw)
    for provider, adapter in sorted(changes.items()):
        slot = proposed_raw["providers"][provider]
        slot["adapter"] = adapter
        for key in ("executable", "model", "effort"):
            slot.pop(key, None)
    proposed = Profile.model_validate(proposed_raw)
    # Re-run final semantic validation immediately before effect.
    _validate_proposed_profile(engine, proposed)
    new_text = yaml.safe_dump(proposed_raw, sort_keys=False)

    event_changes = [
        {"provider": item["provider"], "from_adapter": item["before"]["adapter"], "to_adapter": item["after"]["adapter"]}
        for item in preview["changes"]
    ]
    with engine.store.db:
        engine.store._event(
            None,
            "profile_change_set.intent",
            {
                "change_id": preview["change_id"],
                "changes": event_changes,
                "from_digest": expected_current_digest,
                "to_digest": expected_proposed_digest,
                "actor": actor,
            },
        )

    atomic_write(path, new_text)
    try:
        _, actual_digest, _ = engine.project.load()
        if actual_digest != expected_proposed_digest:
            raise OrchestratorError("provider change-set produced an unexpected profile digest")
    except Exception:
        atomic_write(path, old_text)
        raise

    engine.store.trust(expected_proposed_digest, actor)
    with engine.store.db:
        engine.store._event(
            None,
            "profile_change_set.applied",
            {
                "change_id": preview["change_id"],
                "changes": event_changes,
                "from_digest": expected_current_digest,
                "to_digest": expected_proposed_digest,
                "actor": actor,
            },
        )
    return {
        "change_id": preview["change_id"],
        "changes": event_changes,
        "previous_profile_digest": expected_current_digest,
        "trusted_profile": expected_proposed_digest,
        "profile_retrust_required": False,
    }


def provider_change_preview(engine, provider: str, adapter: str) -> dict[str, Any]:
    """Backward-compatible single-slot wrapper around atomic change-sets."""
    result = provider_change_set_preview(engine, {provider: adapter})
    item = result["changes"][0]
    change = {
        "kind": "provider_adapter",
        "provider": item["provider"],
        "adapter": item["adapter"],
        "current_profile_digest": result["change_set"]["current_profile_digest"],
        "proposed_profile_digest": result["change_set"]["proposed_profile_digest"],
        "before": item["before"],
        "after": item["after"],
        "reset_adapter_specific_fields": item["reset_adapter_specific_fields"],
    }
    return {
        **result,
        "change": change,
    }


def apply_provider_change(
    engine,
    provider: str,
    adapter: str,
    expected_current_digest: str,
    expected_proposed_digest: str,
    actor: str,
) -> dict[str, Any]:
    """Backward-compatible single-slot wrapper around atomic change-sets."""
    preview = provider_change_preview(engine, provider, adapter)
    with engine.store.db:
        engine.store._event(
            None,
            "profile_change.intent",
            {
                "change_id": preview["change_id"],
                "provider": provider,
                "adapter": adapter,
                "from_digest": expected_current_digest,
                "to_digest": expected_proposed_digest,
                "actor": actor,
            },
        )
    result = apply_provider_change_set(
        engine,
        {provider: adapter},
        expected_current_digest,
        expected_proposed_digest,
        actor,
    )
    with engine.store.db:
        engine.store._event(
            None,
            "profile_change.applied",
            {
                "change_id": preview["change_id"],
                "provider": provider,
                "adapter": adapter,
                "from_digest": expected_current_digest,
                "to_digest": expected_proposed_digest,
                "actor": actor,
            },
        )
    return {
        **result,
        "provider": provider,
        "adapter": adapter,
    }
