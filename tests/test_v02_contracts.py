"""The E2E review mismatch and versioned compatibility boundaries."""

import json
import sqlite3

import jsonschema
import pytest
from pydantic import ValidationError

from ai_orchestrator.contracts import ImplementationResult, IntakeState, PlanResult, ReviewResult, SupervisorResult, TaskDraft
from ai_orchestrator.models import OrchestratorError, TaskState, ValidatorConfig
from ai_orchestrator.project import Project, digest
from ai_orchestrator.store import Store
from conftest import approve_and_run, spec


def test_new_tasks_use_explicit_v2_role_contracts(engine):
    controller, reasoning, engineering = engine
    state = controller.create(spec())
    assert state.schema_version == 3
    state = approve_and_run(controller)
    assert state.status == "awaiting_acceptance"
    assert reasoning.requests[0].result_model is PlanResult
    assert engineering.requests[0].result_model is ImplementationResult
    assert reasoning.requests[-1].result_model is ReviewResult
    assert "blocking_findings" in reasoning.requests[-1].prompt


def test_explicit_blocker_overrides_approved_outcome(engine):
    controller, reasoning, _ = engine
    original = reasoning.execute
    def execute(request):
        if request.phase == "review":
            return ReviewResult(outcome="approved", summary="Inconsistent answer", blocking_findings=["Regression in required behavior"], observations=["Some checks passed"], evidence=[])
        return original(request)
    reasoning.execute = execute
    controller.create(spec())
    state = approve_and_run(controller)
    assert state.status == "awaiting_approval"
    assert state.attempt == 2
    assert "Regression" in state.feedback
    assert state.reviewed_snapshot is None


def test_blocked_review_never_repairs_or_accepts(engine):
    controller, reasoning, _ = engine
    original = reasoning.execute
    def execute(request):
        if request.phase == "review":
            return ReviewResult(outcome="blocked", summary="Missing access", blocking_findings=[], observations=[], evidence=[])
        return original(request)
    reasoning.execute = execute
    controller.create(spec())
    state = approve_and_run(controller)
    assert state.status == "failed"
    assert state.attempt == 1
    assert "agent reported blocked" in state.error


def test_wrong_role_result_fails_closed(engine):
    controller, reasoning, _ = engine
    from ai_orchestrator.models import AgentResult
    reasoning.execute = lambda request: AgentResult(outcome="completed", summary="Old response", findings=[], evidence=[])
    controller.create(spec())
    assert controller.run("task-1").status == "failed"


def test_legacy_pending_task_keeps_v1_wire_results_and_scope(engine):
    controller, reasoning, _ = engine
    state = controller.create(spec())
    old = state.model_dump()
    old["schema_version"] = 1
    old.pop("intake_id")
    old.pop("require_execution_approval")
    old.pop("allowed_paths", None)
    old.pop("capability_requirements", None)
    old.pop("provider_resolutions", None)
    with controller.store.db:
        controller.store.db.execute("UPDATE tasks SET data=? WHERE id=?", (json.dumps(old), state.spec.id))
    state = approve_and_run(controller)
    assert state.status == "awaiting_acceptance"
    from ai_orchestrator.models import AgentResult
    assert reasoning.requests[-1].result_model is AgentResult
    assert "findings" in controller.store.latest(state, "review")
    hashes = [artifact.sha256 for artifact in state.artifacts]
    accepted = controller.accept("task-1", "operator")
    reloaded = controller.store.get("task-1")
    assert reloaded.status == "succeeded"
    assert reloaded.schema_version == 1
    assert [a.sha256 for a in reloaded.artifacts[:-1]] == hashes
    assert accepted.reviewed_snapshot == reloaded.reviewed_snapshot


def test_empty_v2_validator_defaults_preserve_v1_profile_digest(workspace):
    profile, actual, context = Project(workspace).load()
    old = profile.model_dump()
    for validator in old["validators"].values():
        validator.pop("env")
        validator.pop("generated_paths")
    for provider in old["providers"].values():
        provider.pop("capabilities", None)
        provider.pop("priority", None)
    for role in old["roles"].values():
        role.pop("capabilities", None)
        role.pop("candidates", None)
    assert digest({"profile": old, "context": context}) == actual


def test_profile_change_with_nonempty_v2_settings_changes_digest(workspace):
    import yaml
    project = Project(workspace)
    old = project.load()[1]
    path = project.control / "config.yaml"
    data = yaml.safe_load(path.read_text())
    data["validators"]["check"]["env"] = {"TEST_MODE": "strict"}
    path.write_text(yaml.safe_dump(data))
    assert project.load()[1] != old


def test_database_upgrade_preserves_existing_rows_and_blocks_downgrade(workspace):
    project = Project(workspace)
    store = Store(project)
    store.db.execute("PRAGMA user_version=1")
    store.db.execute("INSERT OR REPLACE INTO metadata VALUES ('keep','present')")
    store.db.commit()
    store.close()
    store = Store(project)
    assert store.db.execute("PRAGMA user_version").fetchone()[0] == 2
    assert store.db.execute("SELECT value FROM metadata WHERE key='keep'").fetchone()[0] == "present"
    store.db.execute("PRAGMA user_version=999")
    store.close()
    with pytest.raises(OrchestratorError, match="unsupported runtime"):
        Store(project)


@pytest.mark.parametrize("model", [PlanResult, ImplementationResult, ReviewResult, SupervisorResult, TaskDraft])
def test_model_facing_schemas_are_strict_and_all_properties_required(model):
    schema = model.model_json_schema()
    jsonschema.Draft202012Validator.check_schema(schema)
    for node in [schema, *schema.get("$defs", {}).values()]:
        if node.get("type") == "object":
            assert node["additionalProperties"] is False
            assert set(node["properties"]) == set(node["required"])
            assert all("default" not in prop for prop in node["properties"].values())


@pytest.mark.parametrize("value", [".", "/tmp", "..", "src/../tests", "**/*", "foo/*", "src//cache", ".orchestrator/runtime", ".git", "foo/.git/cache", "foo\\cache"])
def test_generated_paths_cannot_disable_whole_workspace_guard(value):
    with pytest.raises(ValidationError):
        ValidatorConfig(argv=["python"], generated_paths=[value])


@pytest.mark.parametrize("key", ["HOME", "PATH", "PYTHONPATH", "GIT_DIR", "LD_PRELOAD", "DYLD_LIBRARY_PATH", "OPENAI_API_KEY", "TOKEN", "BASH_ENV", "lowercase"])
def test_unsafe_validator_environment_rejected(key):
    with pytest.raises(ValidationError):
        ValidatorConfig(argv=["python"], env={key: "value"})
