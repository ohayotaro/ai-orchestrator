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


## v0.8.6 authority-control plane

Authority-control introduces two typed flows beside the task DAG.

Persistent provider change:

```text
natural-language request
  -> inspect/preview existing provider slot
  -> deterministic proposed profile + digest
  -> provider-change HumanGate
  -> atomic config mutation
  -> digest verification
  -> trust resulting digest
```

No arbitrary mapping, policy key, validator command, workflow definition or
trust digest can be supplied through this flow.

Task-scoped provider permission:

```text
awaiting_approval task
  -> resolve current writable AGY node(s)
  -> provider-permission HumanGate
  -> persist attempt/snapshot-bound grant
  -> execution HumanGate on the expanded exact scope
  -> RunRequest(provider_permissions=...)
```

The provider adapter sees the dangerous AGY flag only when the executing node
matches a persisted approved grant. Permission grants are task state, not project
profile authority, and are cleared on repair.


## v0.8.7 binding lifecycle control

The authority-control plane now models unfinished binding retirement explicitly:

```text
provider-change preview
  -> ready=false + exact blocked_by task/intake IDs
  -> binding-cleanup preview
  -> binding-cleanup HumanGate
  -> atomic abandoned/withdrawn transitions
  -> provider-change preview again
  -> provider-change HumanGate
```

Cleanup operates on persisted orchestration state only. It deliberately does not
attempt automatic workspace rollback because earlier provider attempts may have
produced legitimate user-visible edits that cannot be safely inferred as
discardable. Filesystem effects remain separate evidence requiring explicit user
handling when desired.


## v0.8.8 provider telemetry channel

`RunRequest` carries an optional in-memory telemetry sink. Adapters may publish
content-free observations to that sink while retaining their normal Contract
return type. AGY parses its stream-json into two independent views: the terminal
result contract and a tool-name/state aggregate.

For guarded/parallel execution each prepared node owns a separate dictionary
collector. Provider threads mutate only their own collector. After all futures
return, the workflow controller persists `provider.tool_telemetry` events on
the controller thread before normal error normalization/integration. Sequential
calls use the same pattern in a local collector.


## v0.8.10 provider change-set transaction

The authority-control plane now supports an atomic provider mapping transaction:

```text
natural-language role/provider request
  -> resolve affected provider slots
  -> preview_provider_change_set
  -> clone current profile in memory
  -> apply all adapter substitutions
  -> validate final profile once
  -> provider-change-set HumanGate
  -> atomic config replace
  -> verify resulting digest
  -> trust resulting digest
```

This deliberately differs from composing single-slot changes. A swap may be
valid only as a simultaneous transition because either half-swap can temporarily
collapse implementer and reviewer onto the same provider family. No intermediate
profile is materialized or trusted.

The historical single-slot API is implemented as a one-entry change-set wrapper
and retains its legacy audit events for compatibility. Multi-slot operations use
`profile_change_set.intent` / `profile_change_set.applied` provenance.


## v0.9.0 runtime-option registry and Model Variant Resolution

Execution now has two independent deterministic routing stages:

```text
semantic requirements
  -> CapabilityResolver / ProviderResolution
  -> ModelVariantResolver / ModelVariantResolution
  -> resolved ProviderConfig
  -> ProviderAdapter.execute
```

`ProviderResolution` continues to bind provider, adapter, family and semantic
capabilities. `ModelVariantResolution` binds the provider-local model, effort
and named runtime options plus a source per dimension, a digest of the adapter's
runtime-option descriptor, limitations and an explicit no-fallback decision.

Each adapter exposes a versioned `RuntimeOptionsDescriptor`. A dimension may be
`enumerated` (complete list, controller validates), `passthrough` (the adapter
can set the value but does not claim a complete catalog), or `unsupported`.
This metadata is adapter data, not Capability Registry data.

Resolution precedence is exact task/node override, then trusted
`ProviderConfig.model/effort`, then adapter default. Workflow preflight resolves
and freezes the result on each active agent node before relevant billable/effectful
work. Role-level compatibility views are also retained when one node owns that
role. Repeated preflight recomputes the descriptor and resolution; any drift in
the frozen result fails closed.

TaskState v6 stores both `runtime_overrides` and
`model_variant_resolutions`. WorkflowNodeState stores the exact node
`model_variant_resolution`. Approval scope serializes these fields together
with the existing provider resolution and workflow state, so a material runtime
change cannot reuse a prior execution approval.

The Supervisor sees controller-generated runtime-option metadata and may emit
runtime overrides only as task-scoped intent. Overrides are validated against
actual agent roles/node IDs in the selected workflow and never mutate the trusted
project profile. Persistent defaults remain project authority.


## v0.9.1 read-only execution identity

Read-only model phases no longer execute in the controller's project root.
Supervisor, Planner and Reviewer receive a disposable Git-backed materialization
of the project manifest. The materialization deliberately excludes
`.orchestrator` and ignored ambient files, preserves the current tracked and
nonignored-untracked project snapshot, rejects provider writes, and is removed
after the call. The controller continues to bind approvals and validation to the
real project snapshot.

The compatibility policy field `cross_provider_review` now means independent
execution identity rather than literally different vendors. Different provider
families are independent. Within one family, independence is accepted only when
both resolved model IDs are explicit and unequal. Provider-local model strings
are compared literally; the kernel does not maintain a vendor alias-equivalence
catalog. A difference in effort/reasoning level alone is not independence.

Dynamic reviewer routing without a fixed provider retains the historical
different-family preference. Fixed provider bindings and task/node runtime
overrides can intentionally choose distinct models from the same family.


## v0.9.1 observable provider provenance

The controller now emits a content-free audit record from the exact `RunRequest`
object passed to each Provider Adapter. Task calls accumulate those records in the
hash-verified `provider_provenance` artifact; Supervisor stores the equivalent
record directly in schema-v3 intake state because it runs before TaskState exists.

Each record contains role/node/phase, provider/adapter/family, dispatched
model/effort/runtime options, provider permission names, Model Variant source and
runtime-options digest, fallback state and workspace evidence. It intentionally
omits prompts, response content, command lines and workspace paths.

Read-only Supervisor/Planner/Reviewer calls report that their disposable
workspace is outside the project tree, whether `.orchestrator` was materialized,
whether the seed remained unchanged and whether cleanup completed. This is
controller-observed execution provenance, not an independent attestation from the
provider process.

The portable Skill treats language as a presentation boundary: MCP/control-plane
interaction and structured internal instructions remain English for consistency,
while the host agent's conversation with the user follows the user's current
conversation language.


## v0.9.2 provider compatibility evidence

Provider capability resolution and execution compatibility are separate
controller concepts. A provider can satisfy semantic/runtime capabilities while
still depending on provider-native permissions that the controller cannot
pre-attest.

`Engine.provider_compatibility_report()` exposes this distinction without
changing routing authority. Built-in adapters default to `supported`. AGY
Supervisor/Planner/Reviewer report `conditional_native_permissions`: the role
remains eligible for resolution, but a headless session may choose native tools
such as `run_command` whose authorization is governed by AGY configuration.

Provider-change previews surface the same compatibility metadata but do not
convert it into a blocker. Runtime denial remains the fail-closed enforcement
point and is observable through adapter-sanitized provider failure diagnostics.
The controller neither rewrites task prompts to bypass native permission policy
nor mutates AGY global settings.
