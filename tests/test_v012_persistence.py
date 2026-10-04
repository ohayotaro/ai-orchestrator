"""v0.12 persisted-contract and migration compatibility regressions."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from ai_orchestrator.contracts import IntakeState
from ai_orchestrator.human_gates import HumanGate
from ai_orchestrator.models import Artifact, OrchestratorError, TaskSpec, TaskState
from ai_orchestrator.persistence import (
    HUMAN_GATE_DB_READABLE_VERSIONS,
    PERSISTED_CONTRACT_RULES,
    RUNTIME_DB_READABLE_VERSIONS,
    decode_versioned_model_json,
    normalize_control_evidence,
    persistence_compatibility_report,
    validate_database_version,
)
from ai_orchestrator.project import atomic_write


FIXTURE = Path(__file__).parent / "fixtures" / "persistence" / "v0x_states.json"


def retained() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_retained_taskstate_versions_remain_readable_without_rewrite():
    values = retained()["task_states"]
    assert [item["schema_version"] for item in values] == list(range(1, 8))
    for raw in values:
        before = json.dumps(raw, sort_keys=True)
        state = decode_versioned_model_json(
            json.dumps(raw), rule_key="task_state", model=TaskState
        )
        assert state.schema_version == raw["schema_version"]
        assert json.dumps(raw, sort_keys=True) == before
        assert state.require_execution_approval is False
    assert values[3]["allowed_paths"] == ["calculator.py"]
    assert values[5]["runtime_overrides"]["implementer"]["model"] == "fixture-model"


def test_retained_intake_and_gate_versions_remain_readable():
    for raw in retained()["intake_states"]:
        intake = decode_versioned_model_json(
            json.dumps(raw), rule_key="intake_state", model=IntakeState
        )
        assert intake.schema_version == raw["schema_version"]
    gate = decode_versioned_model_json(
        json.dumps(retained()["human_gate"]), rule_key="human_gate", model=HumanGate
    )
    assert gate.schema_version == 1
    legacy_artifact = Artifact.model_validate(retained()["legacy_artifact"])
    assert legacy_artifact.schema_version == 1
    assert legacy_artifact.id is None


@pytest.mark.parametrize(
    ("rule_key", "model", "payload"),
    [
        (
            "task_state",
            TaskState,
            {
                **retained()["task_states"][-1],
                "schema_version": 8,
            },
        ),
        (
            "intake_state",
            IntakeState,
            {
                **retained()["intake_states"][-1],
                "schema_version": 5,
            },
        ),
        (
            "human_gate",
            HumanGate,
            {
                **retained()["human_gate"],
                "schema_version": 2,
            },
        ),
    ],
)
def test_unknown_persisted_contract_versions_fail_closed(rule_key, model, payload):
    with pytest.raises(OrchestratorError, match="unsupported persisted"):
        decode_versioned_model_json(json.dumps(payload), rule_key=rule_key, model=model)


@pytest.mark.parametrize("value", [True, "7", 7.0, None])
def test_persisted_schema_versions_are_strict_integers(value):
    payload = dict(retained()["task_states"][-1])
    payload["schema_version"] = value
    with pytest.raises(OrchestratorError, match="must be an integer"):
        decode_versioned_model_json(
            json.dumps(payload), rule_key="task_state", model=TaskState
        )


def test_unknown_database_versions_fail_closed():
    validate_database_version("runtime", 2, RUNTIME_DB_READABLE_VERSIONS)
    validate_database_version("human-gate", 1, HUMAN_GATE_DB_READABLE_VERSIONS)
    with pytest.raises(OrchestratorError, match="unsupported runtime database version"):
        validate_database_version("runtime", 99, RUNTIME_DB_READABLE_VERSIONS)
    with pytest.raises(OrchestratorError, match="unsupported human-gate database version"):
        validate_database_version("human-gate", 99, HUMAN_GATE_DB_READABLE_VERSIONS)


def test_store_rejects_unknown_task_version_without_rewriting(engine):
    controller, _reasoning, _engineering = engine
    raw = retained()["task_states"][-1]
    task_id = raw["spec"]["id"]
    bad = {**raw, "schema_version": 99}
    encoded = json.dumps(bad, sort_keys=True)
    with controller.store.db:
        controller.store.db.execute(
            "INSERT INTO tasks(id,data) VALUES (?,?)", (task_id, encoded)
        )
    with pytest.raises(OrchestratorError, match="schema_version=99"):
        controller.store.get(task_id)
    stored = controller.store.db.execute(
        "SELECT data FROM tasks WHERE id=?", (task_id,)
    ).fetchone()[0]
    assert stored == encoded


def test_legacy_artifact_wire_shape_and_approval_scope_are_stable(engine):
    controller, _reasoning, _engineering = engine
    task = TaskSpec(
        id="fixture-approval-scope",
        goal="prove legacy artifact scope stability",
        acceptance=["scope is unchanged"],
        risk="T0",
    )
    state = controller.create(task)
    # Exercise the oldest Workflow Schema state version whose approval scope
    # binds Artifact metadata.
    state.schema_version = 4

    # approval_scope verifies artifact bytes first, so retain an actual v1
    # artifact on disk rather than weakening the production verifier in this
    # migration regression.
    text = '{"legacy":true}\n'
    path = ".orchestrator/runtime/fixture/0-plan.json"
    atomic_write(controller.project.root / path, text)
    legacy_raw = {
        **retained()["legacy_artifact"],
        "path": path,
        "sha256": hashlib.sha256(text.encode()).hexdigest(),
    }
    legacy_artifact = Artifact.model_validate(legacy_raw)
    assert legacy_artifact.model_dump() == legacy_raw

    state.artifacts = [legacy_artifact]
    before = controller.approval_scope(state)

    # Round-tripping a retained Artifact v1 through the new model must not add
    # v2 null fields and thereby change an already-approved digest.
    round_tripped = TaskState.model_validate_json(state.model_dump_json())
    after = controller.approval_scope(round_tripped)
    assert after == before
    assert round_tripped.artifacts[0].model_dump() == legacy_raw


def test_new_artifact_v2_identity_and_legacy_v1_read(engine):
    controller, _reasoning, _engineering = engine
    artifact = controller.store.write_artifact(
        "fixture-owner", 3, "provider_provenance", {"schema_version": 1, "records": []}
    )
    assert artifact.schema_version == 2
    assert artifact.id and artifact.id.startswith("A-")
    assert artifact.owner_id == "fixture-owner"
    assert artifact.created_at
    assert controller.store.read_artifact(artifact)["schema_version"] == 1

    raw = b'{"legacy":true}\n'
    path = ".orchestrator/runtime/fixture-owner/1-plan-legacy.json"
    target = controller.project.root / path
    atomic_write(target, raw.decode())
    legacy = Artifact(
        kind="plan",
        path=path,
        sha256=hashlib.sha256(raw).hexdigest(),
        attempt=1,
    )
    assert controller.store.read_artifact(legacy) == {"legacy": True}


def test_legacy_v011_recovery_evidence_is_read_migrated_only_in_memory(engine):
    controller, _reasoning, _engineering = engine
    value = retained()["legacy_recovery_evidence"]
    text = json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    path = ".orchestrator/runtime/fixture-owner/1-recovery-legacy.json"
    target = controller.project.root / path
    atomic_write(target, text)
    legacy = Artifact(
        kind="recovery",
        path=path,
        sha256=hashlib.sha256(text.encode()).hexdigest(),
        attempt=1,
    )
    before = target.read_bytes()
    view = controller.store.read_artifact(legacy)
    assert view["schema_version"] == 1
    assert view["classification"] == "uncertain_effect"
    assert target.read_bytes() == before


def test_unknown_control_evidence_version_fails_closed():
    with pytest.raises(OrchestratorError, match="UsageEvidence"):
        normalize_control_evidence(
            "usage", {"schema_version": 2, "records": [], "summary": {}}
        )


def test_runtime_event_envelope_has_stable_identity(engine):
    controller, _reasoning, _engineering = engine
    with controller.store.db:
        controller.store._event(None, "fixture.event", {"value": 1})
    event = controller.store.events()[-1]
    assert event["schema_version"] == 1
    assert event["event_id"] == f"E-{event['sequence']}"
    assert event["source"] == "runtime_event_log"
    assert event["payload"] == {"value": 1}


def test_cli_persistence_report(workspace, capsys):
    from ai_orchestrator.cli import main

    assert main(["--project", str(workspace), "persistence"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["contracts"]["task_state"]["write_version"] == 7
    assert report["contracts"]["artifact"]["write_version"] == 2


def test_persistence_report_is_explicit_and_complete():
    report = persistence_compatibility_report()
    assert report["schema_version"] == 1
    assert report["policy"]["automatic_rewrite"] is False
    assert report["policy"]["unknown_version"].startswith("fail closed")
    assert report["contracts"]["task_state"]["readable_versions"] == list(range(1, 8))
    assert report["contracts"]["artifact"]["write_version"] == 2
    assert report["contracts"]["recovery_evidence"]["readable_versions"] == [0, 1]
    assert set(PERSISTED_CONTRACT_RULES) <= set(report["contracts"])
