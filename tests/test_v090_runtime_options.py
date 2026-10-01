from __future__ import annotations

import yaml
import pytest

from ai_orchestrator.capabilities import ProviderResolution
from ai_orchestrator.engine import Engine
from ai_orchestrator.models import OrchestratorError, ProviderConfig
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
        assert state.schema_version == 6
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
        with pytest.raises(
            OrchestratorError,
            match="model/effort/runtime-option resolution changed since task binding",
        ):
            engine.run(state.spec.id)
    finally:
        engine.close()
