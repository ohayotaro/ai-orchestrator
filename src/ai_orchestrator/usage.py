"""Normalized provider usage, cost attribution, and budget evaluation.

v0.10 preserves provider truth: missing counters remain unknown/unsupported and
are never estimated from text length or hidden reasoning.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Literal

from pydantic import Field, model_validator

from .models import BudgetPolicy, Contract, OrchestratorError, Policy, PricingRule, identifier


MetricStatus = Literal["known", "unknown", "unsupported"]
SupportStatus = Literal["reported", "unsupported"]


class UsageDescriptor(Contract):
    schema_version: Literal[1] = 1
    input_tokens: SupportStatus = "unsupported"
    output_tokens: SupportStatus = "unsupported"
    reasoning_tokens: SupportStatus = "unsupported"
    cache_read_tokens: SupportStatus = "unsupported"
    cache_write_tokens: SupportStatus = "unsupported"
    total_tokens: SupportStatus = "unsupported"
    provider_elapsed_seconds: SupportStatus = "unsupported"
    provider_cost: SupportStatus = "unsupported"
    limitations: list[str] = Field(default_factory=list)


class UsageValue(Contract):
    status: MetricStatus
    value: int | None = Field(default=None, ge=0, strict=True)
    source: str | None = None

    @model_validator(mode="after")
    def coherent(self) -> "UsageValue":
        if self.status == "known" and self.value is None:
            raise ValueError("known usage requires a value")
        if self.status != "known" and self.value is not None:
            raise ValueError("unknown/unsupported usage must not contain a value")
        return self


class UsageSeconds(Contract):
    status: MetricStatus
    value: float | None = Field(default=None, ge=0)
    source: str | None = None

    @model_validator(mode="after")
    def coherent(self) -> "UsageSeconds":
        if self.status == "known" and self.value is None:
            raise ValueError("known duration requires a value")
        if self.status != "known" and self.value is not None:
            raise ValueError("unknown/unsupported duration must not contain a value")
        return self


class CostEvidence(Contract):
    status: MetricStatus
    amount: str | None = None
    currency: str | None = None
    source: Literal["provider_reported", "controller_computed", "unavailable"] = "unavailable"
    pricing: dict[str, str] | None = None

    @model_validator(mode="after")
    def coherent(self) -> "CostEvidence":
        if self.status == "known":
            if self.amount is None or self.currency is None:
                raise ValueError("known cost requires amount and currency")
            _decimal(self.amount, "cost amount")
        elif self.amount is not None or self.currency is not None:
            raise ValueError("unknown/unsupported cost must not contain amount/currency")
        return self


class UsageRecord(Contract):
    schema_version: Literal[1] = 1
    owner_id: str
    call_index: int = Field(ge=1, strict=True)
    attempt: int = Field(ge=0, strict=True)
    role: str
    node: str | None = None
    phase: str
    provider: str
    adapter: str
    family: str
    model: str | None = None
    effort: str | None = None
    outcome: Literal["completed", "failed", "cancelled"]
    controller_elapsed_seconds: UsageSeconds
    provider_elapsed_seconds: UsageSeconds
    input_tokens: UsageValue
    output_tokens: UsageValue
    reasoning_tokens: UsageValue
    cache_read_tokens: UsageValue
    cache_write_tokens: UsageValue
    total_tokens: UsageValue
    cost: CostEvidence
    limitations: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def identifiers(self) -> "UsageRecord":
        identifier(self.owner_id)
        identifier(self.role)
        if self.node is not None:
            identifier(self.node)
        identifier(self.provider)
        identifier(self.adapter)
        return self


TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "reasoning_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "total_tokens",
)


def _decimal(value: str, label: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except (InvalidOperation, TypeError) as exc:
        raise ValueError(f"{label} must be a finite nonnegative decimal string") from exc
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"{label} must be a finite nonnegative decimal string")
    return parsed


def _money(value: Decimal) -> str:
    # Eight decimal places is precise enough for per-call accounting while
    # retaining deterministic JSON and avoiding binary floating-point drift.
    return format(value.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP), "f")


def _known_int(raw: Any) -> int | None:
    return raw if type(raw) is int and raw >= 0 else None


def _usage_value(raw: dict[str, Any], key: str, support: SupportStatus) -> UsageValue:
    value = _known_int((raw.get("tokens") or {}).get(key) if isinstance(raw.get("tokens"), dict) else None)
    if value is not None:
        return UsageValue(status="known", value=value, source="provider_reported")
    return UsageValue(status="unknown" if support == "reported" else "unsupported")


def usage_descriptor(adapter: Any, config: Any, workspace: Any) -> UsageDescriptor:
    describe = getattr(adapter, "describe_usage", None)
    if not callable(describe):
        return UsageDescriptor(
            limitations=["adapter does not implement the optional v0.10 usage descriptor"]
        )
    value = describe(config, workspace)
    return value if isinstance(value, UsageDescriptor) else UsageDescriptor.model_validate(value)


def pricing_rule(rules: list[PricingRule], provider: str, model: str | None) -> PricingRule | None:
    if model is None:
        return None
    matches = [rule for rule in rules if rule.provider == provider and rule.model == model]
    if len(matches) > 1:
        raise OrchestratorError(
            f"pricing is ambiguous for {provider}/{model}; exact provider/model pricing must be unique"
        )
    return matches[0] if matches else None


def _controller_cost(
    rule: PricingRule,
    values: dict[str, UsageValue],
) -> CostEvidence:
    mapping = {
        "input_tokens": rule.input_per_million,
        "output_tokens": rule.output_per_million,
        "reasoning_tokens": rule.reasoning_per_million,
        "cache_read_tokens": rule.cache_read_per_million,
        "cache_write_tokens": rule.cache_write_per_million,
    }
    configured = [(name, rate) for name, rate in mapping.items() if rate is not None]
    if not configured:
        return CostEvidence(status="unsupported")
    total = Decimal("0")
    for name, rate in configured:
        metric = values[name]
        if metric.status != "known":
            return CostEvidence(status="unknown")
        total += Decimal(metric.value) * _decimal(rate, f"pricing {name}") / Decimal(1_000_000)
    return CostEvidence(
        status="known",
        amount=_money(total),
        currency=rule.currency,
        source="controller_computed",
        pricing={
            "provider": rule.provider,
            "model": rule.model,
            "source": rule.source,
            "version": rule.version,
            "effective_from": rule.effective_from,
        },
    )


def normalize_usage(
    *,
    owner_id: str,
    call_index: int,
    attempt: int,
    role: str,
    node: str | None,
    phase: str,
    provider: str,
    adapter_name: str,
    family: str,
    model: str | None,
    effort: str | None,
    outcome: Literal["completed", "failed", "cancelled"],
    elapsed_seconds: float,
    raw: dict[str, Any] | None,
    descriptor: UsageDescriptor,
    pricing: list[PricingRule],
) -> UsageRecord:
    payload = raw if isinstance(raw, dict) else {}
    values = {
        name: _usage_value(payload, name, getattr(descriptor, name))
        for name in TOKEN_FIELDS
    }

    provider_elapsed_raw = payload.get("provider_elapsed_seconds")
    if isinstance(provider_elapsed_raw, (int, float)) and not isinstance(provider_elapsed_raw, bool) and provider_elapsed_raw >= 0:
        provider_elapsed = UsageSeconds(
            status="known", value=float(provider_elapsed_raw), source="provider_reported"
        )
    else:
        provider_elapsed = UsageSeconds(
            status="unknown" if descriptor.provider_elapsed_seconds == "reported" else "unsupported"
        )

    raw_cost = payload.get("cost")
    cost: CostEvidence
    if isinstance(raw_cost, dict) and raw_cost.get("amount") is not None and isinstance(raw_cost.get("currency"), str):
        try:
            amount = _money(_decimal(str(raw_cost["amount"]), "provider-reported cost"))
        except ValueError:
            cost = CostEvidence(status="unknown")
        else:
            cost = CostEvidence(
                status="known",
                amount=amount,
                currency=raw_cost["currency"].upper(),
                source="provider_reported",
            )
    else:
        rule = pricing_rule(pricing, provider, model)
        cost = _controller_cost(rule, values) if rule is not None else CostEvidence(
            status="unknown" if descriptor.provider_cost == "reported" else "unsupported"
        )

    return UsageRecord(
        owner_id=owner_id,
        call_index=call_index,
        attempt=attempt,
        role=role,
        node=node,
        phase=phase,
        provider=provider,
        adapter=adapter_name,
        family=family,
        model=model,
        effort=effort,
        outcome=outcome,
        controller_elapsed_seconds=UsageSeconds(
            status="known", value=max(0.0, elapsed_seconds), source="controller_monotonic"
        ),
        provider_elapsed_seconds=provider_elapsed,
        **values,
        cost=cost,
        limitations=list(dict.fromkeys(descriptor.limitations)),
    )


def empty_usage() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "records": [],
        "summary": aggregate_usage([]),
    }


def usage_with_call_coverage(
    evidence: dict[str, Any] | None,
    *,
    expected_calls: int,
) -> dict[str, Any]:
    """Return a non-mutating usage view that accounts for missing call records.

    A genuinely new task with zero calls has known-zero usage. Historical tasks
    may have provider calls from before v0.10 usage accounting (or otherwise lack
    a record for every durable call). In that case, treating an empty/partial
    evidence set as the complete total would coerce missing telemetry to zero.
    Preserve recorded subtotals but mark aggregate usage/cost as unknown.
    """

    base = evidence if isinstance(evidence, dict) else empty_usage()
    records = list(base.get("records") or [])
    recorded_calls = len(records)
    if expected_calls == recorded_calls:
        return base

    summary = dict(
        base.get("summary")
        if isinstance(base.get("summary"), dict)
        else aggregate_usage([])
    )
    coverage = {
        "status": "incomplete" if expected_calls > recorded_calls else "inconsistent",
        "expected_calls": expected_calls,
        "recorded_calls": recorded_calls,
        "missing_calls": max(0, expected_calls - recorded_calls),
    }

    for field in TOKEN_FIELDS:
        current = summary.get(field) if isinstance(summary.get(field), dict) else {}
        known_subtotal = current.get("known_subtotal")
        if known_subtotal is None:
            known_subtotal = current.get("value") or 0
        summary[field] = {
            "status": "unknown",
            "value": None,
            "known_subtotal": known_subtotal,
        }

    current_seconds = (
        summary.get("provider_elapsed_seconds")
        if isinstance(summary.get("provider_elapsed_seconds"), dict)
        else {}
    )
    known_seconds = current_seconds.get("known_subtotal")
    if known_seconds is None:
        known_seconds = current_seconds.get("value") or 0.0
    summary["provider_elapsed_seconds"] = {
        "status": "unknown",
        "value": None,
        "known_subtotal": known_seconds,
    }

    current_cost = summary.get("cost") if isinstance(summary.get("cost"), dict) else {}
    summary["cost"] = {
        "status": "unknown",
        "amount": None,
        "currency": current_cost.get("currency"),
        "known_subtotal": current_cost.get("known_subtotal", "0.00000000"),
    }
    summary["call_coverage"] = coverage
    return {
        **base,
        "records": records,
        "summary": summary,
    }


def _aggregate_metric(records: list[UsageRecord], field: str) -> dict[str, Any]:
    if not records:
        return {"status": "known", "value": 0, "known_subtotal": 0}
    values = [getattr(record, field) for record in records]
    known = sum(item.value or 0 for item in values if item.status == "known")
    statuses = {item.status for item in values}
    if statuses == {"known"}:
        return {"status": "known", "value": known, "known_subtotal": known}
    if statuses == {"unsupported"}:
        return {"status": "unsupported", "value": None, "known_subtotal": 0}
    return {"status": "unknown", "value": None, "known_subtotal": known}


def _aggregate_seconds(records: list[UsageRecord], field: str) -> dict[str, Any]:
    if not records:
        return {"status": "known", "value": 0.0, "known_subtotal": 0.0}
    values = [getattr(record, field) for record in records]
    known = sum(item.value or 0.0 for item in values if item.status == "known")
    statuses = {item.status for item in values}
    if statuses == {"known"}:
        return {"status": "known", "value": round(known, 6), "known_subtotal": round(known, 6)}
    if statuses == {"unsupported"}:
        return {"status": "unsupported", "value": None, "known_subtotal": 0.0}
    return {"status": "unknown", "value": None, "known_subtotal": round(known, 6)}


def _aggregate_cost(records: list[UsageRecord]) -> dict[str, Any]:
    if not records:
        return {"status": "known", "amount": "0.00000000", "currency": None, "known_subtotal": "0.00000000"}
    known = [record.cost for record in records if record.cost.status == "known"]
    currencies = {item.currency for item in known if item.currency}
    subtotal = sum((_decimal(item.amount or "0", "cost") for item in known), Decimal("0"))
    statuses = {record.cost.status for record in records}
    if statuses == {"known"} and len(currencies) == 1:
        currency = next(iter(currencies))
        return {"status": "known", "amount": _money(subtotal), "currency": currency, "known_subtotal": _money(subtotal)}
    if statuses == {"unsupported"}:
        return {"status": "unsupported", "amount": None, "currency": None, "known_subtotal": "0.00000000"}
    return {
        "status": "unknown",
        "amount": None,
        "currency": next(iter(currencies)) if len(currencies) == 1 else None,
        "known_subtotal": _money(subtotal),
    }


def _group(records: list[UsageRecord], key) -> list[dict[str, Any]]:
    buckets: dict[str, list[UsageRecord]] = {}
    for record in records:
        label = key(record)
        buckets.setdefault(label, []).append(record)
    result = []
    for label in sorted(buckets):
        items = buckets[label]
        result.append({"key": label, **aggregate_usage(items, include_groups=False)})
    return result


def aggregate_usage(records: list[UsageRecord], *, include_groups: bool = True) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "calls": len(records),
        "controller_elapsed_seconds": round(sum(
            record.controller_elapsed_seconds.value or 0.0
            for record in records
            if record.controller_elapsed_seconds.status == "known"
        ), 6),
        "provider_elapsed_seconds": _aggregate_seconds(records, "provider_elapsed_seconds"),
        **{field: _aggregate_metric(records, field) for field in TOKEN_FIELDS},
        "cost": _aggregate_cost(records),
    }
    if include_groups:
        summary["by_node"] = _group(records, lambda r: r.node or r.role)
        summary["by_attempt"] = _group(records, lambda r: str(r.attempt))
        summary["by_provider"] = _group(records, lambda r: r.provider)
        summary["by_model"] = _group(records, lambda r: f"{r.provider}/{r.model or '<adapter-default>'}")
    return summary


def append_usage(evidence: dict[str, Any] | None, record: UsageRecord) -> dict[str, Any]:
    records: list[UsageRecord] = []
    if isinstance(evidence, dict):
        for item in evidence.get("records") or []:
            records.append(UsageRecord.model_validate(item))
    records.append(record)
    return {
        "schema_version": 1,
        "records": [item.model_dump() for item in records],
        "summary": aggregate_usage(records),
    }


def _metric_limit(
    result: list[dict[str, Any]],
    name: str,
    limit: int | None,
    summary: dict[str, Any],
    unknown_policy: str,
) -> None:
    if limit is None:
        return
    metric = summary[name]
    if metric["status"] != "known":
        if unknown_policy == "fail_closed":
            result.append({
                "dimension": name,
                "status": "unprovable",
                "limit": limit,
                "observed": None,
            })
        return
    value = metric["value"]
    if value >= limit:
        result.append({
            "dimension": name,
            "status": "exhausted",
            "limit": limit,
            "observed": value,
        })


def budget_snapshot(policy: Policy, evidence: dict[str, Any] | None, *, calls: int, elapsed_seconds: float) -> dict[str, Any]:
    usage = evidence if isinstance(evidence, dict) else empty_usage()
    summary = usage.get("summary") if isinstance(usage.get("summary"), dict) else aggregate_usage([])
    budget: BudgetPolicy = policy.budget
    effective_calls = min(
        policy.max_agent_calls,
        budget.max_provider_calls if budget.max_provider_calls is not None else policy.max_agent_calls,
    )
    effective_elapsed = min(
        float(policy.task_timeout_seconds),
        budget.max_controller_elapsed_seconds if budget.max_controller_elapsed_seconds is not None else float(policy.task_timeout_seconds),
    )

    blockers: list[dict[str, Any]] = []
    if calls >= effective_calls:
        blockers.append({
            "dimension": "provider_calls",
            "status": "exhausted",
            "limit": effective_calls,
            "observed": calls,
        })
    if elapsed_seconds >= effective_elapsed:
        blockers.append({
            "dimension": "controller_elapsed_seconds",
            "status": "exhausted",
            "limit": effective_elapsed,
            "observed": round(elapsed_seconds, 6),
        })
    for field in ("input_tokens", "output_tokens", "reasoning_tokens", "total_tokens"):
        _metric_limit(blockers, field, getattr(budget, f"max_{field}"), summary, budget.unknown_usage)

    if budget.max_provider_seconds is not None:
        provider_elapsed = summary.get("provider_elapsed_seconds") or {}
        if provider_elapsed.get("status") != "known":
            if budget.unknown_usage == "fail_closed":
                blockers.append({
                    "dimension": "provider_elapsed_seconds",
                    "status": "unprovable",
                    "limit": budget.max_provider_seconds,
                    "observed": None,
                })
        elif provider_elapsed.get("value", 0.0) >= budget.max_provider_seconds:
            blockers.append({
                "dimension": "provider_elapsed_seconds",
                "status": "exhausted",
                "limit": budget.max_provider_seconds,
                "observed": provider_elapsed.get("value"),
            })

    if budget.max_cost is not None:
        cost = summary["cost"]
        if cost["status"] != "known":
            if budget.unknown_usage == "fail_closed":
                blockers.append({
                    "dimension": "cost",
                    "status": "unprovable",
                    "limit": budget.max_cost,
                    "observed": None,
                    "currency": budget.currency,
                })
        else:
            observed_currency = cost.get("currency")
            if observed_currency not in (None, budget.currency):
                blockers.append({
                    "dimension": "cost",
                    "status": "unprovable",
                    "limit": budget.max_cost,
                    "observed": cost.get("amount"),
                    "currency": observed_currency,
                })
            elif _decimal(cost["amount"], "cost") >= _decimal(budget.max_cost, "budget max_cost"):
                blockers.append({
                    "dimension": "cost",
                    "status": "exhausted",
                    "limit": budget.max_cost,
                    "observed": cost["amount"],
                    "currency": budget.currency,
                })

    return {
        "schema_version": 1,
        "legacy_limits": {
            "max_agent_calls": policy.max_agent_calls,
            "task_timeout_seconds": policy.task_timeout_seconds,
        },
        "policy": budget.model_dump(),
        "effective_limits": {
            "provider_calls": effective_calls,
            "controller_elapsed_seconds": effective_elapsed,
        },
        "consumed": {
            "provider_calls": calls,
            "controller_elapsed_seconds": round(elapsed_seconds, 6),
            "provider_elapsed_seconds": summary.get("provider_elapsed_seconds"),
            "input_tokens": summary.get("input_tokens"),
            "output_tokens": summary.get("output_tokens"),
            "reasoning_tokens": summary.get("reasoning_tokens"),
            "total_tokens": summary.get("total_tokens"),
            "cost": summary.get("cost"),
        },
        "blockers": blockers,
        "can_dispatch": not blockers,
        "fallback": "none",
    }


def _descriptor_supports_cost(
    descriptor: UsageDescriptor,
    rule: PricingRule | None,
) -> bool:
    if descriptor.provider_cost == "reported":
        return True
    if rule is None:
        return False
    mapping = {
        "input_tokens": rule.input_per_million,
        "output_tokens": rule.output_per_million,
        "reasoning_tokens": rule.reasoning_per_million,
        "cache_read_tokens": rule.cache_read_per_million,
        "cache_write_tokens": rule.cache_write_per_million,
    }
    configured = [name for name, rate in mapping.items() if rate is not None]
    return bool(configured) and all(getattr(descriptor, name) == "reported" for name in configured)


def assert_dispatch_allowed(
    *,
    policy: Policy,
    pricing: list[PricingRule],
    evidence: dict[str, Any] | None,
    calls: int,
    elapsed_seconds: float,
    provider: str,
    model: str | None,
    descriptor: UsageDescriptor,
) -> dict[str, Any]:
    snapshot = budget_snapshot(policy, evidence, calls=calls, elapsed_seconds=elapsed_seconds)
    if snapshot["blockers"]:
        detail = ", ".join(
            f"{item['dimension']}:{item['status']}" for item in snapshot["blockers"]
        )
        raise OrchestratorError(f"budget blocks provider dispatch ({detail}); no fallback is permitted")

    budget = policy.budget
    unsupported: list[str] = []
    if budget.unknown_usage == "fail_closed":
        for field in ("input_tokens", "output_tokens", "reasoning_tokens", "total_tokens"):
            if getattr(budget, f"max_{field}") is not None and getattr(descriptor, field) != "reported":
                unsupported.append(field)
        if budget.max_provider_seconds is not None and descriptor.provider_elapsed_seconds != "reported":
            unsupported.append("provider_elapsed_seconds")
        if budget.max_cost is not None and not _descriptor_supports_cost(
            descriptor, pricing_rule(pricing, provider, model)
        ):
            unsupported.append("cost")
    if unsupported:
        raise OrchestratorError(
            "strict budget cannot be proven for this provider/model because telemetry is unsupported: "
            + ", ".join(unsupported)
            + "; no token/cost values were guessed and no cheaper fallback was selected"
        )

    prospective_calls = calls + 1
    effective_calls = snapshot["effective_limits"]["provider_calls"]
    if prospective_calls > effective_calls:
        raise OrchestratorError("provider-call budget would be exceeded by the next dispatch")
    for limit in budget.call_limits:
        if limit.provider != provider or (limit.model is not None and limit.model != model):
            continue
        records = (evidence or {}).get("records") if isinstance(evidence, dict) else []
        used = sum(
            1 for item in (records or [])
            if isinstance(item, dict)
            and item.get("provider") == provider
            and (limit.model is None or item.get("model") == limit.model)
        )
        if used + 1 > limit.max_calls:
            target = provider + (f"/{limit.model}" if limit.model else "")
            raise OrchestratorError(f"provider/model call budget exhausted for {target}")
    return snapshot


def assert_post_call_budget(policy: Policy, evidence: dict[str, Any], *, calls: int, elapsed_seconds: float) -> dict[str, Any]:
    snapshot = budget_snapshot(policy, evidence, calls=calls, elapsed_seconds=elapsed_seconds)
    violations: list[dict[str, Any]] = []
    for item in snapshot["blockers"]:
        if item["status"] == "unprovable":
            violations.append(item)
            continue
        observed, limit = item.get("observed"), item.get("limit")
        if observed is None or limit is None:
            continue
        if item["dimension"] == "cost":
            exceeded = _decimal(str(observed), "observed cost") > _decimal(str(limit), "cost limit")
        else:
            exceeded = float(observed) > float(limit)
        if exceeded:
            violations.append(item)
    if violations:
        detail = ", ".join(
            f"{item['dimension']}:{item['status']}" for item in violations
        )
        raise OrchestratorError(
            f"budget exceeded or became unprovable after provider call ({detail}); stop before the next effect"
        )
    return snapshot
