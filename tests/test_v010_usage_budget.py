from __future__ import annotations

import json

import pytest
import yaml

from ai_orchestrator.engine import Engine
from ai_orchestrator.human_gates import HumanGateBroker, ProfileChangeRequest, compact_gate_summary
from ai_orchestrator.models import BudgetPolicy, OrchestratorError, Policy, PricingRule
from ai_orchestrator.providers import AgyAdapter, ClaudeAdapter, CodexAdapter
from ai_orchestrator.service import ApplicationService
from ai_orchestrator.usage import (
    UsageDescriptor,
    aggregate_usage,
    append_usage,
    assert_dispatch_allowed,
    assert_post_call_budget,
    budget_snapshot,
    empty_usage,
    normalize_usage,
    usage_with_call_coverage,
)
from conftest import FakeAdapter, spec


class UsageAdapter(FakeAdapter):
    def __init__(self, family: str, *, report_cost: bool = True):
        super().__init__(family)
        self.report_cost = report_cost

    def describe_usage(self, config, workspace):
        return UsageDescriptor(
            input_tokens="reported",
            output_tokens="reported",
            reasoning_tokens="unsupported",
            cache_read_tokens="reported",
            cache_write_tokens="reported",
            total_tokens="unsupported",
            provider_elapsed_seconds="reported",
            provider_cost="reported" if self.report_cost else "unsupported",
            limitations=["offline deterministic usage fixture"],
        )

    def execute(self, request):
        if request.usage_sink is not None:
            payload = {
                "tokens": {
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "cache_read_tokens": 2,
                    "cache_write_tokens": 1,
                },
                "provider_elapsed_seconds": 0.025,
            }
            if self.report_cost:
                payload["cost"] = {"amount": "0.001", "currency": "USD"}
            request.usage_sink(payload)
        return super().execute(request)


def _record(*, raw, descriptor, pricing=None, provider="engineering", model="m1", call=1):
    return normalize_usage(
        owner_id="task-usage",
        call_index=call,
        attempt=1,
        role="implementer",
        node="implement",
        phase="execute",
        provider=provider,
        adapter_name="fixture",
        family="test",
        model=model,
        effort=None,
        outcome="completed",
        elapsed_seconds=0.2,
        raw=raw,
        descriptor=descriptor,
        pricing=pricing or [],
    )


def test_zero_call_empty_usage_remains_known_zero():
    usage = usage_with_call_coverage(empty_usage(), expected_calls=0)
    assert usage["summary"]["input_tokens"] == {
        "status": "known", "value": 0, "known_subtotal": 0
    }
    assert "call_coverage" not in usage["summary"]


def test_legacy_calls_without_usage_records_are_unknown_not_zero():
    usage = usage_with_call_coverage(empty_usage(), expected_calls=3)
    summary = usage["summary"]
    assert summary["calls"] == 0
    assert summary["call_coverage"] == {
        "status": "incomplete",
        "expected_calls": 3,
        "recorded_calls": 0,
        "missing_calls": 3,
    }
    assert summary["input_tokens"] == {
        "status": "unknown", "value": None, "known_subtotal": 0
    }
    assert summary["provider_elapsed_seconds"] == {
        "status": "unknown", "value": None, "known_subtotal": 0.0
    }
    assert summary["cost"] == {
        "status": "unknown",
        "amount": None,
        "currency": None,
        "known_subtotal": "0.00000000",
    }


def test_partial_usage_coverage_preserves_known_subtotals_but_total_is_unknown():
    descriptor = UsageDescriptor(input_tokens="reported", provider_elapsed_seconds="reported")
    recorded = append_usage(
        empty_usage(),
        _record(
            raw={"tokens": {"input_tokens": 7}, "provider_elapsed_seconds": 0.25},
            descriptor=descriptor,
        ),
    )
    usage = usage_with_call_coverage(recorded, expected_calls=2)
    summary = usage["summary"]
    assert summary["input_tokens"] == {
        "status": "unknown", "value": None, "known_subtotal": 7
    }
    assert summary["provider_elapsed_seconds"] == {
        "status": "unknown", "value": None, "known_subtotal": 0.25
    }
    assert summary["call_coverage"]["missing_calls"] == 1


def test_engine_legacy_state_calls_without_usage_artifact_are_unknown(engine):
    controller, _reasoning, _engineering = engine
    state = controller.create(spec("legacy-usage-view", risk="T0"))
    state.calls = 3
    controller.store.save(state, "test.legacy_calls_without_usage")
    reloaded = controller.store.get(state.spec.id)
    usage = controller.usage_evidence(reloaded)
    assert usage["summary"]["input_tokens"]["status"] == "unknown"
    assert usage["summary"]["cost"]["status"] == "unknown"
    assert usage["summary"]["call_coverage"]["expected_calls"] == 3


def test_missing_usage_remains_unknown_or_unsupported_not_zero():
    descriptor = UsageDescriptor(
        input_tokens="reported",
        output_tokens="unsupported",
        provider_elapsed_seconds="reported",
    )
    record = _record(raw={}, descriptor=descriptor)

    assert record.input_tokens.status == "unknown"
    assert record.input_tokens.value is None
    assert record.output_tokens.status == "unsupported"
    assert record.output_tokens.value is None
    assert record.provider_elapsed_seconds.status == "unknown"

    summary = aggregate_usage([record])
    assert summary["input_tokens"] == {
        "status": "unknown", "value": None, "known_subtotal": 0
    }
    assert summary["output_tokens"] == {
        "status": "unsupported", "value": None, "known_subtotal": 0
    }


def test_exact_pricing_produces_controller_computed_cost_with_provenance():
    descriptor = UsageDescriptor(input_tokens="reported", output_tokens="reported")
    rule = PricingRule(
        provider="engineering",
        model="m1",
        source="operator-fixture",
        version="2026-10-03",
        effective_from="2026-10-03T00:00:00Z",
        input_per_million="1.25",
        output_per_million="5",
    )
    record = _record(
        raw={"tokens": {"input_tokens": 1_000_000, "output_tokens": 2_000_000}},
        descriptor=descriptor,
        pricing=[rule],
    )
    assert record.cost.status == "known"
    assert record.cost.source == "controller_computed"
    assert record.cost.amount == "11.25000000"
    assert record.cost.currency == "USD"
    assert record.cost.pricing == {
        "provider": "engineering",
        "model": "m1",
        "source": "operator-fixture",
        "version": "2026-10-03",
        "effective_from": "2026-10-03T00:00:00Z",
    }


def test_provider_reported_cost_wins_over_controller_pricing():
    descriptor = UsageDescriptor(
        input_tokens="reported", output_tokens="reported", provider_cost="reported"
    )
    rule = PricingRule(
        provider="engineering",
        model="m1",
        source="operator-fixture",
        version="v1",
        effective_from="2026-10-03",
        input_per_million="100",
    )
    record = _record(
        raw={
            "tokens": {"input_tokens": 1_000_000, "output_tokens": 1},
            "cost": {"amount": "0.75", "currency": "USD"},
        },
        descriptor=descriptor,
        pricing=[rule],
    )
    assert record.cost.source == "provider_reported"
    assert record.cost.amount == "0.75000000"
    assert record.cost.pricing is None


def test_aggregation_is_deterministic_across_node_attempt_provider_and_model():
    descriptor = UsageDescriptor(input_tokens="reported", output_tokens="reported")
    first = _record(
        raw={"tokens": {"input_tokens": 2, "output_tokens": 3}},
        descriptor=descriptor,
        call=1,
    )
    second = _record(
        raw={"tokens": {"input_tokens": 5, "output_tokens": 7}},
        descriptor=descriptor,
        call=2,
    )
    evidence = append_usage(append_usage(empty_usage(), first), second)
    summary = evidence["summary"]
    assert summary["calls"] == 2
    assert summary["input_tokens"]["value"] == 7
    assert summary["output_tokens"]["value"] == 10
    assert summary["by_node"][0]["key"] == "implement"
    assert summary["by_attempt"][0]["key"] == "1"
    assert summary["by_provider"][0]["key"] == "engineering"
    assert summary["by_model"][0]["key"] == "engineering/m1"


def test_strict_budget_fails_before_dispatch_for_unsupported_metric():
    policy = Policy(
        budget=BudgetPolicy(max_reasoning_tokens=100, unknown_usage="fail_closed")
    )
    with pytest.raises(OrchestratorError, match="telemetry is unsupported"):
        assert_dispatch_allowed(
            policy=policy,
            pricing=[],
            evidence=empty_usage(),
            calls=0,
            elapsed_seconds=0.0,
            provider="engineering",
            model="m1",
            descriptor=UsageDescriptor(reasoning_tokens="unsupported"),
        )


def test_exact_budget_exhaustion_blocks_next_dispatch_without_rejecting_completed_call():
    policy = Policy(budget=BudgetPolicy(max_input_tokens=10))
    descriptor = UsageDescriptor(input_tokens="reported")
    evidence = append_usage(
        empty_usage(),
        _record(raw={"tokens": {"input_tokens": 10}}, descriptor=descriptor),
    )
    status = assert_post_call_budget(policy, evidence, calls=1, elapsed_seconds=0.2)
    assert status["can_dispatch"] is False
    assert status["blockers"][0]["dimension"] == "input_tokens"
    with pytest.raises(OrchestratorError, match="budget blocks provider dispatch"):
        assert_dispatch_allowed(
            policy=policy,
            pricing=[],
            evidence=evidence,
            calls=1,
            elapsed_seconds=0.2,
            provider="engineering",
            model="m1",
            descriptor=descriptor,
        )


def test_over_budget_call_is_recorded_then_fails_before_next_effect():
    policy = Policy(budget=BudgetPolicy(max_input_tokens=9))
    descriptor = UsageDescriptor(input_tokens="reported")
    evidence = append_usage(
        empty_usage(),
        _record(raw={"tokens": {"input_tokens": 10}}, descriptor=descriptor),
    )
    with pytest.raises(OrchestratorError, match="budget exceeded"):
        assert_post_call_budget(policy, evidence, calls=1, elapsed_seconds=0.2)


def test_workflow_records_usage_and_budget_artifacts(workspace):
    reasoning = UsageAdapter("anthropic")
    engineering = UsageAdapter("openai")
    engine = Engine(workspace, {"claude": reasoning, "codex": engineering})
    try:
        engine.trust("operator")
        state = engine.create(spec("usage-flow"))
        assert state.schema_version == 8

        state = engine.run(state.spec.id)
        assert state.status == "awaiting_approval", state.error
        assert engine.usage_evidence(state)["summary"]["calls"] == 1

        engine.approve(state.spec.id, engine.approval_scope(state), "operator")
        state = engine.run(state.spec.id)
        assert state.status == "awaiting_acceptance", state.error

        usage = engine.usage_evidence(state)
        assert usage["summary"]["calls"] == 3
        assert usage["summary"]["input_tokens"]["value"] == 30
        assert usage["summary"]["output_tokens"]["value"] == 15
        assert usage["summary"]["cost"]["amount"] == "0.00300000"
        assert {item["role"] for item in usage["records"]} == {
            "planner", "implementer", "reviewer"
        }
        assert all(item["controller_elapsed_seconds"]["status"] == "known" for item in usage["records"])
        assert all(item["provider_elapsed_seconds"]["status"] == "known" for item in usage["records"])
        assert engine.store.latest(state, "budget")["schema_version"] == 1
        assert {"usage", "budget"} <= {artifact.kind for artifact in state.artifacts}
    finally:
        engine.close()


def test_configured_call_budget_never_switches_provider_or_model(workspace):
    config = workspace / ".orchestrator/config.yaml"
    profile = yaml.safe_load(config.read_text())
    profile["policy"]["budget"] = {"max_provider_calls": 1}
    config.write_text(yaml.safe_dump(profile))

    reasoning = UsageAdapter("anthropic")
    engineering = UsageAdapter("openai")
    engine = Engine(workspace, {"claude": reasoning, "codex": engineering})
    try:
        engine.trust("operator")
        state = engine.create(spec("call-budget"))
        state = engine.run(state.spec.id)
        assert state.status == "awaiting_approval"
        assert len(reasoning.requests) == 1
        assert not engineering.requests
        assert engine.budget_status(state)["can_dispatch"] is False

        engine.approve(state.spec.id, engine.approval_scope(state), "operator")
        state = engine.run(state.spec.id)
        assert state.status == "failed"
        assert "budget blocks provider dispatch" in state.error
        assert len(reasoning.requests) == 1
        assert not engineering.requests
    finally:
        engine.close()


def test_human_gate_execution_preview_binds_usage_and_budget(workspace):
    reasoning = UsageAdapter("anthropic")
    engineering = UsageAdapter("openai")
    engine = Engine(workspace, {"claude": reasoning, "codex": engineering})
    try:
        engine.trust("operator")
        state = engine.create(spec("gate-budget"))
        state = engine.run(state.spec.id)
        assert state.status == "awaiting_approval"
    finally:
        engine.close()

    broker = HumanGateBroker(
        ApplicationService(workspace), "usage-session", {"name": "test", "version": "1"}
    )
    try:
        with broker.service.engine() as current:
            captured = broker.capture(current, "execution", "gate-budget")
        assert captured["preview"]["usage_summary"]["summary"]["calls"] == 1
        assert captured["preview"]["budget"]["consumed"]["provider_calls"] == 1
        gate = broker.prepare("execution", "gate-budget", "usage-gate-request")
        summary = compact_gate_summary(gate)
        assert "Budget:" in summary
        assert "calls=1/" in summary
    finally:
        broker.close()


def test_service_task_view_and_inspection_expose_usage_budget(workspace):
    engine = Engine(
        workspace,
        {"claude": UsageAdapter("anthropic"), "codex": UsageAdapter("openai")},
    )
    try:
        engine.trust("operator")
        engine.create(spec("service-usage"))
    finally:
        engine.close()

    # ApplicationService uses installed adapters for project inspection, but it
    # does not execute or authenticate them while describing usage support.
    service = ApplicationService(workspace)
    inspected = service.invoke("inspect_project", {})
    assert inspected["usage_observability"]["schema_version"] == 1
    assert inspected["budget_policy"]["schema_version"] == 1
    view = service.invoke("get_task", {"task_id": "service-usage"})
    assert view["usage"]["summary"]["calls"] == 0
    assert view["budget"]["fallback"] == "none"


def test_provider_usage_parsers_accept_only_explicit_structured_counters():
    codex = CodexAdapter._usage_from_jsonl("\n".join([
        json.dumps({"type": "item.completed", "usage": {"input_tokens": 999}}),
        json.dumps({
            "type": "turn.completed",
            "usage": {
                "input_tokens": 11,
                "cached_input_tokens": 3,
                "cache_write_input_tokens": 2,
                "output_tokens": 7,
                "reasoning_output_tokens": 5,
            },
        }),
    ]))
    assert codex["tokens"] == {
        "input_tokens": 11,
        "cache_read_tokens": 3,
        "cache_write_tokens": 2,
        "output_tokens": 7,
        "reasoning_tokens": 5,
    }

    claude = ClaudeAdapter._usage_from_envelope({
        "usage": {
            "input_tokens": 20,
            "output_tokens": 4,
            "cache_read_input_tokens": 6,
            "cache_creation_input_tokens": 8,
        },
        "duration_api_ms": 1250,
        "total_cost_usd": 0.02,
        "result": "PRIVATE_TEXT_MUST_NOT_BE_ACCOUNTING",
    })
    assert claude == {
        "tokens": {
            "input_tokens": 20,
            "output_tokens": 4,
            "cache_read_tokens": 6,
            "cache_write_tokens": 8,
        },
        "provider_elapsed_seconds": 1.25,
        "cost": {"amount": "0.02", "currency": "USD"},
    }

    agy = AgyAdapter._usage_from_envelope({
        "status": "SUCCESS",
        "response": "PRIVATE_TEXT_MUST_NOT_BE_ACCOUNTING",
    })
    assert agy == {}


def test_budget_snapshot_marks_unknown_cost_unprovable_without_zero_fill():
    policy = Policy(budget=BudgetPolicy(max_cost="1.00", currency="USD"))
    descriptor = UsageDescriptor(input_tokens="reported")
    evidence = append_usage(
        empty_usage(),
        _record(raw={"tokens": {"input_tokens": 1}}, descriptor=descriptor),
    )
    status = budget_snapshot(policy, evidence, calls=1, elapsed_seconds=0.1)
    assert status["consumed"]["cost"]["status"] == "unsupported"
    assert status["consumed"]["cost"]["amount"] is None
    assert status["blockers"] == [{
        "dimension": "cost",
        "status": "unprovable",
        "limit": "1.00",
        "observed": None,
        "currency": "USD",
    }]


def test_provider_adapter_change_invalidates_stale_pricing_authority(workspace):
    config = workspace / ".orchestrator/config.yaml"
    profile = yaml.safe_load(config.read_text())
    profile["providers"]["engineering"]["model"] = "vendor-model"
    profile["pricing"] = [{
        "schema_version": 1,
        "provider": "engineering",
        "model": "vendor-model",
        "currency": "USD",
        "source": "test fixture",
        "version": "v1",
        "effective_from": "2026-10-03",
        "input_per_million": "1.0",
    }]
    config.write_text(yaml.safe_dump(profile, sort_keys=False))

    engine = Engine(workspace)
    try:
        engine.trust("operator")
    finally:
        engine.close()

    service = ApplicationService(workspace)
    preview = service.invoke(
        "preview_provider_change",
        {"provider": "engineering", "adapter": "agy"},
    )
    assert preview["change"]["reset_pricing_rules"] == 1

    broker = HumanGateBroker(
        service, "pricing-reset-session", {"name": "test", "version": "1"}
    )
    try:
        gate = broker.prepare_provider_change(
            ProfileChangeRequest(
                provider="engineering",
                adapter="agy",
                request_id="pricing-reset",
            )
        )
        assert "Reset pricing rules: 1" in broker.form(gate)["message"]
        result = broker.resolve(
            gate, {"action": "accept", "content": {"decision": "yes"}}
        )
        assert result["gate_status"] == "applied"
    finally:
        broker.close()

    updated = yaml.safe_load(config.read_text())
    assert updated["providers"]["engineering"]["adapter"] == "agy"
    assert "model" not in updated["providers"]["engineering"]
    assert updated.get("pricing", []) == []
