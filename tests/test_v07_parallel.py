"""v0.7 isolated parallel execution, integration and recovery."""
from __future__ import annotations

import json
import subprocess
import threading
import time

import pytest
import yaml

from ai_orchestrator.contracts import ImplementationResult
from ai_orchestrator.engine import Engine
from ai_orchestrator.models import OrchestratorError, WorkflowSpec
from ai_orchestrator.project import Project
from ai_orchestrator.workflow import compile_workflow
from ai_orchestrator.workspaces import WorkspaceManager
from conftest import FakeAdapter, reply, spec


def parallel_workflow(*, overlap: bool = False):
    right_paths = ["a.txt"] if overlap else ["b.txt"]
    return {
        "schema_version": 1,
        "id": "parallel-review",
        "nodes": [
            {
                "id": "plan", "kind": "agent", "role": "planner", "run_for": "all",
                "outputs": [{"name": "plan", "type": "plan"}],
            },
            {
                "id": "implement_a", "kind": "agent", "role": "implementer", "run_for": "write",
                "depends_on": ["plan"],
                "inputs": [{"artifact": "plan", "type": "plan"}],
                "outputs": [
                    {"name": "implementation_a", "type": "implementation"},
                    {"name": "write_set_a", "type": "write_set"},
                ],
                "gate_before": "execution", "writes": "task_allowed_paths",
                "workspace": "isolated", "write_paths": ["a.txt"],
            },
            {
                "id": "implement_b", "kind": "agent", "role": "implementer", "run_for": "write",
                "depends_on": ["plan"],
                "inputs": [{"artifact": "plan", "type": "plan"}],
                "outputs": [
                    {"name": "implementation_b", "type": "implementation"},
                    {"name": "write_set_b", "type": "write_set"},
                ],
                "gate_before": "execution", "writes": "task_allowed_paths",
                "workspace": "isolated", "write_paths": right_paths,
            },
            {
                "id": "validate", "kind": "validator", "run_for": "write",
                "depends_on": ["implement_a", "implement_b"],
                "outputs": [{"name": "validation", "type": "validation"}],
            },
            {
                "id": "review", "kind": "agent", "role": "reviewer", "run_for": "write",
                "depends_on": ["validate"],
                "independent_of": ["implement_a", "implement_b"],
                "inputs": [{"artifact": "validation", "type": "validation"}],
                "outputs": [{"name": "review", "type": "review"}],
            },
        ],
    }


def configure_parallel(workspace, *, max_workers: int = 2):
    path = workspace / ".orchestrator/config.yaml"
    data = yaml.safe_load(path.read_text())
    workflow = parallel_workflow()
    data["workflow"] = workflow["id"]
    data["workflows"] = {workflow["id"]: workflow}
    data["policy"]["max_parallel_workers"] = max_workers
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def commit_baseline(workspace):
    subprocess.run(["git", "-C", str(workspace), "config", "user.email", "test@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(workspace), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(workspace), "add", "input.txt"], check=True)
    subprocess.run(["git", "-C", str(workspace), "commit", "-q", "-m", "baseline"], check=True)


class ParallelAdapter(FakeAdapter):
    def __init__(self, family: str, *, fail_node: str | None = None):
        super().__init__(family)
        self.fail_node = fail_node
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()
        self.workspaces = []

    def execute(self, request):
        if request.phase != "execute":
            return super().execute(request)
        self.requests.append(request)
        payload = json.loads(request.prompt)
        node = payload["workflow"]["node"]
        self.workspaces.append(str(request.workspace))
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(0.15)
            if node == self.fail_node:
                raise RuntimeError("synthetic isolated failure")
            name = "a.txt" if node == "implement_a" else "b.txt"
            (request.workspace / name).write_text(node + "\n")
            return reply(
                request, outcome="completed", summary=f"{node} completed",
                findings=[name], evidence=[name],
            )
        finally:
            with self.lock:
                self.active -= 1


def registry(engineering=None):
    return {
        "claude": FakeAdapter("anthropic"),
        "codex": engineering or ParallelAdapter("openai"),
    }


def create_parallel_task(controller):
    state = controller.create(spec())
    state.allowed_paths = ["a.txt", "b.txt"]
    controller.store.save(state, "test.allowed_paths")
    return state


def test_independent_isolated_writers_must_have_disjoint_ownership():
    with pytest.raises(OrchestratorError, match="overlapping write_paths"):
        compile_workflow(
            WorkflowSpec.model_validate(parallel_workflow(overlap=True)),
            cross_provider_review=True,
        )


def test_default_parallel_policy_and_node_fields_preserve_profile_digest(workspace):
    project = Project(workspace)
    before = project.load()[1]
    path = workspace / ".orchestrator/config.yaml"
    data = yaml.safe_load(path.read_text())
    data["policy"]["max_parallel_workers"] = 1
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    after = Project(workspace).load()[1]
    assert after == before


def test_isolated_write_paths_must_fit_task_allowed_paths(workspace):
    commit_baseline(workspace)
    configure_parallel(workspace)
    controller = Engine(workspace, registry())
    try:
        controller.trust("operator")
        state = controller.create(spec())
        state.allowed_paths = ["a.txt"]
        controller.store.save(state, "test.allowed_paths")
        state = controller.run(state.spec.id)
        assert state.status == "blocked"
        assert "write_paths exceed task allowed_paths" in state.error
    finally:
        controller.close()


def test_parallel_writers_are_isolated_integrated_then_validated(workspace):
    commit_baseline(workspace)
    configure_parallel(workspace, max_workers=2)
    engineering = ParallelAdapter("openai")
    controller = Engine(workspace, registry(engineering))
    try:
        controller.trust("operator")
        state = create_parallel_task(controller)

        state = controller.run(state.spec.id)
        assert state.status == "awaiting_approval", state.error
        context = controller.workflow_gate_context(state)
        assert [item["node"] for item in context["execution_batch"]] == ["implement_a", "implement_b"]
        assert context["max_parallel_workers"] == 2

        scope = controller.approval_scope(state)
        controller.approve(state.spec.id, scope, "operator")
        state = controller.run(state.spec.id)

        assert state.status == "awaiting_acceptance", state.error
        assert (workspace / "a.txt").read_text() == "implement_a\n"
        assert (workspace / "b.txt").read_text() == "implement_b\n"
        assert engineering.max_active >= 2
        assert len(set(engineering.workspaces)) == 2
        assert all(".orchestrator/runtime/worktrees/" in item for item in engineering.workspaces)

        validation = controller.store.latest(state, "validation")
        assert validation["snapshot"] == state.reviewed_snapshot == Project(workspace).snapshot()
        write_a = controller.store.latest(state, "write_set_a")
        write_b = controller.store.latest(state, "write_set_b")
        assert write_a["owned_paths"] == ["a.txt"]
        assert write_b["owned_paths"] == ["b.txt"]
        assert write_a["integrated_snapshot"] == write_b["integrated_snapshot"] == state.reviewed_snapshot

        kinds = [event["kind"] for event in controller.store.events(state.spec.id)]
        assert "workflow.parallel.started" in kinds
        assert "workspace.integration.prepared" in kinds
        assert "workspace.integrated" in kinds
        assert "validation.finished" in kinds
        assert not (workspace / ".orchestrator/runtime/worktrees" / state.spec.id).exists()
    finally:
        controller.close()


def test_parallel_provider_failure_does_not_apply_partial_changes(workspace):
    commit_baseline(workspace)
    configure_parallel(workspace, max_workers=2)
    engineering = ParallelAdapter("openai", fail_node="implement_b")
    controller = Engine(workspace, registry(engineering))
    try:
        controller.trust("operator")
        state = create_parallel_task(controller)
        state = controller.run(state.spec.id)
        controller.approve(state.spec.id, controller.approval_scope(state), "operator")
        state = controller.run(state.spec.id)

        assert state.status == "failed"
        assert not (workspace / "a.txt").exists()
        assert not (workspace / "b.txt").exists()
        assert state.workflow_nodes["implement_a"].status == "failed"
        assert state.workflow_nodes["implement_b"].status == "failed"
        assert not (workspace / ".orchestrator/runtime/worktrees" / state.spec.id).exists()
    finally:
        controller.close()


def test_parallelism_is_bounded_by_policy(workspace):
    commit_baseline(workspace)
    configure_parallel(workspace, max_workers=1)
    engineering = ParallelAdapter("openai")
    controller = Engine(workspace, registry(engineering))
    try:
        controller.trust("operator")
        state = create_parallel_task(controller)
        state = controller.run(state.spec.id)
        controller.approve(state.spec.id, controller.approval_scope(state), "operator")
        state = controller.run(state.spec.id)
        assert state.status == "awaiting_acceptance", state.error
        assert engineering.max_active == 1
    finally:
        controller.close()


def test_recover_cleans_stale_isolated_worktrees_without_replay(workspace):
    commit_baseline(workspace)
    configure_parallel(workspace)
    controller = Engine(workspace, registry())
    try:
        controller.trust("operator")
        state = create_parallel_task(controller)
        state.status = "running"
        controller.store.save(state, "test.interrupted")
        manager = WorkspaceManager(controller.project, controller.profile, state.spec.id, 1)
        manager.prepare(["implement_a"])
        assert manager.task_dir.exists()

        recovered = controller.recover(state.spec.id)
        assert recovered.status == "failed"
        assert "without replay" in recovered.error
        assert not (workspace / ".orchestrator/runtime/worktrees" / state.spec.id).exists()
    finally:
        controller.close()
