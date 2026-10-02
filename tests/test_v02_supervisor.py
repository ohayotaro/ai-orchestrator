import io
import json
import sys

import pytest
import yaml
from pydantic import ValidationError

from ai_orchestrator.cli import main
from ai_orchestrator.contracts import SupervisorResult, TaskDraft
from ai_orchestrator.engine import Engine
from ai_orchestrator.models import OrchestratorError, TaskSpec
from ai_orchestrator.project import Project
from ai_orchestrator.service import ApplicationService
from ai_orchestrator.runtime_options import RuntimeOptionsDescriptor, RuntimeOverride, RuntimeValueDescriptor
from ai_orchestrator.supervisor import Supervisor
from ai_orchestrator.worker import process_one
from conftest import FakeAdapter


class IntakeAdapter(FakeAdapter):
    def __init__(self, family):
        super().__init__(family)
        self.next_result = None
        self.mutation = None
        self.interrupt = False

    def describe_runtime_options(self, config, workspace):
        return RuntimeOptionsDescriptor(
            model=RuntimeValueDescriptor(mode="passthrough"),
            effort=RuntimeValueDescriptor(mode="passthrough"),
        )

    def execute(self, request):
        if request.phase != "supervise":
            return super().execute(request)
        self.requests.append(request)
        if self.interrupt:
            raise KeyboardInterrupt()
        if self.mutation:
            self.mutation(request.workspace)
        if self.next_result is not None:
            data = self.next_result.model_dump() if hasattr(self.next_result, "model_dump") else dict(self.next_result)
            if data.get("task") is not None:
                data["task"].setdefault("allowed_paths", ["result.txt"])
                data["task"].setdefault("capabilities", {})
                data["task"].setdefault("workflow_ref", None)
            return request.result_model.model_validate(data)
        advisory = json.loads(request.prompt)["advisory"]
        return request.result_model(outcome="proposed", summary="A focused task", task={"goal":"Produce a result","acceptance":["A result exists"],"risk":"T0" if advisory else "T2","validators":[] if advisory else ["check"],"external_effects":False,"allowed_paths":[] if advisory else ["result.txt"],"capabilities":{},"workflow_ref":None}, questions=[])


@pytest.fixture
def supervisor(workspace):
    reasoning, engineering = IntakeAdapter("anthropic"), IntakeAdapter("openai")
    controller = Engine(workspace, {"claude": reasoning, "codex": engineering})
    controller.trust("operator")
    yield Supervisor(controller), reasoning, engineering
    controller.close()


def test_ask_proposes_without_creating_task_or_granting_approval(supervisor):
    intake, reasoning, engineering = supervisor
    before = intake.project.snapshot()
    state = intake.ask("Please add a result", task_id="natural-task")
    assert state.status == "proposed", state.error
    assert state.task.id == "natural-task"
    assert state.calls == 1
    assert len(reasoning.requests) == 1 and not engineering.requests
    assert reasoning.requests[0].phase == "supervise"
    assert reasoning.requests[0].result_model.__name__ == "SupervisorResultScoped"
    assert not (reasoning.requests[0].workspace / ".orchestrator").exists()
    assert not reasoning.requests[0].workspace.resolve().is_relative_to(intake.project.root.resolve())
    assert intake.store.db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0
    assert intake.store.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 0
    assert before == intake.project.snapshot()
    assert "intake_scope" in intake.describe(state.id)


def test_natural_language_to_accepted_workflow(supervisor):
    intake, reasoning, engineering = supervisor
    proposal = intake.ask("Please add a result")
    task = intake.start(proposal.id, intake.scope(proposal), "operator")
    assert task.calls == 1 and task.require_execution_approval
    state = intake.engine.run(task.spec.id)
    assert state.status == "awaiting_approval"
    assert state.calls == 2
    intake.engine.approve(task.spec.id, intake.engine.approval_scope(state), "operator")
    state = intake.engine.run(task.spec.id)
    assert state.status == "awaiting_acceptance", state.error
    assert state.calls == 4
    assert state.attempt == 1
    assert "supervisor" in {artifact.kind for artifact in state.artifacts}
    assert intake.engine.accept(task.spec.id, "operator").status == "succeeded"
    with pytest.raises(OrchestratorError, match="unconsumed"):
        intake.start(proposal.id, intake.scope(proposal), "operator")


def test_clarification_is_bounded_and_budget_is_carried_forward(supervisor):
    intake, reasoning, _ = supervisor
    reasoning.next_result = SupervisorResult(outcome="needs_clarification", summary="Need a target", task=None, questions=["Which output file?"])
    first = intake.ask("Create it")
    assert first.status == "needs_clarification" and first.task is None
    reasoning.next_result = None
    second = intake.ask("Use result.txt", reply_to=first.id)
    assert second.status == "proposed"
    assert second.round == 2 and second.calls == 2
    payload = json.loads(reasoning.requests[-1].prompt)
    assert payload["clarification_history"][0]["questions"] == ["Which output file?"]
    task = intake.start(second.id, intake.scope(second), "operator")
    assert task.calls == 2 and task.elapsed_seconds >= first.elapsed_seconds


def test_fourth_clarification_round_is_not_started(supervisor):
    intake, reasoning, _ = supervisor
    reasoning.next_result = SupervisorResult(outcome="needs_clarification", summary="Need detail", task=None, questions=["What exactly?"])
    state = intake.ask("Do it")
    state = intake.ask("Please clarify", reply_to=state.id)
    state = intake.ask("More detail", reply_to=state.id)
    assert state.round == 3
    with pytest.raises(OrchestratorError, match="fewer than three"):
        intake.ask("Fourth", reply_to=state.id)
    assert len(reasoning.requests) == 3


def test_wrong_scope_does_not_create_task(supervisor):
    intake, _, _ = supervisor
    state = intake.ask("Create result")
    with pytest.raises(OrchestratorError, match="scope changed"):
        intake.start(state.id, "wrong", "operator")
    assert intake.store.db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0


def test_worktree_change_invalidates_proposal_confirmation(supervisor):
    intake, _, _ = supervisor
    state = intake.ask("Create result")
    scope = intake.scope(state)
    (intake.project.root / "input.txt").write_text("changed")
    with pytest.raises(OrchestratorError, match="worktree changed"):
        intake.start(state.id, scope, "operator")


def test_profile_change_invalidates_proposal_even_after_retrust(supervisor):
    intake, _, _ = supervisor
    state = intake.ask("Create result")
    scope = intake.scope(state)
    (intake.project.control / "policies/new.md").write_text("New rule")
    current = intake.project.load()[1]
    intake.store.trust(current, "operator")
    with pytest.raises(OrchestratorError, match="profile changed"):
        intake.start(state.id, scope, "operator")


def test_artifact_tampering_is_not_accepted(supervisor):
    intake, _, _ = supervisor
    state = intake.ask("Create result")
    (intake.project.root / state.artifact.path).write_text("{}")
    with pytest.raises(OrchestratorError, match="integrity"):
        intake.scope(state)


def test_unknown_validator_is_rejected_not_registered(supervisor):
    intake, reasoning, _ = supervisor
    reasoning.next_result = SupervisorResult(outcome="proposed", summary="Use custom command", task=TaskDraft(goal="Do work", acceptance=["Done"], risk="T2", validators=["shell-rm"], external_effects=False), questions=[])
    state = intake.ask("Do work")
    assert state.status == "failed"
    assert "unknown validator" in state.error
    assert "shell-rm" not in intake.engine.profile.validators
    assert intake.store.db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0


def test_external_effect_is_blocked_not_silently_cleared(supervisor):
    intake, reasoning, _ = supervisor
    reasoning.next_result = SupervisorResult(outcome="proposed", summary="Publish", task=TaskDraft(goal="Publish externally", acceptance=["Published"], risk="T3", validators=["check"], external_effects=True), questions=[])
    state = intake.ask("Publish")
    assert state.status == "failed" and "external-effect" in state.error
    assert state.result.task.external_effects is True
    assert state.task is None


def test_model_cannot_downgrade_execution_gate(workspace):
    path = workspace / ".orchestrator/config.yaml"
    data = yaml.safe_load(path.read_text())
    data["policy"]["require_execution_approval"] = False
    path.write_text(yaml.safe_dump(data))
    reasoning = IntakeAdapter("anthropic")
    reasoning.next_result = SupervisorResult(outcome="proposed", summary="Trivial", task=TaskDraft(goal="Edit something", acceptance=["Done"], risk="T1", validators=["check"], external_effects=False), questions=[])
    engine = Engine(workspace, {"claude": reasoning, "codex": IntakeAdapter("openai")})
    try:
        engine.trust("operator")
        intake = Supervisor(engine)
        proposal = intake.ask("Edit")
        assert proposal.task.risk == "T2" and proposal.notes
        task = intake.start(proposal.id, intake.scope(proposal), "operator")
        assert engine.run(task.spec.id).status == "awaiting_approval"
    finally:
        engine.close()


def test_advisory_has_no_implementation_or_validator_calls(supervisor):
    intake, _, engineering = supervisor
    proposal = intake.ask("Explain the project", advisory=True)
    assert proposal.task.risk == "T0" and not proposal.task.validators
    task = intake.start(proposal.id, intake.scope(proposal), "operator")
    state = intake.engine.run(task.spec.id)
    assert state.status == "awaiting_acceptance" and state.calls == 2
    assert not engineering.requests
    assert "validation" not in {item.kind for item in state.artifacts}


@pytest.mark.parametrize("target", ["input.txt", ".orchestrator/tasks/evil.json", ".env"])
def test_supervisor_file_mutation_prevents_task_proposal(supervisor, target):
    intake, reasoning, _ = supervisor
    reasoning.mutation = lambda root: (root / target).write_text("changed")
    state = intake.ask("Create result")
    assert state.status == "failed"
    if not target.startswith(".orchestrator/"):
        assert "modified" in state.error
    assert state.task is None
    assert intake.store.db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0


def test_untrusted_profile_never_calls_supervisor(supervisor):
    intake, reasoning, _ = supervisor
    intake.store.trust("other-profile", "operator")
    with pytest.raises(OrchestratorError, match="not trusted"):
        intake.ask("Create result")
    assert not reasoning.requests


def test_supervisor_interruption_is_recorded_without_task(supervisor):
    intake, reasoning, _ = supervisor
    reasoning.interrupt = True
    state = intake.ask("Do it")
    assert state.status == "cancelled"
    assert intake.store.get_intake(state.id).status == "cancelled"
    assert intake.store.db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0


def test_existing_profile_uses_planner_binding_without_rewriting(workspace):
    path = workspace / ".orchestrator/config.yaml"
    data = yaml.safe_load(path.read_text())
    data["roles"].pop("supervisor")
    path.write_text(yaml.safe_dump(data))
    before = path.read_bytes()
    engine = Engine(workspace, {"claude": IntakeAdapter("anthropic"), "codex": IntakeAdapter("openai")})
    try:
        engine.trust("operator")
        state = Supervisor(engine).ask("Do it")
        assert state.status == "proposed"
        assert path.read_bytes() == before
    finally:
        engine.close()


def test_supervisor_provider_can_be_swapped(workspace):
    path = workspace / ".orchestrator/config.yaml"
    data = yaml.safe_load(path.read_text())
    data["roles"]["supervisor"]["provider"] = "engineering"
    path.write_text(yaml.safe_dump(data))
    reasoning, engineering = IntakeAdapter("anthropic"), IntakeAdapter("openai")
    engine = Engine(workspace, {"claude": reasoning, "codex": engineering})
    try:
        engine.trust("operator")
        assert Supervisor(engine).ask("Do it").status == "proposed"
        assert not reasoning.requests
        assert engineering.requests[0].phase == "supervise"
    finally:
        engine.close()


@pytest.mark.parametrize("extra", [{"approve": True}, {"trust": True}, {"tools": ["shell"]}, {"validator_command": "rm -rf /"}])
def test_supervisor_cannot_return_control_commands(extra):
    payload = {"outcome": "blocked", "summary": "No", "task": None, "questions": [], **extra}
    with pytest.raises(ValidationError):
        SupervisorResult.model_validate(payload)


def test_cli_natural_language_does_not_require_yaml(workspace, monkeypatch, capsys):
    reasoning, engineering = IntakeAdapter("anthropic"), IntakeAdapter("openai")
    registry = {"claude": reasoning, "codex": engineering}
    monkeypatch.setattr("ai_orchestrator.cli.Engine", lambda root: Engine(root, registry))
    prefix = ["--project", str(workspace)]
    assert main(prefix + ["trust", "--by", "operator", "--ack-local-execution"]) == 0
    capsys.readouterr()
    assert main(prefix + ["ask", "Create result", "--task-id", "via-ask"]) == 0
    proposal = json.loads(capsys.readouterr().out)
    assert proposal["status"] == "proposed"
    assert main(prefix + ["start", proposal["id"], "--scope", proposal["intake_scope"], "--by", "operator"]) == 0
    state = json.loads(capsys.readouterr().out)
    assert state["status"] == "awaiting_approval"
    assert state["spec"]["id"] == "via-ask"
    assert len(reasoning.requests) == 2


def test_interactive_approval_cannot_read_yes_from_pipe(workspace, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", io.StringIO("approve\n"))
    assert main(["--project", str(workspace), "approve", "anything", "--interactive", "--by", "operator"]) == 1
    assert "requires a terminal" in capsys.readouterr().err


def test_interactive_approval_checks_scope_again_after_confirmation(supervisor, monkeypatch, capsys):
    intake, _, _ = supervisor
    proposal = intake.ask("Do work")
    task = intake.start(proposal.id, intake.scope(proposal), "operator")
    assert intake.engine.run(task.spec.id).status == "awaiting_approval"
    class Terminal:
        def isatty(self):
            return True
        def readline(self):
            (intake.project.root / "input.txt").write_text("changed during confirmation")
            return "approve\n"
    monkeypatch.setattr(sys, "stdin", Terminal())
    code = main(["--project", str(intake.project.root), "approve", task.spec.id, "--interactive", "--by", "operator"])
    assert code == 1
    assert "scope changed" in capsys.readouterr().err
    assert intake.store.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 0



def test_supervisor_intake_runtime_override_is_applied_and_frozen(supervisor):
    intake, reasoning, _ = supervisor
    state = intake.ask(
        "Please add a result",
        task_id="supervisor-runtime",
        supervisor_runtime_override=RuntimeOverride(model="claude-opus-test", effort="high"),
    )
    assert state.status == "proposed", state.error
    assert reasoning.requests[0].config.model == "claude-opus-test"
    assert reasoning.requests[0].config.effort == "high"
    assert state.supervisor_runtime_override == {
        "model": "claude-opus-test",
        "effort": "high",
        "options": {},
    }
    assert state.supervisor_provider_resolution["provider"] == "reasoning"
    assert state.supervisor_provider_resolution["adapter"] == "claude"
    assert state.supervisor_provider_resolution["family"] == "anthropic"
    assert state.supervisor_model_variant_resolution["model"] == "claude-opus-test"
    assert state.supervisor_model_variant_resolution["effort"] == "high"
    assert state.supervisor_model_variant_resolution["sources"] == {
        "model": "explicit_override",
        "effort": "explicit_override",
    }
    dispatch = state.supervisor_dispatch_provenance
    assert dispatch["model"] == "claude-opus-test"
    assert dispatch["effort"] == "high"
    assert dispatch["runtime_options"] == {}
    assert dispatch["workspace"]["mode"] == "read_only_disposable"
    assert dispatch["workspace"]["outside_project"] is True
    assert dispatch["workspace"]["control_dir_materialized"] is False
    assert dispatch["workspace"]["unchanged_verified"] is True
    assert dispatch["workspace"]["cleaned"] is True
    assert "provider receipt is not independently attested" in dispatch["evidence_boundary"]
    described = intake.describe(state.id)
    assert described["supervisor_model_variant_resolution"]["model"] == "claude-opus-test"
    assert "intake_scope" in described


def test_same_family_distinct_task_models_pass_supervisor_normalization(workspace):
    path = workspace / ".orchestrator/config.yaml"
    data = yaml.safe_load(path.read_text())
    data["providers"]["reasoning"]["adapter"] = "claude"
    data["providers"]["engineering"]["adapter"] = "claude"
    path.write_text(yaml.safe_dump(data))

    claude = IntakeAdapter("anthropic")
    claude.next_result = {
        "outcome": "proposed",
        "summary": "Use distinct Claude models",
        "task": {
            "goal": "Produce a result",
            "acceptance": ["A result exists"],
            "risk": "T2",
            "validators": ["check"],
            "external_effects": False,
            "allowed_paths": ["result.txt"],
            "capabilities": {},
            "workflow_ref": "build-review",
            "workflow": None,
            "runtime_overrides": {
                "planner": {"model": "claude-opus-test", "effort": "high"},
                "implementer": {"model": "claude-sonnet-test", "effort": "high"},
                "reviewer": {"model": "claude-opus-test", "effort": "high"},
            },
        },
        "questions": [],
    }
    engine = Engine(workspace, {"claude": claude})
    try:
        engine.trust("operator")
        state = Supervisor(engine).ask(
            "Use Claude variants",
            task_id="same-family-intake",
            supervisor_runtime_override=RuntimeOverride(model="claude-opus-test", effort="high"),
        )
        assert state.status == "proposed", state.error
        prompt = json.loads(claude.requests[0].prompt)
        reviewer_runtime = prompt["available_runtime_options"]["roles"]["reviewer"]
        assert "error" not in reviewer_runtime
        assert reviewer_runtime["provider_resolution"]["family"] == "anthropic"
        assert "explicit distinct model IDs" in prompt["available_runtime_options"]["review_independence"]
        assert state.runtime_overrides["implementer"]["model"] == "claude-sonnet-test"
        assert state.runtime_overrides["reviewer"]["model"] == "claude-opus-test"
    finally:
        engine.close()


def test_same_family_same_task_model_fails_supervisor_normalization(workspace):
    path = workspace / ".orchestrator/config.yaml"
    data = yaml.safe_load(path.read_text())
    data["providers"]["reasoning"]["adapter"] = "claude"
    data["providers"]["engineering"]["adapter"] = "claude"
    path.write_text(yaml.safe_dump(data))

    claude = IntakeAdapter("anthropic")
    claude.next_result = {
        "outcome": "proposed",
        "summary": "Same model is not independent",
        "task": {
            "goal": "Produce a result",
            "acceptance": ["A result exists"],
            "risk": "T2",
            "validators": ["check"],
            "external_effects": False,
            "allowed_paths": ["result.txt"],
            "capabilities": {},
            "workflow_ref": "build-review",
            "workflow": None,
            "runtime_overrides": {
                "planner": {"model": "claude-opus-test", "effort": "high"},
                "implementer": {"model": "claude-opus-test", "effort": "high"},
                "reviewer": {"model": "claude-opus-test", "effort": "high"},
            },
        },
        "questions": [],
    }
    engine = Engine(workspace, {"claude": claude})
    try:
        engine.trust("operator")
        state = Supervisor(engine).ask("Use one Claude model", task_id="same-model-intake")
        assert state.status == "failed"
        assert "different provider family or explicit distinct model IDs" in state.error
        assert state.task is None
    finally:
        engine.close()



def test_propose_task_worker_routes_supervisor_runtime_override(workspace):
    reasoning, engineering = IntakeAdapter("anthropic"), IntakeAdapter("openai")
    registry = {"claude": reasoning, "codex": engineering}
    engine = Engine(workspace, registry)
    try:
        engine.trust("operator")
    finally:
        engine.close()

    service = ApplicationService(workspace)
    job = service.invoke(
        "propose_task",
        {
            "request": "Please add a result",
            "request_id": "supervisor-override-job",
            "task_id": "supervisor-override-job-task",
            "supervisor_runtime_override": {
                "model": "claude-opus-test",
                "effort": "high",
            },
        },
    )
    with service.queue() as queue:
        result = process_one(queue, registry=registry)
    assert result["id"] == job["id"]
    assert result["status"] == "succeeded"
    assert reasoning.requests[0].config.model == "claude-opus-test"
    assert reasoning.requests[0].config.effort == "high"
    intake = result["result"]
    assert intake["supervisor_model_variant_resolution"]["model"] == "claude-opus-test"
    assert intake["supervisor_model_variant_resolution"]["sources"]["model"] == "explicit_override"
