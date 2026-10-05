from __future__ import annotations

import yaml
import pytest

from ai_orchestrator.capabilities import ProviderResolution
from ai_orchestrator.engine import Engine
from ai_orchestrator.models import OrchestratorError, ProviderConfig
from ai_orchestrator.service import ApplicationService
from ai_orchestrator.runtime_options import (
    ModelVariantResolver,
    RuntimeOptionsDescriptor,
    RuntimeOverride,
    RuntimeValueDescriptor,
)
from conftest import FakeAdapter, spec


class RuntimeAdapter(FakeAdapter):
    def __init__(self, family: str):
        super().__init__(family)
        self.revision = "r1"

    def describe_runtime_options(self, config, workspace):
        return RuntimeOptionsDescriptor(
            model=RuntimeValueDescriptor(
                mode="enumerated",
                values=["fast-model", "deep-model"],
                default="fast-model",
                complete=True,
            ),
            effort=RuntimeValueDescriptor(
                mode="enumerated",
                values=["low", "medium", "high", "xhigh"],
                default="medium",
                complete=True,
            ),
            options={
                "adapter_mode": RuntimeValueDescriptor(mode="passthrough"),
            },
            limitations=[f"fixture-{self.revision}"],
        )


def provider_resolution(provider="engineering", adapter="codex"):
    return ProviderResolution(
        role="implementer",
        provider=provider,
        adapter=adapter,
        family="openai",
        source="fixed",
        required_capabilities=["code_edit"],
        offered_capabilities=["code_edit"],
        candidates_considered=[provider],
        adapter_api_version=2,
    )


def test_model_variant_precedence_and_fail_closed(tmp_path):
    resolver = ModelVariantResolver()
    adapter = RuntimeAdapter("openai")
    config = ProviderConfig(adapter="codex", model="deep-model", effort="high")

    profile = resolver.resolve(provider_resolution(), config, adapter, tmp_path)
    assert profile.model == "deep-model"
    assert profile.effort == "high"
    assert profile.sources == {"model": "trusted_profile", "effort": "trusted_profile"}
    assert profile.fallback == "none"

    override = resolver.resolve(
        provider_resolution(),
        config,
        adapter,
        tmp_path,
        override=RuntimeOverride(model="fast-model", effort="xhigh"),
    )
    assert override.model == "fast-model"
    assert override.effort == "xhigh"
    assert override.sources == {"model": "explicit_override", "effort": "explicit_override"}

    defaulted = resolver.resolve(
        provider_resolution(),
        ProviderConfig(adapter="codex"),
        adapter,
        tmp_path,
    )
    assert defaulted.model == "fast-model"
    assert defaulted.effort == "medium"
    assert defaulted.sources == {"model": "adapter_default", "effort": "adapter_default"}

    with pytest.raises(OrchestratorError, match="unsupported effort value"):
        resolver.resolve(
            provider_resolution(),
            config,
            adapter,
            tmp_path,
            override=RuntimeOverride(effort="ultra"),
        )


def test_passthrough_records_limitation_without_fabricating_catalog(tmp_path):
    class PassthroughAdapter(FakeAdapter):
        def describe_runtime_options(self, config, workspace):
            limitation = "catalog unavailable; provider validates the provider-local value"
            return RuntimeOptionsDescriptor(
                model=RuntimeValueDescriptor(mode="passthrough", limitations=[limitation]),
                effort=RuntimeValueDescriptor(mode="passthrough", limitations=[limitation]),
                limitations=[limitation],
            )

    resolver = ModelVariantResolver()
    result = resolver.resolve(
        provider_resolution(),
        ProviderConfig(adapter="codex", model="future/provider-model", effort="xhigh"),
        PassthroughAdapter("openai"),
        tmp_path,
    )
    assert result.model == "future/provider-model"
    assert result.effort == "xhigh"
    assert result.limitations == ["catalog unavailable; provider validates the provider-local value"]


def test_workflow_freezes_variant_provenance_and_executes_resolved_config(workspace):
    config_path = workspace / ".orchestrator/config.yaml"
    profile = yaml.safe_load(config_path.read_text())
    profile["providers"]["reasoning"]["model"] = "deep-model"
    profile["providers"]["reasoning"]["effort"] = "high"
    profile["providers"]["engineering"]["model"] = "fast-model"
    profile["providers"]["engineering"]["effort"] = "xhigh"
    config_path.write_text(yaml.safe_dump(profile))

    reasoning = RuntimeAdapter("anthropic")
    engineering = RuntimeAdapter("openai")
    engine = Engine(workspace, {"claude": reasoning, "codex": engineering})
    try:
        engine.trust("test-operator")
        state = engine.create(spec("runtime-options"))
        state = engine.run(state.spec.id)
        assert state.schema_version == 9
        assert state.status == "awaiting_approval"

        agent_nodes = [
            item for item in state.workflow_nodes.values()
            if item.provider_resolution is not None
        ]
        assert agent_nodes
        assert all(item.model_variant_resolution is not None for item in agent_nodes)

        implementer = next(
            item for item in agent_nodes
            if item.provider_resolution["provider"] == "engineering"
        )
        assert implementer.model_variant_resolution["model"] == "fast-model"
        assert implementer.model_variant_resolution["effort"] == "xhigh"
        assert implementer.model_variant_resolution["sources"] == {
            "model": "trusted_profile",
            "effort": "trusted_profile",
        }
        assert state.model_variant_resolutions["implementer"]["model"] == "fast-model"

        assert reasoning.requests
        assert reasoning.requests[0].config.model == "deep-model"
        assert reasoning.requests[0].config.effort == "high"

        scope = engine.approval_scope(state)
        engine.approve(state.spec.id, scope, "test-operator")
        state = engine.run(state.spec.id)
        assert engineering.requests
        assert engineering.requests[0].config.model == "fast-model"
        assert engineering.requests[0].config.effort == "xhigh"
    finally:
        engine.close()



def test_task_runtime_override_beats_profile_and_is_frozen_per_node(workspace):
    config_path = workspace / ".orchestrator/config.yaml"
    profile = yaml.safe_load(config_path.read_text())
    profile["providers"]["reasoning"]["model"] = "fast-model"
    profile["providers"]["reasoning"]["effort"] = "low"
    profile["providers"]["engineering"]["model"] = "fast-model"
    profile["providers"]["engineering"]["effort"] = "low"
    config_path.write_text(yaml.safe_dump(profile))

    reasoning = RuntimeAdapter("anthropic")
    engineering = RuntimeAdapter("openai")
    engine = Engine(workspace, {"claude": reasoning, "codex": engineering})
    try:
        engine.trust("test-operator")
        state = engine.create(
            spec("runtime-override"),
            runtime_overrides={
                "implementer": {
                    "model": "deep-model",
                    "effort": "xhigh",
                    "options": {"adapter_mode": "strict"},
                },
            },
        )
        state = engine.run(state.spec.id)
        implementer = next(
            item for item in state.workflow_nodes.values()
            if item.provider_resolution
            and item.provider_resolution["provider"] == "engineering"
        )
        assert implementer.model_variant_resolution["model"] == "deep-model"
        assert implementer.model_variant_resolution["effort"] == "xhigh"
        assert implementer.model_variant_resolution["sources"] == {
            "model": "explicit_override",
            "effort": "explicit_override",
            "option:adapter_mode": "explicit_override",
        }
        assert state.runtime_overrides["implementer"]["model"] == "deep-model"

        engine.approve(state.spec.id, engine.approval_scope(state), "test-operator")
        state = engine.run(state.spec.id)
        assert engineering.requests
        assert engineering.requests[0].config.model == "deep-model"
        assert engineering.requests[0].config.effort == "xhigh"
        assert engineering.requests[0].runtime_options == {"adapter_mode": "strict"}
    finally:
        engine.close()


def test_task_runtime_override_rejects_unknown_workflow_target(workspace):
    engine = Engine(
        workspace,
        {"claude": RuntimeAdapter("anthropic"), "codex": RuntimeAdapter("openai")},
    )
    try:
        engine.trust("test-operator")
        with pytest.raises(
            OrchestratorError,
            match="runtime override targets are not present in the selected workflow",
        ):
            engine.create(
                spec("runtime-unknown-target"),
                runtime_overrides={"not-a-node": {"effort": "high"}},
            )
    finally:
        engine.close()

def test_frozen_runtime_metadata_drift_fails_closed(workspace):
    config_path = workspace / ".orchestrator/config.yaml"
    profile = yaml.safe_load(config_path.read_text())
    profile["providers"]["reasoning"]["model"] = "deep-model"
    profile["providers"]["engineering"]["model"] = "fast-model"
    config_path.write_text(yaml.safe_dump(profile))

    reasoning = RuntimeAdapter("anthropic")
    engineering = RuntimeAdapter("openai")
    engine = Engine(workspace, {"claude": reasoning, "codex": engineering})
    try:
        engine.trust("test-operator")
        state = engine.create(spec("runtime-drift"))
        state = engine.run(state.spec.id)
        engine.approve(state.spec.id, engine.approval_scope(state), "test-operator")

        engineering.revision = "r2"
        state = engine.run(state.spec.id)
        assert state.status == "blocked"
        assert "model/effort/runtime-option resolution changed since task binding" in state.error
    finally:
        engine.close()


def test_same_family_distinct_models_satisfy_independent_review(workspace):
    config_path = workspace / ".orchestrator/config.yaml"
    profile = yaml.safe_load(config_path.read_text())
    profile["providers"]["reasoning"]["adapter"] = "claude"
    profile["providers"]["engineering"]["adapter"] = "claude"
    profile["providers"]["reasoning"]["model"] = "deep-model"
    profile["providers"]["engineering"]["model"] = "fast-model"
    config_path.write_text(yaml.safe_dump(profile))

    claude = RuntimeAdapter("anthropic")
    engine = Engine(workspace, {"claude": claude})
    try:
        engine.trust("test-operator")
        state = engine.create(spec("same-family-model-review"))
        state = engine.run(state.spec.id)
        assert state.status == "awaiting_approval", state.error
        implementer = state.model_variant_resolutions["implementer"]
        reviewer = state.model_variant_resolutions["reviewer"]
        assert implementer["model"] == "fast-model"
        assert reviewer["model"] == "deep-model"
        assert state.provider_resolutions["implementer"]["family"] == "anthropic"
        assert state.provider_resolutions["reviewer"]["family"] == "anthropic"
    finally:
        engine.close()


def test_same_family_same_model_fails_independent_review(workspace):
    config_path = workspace / ".orchestrator/config.yaml"
    profile = yaml.safe_load(config_path.read_text())
    profile["providers"]["reasoning"]["adapter"] = "claude"
    profile["providers"]["engineering"]["adapter"] = "claude"
    profile["providers"]["reasoning"]["model"] = "deep-model"
    profile["providers"]["engineering"]["model"] = "deep-model"
    config_path.write_text(yaml.safe_dump(profile))

    claude = RuntimeAdapter("anthropic")
    engine = Engine(workspace, {"claude": claude})
    try:
        engine.trust("test-operator")
        state = engine.create(spec("same-family-same-model"))
        state = engine.run(state.spec.id)
        assert state.status == "blocked"
        assert "different provider family or explicit distinct model IDs" in state.error
    finally:
        engine.close()


def test_read_only_workflow_nodes_do_not_see_orchestrator_control_dir(workspace):
    class ObservingAdapter(RuntimeAdapter):
        def __init__(self, family):
            super().__init__(family)
            self.control_visibility = []

        def execute(self, request):
            if request.phase in ("plan", "review"):
                self.control_visibility.append(
                    (
                        request.phase,
                        (request.workspace / ".orchestrator").exists(),
                        request.workspace.resolve().is_relative_to(workspace.resolve()),
                    )
                )
            return super().execute(request)

    reasoning = ObservingAdapter("anthropic")
    engineering = RuntimeAdapter("openai")
    engine = Engine(workspace, {"claude": reasoning, "codex": engineering})
    try:
        engine.trust("test-operator")
        state = engine.create(spec("readonly-control-isolation"))
        state = engine.run(state.spec.id)
        assert state.status == "awaiting_approval", state.error
        assert ("plan", False, False) in reasoning.control_visibility

        engine.approve(state.spec.id, engine.approval_scope(state), "test-operator")
        state = engine.run(state.spec.id)
        assert state.status == "awaiting_acceptance", state.error
        assert ("review", False, False) in reasoning.control_visibility

        provenance = engine.store.latest(state, "provider_provenance")
        records = provenance["records"]
        plan = next(item for item in records if item["role"] == "planner")
        implement = next(item for item in records if item["role"] == "implementer")
        review = next(item for item in records if item["role"] == "reviewer")

        for item in (plan, review):
            assert item["workspace"]["mode"] == "read_only_disposable"
            assert item["workspace"]["outside_project"] is True
            assert item["workspace"]["control_dir_materialized"] is False
            assert item["workspace"]["unchanged_verified"] is True
            assert item["workspace"]["cleaned"] is True

        assert implement["model"] == "fast-model"
        assert implement["effort"] == "medium"
        assert implement["runtime_options"] == {}
        assert implement["workspace"]["mode"] == "shared_project"
        assert "provider receipt is not independently attested" in implement["evidence_boundary"]
    finally:
        engine.close()

    official = ApplicationService(workspace).invoke(
        "get_artifact",
        {"task_id": "readonly-control-isolation", "kind": "provider_provenance"},
    )
    assert official["content"]["schema_version"] == 1
    assert {item["role"] for item in official["content"]["records"]} == {
        "planner", "implementer", "reviewer"
    }


def test_same_provider_slot_can_use_distinct_models_per_role(workspace):
    config_path = workspace / ".orchestrator/config.yaml"
    profile = yaml.safe_load(config_path.read_text())
    profile["providers"]["reasoning"]["adapter"] = "claude"
    profile["roles"]["planner"]["provider"] = "reasoning"
    profile["roles"]["implementer"]["provider"] = "reasoning"
    profile["roles"]["reviewer"]["provider"] = "reasoning"
    config_path.write_text(yaml.safe_dump(profile))

    claude = RuntimeAdapter("anthropic")
    engine = Engine(workspace, {"claude": claude})
    try:
        engine.trust("test-operator")
        state = engine.create(
            spec("same-slot-distinct-models"),
            runtime_overrides={
                "planner": {"model": "deep-model"},
                "implementer": {"model": "fast-model"},
                "reviewer": {"model": "deep-model"},
            },
        )
        state = engine.run(state.spec.id)
        assert state.status == "awaiting_approval", state.error
        assert state.provider_resolutions["implementer"]["provider"] == "reasoning"
        assert state.provider_resolutions["reviewer"]["provider"] == "reasoning"
        assert state.model_variant_resolutions["implementer"]["model"] == "fast-model"
        assert state.model_variant_resolutions["reviewer"]["model"] == "deep-model"
    finally:
        engine.close()



def test_reports_do_not_preexclude_fixed_same_family_reviewer(workspace):
    config_path = workspace / ".orchestrator/config.yaml"
    profile = yaml.safe_load(config_path.read_text())
    profile["providers"]["reasoning"]["adapter"] = "claude"
    profile["providers"]["engineering"]["adapter"] = "claude"
    config_path.write_text(yaml.safe_dump(profile))

    claude = RuntimeAdapter("anthropic")
    engine = Engine(workspace, {"claude": claude})
    try:
        capability = engine.capability_report()
        reviewer_capability = capability["roles"]["reviewer"]
        assert "error" not in reviewer_capability
        assert reviewer_capability["family"] == "anthropic"
        assert "explicit distinct model IDs" in capability["review_independence"]

        runtime = engine.runtime_option_report()
        reviewer_runtime = runtime["roles"]["reviewer"]
        assert "error" not in reviewer_runtime
        assert reviewer_runtime["provider_resolution"]["family"] == "anthropic"
        assert "explicit distinct model IDs" in runtime["review_independence"]
    finally:
        engine.close()


def test_reports_keep_family_exclusion_for_dynamic_reviewer_routing(workspace):
    config_path = workspace / ".orchestrator/config.yaml"
    profile = yaml.safe_load(config_path.read_text())
    profile["providers"]["reasoning"]["adapter"] = "claude"
    profile["providers"]["engineering"]["adapter"] = "claude"
    profile["roles"]["reviewer"]["provider"] = None
    profile["roles"]["reviewer"]["candidates"] = ["reasoning", "engineering"]
    config_path.write_text(yaml.safe_dump(profile))

    claude = RuntimeAdapter("anthropic")
    engine = Engine(workspace, {"claude": claude})
    try:
        capability = engine.capability_report()
        assert "family anthropic excluded by policy" in capability["roles"]["reviewer"]["error"]

        runtime = engine.runtime_option_report()
        assert "family anthropic excluded by policy" in runtime["roles"]["reviewer"]["error"]
    finally:
        engine.close()
