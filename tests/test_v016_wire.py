"""Actual MCP stdio + managed workers + read-only exploration + three gates.

The provider shims are deterministic subprocesses, not live external models.
"""
import sys
import time

import yaml

from ai_orchestrator.engine import Engine
from ai_orchestrator.project import Project
from test_v04_wire import SHIM, launch, close


EXPLORATION_SHIM = SHIM.replace(
    "if role == 'SupervisorResult':",
    """if role == 'ExplorationResult':
    assert request['role'] == 'exploration'
    assert not pathlib.Path('.orchestrator').exists()
    assert 'validators' not in request
    changed = request['prior_context'] is not None
    result = {'summary':request['request'],'hypotheses':['Inspect the calculator'],
              'assumptions':[], 'options':['Keep add','Add multiplication'],
              'tradeoffs':['Small patch'], 'open_questions':[],
              'decisions':['Prefer multiplication' if changed else 'Consider subtraction'],
              'discarded':['Subtraction'] if changed else [],
              'reported_paths':['calculator.py']}
elif role == 'SupervisorResult':""",
)


def test_exploration_to_accepted_task_over_real_mcp_and_managed_worker(workspace, tmp_path_factory):
    shim = tmp_path_factory.mktemp('explore-wire') / 'agent-shim'
    shim.write_text('#!' + sys.executable + ' -S\n' + EXPLORATION_SHIM)
    shim.chmod(0o755)
    config = workspace / '.orchestrator/config.yaml'
    profile = yaml.safe_load(config.read_text())
    for provider in profile['providers'].values():
        provider['executable'] = str(shim)
    profile['validators']['check'] = {
        'argv': [sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider'],
        'timeout_seconds': 20, 'env': {'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'},
    }
    config.write_text(yaml.safe_dump(profile))
    (workspace / 'calculator.py').write_text('def add(a,b):\n    return a+b\n')
    (workspace / 'test_calculator.py').write_text('from calculator import add\n\ndef test_add():\n    assert add(2,3)==5\n')
    engine = Engine(workspace)
    engine.trust('operator')
    original_digest = engine.profile_digest
    original_snapshot = Project(workspace).snapshot()
    engine.close()
    process, client = launch(workspace)
    try:
        initial = client.tool('inspect_project')
        assert not initial['worker']['manager_started']
        job = client.tool('explore', request='まだ仕様が曖昧です。まず選択肢を比較してください。', request_id='explore-1')
        session = client.wait_job(job['id'])
        assert session['status'] == 'active'
        assert client.tool('get_exploration', exploration_id=session['id'])['revision'] == 1
        job = client.tool('explore', request='引き算ではなく掛け算を優先します。まだ実装しないでください。',
                          exploration_id=session['id'], expected_revision=1, request_id='explore-2')
        session = client.wait_job(job['id'])
        assert session['revision'] == 2 and session['current']['discarded'] == ['Subtraction']
        assert Project(workspace).snapshot() == original_snapshot
        engine = Engine(workspace)
        assert engine.store.task_ids() == [] and engine.store.intake_ids() == []
        assert engine.store.db.execute('SELECT count(*) FROM approvals').fetchone()[0] == 0
        engine.close()
        job = client.tool('propose_from_exploration', exploration_id=session['id'], expected_revision=2,
                          decision='掛け算の実装とテストを具体的なタスクとして提案してください。',
                          task_id='exploration-wire-task', request_id='explore-propose')
        intake = client.wait_job(job['id'])
        assert intake['status'] == 'proposed' and intake['calls'] == 3
        assert intake['exploration']['session_id'] == session['id']
        declined = client.gate('request_start', {'intake_id': intake['id'], 'request_id': 'explore-decline'}, confirm=False)
        assert declined['gate_status'] == 'declined'
        started = client.gate('request_start', {'intake_id': intake['id'], 'request_id': 'explore-start'})
        task = client.wait_job(started['result']['job_id'])
        assert task['status'] == 'awaiting_approval' and task['calls'] == 4
        execution = client.gate('request_execution', {'task_id': task['spec']['id'], 'request_id': 'explore-execution'})
        task = client.wait_job(execution['result']['job_id'])
        assert task['status'] == 'awaiting_acceptance' and task['calls'] == 6
        acceptance = client.gate('request_acceptance', {'task_id': task['spec']['id'], 'request_id': 'explore-acceptance'})
        assert acceptance['gate_status'] == 'applied'
        task = client.tool('get_task', task_id=task['spec']['id'])
        assert task['status'] == 'succeeded'
        assert task['usage']['summary']['calls'] == 6
        source = client.tool('get_artifact', task_id=task['spec']['id'], kind='exploration_transition')['content']
        assert source['revision'] == 2
        assert source['context']['understanding']['discarded'] == ['Subtraction']
        assert client.tool('get_exploration', exploration_id=session['id'])['status'] == 'transitioned'
        assert client.tool('inspect_project')['profile_digest'] == original_digest
    finally:
        close(process, client)
    time.sleep(2.5)
