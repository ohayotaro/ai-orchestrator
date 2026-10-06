"""Machine-readable candidate surface. Descriptive prose/private helpers are not frozen."""
from __future__ import annotations
import argparse
import importlib
import inspect
import json
from pathlib import Path
from .models import Contract
from .project import digest

ASSET = Path(__file__).resolve().parent/'assets/contracts.json'


def schema_semantics(value):
    """Canonical JSON-Schema semantics across supported Pydantic releases.

    Presentation fields are excluded. Pydantic 2.10 omitted
    ``additionalProperties: true`` for unconstrained mappings while later
    releases emit it explicitly; JSON Schema defines those forms identically.
    JSON numeric values also treat integral floats and integers equivalently.
    Defaults and actual validation constraints remain part of the contract.
    """
    if isinstance(value, dict):
        result = {
            k: schema_semantics(v)
            for k, v in value.items()
            if k not in ('title', 'description', '$comment')
        }
        if (
            result.get('type') == 'object'
            and 'additionalProperties' not in result
            and 'properties' not in result
            and '$ref' not in result
            and not any(key in result for key in ('allOf', 'anyOf', 'oneOf'))
        ):
            result['additionalProperties'] = True
        return result
    if isinstance(value, list):
        return [schema_semantics(v) for v in value]
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _cli_authority(command: str) -> str:
    if command in ('identity','contracts','status','events','intake','job','gate','persistence','capabilities','provider-plugins',
                   'exploration','explorations','maintenance inspect','retention','backup inspect','learning report','learning context',
                   'proposal','workflow','workflows','workflow-candidate'):
        return 'read-only diagnosis; no authority granted'
    if command == 'cancel':
        return 'cooperative intent; --finalize is exact-scope operator-only terminalization'
    if command in ('maintenance reconcile','restore','cleanup','trust','promote','workflow-save','validator add'):
        return 'operator-only explicit authority/maintenance change'
    if command in ('approve','accept','start'):
        return 'explicit operator approval; never an agent fallback for a refused HumanGate'
    if command in ('doctor','validator check'):
        return 'doctor inspects/probes; validator check explicitly executes trusted validation'
    return 'bounded operator command; not a HumanGate response'


def _cli_commands(parser, prefix=''):
    results=[]
    sub=next((a for a in parser._actions if isinstance(a,argparse._SubParsersAction)),None)
    if sub:
        for name,child in sorted(sub.choices.items()):
            results.extend(_cli_commands(child, (prefix+' '+name).strip()))
    else:
        options=[]
        for action in parser._actions:
            if action.dest=='help': continue
            options.append({'dest':action.dest,'flags':action.option_strings,'required':action.required,
                            'nargs':action.nargs, 'choices':list(action.choices) if action.choices is not None else None})
        results.append({'name':prefix,'arguments':options,'stability':'candidate',
                        'authority':_cli_authority(prefix),
                        'negative_tests':['tests/test_v017_contracts.py','tests/test_v017_hardening.py']})
    return results


def generate() -> dict:
    from .service import TOOLS
    from .human_gates import GATE_TOOLS
    from .cli import parser
    from .persistence import persistence_compatibility_report
    models=[]
    for name in ('models','contracts','exploration','jobs','human_gates','runtime_options',
                 'provider_sdk','capabilities','usage','service','cancellation','receipts','maintenance'):
        module=importlib.import_module('ai_orchestrator.'+name)
        for cname,cls in inspect.getmembers(module,inspect.isclass):
            if cls.__module__!=module.__name__ or not issubclass(cls,Contract) or cls is Contract or cname.startswith('_'):
                continue
            schema=cls.model_json_schema()
            version=schema.get('properties',{}).get('schema_version',{})
            models.append({'name':name+'.'+cname,'version_schema':schema_semantics(version),
                           'schema_sha256':digest(schema_semantics(schema)),
                           'public_entry_point':'schema/MCP or typed persisted reader',
                           'authority':'typed data; not an approval response',
                           'compatibility':'supported versions read without historical hash rewriting',
                           'stability':'candidate', 'negative_tests':['tests/test_v017_contracts.py','tests/test_v012_persistence.py']})
    tools=[]
    for name,(model,description,readonly) in sorted({**TOOLS,**GATE_TOOLS}.items()):
        tools.append({'name':name, 'schema_sha256':digest(schema_semantics(model.model_json_schema())),
                      'readonly':readonly, 'authority':'client-mediated HumanGate only' if name in GATE_TOOLS else
                      'read-only' if readonly else 'bounded request, not permission',
                      'stability':'candidate','negative_tests':['tests/test_v04_protocol.py','tests/test_v016_wire.py','tests/test_v017_contracts.py']})
    return {'schema_version':1,'candidate_version':'0.17.0','v1_release_declared':False,
            'models':sorted(models,key=lambda v:v['name']), 'mcp_tools':tools,
            'cli_commands':_cli_commands(parser()), 'persistence':persistence_compatibility_report(),
            'human_gate_decision':{'type':'string','required':True,'enum':['no','yes'],'server_supplied_default':False},
            'intentionally_unstable':['display prose','private Python helpers','bounded selection/distillation heuristics'],
            'safety_compatibility':'unstable internals cannot silently change authority, persisted hashes or replay behavior'}


def report() -> dict:
    value=json.loads(ASSET.read_text(encoding='utf-8'))
    return {**value, 'inventory_digest':digest(value)}


if __name__=='__main__':
    print(json.dumps(generate(),ensure_ascii=False,sort_keys=True,indent=2))
