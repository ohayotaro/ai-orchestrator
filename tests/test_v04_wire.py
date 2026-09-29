"""Real bidirectional MCP + automatically managed worker + real pytest.

Providers are deterministic CLI-shaped subprocesses, never live model calls.
"""
import json
import os
import selectors
import subprocess
import sys
import time
from pathlib import Path

import pytest
import yaml

from ai_orchestrator.human_gates import GateStore
from ai_orchestrator.project import Project
from test_v04_gates import IntakeAdapter
from ai_orchestrator.engine import Engine
from ai_orchestrator.supervisor import Supervisor

SHIM = r'''
import json, os, pathlib, sys
args = sys.argv[1:]
if '--version' in args:
    print('wire-provider 1.0'); raise SystemExit(0)
if '--help' in args:
    print('--output-schema --output-last-message --sandbox --ephemeral --json-schema --no-session-persistence --permission-mode --tools --strict-mcp-config --setting-sources --disable-slash-commands'); raise SystemExit(0)
assert 'CLAUDECODE' not in os.environ, 'parent host session leaked into worker'
assert 'AI_ORCHESTRATOR_INTERNAL_WORKER' in os.environ
assert 'PYTHONPATH' not in os.environ, 'host Python path leaked into worker'
request = json.loads(sys.stdin.read())
if '--json-schema' in args:
    schema = json.loads(args[args.index('--json-schema') + 1])
    assert args[args.index('--permission-mode') + 1] == 'dontAsk'
else:
    schema = json.loads(pathlib.Path(args[args.index('--output-schema') + 1]).read_text())
    assert '--ephemeral' in args
role = schema['title']
if role == 'SupervisorResult':
    result = {'outcome':'proposed','summary':'Add multiplication','task':{'goal':'Add multiply(a,b) and a regression test','acceptance':['multiply(2,3)==6','Existing add test passes'],'risk':'T2','validators':['check'],'external_effects':False,'allowed_paths':['calculator.py','test_calculator.py']},'questions':[]}
elif role == 'PlanResult':
    result = {'outcome':'completed','summary':'Focused plan','steps':['Add multiply','Add test'],'uncertainties':[],'evidence':['calculator.py']}
elif role == 'ImplementationResult':
    pathlib.Path('calculator.py').write_text('def add(a,b):\n    return a+b\n\ndef multiply(a,b):\n    return a*b\n')
    pathlib.Path('test_calculator.py').write_text('from calculator import add, multiply\n\ndef test_add():\n    assert add(2,3)==5\n\ndef test_multiply():\n    assert multiply(2,3)==6\n')
    result = {'outcome':'completed','summary':'Added multiply','changes':['calculator.py','test_calculator.py'],'uncertainties':[],'evidence':['calculator.py']}
elif role == 'ReviewResult':
    assert 'plan' not in request
    assert request['validation']['checks'][0]['exit_code']==0
    assert '2 passed' in request['validation']['checks'][0]['stdout_tail']
    result = {'outcome':'approved','summary':'Acceptance met','blocking_findings':[],'observations':['Non-blocking confirmation'],'evidence':['calculator.py','test_calculator.py']}
else:
    raise RuntimeError(role)
if '--json-schema' in args:
    print(json.dumps({'is_error':False,'structured_output':result}))
else:
    pathlib.Path(args[args.index('--output-last-message')+1]).write_text(json.dumps(result))
'''


class Client:
    def __init__(self, process):
        self.process = process
        self.sequence = 0
        self.buffer = bytearray()
        self.selector = selectors.DefaultSelector()
        self.selector.register(process.stdout, selectors.EVENT_READ)

    def send(self, data):
        self.process.stdin.write((json.dumps(data)+'\n').encode())
        self.process.stdin.flush()

    def read(self, timeout=15):
        deadline = time.monotonic() + timeout
        while b'\n' not in self.buffer:
            assert self.selector.select(max(0, deadline-time.monotonic())), 'MCP response timed out'
            data = os.read(self.process.stdout.fileno(), 65536)
            assert data, 'MCP unexpectedly closed'
            self.buffer.extend(data)
        line, _, tail = self.buffer.partition(b'\n')
        self.buffer = bytearray(tail)
        return json.loads(line)

    def request(self, method, params=None):
        self.sequence += 1
        self.send({'jsonrpc':'2.0','id':self.sequence,'method':method,'params':params or {}})
        return self.sequence

    def tool(self, name, **arguments):
        rid = self.request('tools/call', {'name':name, 'arguments':arguments})
        result = self.read()
        assert result['id'] == rid, result
        assert 'error' not in result, result
        assert not result['result']['isError'], result
        return result['result']['structuredContent']

    def gate(self, name, arguments, *, confirm=True):
        rid = self.request('tools/call', {'name':name, 'arguments':arguments})
        form = self.read()
        assert form['method']=='elicitation/create', form
        assert form['params']['requestedSchema']['properties']['decision']['enum'] == ['yes','no']
        assert 'scope' in form['params']['message']
        ping = self.request('ping')
        assert self.read()['id'] == ping  # host stays responsive while dialog open
        self.send({'jsonrpc':'2.0','id':form['id'],'result':{'action':'accept','content':{'decision':'yes' if confirm else 'no'}}})
        result = self.read()
        assert result['id']==rid and not result['result']['isError'], result
        return result['result']['structuredContent']

    def wait_job(self, job_id):
        rid = self.request('tools/call', {'name':'wait_job','arguments':{'job_id':job_id,'timeout_seconds':35},'_meta':{'progressToken':'wire-'+job_id}})
        deadline = time.monotonic()+40
        progress = []
        while time.monotonic()<deadline:
            message = self.read(timeout=max(.1, deadline-time.monotonic()))
            if message.get('method') == 'notifications/progress':
                progress.append(message['params'])
                continue
            assert message['id'] == rid, message
            assert not message['result']['isError'], message
            job = message['result']['structuredContent']
            assert not job['wait_timed_out'], job
            assert job['status'] == 'succeeded', job
            return job['result']  # progress may be empty if the job finished before the wait began
        raise AssertionError('wait_job did not complete')


def launch(workspace, timeout=30):
    env = dict(os.environ, CLAUDECODE='parent-host-session')
    env.pop('AI_ORCHESTRATOR_INTERNAL_WORKER', None)
    process = subprocess.Popen([sys.executable,'-I','-m','ai_orchestrator','--project',str(workspace),'serve','--single-terminal','--gate-timeout',str(timeout)], env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
    client = Client(process)
    rid = client.request('initialize', {'protocolVersion':'2025-06-18','capabilities':{'elicitation':{'form':{}}},'clientInfo':{'name':'offline-native-ui','version':'1'}})
    assert client.read()['id']==rid
    client.send({'jsonrpc':'2.0','method':'notifications/initialized'})
    return process, client


def close(process, client):
    process.stdin.close()
    try:
        assert process.wait(timeout=8)==0, process.stderr.read().decode()
    finally:
        if process.poll() is None:
            process.kill(); process.wait()
        client.selector.close()
        process.stdout.close(); process.stderr.close()


@pytest.mark.parametrize('implementer',['engineering','reasoning'])
def test_single_terminal_native_gates_and_auto_workers(workspace, tmp_path_factory, implementer):
    shim = tmp_path_factory.mktemp('native-wire')/'agent-shim'
    shim.write_text('#!'+sys.executable+' -S\n'+SHIM)
    shim.chmod(0o755)
    path = workspace/'.orchestrator/config.yaml'
    profile = yaml.safe_load(path.read_text())
    for cfg in profile['providers'].values():
        cfg['executable']=str(shim)
    profile['roles']['implementer']['provider']=implementer
    profile['roles']['reviewer']['provider']='reasoning' if implementer=='engineering' else 'engineering'
    profile['validators']['check']={'argv':[sys.executable,'-m','pytest','-q','-p','no:cacheprovider'],'timeout_seconds':15,'env':{'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1'}}
    path.write_text(yaml.safe_dump(profile))
    (workspace/'calculator.py').write_text('def add(a,b):\n    return a+b\n')
    (workspace/'test_calculator.py').write_text('from calculator import add\n\ndef test_add():\n    assert add(2,3)==5\n')
    engine = Engine(workspace); engine.trust('operator'); engine.close()
    process, client = launch(workspace)
    try:
        inspection=client.tool('inspect_project')
        assert inspection['host_confirmation']['form_supported']
        assert inspection['worker']['manager_started'] is False
        job=client.tool('propose_task',request='multiplyとテストを追加',task_id='native-task',request_id='ask-native')
        intake=client.wait_job(job['id'])
        declined=client.gate('request_start',{'intake_id':intake['id'],'request_id':'decline-native'},confirm=False)
        assert declined['gate_status']=='declined'
        engine = Engine(workspace)
        assert engine.store.db.execute('SELECT count(*) FROM tasks').fetchone()[0]==0
        engine.close()
        started=client.gate('request_start',{'intake_id':intake['id'],'request_id':'start-native'})
        assert started['gate_status']=='applied'
        task=client.wait_job(started['result']['job_id'])
        assert task['status']=='awaiting_approval' and task['calls']==2
        executed=client.gate('request_execution',{'task_id':'native-task','request_id':'execute-native'})
        task=client.wait_job(executed['result']['job_id'])
        assert task['status']=='awaiting_acceptance' and task['calls']==4,task
        assert client.tool('get_artifact',task_id='native-task',kind='review')['content']['blocking_findings']==[]
        accepted=client.gate('request_acceptance',{'task_id':'native-task','request_id':'accept-native'})
        assert accepted['gate_status']=='applied'
        assert client.tool('get_task',task_id='native-task')['status']=='succeeded'
        gate_store=GateStore(Project(workspace))
        assert gate_store.db.execute("SELECT count(*) FROM gates WHERE status='applied'").fetchone()[0]==3
        gate_store.close()
        assert list((workspace/'.orchestrator/runtime').glob('auto-worker-*.log'))
        assert not list(workspace.rglob('*.pyc'))
        # No manual worker/start/approve/accept command was issued by this test.
    finally:
        close(process,client)
    time.sleep(2.5)  # managed worker drains and idle-exits, without a server-owned tty


def prepared_intake(workspace):
    registry={'claude':IntakeAdapter('anthropic'),'codex':IntakeAdapter('openai')}
    engine=Engine(workspace,registry); engine.trust('operator')
    proposal=Supervisor(engine).ask('Make a result',task_id='pending-form')
    engine.close()
    assert proposal.status=='proposed'
    return proposal


def test_real_stream_timeout_without_any_client_message(workspace):
    intake=prepared_intake(workspace)
    process,client=launch(workspace,timeout=.2)
    try:
        rid=client.request('tools/call',{'name':'request_start','arguments':{'intake_id':intake.id,'request_id':'timeout-native'}})
        form=client.read()
        assert form['method']=='elicitation/create'
        response=client.read(timeout=3)
        assert response['id']==rid
        assert response['result']['structuredContent']['gate_status']=='expired'
    finally:
        close(process,client)
    engine=Engine(workspace)
    assert engine.store.db.execute('SELECT count(*) FROM tasks').fetchone()[0]==0
    engine.close()


def test_real_stream_disconnect_cancels_unanswered_confirmation(workspace):
    intake=prepared_intake(workspace)
    process,client=launch(workspace)
    client.request('tools/call',{'name':'request_start','arguments':{'intake_id':intake.id,'request_id':'disconnect-native'}})
    assert client.read()['method']=='elicitation/create'
    close(process,client)
    gates=GateStore(Project(workspace))
    assert gates.db.execute('SELECT status FROM gates').fetchone()[0]=='cancelled'
    gates.close()


def test_official_sdk_native_elicitation_decline(workspace):
    pytest.importorskip('mcp',reason='install .[interop] for independent official SDK verification')
    import asyncio
    from mcp import ClientSession, StdioServerParameters, types
    from mcp.client.stdio import stdio_client
    intake=prepared_intake(workspace)
    callbacks=[]
    async def elicit(context,params):
        callbacks.append(params)
        assert params.requestedSchema['properties']['decision']['enum']==['yes','no']
        return types.ElicitResult(action='decline')
    async def exercise():
        server=StdioServerParameters(command=sys.executable,args=['-I','-m','ai_orchestrator','--project',str(workspace),'serve','--single-terminal'])
        async with stdio_client(server) as (reader,writer):
            async with ClientSession(reader,writer,elicitation_callback=elicit) as session:
                await session.initialize()
                listed=await session.list_tools()
                assert 'request_start' in {t.name for t in listed.tools}
                response=await session.call_tool('request_start',{'intake_id':intake.id,'request_id':'sdk-native'})
                assert not response.isError
                assert response.structuredContent['gate_status']=='declined'
                await session.send_ping()
    asyncio.run(asyncio.wait_for(exercise(),20))
    assert len(callbacks)==1
