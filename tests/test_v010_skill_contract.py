"""Portable skill contract regression coverage for v0.10."""

from pathlib import Path

import ai_orchestrator


def skill_text() -> str:
    return (Path(ai_orchestrator.__file__).parent / "assets" / "SKILL.md").read_text(encoding="utf-8")


def test_packaged_skill_carries_v010_usage_budget_safety_contract():
    text = skill_text()
    required = [
        "Task -> Workflow Node -> Provider Resolution -> Model Variant Resolution -> Execution -> Usage Evidence -> Budget Evaluation",
        "known`, `unknown` or `unsupported",
        "Never coerce missing/unknown/unsupported telemetry\n        to zero",
        "Do not select a cheaper provider/model",
        "Controller-computed cost requires",
        "Budget configuration is trusted controller policy",
        "Exact exhaustion",
        "get_artifact(kind=usage)",
        "get_artifact(kind=budget)",
        "stale pricing rules",
        "Codex: use only structured token counters",
        "Claude: use only explicit usage counters",
        "AGY: the current stream-json contract is not treated as a stable",
    ]
    for phrase in required:
        assert phrase in text


def test_packaged_skill_keeps_humangate_no_fallback_boundary():
    text = skill_text()
    assert "Do not fall back to executing" in text
    assert "approval/configuration commands through shell or CLI" in text
    assert "do not edit config.yaml" in text
