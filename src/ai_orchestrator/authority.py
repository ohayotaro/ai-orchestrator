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
    # Workflow authority must still compile under the proposed profile.
    workflow_registry(profile)
    resolver = CapabilityResolver(profile, engine.registry)
    roles: dict[str, Any] = {}
    implementer_family: str | None = None
    for role in ("supervisor", "planner", "implementer", "reviewer"):
        if role != "supervisor" and role not in profile.roles:
            continue
        exclude = (
            {implementer_family}
            if role == "reviewer"
            and profile.policy.cross_provider_review
            and implementer_family
            else None
        )
        resolution = resolver.resolve(role, exclude_families=exclude)
        roles[role] = resolution.model_dump()
        if role == "implementer":
            implementer_family = resolution.family
    return {"roles": roles, "providers": resolver.report()["providers"]}


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


def provider_change_preview(engine, provider: str, adapter: str) -> dict[str, Any]:
    provider = identifier(provider)
    adapter = identifier(adapter)
    current = _assert_current_trusted(engine)
    active_tasks = engine.store.active_task_ids()
    active_intakes = engine.store.active_intake_ids()
    if provider not in engine.profile.providers:
        raise OrchestratorError(f"unknown provider slot: {provider}")
    if adapter not in engine.registry:
        raise OrchestratorError(f"adapter is not installed: {adapter}")
    before = engine.profile.providers[provider]
    if before.adapter == adapter:
        raise OrchestratorError(f"provider {provider} already uses adapter {adapter}")

    path = _config_path(engine.project)
    raw = load_yaml(path)
    if not isinstance(raw, dict) or not isinstance(raw.get("providers"), dict):
        raise OrchestratorError("project config has no provider map")
    proposed_raw = deepcopy(raw)
    slot = proposed_raw["providers"].get(provider)
    if not isinstance(slot, dict):
        raise OrchestratorError(f"provider config is malformed: {provider}")
    slot["adapter"] = adapter

    # These values are vendor/CLI specific. Carrying them across an adapter
    # switch can silently point at the wrong executable/model/effort contract.
    reset_fields: dict[str, Any] = {}
    for key in ("executable", "model", "effort"):
        if key in slot and slot[key] is not None:
            reset_fields[key] = slot[key]
        slot.pop(key, None)

    proposed = Profile.model_validate(proposed_raw)
    report = _validate_proposed_profile(engine, proposed)
    proposed_digest = Project.fingerprint(proposed, engine.context)
    if proposed_digest == current:
        raise OrchestratorError("provider change did not alter profile authority")

    after = proposed.providers[provider]
    change = {
        "kind": "provider_adapter",
        "provider": provider,
        "adapter": adapter,
        "current_profile_digest": current,
        "proposed_profile_digest": proposed_digest,
        "before": before.model_dump(),
        "after": after.model_dump(),
        "reset_adapter_specific_fields": sorted(reset_fields),
    }
    change_id = "PC-" + digest(change)[:32]
    return {
        "change_id": change_id,
        "change": change,
        "resolution_after": report,
        "ready": not (active_tasks or active_intakes),
        "blocked_by": {
            "task_ids": active_tasks,
            "intake_ids": active_intakes,
        },
        "trust_effect": "HumanGate approval applies the exact config change and trusts only the resulting profile digest.",
        "task_effect": (
            "Provider change requires no active task/intake bindings. Use binding-cleanup preview + its own "
            "HumanGate to abandon/withdraw selected stale or unwanted bindings; cleanup never rolls back workspace changes."
        ),
    }


def apply_provider_change(
    engine,
    provider: str,
    adapter: str,
    expected_current_digest: str,
    expected_proposed_digest: str,
    actor: str,
) -> dict[str, Any]:
    if not actor.strip():
        raise OrchestratorError("an approval actor is required")
    preview = provider_change_preview(engine, provider, adapter)
    if not preview["ready"]:
        blockers = preview["blocked_by"]
        raise OrchestratorError(
            "provider authority cannot change while task/intake bindings are active: "
            f"tasks={','.join(blockers['task_ids']) or '-'}; "
            f"intakes={','.join(blockers['intake_ids']) or '-'}"
        )
    change = preview["change"]
    if (
        change["current_profile_digest"] != expected_current_digest
        or change["proposed_profile_digest"] != expected_proposed_digest
    ):
        raise OrchestratorError("provider-change scope changed; request a fresh confirmation")

    path = _config_path(engine.project)
    old_text = path.read_text(encoding="utf-8")
    raw = load_yaml(path)
    proposed_raw = deepcopy(raw)
    slot = proposed_raw["providers"][provider]
    slot["adapter"] = adapter
    for key in ("executable", "model", "effort"):
        slot.pop(key, None)
    proposed = Profile.model_validate(proposed_raw)
    new_text = yaml.safe_dump(proposed_raw, sort_keys=False)

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

    atomic_write(path, new_text)
    try:
        _, actual_digest, _ = engine.project.load()
        if actual_digest != expected_proposed_digest:
            raise OrchestratorError("provider change produced an unexpected profile digest")
    except Exception:
        # Best effort restore for a deterministic write/validation mismatch.
        # A process crash after atomic replacement still leaves the profile
        # untrusted, which is the safe failure mode.
        atomic_write(path, old_text)
        raise

    engine.store.trust(expected_proposed_digest, actor)
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
        "change_id": preview["change_id"],
        "provider": provider,
        "adapter": adapter,
        "previous_profile_digest": expected_current_digest,
        "trusted_profile": expected_proposed_digest,
        "profile_retrust_required": False,
    }
