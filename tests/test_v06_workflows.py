"""v0.6 Workflow Schema v1, DAG validation and deterministic sequential execution."""
from __future__ import annotations

import json

import pytest
import yaml

from ai_orchestrator.cli import main
from ai_orchestrator.engine import Engine
from ai_orchestrator.models import (
    OrchestratorError,
    WorkflowArtifactSpec,
    WorkflowInputSpec,
    WorkflowNodeSpec,
    WorkflowSpec,
)
from ai_orchestrator.project import Project
from ai_orchestrator.service import ApplicationService
from ai_orchestrator.workflow import builtin_build_review, compile_workflow
from conftest import FakeAdapter, spec


def registry():
    return {"claude": FakeAdapter("anthropic"), "codex": FakeAdapter("openai")}


def branched_workflow():
    return {
        "schema_version": 1,
        "id": "branched-review",
        "nodes": [
            {
                "id": "analyze_a", "kind": "agent", "role": "planner", "run_for": "all",
                "outputs": [{"name": "analysis_a", "type": "plan"}],
            },
            {
                "id": "analyze_b", "kind": "agent", "role": "planner", "run_for": "all",
                "outputs": [{"name": "analysis_b", "type": "plan"}],
            },
            {
                "id": "implement", "kind": "agent", "role": "implementer", "run_for": "write",
                "depends_on": ["analyze_a", "analyze_b"],
                "inputs": [
                    {"artifact": "analysis_a", "type": "plan"},
                    {"artifact": "analysis_b", "type": "plan"},
                ],
                "outputs": [
                    {"name": "execute", "type": "implementation"},
                    {"name": "write_set", "type": "write_set"},
                ],
                "gate_before": "execution", "writes": "task_allowed_paths",
            },
            {
                "id": "validate", "kind": "validator", "run_for": "write",
                "depends_on": ["implement"],
                "inputs": [
                    {"artifact": "execute", "type": "implementation"},
                    {"artifact": "write_set", "type": "write_set"},
                ],
                "outputs": [{"name": "validation", "type": "validation"}],
            },
            {
                "id": "review", "kind": "agent", "role": "reviewer", "run_for": "write",
                "depends_on": ["validate"], "independent_of": ["implement"],
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


def use_workflow(workspace, workflow):
    path = workspace / ".orchestrator/config.yaml"
    data = yaml.safe_load(path.read_text())
    data["workflow"] = workflow["id"]
    data["workflows"] = {workflow["id"]: workflow}
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def test_builtin_workflow_schema_and_order_are_explicit():
    compiled = compile_workflow(builtin_build_review(), cross_provider_review=True)
    assert compiled.order == ("plan", "implement", "validate", "review")
    assert compiled.artifact_types == {
        "plan": "plan",
        "execute": "implementation",
        "write_set": "write_set",
        "validation": "validation",
        "review": "review",
    }
    assert compiled.nodes["implement"].gate_before == "execution"
    assert compiled.nodes["review"].independent_of == ["implement"]


def test_cycle_unknown_dependency_and_type_mismatch_fail_closed():
    cycle = WorkflowSpec(
        id="cycle",
        nodes=[
            WorkflowNodeSpec(id="a", kind="agent", role="planner", depends_on=["b"], outputs=[WorkflowArtifactSpec(name="a_plan", type="plan")]),
            WorkflowNodeSpec(id="b", kind="agent", role="planner", depends_on=["a"], outputs=[WorkflowArtifactSpec(name="b_plan", type="plan")]),
        ],
    )
    with pytest.raises(OrchestratorError, match="cycle"):
        compile_workflow(cycle, cross_provider_review=False)

    unknown = WorkflowSpec(
        id="unknown",
        nodes=[WorkflowNodeSpec(id="a", kind="agent", role="planner", depends_on=["missing"], outputs=[WorkflowArtifactSpec(name="plan", type="plan")])],
    )
    with pytest.raises(OrchestratorError, match="unknown dependency"):
        compile_workflow(unknown, cross_provider_review=False)

    mismatch = WorkflowSpec(
        id="mismatch",
        nodes=[
            WorkflowNodeSpec(id="plan", kind="agent", role="planner", outputs=[WorkflowArtifactSpec(name="plan", type="plan")]),
            WorkflowNodeSpec(
                id="implement", kind="agent", role="implementer", run_for="write",
                depends_on=["plan"], inputs=[WorkflowInputSpec(artifact="plan", type="review")],
                outputs=[
                    WorkflowArtifactSpec(name="execute", type="implementation"),
                    WorkflowArtifactSpec(name="write_set", type="write_set"),
                ],
                gate_before="execution", writes="task_allowed_paths",
            ),
            WorkflowNodeSpec(
                id="validate", kind="validator", run_for="write", depends_on=["implement"],
                inputs=[WorkflowInputSpec(artifact="execute", type="implementation")],
                outputs=[WorkflowArtifactSpec(name="validation", type="validation")],
            ),
            WorkflowNodeSpec(
                id="review", kind="agent", role="reviewer", run_for="write", depends_on=["validate"],
                independent_of=["implement"],
                inputs=[WorkflowInputSpec(artifact="validation", type="validation")],
                outputs=[WorkflowArtifactSpec(name="review", type="review")],
            ),
        ],
    )
    with pytest.raises(OrchestratorError, match="type mismatch"):
        compile_workflow(mismatch, cross_provider_review=True)


def test_write_workflow_requires_validator_reviewer_and_independence():
    missing_review = WorkflowSpec(
        id="unsafe",
        nodes=[
            WorkflowNodeSpec(id="plan", kind="agent", role="planner", outputs=[WorkflowArtifactSpec(name="plan", type="plan")]),
            WorkflowNodeSpec(
                id="implement", kind="agent", role="implementer", run_for="write", depends_on=["plan"],
                outputs=[
                    WorkflowArtifactSpec(name="execute", type="implementation"),
                    WorkflowArtifactSpec(name="write_set", type="write_set"),
                ],
                gate_before="execution", writes="task_allowed_paths",
            ),
            WorkflowNodeSpec(
                id="validate", kind="validator", run_for="write", depends_on=["implement"],
                outputs=[WorkflowArtifactSpec(name="validation", type="validation")],
            ),
        ],
    )
    with pytest.raises(OrchestratorError, match="writable agent, validator and reviewer"):
        compile_workflow(missing_review, cross_provider_review=True)

    data = branched_workflow()
    data["nodes"][-1]["independent_of"] = []
    with pytest.raises(OrchestratorError, match="independent_of"):
        compile_workflow(WorkflowSpec.model_validate(data), cross_provider_review=True)


def test_new_tasks_bind_builtin_workflow_and_preserve_behavior(engine):
    controller, reasoning, engineering = engine
    state = controller.create(spec())
    assert state.schema_version == 7
    assert state.workflow_id == "build-review"
    assert state.workflow_order == ["plan", "implement", "validate", "review"]
    assert state.workflow_nodes["plan"].status == "pending"

    state = controller.run("task-1")
    assert state.status == "awaiting_approval"
    assert state.workflow_current == "implement"
    assert state.workflow_nodes["plan"].status == "succeeded"
    assert state.workflow_nodes["implement"].status == "pending"
    assert state.provider_resolutions["implementer"]["provider"] == "engineering"
    assert len(reasoning.requests) == 1 and not engineering.requests

    controller.approve("task-1", controller.approval_scope(state), "operator")
    state = controller.run("task-1")
    assert state.status == "awaiting_acceptance", state.error
    assert all(state.workflow_nodes[node].status == "succeeded" for node in state.workflow_order)
    assert state.calls == 3
    assert {artifact.kind for artifact in state.artifacts} == {"plan", "execute", "validation", "review", "provider_provenance", "usage", "budget"}
    assert controller.accept("task-1", "operator").status == "succeeded"


def test_advisory_task_skips_write_nodes(engine):
    controller, reasoning, engineering = engine
    state = controller.create(spec(risk="T0"))
    state = controller.run(state.spec.id)
    assert state.status == "awaiting_acceptance"
    assert state.workflow_nodes["plan"].status == "succeeded"
    assert state.workflow_nodes["implement"].status == "skipped"
    assert state.workflow_nodes["validate"].status == "skipped"
    assert state.workflow_nodes["review"].status == "skipped"
    assert state.calls == 1
    assert len(reasoning.requests) == 1 and not engineering.requests


def test_branched_dag_runs_sequentially_and_passes_typed_artifacts(workspace):
    use_workflow(workspace, branched_workflow())
    reasoning, engineering = FakeAdapter("anthropic"), FakeAdapter("openai")
    controller = Engine(workspace, {"claude": reasoning, "codex": engineering})
    try:
        controller.trust("operator")
        state = controller.create(spec())
        state.allowed_paths = ["result.txt"]
        controller.store.save(state, "test.allowed_paths")

        state = controller.run(state.spec.id)
        assert state.status == "awaiting_approval", state.error
        assert state.workflow_order == ["analyze_a", "analyze_b", "implement", "validate", "review"]
        assert state.workflow_nodes["analyze_a"].status == "succeeded"
        assert state.workflow_nodes["analyze_b"].status == "succeeded"
        assert [request.phase for request in reasoning.requests] == ["plan", "plan"]
        assert not engineering.requests

        controller.approve(state.spec.id, controller.approval_scope(state), "operator")
        state = controller.run(state.spec.id)
        assert state.status == "awaiting_acceptance", state.error
        assert state.calls == 4
        implement_prompt = json.loads(engineering.requests[0].prompt)
        assert set(implement_prompt["inputs"]) == {"analysis_a", "analysis_b"}
        assert implement_prompt["inputs"]["analysis_a"]["type"] == "plan"
        review_prompt = json.loads(reasoning.requests[-1].prompt)
        assert "plan" not in review_prompt
        assert review_prompt["validation"]["checks"][0]["exit_code"] == 0
        assert controller.store.latest(state, "write_set")["violations"] == []
        assert state.workflow_nodes["review"].provider_resolution["family"] != state.workflow_nodes["implement"].provider_resolution["family"]
    finally:
        controller.close()


def test_workflow_repair_resets_only_downstream_nodes(engine):
    controller, reasoning, _ = engine
    reasoning.reject_reviews = 1
    controller.create(spec())
    state = controller.run("task-1")
    controller.approve("task-1", controller.approval_scope(state), "operator")
    state = controller.run("task-1")
    assert state.status == "awaiting_approval"
    assert state.attempt == 2
    assert state.workflow_nodes["plan"].status == "succeeded"
    assert state.workflow_nodes["implement"].status == "pending"
    assert state.workflow_nodes["validate"].status == "pending"
    assert state.workflow_nodes["review"].status == "pending"
    assert state.calls == 3
    controller.approve("task-1", controller.approval_scope(state), "operator")
    state = controller.run("task-1")
    assert state.status == "awaiting_acceptance"
    assert state.calls == 5


def test_custom_workflow_is_profile_bound_and_requires_retrust(workspace):
    project = Project(workspace)
    before = project.load()[1]
    use_workflow(workspace, branched_workflow())
    profile, after, _ = project.load()
    assert after != before
    engine = Engine(workspace, registry())
    try:
        assert engine.workflow_report()["id"] == "branched-review"
        assert not engine.store.trusted(after)
    finally:
        engine.close()


def test_workflow_cli_and_mcp_inspection(workspace, capsys):
    code = main(["--project", str(workspace), "workflow"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["id"] == "build-review"
    assert payload["order"] == ["plan", "implement", "validate", "review"]

    service = ApplicationService(workspace)
    inspected = service.invoke("inspect_project", {})
    assert inspected["workflow"]["id"] == "build-review"
    assert inspected["workflow"]["digest"] == payload["digest"]


def test_workflow_schema_rejects_duplicate_artifacts():
    data = branched_workflow()
    data["nodes"][1]["outputs"][0]["name"] = "analysis_a"
    with pytest.raises(OrchestratorError, match="duplicate artifact"):
        compile_workflow(WorkflowSpec.model_validate(data), cross_provider_review=True)


def test_workflow_resolution_provenance_is_per_node(workspace):
    use_workflow(workspace, branched_workflow())
    controller = Engine(workspace, registry())
    try:
        controller.trust("operator")
        state = controller.create(spec())
        state.allowed_paths = ["result.txt"]
        controller.store.save(state, "test.allowed_paths")
        state = controller.run(state.spec.id)
        assert state.status == "awaiting_approval"
        assert state.workflow_nodes["analyze_a"].provider_resolution["role"] == "planner"
        assert state.workflow_nodes["analyze_b"].provider_resolution["role"] == "planner"
        assert state.workflow_nodes["implement"].provider_resolution["provider"] == "engineering"
        events = controller.store.events(state.spec.id)
        resolved = [event for event in events if event["kind"] == "workflow.resolved"]
        assert len(resolved) == 1
    finally:
        controller.close()


def test_dynamic_candidate_resolution_does_not_drift_execution_approval_scope(workspace):
    path = workspace / ".orchestrator/config.yaml"
    data = yaml.safe_load(path.read_text())
    data["providers"]["engineering"]["priority"] = 10
    data["providers"]["reasoning"]["priority"] = 20
    data["roles"]["implementer"]["provider"] = None
    data["roles"]["implementer"]["candidates"] = ["engineering", "reasoning"]
    data["roles"]["implementer"]["capabilities"] = ["code_edit"]
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    reasoning, engineering = FakeAdapter("anthropic"), FakeAdapter("openai")
    controller = Engine(workspace, {"claude": reasoning, "codex": engineering})
    try:
        controller.trust("operator")
        state = controller.create(spec(), capability_requirements={"implementer": ["test_authoring"]})
        state.allowed_paths = ["result.txt"]
        controller.store.save(state, "test.allowed_paths")

        state = controller.run(state.spec.id)
        assert state.status == "awaiting_approval"
        assert state.provider_resolutions["implementer"]["source"] == "candidates"
        assert state.workflow_nodes["implement"].provider_resolution["source"] == "candidates"
        first_scope = controller.approval_scope(state)

        # Re-running preflight is what happens when the approved execution job
        # reloads/runs the task. It must validate the frozen choice without
        # rewriting provenance to source=fixed.
        controller._preflight(state)
        second_scope = controller.approval_scope(state)
        assert second_scope == first_scope
        assert state.provider_resolutions["implementer"]["source"] == "candidates"
        assert state.provider_resolutions["implementer"]["candidates_considered"] == ["engineering"]
        assert state.workflow_nodes["implement"].provider_resolution["source"] == "candidates"

        controller.approve(state.spec.id, first_scope, "operator")
        state = controller.run(state.spec.id)
        assert state.status == "awaiting_acceptance", state.error
        assert len(engineering.requests) == 1
        assert state.provider_resolutions["implementer"]["source"] == "candidates"
    finally:
        controller.close()


def test_dynamic_priority_resolution_does_not_drift_execution_approval_scope(workspace):
    path = workspace / ".orchestrator/config.yaml"
    data = yaml.safe_load(path.read_text())
    data["providers"]["engineering"]["priority"] = 10
    data["providers"]["reasoning"]["priority"] = 20
    data["roles"]["implementer"]["provider"] = None
    data["roles"]["implementer"]["candidates"] = []
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    controller = Engine(workspace, registry())
    try:
        controller.trust("operator")
        state = controller.create(spec())
        state = controller.run(state.spec.id)
        assert state.status == "awaiting_approval"
        assert state.provider_resolutions["implementer"]["source"] == "priority"
        first_scope = controller.approval_scope(state)
        controller._preflight(state)
        assert controller.approval_scope(state) == first_scope
        assert state.provider_resolutions["implementer"]["source"] == "priority"
    finally:
        controller.close()
