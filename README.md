# AI Orchestrator

Project-driven, provider-neutral orchestration for existing AI clients.
**v0.9.2 alpha** closes the v0.9 line with provider-local model/effort resolution,
read-only workspace hardening, observable dispatch provenance and explicit
provider-compatibility boundaries. Supervisor, Planner and Reviewer execute
against disposable project snapshots that omit `.orchestrator`. Independent
review may use a different provider family or explicit unequal model IDs within
one family. AGY read-only headless roles are conditionally supported: they may
run when AGY native scoped permissions are sufficient, but Orchestrator does not
modify or attest that permission policy and fails closed on denial. This remains
a trusted-local application, not authenticated human identity or a general
OS-isolated control plane.

```text
User <-> Claude Code / Codex + portable Skill
                    |
           MCP serve
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
.venv/bin/orchestrator --version  # 0.9.2
```

For a new checkout, first create a new environment with `python3.13 -m venv .venv`
(or Python 3.11/3.12). Install/authenticate the provider CLIs you intend to use separately. Built-in adapters are available for Claude Code, Codex CLI, and Antigravity CLI (`agy`).
No vendor model list is fixed in the kernel. v0.9 resolves provider-local
model/effort after provider selection using task/node explicit override > trusted
profile setting > adapter default. `inspect_project.provider_compatibility`
separately reports execution compatibility without turning that metadata into
authority. AGY Supervisor/Planner/Reviewer report
`conditional_native_permissions`: the role remains routable, but native scoped
permission sufficiency is an operator/provider concern rather than something the
kernel claims to verify. Built-in adapters report honest pass-through
limitations when their CLIs do not expose a complete reliable catalog. AGY
permission denials expose only adapter-sanitized diagnostics (for example action
type, executable basename and shell-shape flags) through the official intake/task
interfaces; raw denied commands and arguments are not retained. Adaptive
task-scoped DAGs and isolated parallel execution still cannot install new
providers, validator commands, policies or external-effect authority.

## Configure the existing calculator fixture

Use a normal terminal for this one-time host setup. Do not reinitialize or reset
existing projects, tasks or uncommitted calculator changes.

```bash
ORCH=/Users/ohayotaro/ai-orchestrator/.venv/bin/orchestrator
PROJECT=/Users/ohayotaro/ai-orchestrator-e2e
```

A normal `serve` registration now defaults to single-terminal operation. The
`--single-terminal` flag remains accepted for compatibility but is unnecessary.
Use `serve --legacy-terminal` only when you deliberately want the old manual
worker/operator-terminal flow. For Claude Code (local project scope):

```bash
cd "$PROJECT"
claude mcp remove ai-orchestrator --scope local
claude mcp add --transport stdio --scope local ai-orchestrator -- \
  "$ORCH" --project "$PROJECT" serve
"$ORCH" skill --output "$HOME/.claude/skills/ai-orchestrator/SKILL.md" --replace
```

For Codex, update the existing registration:

```bash
codex mcp remove ai-orchestrator
codex mcp add ai-orchestrator -- \
  "$ORCH" --project "$PROJECT" serve
"$ORCH" skill --output "$HOME/.agents/skills/ai-orchestrator/SKILL.md" --replace
```

`skill --replace` makes an adjacent uniquely named backup before replacing a
regular file. It refuses symlinks and never changes client configuration itself.
Inspect registration scope before removing any existing server; do not remove an
unrelated server. Reload/restart the client as needed after configuration changes.

An unchanged profile needs no new trust grant. If configuration changed, inspect
it and explicitly retrust from the operator terminal. No MCP request grants
project trust. A manual worker already running is reused; stop it before testing
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
knowledge commands remain supported. Persisted TaskState v1-v4 remains readable;
trusted/manual workflows continue to create v4 state, while confirmed embedded
adaptive DAGs use v5. Default v0.8 template metadata preserves an unchanged v0.7
profile fingerprint. Gates are stored separately in `runtime/gates.sqlite3`;
old artifacts are not rewritten. `orchestrator gate G-ID` reads the gate/audit metadata.

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
phase first separates provider-local model/effort/runtime-option resolution from
provider identity, then layers usage observability, budgets and recovery
hardening on top of that provenance.

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


## v0.8.1 Antigravity CLI provider

The built-in `agy` adapter lets Antigravity replace Codex as an implementer
without changing Workflow Schema or task prompts. Provider choice remains a
profile/capability-resolution concern.

A fixed provider configuration can look like:

```yaml
providers:
  reasoning:
    adapter: claude
  engineering:
    adapter: agy

roles:
  supervisor:
    provider: reasoning
  planner:
    provider: reasoning
  implementer:
    provider: engineering
  reviewer:
    provider: reasoning
```

Changing provider configuration is a project-authority change and requires the
normal inspect/re-trust ceremony.

The adapter uses AGY headless `stream-json` mode with prompts on stdin,
`--json-schema` structured output, `--sandbox`, and never
`--dangerously-skip-permissions`. Implementation runs use
`--mode=accept-edits`; read-only orchestration phases use `--mode=plan`.
The controller still enforces its own allowed-path/write-set/validator/review
boundaries after provider execution.

Authenticate AGY interactively once before headless use:

```bash
agy
agy --version
```



## v0.8.4 guarded writable execution

Exact-scope writable tasks no longer let a provider edit the user's project
worktree before its structured result is accepted. A shared Workflow Schema
implementer with task `allowed_paths` is executed in a private runtime worktree,
validated there, converted to a verified patch, and only then integrated into the
project. Provider/result failure discards the private workspace.

This is a safety hardening, not new authority, so existing workflow definitions
and approval scopes do not need provider-specific DAG changes. Explicit v0.7
isolated parallel workflows continue to use the same underlying integration path.
Legacy/manual tasks without an exact `allowed_paths` contract retain their
historical behavior.



## v0.8.6 bounded authority-control

Single-terminal conversations can now handle two previously operator-manual
authority cases without exposing arbitrary config editing.

A user can ask to switch an existing provider slot, for example "switch
engineering from AGY back to Codex". The agent first calls
`preview_provider_change`, which returns the exact before/after provider
configuration and proposed profile digest. Only `request_provider_change`
can present the dedicated host HumanGate. Yes applies exactly that adapter
change, clears vendor-specific executable/model/effort overrides, validates
the resulting profile, and trusts only the resulting digest. Active tasks or
unconsumed task proposals block the change.

AGY broad native permission is separate. If the user explicitly asks to allow
`--dangerously-skip-permissions` for a task attempt, the agent must call
`request_provider_permission` before `request_execution`. The permission
gate does not start execution. The grant is bound to the task, attempt, AGY
workflow node(s), profile digest and worktree snapshot; repair or workspace
drift requires a fresh permission gate.

Ordinary execution approval never implies broad provider permission. Arbitrary
policy/config mutation, validator registration and direct trust remain outside
the agent-facing mutation surface.


## v0.8.7 binding lifecycle cleanup

Provider changes can now recover cleanly from unfinished historical bindings
without requiring direct runtime edits. `preview_provider_change` returns
structured `ready` and `blocked_by` fields. If unfinished tasks/intakes block
the change, the agent may call `preview_binding_cleanup` for exact IDs and then
`request_binding_cleanup` to present a separate HumanGate.

Confirmed cleanup moves selected unfinished tasks to `abandoned` and selected
unconsumed intakes to `withdrawn` in one transaction. It never deletes history,
artifacts or task files and never restores/rolls back workspace files. A cleanup
confirmation and a provider-change confirmation remain separate authority
decisions.

Running tasks/intakes cannot be cleaned up through this path; they must first
finish or be stopped/recovered through the appropriate existing control.


## v0.8.8 content-free provider tool telemetry

Antigravity calls now emit a `provider.tool_telemetry` audit event containing
only tool names and aggregate terminal call states/counts. This makes it possible
to distinguish, for example, `write_to_file`, `replace_file_content` and
`run_command` usage without retaining the file path, command, prompt, tool
output, provider response or conversation ID.

Telemetry is observational only. It does not authorize tools and does not change
the AGY denied-action or structured-output fail-closed rules. For isolated
parallel/guarded execution, worker threads write only to per-call in-memory
collectors; the controller persists telemetry after futures return.


## v0.8.9 compact HumanGate previews

HumanGate authority is unchanged, but confirmation forms now render a short
operation-specific summary rather than the complete bound preview JSON. This
avoids relying on client-specific expand/collapse behavior for critical approval
details.

The controller still stores and revalidates the full exact preview and snapshots.
Compact display includes the fields a user needs to decide: task/attempt, allowed
paths, workflow and write ownership, provider/permission override, changed paths,
validation/review outcome, provider adapter before/after, or exact cleanup IDs.

AGY `--dangerously-skip-permissions` forms explicitly state that all AGY-native
tool permission prompts are auto-approved for that scoped session, list retained
controller protections, and state that a separate execution confirmation is
still required.


## v0.8.10 atomic provider change-sets

Provider swaps no longer need to pass through invalid intermediate profiles.
For example, a project with reasoning=Claude and engineering=AGY can atomically
swap to reasoning=AGY and engineering=Claude by previewing one change-set:

```json
{"changes":{"reasoning":"agy","engineering":"claude"}}
```

The controller applies those adapter changes to an in-memory copy of the profile,
clears adapter-specific executable/model/effort overrides for each changed slot,
and validates only the final combined profile against capability and
cross-provider review policy. If valid, a dedicated HumanGate shows every
before/after adapter mapping and the resulting profile digest.

A Yes response performs one atomic config replacement and trusts only the
verified resulting digest. No intermediate same-family provider configuration is
created. Existing single-provider change tools remain available as compatibility
wrappers.


## v0.9.1 read-only provider hardening and model-level review independence

Supervisor, Planner and Reviewer now run against disposable project snapshots that
exclude `.orchestrator` and ignored ambient files. The controller rejects writes
to these read-only snapshots and removes them after each call. Provider-native
headless permission failures remain fail-closed; v0.9.1 does not silently grant
broad AGY permissions.

The compatibility policy `cross_provider_review: true` no longer requires two
vendors in every configuration. Review independence is satisfied by either a
different provider family or explicit unequal provider-local model IDs within the
same family. Thus a single Claude provider slot may run, for example, Sonnet for
implementation and Opus for review via task/node runtime overrides. Effort alone
does not establish independence.

Supervisor executes before TaskState exists. When a user explicitly requests its
model/effort, the agent-facing `propose_task` call may carry
`supervisor_runtime_override`; this is intake-scoped, frozen into intake
provenance and shown in the Start HumanGate. Planner/Implementer/Reviewer
overrides remain task/node-scoped and are proposed by the Supervisor.

Successful provider calls now expose content-free controller dispatch evidence.
Use `get_artifact(kind=provider_provenance)` for task agent nodes and
`get_intake` for Supervisor provenance. The evidence records the exact RunRequest
model/effort/runtime options and workspace isolation facts without prompts,
command lines or response content. It is controller evidence, not independent
provider-side attestation.

The portable Skill keeps control-plane/tool interaction in English but requires
the host agent to explain progress, choices, errors and results in the user's
current conversation language.

Capability and runtime-option reports use the same review-independence semantics
as execution: fixed same-family roles are not rejected before model selection,
while dynamically routed reviewers still prefer a different provider family.

## v0.9.0 provider-local model and effort resolution

v0.9.0 makes provider selection and runtime selection separate, inspectable
contracts:

```text
task / workflow node
  -> semantic capabilities
  -> Provider Resolution
  -> Model Variant Resolution
  -> adapter execution
```

Model Variant Resolution uses deterministic precedence:

```text
task/node explicit override
        >
trusted profile model/effort
        >
adapter default
```

A task-scoped override is ephemeral. It is validated against the selected
workflow, resolved only after the provider is known, frozen into TaskState v6 and
the workflow-node state, and included in approval scope. It does not rewrite
`.orchestrator/config.yaml`. The execution HumanGate shows the exact resolved
provider/adapter/model/effort for the affected implementation node(s).

Conversational requests may therefore express concrete intent such as
"implementation model X with effort=xhigh" or "review only at high effort".
The Supervisor may preserve such an explicit request as `runtime_overrides`;
it is instructed not to increase effort/cost on its own.

Adapters advertise whether model/effort values are enumerated, unsupported or
pass-through. Enumerated values fail closed when unsupported. Pass-through means
the adapter can set the provider-local value but cannot truthfully claim a
complete catalog; the provider runtime remains responsible for validating that
value. AI Orchestrator records that limitation rather than maintaining a stale
kernel-global vendor model list.

Use `orchestrator schema runtime-options`,
`orchestrator schema runtime-override`, and
`orchestrator schema model-variant-resolution` for the wire contracts. MCP
`inspect_project` also reports runtime-option descriptors and current role
resolutions.
