"""Mutations test the checker, independently of generated snapshot equality."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from ai_orchestrator.contract_inventory import _cli_commands, schema_semantics
from ai_orchestrator.cli import parser
from ai_orchestrator.project import digest


@pytest.mark.parametrize('name', ['description', 'title', '$comment'])
def test_named_properties_are_not_annotations(name):
    left = {'type':'object','properties':{name:{'type':'string'}},'required':[name]}
    right = copy.deepcopy(left); right['properties'][name]['type']='integer'
    assert Draft202012Validator(left).is_valid({name:'no'})
    assert not Draft202012Validator(right).is_valid({name:'no'})
    assert digest(schema_semantics(left)) != digest(schema_semantics(right))


@pytest.mark.parametrize('keyword', ['$defs','definitions','properties','patternProperties','dependentSchemas','dependencies'])
def test_named_schema_maps_preserve_reserved_names(keyword):
    left = {keyword:{'description':{'type':'string'}}}
    right = {keyword:{'description':{'type':'integer'}}}
    assert schema_semantics(left) != schema_semantics(right)


@pytest.mark.parametrize('keyword', ['const','enum','default','examples','x-extension'])
def test_literal_and_unknown_vocabulary_preserved(keyword):
    a,b = {'description':'no','title':'keep','$comment':{'type':'object'}}, {'description':'yes','title':'keep','$comment':{'type':'object'}}
    left = {keyword: [a] if keyword in ('enum','examples') else a}
    right = {keyword: [b] if keyword in ('enum','examples') else b}
    assert schema_semantics(left) != schema_semantics(right)
    assert schema_semantics(left) == left


@pytest.mark.parametrize('keyword', ['items','not','if','then','else','contains','additionalProperties','propertyNames','unevaluatedProperties','unevaluatedItems','contentSchema'])
def test_actual_schema_annotation_changes_are_ignored(keyword):
    assert schema_semantics({keyword:{'type':'string','title':'a'}}) == schema_semantics({keyword:{'type':'string','title':'b'}})


def test_annotations_arrays_numbers_and_known_pydantic_equivalence():
    assert schema_semantics({'allOf':[{'title':'a','type':'object'}]}) == schema_semantics({'allOf':[{'description':'b','type':'object','additionalProperties':True}]})
    assert schema_semantics({'default':1.0}) == schema_semantics({'default':1})
    assert digest(schema_semantics({'default':True})) != digest(schema_semantics({'default':1}))
    assert schema_semantics({'dependencies':{'title':['description']}}) == {'dependencies':{'title':['description']}}
    assert schema_semantics({'items':[True,False]}) == {'items':[True,False]}
    for bad in (float('nan'),float('inf')):
        with pytest.raises(ValueError): schema_semantics({'default':bad})


def subcommand(p, name):
    return next(a for a in p._actions if isinstance(a,argparse._SubParsersAction)).choices[name]


def action(p, flag):
    return next(a for a in p._actions if flag in a.option_strings)


@pytest.mark.parametrize('mutation', ['default','type','const','global','exclusion','parent-default','action','alias','arity','choices','position','parse-abbreviation','version'])
def test_complete_cli_mutations_are_detected(mutation):
    left,right=parser(),parser(); node=subcommand(right,'serve')
    if mutation=='default': node.set_defaults(single_terminal=False)
    elif mutation=='type': action(node,'--gate-timeout').type=str
    elif mutation=='const': action(node,'--single-terminal').const=False
    elif mutation=='global': action(right,'--project').required=True
    elif mutation=='exclusion': node._mutually_exclusive_groups.clear()
    elif mutation=='parent-default': right.set_defaults(extra='value')
    elif mutation=='action': action(node,'--single-terminal').__class__=argparse._StoreFalseAction
    elif mutation=='alias': action(node,'--gate-timeout').option_strings.append('--other-timeout')
    elif mutation=='arity': action(node,'--gate-timeout').nargs='?'
    elif mutation=='choices': action(node,'--gate-timeout').choices=[1,2]
    elif mutation=='position': node._actions.reverse()
    elif mutation=='parse-abbreviation': right.allow_abbrev=False
    else: action(right,'--version').version='misreported-version'
    assert _cli_commands(left) != _cli_commands(right)


def test_cli_cwd_is_symbolic_without_hiding_literal_default_mutation(tmp_path,monkeypatch):
    before=_cli_commands(parser()); monkeypatch.chdir(tmp_path)
    assert _cli_commands(parser())==before
    p=parser(); action(p,'--project').default=Path('/explicit-other-project')
    assert _cli_commands(p)!=before
    assert str(tmp_path) not in json.dumps(before)


def test_path_callable_uses_public_identity_across_supported_python():
    from ai_orchestrator.contract_inventory import _symbol
    assert _symbol(Path)=="pathlib.Path"
    assert _symbol(str)=="builtins.str"
    assert _symbol(Path)!=_symbol(str)
