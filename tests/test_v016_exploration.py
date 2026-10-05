"""v0.16 pre-authority exploration lifecycle and negative authority regressions."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from ai_orchestrator.contracts import IntakeState
from ai_orchestrator.engine import Engine
from ai_orchestrator.exploration import (
    Explorations, ExplorationResult, ExplorationState, ExploreInput,
    ExplorationProposalInput, _context,
)
from ai_orchestrator.human_gates import HumanGateBroker, compact_gate_summary
from ai_orchestrator.jobs import Job, JobQueue
from ai_orchestrator.models import OrchestratorError, TaskState
from ai_orchestrator.operational import diagnose_runtime, retention_plan, apply_retention, create_backup, restore_backup
from ai_orchestrator.persistence import decode_versioned_model_json, persistence_compatibility_report
from ai_orchestrator.project import Project, digest
from ai_orchestrator.runtime_options import RuntimeOptionsDescriptor, RuntimeValueDescriptor
from ai_orchestrator.service import ApplicationService, TOOLS
from ai_orchestrator.store import Store
from ai_orchestrator.supervisor import Supervisor
from ai_orchestrator.worker import process_one
from test_v04_gates import IntakeAdapter


class ExploreAdapter(IntakeAdapter):
    def __init__(self, family):
        super().__init__(family)
        self.bad = None
        self.payloads = []

    def describe_runtime_options(self, config, workspace):
        return RuntimeOptionsDescriptor(model=RuntimeValueDescriptor(mode="passthrough"),
                                        effort=RuntimeValueDescriptor(mode="passthrough"))

    def execute(self, request):
        if request.result_model is not ExplorationResult:
            return super().execute(request)
        self.requests.append(request)
        payload = json.loads(request.prompt)
        self.payloads.append(payload)
        assert request.phase == "supervise"
        assert not (request.workspace / ".orchestrator").exists()
        assert request.provider_permissions == frozenset()
        if self.bad == "write":
            (request.workspace / "unauthorized.txt").write_text("must not integrate")
        if self.bad == "crash":
            raise SystemExit("simulated process loss")
        result = dict(summary=payload["request"], hypotheses=["Investigate the existing helper"],
                      assumptions=[], options=["Small local change", "Larger rewrite"],
                      tradeoffs=["Prefer bounded impact"], open_questions=["Which behavior matters?"],
                      decisions=[payload["request"]], discarded=["Previous tentative direction"] if payload["prior_context"] else [],
                      reported_paths=["input.txt"])
        if self.bad == "authority":
            result["allowed_paths"] = ["all.py"]
        if self.bad == "path":
            result["reported_paths"] = [".orchestrator/config.yaml"]
        if self.bad == "missing_path":
            result["reported_paths"] = ["not-inspected.py"]
        return result


@pytest.fixture
def sessions(workspace):
    providers = {"claude": ExploreAdapter("anthropic"), "codex": ExploreAdapter("openai")}
    engine = Engine(workspace, providers)
    engine.trust("operator")
    yield Explorations(engine), providers
    engine.close()


def counts(store):
    return {table: store.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("tasks", "intakes", "approvals")}


def test_multiturn_exploration_is_non_authoritative_and_compacted(sessions):
    sessions, providers = sessions
    project = sessions.project
    before = (project.snapshot(), project.control_snapshot(), project.load()[1], counts(sessions.store))
    state = sessions.turn("Not sure what to change; compare options")
    first_artifact = state.turn_artifacts[-1]
    for revision, message in [(1, "Change direction: do not rewrite"), (2, "Prefer a narrow helper")]:
        state = sessions.turn(message, exploration_id=state.id, expected_revision=revision)
    assert state.status == "active" and state.revision == 3 and state.calls == 3
    assert before == (project.snapshot(), project.control_snapshot(), project.load()[1], counts(sessions.store))
    assert sessions.store.trusted(state.profile_digest)
    assert not list((project.control / "knowledge/candidates").glob("*.json"))
    assert len(state.turn_artifacts) == 3
    assert sessions.store.read_artifact(first_artifact)["request"].startswith("Not sure")
    assert state.current.discarded
    current_context = _context(state)
    assert current_context["selection"]["omitted_turn_count"] == 2
    assert len(current_context["selection"]["selected_turns"]) == 1
    for call in providers["claude"].payloads:
        assert len(json.dumps(call).encode()) < 65536
    evidence = sessions.store.read_artifact(state.turn_artifacts[-1])
    assert evidence["repository_evidence"][0]["path"] == "input.txt"
    assert evidence["provider_provenance"]["workspace"]["mode"] == "read_only_disposable"
    assert evidence["provider_provenance"]["workspace"]["cleaned"]


def test_explicit_transition_then_three_independent_humangates(sessions):
    sessions, providers = sessions
    state = sessions.turn("Explore first")
    state = sessions.turn("User changes direction", exploration_id=state.id, expected_revision=1)
    intake = sessions.propose(state.id, 2, "Now propose the narrow result", task_id="explored-task")
    assert counts(sessions.store) == {"tasks": 0, "intakes": 1, "approvals": 0}
    assert intake.schema_version == 6 and intake.calls == 3
    assert intake.exploration.session_id == state.id and intake.exploration.revision == 2
    assert intake.usage_evidence["summary"]["calls"] == 3
    broker = HumanGateBroker(ApplicationService(sessions.project.root), "explore-session", {"name": "test", "version": "1"})
    try:
        gate = broker.prepare("start", intake.id, "start-explored")
        assert "Exploration source:" in compact_gate_summary(gate)
        assert gate.preview["exploration"]["revision"] == 2
        started = broker.resolve(gate, {"action": "accept", "content": {"decision": "yes"}})
        assert started["gate_status"] == "applied", started
        assert sessions.store.get_exploration(state.id).status == "transitioned"
        task = sessions.store.get("explored-task")
        assert task.schema_version == 9 and task.exploration == intake.exploration
        assert sessions.store.db.execute("SELECT COUNT(*) FROM approvals").fetchone()[0] == 0
        with broker.service.queue() as queue:
            planned = process_one(queue, registry=providers)
        assert planned["result"]["status"] == "awaiting_approval"
        gate = broker.prepare("execution", task.spec.id, "exec-explored")
        approved = broker.resolve(gate, {"action": "accept", "content": {"decision": "yes"}})
        assert approved["gate_status"] == "applied", approved
        with broker.service.queue() as queue:
            executed = process_one(queue, registry=providers)
        assert executed["result"]["status"] == "awaiting_acceptance", executed
        gate = broker.prepare("acceptance", task.spec.id, "accept-explored")
        accepted = broker.resolve(gate, {"action": "accept", "content": {"decision": "yes"}})
        assert accepted["gate_status"] == "applied", accepted
        finished = sessions.store.get(task.spec.id)
        assert finished.status == "succeeded" and finished.calls == 6
        assert sessions.engine.usage_evidence(finished)["summary"]["calls"] == 6
        assert sessions.store.latest(finished, "exploration_transition")["decision"] == intake.request
    finally:
        broker.close()
    with pytest.raises(OrchestratorError, match="already became"):
        sessions.abandon(state.id, 2)


@pytest.mark.parametrize("action", ["revise", "abandon"])
def test_old_start_gate_is_invalidated_by_exploration_change(sessions, action):
    sessions, _ = sessions
    state = sessions.turn("Explore")
    intake = sessions.propose(state.id, 1, "Propose one change", task_id="stale-start")
    broker = HumanGateBroker(ApplicationService(sessions.project.root), "stale-gate", {"name": "test", "version": "1"})
    try:
        old = broker.prepare("start", intake.id, "old-start")
        if action == "revise":
            state = sessions.turn("Actually another direction", exploration_id=state.id, expected_revision=1)
            assert state.revision == 2 and state.status == "active"
        else:
            state = sessions.abandon(state.id, 1)
            assert state.status == "abandoned"
        result = broker.resolve(old, {"action": "accept", "content": {"decision": "yes"}})
        assert result["gate_status"] == "stale"
        assert sessions.store.db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0
        assert sessions.store.get_intake(intake.id).status in ("superseded", "withdrawn")
    finally:
        broker.close()


def test_session_revision_and_intake_reply_to_cannot_bypass_transition(sessions):
    sessions, _ = sessions
    state = sessions.turn("Explore")
    intake = sessions.propose(state.id, 1, "Propose one change")
    with pytest.raises(OrchestratorError, match="source exploration"):
        Supervisor(sessions.engine).ask("bypass", reply_to=intake.id)
    with pytest.raises(OrchestratorError, match="revision changed"):
        sessions.turn("old branch", exploration_id=state.id, expected_revision=2)
    with pytest.raises(OrchestratorError, match="only an active"):
        sessions.propose(state.id, 1, "duplicate")


@pytest.mark.parametrize("bad", ["write", "authority", "path", "missing_path"])
def test_reasoning_cannot_grant_authority_or_modify_the_project(sessions, bad):
    sessions, providers = sessions
    before = (sessions.project.snapshot(), sessions.project.control_snapshot(), counts(sessions.store))
    providers["claude"].bad = bad
    state = sessions.turn("Inspect")
    assert state.status == "failed" and state.error
    assert before == (sessions.project.snapshot(), sessions.project.control_snapshot(), counts(sessions.store))
    with pytest.raises(OrchestratorError):
        sessions.propose(state.id, 1, "force it")


def test_interrupted_turn_is_read_only_diagnosed_and_never_replayed(sessions):
    sessions, providers = sessions
    providers["claude"].bad = "crash"
    with pytest.raises(SystemExit):
        sessions.turn("Crash after durable reservation")
    session_id = sessions.store.exploration_ids()[0]
    state = sessions.describe(session_id)
    assert state["status"] == "running" and state["calls"] == 1
    assert state["usage_evidence"]["summary"]["call_coverage"]["status"] == "incomplete"
    with pytest.raises(OrchestratorError):
        sessions.turn("Retry", exploration_id=session_id, expected_revision=1)
    assert len(providers["claude"].requests) == 1
    report = diagnose_runtime(sessions.project.root)
    assert session_id in report["runtime:state"]["unfinished_explorations"]
    state = sessions.abandon(session_id, 1)
    assert state.status == "abandoned" and state.calls == 1


def test_profile_and_repository_drift_fail_closed_and_revision_can_refresh_snapshot(sessions):
    sessions, _ = sessions
    state = sessions.turn("Inspect repository")
    (sessions.project.root / "input.txt").write_text("changed by user")
    with pytest.raises(OrchestratorError, match="worktree changed"):
        sessions.propose(state.id, 1, "Propose")
    state = sessions.turn("Reinspect changed repository", exploration_id=state.id, expected_revision=1)
    assert state.workspace_snapshot == sessions.project.snapshot()
    assert sessions.propose(state.id, 2, "Use the new snapshot").status == "proposed"
    (sessions.project.control / "policies/drift.md").write_text("new policy")
    with pytest.raises(OrchestratorError, match="profile changed"):
        sessions.turn("new turn", exploration_id=state.id, expected_revision=2)


def test_budget_is_cumulative_across_turns_and_proposal(sessions):
    sessions, providers = sessions
    # Trusted configuration, not a model-generated setting.
    path = sessions.project.control / "config.yaml"
    config = yaml.safe_load(path.read_text())
    config["policy"]["max_agent_calls"] = 2
    path.write_text(yaml.safe_dump(config))
    engine = Engine(sessions.project.root, providers)
    try:
        engine.trust("operator")
        ex = Explorations(engine)
        state = ex.turn("First")
        state = ex.turn("Second", exploration_id=state.id, expected_revision=1)
        with pytest.raises(OrchestratorError, match="budget"):
            ex.propose(state.id, 2, "No budget remains")
        assert len(providers["claude"].requests) == 2
        assert counts(engine.store)["tasks"] == 0
    finally:
        engine.close()


def test_exploration_queue_is_idempotent_and_revision_bound(sessions):
    sessions, providers = sessions
    service = ApplicationService(sessions.project.root)
    params = {"request": "ambiguous goal", "request_id": "explore-idempotent"}
    first = service.invoke("explore", params)
    assert first["schema_version"] == 2
    assert first == service.invoke("explore", params)
    assert not sessions.store.exploration_ids()
    with service.queue() as queue:
        result = process_one(queue, registry=providers)
    assert result["status"] == "succeeded", result
    session_id = result["result"]["id"]
    assert service.invoke("get_exploration", {"exploration_id": session_id})["status"] == "active"
    assert service.invoke("list_explorations", {})["total"] == 1
    assert service.invoke("explore", params)["id"] == first["id"]
    assert len(providers["claude"].requests) == 1
    with pytest.raises(OrchestratorError, match="different arguments"):
        service.invoke("explore", {**params, "request": "different"})
    job = service.invoke("propose_from_exploration", {"exploration_id": session_id, "expected_revision": 1,
                                                      "decision": "Make a proposal", "request_id": "transition-1"})
    with service.queue() as queue:
        result = process_one(queue, registry=providers)
    assert result["status"] == "succeeded" and result["result"]["status"] == "proposed", result
    assert counts(sessions.store)["tasks"] == 0


def test_retention_backup_and_restore_preserve_exploration_evidence(sessions, tmp_path_factory):
    sessions, _ = sessions
    state = sessions.turn("Persist exploration")
    intake = sessions.propose(state.id, 1, "Build a proposal")
    sessions.abandon(state.id, 1)
    state = sessions.store.get_exploration(state.id)
    before = {item.path: hashlib.sha256((sessions.project.root/item.path).read_bytes()).hexdigest() for item in state.artifacts}
    cutoff = (datetime.now(timezone.utc) + timedelta(seconds=5)).isoformat()
    plan = retention_plan(sessions.project.root, cutoff=cutoff)
    assert not set(before).intersection(plan["orphan_artifacts"])
    apply_retention(sessions.project.root, cutoff=cutoff, scope=plan["scope"], actor="operator")
    assert before == {name: hashlib.sha256((sessions.project.root/name).read_bytes()).hexdigest() for name in before}
    archive = tmp_path_factory.mktemp("backup") / "full.zip"
    saved = create_backup(sessions.project.root, archive, mode="full")
    target = tmp_path_factory.mktemp("restore")
    result = restore_backup(target, archive, scope=saved["scope"], actor="operator", replace=True,
                            acknowledge_authority_restore=True)
    assert result["restored"]
    store = Store(Project(target))
    try:
        restored = store.get_exploration(state.id)
        assert restored.model_dump() == state.model_dump()
        for artifact in restored.artifacts:
            store.read_artifact(artifact)
    finally:
        store.close()


@pytest.mark.parametrize("component", ["state", "turn", "transition"])
def test_tampering_blocks_exploration_inspection_or_transition(sessions, component):
    sessions, _ = sessions
    state = sessions.turn("Create evidence")
    if component == "state":
        with sessions.store.db:
            raw = state.model_dump(); raw["schema_version"] = 99
            sessions.store.db.execute("UPDATE explorations SET data=? WHERE id=?", (json.dumps(raw), state.id))
        with pytest.raises(OrchestratorError, match="unsupported persisted"):
            sessions.describe(state.id)
    else:
        if component == "transition":
            intake = sessions.propose(state.id, 1, "Propose")
            artifact = intake.exploration.transition_artifact
        else:
            artifact = state.turn_artifacts[0]
        (sessions.project.root/artifact.path).write_text("{}")
        with pytest.raises(OrchestratorError, match="integrity"):
            sessions.describe(state.id)
        assert not diagnose_runtime(sessions.project.root)["runtime:state"]["integrity_ok"]


def test_legacy_task_and_intake_hashes_do_not_gain_exploration_null_field(workspace):
    fixture = json.loads((Path(__file__).parent / "fixtures/persistence/v0x_states.json").read_text())
    for data in fixture["task_states"]:
        state = TaskState.model_validate(data)
        assert "exploration" not in state.model_dump()
    for data in fixture["intake_states"]:
        state = IntakeState.model_validate(data)
        assert "exploration" not in state.model_dump()
    report = persistence_compatibility_report()
    assert report["databases"]["runtime_state"]["write_version"] == 3
    assert report["contracts"]["exploration_state"]["write_version"] == 1


def test_v015_runtime_upgrade_adds_table_without_rewriting_old_rows(workspace):
    project = Project(workspace)
    store = Store(project)
    try:
        with store.db:
            store.db.execute("DROP TABLE explorations")
            store.db.execute("PRAGMA user_version=2")
            store.db.execute("INSERT INTO metadata VALUES ('fixture','keep')")
        before = store.db.execute("SELECT * FROM metadata").fetchall()
    finally:
        store.close()
    # Diagnostic read on v2 must not add the new table.
    path = project.runtime/"state.sqlite3"
    raw = path.read_bytes()
    assert diagnose_runtime(workspace)["runtime:state"]["ok"]
    assert path.read_bytes() == raw
    store = Store(project)
    try:
        assert store.db.execute("PRAGMA user_version").fetchone()[0] == 3
        assert store.exploration_ids() == []
        assert store.db.execute("SELECT * FROM metadata").fetchall() == before
    finally:
        store.close()


@pytest.mark.parametrize("extra", ["approved", "allowed_paths", "external_effects", "provider_permissions", "validators", "budget"])
def test_tool_inputs_cannot_smuggle_authority(extra):
    with pytest.raises(ValidationError):
        ExploreInput.model_validate({"request": "explore", "request_id": "x", extra: True})
    with pytest.raises(ValidationError):
        ExplorationProposalInput.model_validate({"exploration_id": "X-test", "expected_revision": 1,
                                                 "decision": "propose", "request_id": "x", extra: True})
    assert all(name not in TOOLS for name in ("exploration_execute", "exploration_trust", "exploration_promote"))


def test_proposal_process_loss_preserves_session_call_coverage_and_abandonment(sessions, monkeypatch):
    sessions, providers = sessions
    state = sessions.turn("Inspect before a proposal")
    original_save = sessions.store.save_intake
    def crash(intake, kind, **kwargs):
        result = original_save(intake, kind, **kwargs)
        if kind == "supervisor.started":
            raise SystemExit("proposal process lost after durable call marker")
        return result
    monkeypatch.setattr(sessions.store, "save_intake", crash)
    with pytest.raises(SystemExit):
        sessions.propose(state.id, 1, "Create a proposal")
    view = sessions.describe(state.id)
    assert view["status"] == "proposing" and view["calls"] == 2
    assert view["usage_evidence"]["summary"]["call_coverage"]["missing_calls"] == 1
    intake_id = view["latest_intake_id"]
    assert intake_id and sessions.store.get_intake(intake_id).status == "running"
    abandoned = sessions.abandon(state.id, 1)
    assert abandoned.status == "abandoned" and abandoned.calls == 2
    assert sessions.store.get_intake(intake_id).status == "withdrawn"
    assert not sessions.store.task_ids()


def test_strict_budget_unknown_telemetry_blocks_exploration_before_call(sessions):
    sessions, providers = sessions
    path = sessions.project.control/"config.yaml"
    config = yaml.safe_load(path.read_text())
    config["policy"]["budget"] = {"max_total_tokens": 1000}
    path.write_text(yaml.safe_dump(config))
    engine = Engine(sessions.project.root, providers)
    try:
        engine.trust("operator")
        with pytest.raises(OrchestratorError, match="strict budget"):
            Explorations(engine).turn("Do not guess tokens")
        assert not providers["claude"].requests
        assert not engine.store.exploration_ids()
    finally:
        engine.close()


def test_runtime_override_is_frozen_and_cannot_be_changed_mid_exploration(sessions):
    sessions, providers = sessions
    state = sessions.turn("Specific model", supervisor_runtime_override={"model": "model-a", "effort": "high"})
    assert state.model_variant_resolution["model"] == "model-a"
    assert providers["claude"].requests[-1].config.model == "model-a"
    with pytest.raises(ValidationError, match="frozen"):
        sessions.turn("Change model silently", exploration_id=state.id, expected_revision=1,
                      supervisor_runtime_override={"model": "model-b"})
    state = sessions.turn("Continue with same binding", exploration_id=state.id, expected_revision=1)
    assert state.model_variant_resolution["model"] == "model-a"
    intake = sessions.propose(state.id, 2, "Propose with inherited reasoning identity")
    assert intake.supervisor_model_variant_resolution["model"] == "model-a"


def test_reasoning_result_cannot_exceed_context_budget_or_use_traversal():
    base = {"summary": "s", "hypotheses": [], "assumptions": [], "options": [], "tradeoffs": [],
            "open_questions": [], "decisions": [], "discarded": [], "reported_paths": []}
    for path in ("../secrets", ".git/config", ".orchestrator/config.yaml", "/tmp/file"):
        with pytest.raises(ValidationError):
            ExplorationResult.model_validate({**base, "reported_paths": [path]})
    with pytest.raises(ValidationError, match="12 KiB"):
        ExplorationResult.model_validate({**base, "hypotheses": ["a"*1000]*12, "assumptions": ["b"*1000]*12})


def test_repeated_read_only_session_inspection_never_creates_work_or_changes_rows(sessions):
    sessions, providers = sessions
    state = sessions.turn("Inspect once")
    before = tuple(sessions.store.db.iterdump())
    service = ApplicationService(sessions.project.root)
    for _ in range(2):
        assert service.invoke("get_exploration", {"exploration_id": state.id})["status"] == "active"
        service.invoke("get_exploration_artifact", {"exploration_id": state.id, "artifact_id": state.artifacts[0].id})
        service.invoke("list_explorations", {})
    assert tuple(sessions.store.db.iterdump()) == before
    assert len(providers["claude"].requests) == 1


@pytest.mark.parametrize("command", ["explore", "exploration-propose"])
def test_cli_provider_calls_cannot_bypass_host_worker_boundary(workspace, monkeypatch, capsys, command):
    from ai_orchestrator.cli import main
    monkeypatch.setenv("CLAUDECODE", "host-session")
    args = ["explore", "inspect"] if command == "explore" else ["exploration-propose", "X-test", "--revision", "1", "--decision", "propose"]
    assert main(["--project", str(workspace), *args]) == 1
    assert "nested provider calls" in capsys.readouterr().err
    assert not (workspace / ".orchestrator/runtime/state.sqlite3").exists()
