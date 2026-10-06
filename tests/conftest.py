from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from ai_orchestrator.engine import Engine
from ai_orchestrator.contracts import PlanResult, ImplementationResult, ReviewResult
from ai_orchestrator.models import AgentResult, TaskSpec
from ai_orchestrator.project import initialize


def reply(request, *, outcome, summary, findings, evidence):
    values = {"outcome": outcome, "summary": summary, "evidence": evidence}
    if request.result_model is PlanResult:
        values.update(steps=findings, uncertainties=[])
    elif request.result_model is ImplementationResult:
        values.update(changes=findings, uncertainties=[])
    elif request.result_model is ReviewResult:
        values.update(blocking_findings=findings if outcome == "changes_required" else [], observations=findings if outcome == "approved" else [])
    else:
        values["findings"] = findings
    return request.result_model(**values)


class FakeAdapter:
    api_version = 2
    capabilities = frozenset({"read_files", "write_files", "fresh_session", "structured_output", "shell"})
    semantic_capabilities = frozenset({"repository_analysis", "planning", "code_edit", "test_authoring", "review", "supervision"})

    def __init__(self, family: str):
        self.family = family
        self.requests = []
        self.reject_reviews = 0
        self.mutate_review = False
        self.mutate_protected = False
        self.explode = False

    def doctor(self, config, workspace):
        return {"version": "offline-fixture", "family": self.family}

    def execute(self, request):
        self.requests.append(request)
        if self.explode:
            raise RuntimeError("synthetic provider failure")
        if request.phase == "execute":
            (request.workspace / "result.txt").write_text("implemented\n")
            if self.mutate_protected:
                (request.workspace / ".env").write_text("changed")
            return reply(request, outcome="completed", summary="IMPLEMENTER_TRANSCRIPT_MARKER", findings=[], evidence=["result.txt"])
        if request.phase == "review":
            if self.mutate_review:
                (request.workspace / "unexpected.txt").write_text("violation")
            if self.reject_reviews:
                self.reject_reviews -= 1
                return reply(request, outcome="changes_required", summary="Repair the issue", findings=["synthetic defect"], evidence=[])
            return reply(request, outcome="approved", summary="Acceptance criteria satisfied", findings=[], evidence=["result.txt"])
        return reply(request, outcome="completed", summary="Inspect, implement and test the requested change", findings=[], evidence=[])


@pytest.fixture
def workspace(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "input.txt").write_text("input\n")
    initialize(tmp_path, "fixture")
    config = tmp_path / ".orchestrator/config.yaml"
    profile = yaml.safe_load(config.read_text())
    profile["validators"] = {"check": {"argv": [sys.executable, "-c", "print('validated')"], "timeout_seconds": 5}}
    config.write_text(yaml.safe_dump(profile))
    return tmp_path


@pytest.fixture
def engine(workspace):
    reasoning, engineering = FakeAdapter("anthropic"), FakeAdapter("openai")
    instance = Engine(workspace, {"claude": reasoning, "codex": engineering})
    instance.trust("test-operator")
    yield instance, reasoning, engineering
    instance.close()


def spec(task_id="task-1", risk="T2", **kwargs):
    return TaskSpec(id=task_id, goal="Implement the requested result", acceptance=["A result is produced and checks pass"], risk=risk, validators=[] if risk == "T0" else ["check"], **kwargs)


def approve_and_run(engine, task_id="task-1"):
    state = engine.run(task_id)
    assert state.status == "awaiting_approval", state.model_dump()
    engine.approve(task_id, engine.approval_scope(state), "test-operator")
    return engine.run(task_id)


@pytest.fixture(autouse=True)
def public_response_conformance(monkeypatch):
    """Validate real service/CLI return values across existing regression cases.

    Test doubles that replace these public methods remain test doubles, not live
    compatibility evidence. This never validates or transforms runtime writes.
    """
    from functools import lru_cache, wraps
    from public_response_checks import validators, declared
    from ai_orchestrator.service import ApplicationService
    from ai_orchestrator import cli
    invoke=ApplicationService.invoke
    dispatch=cli.dispatch

    @wraps(invoke)
    def checked_invoke(self,name,arguments):
        result=invoke(self,name,arguments)
        validators()[declared()['mcp_tools'][name]['response']].validate(result)
        return result

    @wraps(dispatch)
    def checked_dispatch(args):
        result,code=dispatch(args)
        name=args.command
        if name in ('backup','learning','maintenance','validator'):
            name+=' '+getattr(args,args.command+'_action')
        validators()[declared()['cli_commands'][name]['response']].validate(result)
        assert code in (0,1)
        return result,code

    monkeypatch.setattr(ApplicationService,'invoke',checked_invoke)
    monkeypatch.setattr(cli,'dispatch',checked_dispatch)
