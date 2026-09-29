import os
import sys
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from ai_orchestrator.auto_worker import AutoWorker, worker_environment
from ai_orchestrator.cli import main
from ai_orchestrator.models import OrchestratorError
from ai_orchestrator.worker import WORKER_MARKER, run_worker, worker_lock
from ai_orchestrator.project import Project


def test_worker_environment_is_new_and_not_host_session_state():
    source = {"PATH": "/usr/bin", "HOME": "/home/user", "CLAUDECODE": "parent", "CODEX_CLI_PATH": "/host", "PYTHONPATH": "/evil", "LD_PRELOAD": "evil", "BASH_ENV": "evil", "GITHUB_TOKEN": "secret", "OPENAI_API_KEY": "allowed-provider-key", WORKER_MARKER: "parent"}
    env = worker_environment(source)
    assert env["OPENAI_API_KEY"] == "allowed-provider-key"
    for key in ("CLAUDECODE", "CODEX_CLI_PATH", "PYTHONPATH", "LD_PRELOAD", "BASH_ENV", "GITHUB_TOKEN", WORKER_MARKER):
        assert key not in env
    assert source["CLAUDECODE"] == "parent"
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"


def test_recursive_auto_worker_is_rejected(workspace, monkeypatch):
    monkeypatch.setenv(WORKER_MARKER, "1")
    with pytest.raises(OrchestratorError, match="cannot auto-spawn"):
        AutoWorker(workspace)


def test_initializing_manager_does_not_launch_old_work(workspace, monkeypatch):
    popen = Mock()
    monkeypatch.setattr("ai_orchestrator.auto_worker.subprocess.Popen", popen)
    manager = AutoWorker(workspace)
    try:
        assert manager.status()["manager_started"] is False
        manager._tick()
        popen.assert_not_called()
    finally:
        manager.close()


def test_worker_idle_exit_preserves_manual_mode(workspace, monkeypatch):
    monkeypatch.delenv("CLAUDECODE", raising=False)
    monkeypatch.delenv(WORKER_MARKER, raising=False)
    result = run_worker(workspace, poll_interval=0.1, idle_seconds=0.1)
    assert result["idle_exit"] and result["processed"] == 0
    assert WORKER_MARKER not in os.environ
    assert run_worker(workspace, once=True)["processed"] == 0


def test_existing_worker_lock_prevents_duplicate_auto_spawn(workspace, monkeypatch):
    from ai_orchestrator.jobs import JobQueue
    project = Project(workspace)
    queue = JobQueue(project)
    queue.enqueue("ask", {"request": "x"}, "req", project.load()[1], project.snapshot())
    queue.close()
    popen = Mock()
    monkeypatch.setattr("ai_orchestrator.auto_worker.subprocess.Popen", popen)
    manager = AutoWorker(workspace)
    try:
        with worker_lock(project):
            manager._tick()
        popen.assert_not_called()
    finally:
        manager.close()


def test_spawn_is_bounded_and_has_private_stdio(workspace, monkeypatch):
    from ai_orchestrator.jobs import JobQueue
    project = Project(workspace)
    queue = JobQueue(project)
    queue.enqueue("ask", {"request": "x"}, "req", project.load()[1], project.snapshot())
    queue.close()
    fake = Mock()
    fake.poll.return_value = None
    popen = Mock(return_value=fake)
    monkeypatch.setattr("ai_orchestrator.auto_worker.subprocess.Popen", popen)
    manager = AutoWorker(workspace)
    try:
        manager._tick()
        args, kwargs = popen.call_args
        assert args[0][:4] == [os.path.abspath(sys.executable), "-I", "-m", "ai_orchestrator"]
        assert kwargs["start_new_session"] and kwargs["close_fds"]
        assert kwargs["stdin"] == -3  # subprocess.DEVNULL
        assert kwargs["stdout"] is kwargs["stderr"]
        manager._tick()
        assert popen.call_count == 1
        fake.poll.return_value = 1
        manager._tick(); manager._tick(); manager._tick()
        assert manager.disabled and popen.call_count == 3
    finally:
        manager.close()


def test_nested_start_cli_fails_before_creating_task(workspace, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDECODE", "host")
    code = main(["--project", str(workspace), "start", "nonexistent", "--scope", "fake", "--by", "operator"])
    assert code == 1
    assert "No task was created" in capsys.readouterr().err
    assert not list((workspace / ".orchestrator/tasks").glob("*.json"))


def test_healthy_worker_exits_do_not_trigger_crash_loop_limit(workspace, monkeypatch):
    from ai_orchestrator.jobs import JobQueue
    project = Project(workspace)
    queue = JobQueue(project)
    queue.enqueue("ask", {"request": "x"}, "req", project.load()[1], project.snapshot())
    queue.close()
    child = Mock()
    child.poll.return_value = 0
    popen = Mock(return_value=child)
    monkeypatch.setattr("ai_orchestrator.auto_worker.subprocess.Popen", popen)
    manager = AutoWorker(workspace)
    try:
        for _ in range(6):
            manager._tick()
        assert popen.call_count == 6 and not manager.disabled
    finally:
        manager.close()
