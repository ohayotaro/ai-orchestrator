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
from .models import AgentResult, Artifact, OrchestratorError, Profile, Proposal, TaskSpec, TaskState
from .project import atomic_write, digest, initialize, load_yaml


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(prog="orchestrator", description="Project-driven, provider-neutral local orchestration (v0.1 alpha)")
    cli.add_argument("--version", action="version", version=__version__)
    cli.add_argument("--project", type=Path, default=Path.cwd(), help="Git worktree root; put this option before the command")
    commands = cli.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("--name", default="my-project")
    commands.add_parser("doctor")
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
    approve.add_argument("--scope", required=True, help="exact hash displayed by status")
    approve.add_argument("--by", required=True)
    accept = commands.add_parser("accept")
    accept.add_argument("task_id")
    accept.add_argument("--by", required=True)
    schema = commands.add_parser("schema")
    schema.add_argument("kind", choices=["profile", "task", "result", "state", "artifact", "proposal"])
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
        model = {"profile": Profile, "task": TaskSpec, "result": AgentResult, "state": TaskState, "artifact": Artifact, "proposal": Proposal}[args.kind]
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
    engine = Engine(root)
    try:
        if args.command == "trust":
            return engine.trust(args.by), 0
        if args.command == "doctor":
            report = engine.doctor()
            return report, 0 if all(item["ok"] for item in report.values()) else 1
        if args.command == "create":
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
            state = engine.approve(args.task_id, args.scope, args.by)
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
