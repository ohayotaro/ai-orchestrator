"""v0.6.2 task-scoped selection from the already-trusted workflow registry."""
from __future__ import annotations

import json

import pytest

from ai_orchestrator.cli import main
from ai_orchestrator.engine import Engine
from ai_orchestrator.human_gates import HumanGateBroker
from ai_orchestrator.models import OrchestratorError
from ai_orchestrator.project import Project
from ai_orchestrator.service import ApplicationService
from ai_orchestrator.supervisor import Supervisor
from conftest import FakeAdapter, spec
from test_v02_supervisor import IntakeAdapter


def registry():
    return {"claude": IntakeAdapter("anthropic"), "codex": IntakeAdapter("openai")}


def test_builtin_registry_is_available_without_profile_mutation_or_retrust(workspace):
    config = workspace / ".orchestrator/config.yaml"
    before_bytes = config.read_bytes()
    before_digest = Project(workspace).load()[1]
    engine = Engine(workspace, {"claude": FakeAdapter("anthropic"), "codex": FakeAdapter("openai")})
    try:
        engine.trust("operator")
        report = engine.workflow_registry_report()
        assert report["default"] == "build-review"
        assert report["workflows"]["build-review"]["source"] == "builtin"
        assert report["workflows"]["branched-review"]["source"] == "builtin"
        assert report["workflows"]["branched-review"]["order"] == [
            "analyze_a", "analyze_b", "implement", "validate", "review"
        ]
        assert Project(workspace).load()[1] == before_digest
        assert engine.store.trusted(before_digest)
        assert config.read_bytes() == before_bytes
    finally:
        engine.close()


def test_manual_task_can_select_builtin_branched_workflow_without_retrust(workspace):
    config = workspace / ".orchestrator/config.yaml"
    before_bytes = config.read_bytes()
    before_digest = Project(workspace).load()[1]
    reasoning, engineering = FakeAdapter("anthropic"), FakeAdapter("openai")
    engine = Engine(workspace, {"claude": reasoning, "codex": engineering})
    try:
        engine.trust("operator")
        state = engine.create(spec(), workflow_ref="branched-review")
        assert state.workflow_id == "branched-review"
        assert state.workflow_selection_source == "task"
        assert state.profile_digest == before_digest
        assert engine.store.trusted(before_digest)
        assert config.read_bytes() == before_bytes

        state = engine.run(state.spec.id)
        assert state.status == "awaiting_approval", state.error
        assert [request.phase for request in reasoning.requests] == ["plan", "plan"]
        assert state.workflow_nodes["analyze_a"].status == "succeeded"
        assert state.workflow_nodes["analyze_b"].status == "succeeded"
        assert state.workflow_current == "implement"
        assert not engineering.requests
    finally:
        engine.close()


def test_explicit_supervisor_workflow_selection_is_frozen_into_start_scope(workspace):
    config = workspace / ".orchestrator/config.yaml"
    before = config.read_bytes()
    reasoning, engineering = IntakeAdapter("anthropic"), IntakeAdapter("openai")
    engine = Engine(workspace, {"claude": reasoning, "codex": engineering})
    try:
        engine.trust("operator")
        supervisor = Supervisor(engine)
        intake = supervisor.ask("Use the branched analysis workflow", task_id="selected-flow",
                                workflow_ref="branched-review")
        assert intake.status == "proposed", intake.error
        assert intake.requested_workflow_ref == "branched-review"
        assert intake.workflow_ref == "branched-review"
        assert intake.workflow_source == "requested"
        assert intake.workflow_digest == engine.workflow_report("branched-review")["digest"]
        assert engine.store.trusted(engine.profile_digest)
        assert config.read_bytes() == before

        broker = HumanGateBroker(ApplicationService(workspace), "session", {"name": "test", "version": "1"})
        try:
            captured = broker.capture(engine, "start", intake.id)
            assert captured["preview"]["workflow_ref"] == "branched-review"
            assert captured["preview"]["workflow_source"] == "requested"
            assert captured["preview"]["workflow"]["id"] == "branched-review"
        finally:
            broker.close()

        state = supervisor.start(intake.id, supervisor.scope(intake), "operator")
        assert state.workflow_id == "branched-review"
        assert state.workflow_digest == intake.workflow_digest
        assert state.workflow_selection_source == "requested"
        assert config.read_bytes() == before
        assert engine.store.trusted(engine.profile_digest)
    finally:
        engine.close()


def test_supervisor_can_propose_only_an_advertised_trusted_workflow(workspace):
    reasoning, engineering = IntakeAdapter("anthropic"), IntakeAdapter("openai")
    reasoning.next_result = {
        "outcome": "proposed",
        "summary": "Use two independent analyses",
        "task": {
            "goal": "Produce a result",
            "acceptance": ["A result exists"],
            "risk": "T2",
            "validators": ["check"],
            "external_effects": False,
            "allowed_paths": ["result.txt"],
            "capabilities": {},
            "workflow_ref": "branched-review",
        },
        "questions": [],
    }
    engine = Engine(workspace, {"claude": reasoning, "codex": engineering})
    try:
        engine.trust("operator")
        intake = Supervisor(engine).ask("Analyze from two angles and implement", task_id="supervisor-flow")
        assert intake.status == "proposed", intake.error
        assert intake.workflow_ref == "branched-review"
        assert intake.workflow_source == "supervisor"
    finally:
        engine.close()

    reasoning, engineering = IntakeAdapter("anthropic"), IntakeAdapter("openai")
    reasoning.next_result = {
        "outcome": "proposed",
        "summary": "Invent a workflow",
        "task": {
            "goal": "Produce a result",
            "acceptance": ["A result exists"],
            "risk": "T2",
            "validators": ["check"],
            "external_effects": False,
            "allowed_paths": ["result.txt"],
            "capabilities": {},
            "workflow_ref": "untrusted-new-flow",
        },
        "questions": [],
    }
    engine = Engine(workspace, {"claude": reasoning, "codex": engineering})
    try:
        engine.trust("operator")
        intake = Supervisor(engine).ask("Do it differently", task_id="bad-flow")
        assert intake.status == "failed"
        assert "unknown trusted workflow" in intake.error
        assert engine.store.db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0
    finally:
        engine.close()


def test_unknown_explicit_workflow_is_rejected_before_supervisor_call(workspace):
    reasoning, engineering = IntakeAdapter("anthropic"), IntakeAdapter("openai")
    engine = Engine(workspace, {"claude": reasoning, "codex": engineering})
    try:
        engine.trust("operator")
        with pytest.raises(OrchestratorError, match="unknown trusted workflow"):
            Supervisor(engine).ask("Do it", workflow_ref="not-installed")
        assert not reasoning.requests and not engineering.requests
    finally:
        engine.close()


def test_mcp_inspection_and_queue_expose_task_scoped_workflow_selection(workspace):
    engine = Engine(workspace)
    engine.trust("operator")
    profile_digest = engine.profile_digest
    engine.close()

    service = ApplicationService(workspace)
    inspected = service.invoke("inspect_project", {})
    assert inspected["workflows"]["default"] == "build-review"
    assert inspected["workflows"]["workflows"]["branched-review"]["source"] == "builtin"

    job = service.invoke("propose_task", {
        "request": "Use two analyses",
        "request_id": "workflow-job",
        "task_id": "workflow-task",
        "workflow_ref": "branched-review",
    })
    assert job["arguments"]["workflow_ref"] == "branched-review"
    assert job["profile_digest"] == profile_digest
    assert Project(workspace).load()[1] == profile_digest


def test_cli_registry_and_manual_create_workflow_ref(workspace, tmp_path, capsys):
    assert main(["--project", str(workspace), "workflows"]) == 0
    registry_payload = json.loads(capsys.readouterr().out)
    assert "branched-review" in registry_payload["workflows"]

    task_file = tmp_path / "task.yaml"
    task_file.write_text(
        "schema_version: 1\n"
        "id: cli-branched\n"
        "goal: Produce a result\n"
        "acceptance:\n  - Result exists\n"
        "risk: T2\n"
        "validators:\n  - check\n"
        "external_effects: false\n"
    )
    assert main([
        "--project", str(workspace), "create", "--task-file", str(task_file),
        "--workflow", "branched-review",
    ]) == 0
    state = json.loads(capsys.readouterr().out)
    assert state["workflow_id"] == "branched-review"
    assert state["workflow_selection_source"] == "task"


def test_explicit_workflow_wins_over_different_supervisor_proposal(workspace):
    reasoning, engineering = IntakeAdapter("anthropic"), IntakeAdapter("openai")
    reasoning.next_result = {
        "outcome": "proposed",
        "summary": "Different suggestion",
        "task": {
            "goal": "Produce a result",
            "acceptance": ["A result exists"],
            "risk": "T2",
            "validators": ["check"],
            "external_effects": False,
            "allowed_paths": ["result.txt"],
            "capabilities": {},
            "workflow_ref": "build-review",
        },
        "questions": [],
    }
    engine = Engine(workspace, {"claude": reasoning, "codex": engineering})
    try:
        engine.trust("operator")
        intake = Supervisor(engine).ask(
            "Use branched-review", task_id="explicit-wins", workflow_ref="branched-review"
        )
        assert intake.status == "proposed", intake.error
        assert intake.workflow_ref == "branched-review"
        assert intake.workflow_source == "requested"
        assert any("explicitly requested" in note for note in intake.notes)
    finally:
        engine.close()
