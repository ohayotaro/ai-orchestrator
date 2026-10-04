"""Public Provider Adapter SDK and trusted project plugin loading.

External entry points are metadata-only until an exact project profile pin is
trusted. Loading a plugin executes third-party Python code in the controller
process, so enabled plugins are explicitly part of the trusted-local TCB.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any

from .models import OrchestratorError, Profile, ProviderConfig, identifier
from .providers import ProviderAdapter, ProviderExecutionError, RunRequest, default_registry
from .runtime_options import RuntimeOptionsDescriptor
from .usage import UsageDescriptor

PROVIDER_SDK_VERSION = 1
PROVIDER_PLUGIN_ENTRYPOINT_GROUP = "ai_orchestrator.providers"
SUPPORTED_EXTERNAL_ADAPTER_API_VERSIONS = frozenset({2})


def canonical_distribution_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


@dataclass(frozen=True)
class _PluginCandidate:
    adapter: str
    distribution: str
    version: str
    entry_point: str
    loader: Any


class LoadedPluginAdapter:
    """Delegating wrapper that retains controller-owned plugin identity."""

    def __init__(self, adapter: Any, identity: dict[str, str]):
        self._adapter = adapter
        self.plugin_identity = dict(identity)

    @property
    def provider_sdk_version(self) -> int:
        return int(getattr(self._adapter, "provider_sdk_version"))

    @property
    def api_version(self) -> int:
        return int(getattr(self._adapter, "api_version"))

    @property
    def family(self) -> str:
        return str(getattr(self._adapter, "family"))

    @property
    def capabilities(self):
        return getattr(self._adapter, "capabilities")

    @property
    def semantic_capabilities(self):
        return getattr(self._adapter, "semantic_capabilities")

    def doctor(self, config: ProviderConfig, workspace: Path):
        return self._adapter.doctor(config, workspace)

    def execute(self, request: RunRequest):
        return self._adapter.execute(request)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._adapter, name)


def _bounded_identifier_set(value: object, field: str) -> frozenset[str]:
    if not isinstance(value, (set, frozenset, list, tuple)):
        raise OrchestratorError(f"provider adapter {field} must be a finite identifier collection")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise OrchestratorError(f"provider adapter {field} entries must be strings")
        try:
            normalized = identifier(item)
        except ValueError as exc:
            raise OrchestratorError(f"provider adapter {field} contains an invalid identifier") from exc
        if normalized not in result:
            result.append(normalized)
    return frozenset(result)


def assert_provider_adapter_conforms(
    adapter_id: str,
    adapter: Any,
    *,
    config: ProviderConfig | None = None,
    workspace: Path | None = None,
) -> dict[str, Any]:
    """Validate the public v0.13 adapter contract.

    Supplying config/workspace additionally exercises doctor and optional
    descriptor methods. execute is deliberately not invoked by conformance
    checks because provider dispatch may be billable/effectful.
    """
    try:
        adapter_id = identifier(adapter_id)
    except ValueError as exc:
        raise OrchestratorError("provider plugin adapter ID is invalid") from exc

    if type(getattr(adapter, "provider_sdk_version", None)) is not int:
        raise OrchestratorError(f"{adapter_id}: external adapter must declare integer provider_sdk_version")
    if adapter.provider_sdk_version != PROVIDER_SDK_VERSION:
        raise OrchestratorError(
            f"{adapter_id}: unsupported provider SDK version {adapter.provider_sdk_version}; "
            f"kernel supports {PROVIDER_SDK_VERSION}"
        )
    if type(getattr(adapter, "api_version", None)) is not int:
        raise OrchestratorError(f"{adapter_id}: adapter api_version must be an integer")
    if adapter.api_version not in SUPPORTED_EXTERNAL_ADAPTER_API_VERSIONS:
        raise OrchestratorError(
            f"{adapter_id}: unsupported external adapter API version {adapter.api_version}; "
            f"supported={','.join(str(v) for v in sorted(SUPPORTED_EXTERNAL_ADAPTER_API_VERSIONS))}"
        )

    family = getattr(adapter, "family", None)
    if not isinstance(family, str):
        raise OrchestratorError(f"{adapter_id}: adapter family must be an identifier")
    try:
        family = identifier(family)
    except ValueError as exc:
        raise OrchestratorError(f"{adapter_id}: adapter family must be an identifier") from exc

    runtime_capabilities = _bounded_identifier_set(getattr(adapter, "capabilities", None), "capabilities")
    semantic_capabilities = _bounded_identifier_set(
        getattr(adapter, "semantic_capabilities", None), "semantic_capabilities"
    )
    if not callable(getattr(adapter, "doctor", None)):
        raise OrchestratorError(f"{adapter_id}: adapter must implement doctor(config, workspace)")
    if not callable(getattr(adapter, "execute", None)):
        raise OrchestratorError(f"{adapter_id}: adapter must implement execute(request)")

    optional_features = {
        "runtime_options": callable(getattr(adapter, "describe_runtime_options", None)),
        "usage": callable(getattr(adapter, "describe_usage", None)),
        "role_compatibility": callable(getattr(adapter, "role_compatibility", None)),
    }

    if (config is None) != (workspace is None):
        raise OrchestratorError("provider conformance requires config and workspace together")
    if config is not None and workspace is not None:
        report = adapter.doctor(config, workspace)
        if not isinstance(report, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in report.items()
        ):
            raise OrchestratorError(f"{adapter_id}: doctor must return dict[str, str]")
        describe_runtime = getattr(adapter, "describe_runtime_options", None)
        if callable(describe_runtime):
            RuntimeOptionsDescriptor.model_validate(describe_runtime(config, workspace))
        describe_usage = getattr(adapter, "describe_usage", None)
        if callable(describe_usage):
            UsageDescriptor.model_validate(describe_usage(config, workspace))

    return {
        "schema_version": 1,
        "provider_sdk_version": PROVIDER_SDK_VERSION,
        "adapter": adapter_id,
        "adapter_api_version": adapter.api_version,
        "family": family,
        "runtime_capabilities": sorted(runtime_capabilities),
        "semantic_capabilities": sorted(semantic_capabilities),
        "optional_features": optional_features,
    }


def _installed_candidates() -> tuple[list[_PluginCandidate], list[dict[str, str]]]:
    candidates: list[_PluginCandidate] = []
    errors: list[dict[str, str]] = []
    try:
        distributions = list(metadata.distributions())
    except Exception as exc:
        return [], [{"status": "metadata_error", "error_type": type(exc).__name__}]

    for dist in distributions:
        raw_name = None
        try:
            raw_name = dist.metadata.get("Name")
        except Exception:
            raw_name = None
        raw_name = raw_name or getattr(dist, "name", None)
        version = getattr(dist, "version", None)
        if not isinstance(raw_name, str) or not raw_name.strip() or not isinstance(version, str):
            continue
        distribution = canonical_distribution_name(raw_name.strip())
        try:
            entry_points = list(dist.entry_points)
        except Exception as exc:
            errors.append({
                "status": "metadata_error",
                "distribution": distribution,
                "error_type": type(exc).__name__,
            })
            continue
        for entry_point in entry_points:
            if getattr(entry_point, "group", None) != PROVIDER_PLUGIN_ENTRYPOINT_GROUP:
                continue
            name = getattr(entry_point, "name", None)
            value = getattr(entry_point, "value", None)
            if not isinstance(name, str) or not isinstance(value, str):
                errors.append({"status": "invalid_entry_point", "distribution": distribution})
                continue
            try:
                adapter_id = identifier(name)
            except ValueError:
                errors.append({
                    "status": "invalid_adapter_id",
                    "distribution": distribution,
                    "entry_point": value,
                })
                continue
            candidates.append(_PluginCandidate(
                adapter=adapter_id,
                distribution=distribution,
                version=version,
                entry_point=value,
                loader=entry_point,
            ))
    candidates.sort(key=lambda item: (item.adapter, item.distribution, item.version, item.entry_point))
    return candidates, errors


def inspect_provider_plugins(
    profile: Profile,
    *,
    trusted: bool,
    load_diagnostics: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Inspect package metadata only; this function never loads plugin code."""
    candidates, metadata_errors = _installed_candidates()
    installed = [
        {
            "adapter": item.adapter,
            "distribution": item.distribution,
            "version": item.version,
            "entry_point": item.entry_point,
        }
        for item in candidates
    ]
    configured: dict[str, Any] = {}
    diagnostics = load_diagnostics or {}
    for adapter_id, pin in sorted(profile.provider_plugins.items()):
        exact = [
            item for item in candidates
            if item.adapter == adapter_id
            and item.distribution == canonical_distribution_name(pin.distribution)
            and item.version == pin.version
            and item.entry_point == pin.entry_point
        ]
        status = "ready" if len(exact) == 1 else ("ambiguous" if len(exact) > 1 else "missing_or_mismatched")
        if adapter_id in diagnostics:
            status = str(diagnostics[adapter_id].get("status", status))
        configured[adapter_id] = {
            "pin": pin.model_dump(),
            "metadata_status": "exact_match" if len(exact) == 1 else status,
            "load_status": status,
            "diagnostics": diagnostics.get(adapter_id),
        }
    return {
        "schema_version": 1,
        "provider_sdk_version": PROVIDER_SDK_VERSION,
        "entry_point_group": PROVIDER_PLUGIN_ENTRYPOINT_GROUP,
        "profile_trusted": trusted,
        "configured": configured,
        "installed_entry_points": installed,
        "metadata_errors": metadata_errors,
        "activation_policy": (
            "installed entry points are metadata only; external code loads only for exact profile pins "
            "after that profile digest is trusted"
        ),
        "trust_boundary": (
            "loaded in-process adapters are trusted controller code; package/version pins express operator intent "
            "but do not cryptographically attest immutable package bytes"
        ),
    }


def _instantiate_plugin(candidate: _PluginCandidate) -> Any:
    try:
        loaded = candidate.loader.load()
        if isinstance(loaded, type):
            return loaded()
        if callable(loaded) and not callable(getattr(loaded, "execute", None)):
            return loaded()
        return loaded
    except Exception as exc:
        raise OrchestratorError(
            f"{candidate.adapter}: provider plugin load failed ({type(exc).__name__})"
        ) from exc


def load_provider_registry(
    profile: Profile,
    *,
    trusted: bool,
    builtin_registry: dict[str, ProviderAdapter] | None = None,
) -> tuple[dict[str, ProviderAdapter], dict[str, dict[str, Any]]]:
    """Load only trusted, exactly pinned external provider adapters."""
    registry: dict[str, ProviderAdapter] = dict(builtin_registry or default_registry())
    diagnostics: dict[str, dict[str, Any]] = {}
    if not profile.provider_plugins:
        return registry, diagnostics

    candidates, _ = _installed_candidates()
    for adapter_id, pin in sorted(profile.provider_plugins.items()):
        base = {"adapter": adapter_id, "pin": pin.model_dump()}
        if adapter_id in registry:
            diagnostics[adapter_id] = {
                **base,
                "ok": False,
                "status": "builtin_collision",
                "error": "external provider plugin ID collides with a built-in adapter",
            }
            continue
        if not trusted:
            diagnostics[adapter_id] = {
                **base,
                "ok": False,
                "status": "profile_untrusted",
                "error": "external provider code is not loaded until the exact profile digest is trusted",
            }
            continue

        matches = [
            item for item in candidates
            if item.adapter == adapter_id
            and item.distribution == canonical_distribution_name(pin.distribution)
            and item.version == pin.version
            and item.entry_point == pin.entry_point
        ]
        if len(matches) != 1:
            diagnostics[adapter_id] = {
                **base,
                "ok": False,
                "status": "ambiguous" if len(matches) > 1 else "missing_or_mismatched",
                "error": "installed provider entry point does not exactly match the trusted project pin",
            }
            continue

        candidate = matches[0]
        try:
            adapter = _instantiate_plugin(candidate)
            conformance = assert_provider_adapter_conforms(adapter_id, adapter)
        except OrchestratorError as exc:
            diagnostics[adapter_id] = {
                **base,
                "ok": False,
                "status": "conformance_failed",
                "error": str(exc),
            }
            continue

        identity = {
            "adapter": adapter_id,
            "distribution": candidate.distribution,
            "version": candidate.version,
            "entry_point": candidate.entry_point,
            "provider_sdk_version": str(PROVIDER_SDK_VERSION),
            "adapter_api_version": str(conformance["adapter_api_version"]),
        }
        registry[adapter_id] = LoadedPluginAdapter(adapter, identity)
        diagnostics[adapter_id] = {
            **base,
            "ok": True,
            "status": "loaded",
            "identity": identity,
            "conformance": conformance,
        }
    return registry, diagnostics


__all__ = [
    "PROVIDER_PLUGIN_ENTRYPOINT_GROUP",
    "PROVIDER_SDK_VERSION",
    "ProviderAdapter",
    "ProviderExecutionError",
    "RunRequest",
    "assert_provider_adapter_conforms",
    "canonical_distribution_name",
    "inspect_provider_plugins",
    "load_provider_registry",
]
