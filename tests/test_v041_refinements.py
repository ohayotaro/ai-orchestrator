"""v0.4.1 Yes/No, write-set, and bounded progress refinements."""
import json
import pytest

from ai_orchestrator.contracts import SupervisorResultScoped
from ai_orchestrator.engine import Engine
from ai_orchestrator.human_gates import HumanGateBroker
from ai_orchestrator.mcp_server import StdioServer
from ai_orchestrator.service import ApplicationService
from ai_orchestrator.supervisor import Supervisor
from conftest import approve_and_run, spec
from test_v02_supervisor import IntakeAdapter


def test_current_supervisor_schema_requires_allowed_paths():
    schema = SupervisorResultScoped.model_json_schema()
    task = schema["$defs"]["TaskDraftScoped"]
    assert "allowed_paths" in task["required"]


def test_new_intake_persists_exact_allowed_paths(workspace):
    engine = Engine(workspace, {"claude": IntakeAdapter("anthropic"), "codex": IntakeAdapter("openai")})
    try:
        engine.trust("operator")
        intake = Supervisor(engine).ask("Create a result", task_id="scoped-task")
        assert intake.allowed_paths == ["result.txt"]
        state = Supervisor(engine).start(intake.id, Supervisor(engine).scope(intake), "operator")
        assert state.allowed_paths == ["result.txt"]
    finally:
        engine.close()


def test_write_set_evidence_reaches_reviewer(engine):
    controller, reasoning, _ = engine
    state = controller.create(spec())
    state.allowed_paths = ["result.txt"]
    controller.store.save(state, "test.allowed_paths")
    state = approve_and_run(controller)
    assert state.status == "awaiting_acceptance"
    evidence = controller.store.latest(state, "write_set")
    assert evidence["changed_paths"] == ["result.txt"]
    assert evidence["violations"] == []
    assert json.loads(reasoning.requests[-1].prompt)["write_set"]["changed_paths"] == ["result.txt"]


def test_write_outside_allowed_paths_fails_with_evidence(engine):
    controller, _, implementer = engine
    original = implementer.execute
    def execute(request):
        result = original(request)
        (request.workspace / "unexpected.txt").write_text("outside")
        return result
    implementer.execute = execute
    state = controller.create(spec())
    state.allowed_paths = ["result.txt"]
    controller.store.save(state, "test.allowed_paths")
    state = approve_and_run(controller)
    assert state.status == "failed"
    assert "outside allowed_paths" in state.error
    assert controller.store.latest(state, "write_set")["violations"] == ["unexpected.txt"]


def test_invalid_allowed_paths_fail_closed():
    from ai_orchestrator.models import TaskState
    base = {"spec": spec(), "profile_digest": "x"}
    for paths in [[".orchestrator/config.yaml"], ["../escape"], ["src/*.py"], ["dir/"], ["dir\\file.py"]]:
        with pytest.raises(Exception):
            TaskState(**base, allowed_paths=paths)


def test_existing_directory_cannot_be_an_allowed_file(engine):
    controller, _, _ = engine
    (controller.project.root / "output-dir").mkdir()
    state = controller.create(spec())
    state.allowed_paths = ["output-dir"]
    controller.store.save(state, "test.allowed_directory")
    assert controller.run(state.spec.id).status == "blocked"
    assert "must be a file" in controller.store.get(state.spec.id).error


def test_gate_uses_explicit_yes_no_enum(workspace):
    engine = Engine(workspace, {"claude": IntakeAdapter("anthropic"), "codex": IntakeAdapter("openai")})
    try:
        engine.trust("operator")
        intake = Supervisor(engine).ask("Create a result", task_id="enum-task")
        broker = HumanGateBroker(ApplicationService(workspace), "session", {"name":"client","version":"1"})
        try:
            gate = broker.prepare("start", intake.id, "enum-1")
            field = broker.form(gate)["requestedSchema"]["properties"]["decision"]
            assert field["enum"] == ["no", "yes"] and "default" not in field
            assert broker.resolve(gate, {"action":"accept","content":{"decision":"no"}})["gate_status"] == "declined"
        finally:
            broker.close()
    finally:
        engine.close()


class NoWorker:
    def status(self): return {"manager_started": False}
    def kick(self): pass
    def close(self): pass


def initialize(server):
    assert server.handle({"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{"elicitation":{"form":{}}},"clientInfo":{"name":"test","version":"1"}}})["result"]
    assert server.handle({"jsonrpc":"2.0","method":"notifications/initialized"}) is None


def test_wait_job_emits_progress_and_completes_without_poll_loop(workspace):
    engine = Engine(workspace); engine.trust("operator"); engine.close()
    service = ApplicationService(workspace)
    job = service.invoke("propose_task", {"request":"Create a result","request_id":"wait-1","task_id":"wait-task"})
    server = StdioServer(service, single_terminal=True, auto_worker=NoWorker())
    try:
        initialize(server)
        call = {"jsonrpc":"2.0","id":9,"method":"tools/call","params":{"name":"wait_job","arguments":{"job_id":job["id"],"timeout_seconds":5},"_meta":{"progressToken":"p-1"}}}
        assert server.handle(call) is None
        first = server._poll_wait()
        assert first[0]["method"] == "notifications/progress"
        service.invoke("cancel_job", {"job_id":job["id"]})
        final = server._poll_wait()
        response = next(item for item in final if item.get("id") == 9)
        assert response["result"]["structuredContent"]["status"] == "cancelled"
        assert response["result"]["structuredContent"]["wait_timed_out"] is False
    finally:
        server.close()


def test_cancelling_wait_does_not_cancel_job(workspace):
    engine = Engine(workspace); engine.trust("operator"); engine.close()
    service = ApplicationService(workspace)
    job = service.invoke("propose_task", {"request":"Create a result","request_id":"wait-2","task_id":"wait-task-2"})
    server = StdioServer(service, single_terminal=True, auto_worker=NoWorker())
    try:
        initialize(server)
        assert server.handle({"jsonrpc":"2.0","id":10,"method":"tools/call","params":{"name":"wait_job","arguments":{"job_id":job["id"]}}}) is None
        response = server.handle({"jsonrpc":"2.0","method":"notifications/cancelled","params":{"requestId":10}})
        assert response["id"] == 10 and response["result"]["isError"]
        assert service.invoke("get_job", {"job_id":job["id"]})["status"] == "queued"
    finally:
        server.close()
