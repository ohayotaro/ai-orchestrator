from __future__ import annotations

import yaml

from ai_orchestrator.engine import Engine
from ai_orchestrator.runtime_options import RuntimeOptionsDescriptor, RuntimeValueDescriptor
from conftest import FakeAdapter, spec


class ExecutionPolicyAdapter(FakeAdapter):
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
        )


def configure_classes(workspace):
    path = workspace / ".orchestrator/config.yaml"
    profile = yaml.safe_load(path.read_text())
    profile["providers"]["engineering"]["model"] = "fast-model"
    profile["providers"]["engineering"]["effort"] = "low"
    profile["execution_classes"] = {
        "deep": {
            "providers": {
                "engineering": {"model": "deep-model", "effort": "xhigh"},
            },
        },
        "balanced": {
            "default": {"effort": "medium"},
        },
    }
    path.write_text(yaml.safe_dump(profile))


def test_named_execution_class_resolves_after_provider_and_is_frozen(workspace):
    configure_classes(workspace)
    reasoning = ExecutionPolicyAdapter("anthropic")
    engineering = ExecutionPolicyAdapter("openai")
    engine = Engine(workspace, {"claude": reasoning, "codex": engineering})
    try:
        engine.trust("test-operator")
        state = engine.create(
            spec("named-deep"),
            execution_classes={"implementer": "deep"},
        )
        state = engine.run(state.spec.id)
        assert state.schema_version == 7
        assert state.execution_classes == {"implementer": "deep"}
        implementer = next(
            item for item in state.workflow_nodes.values()
            if item.provider_resolution
            and item.provider_resolution["provider"] == "engineering"
        )
        variant = implementer.model_variant_resolution
        assert variant["execution_class"] == "deep"
        assert variant["model"] == "deep-model"
        assert variant["effort"] == "xhigh"
        assert variant["sources"]["model"] == "execution_class"
        assert variant["sources"]["effort"] == "execution_class"

        engine.approve(state.spec.id, engine.approval_scope(state), "test-operator")
        state = engine.run(state.spec.id)
        assert engineering.requests
        assert engineering.requests[0].config.model == "deep-model"
        assert engineering.requests[0].config.effort == "xhigh"
    finally:
        engine.close()


def test_explicit_runtime_override_wins_per_dimension_over_execution_class(workspace):
    configure_classes(workspace)
    reasoning = ExecutionPolicyAdapter("anthropic")
    engineering = ExecutionPolicyAdapter("openai")
    engine = Engine(workspace, {"claude": reasoning, "codex": engineering})
    try:
        engine.trust("test-operator")
        state = engine.create(
            spec("named-plus-raw"),
            execution_classes={"implementer": "deep"},
            runtime_overrides={"implementer": {"effort": "low"}},
        )
        state = engine.run(state.spec.id)
        implementer = next(
            item for item in state.workflow_nodes.values()
            if item.provider_resolution
            and item.provider_resolution["provider"] == "engineering"
        )
        variant = implementer.model_variant_resolution
        assert variant["model"] == "deep-model"
        assert variant["effort"] == "low"
        assert variant["sources"]["model"] == "execution_class"
        assert variant["sources"]["effort"] == "explicit_override"
    finally:
        engine.close()


def test_named_execution_class_without_selected_provider_mapping_fails_closed(workspace):
    path = workspace / ".orchestrator/config.yaml"
    profile = yaml.safe_load(path.read_text())
    profile["execution_classes"] = {
        "reasoning-only": {
            "providers": {
                "reasoning": {"effort": "high"},
            },
        },
    }
    path.write_text(yaml.safe_dump(profile))

    engine = Engine(
        workspace,
        {
            "claude": ExecutionPolicyAdapter("anthropic"),
            "codex": ExecutionPolicyAdapter("openai"),
        },
    )
    try:
        engine.trust("test-operator")
        state = engine.create(
            spec("named-missing-provider"),
            execution_classes={"implementer": "reasoning-only"},
        )
        state = engine.run(state.spec.id)
        assert state.status == "blocked"
        assert "has no mapping for provider engineering" in state.error
    finally:
        engine.close()
