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


CANONICALIZER_VERSION = "json-schema-positions-v2"

# Only these keywords contain schemas. Unknown vocabularies and instance values
# are copied as JSON, never recursively interpreted as annotation positions.
_SCHEMA_MAPS = frozenset({"properties", "patternProperties", "$defs", "definitions", "dependentSchemas"})
_SCHEMA_SINGLE = frozenset({"additionalProperties", "unevaluatedProperties", "propertyNames", "contains",
                            "additionalItems", "unevaluatedItems", "not", "if", "then", "else", "contentSchema"})
_SCHEMA_ARRAYS = frozenset({"allOf", "anyOf", "oneOf", "prefixItems"})
_PRESENTATION = frozenset({"title", "description", "$comment"})


def _json_value(value):
    """Copy literal JSON, preserving named keys; normalize finite JSON numbers."""
    import math
    if isinstance(value, dict):
        if not all(isinstance(k, str) for k in value):
            raise ValueError("contract JSON keys must be strings")
        return {k: _json_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_value(v) for v in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite contract number")
        return int(value) if value.is_integer() else value
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise ValueError("unsupported contract JSON value")


def schema_semantics(value):
    """Position-aware, conservative canonicalization; NOT an equivalence prover.

    Only actual schema annotations are removed. Named-schema maps preserve all
    names and const/enum/default/unknown extension data remain literal JSON.
    The two known Pydantic mapping/number representation differences retain the
    historical minimum/reference equivalence. This function never participates
    in task, artifact, profile or authority hashing.
    """
    if isinstance(value, bool):
        return value
    if not isinstance(value, dict):
        raise ValueError("expected a JSON Schema object or boolean")
    result = {}
    for key, item in value.items():
        if key in _PRESENTATION:
            if not isinstance(item, str):
                raise ValueError("schema annotation must be a string")
            continue
        if key in _SCHEMA_MAPS:
            if not isinstance(item, dict):
                raise ValueError("named schemas must be an object")
            result[key] = {name: schema_semantics(child) for name, child in item.items()}
        elif key in _SCHEMA_SINGLE:
            result[key] = schema_semantics(item)
        elif key in _SCHEMA_ARRAYS or (key == "items" and isinstance(item, list)):
            if not isinstance(item, list):
                raise ValueError("schema applicator must be an array")
            result[key] = [schema_semantics(child) for child in item]
        elif key == "items":
            result[key] = schema_semantics(item)
        elif key == "dependencies":  # draft-07: schema or a list of names
            if not isinstance(item, dict):
                raise ValueError("dependencies must be an object")
            result[key] = {name: _json_value(child) if isinstance(child, list)
                           else schema_semantics(child) for name, child in item.items()}
        else:
            result[key] = _json_value(item)
    if (result.get("type") == "object" and "additionalProperties" not in result
            and "properties" not in result and "$ref" not in result
            and not any(k in result for k in ("allOf", "anyOf", "oneOf"))):
        result["additionalProperties"] = True
    return result


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


def _symbol(value):
    """Stable callable/type identity; never include repr addresses or local paths."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    # Path moved to pathlib._local in Python 3.13; its public callable contract
    # is still pathlib.Path. Do not fingerprint that private module move.
    if value is Path:
        return "pathlib.Path"
    module = getattr(value, "__module__", None)
    name = getattr(value, "__qualname__", None)
    if module and name and "<lambda>" not in name and "<locals>" not in name:
        return module + "." + name
    raise ValueError("CLI/SDK callable needs an explicit stable identity")


def _cli_value(value, *, path='', dest='', version=False):
    from . import __version__
    if path == '' and dest == 'project' and isinstance(value, Path) and value == Path.cwd():
        return {"factory": "current_working_directory"}
    if version and value == __version__:
        return {"source": "package_version"}
    if value is argparse.SUPPRESS:
        return {"special": "argparse.SUPPRESS"}
    if isinstance(value, Path):
        return {"path_literal": value.as_posix()}
    return _json_value(value)


def _cli_node(parser, path):
    options = []
    for index, action in enumerate(parser._actions):
        # Help prose/wrapping are not API; the help action/exit behavior is.
        if isinstance(action, argparse._SubParsersAction):
            options.append({"action": "subcommands", "dest": action.dest,
                            "required": action.required, "names": sorted(action.choices)})
            continue
        options.append({
            "position": index, "dest": action.dest, "flags": list(action.option_strings),
            "required": action.required, "nargs": action.nargs,
            "choices": _json_value(list(action.choices)) if action.choices is not None else None,
            "action": _symbol(type(action)), "type": _symbol(action.type),
            "default": _cli_value(action.default, path=path, dest=action.dest),
            "const": _cli_value(action.const),
            **({"version": _cli_value(action.version, version=True)} if hasattr(action, "version") else {}),
        })
    return {"path": path, "arguments": options,
            "defaults": {k: _cli_value(v, path=path, dest=k) for k,v in sorted(parser._defaults.items())},
            "mutually_exclusive": [
                {"required": group.required,
                 "members": [parser._actions.index(a) for a in group._group_actions]}
                for group in parser._mutually_exclusive_groups],
            "parsing": {"allow_abbrev": parser.allow_abbrev, "prefix_chars": parser.prefix_chars,
                        "fromfile_prefix_chars": parser.fromfile_prefix_chars,
                        "argument_default": _cli_value(parser.argument_default),
                        "conflict_handler": parser.conflict_handler, "exit_on_error": parser.exit_on_error}}


def _cli_commands(parser, prefix='', _parents=()):
    nodes = (*_parents, _cli_node(parser, prefix))
    sub = next((a for a in parser._actions if isinstance(a, argparse._SubParsersAction)), None)
    if sub:
        return [entry for name, child in sorted(sub.choices.items())
                for entry in _cli_commands(child, (prefix+' '+name).strip(), nodes)]
    return [{"name": prefix, "parser_path": list(nodes), "stability": "v1-target",
             "authority": _cli_authority(prefix),
             "negative_tests": ["tests/test_v1_inventory.py", "tests/test_v017_hardening.py"]}]


def generate() -> dict:
    from . import __version__
    from .service import TOOLS
    from .human_gates import GATE_TOOLS
    from .cli import parser
    from .persistence import persistence_compatibility_report
    from .public_contracts import surface, resolve, output_schemas, sdk_contracts, tool_annotations
    declared = surface()
    models=[]
    for name in declared['models']:
        cls=resolve(name)
        schema=cls.model_json_schema()
        models.append({'name':name,
                       'version_schema':schema_semantics(schema.get('properties',{}).get('schema_version',{})),
                       'schema_sha256':digest(schema_semantics(schema)),
                       'stability':'v1-target-data', 'python_import_stable':False})
    outputs=output_schemas()
    tools=[]
    actual={**TOOLS, **GATE_TOOLS}
    if set(actual) != set(declared['mcp_tools']):
        raise ValueError('public MCP allowlist differs from dispatch surface')
    for name,(model,description,readonly) in sorted(actual.items()):
        rule=declared['mcp_tools'][name]
        tools.append({'name':name,'schema_sha256':digest(schema_semantics(model.model_json_schema())),
                      'readonly':readonly,'annotations':tool_annotations(name,readonly),
                      'authority':'client-mediated HumanGate only' if name in GATE_TOOLS else
                          'read-only' if readonly else 'bounded request, not permission',
                      'stability':'v1-target',**rule})
    commands=_cli_commands(parser())
    if {v['name'] for v in commands} != set(declared['cli_commands']):
        raise ValueError('public CLI allowlist differs from parser surface')
    parsers={}
    for command in commands:
        for node in command['parser_path']:
            key=node['path']
            if key in parsers and parsers[key]!=node:
                raise ValueError('conflicting CLI parser path')
            parsers[key]=node
        command['parser_path']=[node['path'] for node in command['parser_path']]
        command.update(declared['cli_commands'][command['name']])
    return {'schema_version':2,'canonicalizer':CANONICALIZER_VERSION,
            'package_version':__version__,'target_version':'1.0.0','stability':'v1-target; qualification pending',
            'models':models,'mcp_tools':tools,'cli_commands':commands,
            'cli_parsers':dict(sorted(parsers.items())),
            'output_schemas':{name:{'schema_sha256':digest(schema_semantics(schema))}
                              for name,schema in sorted(outputs.items())},
            'sdk':sdk_contracts(), 'protocols':declared['protocols'],
            'runtime_limits':declared['runtime_limits'],
            'compatibility_policy':declared['compatibility_policy'],
            'stable_extension_boundaries':declared['stable_extension_boundaries'],
            'persistence':persistence_compatibility_report(),
            'human_gate_decision':{'type':'string','required':True,'enum':['no','yes'],'server_supplied_default':False},
            'intentionally_unstable':['display prose','private Python helpers','bounded selection/distillation heuristics'],
            'safety_compatibility':'unstable internals cannot silently change authority, persisted hashes or replay behavior'}


def report() -> dict:
    value=json.loads(ASSET.read_text(encoding='utf-8'))
    return {**value, 'inventory_digest':digest(value)}


if __name__=='__main__':
    print(json.dumps(generate(),ensure_ascii=False,sort_keys=True,indent=2))
