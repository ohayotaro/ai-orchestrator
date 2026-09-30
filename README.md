# AI Orchestrator

Project-driven, provider-neutral orchestration for existing AI clients.
**v0.8 alpha** adds adaptive, task-scoped workflow authoring: users can describe
the desired outcome while the Supervisor reuses trusted templates or proposes a
bounded DAG for that task. Persistent template installation remains an explicit
operator/profile action. This remains a trusted-local application, not
authenticated human identity or a general OS-isolated control plane.

```text
User <-> Claude Code / Codex + portable Skill
                    |
           MCP serve --single-terminal
                    |
       propose -> Supervisor -> task proposal
                    |
         host confirmation: start?
                    |
                 Planner
                    |
       host confirmation: execute this attempt?
                    |
       Implementer -> validators -> fresh Reviewer
                    |
         host confirmation: accept result?
                    |
                 succeeded
```

Workers run in separate managed processes, not in the conversational agent's
session. After initial setup and project trust, normal work can remain in the
same client terminal **when the client supports interactive form elicitation**.
Unsupported forms, No/cancel, expired dialogs and changed scopes never auto-approve.

## v0.4.1 refinements

- Confirmation uses an explicit **Yes / No enum choice** rather than a checkbox plus Accept.
- New Supervisor write tasks declare exact `allowed_paths`; the kernel records a
  `write_set` artifact and fails if implementation changes any other tracked/nonignored path.
- Use `wait_job` for bounded waiting. With an MCP progress token, the server emits
  `notifications/progress`; repeated polling and "continue" are normally unnecessary.
- Frontends should use write_set + validation + review artifacts instead of running
  their own git diff/status or rerunning tests solely to re-check Orchestrator evidence.

Legacy/manual tasks without an allowed-path contract retain prior behavior.

## v0.5 capability-based provider resolution

v0.5 generalizes provider selection without introducing DAG execution. Roles and
Supervisor-generated tasks can declare semantic requirements independently of
provider names. Fixed provider bindings still win; otherwise ordered candidates
or explicit provider priorities resolve the first eligible Provider Adapter v2.

Resolution is deterministic, frozen into new task state before billable calls,
included in HumanGate/approval provenance and revalidated on later runs. There is
no automatic "best model" ranking.

```bash
orchestrator capabilities
```

shows the registry, effective provider descriptors and baseline role resolution.
See **[Capability Registry and Provider Adapter v2](docs/CAPABILITIES.md)**.

Existing profiles with no new capability fields keep their previous digest and
do not need re-trust merely because the package was upgraded. Explicit capability,
candidate or priority changes are normal profile changes and do require re-trust.

## v0.6 declarative Workflow Schema / DAG

v0.6 moves the existing sequential build-review flow onto a versioned Workflow
Schema v1. The default `workflow: build-review` requires no configuration change:
it is now a built-in DAG with typed artifacts and deterministic node ordering.

Custom workflows can define multiple read-only analysis/planning nodes that
converge on a gated implementation, registered validators and independent review.
Each agent node resolves semantic capabilities through the v0.5 Provider Resolver;
provider/model identity is not baked into the graph.

Execution remains deliberately **sequential**. v0.6 validates dependencies,
cycles, typed artifact edges, advisory/write safety, repair semantics and
cross-provider independence before running. Writable parallelism and isolated
worktrees remain v0.7 work.

```bash
orchestrator workflow
```

shows the active compiled workflow, digest, deterministic order and artifact
producers. MCP `inspect_project` exposes the same report. New tasks persist
Workflow/DAG provenance in TaskState schema v4.

See **[Workflow Schema v1](docs/WORKFLOWS.md)**.

## v0.6.2 task-scoped trusted workflow selection

Workflow shape is now separable from profile authority. `inspect_project` and
`orchestrator workflows` expose the trusted registry. The package provides
`build-review` and `branched-review`; project-defined workflows already present
in the trusted profile are also selectable.

Selecting a listed workflow for one task does **not** edit config or require
re-trust:

```bash
orchestrator ask --workflow branched-review "Implement the requested change"
# or for a manual TaskSpec:
orchestrator create --task-file task.yaml --workflow branched-review
```

The selected ID/digest is frozen into intake/task provenance and displayed by
the Start HumanGate. Adding a new workflow definition remains a profile/trust
operation; models cannot install or trust one.

## v0.8 adaptive task-scoped orchestration

Normal users no longer need to choose a workflow ID, edit `.orchestrator/config.yaml`,
design a DAG, decide whether work should be parallel, or name a provider. When
`workflow_ref` is omitted, the Supervisor first considers the trusted workflow
registry. If no trusted template expresses the requested structure, it may
propose one bounded Workflow Schema v1 DAG for that intake.

The proposed DAG is **ephemeral authority**: it is embedded in the immutable
Supervisor artifact, bound into the Start HumanGate, and persisted with the task
in TaskState v5. It may only use the already configured roles, semantic
capabilities, validators and policy. It cannot install providers, validators,
models, executable commands, permissions, policies or external effects.

An unconfirmed proposal can be revised conversationally with `reply_to`; a
successful revision supersedes the older proposal so a stale confirmation cannot
register it. Adaptive execution then uses the existing v0.5-v0.7 machinery,
including capability resolution, exact allowed paths, isolated worktrees,
bounded parallelism, deterministic integration, validators, independent review
and final acceptance.

Successful task-scoped workflows can optionally become reusable project
templates, but only through explicit operator commands:

```bash
orchestrator workflow-candidate I-... --as my-template
orchestrator workflow-save I-... --as my-template --scope <exact-scope> --by "$USER"
```

Saving records version/provenance in project configuration, changes profile
authority and therefore requires the normal inspection/re-trust ceremony. No MCP
agent tool can persist or trust a template.

See **[Adaptive orchestration](docs/ADAPTIVE_ORCHESTRATION.md)**.

## Important approval distinction

v0.4 uses MCP `elicitation/create`, not ordinary tool permission prompts,
`destructiveHint`, "always allow", an agent boolean or a chat "yes". The host
receives the server-built task/plan/evidence preview and returns an explicit form
response. Every successful response is bound to the session, operation, exact
state, current worktree and expiration, with a local audit record.

**The protocol does not attest that a human personally answered.** Clients or
Claude Code hooks can auto-answer elicitation. Enabling single-terminal mode
therefore explicitly trusts the local client's response channel. Use an
interactive client with approval automation disabled when personal confirmation
is required. No authenticated live v0.4 client test is claimed by the offline suite.
See [Single-terminal design and setup](docs/SINGLE_TERMINAL.md).

## Install / upgrade

Use Python 3.11+ on Linux/macOS. An old Python 3.9 virtualenv must be replaced,
not upgraded by installing a newer pip. Existing users should stop active workers
and back up each project's complete `.orchestrator/runtime/` before upgrading.

```bash
git pull --ff-only
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev,interop]'
.venv/bin/python -m pytest -q
.venv/bin/orchestrator --version  # 0.8.0
```

For a new checkout, first create a new environment with `python3.13 -m venv .venv`
(or Python 3.11/3.12). Install/authenticate Claude Code and Codex CLI separately.
No model name is fixed; configured CLI defaults apply unless the profile specifies
one. Additional provider adapters, arbitrary DAGs and parallel workspaces remain
outside this release.

## Opt in for the existing calculator fixture

Use a normal terminal for this one-time host setup. Do not reinitialize or reset
existing projects, tasks or uncommitted calculator changes.

```bash
ORCH=/Users/ohayotaro/ai-orchestrator/.venv/bin/orchestrator
PROJECT=/Users/ohayotaro/ai-orchestrator-e2e
```

Update your existing MCP entry so its arguments end in `serve --single-terminal`,
or remove/re-add only this server. For Claude Code (local project scope):

```bash
cd "$PROJECT"
claude mcp remove ai-orchestrator --scope local
claude mcp add --transport stdio --scope local ai-orchestrator -- \
  "$ORCH" --project "$PROJECT" serve --single-terminal
"$ORCH" skill --output "$HOME/.claude/skills/ai-orchestrator/SKILL.md" --replace
```

For Codex, update the existing registration:

```bash
codex mcp remove ai-orchestrator
codex mcp add ai-orchestrator -- \
  "$ORCH" --project "$PROJECT" serve --single-terminal
"$ORCH" skill --output "$HOME/.agents/skills/ai-orchestrator/SKILL.md" --replace
```

`skill --replace` makes an adjacent uniquely named backup before replacing a
regular file. It refuses symlinks and never changes client configuration itself.
Inspect registration scope before removing any existing server; do not remove an
unrelated server. Reload/restart the client as needed after configuration changes.

An unchanged profile needs no new trust grant. If configuration changed, inspect
it and explicitly retrust from the operator terminal. v0.4 does not grant trust
through MCP. A manual worker already running is reused; stop it before testing
that automatic startup works. Do not run a second manual worker.

## Ordinary use

Ask the connected client to use ai-orchestrator for a small change. It calls
`inspect_project` then `propose_task`. In opt-in mode, workers start automatically.
The three request tools present native host confirmations:

| Tool | What a confirmed response permits |
| --- | --- |
| `request_start` | Register the proposed task and queue planning only |
| `request_execution` | Authorize the exact implementation attempt and validators, then queue it |
| `request_acceptance` | Accept the exact reviewed result; no commit/push/deployment |

The client must show No/cancel as a real choice and must not answer for the user.
If `inspect_project.host_confirmation.form_supported` is false, remain blocked
or deliberately use the manual operator CLI. There is no silent CLI fallback.

`get_job` reports queue operation state, not task completion. `get_task` is the
canonical task state; `get_artifact` reads hash-verified evidence. A repair requires
a fresh execution confirmation. Do not change files or run additional tests while
an approval scope is pending. Read existing validation evidence instead.

## Compatibility / diagnostics

Plain `orchestrator serve` retains the v0.3 manual-worker/operator-gate behavior.
The existing `ask`, `create`, `start`, `approve`, `run`, `accept`, validator and
knowledge commands remain supported. Task/profile schemas and fingerprints are
unchanged. Gates are stored separately in `runtime/gates.sqlite3`; old artifacts
are not rewritten. `orchestrator gate G-ID` reads the gate/audit metadata.

Managed workers idle-exit after draining the queue. Their private log paths and
startup errors appear in MCP job/inspection output. Repeated failed startups stop
rather than looping indefinitely. Host disconnect does not undo already dispatched
work; it cancels an unanswered confirmation, while the separate worker completes
accepted queue work and idle-exits. Interrupted effects are never automatically
replayed.

## Roadmap

The current v0.8 baseline combines deterministic capability/provider resolution,
declarative workflows, isolated parallel execution and adaptive task-scoped DAG
proposal behind the existing HumanGate/evidence boundaries. The next development
phase is observability, budgets and recovery hardening.

See **[ROADMAP.md](ROADMAP.md)** for the planned path from completed v0.5 provider resolution and v0.6 workflow DAGs, isolated parallel execution,
adaptive/user-defined orchestration, observability and stable v1.0 contracts.
The roadmap is directional rather than a release-date commitment and may be
revised from measured E2E evidence.

## Verification / limitations

Tests cover malformed/negative confirmations, correlation and replay, stale state,
expiration, cancellation, native tool paths, worker lifecycle and subprocess wire
E2E with model shims plus actual pytest. Optional official MCP SDK interoperability
runs in CI via `.[interop]`. Those checks are not live Claude Code/Codex UI tests.
The owner previously reported complete v0.3 flows from both clients; those do not
verify v0.4 elicitation or new worker-environment behavior.

Read [v0.4 design/setup](docs/SINGLE_TERMINAL.md) and [changelog](CHANGELOG.md).
Earlier [architecture](docs/ARCHITECTURE.md), [security](docs/SECURITY.md),
[MCP v0.3 guide](docs/MCP.md) and [migration](docs/MIGRATION.md) describe the
retained legacy mode; the v0.4 document supersedes their manual-only claims for
explicit single-terminal mode. Trust/configuration changes remain operator-only
in both modes. License remains to be determined.


## v0.7 isolated parallel execution

Trusted project workflows may mark writable implementer nodes with
`workspace: isolated` and exact `write_paths`. Independent isolated nodes with
disjoint ownership may execute concurrently. `policy.max_parallel_workers`
bounds the worker pool and defaults to `1`, so existing projects remain
sequential unless the trusted profile explicitly opts in.

The controller seeds private Git worktrees from the exact approved project
snapshot, executes providers only in those worktrees, rejects writes outside the
node's ownership, and prepares each result as a binary patch. Patches are applied
to an integration worktree in compiled workflow order. Only after every branch
integrates successfully is one aggregate patch applied to the user's worktree.
Registered validators and fresh review then run against that integrated result.

The execution HumanGate binds the complete ready isolated batch, ownership and
worker bound. Provider threads never write TaskState/SQLite directly; controller
state transitions remain serialized. Failed/cancelled batches do not partially
apply successful siblings. Recovery removes stale isolated worktrees without
automatic replay.

See `docs/PARALLEL_EXECUTION.md` and `docs/SECURITY.md` for the exact boundary
and limitations.
