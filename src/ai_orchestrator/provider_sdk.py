"""Public Provider Adapter SDK and trusted project plugin loading.

External entry points are metadata-only until an exact project profile pin is
trusted. Loading a plugin executes third-party Python code in the controller
process, so enabled plugins are explicitly part of the trusted-local TCB.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any

from .capabilities import CAPABILITIES
from .models import OrchestratorError, Profile, ProviderConfig, identifier
from .providers import ProviderAdapter, ProviderExecutionError, RunRequest, default_registry
from .runtime_options import RuntimeOptionsDescriptor
from .usage import UsageDescriptor

PROVIDER_SDK_VERSION = 1
PROVIDER_PLUGIN_ENTRYPOINT_GROUP = "ai_orchestrator.providers"
SUPPORTED_EXTERNAL_ADAPTER_API_VERSIONS = frozenset({2})
PROVIDER_FAILURE_CATEGORIES = frozenset({
    "authentication",
    "quota",
    "permission",
    "configuration",
    "protocol",
    "provider_process",
})
_SAFE_DIAGNOSTIC_LABEL = re.compile(r"[A-Za-z0-9_.:-]{1,120}")


def canonical_distribution_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


@dataclass(frozen=True)
class _PluginCandidate:
    adapter: str
    distribution: str
    version: str
    entry_point: str
    loader: Any


def _bounded_diagnostic_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 3:
        raise OrchestratorError("external provider diagnostics exceed the nesting limit")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        if abs(value) > 2**63 - 1:
            raise OrchestratorError("external provider diagnostic integer is out of range")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise OrchestratorError("external provider diagnostic number must be finite")
        return value
    if isinstance(value, str):
        if not _SAFE_DIAGNOSTIC_LABEL.fullmatch(value):
            raise OrchestratorError("external provider diagnostic strings must be bounded identifier-like labels")
        return value
    if isinstance(value, list):
        if len(value) > 32:
            raise OrchestratorError("external provider diagnostic lists are too large")
        return [_bounded_diagnostic_value(item, depth=depth + 1) for item in value]
    if isinstance(value, dict):
        if len(value) > 32:
            raise OrchestratorError("external provider diagnostic mappings are too large")
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", key):
                raise OrchestratorError("external provider diagnostic keys must be bounded identifiers")
            result[key] = _bounded_diagnostic_value(item, depth=depth + 1)
        return result
    raise OrchestratorError("external provider diagnostics contain an unsupported value type")


def normalize_provider_failure_diagnostics(adapter_id: str, diagnostics: object) -> dict[str, Any]:
    """Validate content-free diagnostics before they enter durable controller state."""
    raw = diagnostics if isinstance(diagnostics, dict) else {}
    normalized = _bounded_diagnostic_value(raw)
    assert isinstance(normalized, dict)
    category = normalized.get("failure_category", "provider_process")
    if not isinstance(category, str) or category not in PROVIDER_FAILURE_CATEGORIES:
        raise OrchestratorError("external provider diagnostics contain an unsupported failure_category")
    normalized["failure_category"] = category
    normalized["adapter"] = identifier(adapter_id)
    return normalized


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
        adapter_id = self.plugin_identity["adapter"]
        try:
            report = self._adapter.doctor(config, workspace)
        except Exception as exc:
            exception_type = type(exc).__name__
            if not _SAFE_DIAGNOSTIC_LABEL.fullmatch(exception_type):
                exception_type = "Exception"
            raise OrchestratorError(
                f"{adapter_id}: provider plugin doctor failed ({exception_type})"
            ) from exc
        if not isinstance(report, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in report.items()
        ):
            raise OrchestratorError(
                f"{adapter_id}: doctor must return dict[str, str]"
            )
        return report

    def execute(self, request: RunRequest):
        adapter_id = self.plugin_identity["adapter"]
        try:
            return self._adapter.execute(request)
        except ProviderExecutionError as exc:
            try:
                diagnostics = normalize_provider_failure_diagnostics(adapter_id, exc.diagnostics)
            except (OrchestratorError, ValueError):
                diagnostics = {
                    "adapter": adapter_id,
                    "failure_category": "protocol",
                    "diagnostics_omitted": True,
                }
            raise ProviderExecutionError(
                f"{adapter_id} provider execution failed; inspect sanitized provider diagnostics",
                diagnostics,
            ) from exc
        except Exception as exc:
            exception_type = type(exc).__name__
            if not _SAFE_DIAGNOSTIC_LABEL.fullmatch(exception_type):
                exception_type = "Exception"
            raise ProviderExecutionError(
                f"{adapter_id} provider execution failed; inspect sanitized provider diagnostics",
                {
                    "adapter": adapter_id,
                    "failure_category": "provider_process",
                    "exception_type": exception_type,
                },
            ) from exc

    def __getattr__(self, name: str) -> Any:
        value = getattr(self._adapter, name)
        if name in {"describe_runtime_options", "describe_usage", "role_compatibility"} and callable(value):
            def checked(*args: Any, **kwargs: Any):
                adapter_id = self.plugin_identity["adapter"]
                try:
                    report = value(*args, **kwargs)
                except Exception as exc:
                    exception_type = type(exc).__name__
                    if not _SAFE_DIAGNOSTIC_LABEL.fullmatch(exception_type):
                        exception_type = "Exception"
                    raise OrchestratorError(
                        f"{adapter_id}: provider plugin {name} failed ({exception_type})"
                    ) from exc
                if name == "role_compatibility" and not isinstance(report, dict):
                    raise OrchestratorError(
                        f"{adapter_id}: role_compatibility must return a mapping"
                    )
                return report
            return checked
        return value


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
    unknown_semantic = semantic_capabilities - set(CAPABILITIES)
    if unknown_semantic:
        raise OrchestratorError(
            f"{adapter_id}: unknown semantic capabilities: {', '.join(sorted(unknown_semantic))}"
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
        same_id = [item for item in candidates if item.adapter == adapter_id]
        exact = [
            item for item in same_id
            if item.distribution == canonical_distribution_name(pin.distribution)
            and item.version == pin.version
            and item.entry_point == pin.entry_point
        ]
        if len(same_id) > 1:
            metadata_status = "duplicate_adapter_id"
        elif len(exact) == 1:
            metadata_status = "exact_match"
        else:
            metadata_status = "missing_or_mismatched"
        status = "ready" if metadata_status == "exact_match" else metadata_status
        if adapter_id in diagnostics:
            status = str(diagnostics[adapter_id].get("status", status))
        configured[adapter_id] = {
            "pin": pin.model_dump(),
            "metadata_status": metadata_status,
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
            # A configured external pin with a built-in ID is ambiguous
            # authority. Remove that ID from the effective registry so normal
            # provider resolution cannot silently continue with the built-in.
            registry.pop(adapter_id, None)
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

        same_id = [item for item in candidates if item.adapter == adapter_id]
        if len(same_id) > 1:
            diagnostics[adapter_id] = {
                **base,
                "ok": False,
                "status": "duplicate_adapter_id",
                "error": "multiple installed provider entry points advertise the same adapter ID",
            }
            continue
        matches = [
            item for item in same_id
            if item.distribution == canonical_distribution_name(pin.distribution)
            and item.version == pin.version
            and item.entry_point == pin.entry_point
        ]
        if len(matches) != 1:
            diagnostics[adapter_id] = {
                **base,
                "ok": False,
                "status": "missing_or_mismatched",
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
    "PROVIDER_FAILURE_CATEGORIES",
    "PROVIDER_PLUGIN_ENTRYPOINT_GROUP",
    "PROVIDER_SDK_VERSION",
    "ProviderAdapter",
    "ProviderConfig",
    "ProviderExecutionError",
    "RunRequest",
    "RuntimeOptionsDescriptor",
    "UsageDescriptor",
    "assert_provider_adapter_conforms",
    "normalize_provider_failure_diagnostics",
    "canonical_distribution_name",
    "inspect_provider_plugins",
    "load_provider_registry",
]
