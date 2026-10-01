"""v0.5 semantic capability registry, deterministic routing and provenance."""
from __future__ import annotations

import json
import sys

import pytest
import yaml

from ai_orchestrator.cli import main
from ai_orchestrator.engine import Engine
from ai_orchestrator.models import OrchestratorError
from ai_orchestrator.project import Project
from conftest import FakeAdapter, spec


def adapters():
    return {"claude": FakeAdapter("anthropic"), "codex": FakeAdapter("openai")}


def edit_profile(workspace, mutate):
    path = workspace / ".orchestrator/config.yaml"
    data = yaml.safe_load(path.read_text())
    mutate(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def controller(workspace, registry=None):
    engine = Engine(workspace, registry or adapters())
    engine.trust("operator")
    return engine


def test_builtin_adapters_expose_v2_semantic_descriptors(workspace):
    engine = controller(workspace)
    try:
        report = engine.capability_report()
        assert report["registry"]["schema_version"] == 1
        assert "research" in report["registry"]["capabilities"]
        assert report["providers"]["engineering"]["schema_version"] == 2
        assert report["providers"]["engineering"]["adapter_api_version"] == 2
        assert "code_edit" in report["providers"]["engineering"]["capabilities"]
        assert report["roles"]["implementer"]["provider"] == "engineering"
    finally:
        engine.close()


def test_fixed_provider_override_wins_over_priority(workspace):
    edit_profile(workspace, lambda data: (
        data["providers"]["reasoning"].update(priority=1),
        data["providers"]["engineering"].update(priority=999),
    ))
    engine = controller(workspace)
    try:
        assert engine.capability_report()["roles"]["implementer"]["provider"] == "engineering"
        assert engine.capability_report()["roles"]["implementer"]["source"] == "fixed"
    finally:
        engine.close()


def test_dynamic_priority_and_cross_family_review_are_deterministic(workspace):
    def mutate(data):
        data["providers"]["engineering"]["priority"] = 10
        data["providers"]["reasoning"]["priority"] = 20
        data["roles"]["implementer"]["provider"] = None
        data["roles"]["reviewer"]["provider"] = None
    edit_profile(workspace, mutate)
    registry = adapters()
    engine = controller(workspace, registry)
    try:
        engine.create(spec())
        state = engine.run("task-1")
        assert state.status == "awaiting_approval", state.error
        assert state.schema_version == 6
        assert state.provider_resolutions["implementer"]["provider"] == "engineering"
        assert state.provider_resolutions["implementer"]["source"] == "priority"
        assert state.provider_resolutions["reviewer"]["provider"] == "reasoning"
        assert state.provider_resolutions["reviewer"]["family"] != state.provider_resolutions["implementer"]["family"]
        assert not registry["codex"].requests  # resolution happens before implementation approval
    finally:
        engine.close()


def test_role_candidates_override_global_priority(workspace):
    def mutate(data):
        data["providers"]["engineering"]["priority"] = 1
        data["providers"]["reasoning"]["priority"] = 100
        data["roles"]["implementer"]["provider"] = None
        data["roles"]["implementer"]["candidates"] = ["reasoning", "engineering"]
    edit_profile(workspace, mutate)
    engine = controller(workspace)
    try:
        resolution = engine.capability_report()["roles"]["implementer"]
        assert resolution["provider"] == "reasoning"
        assert resolution["source"] == "candidates"
        assert resolution["candidates_considered"] == ["reasoning"]
    finally:
        engine.close()


def test_task_capability_requirement_blocks_before_billable_calls(workspace):
    registry = adapters()
    engine = controller(workspace, registry)
    try:
        engine.create(spec(), capability_requirements={"implementer": ["research"]})
        state = engine.run("task-1")
        assert state.status == "blocked"
        assert "research" in state.error
        assert not registry["claude"].requests and not registry["codex"].requests
    finally:
        engine.close()


def test_provider_config_can_restrict_but_not_invent_capabilities(workspace):
    edit_profile(workspace, lambda data: data["providers"]["engineering"].update(capabilities=["planning"]))
    registry = adapters()
    engine = controller(workspace, registry)
    try:
        engine.create(spec())
        state = engine.run("task-1")
        assert state.status == "blocked"
        assert "code_edit" in state.error
        assert not registry["claude"].requests and not registry["codex"].requests
    finally:
        engine.close()

    edit_profile(workspace, lambda data: data["providers"]["engineering"].update(capabilities=["research"]))
    engine = Engine(workspace, adapters())
    engine.trust("operator")
    try:
        engine.create(spec(task_id="task-2"))
        state = engine.run("task-2")
        assert state.status == "blocked"
        assert "does not advertise" in state.error
    finally:
        engine.close()


def test_resolution_is_frozen_for_task_lifetime(workspace):
    registry = adapters()
    engine = controller(workspace, registry)
    try:
        engine.create(spec())
        state = engine.run("task-1")
        assert state.status == "awaiting_approval"
        scope = engine.approval_scope(state)
        registry["codex"].semantic_capabilities = frozenset({"planning", "review"})
        engine.approve("task-1", scope, "operator")
        state = engine.run("task-1")
        assert state.status == "blocked"
        assert "resolution changed" in state.error or "code_edit" in state.error
        assert not registry["codex"].requests
    finally:
        engine.close()


def test_resolution_provenance_is_persisted_and_auditable(workspace):
    engine = controller(workspace)
    try:
        engine.create(spec())
        state = engine.run("task-1")
        assert state.status == "awaiting_approval"
        assert set(state.capability_requirements) == {"planner", "implementer", "reviewer"}
        assert state.capability_requirements["implementer"] == ["code_edit"]
        assert state.provider_resolutions["planner"]["provider"] == "reasoning"
        events = engine.store.events("task-1")
        resolved = [event for event in events if event["kind"] == "capabilities.resolved"]
        assert len(resolved) == 1
        started = [event for event in events if event["kind"] == "call.started"]
        assert started[0]["payload"]["provider"] == "reasoning"
        assert "planning" in started[0]["payload"]["required_capabilities"]
        assert started[0]["payload"]["adapter_api_version"] == 2
    finally:
        engine.close()


class LegacyAdapter(FakeAdapter):
    api_version = 1
    semantic_capabilities = frozenset()


def old_style_profile(data):
    for provider in data["providers"].values():
        provider.pop("capabilities", None)
        provider.pop("priority", None)
    for role in data["roles"].values():
        role.pop("capabilities", None)
        role.pop("candidates", None)


def test_legacy_fixed_v1_adapter_compatibility_and_dynamic_fail_closed(workspace):
    edit_profile(workspace, old_style_profile)
    registry = {"claude": LegacyAdapter("anthropic"), "codex": LegacyAdapter("openai")}
    engine = controller(workspace, registry)
    try:
        engine.create(spec())
        assert engine.run("task-1").status == "awaiting_approval"
    finally:
        engine.close()

    def make_dynamic(data):
        old_style_profile(data)
        data["roles"]["implementer"]["provider"] = None
        data["roles"]["implementer"]["candidates"] = ["engineering"]
    edit_profile(workspace, make_dynamic)
    engine = controller(workspace, registry)
    try:
        engine.create(spec(task_id="task-dynamic"))
        state = engine.run("task-dynamic")
        assert state.status == "blocked"
        assert "semantic capabilities" in state.error
    finally:
        engine.close()


def test_empty_v05_defaults_preserve_old_profile_digest(workspace):
    path = workspace / ".orchestrator/config.yaml"
    data = yaml.safe_load(path.read_text())
    old_style_profile(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    old_digest = Project(workspace).load()[1]
    for provider in data["providers"].values():
        provider["capabilities"] = []
        provider["priority"] = 100
    for role in data["roles"].values():
        role["capabilities"] = []
        role["candidates"] = []
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    assert Project(workspace).load()[1] == old_digest


def test_cli_create_can_declare_task_capability(workspace, tmp_path, capsys):
    task = tmp_path / "task.yaml"
    task.write_text(yaml.safe_dump(spec().model_dump(), sort_keys=False))
    code = main(["--project", str(workspace), "create", "--task-file", str(task),
                 "--require", "implementer=test_authoring"])
    assert code == 0, capsys.readouterr().err
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == 6
    assert payload["capability_requirements"] == {"implementer": ["test_authoring"]}


def test_unknown_task_capability_is_rejected_before_task_creation(workspace):
    engine = controller(workspace)
    try:
        with pytest.raises(OrchestratorError, match="unknown semantic capability"):
            engine.create(spec(), capability_requirements={"implementer": ["not_a_capability"]})
        assert engine.store.db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0
    finally:
        engine.close()
