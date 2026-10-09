"""Real SDK loader with synthetic metadata: no Devin process or actual approval."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

from ai_orchestrator.engine import Engine
from ai_orchestrator.models import OrchestratorError


@dataclass
class FakeDistribution:
    version: str
    entry_points: list
    metadata: dict[str, str]


class EntryPoint:
    group = 'ai_orchestrator.providers'
    name = 'devin'
    value = 'ai_orchestrator_provider_devin:Adapter'

    def __init__(self, adapter_class):
        self.adapter_class = adapter_class
        self.loads = 0

    def load(self):
        self.loads += 1
        return self.adapter_class


def test_devin_plugin_pin_trust_and_capability_fail_closed(workspace, monkeypatch):
    src = Path(__file__).parents[1]/'integrations'/'devin_provider'/'src'
    monkeypatch.syspath_prepend(str(src))
    from ai_orchestrator_provider_devin import Adapter

    ep = EntryPoint(Adapter)
    version = {'value': '0.1.0'}
    monkeypatch.setattr('ai_orchestrator.provider_sdk.metadata.distributions',
                        lambda: [FakeDistribution(version['value'], [ep], {'Name': 'ai-orchestrator-provider-devin'})])

    config = workspace/'.orchestrator'/'config.yaml'
    profile = yaml.safe_load(config.read_text())
    profile['provider_plugins'] = {
        'devin': {'schema_version': 1,
                  'distribution': 'ai-orchestrator-provider-devin',
                  'version': '0.1.0',
                  'entry_point': ep.value}
    }
    profile['providers']['engineering']['adapter'] = 'devin'
    config.write_text(yaml.safe_dump(profile, sort_keys=False))

    engine = Engine(workspace)
    try:
        assert 'devin' not in engine.registry
        assert engine.provider_plugin_report()['configured']['devin']['load_status'] == 'profile_untrusted'
        assert ep.loads == 0
        engine.trust('operator')
    finally:
        engine.close()

    engine = Engine(workspace)
    try:
        assert ep.loads == 1
        assert 'devin' in engine.registry
        assert engine.provider_plugin_report()['configured']['devin']['load_status'] == 'loaded'
        with pytest.raises(OrchestratorError):
            engine.capability_resolver.resolve('implementer')
    finally:
        engine.close()

    version['value'] = '0.1.1'
    engine = Engine(workspace)
    try:
        assert 'devin' not in engine.registry
        assert engine.provider_plugin_report()['configured']['devin']['load_status'] == 'missing_or_mismatched'
    finally:
        engine.close()
