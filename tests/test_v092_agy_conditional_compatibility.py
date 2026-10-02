from __future__ import annotations

import yaml

from ai_orchestrator.authority import provider_change_preview
from ai_orchestrator.engine import Engine
from ai_orchestrator.providers import AgyAdapter
from ai_orchestrator.service import ApplicationService


def edit_profile(workspace, mutate):
    path = workspace / ".orchestrator/config.yaml"
    data = yaml.safe_load(path.read_text())
    mutate(data)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def test_agy_readonly_roles_are_conditionally_supported_not_blocked():
    adapter = AgyAdapter()

    for role in ("supervisor", "planner", "reviewer"):
        report = adapter.role_compatibility(role)
        assert report["status"] == "conditional_native_permissions"
        assert report["requires_native_scoped_permissions"] is True
        assert report["orchestrator_attests_permissions_sufficient"] is False
        assert any("run_command" in item for item in report["limitations"])
        assert any("does not modify or attest" in item for item in report["limitations"])

    implementer = adapter.role_compatibility("implementer")
    assert implementer["status"] == "supported"


def test_engine_reports_conditional_agy_roles_without_rejecting_resolution(workspace):
    edit_profile(
        workspace,
        lambda data: data["providers"]["reasoning"].update(adapter="agy"),
    )
    engine = Engine(workspace)
    try:
        engine.trust("operator")
        compatibility = engine.provider_compatibility_report()

        for role in ("supervisor", "planner", "reviewer"):
            role_report = compatibility["roles"][role]
            assert role_report["provider"] == "reasoning"
            assert role_report["adapter"] == "agy"
            assert role_report["family"] == "google"
            assert role_report["compatibility"]["status"] == "conditional_native_permissions"

        assert compatibility["roles"]["implementer"]["compatibility"]["status"] == "supported"

        # Conditional compatibility is evidence, not a routing prohibition.
        assert engine.capability_resolver.resolve("supervisor").adapter == "agy"
        assert engine.capability_resolver.resolve("planner").adapter == "agy"
        assert engine.capability_resolver.resolve("reviewer").adapter == "agy"
    finally:
        engine.close()


def test_provider_change_preview_surfaces_agy_conditions_but_remains_ready(workspace):
    engine = Engine(workspace)
    try:
        engine.trust("operator")
        preview = provider_change_preview(engine, "reasoning", "agy")
        assert preview["ready"] is True
        compatibility = preview["resolution_after"]["role_compatibility"]
        assert compatibility["supervisor"]["status"] == "conditional_native_permissions"
        assert compatibility["planner"]["status"] == "conditional_native_permissions"
        assert compatibility["reviewer"]["status"] == "conditional_native_permissions"
        assert compatibility["implementer"]["status"] == "supported"
    finally:
        engine.close()


def test_inspect_project_exposes_provider_compatibility(workspace):
    edit_profile(
        workspace,
        lambda data: data["providers"]["reasoning"].update(adapter="agy"),
    )
    engine = Engine(workspace)
    try:
        engine.trust("operator")
    finally:
        engine.close()

    report = ApplicationService(workspace).invoke("inspect_project", {})
    compatibility = report["provider_compatibility"]
    assert compatibility["schema_version"] == 1
    assert compatibility["roles"]["supervisor"]["compatibility"]["status"] == "conditional_native_permissions"
    assert "fail closed" in compatibility["policy"]


def test_skill_forbids_prompt_rewrite_auto_retry_after_agy_denial():
    from importlib.resources import files

    text = files("ai_orchestrator").joinpath("assets/SKILL.md").read_text()
    assert "conditional_native_permissions" in text
    assert "STOP after the denial" in text
    assert 'such as "do not use shell"' in text
    assert "explicitly start a new intake" in text
    assert "not a Supervisor/Planner intake workaround" in text
