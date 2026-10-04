"""Small JSON-output CLI. Approvals are explicit local operator actions."""

from __future__ import annotations

import argparse
import os
import uuid
import json
import sys
import sqlite3
from pathlib import Path
from typing import Any

from pydantic import ValidationError
import yaml

from . import __version__, knowledge, workflow_templates
from .capabilities import CapabilityRegistryDescriptor, ProviderDescriptor, ProviderResolution
from .engine import Engine
from .contracts import IntakeState, PlanResult, ImplementationResult, ReviewResult, SupervisorResult
from .supervisor import Supervisor
from .validators import register_validator
from .models import AgentResult, Artifact, OrchestratorError, Profile, Proposal, TaskSpec, TaskState, WorkflowArtifactSpec, WorkflowInputSpec, WorkflowNodeSpec, WorkflowSpec
from .persistence import persistence_compatibility_report
from .project import atomic_write, digest, initialize, load_yaml
from .runtime_options import ModelVariantResolution, RuntimeOptionsDescriptor, RuntimeOverride, RuntimeValueDescriptor


def parser() -> argparse.ArgumentParser:
    cli = argparse.ArgumentParser(prog="orchestrator", description="Project-driven, provider-neutral local orchestration (v0.12 alpha)")
    cli.add_argument("--version", action="version", version=__version__)
    cli.add_argument("--project", type=Path, default=Path.cwd(), help="Git worktree root; put this option before the command")
    commands = cli.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="Run the fixed-project MCP stdio frontend")
    terminal_mode = serve.add_mutually_exclusive_group()
    terminal_mode.add_argument(
        "--single-terminal",
        dest="single_terminal",
        action="store_true",
        help="Use client-mediated confirmation forms and automatic separate workers (default)",
    )
    terminal_mode.add_argument(
        "--legacy-terminal",
        dest="single_terminal",
        action="store_false",
        help="Use the legacy manual worker/operator-terminal authority flow",
    )
    serve.set_defaults(single_terminal=True)
    serve.add_argument("--gate-timeout", type=float, default=120, help="Seconds to answer a host form (maximum 600)")
    worker = commands.add_parser("worker", help="Run queued jobs from a separate operator terminal")
    worker.add_argument("--once", action="store_true", help="Process at most one job and exit")
    worker.add_argument("--poll-interval", type=float, default=1.0)
    worker.add_argument("--idle-seconds", type=float, help="Exit after this idle period instead of staying resident")
    job = commands.add_parser("job", help="Inspect a durable queued operation")
    job.add_argument("job_id")
    cancel_job = commands.add_parser("cancel-job", help="Request queued/running operation cancellation")
    cancel_job.add_argument("job_id")
    skill = commands.add_parser("skill", help="Export the portable Agent Skill; never modify client config implicitly")
    skill.add_argument("--output", type=Path, required=True)
    skill.add_argument("--replace", action="store_true", help="Back up an existing exported Skill, then replace it explicitly")
    gate = commands.add_parser("gate", help="Inspect a stored host-confirmation record without changing it")
    gate.add_argument("gate_id")
    init = commands.add_parser("init")
    init.add_argument("--name", default="my-project")
    doctor = commands.add_parser("doctor")
    doctor.add_argument("--validators-only", action="store_true")
    commands.add_parser("capabilities", help="Inspect the semantic capability registry and deterministic provider resolution")
    commands.add_parser("provider-plugins", help="Inspect provider plugin entry-point metadata, trusted pins and load/conformance status")
    commands.add_parser("persistence", help="Inspect persisted-contract and migration compatibility rules")
    workflow = commands.add_parser("workflow", help="Inspect a trusted compiled Workflow Schema v1 DAG")
    workflow.add_argument("--ref", dest="workflow_ref", help="Trusted workflow ID; defaults to the project default")
    commands.add_parser("workflows", help="List the trusted workflow registry without changing the profile")
    workflow_candidate = commands.add_parser("workflow-candidate", help="Inspect an evidence-backed task-scoped workflow before optional persistent save")
    workflow_candidate.add_argument("intake_id")
    workflow_candidate.add_argument("--as", dest="template_id", required=True)
    workflow_candidate.add_argument("--replace", action="store_true", help="Preview revision of an existing project workflow template")
    workflow_save = commands.add_parser("workflow-save", help="Persist a successful task-scoped workflow into project config; requires subsequent re-trust")
    workflow_save.add_argument("intake_id")
    workflow_save.add_argument("--as", dest="template_id", required=True)
    workflow_save.add_argument("--scope", required=True)
    workflow_save.add_argument("--by", required=True)
    workflow_save.add_argument("--replace", action="store_true")
    ask = commands.add_parser("ask", help="Propose a TaskSpec from natural language; never auto-approve execution")
    ask.add_argument("prompt")
    ask.add_argument("--task-id")
    ask.add_argument("--advisory", action="store_true")
    ask.add_argument("--reply-to", help="Intake ID to answer clarification or revise an unconfirmed proposal")
    ask.add_argument("--workflow", dest="workflow_ref", help="Select an already-trusted workflow for this intake/task")
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
    create.add_argument("--require", action="append", default=[], metavar="ROLE=CAPABILITY",
                        help="Add a semantic capability requirement to this task; repeat as needed")
    create.add_argument("--workflow", dest="workflow_ref", help="Select an already-trusted workflow for this task")
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
    schema.add_argument("kind", choices=["profile", "task", "result", "plan", "implementation", "review", "supervisor", "intake", "state", "artifact", "proposal", "capability-registry", "provider-descriptor", "provider-resolution", "workflow", "workflow-node", "workflow-input", "workflow-artifact", "runtime-value", "runtime-options", "runtime-override", "model-variant-resolution"])
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
    if args.command == "worker":
        from .worker import run_worker
        result = run_worker(root, once=args.once, poll_interval=args.poll_interval, idle_seconds=args.idle_seconds)
        job = result.get("job") or {}
        return result, 1 if job.get("status") in ("failed", "cancelled", "interrupted") else 0
    if args.command in ("job", "cancel-job"):
        from .service import ApplicationService
        method = "get_job" if args.command == "job" else "cancel_job"
        return ApplicationService(root).invoke(method, {"job_id": args.job_id}), 0
    if args.command == "gate":
        from .human_gates import GateStore, HumanGateBroker
        from .project import Project
        store = GateStore(Project(root))
        try:
            return HumanGateBroker.describe(store.get(args.gate_id)), 0
        finally:
            store.close()
    if args.command == "skill":
        from importlib.resources import files
        if args.output.is_symlink():
            raise OrchestratorError("refusing to replace a symlink Skill")
        backup = None
        if args.output.exists():
            if not args.replace:
                raise OrchestratorError("skill output already exists; no file was overwritten")
            if not args.output.is_file() or args.output.stat().st_size > 1024 * 1024:
                raise OrchestratorError("existing Skill is not a bounded regular text file")
            backup = args.output.with_name(args.output.name + ".bak-" + uuid.uuid4().hex[:12])
            with backup.open("x", encoding="utf-8") as stream:
                stream.write(args.output.read_text(encoding="utf-8"))
        atomic_write(args.output, files("ai_orchestrator").joinpath("assets/SKILL.md").read_text(encoding="utf-8"))
        return {"path": str(args.output), "backup": str(backup) if backup else None, "installed_into_client": False}, 0
    if args.command == "init":
        initialize(root, args.name)
        return {"project": str(root), "initialized": True, "trusted": False}, 0
    if args.command == "schema":
        model = {"profile": Profile, "task": TaskSpec, "result": AgentResult, "state": TaskState, "artifact": Artifact, "proposal": Proposal, "plan": PlanResult, "implementation": ImplementationResult, "review": ReviewResult, "supervisor": SupervisorResult, "intake": IntakeState, "capability-registry": CapabilityRegistryDescriptor, "provider-descriptor": ProviderDescriptor, "provider-resolution": ProviderResolution, "workflow": WorkflowSpec, "workflow-node": WorkflowNodeSpec, "workflow-input": WorkflowInputSpec, "workflow-artifact": WorkflowArtifactSpec, "runtime-value": RuntimeValueDescriptor, "runtime-options": RuntimeOptionsDescriptor, "runtime-override": RuntimeOverride, "model-variant-resolution": ModelVariantResolution}[args.kind]
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
        if args.command == "capabilities":
            return engine.capability_report(), 0
        if args.command == "provider-plugins":
            return engine.provider_plugin_report(), 0
        if args.command == "persistence":
            return persistence_compatibility_report(), 0
        if args.command == "workflow":
            return engine.workflow_report(args.workflow_ref), 0
        if args.command == "workflows":
            return engine.workflow_registry_report(), 0
        if args.command == "workflow-candidate":
            return workflow_templates.candidate(engine, args.intake_id, args.template_id, replace=args.replace), 0
        if args.command == "workflow-save":
            return workflow_templates.save(
                engine, args.intake_id, args.template_id, args.scope, args.by, replace=args.replace
            ), 0
        if args.command == "ask":
            supervisor = Supervisor(engine)
            intake = supervisor.ask(args.prompt, task_id=args.task_id, advisory=args.advisory,
                                    reply_to=args.reply_to, workflow_ref=args.workflow_ref)
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
            requirements: dict[str, list[str]] = {}
            for item in args.require:
                if "=" not in item:
                    raise OrchestratorError("--require must use ROLE=CAPABILITY")
                role, capability = item.split("=", 1)
                if not role or not capability:
                    raise OrchestratorError("--require must use nonempty ROLE=CAPABILITY")
                requirements.setdefault(role, []).append(capability)
            state = engine.create(
                TaskSpec.model_validate(load_yaml(args.task_file)),
                capability_requirements=requirements or None,
                workflow_ref=args.workflow_ref,
            )
        elif args.command == "run":
            state = engine.run(args.task_id)
        elif args.command == "status":
            state = engine.store.get(args.task_id)
            result = state.model_dump()
            if state.status == "running":
                result["recovery"] = engine.recovery_status(args.task_id)
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
        if os.environ.get("CLAUDECODE") and (args.command in ("ask", "run") or (args.command == "start" and not args.no_run)):
            raise OrchestratorError("this command would start a nested model session; use MCP single-terminal requests or a separate operator terminal. No task was created or changed")
        if args.command == "serve":
            from .mcp_server import serve
            serve(args.project.resolve(), single_terminal=args.single_terminal, gate_timeout=args.gate_timeout)
            return 0
        result, code = dispatch(args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return code
    except (OrchestratorError, ValidationError, ValueError, OSError, sqlite3.Error, yaml.YAMLError) as exc:
        # Validation errors may include supplied content; never paste secrets into profiles/tasks.
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
