"""Versioned semantic capability registry and deterministic provider resolution."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from .models import Contract, OrchestratorError, Profile, ProviderConfig, RoleConfig, identifier


CAPABILITY_REGISTRY_VERSION = 1
CAPABILITIES: dict[str, str] = {
    "repository_analysis": "Inspect and reason about repository-local files without external research.",
    "planning": "Produce a bounded implementation/advisory plan.",
    "code_edit": "Modify project files within the controller's write contract.",
    "test_authoring": "Design or edit tests; deterministic validators still run outside the model.",
    "review": "Independently assess acceptance criteria and controller evidence.",
    "supervision": "Translate natural-language requests into bounded task proposals.",
    "research": "Perform research beyond repository-local evidence. No built-in adapter advertises this by default.",
}
DEFAULT_ROLE_CAPABILITIES: dict[str, tuple[str, ...]] = {
    "supervisor": ("supervision", "repository_analysis"),
    "planner": ("planning", "repository_analysis"),
    "implementer": ("code_edit",),
    "reviewer": ("review", "repository_analysis"),
}


class CapabilityRegistryDescriptor(Contract):
    schema_version: Literal[1] = 1
    capabilities: dict[str, str]


class ProviderDescriptor(Contract):
    schema_version: Literal[2] = 2
    provider: str
    adapter: str
    adapter_api_version: int = Field(ge=1, strict=True)
    family: str
    capabilities: list[str]
    runtime_capabilities: list[str]
    priority: int
    capability_source: Literal["adapter", "config", "legacy_fixed_compat"]


class ProviderResolution(Contract):
    schema_version: Literal[1] = 1
    role: str
    provider: str
    adapter: str
    family: str
    source: Literal["fixed", "candidates", "priority"]
    required_capabilities: list[str]
    offered_capabilities: list[str]
    candidates_considered: list[str]
    adapter_api_version: int


def capability_registry() -> CapabilityRegistryDescriptor:
    return CapabilityRegistryDescriptor(capabilities=dict(CAPABILITIES))


def validate_requirements(requirements: dict[str, list[str]] | None) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for role, values in (requirements or {}).items():
        identifier(role)
        if role not in ("planner", "implementer", "reviewer"):
            raise OrchestratorError(f"task capability requirements are unsupported for role: {role}")
        normalized: list[str] = []
        for value in values:
            identifier(value)
            if value not in CAPABILITIES:
                raise OrchestratorError(f"unknown semantic capability: {value}")
            if value not in normalized:
                normalized.append(value)
        result[role] = normalized
    return result


class CapabilityResolver:
    def __init__(self, profile: Profile, adapters: dict[str, Any]):
        self.profile = profile
        self.adapters = adapters

    def role_config(self, role: str) -> RoleConfig:
        binding = self.profile.roles.get(role)
        if binding is None and role == "supervisor":
            binding = self.profile.roles["planner"]
        if binding is None:
            raise OrchestratorError(f"role is not configured: {role}")
        return binding

    def required(self, role: str, extra: list[str] | None = None) -> list[str]:
        binding = self.role_config(role)
        ordered = [*DEFAULT_ROLE_CAPABILITIES.get(role, ()), *binding.capabilities, *(extra or [])]
        result: list[str] = []
        for value in ordered:
            identifier(value)
            if value not in CAPABILITIES:
                raise OrchestratorError(f"{role}: unknown semantic capability: {value}")
            if value not in result:
                result.append(value)
        return result

    def runtime_required(self, role: str) -> set[str]:
        binding = self.role_config(role)
        if role != "implementer" and "write_files" in binding.requires:
            raise OrchestratorError(f"{role}: read-only phases cannot require write_files")
        required = {"fresh_session", "structured_output", "read_files", *binding.requires}
        if role == "implementer":
            required.add("write_files")
        return required

    def describe_provider(self, provider: str, *, legacy_role: str | None = None) -> ProviderDescriptor:
        if provider not in self.profile.providers:
            raise OrchestratorError(f"unknown provider: {provider}")
        config: ProviderConfig = self.profile.providers[provider]
        adapter = self.adapters.get(config.adapter)
        if adapter is None:
            raise OrchestratorError(f"adapter is not installed: {config.adapter}; no implicit fallback")
        api_version = int(getattr(adapter, "api_version", 1))
        runtime = sorted(getattr(adapter, "capabilities", frozenset()))
        advertised = set(getattr(adapter, "semantic_capabilities", frozenset()))
        if config.capabilities:
            unknown = set(config.capabilities) - set(CAPABILITIES)
            if unknown:
                raise OrchestratorError(f"{provider}: unknown configured capabilities: {', '.join(sorted(unknown))}")
            if api_version < 2:
                raise OrchestratorError(f"{provider}: explicit semantic capabilities require Provider Adapter v2")
            unsupported = set(config.capabilities) - advertised
            if unsupported:
                raise OrchestratorError(f"{provider}: adapter does not advertise configured capabilities: {', '.join(sorted(unsupported))}")
            offered = list(config.capabilities)
            source = "config"
        elif api_version >= 2:
            offered = sorted(advertised)
            source = "adapter"
        elif legacy_role is not None:
            # Compatibility only for an existing fixed binding without semantic
            # declarations. Dynamic routing never assumes capabilities for v1.
            offered = self.required(legacy_role)
            source = "legacy_fixed_compat"
        else:
            offered = []
            source = "adapter"
        family = str(getattr(adapter, "family", ""))
        if not family:
            raise OrchestratorError(f"{provider}: adapter family is required")
        return ProviderDescriptor(provider=provider, adapter=config.adapter, adapter_api_version=api_version,
                                  family=family, capabilities=offered, runtime_capabilities=runtime,
                                  priority=config.priority, capability_source=source)

    def _candidate_names(self, role: str) -> tuple[list[str], str]:
        binding = self.role_config(role)
        if binding.provider is not None:
            return [binding.provider], "fixed"
        if binding.candidates:
            return list(binding.candidates), "candidates"
        return [name for name, _ in sorted(self.profile.providers.items(), key=lambda item: (item[1].priority, item[0]))], "priority"

    def resolve(self, role: str, *, required: list[str] | None = None,
                exclude_families: set[str] | None = None, force_provider: str | None = None) -> ProviderResolution:
        required_values = self.required(role, required)
        runtime_required = self.runtime_required(role)
        names, source = self._candidate_names(role)
        if force_provider is not None:
            names, source = [force_provider], "fixed"
        considered: list[str] = []
        errors: list[str] = []
        binding = self.role_config(role)
        for name in names:
            considered.append(name)
            legacy_role = role if binding.provider == name and not binding.capabilities else None
            try:
                descriptor = self.describe_provider(name, legacy_role=legacy_role)
            except OrchestratorError as exc:
                errors.append(f"{name}: {exc}")
                continue
            if exclude_families and descriptor.family in exclude_families:
                errors.append(f"{name}: family {descriptor.family} excluded by policy")
                continue
            semantic_missing = set(required_values) - set(descriptor.capabilities)
            runtime_missing = runtime_required - set(descriptor.runtime_capabilities)
            if semantic_missing:
                errors.append(f"{name}: missing semantic capabilities {', '.join(sorted(semantic_missing))}")
                continue
            if runtime_missing:
                errors.append(f"{name}: missing runtime capabilities {', '.join(sorted(runtime_missing))}")
                continue
            return ProviderResolution(role=role, provider=name, adapter=descriptor.adapter,
                                      family=descriptor.family, source=source,
                                      required_capabilities=required_values,
                                      offered_capabilities=descriptor.capabilities,
                                      candidates_considered=considered,
                                      adapter_api_version=descriptor.adapter_api_version)
        detail = "; ".join(errors) if errors else "no candidate providers"
        raise OrchestratorError(f"{role}: no provider satisfies required capabilities: {detail}")

    def report(self) -> dict[str, Any]:
        providers: dict[str, Any] = {}
        for name in sorted(self.profile.providers):
            try:
                providers[name] = self.describe_provider(name).model_dump()
            except OrchestratorError as exc:
                providers[name] = {"provider": name, "error": str(exc)}
        return {"registry": capability_registry().model_dump(), "providers": providers}
