# Architecture: v0.2

## Layers and responsibilities

`Supervisor -> TaskSpec -> deterministic Engine -> role-specific providers/validators` is the core boundary. The Supervisor performs semantic intake, not orchestration authority. The engine alone chooses executable phase transitions and checks budgets, approvals, artifacts and workspace integrity. Policies, skills and knowledge remain project-owned rather than predefined domains.

The modules are:

- `models.py`: stable TaskSpec/Profile plus versioned task state and validator configuration.
- `contracts.py`: PlanResult, ImplementationResult, ReviewResult, TaskDraft, SupervisorResult, IntakeState.
- `supervisor.py`: proposal/clarification invocation, policy normalization, exact-scope operator confirmation.
- `engine.py`: sequential `build-review` execution, approval/acceptance and named validation.
- `providers.py`: CLI adapters and schema-parameterized RunRequest; fresh sessions and phase-specific tools.
- `validators.py`: executable resolution, static preflight, guarded execution and explicit user registration.
- `project.py`: profile/context loading, fingerprints, path checks and cooperating-controller lock.
- `store.py`: transactional SQLite state/events/intakes and immutable artifact references.
- `knowledge.py`: human-governed knowledge/policy/skill promotion, unchanged as a separate lifecycle.
- `cli.py`: user-facing commands, including ask/start and explicit human gates.

Provider implementations remain Python registry entries injected into `Engine(root, registry=...)`. No arbitrary class/module import is taken from project configuration. Additional vendors are extension points, not implemented adapters in this release.

## Natural-language intake

`ask` checks trusted effective context, required validator executables, input size, provider capabilities and budgets before making one Supervisor call. Normal intake requires registered validators; explicitly advisory intake may omit them. New profiles declare a supervisor role. Old profiles fall back to their planner binding without a profile mutation.

The Supervisor receives the user's request, bounded clarification history, approved project context and available validator **names**. It produces a proposal, concrete clarification questions, or a blocked result. IDs come from the operator/controller, never the model. Machine permissions, command registration, approvals and workflow graphs are not representable in TaskDraft.

The controller validates the output, rejects unknown validators and external effects, and raises normal write requests below T2 to T2 with a visible note. All tasks originating from ask retain explicit execution approval regardless of the profile's lower-tier default. Advisory mode requires T0/no validators and cannot silently turn into writing work. Classification is still model-assisted, not a complete detector of every external consequence.

Intakes live in a dedicated SQLite table. Successful outputs also have immutable hashed Supervisor artifacts. Proposal confirmation binds the intake ID, task, request, profile, original worktree snapshot, artifact hash and cumulative execution accounting. `start` rechecks that scope/current state and transactionally creates a task while marking the intake consumed. It never creates an execution approval. The CLI then runs planning unless `--no-run` is selected.

An interruption after registration but before planning leaves a ready task; inspect `intake <id>`/`status <task-id>` and use `run`, not a second `start`. An interrupted Supervisor call creates no task. A stale running intake is not implicitly replayed; inspect it and start a new intake. Clarifications are fresh calls with explicit history, limited to three rounds. Their calls/time count toward the created task's budget.

## Execution and result versioning

New TaskState rows have `schema_version: 2`; existing rows missing new fields remain schema v1. TaskSpec and Artifact schemas remain version 1. v1 tasks request legacy AgentResult on every model phase and retain the outcome-only review compatibility rule introduced in commit 2067408.

v2 phases request separate result schemas. All model-facing fields are required, unknown properties are forbidden, and no new result format is silently coerced from an old one. The reviewer has `blocking_findings`, `observations`, and `evidence`. A blocked response stops; a requested change or any blocker requests bounded repair; explicit approval with no blockers requests human acceptance. Non-blocking observations are preserved in artifacts but never interpreted as defects.

The phase graph is still the single built-in sequential build-review workflow. T0 only plans/answers and requests acceptance. Writing tasks implement, validate and freshly review before acceptance. Repair increments the implementation attempt and consumes the same call/time budget. Arbitrary graphs, parallel workers, native subagents and automatic model fallback remain outside v0.2.

Reviewer inputs omit Supervisor conversations, implementation summaries and plans. They contain task criteria, approved project context and runner validation evidence. They can inspect current project files, so a fresh invocation is not proof of independent reasoning or isolation from all model-written content on disk.

## Validators

`doctor` and task preflight resolve every selected executable without running validator code. A slash-containing relative executable is anchored at the project root; a bare command uses PATH; an absolute executable stays absolute. Symlinked virtualenv interpreters are deliberately not resolved to their underlying system binary. Inspection does not certify shebang interpreters, installed modules or arbitrary argument semantics.

`validator check` is a separate operator-authorized execution path using the same runner, filtered environment and integrity checks as task validation. Python bytecode generation is disabled by default; explicit user environment entries can configure test behavior but cannot override reserved path/home/loader/credential-like keys. This is convenience and defense in depth, not an OS sandbox.

`generated_paths` contains literal project-relative directories. The runner rejects traversal, globs, symlink escape, overlap with tracked paths and overlap with protected paths. Only mutations within those untracked directories are allowed during that validator. The roots are rechecked afterwards. Generated output is recorded separately; other mutations cause failure with changed paths. Validation evidence is retained even when the process returns zero but violates the integrity guard.

Active policy/context hashes and a separate control-file snapshot detect edits to `.orchestrator` outside runtime. Worktree snapshots preserve the v0.1 digest ordering, cover tracked/nonignored untracked files, and ignore `.DS_Store`. Git metadata, ignored output and hostile same-user manipulation remain documented limitations.

## Persistence and migration

Runtime database schema 2 adds `intakes` without rewriting existing task/event/artifact rows. `PRAGMA user_version=2` prevents the older executable from consuming new state unknowingly. Back up the entire stopped runtime before upgrading; downgrades are not supported.

Effective profile fingerprints omit empty newly added validator `env`/`generated_paths` fields, preserving v0.1 hashes for unchanged configurations. Adding a nonempty setting, role or approved context still invalidates trust and task bindings. New task approval scopes also include result-contract version and intake/mandatory-approval metadata. Existing v1 scopes keep the original calculation.

All files, SQLite, and CLIs still run under a local user account. Transactions, hashes and locks provide consistency between cooperating processes, not authenticated authority against hostile actors. See SECURITY.md.

## Upstream interfaces

The v0.1 CLI invocation controls that the owner tested live are retained. v0.2 selects a different JSON Schema per role through the existing structured-output interfaces:

- https://developers.openai.com/codex/noninteractive
- https://code.claude.com/docs/en/headless
- https://code.claude.com/docs/en/cli-reference

These primary-source interfaces were reviewed during v0.2 implementation. Version/help probes check expected flags, not authenticated end-to-end compatibility. The new schemas and Supervisor require a live v0.2 smoke test after the offline suite.


## v0.3 agent-facing dispatch

`ApplicationService` exposes only the fixed-project agent operations in `TOOLS`.
`StdioServer` maps the advertised MCP schemas to that service. `JobQueue` stores
requests/results in runtime/jobs.sqlite3 separately from the existing kernel DB.
A unique request ID binds action/arguments; atomic claims and an exclusive worker
lock prevent duplicate cooperative execution. A completed dispatch job is not a
completed task. Job state and task state are distinct and intentionally visible.

The MCP process never calls provider.execute. A manually started worker dispatches
Supervisor.ask or Engine.run with the queued profile/worktree binding, fresh engine
state and a cancellation callback. Existing kernel gates remain authoritative.
Agent-facing run rejects ungated write policies rather than treating a host-client
approval prompt as an execution grant. Direct operator CLI interfaces are retained.

Protocol scope, installation, supported tool names, limits and restart behavior
are specified in MCP.md. No domain taxonomy, provider identity or client-specific
model role is introduced into the kernel. The stdio subset advertises only tools,
not sampling, elicitation or experimental MCP task support.


## v0.5 capability/provider layer

The fixed sequential workflow remains unchanged, but role binding now passes
through CapabilityResolver. Semantic capabilities are distinct from runtime
adapter capabilities. New tasks freeze effective requirements and provider
resolution before the first provider call; approval and audit provenance include
that resolution. See CAPABILITIES.md.


## v0.6 workflow/DAG layer

New tasks bind a compiled Workflow Schema v1 from the trusted profile. The
scheduler validates the graph and executes one ready node at a time. Agent nodes
resolve v0.5 capabilities per node; validator nodes remain deterministic
controller operations. Typed artifact edges control what downstream agents
receive. HumanGate/write-set/acceptance remain outside model authority.

TaskState v4 stores workflow digest/order/current node and per-node status,
artifact/provisioning provenance. v1-v3 tasks retain the legacy state machine.


## v0.6.2 workflow registry/binding

The Engine compiles a trusted workflow registry at startup. Package templates
and profile-defined templates are authority; a task merely selects an entry.
Task selection therefore does not alter the profile digest. The selected
workflow ID/digest is frozen in TaskState and a state-specific executor is
resolved from that frozen ID on every preflight/run.

Supervisor output may reference only advertised registry IDs. Explicit
user/controller selection is kept outside TaskSpec business semantics and wins
over a conflicting model suggestion.


## v0.7 isolated writable execution

WorkflowExecutor now has two scheduling paths. Shared nodes retain the
declaration-ordered v0.6 path. A ready set of `workspace: isolated` writable
nodes is treated as one approval-bound batch. Provider calls may run in a bounded
thread pool, but those threads receive only immutable RunRequest inputs and call
provider adapters; SQLite, TaskState, artifacts and events remain controller-
thread operations.

`workspaces.py` owns the effect boundary. It creates a temporary integration
worktree, materializes the current non-control project snapshot into a detached
seed commit, and creates one detached worker worktree per node. Per-node
ownership is verified before a binary patch is accepted. Patches are integrated
in compiled workflow order away from the project worktree, then one aggregate
patch is applied only if the root/control/protected snapshots are still the
approved values.

This makes provider completion nondeterministic while keeping effect ordering,
state transitions and downstream validation deterministic. Registered validators
and reviewers run against the integrated project state, never as a substitute
branch-local check.

The execution approval scope and HumanGate preview include the full isolated
batch, node ownership and worker bound. Normal cleanup removes worktrees;
interrupted running tasks use conservative recovery to remove stale worktrees
without replay. See `PARALLEL_EXECUTION.md`.

## v0.8 adaptive task-scoped orchestration

The Supervisor output contract may now contain either a trusted `workflow_ref`
or a complete task-scoped Workflow Schema v1 proposal. The latter is structure,
not new authority. Before the Start HumanGate the controller compiles it using
the same DAG validator as trusted workflows, checks its semantic capabilities
against the existing registry, verifies isolated ownership against the proposed
task `allowed_paths`, and resolves every active agent node through existing
provider policy.

An adaptive intake stores the exact workflow separately from the legacy
Supervisor TaskDraft and includes it in the immutable Supervisor artifact and
intake scope. Start confirmation displays the compiled graph and its
`task_scoped_only` persistence status. Once confirmed, TaskState v5 embeds that
workflow spec plus its semantic digest. On later process starts
`Engine.workflow_for_state` recompiles the persisted graph and rejects any
ID/digest drift before execution.

Trusted/manual workflow tasks continue to use TaskState v4. The WorkflowExecutor
is unchanged in authority: v0.8 adaptive graphs reuse v0.5 capability resolution,
v0.6 typed DAG semantics and v0.7 isolated integration rather than adding a
parallel execution bypass.

Conversation revision is represented as a new intake linked by `reply_to`.
A successful revised intake marks the former proposed intake `superseded`.
There is no mutation-in-place of a confirmed TaskState workflow.

Reusable template promotion is a separate operator path in
`workflow_templates.py`. It requires a final succeeded task with a reviewed
snapshot, freezes an evidence-backed candidate scope, then writes a versioned
project workflow only after exact operator confirmation. Because this changes
project configuration, the resulting profile digest is intentionally untrusted
until normal re-trust.


## v0.8.4 guarded single-writer path

The v0.7 `WorkspaceManager` is now also the write-effect boundary for ordinary
exact-scope shared implementers. Workflow scheduling semantics remain sequential,
but before the provider call the controller synthesizes a single isolated writer
whose ownership is the task's `allowed_paths`. The provider runs there; only a
validated completed result can proceed to `finalize_node -> integrate ->
apply_integrated`.

This reuses the same deterministic patch provenance as isolated parallel
execution without changing workflow authority. The effective isolation is an
execution hardening beneath the declared DAG. Repositories without HEAD are
supported by initializing the disposable runtime integration repository directly
from the approved manifest.
