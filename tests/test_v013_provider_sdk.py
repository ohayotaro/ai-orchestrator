from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
import sys

import pytest
import yaml

from ai_orchestrator.engine import Engine
from ai_orchestrator.models import OrchestratorError, ProviderConfig
from ai_orchestrator.provider_sdk import (
    PROVIDER_FAILURE_CATEGORIES,
    PROVIDER_PLUGIN_ENTRYPOINT_GROUP,
    PROVIDER_SDK_VERSION,
    LoadedPluginAdapter,
    ProviderExecutionError,
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


def test_real_dist_info_entry_point_loads_only_after_profile_trust(workspace, tmp_path, monkeypatch):
    site = tmp_path / "site"
    site.mkdir()
    module_name = "v013_external_fixture"
    (site / f"{module_name}.py").write_text(
        """
class Adapter:
    provider_sdk_version = 1
    api_version = 2
    family = "fixture"
    capabilities = frozenset({"read_files", "write_files", "fresh_session", "structured_output"})
    semantic_capabilities = frozenset({"repository_analysis", "planning", "code_edit", "test_authoring", "review", "supervision"})

    def doctor(self, config, workspace):
        return {"version": "real-dist-fixture", "family": self.family}

    def execute(self, request):
        raise AssertionError("real distribution fixture must not dispatch")
""".lstrip()
    )
    dist_info = site / "fixture_provider-1.2.3.dist-info"
    dist_info.mkdir()
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: Fixture_Provider\nVersion: 1.2.3\n"
    )
    (dist_info / "entry_points.txt").write_text(
        f"[{PROVIDER_PLUGIN_ENTRYPOINT_GROUP}]\nfixture-real = {module_name}:Adapter\n"
    )
    monkeypatch.syspath_prepend(str(site))
    distributions = list(metadata.distributions(path=[str(site)]))
    assert len(distributions) == 1
    monkeypatch.setattr(
        "ai_orchestrator.provider_sdk.metadata.distributions",
        lambda: distributions,
    )

    path = workspace / ".orchestrator/config.yaml"
    data = yaml.safe_load(path.read_text())
    data["provider_plugins"] = {
        "fixture-real": {
            "schema_version": 1,
            "distribution": "fixture-provider",
            "version": "1.2.3",
            "entry_point": f"{module_name}:Adapter",
        }
    }
    data["providers"]["engineering"]["adapter"] = "fixture-real"
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    sys.modules.pop(module_name, None)
    first = Engine(workspace)
    try:
        assert module_name not in sys.modules
        first.trust("operator")
        assert module_name not in sys.modules
    finally:
        first.close()

    second = Engine(workspace)
    try:
        assert module_name in sys.modules
        assert "fixture-real" in second.registry
        resolution = second.capability_resolver.resolve("implementer")
        assert resolution.plugin_identity == {
            "adapter": "fixture-real",
            "distribution": "fixture-provider",
            "version": "1.2.3",
            "entry_point": f"{module_name}:Adapter",
            "provider_sdk_version": "1",
            "adapter_api_version": "2",
        }
    finally:
        second.close()
        sys.modules.pop(module_name, None)


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


def test_duplicate_external_adapter_ids_fail_closed_even_with_exact_pin(workspace, monkeypatch):
    first = FakeEntryPoint()
    second = FakeEntryPoint()
    second.value = "another_fixture.adapter:Adapter"
    monkeypatch.setattr(
        "ai_orchestrator.provider_sdk.metadata.distributions",
        lambda: [
            distribution(first),
            FakeDistribution(
                version="9.9.9",
                entry_points=[second],
                metadata={"Name": "Another_Provider"},
            ),
        ],
    )
    pin_fixture(workspace)

    engine = Engine(workspace)
    try:
        engine.trust("operator")
    finally:
        engine.close()

    engine = Engine(workspace)
    try:
        assert "fixture" not in engine.registry
        report = engine.provider_plugin_report()["configured"]["fixture"]
        assert report["metadata_status"] == "duplicate_adapter_id"
        assert report["load_status"] == "duplicate_adapter_id"
        with pytest.raises(OrchestratorError, match="adapter is not installed"):
            engine.capability_resolver.resolve("implementer")
    finally:
        engine.close()


def test_builtin_id_collision_removes_ambiguous_adapter_from_active_registry(workspace, monkeypatch):
    class CodexEntryPoint(FakeEntryPoint):
        name = "codex"
        value = "external_fixture.adapter:ExternalCodexAdapter"

    entry_point = CodexEntryPoint()
    monkeypatch.setattr(
        "ai_orchestrator.provider_sdk.metadata.distributions",
        lambda: [FakeDistribution(
            version="1.2.3",
            entry_points=[entry_point],
            metadata={"Name": "Fixture_Provider"},
        )],
    )
    path = workspace / ".orchestrator/config.yaml"
    data = yaml.safe_load(path.read_text())
    data["provider_plugins"] = {
        "codex": {
            "schema_version": 1,
            "distribution": "fixture-provider",
            "version": "1.2.3",
            "entry_point": entry_point.value,
        }
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    engine = Engine(workspace)
    try:
        assert "codex" not in engine.registry
        engine.trust("operator")
    finally:
        engine.close()

    engine = Engine(workspace)
    try:
        assert "codex" not in engine.registry
        report = engine.provider_plugin_report()["configured"]["codex"]
        assert report["load_status"] == "builtin_collision"
        with pytest.raises(OrchestratorError, match="adapter is not installed"):
            engine.capability_resolver.resolve("implementer")
    finally:
        engine.close()


def test_external_provider_failure_diagnostics_are_bounded_and_content_free():
    class UnsafeFailureAdapter(ExternalFixtureAdapter):
        def execute(self, request):
            raise ProviderExecutionError(
                "raw provider output secret-token-123",
                {
                    "failure_category": "protocol",
                    "detail": "raw provider output secret-token-123",
                },
            )

    wrapper = LoadedPluginAdapter(
        UnsafeFailureAdapter(),
        {
            "adapter": "fixture",
            "distribution": "fixture-provider",
            "version": "1.2.3",
            "entry_point": "fixture:Adapter",
            "provider_sdk_version": "1",
            "adapter_api_version": "2",
        },
    )
    with pytest.raises(ProviderExecutionError) as caught:
        wrapper.execute(None)
    assert "secret-token" not in str(caught.value)
    assert caught.value.diagnostics == {
        "adapter": "fixture",
        "failure_category": "protocol",
        "diagnostics_omitted": True,
    }


def test_external_provider_probe_exception_text_is_not_exposed(tmp_path):
    class UnsafeDoctorAdapter(ExternalFixtureAdapter):
        def doctor(self, config, workspace):
            raise RuntimeError("credential=secret-token-123")

    wrapper = LoadedPluginAdapter(
        UnsafeDoctorAdapter(),
        {
            "adapter": "fixture",
            "distribution": "fixture-provider",
            "version": "1.2.3",
            "entry_point": "fixture:Adapter",
            "provider_sdk_version": "1",
            "adapter_api_version": "2",
        },
    )
    with pytest.raises(OrchestratorError) as caught:
        wrapper.doctor(ProviderConfig(adapter="fixture"), tmp_path)
    assert "secret-token" not in str(caught.value)
    assert "RuntimeError" in str(caught.value)


def test_external_provider_failure_categories_are_public_and_normalized():
    assert PROVIDER_FAILURE_CATEGORIES == {
        "authentication",
        "quota",
        "permission",
        "configuration",
        "protocol",
        "provider_process",
    }


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
