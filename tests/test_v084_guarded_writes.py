"""v0.8.4 guarded writable execution and provider diagnostics."""
from __future__ import annotations

from pathlib import Path

from ai_orchestrator.engine import Engine
from ai_orchestrator.models import OrchestratorError
from ai_orchestrator.providers import ProviderExecutionError
from conftest import FakeAdapter, approve_and_run, reply, spec


class WorkspaceRecordingAdapter(FakeAdapter):
    def __init__(self, family: str, *, fail_after_write: bool = False):
        super().__init__(family)
        self.fail_after_write = fail_after_write
        self.execute_workspaces: list[Path] = []

    def execute(self, request):
        if request.phase != "execute":
            return super().execute(request)
        self.requests.append(request)
        self.execute_workspaces.append(request.workspace)
        (request.workspace / "result.txt").write_text("implemented\n")
        if self.fail_after_write:
            raise ProviderExecutionError(
                "synthetic provider result parse failure",
                {
                    "provider": "agy",
                    "terminal_status": "SUCCESS",
                    "structured_output_type": "NoneType",
                    "response_json_type": "invalid",
                    "response_bytes": 123,
                },
            )
        return reply(
            request,
            outcome="completed",
            summary="implementation completed",
            findings=["result.txt"],
            evidence=["result.txt"],
        )


def controller(workspace, engineering):
    return Engine(
        workspace,
        {
            "claude": FakeAdapter("anthropic"),
            "codex": engineering,
        },
    )


def scoped_task(engine, task_id="guarded-task"):
    state = engine.create(spec(task_id))
    state.allowed_paths = ["result.txt"]
    engine.store.save(state, "test.allowed_paths")
    return state


def test_shared_scoped_writer_executes_off_worktree_then_integrates(workspace):
    engineering = WorkspaceRecordingAdapter("openai")
    engine = controller(workspace, engineering)
    try:
        engine.trust("operator")
        state = scoped_task(engine)
        state = approve_and_run(engine, state.spec.id)

        assert state.status == "awaiting_acceptance", state.error
        assert (workspace / "result.txt").read_text() == "implemented\n"
        assert len(engineering.execute_workspaces) == 1
        worker = engineering.execute_workspaces[0]
        assert worker != workspace
        assert ".orchestrator/runtime/worktrees/" in str(worker)

        write_set = engine.store.latest(state, "write_set")
        assert write_set["changed_paths"] == ["result.txt"]
        assert write_set["owned_paths"] == ["result.txt"]
        assert write_set["violations"] == []
        assert write_set["integrated_snapshot"] == state.reviewed_snapshot

        kinds = [item["kind"] for item in engine.store.events(state.spec.id)]
        assert "workflow.guarded_write.preparing" in kinds
        assert "workflow.guarded_write.started" in kinds
        assert "workspace.patch.ready" in kinds
        assert "workspace.integrated" in kinds
        assert "workflow.guarded_write.finished" in kinds
        assert "validation.finished" in kinds
        assert not (workspace / ".orchestrator/runtime/worktrees" / state.spec.id).exists()
    finally:
        engine.close()


def test_provider_failure_after_private_write_does_not_mutate_project(workspace):
    engineering = WorkspaceRecordingAdapter("openai", fail_after_write=True)
    engine = controller(workspace, engineering)
    try:
        engine.trust("operator")
        state = scoped_task(engine, "guarded-failure")
        state = engine.run(state.spec.id)
        assert state.status == "awaiting_approval"
        engine.approve(state.spec.id, engine.approval_scope(state), "operator")
        state = engine.run(state.spec.id)

        assert state.status == "failed"
        assert not (workspace / "result.txt").exists()
        assert len(engineering.execute_workspaces) == 1
        assert engineering.execute_workspaces[0] != workspace
        assert engine.store.latest(state, "write_set") is None
        assert engine.store.latest(state, "implementation") is None
        assert not (workspace / ".orchestrator/runtime/worktrees" / state.spec.id).exists()

        events = engine.store.events(state.spec.id)
        diagnostics = [item for item in events if item["kind"] == "provider.execution.failed"]
        assert len(diagnostics) == 1
        assert diagnostics[0]["payload"]["diagnostics"] == {
            "provider": "agy",
            "terminal_status": "SUCCESS",
            "structured_output_type": "NoneType",
            "response_json_type": "invalid",
            "response_bytes": 123,
        }
        assert "workflow.guarded_write.failed" in {item["kind"] for item in events}
    finally:
        engine.close()


def test_guarded_write_supports_repository_without_head(workspace):
    # The shared-write safety upgrade must not introduce a first-commit
    # prerequisite for normal exact-scope Supervisor tasks.
    engineering = WorkspaceRecordingAdapter("openai")
    engine = controller(workspace, engineering)
    try:
        engine.trust("operator")
        state = scoped_task(engine, "guarded-no-head")
        state = approve_and_run(engine, state.spec.id)
        assert state.status == "awaiting_acceptance", state.error
        assert (workspace / "result.txt").read_text() == "implemented\n"
    finally:
        engine.close()
