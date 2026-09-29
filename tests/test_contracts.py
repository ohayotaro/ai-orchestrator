import json
import sys

import jsonschema
import pytest
import yaml
from pydantic import ValidationError

from ai_orchestrator import knowledge
from ai_orchestrator.cli import main
from ai_orchestrator.models import AgentResult, Artifact, OrchestratorError, Policy, Profile, Proposal, TaskSpec, TaskState
from ai_orchestrator.project import Project, confined, digest, initialize, load_yaml
from conftest import spec


@pytest.mark.parametrize("value", ["../escape", "a/b", ".", "..", "a b", "-leading", "a" * 65, "名前"])
def test_invalid_identifiers(value):
    with pytest.raises(ValidationError):
        spec(task_id=value)


@pytest.mark.parametrize("payload", [{"risk": "T4"}, {"external_effects": "false"}, {"schema_version": 2}, {"extra_setting": 1}])
def test_task_contract_fails_closed(payload):
    original = spec().model_dump()
    original.update(payload)
    with pytest.raises(ValidationError):
        TaskSpec.model_validate(original)


@pytest.mark.parametrize("value", ["../../etc", "/etc", "a/../b", "a\\b", ".orchestrator", ".git"])
def test_protected_paths_no_traversal(value):
    with pytest.raises(ValidationError):
        Policy(protected_paths=[value])


def test_yaml_duplicate_keys_rejected(tmp_path):
    path = tmp_path / "duplicate.yaml"
    path.write_text("name: first\nname: second\n")
    with pytest.raises(OrchestratorError, match="unique"):
        load_yaml(path)


def test_control_symlink_escape_rejected(tmp_path):
    (tmp_path / "link").symlink_to(tmp_path.parent, target_is_directory=True)
    with pytest.raises(OrchestratorError, match="symlink"):
        confined(tmp_path, "link/anything")


def test_init_does_not_overwrite(workspace):
    before = (workspace / ".orchestrator/config.yaml").read_bytes()
    with pytest.raises(OrchestratorError, match="never overwrites"):
        initialize(workspace, "replacement")
    assert before == (workspace / ".orchestrator/config.yaml").read_bytes()


def test_knowledge_requires_evidence_and_exact_human_promotion(workspace):
    old_digest = Project(workspace).load()[1]
    with pytest.raises(ValidationError):
        knowledge.propose(workspace, "policy", "candidate", [])
    proposal = knowledge.propose(workspace, "policy", "Keep schema snapshots current", ["task:T-42"])
    assert old_digest == Project(workspace).load()[1]
    with pytest.raises(OrchestratorError, match="changed"):
        knowledge.promote(workspace, proposal.id, "wrong", "operator")
    result = knowledge.promote(workspace, proposal.id, digest(proposal.model_dump()), "operator")
    assert result.status == "approved"
    assert old_digest != Project(workspace).load()[1]
    assert (workspace / f".orchestrator/policies/{proposal.id}.md").is_file()
    with pytest.raises(OrchestratorError, match="candidate"):
        knowledge.promote(workspace, proposal.id, digest(proposal.model_dump()), "operator")


def test_all_contract_schemas_are_valid(workspace):
    profile = Project(workspace).load()[0]
    instances = [profile, spec(), AgentResult(outcome="completed", summary="ok", findings=[], evidence=[]), Artifact(kind="plan", path="x", sha256="a" * 64, attempt=0), TaskState(spec=spec(), profile_digest="hash"), Proposal(id="p1", kind="knowledge", statement="fact", evidence=["source"])]
    for instance in instances:
        schema = type(instance).model_json_schema()
        jsonschema.Draft202012Validator.check_schema(schema)
        jsonschema.validate(instance.model_dump(), schema)


def test_cli_schema_without_project(tmp_path, capsys):
    assert main(["--project", str(tmp_path), "schema", "task"]) == 0
    schema = json.loads(capsys.readouterr().out)
    assert schema["additionalProperties"] is False
    assert "acceptance" in schema["required"]


def test_cli_create_status_events(workspace, capsys):
    source = workspace / "task-input.json"
    source.write_text(spec(risk="T0").model_dump_json())
    assert main(["--project", str(workspace), "create", "--task-file", str(source)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ready"
    assert main(["--project", str(workspace), "status", "task-1"]) == 0
    assert json.loads(capsys.readouterr().out)["spec"]["risk"] == "T0"
    assert main(["--project", str(workspace), "events", "--task-id", "task-1"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["kind"] == "task.created"


def test_missing_provider_is_a_clear_error(engine, monkeypatch):
    from ai_orchestrator.providers import CodexAdapter
    controller, _, _ = engine
    monkeypatch.setattr("ai_orchestrator.providers.shutil.which", lambda value: None)
    with pytest.raises(OrchestratorError, match="not found"):
        CodexAdapter().doctor(controller.profile.providers["engineering"], controller.project.root)


@pytest.mark.parametrize("value", [True, False, "1", 1.0])
def test_schema_version_never_coerces(value):
    payload = spec().model_dump()
    payload["schema_version"] = value
    with pytest.raises(ValidationError):
        TaskSpec.model_validate(payload)


def test_artifact_cannot_escape_control_root(engine):
    controller, _, _ = engine
    artifact = Artifact(kind="review", path="../outside", sha256="a" * 64, attempt=1)
    with pytest.raises(OrchestratorError, match="escapes"):
        controller.store.read_artifact(artifact)


def test_snapshot_covers_untracked_and_deleted_files(workspace):
    project = Project(workspace)
    before = project.snapshot()
    (workspace / "new-file.txt").write_text("new")
    assert before != project.snapshot()
    (workspace / "new-file.txt").unlink()
    assert before == project.snapshot()


def test_schema_cli_export_roundtrip(tmp_path, capsys):
    output = tmp_path / "schema.json"
    assert main(["schema", "profile", "--output", str(output)]) == 0
    assert json.loads(capsys.readouterr().out)["path"] == str(output)
    assert json.loads(output.read_text()) == Profile.model_json_schema()


def test_shipped_example_profile_and_task_validate():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    profile = Profile.model_validate(load_yaml(root / "examples/project.yaml"))
    task = TaskSpec.model_validate(load_yaml(root / "examples/task.yaml"))
    assert set(task.validators) <= profile.validators.keys()


@pytest.mark.parametrize("implementation,review,cross", [("claude", "codex", True), ("codex", "claude", True), ("codex", "codex", False)])
def test_migration_role_recipes_are_configurable(workspace, implementation, review, cross):
    data = Project(workspace).load()[0].model_dump()
    data["providers"] = {"claude": {"adapter": "claude"}, "codex": {"adapter": "codex"}}
    data["roles"] = {"planner": {"provider": "claude"}, "implementer": {"provider": implementation}, "reviewer": {"provider": review}}
    data["policy"]["cross_provider_review"] = cross
    profile = Profile.model_validate(data)
    assert profile.roles["implementer"].provider == implementation
    assert profile.roles["reviewer"].provider == review
