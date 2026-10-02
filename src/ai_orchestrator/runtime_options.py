"""Provider-local runtime option metadata and deterministic Model Variant Resolution."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, StrictBool, field_validator, model_validator

from .capabilities import ProviderResolution
from .models import Contract, OrchestratorError, ProviderConfig, identifier


RUNTIME_OPTION_REGISTRY_VERSION = 1
RuntimeSelectionMode = Literal["unsupported", "enumerated", "passthrough"]
RuntimeResolutionSource = Literal["explicit_override", "trusted_profile", "adapter_default"]


def _runtime_value(value: str) -> str:
    if not value or value != value.strip() or len(value) > 256:
        raise ValueError("runtime option values must be nonempty, trimmed, and at most 256 characters")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("runtime option values must not contain control characters")
    return value


class RuntimeValueDescriptor(Contract):
    schema_version: Literal[1] = 1
    mode: RuntimeSelectionMode
    values: list[str] = Field(default_factory=list)
    default: str | None = None
    complete: StrictBool = False
    source: Literal["adapter_contract", "runtime_probe", "operator_config"] = "adapter_contract"
    limitations: list[str] = Field(default_factory=list)

    @field_validator("values")
    @classmethod
    def valid_values(cls, values: list[str]) -> list[str]:
        normalized = [_runtime_value(value) for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("runtime option values must not contain duplicates")
        return normalized

    @field_validator("default")
    @classmethod
    def valid_default(cls, value: str | None) -> str | None:
        return _runtime_value(value) if value is not None else None

    @model_validator(mode="after")
    def coherent_domain(self) -> "RuntimeValueDescriptor":
        if self.mode == "unsupported":
            if self.values or self.default is not None or self.complete:
                raise ValueError("unsupported runtime options cannot advertise values/defaults")
        elif self.mode == "enumerated":
            if not self.values or not self.complete:
                raise ValueError("enumerated runtime options require a complete nonempty value catalog")
            if self.default is not None and self.default not in self.values:
                raise ValueError("enumerated runtime-option default must be present in values")
        elif self.complete:
            raise ValueError("passthrough runtime options cannot claim a complete catalog")
        return self


class RuntimeOptionsDescriptor(Contract):
    schema_version: Literal[1] = 1
    registry_version: Literal[1] = RUNTIME_OPTION_REGISTRY_VERSION
    model: RuntimeValueDescriptor
    effort: RuntimeValueDescriptor
    options: dict[str, RuntimeValueDescriptor] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)

    @field_validator("options")
    @classmethod
    def valid_option_names(cls, values: dict[str, RuntimeValueDescriptor]) -> dict[str, RuntimeValueDescriptor]:
        for key in values:
            identifier(key)
        return values


class RuntimeOverride(Contract):
    """Ephemeral runtime intent. v0.9.0 exposes the resolver contract; authority UX follows in v0.9.1."""

    model: str | None = None
    effort: str | None = None
    options: dict[str, str] = Field(default_factory=dict)

    @field_validator("model", "effort")
    @classmethod
    def valid_primary_values(cls, value: str | None) -> str | None:
        return _runtime_value(value) if value is not None else None

    @field_validator("options")
    @classmethod
    def valid_options(cls, values: dict[str, str]) -> dict[str, str]:
        return {identifier(key): _runtime_value(value) for key, value in values.items()}


class ModelVariantResolution(Contract):
    schema_version: Literal[1] = 1
    provider: str
    adapter: str
    model: str | None = None
    effort: str | None = None
    options: dict[str, str] = Field(default_factory=dict)
    sources: dict[str, RuntimeResolutionSource]
    runtime_options_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    runtime_registry_version: Literal[1] = RUNTIME_OPTION_REGISTRY_VERSION
    limitations: list[str] = Field(default_factory=list)
    fallback: Literal["none"] = "none"

    @field_validator("provider", "adapter")
    @classmethod
    def valid_ids(cls, value: str) -> str:
        return identifier(value)


def _descriptor_digest(descriptor: RuntimeOptionsDescriptor) -> str:
    payload = json.dumps(
        descriptor.model_dump(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def unavailable_runtime_options() -> RuntimeOptionsDescriptor:
    limitation = (
        "adapter does not implement versioned runtime-option metadata; model/effort overrides are unavailable"
    )
    return RuntimeOptionsDescriptor(
        model=RuntimeValueDescriptor(mode="unsupported", limitations=[limitation]),
        effort=RuntimeValueDescriptor(mode="unsupported", limitations=[limitation]),
        limitations=[limitation],
    )


class ModelVariantResolver:
    """Resolve provider-local execution settings only after Provider Resolution."""

    def describe(
        self,
        adapter: Any,
        config: ProviderConfig,
        workspace: Path,
    ) -> RuntimeOptionsDescriptor:
        describe = getattr(adapter, "describe_runtime_options", None)
        if describe is None:
            return unavailable_runtime_options()
        raw = describe(config, workspace)
        if isinstance(raw, RuntimeOptionsDescriptor):
            return raw
        if isinstance(raw, Contract):
            raw = raw.model_dump()
        return RuntimeOptionsDescriptor.model_validate(raw)

    @staticmethod
    def _validate_selected(kind: str, value: str | None, domain: RuntimeValueDescriptor) -> str | None:
        if value is None:
            return None
        value = _runtime_value(value)
        if domain.mode == "unsupported":
            raise OrchestratorError(f"adapter does not support explicit {kind} selection")
        if domain.mode == "enumerated" and value not in domain.values:
            raise OrchestratorError(
                f"unsupported {kind} value: {value}; supported values: {', '.join(domain.values)}"
            )
        return value

    @staticmethod
    def _select(
        kind: str,
        override: str | None,
        profile_value: str | None,
        domain: RuntimeValueDescriptor,
    ) -> tuple[str | None, RuntimeResolutionSource]:
        if override is not None:
            return ModelVariantResolver._validate_selected(kind, override, domain), "explicit_override"
        if profile_value is not None:
            return ModelVariantResolver._validate_selected(kind, profile_value, domain), "trusted_profile"
        return ModelVariantResolver._validate_selected(kind, domain.default, domain), "adapter_default"

    def resolve(
        self,
        provider: ProviderResolution,
        config: ProviderConfig,
        adapter: Any,
        workspace: Path,
        *,
        override: RuntimeOverride | None = None,
    ) -> ModelVariantResolution:
        descriptor = self.describe(adapter, config, workspace)
        override = override or RuntimeOverride()
        model, model_source = self._select("model", override.model, config.model, descriptor.model)
        effort, effort_source = self._select("effort", override.effort, config.effort, descriptor.effort)

        options: dict[str, str] = {}
        sources: dict[str, RuntimeResolutionSource] = {
            "model": model_source,
            "effort": effort_source,
        }
        for name, value in override.options.items():
            domain = descriptor.options.get(name)
            if domain is None:
                raise OrchestratorError(f"adapter does not advertise runtime option: {name}")
            selected = self._validate_selected(name, value, domain)
            if selected is not None:
                options[name] = selected
                sources[f"option:{name}"] = "explicit_override"
        for name, domain in descriptor.options.items():
            if name in options:
                continue
            selected = self._validate_selected(name, domain.default, domain)
            if selected is not None:
                options[name] = selected
                sources[f"option:{name}"] = "adapter_default"

        limitations = list(dict.fromkeys([
            *descriptor.limitations,
            *descriptor.model.limitations,
            *descriptor.effort.limitations,
            *(item for domain in descriptor.options.values() for item in domain.limitations),
        ]))
        return ModelVariantResolution(
            provider=provider.provider,
            adapter=provider.adapter,
            model=model,
            effort=effort,
            options=options,
            sources=sources,
            runtime_options_digest=_descriptor_digest(descriptor),
            limitations=limitations,
        )

    def validate_frozen(
        self,
        frozen: dict[str, object],
        provider: ProviderResolution,
        config: ProviderConfig,
        adapter: Any,
        workspace: Path,
        *,
        override: RuntimeOverride | None = None,
    ) -> ModelVariantResolution:
        current = self.resolve(provider, config, adapter, workspace, override=override)
        saved = ModelVariantResolution.model_validate(frozen)
        if saved.model_dump() != current.model_dump():
            raise OrchestratorError(
                "model/effort/runtime-option resolution changed since task binding; create a new task"
            )
        return saved


def execution_identities_independent(
    first_provider: ProviderResolution,
    first_variant: ModelVariantResolution,
    second_provider: ProviderResolution,
    second_variant: ModelVariantResolution,
) -> bool:
    """Review independence: distinct family, or a provably distinct model in one family.

    Effort alone is not an independent identity. When both providers are in the
    same family, both model IDs must be explicit and unequal. Provider-local
    aliases are compared literally because the kernel must not invent vendor
    model equivalence.
    """
    if first_provider.family != second_provider.family:
        return True
    return bool(
        first_variant.model
        and second_variant.model
        and first_variant.model != second_variant.model
    )


def config_for_variant(config: ProviderConfig, resolution: ModelVariantResolution) -> ProviderConfig:
    return config.model_copy(update={"model": resolution.model, "effort": resolution.effort})
