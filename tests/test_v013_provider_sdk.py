from __future__ import annotations

from dataclasses import dataclass

import pytest
import yaml

from ai_orchestrator.engine import Engine
from ai_orchestrator.models import OrchestratorError, ProviderConfig
from ai_orchestrator.provider_sdk import (
    PROVIDER_PLUGIN_ENTRYPOINT_GROUP,
    PROVIDER_SDK_VERSION,
    assert_provider_adapter_conforms,
)


class ExternalFixtureAdapter:
    provider_sdk_version = PROVIDER_SDK_VERSION
    api_version = 2
    family = "fixture"
    capabilities = frozenset({
        "read_files", "write_files", "fresh_session", "structured_output"
    })
    semantic_capabilities = frozenset({
        "repository_analysis", "planning", "code_edit", "test_authoring",
        "review", "supervision",
    })

    def doctor(self, config, workspace):
        return {"version": "fixture-1", "family": self.family}

    def execute(self, request):
        raise AssertionError("fixture execute is not used by SDK loading tests")


class NonConformingAdapter(ExternalFixtureAdapter):
    provider_sdk_version = 99


class FakeEntryPoint:
    group = PROVIDER_PLUGIN_ENTRYPOINT_GROUP
    name = "fixture"
    value = "external_fixture.adapter:ExternalFixtureAdapter"

    def __init__(self):
        self.loads = 0

    def load(self):
        self.loads += 1
        return ExternalFixtureAdapter


@dataclass
class FakeDistribution:
    version: str
    entry_points: list
    metadata: dict[str, str]


def distribution(entry_point: FakeEntryPoint, version: str = "1.2.3"):
    return FakeDistribution(
        version=version,
        entry_points=[entry_point],
        metadata={"Name": "Fixture_Provider"},
    )


def pin_fixture(workspace, *, version: str = "1.2.3", use_for_engineering: bool = True):
    path = workspace / ".orchestrator/config.yaml"
    data = yaml.safe_load(path.read_text())
    data["provider_plugins"] = {
        "fixture": {
            "schema_version": 1,
            "distribution": "fixture-provider",
            "version": version,
            "entry_point": FakeEntryPoint.value,
        }
    }
    if use_for_engineering:
        data["providers"]["engineering"]["adapter"] = "fixture"
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def test_external_plugin_is_metadata_only_until_exact_profile_is_trusted(workspace, monkeypatch):
    entry_point = FakeEntryPoint()
    monkeypatch.setattr(
        "ai_orchestrator.provider_sdk.metadata.distributions",
        lambda: [distribution(entry_point)],
    )
    pin_fixture(workspace)

    first = Engine(workspace)
    try:
        assert "fixture" not in first.registry
        report = first.provider_plugin_report()
        assert report["profile_trusted"] is False
        assert report["configured"]["fixture"]["load_status"] == "profile_untrusted"
        assert entry_point.loads == 0
        first.trust("operator")
        assert entry_point.loads == 0
    finally:
        first.close()

    second = Engine(workspace)
    try:
        assert entry_point.loads == 1
        assert "fixture" in second.registry
        report = second.provider_plugin_report()
        assert report["configured"]["fixture"]["load_status"] == "loaded"
        resolution = second.capability_resolver.resolve("implementer")
        assert resolution.adapter == "fixture"
        assert resolution.plugin_identity["distribution"] == "fixture-provider"
        assert resolution.plugin_identity["version"] == "1.2.3"
        assert resolution.plugin_identity["entry_point"] == FakeEntryPoint.value
    finally:
        second.close()


def test_installed_but_unpinned_plugin_never_loads(workspace, monkeypatch):
    entry_point = FakeEntryPoint()
    monkeypatch.setattr(
        "ai_orchestrator.provider_sdk.metadata.distributions",
        lambda: [distribution(entry_point)],
    )
    engine = Engine(workspace)
    try:
        engine.trust("operator")
    finally:
        engine.close()

    engine = Engine(workspace)
    try:
        assert "fixture" not in engine.registry
        assert entry_point.loads == 0
    finally:
        engine.close()


def test_package_version_drift_fails_closed_after_trust(workspace, monkeypatch):
    entry_point = FakeEntryPoint()
    versions = {"value": "1.2.3"}
    monkeypatch.setattr(
        "ai_orchestrator.provider_sdk.metadata.distributions",
        lambda: [distribution(entry_point, versions["value"])],
    )
    pin_fixture(workspace)

    engine = Engine(workspace)
    try:
        engine.trust("operator")
    finally:
        engine.close()

    versions["value"] = "1.2.4"
    engine = Engine(workspace)
    try:
        assert "fixture" not in engine.registry
        plugin = engine.provider_plugin_report()["configured"]["fixture"]
        assert plugin["load_status"] == "missing_or_mismatched"
        with pytest.raises(OrchestratorError, match="adapter is not installed"):
            engine.capability_resolver.resolve("implementer")
    finally:
        engine.close()


def test_conformance_kit_separates_required_core_from_optional_features(tmp_path):
    report = assert_provider_adapter_conforms(
        "fixture",
        ExternalFixtureAdapter(),
        config=ProviderConfig(adapter="fixture"),
        workspace=tmp_path,
    )
    assert report["provider_sdk_version"] == 1
    assert report["adapter_api_version"] == 2
    assert report["optional_features"] == {
        "runtime_options": False,
        "usage": False,
        "role_compatibility": False,
    }


def test_conformance_rejects_unsupported_sdk_version():
    with pytest.raises(OrchestratorError, match="unsupported provider SDK version"):
        assert_provider_adapter_conforms("fixture", NonConformingAdapter())


def test_empty_plugin_support_preserves_legacy_profile_shape_and_fingerprint(workspace):
    path = workspace / ".orchestrator/config.yaml"
    raw = yaml.safe_load(path.read_text())
    assert "provider_plugins" not in raw

    engine = Engine(workspace)
    try:
        baseline = engine.profile_digest
    finally:
        engine.close()

    raw["provider_plugins"] = {}
    path.write_text(yaml.safe_dump(raw, sort_keys=False))
    engine = Engine(workspace)
    try:
        assert engine.profile_digest == baseline
    finally:
        engine.close()
