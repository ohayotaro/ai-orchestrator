"""v0.8 adaptive task-scoped orchestration and evidence-backed templates."""
from __future__ import annotations

import json

import pytest
import yaml

from ai_orchestrator.engine import Engine
from ai_orchestrator.human_gates import HumanGateBroker
from ai_orchestrator.models import OrchestratorError, WorkflowSpec
from ai_orchestrator.project import Project
from ai_orchestrator.service import ApplicationService
from ai_orchestrator.supervisor import Supervisor
from ai_orchestrator import workflow_templates
from test_v02_supervisor import IntakeAdapter


def workflow_payload(workflow_id: str = "adaptive-flow", *, isolated_path: str | None = None):
    implement = {
        "id": "implement",
        "kind": "agent",
        "role": "implementer",
        "run_for": "write",
        "depends_on": ["plan"],
        "inputs": [{"artifact": "plan", "type": "plan"}],
        "outputs": [
            {"name": "implementation", "type": "implementation"},
            {"name": "write_set", "type": "write_set"},
        ],
        "gate_before": "execution",
        "writes": "task_allowed_paths",
    }
    if isolated_path is not None:
        implement.update(workspace="isolated", write_paths=[isolated_path])
    return {
        "schema_version": 1,
        "id": workflow_id,
        "nodes": [
            {
                "id": "plan",
                "kind": "agent",
                "role": "planner",
                "run_for": "all",
                "outputs": [{"name": "plan", "type": "plan"}],
            },
            implement,
            {
                "id": "validate",
                "kind": "validator",
                "run_for": "write",
                "depends_on": ["implement"],
                "inputs": [
                    {"artifact": "implementation", "type": "implementation"},
                    {"artifact": "write_set", "type": "write_set"},
                ],
                "outputs": [{"name": "validation", "type": "validation"}],
            },
            {
                "id": "review",
                "kind": "agent",
                "role": "reviewer",
                "run_for": "write",
                "depends_on": ["validate"],
                "independent_of": ["implement"],
                "inputs": [
                    {"artifact": "validation", "type": "validation"},
                    {"artifact": "write_set", "type": "write_set"},
                ],
                "outputs": [{"name": "review", "type": "review"}],
            },
        ],
        "repair_on": "review",
        "repair_from": "implement",
    }


def proposed_result(workflow=None):
    return {
        "outcome": "proposed",
        "summary": "Use task-scoped orchestration",
        "task": {
            "goal": "Produce a result",
            "acceptance": ["A result exists"],
            "risk": "T2",
            "validators": ["check"],
            "external_effects": False,
            "allowed_paths": ["result.txt"],
            "capabilities": {},
            "workflow_ref": None,
            **({"workflow": workflow} if workflow is not None else {}),
        },
        "questions": [],
    }


def registry(reasoning, engineering):
    return {"claude": reasoning, "codex": engineering}


def complete_proposed_workflow(workspace, *, workflow=None, configure=None):
    if configure is not None:
        configure(workspace)
    reasoning, engineering = IntakeAdapter("anthropic"), IntakeAdapter("openai")
    reasoning.next_result = proposed_result(workflow or workflow_payload())
    engine = Engine(workspace, registry(reasoning, engineering))
    engine.trust("operator")
    supervisor = Supervisor(engine)
    intake = supervisor.ask("Do the task using the structure that best fits", task_id="adaptive-task")
    assert intake.status == "proposed", intake.error
    state = supervisor.start(intake.id, supervisor.scope(intake), "operator")
    state = engine.run(state.spec.id)
    assert state.status == "awaiting_approval", state.error
    engine.approve(state.spec.id, engine.approval_scope(state), "operator")
    state = engine.run(state.spec.id)
    assert state.status == "awaiting_acceptance", state.error
    state = engine.accept(state.spec.id, "operator")
    assert state.status == "succeeded"
    return engine, supervisor, intake, state, reasoning, engineering


def test_supervisor_can_author_task_scoped_workflow_without_profile_mutation(workspace):
    config = workspace / ".orchestrator/config.yaml"
    before_bytes = config.read_bytes()
    before_digest = Project(workspace).load()[1]
    reasoning, engineering = IntakeAdapter("anthropic"), IntakeAdapter("openai")
    reasoning.next_result = proposed_result(workflow_payload())
    engine = Engine(workspace, registry(reasoning, engineering))
    try:
        engine.trust("operator")
        supervisor = Supervisor(engine)
        intake = supervisor.ask("Split this task using the structure that best fits", task_id="adaptive-task")

        assert intake.status == "proposed", intake.error
        assert intake.schema_version == 6
        assert intake.workflow_source == "supervisor_proposed"
        assert intake.workflow_ref == "adaptive-flow"
        assert intake.workflow_spec is not None
        assert intake.workflow_digest == engine.compile_proposed_workflow(intake.workflow_spec).digest
        assert config.read_bytes() == before_bytes
        assert Project(workspace).load()[1] == before_digest
        assert engine.store.trusted(before_digest)

        broker = HumanGateBroker(ApplicationService(workspace), "session", {"name": "test", "version": "1"})
        try:
            captured = broker.capture(engine, "start", intake.id)
            preview = captured["preview"]
            assert preview["workflow_source"] == "supervisor_proposed"
            assert preview["workflow_persistence"].startswith("task_scoped_only")
            assert preview["workflow"]["id"] == "adaptive-flow"
            assert preview["workflow"]["source"] == "task_scoped_supervisor_proposal"
        finally:
            broker.close()

        state = supervisor.start(intake.id, supervisor.scope(intake), "operator")
        assert state.schema_version == 9
        assert state.workflow_selection_source == "supervisor_proposed"
        assert state.workflow_spec == intake.workflow_spec

        state = engine.run(state.spec.id)
        assert state.status == "awaiting_approval", state.error
        engine.approve(state.spec.id, engine.approval_scope(state), "operator")
        state = engine.run(state.spec.id)
        assert state.status == "awaiting_acceptance", state.error
        assert engine.accept(state.spec.id, "operator").status == "succeeded"
        assert config.read_bytes() == before_bytes
        assert engine.store.trusted(before_digest)
    finally:
        engine.close()


def test_proposed_workflow_cannot_spoof_trusted_id_or_template_provenance(workspace):
    reasoning, engineering = IntakeAdapter("anthropic"), IntakeAdapter("openai")
    reasoning.next_result = proposed_result(workflow_payload("build-review"))
    engine = Engine(workspace, registry(reasoning, engineering))
    try:
        engine.trust("operator")
        intake = Supervisor(engine).ask("Invent a workflow", task_id="collision")
        assert intake.status == "failed"
        assert "collides with trusted workflow" in intake.error
    finally:
        engine.close()

    spoofed = workflow_payload("adaptive-spoof")
    spoofed["template_version"] = 2
    reasoning, engineering = IntakeAdapter("anthropic"), IntakeAdapter("openai")
    reasoning.next_result = proposed_result(spoofed)
    engine = Engine(workspace, registry(reasoning, engineering))
    try:
        # Existing trust remains valid because the profile did not change.
        intake = Supervisor(engine).ask("Invent versioned authority", task_id="spoof")
        assert intake.status == "failed"
        assert "cannot set template version/provenance" in intake.error
    finally:
        engine.close()


def test_proposed_isolated_ownership_must_fit_supervisor_allowed_paths(workspace):
    reasoning, engineering = IntakeAdapter("anthropic"), IntakeAdapter("openai")
    reasoning.next_result = proposed_result(workflow_payload(isolated_path="other.txt"))
    engine = Engine(workspace, registry(reasoning, engineering))
    try:
        engine.trust("operator")
        intake = Supervisor(engine).ask("Parallelize it", task_id="bad-ownership")
        assert intake.status == "failed"
        assert "write_paths exceed proposed allowed_paths" in intake.error
        assert engine.store.db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0
    finally:
        engine.close()


def test_proposed_intake_can_be_revised_conversationally_and_old_scope_is_invalid(workspace):
    reasoning, engineering = IntakeAdapter("anthropic"), IntakeAdapter("openai")
    reasoning.next_result = proposed_result(workflow_payload())
    engine = Engine(workspace, registry(reasoning, engineering))
    try:
        engine.trust("operator")
        supervisor = Supervisor(engine)
        first = supervisor.ask("Use a custom structure", task_id="revision-task")
        first_scope = supervisor.scope(first)
        assert first.status == "proposed"

        reasoning.next_result = None  # Default fixture selects the trusted project default.
        second = supervisor.ask("Make the orchestration simpler", reply_to=first.id)
        assert second.status == "proposed", second.error
        assert second.round == 2
        assert second.workflow_source == "profile_default"
        assert engine.store.get_intake(first.id).status == "superseded"
        history = json.loads(reasoning.requests[-1].prompt)["clarification_history"]
        assert history[-1]["proposal"]["workflow_spec"]["id"] == "adaptive-flow"

        with pytest.raises(OrchestratorError, match="unconsumed proposed intake"):
            supervisor.start(first.id, first_scope, "operator")
        state = supervisor.start(second.id, supervisor.scope(second), "operator")
        assert state.workflow_id == "build-review"
    finally:
        engine.close()


def test_successful_task_scoped_workflow_can_be_saved_only_by_explicit_operator(workspace):
    config = workspace / ".orchestrator/config.yaml"
    before = config.read_bytes()
    engine, _, intake, state, _, _ = complete_proposed_workflow(workspace)
    try:
        candidate = workflow_templates.candidate(engine, intake.id, "learned-flow")
        assert candidate["template_version"] == 1
        assert candidate["source_workflow_digest"] == state.workflow_digest
        assert candidate["authority_change"].startswith("project profile mutation")
        assert config.read_bytes() == before

        with pytest.raises(OrchestratorError, match="candidate changed"):
            workflow_templates.save(engine, intake.id, "learned-flow", "wrong", "operator")

        saved = workflow_templates.save(
            engine, intake.id, "learned-flow", candidate["scope"], "operator"
        )
        assert saved["profile_retrust_required"] is True
        assert saved["workflow"]["provenance"]["source"] == "supervisor_evidence"
        assert saved["workflow"]["provenance"]["task_id"] == state.spec.id
        assert saved["workflow"]["provenance"]["saved_by"] == "operator"
        assert not engine.store.trusted(saved["new_profile_digest"])
    finally:
        engine.close()

    reloaded = Engine(workspace, registry(IntakeAdapter("anthropic"), IntakeAdapter("openai")))
    try:
        assert reloaded.profile.workflows["learned-flow"].template_version == 1
        assert reloaded.profile.workflows["learned-flow"].provenance.task_id == "adaptive-task"
        assert reloaded.workflow_registry_report()["workflows"]["learned-flow"]["source"] == "project"
        assert not reloaded.store.trusted(reloaded.profile_digest)
        reloaded.trust("operator")
        assert reloaded.store.trusted(reloaded.profile_digest)
    finally:
        reloaded.close()


def test_saved_template_revision_increments_version_and_records_parent_digest(workspace):
    def configure(path):
        config = path / ".orchestrator/config.yaml"
        data = yaml.safe_load(config.read_text())
        data["workflows"] = {"existing-flow": workflow_payload("existing-flow")}
        config.write_text(yaml.safe_dump(data, sort_keys=False))

    engine, _, intake, _, _, _ = complete_proposed_workflow(
        workspace, workflow=workflow_payload("adaptive-source"), configure=configure
    )
    try:
        parent_digest = engine.workflow_for_ref("existing-flow").digest
        candidate = workflow_templates.candidate(
            engine, intake.id, "existing-flow", replace=True
        )
        assert candidate["template_version"] == 2
        assert candidate["parent_template_digest"] == parent_digest
        saved = workflow_templates.save(
            engine, intake.id, "existing-flow", candidate["scope"], "operator", replace=True
        )
        assert saved["workflow"]["template_version"] == 2
        assert saved["workflow"]["provenance"]["parent_template_digest"] == parent_digest
    finally:
        engine.close()


def test_v08_template_defaults_do_not_change_legacy_custom_workflow_profile_digest(workspace):
    config = workspace / ".orchestrator/config.yaml"
    data = yaml.safe_load(config.read_text())
    data["workflows"] = {"legacy-flow": workflow_payload("legacy-flow")}
    config.write_text(yaml.safe_dump(data, sort_keys=False))
    before = Project(workspace).load()[1]

    data = yaml.safe_load(config.read_text())
    data["workflows"]["legacy-flow"]["template_version"] = 1
    data["workflows"]["legacy-flow"]["provenance"] = None
    config.write_text(yaml.safe_dump(data, sort_keys=False))
    after = Project(workspace).load()[1]
    assert after == before


def test_workflow_semantic_digest_ignores_template_metadata():
    plain = WorkflowSpec.model_validate(workflow_payload("stable"))
    versioned = plain.model_copy(update={"template_version": 7})
    # compile_proposed_workflow intentionally rejects non-default version; the
    # lower-level semantic compiler still keeps metadata out of the DAG digest.
    from ai_orchestrator.workflow import compile_workflow
    assert compile_workflow(plain, cross_provider_review=True).digest == compile_workflow(
        versioned, cross_provider_review=True
    ).digest
