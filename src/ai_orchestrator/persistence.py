"""Persisted contract versions and non-mutating compatibility readers.

v0.12 treats persistence compatibility as an explicit control-plane contract.
Old rows/artifacts are never rewritten merely because they were read.  Unknown
versions fail closed before authority or effectful state can be interpreted.
"""

from __future__ import annotations

import json
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from .models import OrchestratorError


ModelT = TypeVar("ModelT", bound=BaseModel)

RUNTIME_DB_VERSION = 2
RUNTIME_DB_READABLE_VERSIONS = (0, 1, 2)
HUMAN_GATE_DB_VERSION = 1
HUMAN_GATE_DB_READABLE_VERSIONS = (0, 1)
JOB_DB_VERSION = 1
JOB_DB_READABLE_VERSIONS = (0, 1)
EVENT_SCHEMA_VERSION = 1

PERSISTED_CONTRACT_RULES: dict[str, dict[str, Any]] = {
    "task_state": {
        "name": "TaskState",
        "readable_versions": (1, 2, 3, 4, 5, 6, 7, 8),
        "write_version": 8,
        "strategy": "read-compatible; never rewrite on read",
    },
    "intake_state": {
        "name": "IntakeState",
        "readable_versions": (1, 2, 3, 4, 5),
        "write_version": 5,
        "strategy": "read-compatible; never rewrite on read",
    },
    "human_gate": {
        "name": "HumanGate",
        "readable_versions": (1,),
        "write_version": 1,
        "strategy": "read-compatible; terminal gate history is never replayed",
    },
    "artifact": {
        "name": "Artifact",
        "readable_versions": (1, 2),
        "write_version": 2,
        "strategy": "v1 remains readable; v2 adds stable identity/provenance metadata",
    },
    "runtime_event": {
        "name": "RuntimeEvent",
        "readable_versions": (1,),
        "write_version": 1,
        "strategy": "legacy SQLite rows are exposed through the v1 event envelope",
    },
    "usage_evidence": {
        "name": "UsageEvidence",
        "readable_versions": (1,),
        "write_version": 1,
        "strategy": "unknown counters remain unknown; no inferred migration",
    },
    "budget_evidence": {
        "name": "BudgetEvidence",
        "readable_versions": (1,),
        "write_version": 1,
        "strategy": "policy evidence is interpreted only under the recorded schema",
    },
    "provider_provenance": {
        "name": "ProviderProvenance",
        "readable_versions": (1,),
        "write_version": 1,
        "strategy": "content-free dispatch provenance is append-only evidence",
    },
    "project_learning_candidate": {
        "name": "ProjectLearningCandidate",
        "readable_versions": (1, 2),
        "write_version": 2,
        "strategy": "v1 manual proposals remain readable; v2 adds typed evidence/support/provenance",
    },
    "context_influence": {
        "name": "ContextInfluence",
        "readable_versions": (1,),
        "write_version": 1,
        "strategy": "frozen selected-context provenance; unknown selector contracts fail closed",
    },
    "recovery_evidence": {
        "name": "RecoveryEvidence",
        "readable_versions": (0, 1),
        "write_version": 1,
        "strategy": (
            "legacy v0.11 unversioned recovery JSON is read as schema v1 in memory; "
            "artifact bytes and hashes are not rewritten"
        ),
    },
}

EVIDENCE_RULES = {
    "usage": "usage_evidence",
    "budget": "budget_evidence",
    "provider_provenance": "provider_provenance",
    "context_influence": "context_influence",
    "recovery": "recovery_evidence",
}


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def _versions_text(versions: tuple[int, ...]) -> str:
    return ",".join(str(item) for item in versions)


def validate_database_version(
    label: str,
    version: int,
    readable_versions: tuple[int, ...],
) -> None:
    if type(version) is not int or version not in readable_versions:
        raise OrchestratorError(
            f"unsupported {label} database version {version}; readable versions are "
            f"{_versions_text(readable_versions)}. No persisted state was changed."
        )


def _schema_version(
    payload: dict[str, Any],
    *,
    rule_key: str,
    legacy_missing_version: int | None = None,
) -> int:
    rule = PERSISTED_CONTRACT_RULES[rule_key]
    if "schema_version" not in payload:
        if legacy_missing_version is not None:
            return legacy_missing_version
        raise OrchestratorError(
            f"{rule['name']} is missing schema_version; no persisted state was changed"
        )
    version = payload["schema_version"]
    if type(version) is not int:
        raise OrchestratorError(
            f"{rule['name']} schema_version must be an integer; no persisted state was changed"
        )
    if version not in rule["readable_versions"]:
        raise OrchestratorError(
            f"unsupported persisted {rule['name']} schema_version={version}; readable versions are "
            f"{_versions_text(rule['readable_versions'])}. No persisted state was changed."
        )
    return version


def decode_versioned_model_json(
    text: str,
    *,
    rule_key: str,
    model: type[ModelT],
) -> ModelT:
    rule = PERSISTED_CONTRACT_RULES[rule_key]
    try:
        payload = json.loads(text, parse_constant=_reject_constant)
    except (json.JSONDecodeError, ValueError) as exc:
        raise OrchestratorError(
            f"persisted {rule['name']} is not strict JSON; no persisted state was changed"
        ) from exc
    if not isinstance(payload, dict):
        raise OrchestratorError(
            f"persisted {rule['name']} must be a JSON object; no persisted state was changed"
        )
    version = _schema_version(payload, rule_key=rule_key)
    try:
        return model.model_validate(payload)
    except ValidationError as exc:
        raise OrchestratorError(
            f"persisted {rule['name']} schema_version={version} is invalid; "
            "no persisted state was changed"
        ) from exc


def normalize_control_evidence(kind: str, value: Any) -> Any:
    """Validate known versioned evidence after its artifact hash is verified.

    Recovery artifacts written by v0.11 predate an explicit evidence
    schema_version.  They are represented as v0 and upgraded only in the
    returned compatibility view; immutable bytes and hashes stay untouched.
    """

    rule_key = EVIDENCE_RULES.get(kind)
    if rule_key is None:
        return value
    rule = PERSISTED_CONTRACT_RULES[rule_key]
    if not isinstance(value, dict):
        raise OrchestratorError(
            f"{rule['name']} must be a JSON object; artifact bytes were not changed"
        )
    legacy = 0 if kind == "recovery" else None
    version = _schema_version(
        value,
        rule_key=rule_key,
        legacy_missing_version=legacy,
    )
    if version == 0:
        return {**value, "schema_version": 1}
    return value


def persistence_compatibility_report() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "policy": {
            "read_migration": "non-mutating compatibility view",
            "unknown_version": "fail closed before authority/effect interpretation",
            "automatic_rewrite": False,
            "forward_compatibility": "never guess semantics for unknown versions",
            "downgrade": (
                "restore a complete runtime backup with the matching older executable; "
                "lossy in-place downgrade is unsupported"
            ),
        },
        "databases": {
            "runtime_state": {
                "readable_versions": list(RUNTIME_DB_READABLE_VERSIONS),
                "write_version": RUNTIME_DB_VERSION,
            },
            "human_gate": {
                "readable_versions": list(HUMAN_GATE_DB_READABLE_VERSIONS),
                "write_version": HUMAN_GATE_DB_VERSION,
            },
            "jobs": {
                "readable_versions": list(JOB_DB_READABLE_VERSIONS),
                "write_version": JOB_DB_VERSION,
            },
        },
        "contracts": {
            key: {
                "name": rule["name"],
                "readable_versions": list(rule["readable_versions"]),
                "write_version": rule["write_version"],
                "strategy": rule["strategy"],
            }
            for key, rule in PERSISTED_CONTRACT_RULES.items()
        },
    }
