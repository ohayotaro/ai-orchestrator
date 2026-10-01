"""v0.8.8 provider tool telemetry persistence."""
from __future__ import annotations

from ai_orchestrator.engine import Engine
from ai_orchestrator.providers import ProviderExecutionError
from conftest import FakeAdapter, approve_and_run, reply, spec


class TelemetryAdapter(FakeAdapter):
    def __init__(self, family: str, *, fail: bool = False):
        super().__init__(family)
        self.fail = fail

    def execute(self, request):
        if request.telemetry_sink is not None:
            request.telemetry_sink({
                "provider": "agy",
                "tools": [
                    {"name": "mystery_edit_tool", "calls": 1, "done": 1, "error": 0, "other": 0}
                ],
                "tool_names": ["mystery_edit_tool"],
                "tool_call_count": 1,
            })
        if request.phase == "execute":
            (request.workspace / "result.txt").write_text("implemented\n")
            if self.fail:
                raise ProviderExecutionError(
                    "synthetic failure",
                    {"provider": "agy", "terminal_status": "SUCCESS"},
                )
            return reply(
                request,
                outcome="completed",
                summary="implementation completed",
                findings=["result.txt"],
                evidence=["result.txt"],
            )
        return super().execute(request)


def controller(workspace, engineering):
    return Engine(
        workspace,
        {"claude": FakeAdapter("anthropic"), "codex": engineering},
    )


def scoped(engine, task_id):
    state = engine.create(spec(task_id))
    state.allowed_paths = ["result.txt"]
    engine.store.save(state, "test.allowed_paths")
    return state


def test_guarded_success_persists_tool_telemetry(workspace):
    engine = controller(workspace, TelemetryAdapter("openai"))
    try:
        engine.trust("operator")
        state = scoped(engine, "telemetry-success")
        state = approve_and_run(engine, state.spec.id)
        assert state.status == "awaiting_acceptance", state.error
        events = [
            item for item in engine.store.events(state.spec.id)
            if item["kind"] == "provider.tool_telemetry"
        ]
        assert len(events) == 1
        assert events[0]["payload"] == {
            "node": "implement",
            "phase": "execute",
            "provider": "agy",
            "tools": [
                {"name": "mystery_edit_tool", "calls": 1, "done": 1, "error": 0, "other": 0}
            ],
            "tool_names": ["mystery_edit_tool"],
            "tool_call_count": 1,
        }
    finally:
        engine.close()


def test_guarded_failure_persists_tool_telemetry_before_failure_event(workspace):
    engine = controller(workspace, TelemetryAdapter("openai", fail=True))
    try:
        engine.trust("operator")
        state = scoped(engine, "telemetry-failure")
        state = engine.run(state.spec.id)
        engine.approve(state.spec.id, engine.approval_scope(state), "operator")
        state = engine.run(state.spec.id)
        assert state.status == "failed"
        events = engine.store.events(state.spec.id)
        kinds = [item["kind"] for item in events]
        assert "provider.tool_telemetry" in kinds
        assert "provider.execution.failed" in kinds
        assert kinds.index("provider.tool_telemetry") < kinds.index("provider.execution.failed")
        assert not (workspace / "result.txt").exists()
    finally:
        engine.close()
