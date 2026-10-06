"""Independent public response, discovery, parser, and SDK conformance checks."""
from __future__ import annotations

import copy
import dataclasses
import inspect
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from ai_orchestrator import contract_inventory as inventory
from ai_orchestrator.public_contracts import output_schemas, sdk_contracts, signature, surface
from ai_orchestrator.models import OrchestratorError
from ai_orchestrator.service import ApplicationService, TOOLS
from ai_orchestrator.human_gates import GATE_TOOLS, HumanGate, HumanGateBroker
from ai_orchestrator.cli import parser, main
from ai_orchestrator.mcp_server import StdioServer, PROTOCOLS, MAX_MESSAGE_BYTES
from ai_orchestrator.jobs import MAX_PENDING, JOB_TTL_SECONDS
from test_v04_gates import gate_setup
from test_v04_protocol import RecordingWorker, initialize, tool, confirm, rpc


@pytest.fixture(scope='session')
def response_validators():
    schemas=output_schemas()
    for schema in schemas.values(): Draft202012Validator.check_schema(schema)
    return {name:Draft202012Validator(value) for name,value in schemas.items()}


def test_allowlist_and_fixture_links_are_complete():
    declared=surface(); expected=inventory.generate()
    assert set(declared['mcp_tools'])==set(TOOLS)|set(GATE_TOOLS)
    assert {v['name'] for v in inventory._cli_commands(parser())}==set(declared['cli_commands'])
    for section in ('mcp_tools','cli_commands'):
        for name,rule in declared[section].items():
            assert rule['response'] in expected['output_schemas'],name
            for fixture in rule['fixtures']: assert (Path(__file__).parents[1]/fixture).is_file(),fixture
    assert expected['protocols']==list(PROTOCOLS)
    assert expected['runtime_limits']['mcp_message_bytes']==MAX_MESSAGE_BYTES
    assert expected['runtime_limits']['queue_pending_max']==MAX_PENDING
    assert expected['runtime_limits']['job_ttl_seconds']==JOB_TTL_SECONDS


def test_schema_every_public_response_is_valid(response_validators):
    assert len(response_validators)>=45


def test_sdk_signature_and_dataclass_field_mutations_are_detected(monkeypatch):
    from ai_orchestrator import provider_sdk
    original=sdk_contracts()
    request=provider_sdk.RunRequest
    fields=request.__dataclass_fields__
    replacement={name:copy.copy(field) for name,field in fields.items()}
    replacement['timeout'].type='str'
    monkeypatch.setattr(request,'__dataclass_fields__',replacement)
    assert sdk_contracts()!=original
    def before(request): pass
    def after(request, permission): pass
    assert signature(before)!=signature(after)


def test_response_field_mutation_changes_inventory(monkeypatch):
    import ai_orchestrator.public_contracts as public
    baseline=inventory.generate(); changed=copy.deepcopy(public.output_schemas())
    changed['identity']['properties']['matches']={'type':'string'}
    monkeypatch.setattr(public,'output_schemas',lambda:changed)
    assert inventory.generate()!=baseline
    validator=Draft202012Validator(changed['identity'])
    from ai_orchestrator.build_identity import report
    assert not validator.is_valid(report())


def test_gate_actual_responses_match_public_schema(gate_setup,response_validators):
    _,intake,broker,_=gate_setup
    server=StdioServer(broker.service,single_terminal=True,auto_worker=RecordingWorker())
    try:
        initialize(server)
        response=tool(server,'request_start',{'intake_id':intake.id,'request_id':'public-no'})
        answer=confirm(server,response,content={'decision':'no'})
        response_validators['gate'].validate(answer['result']['structuredContent'])
        assert answer['result']['isError'] is False  # genuine refusal is not a transport error
        assert answer['result']['structuredContent']['gate_status']=='declined'
    finally:server.close()


def test_actual_discovery_and_error_envelopes(gate_setup,response_validators):
    _,_,broker,_=gate_setup
    server=StdioServer(broker.service,single_terminal=True,auto_worker=RecordingWorker())
    try:
        initialize(server)
        discovery=server.handle(rpc('tools/list'))['result']['tools']
        expected={x['name']:x for x in inventory.generate()['mcp_tools']}
        assert set(expected)=={x['name'] for x in discovery}
        for actual in discovery:
            assert actual['annotations']==expected[actual['name']]['annotations']
            assert inventory.digest(inventory.schema_semantics(actual['inputSchema']))==expected[actual['name']]['schema_sha256']
        invalid=tool(server,'get_task',{'task_id':'x','decision':'yes'})
        response_validators['rpc_error'].validate(invalid)
        assert invalid['error']['code']==-32602
        unknown=tool(server,'get_task',{'task_id':'missing'})
        assert unknown['result']['isError'] is True
        response_validators['error'].validate(unknown['result']['structuredContent'])
        assert json.loads(unknown['result']['content'][0]['text'])==unknown['result']['structuredContent']
    finally:server.close()


@pytest.mark.parametrize('protocol',PROTOCOLS)
def test_wire_envelopes_keep_protocol_specific_structured_content(gate_setup,protocol):
    _,_,broker,_=gate_setup
    server=StdioServer(broker.service)
    try:
        initialize(server,protocol=protocol)
        value=tool(server,'get_task',{'task_id':'missing'})['result']
        assert ('structuredContent' in value)==(protocol=='2025-06-18')
        assert value['isError'] is True
    finally:server.close()


def test_cli_streams_and_exit_categories(tmp_path,capsys,response_validators):
    assert main(['identity'])==0
    result=capsys.readouterr(); assert not result.err
    response_validators['identity'].validate(json.loads(result.out))
    with pytest.raises(SystemExit) as error:main(['unknown-command'])
    assert error.value.code==2
    result=capsys.readouterr(); assert result.err and not result.out
    assert main(['--project',str(tmp_path),'status','missing'])==1
    result=capsys.readouterr();assert not result.out
    response_validators['error'].validate(json.loads(result.err))
