"""Small JSON-output CLI. Approvals are explicit local operator actions."""

from __future__ import annotations

import argparse
import json
import sys
import sqlite3
from pathlib import Path
from typing import Any

from pydantic import ValidationError
import yaml

from . import __version__, knowledge
from .engine import Engine
from .contracts import IntakeState, PlanResult, ImplementationResult, ReviewResult, SupervisorResult
from .supervisor import Supervisor
from .validators import register_validator
from .models import AgentResult, Artifact, OrchestratorError, Profile, Proposal, TaskSpec, TaskState
from .project import atomic_write, digest, initialize, load_yaml


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(prog="orchestrator", description="Project-driven, provider-neutral local orchestration (v0.2 alpha)")
    cli.add_argument("--version", action="version", version=__version__)
    cli.add_argument("--project", type=Path, default=Path.cwd(), help="Git worktree root; put this option before the command")
    commands = cli.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--name", default="my-project")
    doctor = commands.add_parser("doctor")
    doctor.add_argument("--validators-only", action="store_true")
    ask = commands.add_parser("ask", help="Propose a TaskSpec from natural language; never auto-approve execution")
    ask.add_argument("prompt")
    ask.add_argument("--task-id")
    ask.add_argument("--advisory", action="store_true")
    ask.add_argument("--reply-to", help="Intake ID whose clarification questions this prompt answers")
    intake = commands.add_parser("intake", help="Inspect an intake proposal and its confirmation scope")
    intake.add_argument("intake_id")
    start = commands.add_parser("start", help="Confirm an intake and run planning, stopping at the execution gate")
    start.add_argument("intake_id")
    start.add_argument("--scope", required=True)
    start.add_argument("--by", required=True)
    start.add_argument("--no-run", action="store_true", help="Register only; do not call the planner yet")
    validator = commands.add_parser("validator")
    actions = validator.add_subparsers(dest="validator_action", required=True)
    add = actions.add_parser("add", help="Register a user-owned command; does not execute or trust it")
    add.add_argument("name")
    add.add_argument("--replace", action="store_true")
    add.add_argument("--timeout", type=int, default=120)
    add.add_argument("--env", action="append", default=[], metavar="NAME=VALUE")
    add.add_argument("--generated-path", action="append", default=[])
    add.add_argument("argv", nargs="+", help="Use -- before the executable and arguments")
    check = actions.add_parser("check", help="Explicitly execute one trusted validator without model calls")
    check.add_argument("name")

    trust = commands.add_parser("trust")
    trust.add_argument("--by", required=True)
    trust.add_argument("--ack-local-execution", action="store_true", required=True)
    create = commands.add_parser("create")
    create.add_argument("--task-file", type=Path, required=True, help="TaskSpec YAML or JSON")
    for command in ("run", "status", "cancel", "recover"):
        sub = commands.add_parser(command)
        sub.add_argument("task_id")
    events = commands.add_parser("events")
    events.add_argument("--task-id")
    approve = commands.add_parser("approve")
    approve.add_argument("task_id")
    approval = approve.add_mutually_exclusive_group(required=True)
    approval.add_argument("--scope", help="exact hash displayed by status")
    approval.add_argument("--interactive", action="store_true", help="Inspect the current plan/feedback, then confirm in a real terminal")
    approve.add_argument("--by", required=True)
    accept = commands.add_parser("accept")
    accept.add_argument("task_id")
    accept.add_argument("--by", required=True)
    schema = commands.add_parser("schema")
    schema.add_argument("kind", choices=["profile", "task", "result", "plan", "implementation", "review", "supervisor", "intake", "state", "artifact", "proposal"])
    schema.add_argument("--output", type=Path)
    proposal = commands.add_parser("propose")
    proposal.add_argument("--kind", choices=["knowledge", "policy", "skill"], required=True)
    proposal.add_argument("--statement", required=True)
    proposal.add_argument("--evidence", action="append", required=True)
    show = commands.add_parser("proposal")
    show.add_argument("proposal_id")
    promote = commands.add_parser("promote")
    promote.add_argument("proposal_id")
    promote.add_argument("--scope", required=True)
    promote.add_argument("--by", required=True)
    return cli


def dispatch(args: argparse.Namespace) -> tuple[Any, int]:
    root = args.project.resolve()
    if args.command == "init":
        initialize(root, args.name)
        return {"project": str(root), "initialized": True, "trusted": False}, 0
    if args.command == "schema":
        model = {"profile": Profile, "task": TaskSpec, "result": AgentResult, "state": TaskState, "artifact": Artifact, "proposal": Proposal, "plan": PlanResult, "implementation": ImplementationResult, "review": ReviewResult, "supervisor": SupervisorResult, "intake": IntakeState}[args.kind]
        schema = model.model_json_schema()
        if args.output:
            atomic_write(args.output, json.dumps(schema, indent=2) + "\n")
            return {"path": str(args.output)}, 0
        return schema, 0
    if args.command == "propose":
        proposal = knowledge.propose(root, args.kind, args.statement, args.evidence)
        return {**proposal.model_dump(), "scope": digest(proposal.model_dump())}, 0
    if args.command == "proposal":
        proposal = knowledge.load_proposal(root, args.proposal_id)
        return {**proposal.model_dump(), "scope": digest(proposal.model_dump())}, 0
    if args.command == "promote":
        proposal = knowledge.promote(root, args.proposal_id, args.scope, args.by)
        return {**proposal.model_dump(), "profile_retrust_required": True}, 0
    if args.command == "validator" and args.validator_action == "add":
        env = {}
        for item in args.env:
            if "=" not in item:
                raise OrchestratorError("--env requires NAME=VALUE")
            key, value = item.split("=", 1)
            if key in env:
                raise OrchestratorError(f"duplicate validator environment key: {key}")
            env[key] = value
        argv = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
        return register_validator(root, args.name, argv, timeout=args.timeout, env=env, generated_paths=args.generated_path, replace=args.replace), 0
    engine = Engine(root)
    try:
        if args.command == "trust":
            return engine.trust(args.by), 0
        if args.command == "doctor":
            report = engine.doctor(validators_only=args.validators_only)
            return report, 0 if all(item["ok"] for item in report.values()) else 1
        if args.command == "ask":
            supervisor = Supervisor(engine)
            intake = supervisor.ask(args.prompt, task_id=args.task_id, advisory=args.advisory, reply_to=args.reply_to)
            return supervisor.describe(intake.id), 1 if intake.status in ("blocked", "failed", "cancelled") else 0
        if args.command == "intake":
            return Supervisor(engine).describe(args.intake_id), 0
        if args.command == "validator":
            report = engine.check_validator(args.name)
            return report, 0 if report["ok"] else 1
        if args.command == "start":
            state = Supervisor(engine).start(args.intake_id, args.scope, args.by)
            if not args.no_run:
                state = engine.run(state.spec.id)
        elif args.command == "create":
            state = engine.create(TaskSpec.model_validate(load_yaml(args.task_file)))
        elif args.command == "run":
            state = engine.run(args.task_id)
        elif args.command == "status":
            state = engine.store.get(args.task_id)
            result = state.model_dump()
            if state.status == "awaiting_approval":
                result["approval_scope"] = engine.approval_scope(state)
            return result, 0
        elif args.command == "approve":
            scope = args.scope
            if args.interactive:
                if not sys.stdin.isatty():
                    raise OrchestratorError("interactive approval requires a terminal; pipes cannot confirm")
                current = engine.store.get(args.task_id)
                if current.status != "awaiting_approval":
                    raise OrchestratorError("task is not awaiting execution approval")
                scope = engine.approval_scope(current)
                # Escape model/user strings so terminal control sequences cannot
                # disguise the task or the affirmative confirmation prompt.
                preview = {"task": current.spec.model_dump(), "attempt": current.attempt, "plan": engine.store.latest(current, "plan"), "feedback": current.feedback, "approval_scope": scope}
                print(json.dumps(preview, ensure_ascii=True, indent=2), file=sys.stderr)
                print("Inspect the worktree too. Type approve to authorize this exact scope:", file=sys.stderr)
                if sys.stdin.readline().strip() != "approve":
                    raise OrchestratorError("approval declined; no execution was authorized")
            state = engine.approve(args.task_id, scope, args.by)
        elif args.command == "accept":
            state = engine.accept(args.task_id, args.by)
        elif args.command == "recover":
            state = engine.recover(args.task_id)
        elif args.command == "cancel":
            engine.store.request_cancel(args.task_id)
            return {"task_id": args.task_id, "cancellation_requested": True}, 0
        elif args.command == "events":
            return engine.store.events(args.task_id), 0
        else:
            raise OrchestratorError("unknown command")
        result = state.model_dump()
        if state.status == "awaiting_approval":
            result["approval_scope"] = engine.approval_scope(state)
        return result, 1 if state.status in ("blocked", "failed", "cancelled") else 0
    finally:
        engine.close()


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result, code = dispatch(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return code
    except (OrchestratorError, ValidationError, ValueError, OSError, sqlite3.Error, yaml.YAMLError) as exc:
        # Validation errors may include supplied content; never paste secrets into profiles/tasks.
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
