"""Regression coverage for platform-specific process-group cleanup races."""

import pytest

from ai_orchestrator.models import OrchestratorError


def test_exited_process_group_denial_is_retried_after_reaping(monkeypatch):
    from unittest.mock import Mock
    from ai_orchestrator.process import stop_process_group

    process = Mock(pid=12345)
    process.poll.return_value = 0
    signal_group = Mock(side_effect=[PermissionError(1, "exited group"), ProcessLookupError()])
    monkeypatch.setattr("ai_orchestrator.process.os.killpg", signal_group)
    stop_process_group(process)
    assert signal_group.call_count == 2
    process.kill.assert_not_called()
    process.wait.assert_called_once_with(timeout=5)


def test_persistent_process_group_denial_is_not_silently_ignored(monkeypatch):
    from unittest.mock import Mock
    from ai_orchestrator.process import stop_process_group

    process = Mock(pid=12345)
    process.poll.return_value = 0
    monkeypatch.setattr("ai_orchestrator.process.os.killpg", Mock(side_effect=PermissionError(1, "denied")))
    with pytest.raises(OrchestratorError, match="termination was denied"):
        stop_process_group(process)
    process.wait.assert_called_once_with(timeout=5)


def test_live_process_cleanup_denial_still_reaps_parent(monkeypatch):
    from unittest.mock import Mock
    from ai_orchestrator.process import stop_process_group

    process = Mock(pid=12345)
    process.poll.return_value = None
    monkeypatch.setattr("ai_orchestrator.process.os.killpg", Mock(side_effect=PermissionError(1, "denied")))
    with pytest.raises(OrchestratorError, match="termination was denied"):
        stop_process_group(process)
    process.kill.assert_called_once()
    process.wait.assert_called_once_with(timeout=5)
