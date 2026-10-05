# AI Orchestrator Roadmap

This document describes the implemented path through v0.16 Exploration /
Deliberation Sessions (live closure pending) and the remaining path toward stable v1.0
contracts. Version numbers describe sequencing and design boundaries, not
promised release dates. Live E2E evidence, security findings and implementation
experience may change the details or order.

## Vision

AI Orchestrator is a provider-neutral execution control plane between a
user-facing AI agent and one or more worker agents.

The frontend may be Claude Code, Codex or another compatible agent. Worker
providers may change independently. The kernel should coordinate capabilities,
authority, evidence and effects without making a particular vendor, domain or
frontend a permanent architectural dependency.

The intended abstraction is:

```text
User
  |
Frontend agent / Skill / MCP
  |
AI Orchestrator control plane
  |
  +-- HumanGate / policy / budgets
  +-- capability and workflow resolution
  +-- evidence / validation / review
  |
Provider workers
```

## Design principles

These principles should survive future feature work.

1. **Agent intent is not human authorization.** Models may propose and request
   gates; only the configured human-authorization channel applies them.
2. **Task -> capabilities -> workflow.** Domain names such as finance, research
   or fullstack should normally be reusable templates/skills, not kernel
   branches.
3. **Deterministic validation is first-class evidence.** Model claims do not
   replace registered validators.
4. **Independent review remains separate from implementation.** Cross-provider
   review can be required by policy.
5. **Effects are explicit and bounded.** Write sets, protected paths, external
   effects and later sandbox boundaries are control-plane contracts.
6. **Frontend and provider are independent.** The agent a user talks to does not
   determine which worker performs a role.
7. **Provider neutrality is explicit, not automatic model ranking.** Profiles
   must retain deterministic bindings/priority policies and operator overrides.
8. **Recovery is conservative.** Interrupted or stale work is inspected rather
   than silently replayed.
9. **Evidence precedes adaptation.** Routing and workflow improvements should be
   informed by provenance and measured runs, not opaque self-ranking.

## Previous baseline — v0.4.1

The current baseline has live owner-reported E2E evidence from both Claude Code
and Codex frontends.

Implemented foundations include:

- portable Agent Skill and fixed-project MCP frontend;
- single-terminal host confirmations for start, execution and acceptance;
- managed separate workers with recursion guards;
- persistent idempotent jobs and bounded waiting/progress;
- Supervisor-generated TaskSpec proposals;
- exact `allowed_paths` for new Supervisor write tasks;
- kernel-enforced implementation `write_set` evidence;
- deterministic validators and fresh independent review;
- profile/worktree/scope binding and explicit acceptance;
- direct/manual CLI retained for diagnostics, recovery and advanced use.

See `docs/E2E.md` for the observed Claude Code and Codex live runs and their
limitations.

## v0.5 — Capability Registry and Provider Adapter v2 — implemented

v0.5 generalizes **who can do a unit of work**, without generalizing the workflow into an arbitrary DAG.

Goals:

- introduce a versioned provider/capability description;
- describe capabilities such as planning, code editing, testing, research or
  review independently of provider names;
- let roles/tasks declare required capabilities;
- resolve eligible providers using explicit profile policy;
- preserve fixed provider bindings and deterministic priority/override behavior;
- record the resolved provider, capability requirements and provenance;
- define Provider Adapter v2 without breaking existing Claude/Codex adapters
  unnecessarily;
- make unsupported capabilities fail closed before billable work.

Non-goals for v0.5:

- arbitrary DAG execution;
- automatic "best model" rankings;
- self-benchmarking that silently changes routing;
- parallel edits to one worktree;
- new domain-specific kernel branches.

Implemented output: a versioned semantic registry, Adapter v2 descriptors, deterministic fixed/candidate/priority resolution, task/profile capability requirements and frozen provenance. See `docs/CAPABILITIES.md`.

The next implementation milestone is v0.6 workflow/DAG schema.

## v0.5.x design boundary — Provider vs Model Variant Resolution

Before v0.6 generalizes workflow topology, the resolver boundary is fixed as a
design contract. v0.5.x does not need to implement automatic variant routing.

- **Provider Resolution answers who can do the work.** Inputs are semantic
  capabilities, explicit fixed bindings/candidates/priority and provider-family
  policy. Output is provider identity, adapter and family.
- **Model Variant Resolution answers how the selected provider should run.**
  Inputs are the selected provider plus explicit execution-class/policy and later
  budget constraints. Output is a provider-local variant, concrete model, effort
  and execution options.
- Semantic capabilities such as `code_edit` or `review` must not be mixed with
  execution characteristics such as fast/balanced/deep or reasoning effort.
- Model variants belong under a provider/adapter contract. Workflow/DAG nodes
  should normally request capabilities and an abstract execution class/policy,
  not vendor model names.
- Variant policy remains operator-controlled. Difficulty-based or learned
  automatic routing is a later adaptive feature, not part of the v0.5 resolver.
- Variant fallback must be explicit. Policies can allow an ordered fallback or
  require fail-closed behavior.
- Provider resolution and variant resolution must be separately frozen and
  recorded as provenance. Both are bound into the execution approval scope; a
  material post-approval change invalidates that scope.
- Budgets are a third concern: capabilities describe **what**, provider
  resolution **who**, variant resolution **how**, and budget policy **how much**.

See `docs/MODEL_VARIANTS.md` for the full design decision.

## v0.6 — Workflow Schema and DAG — implemented

v0.6 generalizes the fixed Supervisor -> Planner -> Implementer -> Validator -> Reviewer sequence into a versioned, deterministically scheduled Workflow Schema v1.

Goals:

- explicit nodes and dependencies;
- node capability requirements rather than hard-coded provider identities;
- typed artifact/evidence passing between nodes;
- per-node validators, effects and write contracts;
- human gates at explicit workflow boundaries;
- reusable workflow templates;
- deterministic graph validation before execution.

A conceptual node may look like:

```yaml
id: implement_backend
requires:
  - code_edit
  - python
depends_on:
  - architecture
writes:
  - src/backend/**
validators:
  - pytest
```

The final schema may differ. In particular, write patterns must not weaken the
exact write-set/security guarantees already established.

Implemented output: typed node/artifact dependencies, DAG validation, per-node capability resolution, bounded repair and a sequential scheduler. The built-in build-review profile now runs through this engine without requiring configuration changes.

v0.6 intentionally established the sequential baseline before isolated parallel execution.

## v0.6.2 — Task-scoped workflow selection — implemented

Live custom-DAG E2E showed a real usability cost in requiring users to hand-edit
`.orchestrator/config.yaml` and manually re-trust the profile merely to select
a workflow shape for one task. v0.6.2 resolves that distinction before v0.7:

- **Selecting already-trusted authority should be task-scoped.** A task should be
  able to reference an existing built-in or project-trusted workflow template
  (for example `build-review` or `branched-review`) without mutating the
  project profile or requiring re-trust.
- **Adding new authority remains a profile change.** Installing a new project
  workflow definition, validator, provider executable or materially broader
  effect policy still requires explicit inspection/trust.
- The intended boundary is:
  `select existing authority -> task/start confirmation`, while
  `expand authority -> trust confirmation`.
- The Workflow Registry distinguishes package built-ins from project-defined trusted templates and allows task/intake-scoped `workflow_ref` binding.
- The Supervisor may propose/select from already-trusted workflows, but must not
  silently author, install, switch to or trust a new workflow definition.
- YAML hand-editing is not required to select existing authority. Installing new project workflow authority remains an explicit profile/trust action and may gain a dedicated install UX later.
- Task-scoped workflow selection must be frozen into TaskState/HumanGate
  provenance exactly like current workflow digest/provider resolution.
- This UX work must not weaken profile digest binding, HumanGate semantics,
  write-set enforcement, validator registration or fail-closed behavior.

Implemented in v0.6.2: built-in `build-review` and `branched-review` registry entries, task/intake workflow selection, frozen workflow provenance, CLI/MCP inspection and Supervisor selection constrained to advertised trusted IDs. This does not permit models to mutate trusted workflow configuration.

See `docs/WORKFLOWS.md` for the workflow-selection/authority distinction.

## v0.6.x live baseline — verified before v0.7

Owner-reported Claude Code live E2E now covers the built-in sequential DAG,
v0.6.1 approval-scope regression fix, a custom branched DAG, and v0.6.2
task-scoped selection of built-in `branched-review` while the project default
remained `build-review`. The final task used selection source `requested`,
required no config edit or re-trust, executed all five nodes in deterministic
order, passed 45 pytest tests, received independent review and reached
`succeeded`.

This closes the v0.6.x workflow-selection/DAG validation milestone. See
`docs/E2E.md` for the evidence and limitations. v0.7 must preserve this
sequential/authority behavior while introducing isolation and concurrency.

## v0.7 — Isolated parallel execution — implemented

v0.7 adds writable concurrency only after the v0.6 dependency and effect
contracts are explicit.

Implemented:

- private Git worktrees per isolated writable node;
- exact per-node `write_paths` ownership checked against task
  `allowed_paths`;
- compile-time rejection of overlapping ownership between independent isolated
  writers;
- bounded provider concurrency through trusted
  `policy.max_parallel_workers`, defaulting to one;
- deterministic patch integration in workflow order inside a separate
  integration worktree;
- one aggregate project-worktree apply only after all branches pass ownership
  checks and the approved root/control/protected snapshots remain unchanged;
- deterministic validators and fresh review only after integrated changes are
  present in the project worktree;
- integration/patch/workspace provenance in events and write-set artifacts;
- cancellation propagation to concurrent workers where adapters honor the
  callback, fail-closed batch behavior and cleanup;
- conservative recovery that removes stale isolated worktrees without replay.

The invariant is enforced:

> No two independent workers concurrently mutate the same unisolated worktree.

Parallel writes remain opt-in. Existing workflows keep shared sequential
execution, and the new concurrency limit defaults to `1`. v0.7 worktree
isolation separates cooperating worker writes; it is not a general OS security
sandbox against a hostile same-user process.

See `docs/PARALLEL_EXECUTION.md`.

## v0.8 — Adaptive and user-defined orchestration — implemented

Capabilities, Workflow Schema v1 and isolated execution now support adaptive
task structure without turning model intent into persistent authority.

Implemented flow:

```text
User task
  -> Supervisor identifies task/capabilities
  -> trusted workflow/template lookup
  -> task-scoped workflow proposal when no suitable template exists
  -> Start HumanGate binds the exact proposal
  -> existing capability/provider resolution and execution controls
  -> evidence/provenance retained
  -> optional operator-only template save after successful acceptance
```

Implemented:

- Supervisor-authored Workflow Schema v1 proposals embedded in intake/TaskState,
  not silently written into project configuration;
- default conversational UX that does not require users to choose workflow IDs,
  DAG topology, parallelism or vendors;
- pre-confirmation enforcement of existing capabilities, validators, policy,
  allowed paths, DAG invariants and cross-provider review;
- conversational revision of unconfirmed proposals with stale-proposal
  supersession;
- TaskState v5 for embedded adaptive DAG provenance while existing trusted/manual
  tasks remain v4;
- explicit evidence-backed `workflow-candidate` / `workflow-save` operator
  flow for reusable project templates;
- template version/provenance and parent-digest tracking on explicit revisions;
- mandatory normal profile re-trust after persistent template save;
- semantic workflow digests separated from template metadata so promotion
  metadata does not rewrite executable graph identity.

The invariant remains: the system may learn/reuse **structure**, but it cannot
silently grant itself providers, validator commands, policies, permissions,
external effects or project trust.

See `docs/ADAPTIVE_ORCHESTRATION.md`. v0.9 subsequently completed the
model/runtime-resolution, isolation and observability foundation described below.

## v0.9 — Model/runtime policy and observable execution — completed

v0.9 is closed for the trusted-local alpha scope. The implemented line separates
provider identity from provider-local model/runtime choice and makes the resulting
execution observable without turning metrics into opaque automatic ranking.

The retained resolution boundary is:

```text
task / workflow node
  -> semantic capabilities
  -> Provider Resolution        # who
  -> Model Variant Resolution   # how
  -> adapter execution
```

### v0.9.0 — Runtime option registry and Model Variant Resolution — completed

Implemented:

- adapter-advertised runtime-option metadata;
- provider-local model/effort pass-through without a kernel-owned vendor catalog;
- deterministic precedence:
  task/node explicit override > trusted profile setting > adapter default;
- frozen Model Variant Resolution provenance;
- exact model/effort/runtime-option visibility in HumanGate/controller evidence;
- task/node-scoped runtime overrides without persistent profile mutation;
- explicit no-fallback behavior unless separately authorized by policy.

### v0.9.1 — Read-only isolation, model-aware review identity and provenance — completed

Implemented:

- disposable read-only workspaces for Supervisor, Planner and Reviewer;
- omission of `.orchestrator` and ignored ambient control/runtime material;
- unchanged verification and cleanup evidence;
- same-family independent review when implementation and review use explicit,
  unequal provider-local model IDs;
- intake-scoped Supervisor model/effort override;
- content-free controller RunRequest dispatch provenance;
- safe provider failure diagnostics;
- user-language presentation separated from English control-plane protocol;
- single-terminal as the standard `serve` mode.

Live Claude-only Fresh-Write E2E verified Sonnet implementation + Opus review
within one family, exact write ownership, deterministic pytest validation,
read-only provenance, three HumanGates and final `succeeded`.

### v0.9.2 — Compatibility boundaries and HumanGate interoperability diagnostics — completed

Implemented:

- AGY Supervisor/Planner/Reviewer represented as
  `conditional_native_permissions`, not categorically unsupported;
- provider compatibility surfaced independently from capability resolution;
- AGY native permission denial remains fail-closed and does not trigger prompt
  rewriting or automatic `--dangerously-skip-permissions`;
- adapter-sanitized denied-action diagnostics without raw command arguments;
- HumanGate transport diagnostics for client name/version, negotiated MCP
  protocol, advertised form/url elicitation capability, send/response state and
  cancel/error/timeout/disconnect outcomes;
- plain `serve` remains managed single-terminal mode; legacy manual mode is an
  explicit opt-out.

Live Antigravity-host testing verified MCP tool access and
`elicitation/create` delivery. The tested `antigravity-client v1.0.0`
advertised form/url elicitation but returned `action=cancel`; this is retained
as a host-interoperability boundary rather than bypassed through another
authority channel.

### v0.9 completion boundary

v0.9 intentionally does **not** claim:

- provider-side attestation that requested model/effort settings were honored;
- cryptographic proof of a human click;
- OS-level isolation against a hostile same-user process;
- universal AGY native-permission or HumanGate compatibility;
- automatic performance/cost-based model ranking.

Those boundaries are explicit evidence, not reasons to weaken HumanGate,
workspace or provider-permission controls.

## v0.10 — Usage Observability & Budget Policy — implemented

v0.10 extends the v0.9 execution/provenance chain with attributable usage and
explicit resource limits:

```text
Task
  -> Node
  -> Provider
  -> Model Variant
  -> Execution
  -> Usage
  -> Budget
  -> Evidence
```

The architectural distinction is:

```text
Capabilities  = what
Provider      = who
Model Variant = how
Budget        = how much
```

Usage/budget policy is a separate control-plane concern. It must not silently
rewrite capability requirements, provider identity, model choice or HumanGate
authority.

### v0.10.0 — Usage Accounting

Establish a normalized usage evidence contract while preserving provider truth.

Implemented:

- adapter-level structured usage extraction where the provider exposes reliable
  input/output/reasoning/cache/token or call data;
- explicit `known` / `unknown` / `unsupported` representation rather than
  estimating missing provider counters;
- per-call and per-node usage records linked to Provider Resolution, Model
  Variant Resolution, attempts and artifacts;
- deterministic aggregation from call -> node -> attempt -> task;
- elapsed controller/provider time recorded separately from token usage;
- content-free usage provenance suitable for `get_artifact`, inspection and
  later budget accounting;
- adapter capability/limitation reporting when a provider does not expose a
  reliable usage field.

Usage accounting must not infer hidden reasoning tokens, fabricate token counts
from text length, or treat incomplete provider telemetry as zero.

### v0.10.1 — Budget Policy & Enforcement

Add explicit, inspectable limits over attributable execution resources.

Planned budget dimensions:

- provider/model call count;
- wall-clock/provider execution time where reliably attributable;
- input/output/reasoning/total tokens where exposed;
- cost only when the required usage and pricing attribution are trustworthy.

Enforcement principles:

- budget configuration is trusted policy, not model-authored authority;
- check enforceable remaining budget before dispatch where possible;
- account actual usage after each provider call;
- stop before the next effect when an enforceable budget is exhausted;
- never silently switch to a cheaper provider/model, lower effort, weaker
  validator or different workflow to stay within budget;
- any policy that permits a budget-driven fallback must be separately explicit,
  inspectable and provenance-recorded;
- unknown telemetry must remain unknown. A strict budget that cannot be proven
  safe to enforce fails closed rather than guessing.

HumanGate previews should expose material budget scope when the authorized
execution is budget-constrained.

### v0.10.2 — Cost Attribution & Usage Evidence

Complete the evidence layer for auditable usage/cost reporting.

Implemented:

- pricing metadata with source/version/effective-time provenance rather than
  hard-coded unversioned cost constants;
- provider/model-specific cost calculation only when usage dimensions map
  unambiguously to the pricing contract;
- explicit distinction between provider-reported cost, controller-computed cost
  and unavailable cost;
- task/node/provider/model usage summaries linked to validation/review evidence;
- budget-consumption artifacts suitable for post-run inspection;
- clear rounding/currency semantics where monetary accounting is supported.

Metrics remain provenance first. v0.10 does not introduce automatic
performance/cost leaderboards or opaque model ranking.

### v0.10 closure — live verification

**Closed 2026-10-03.** The v0.10 kernel and evidence contracts were validated
end-to-end with the intended mixed-provider assignment:

- Supervisor / Planner / Reviewer: Claude;
- Implementer: Codex;
- Usage evidence preserved explicit `known` / `unknown` / `unsupported`
  states across Claude and Codex live calls, including provider-reported Claude
  duration/cost and structured Codex token counters without inference;
- Supervisor usage survived Intake -> Task registration and remained in task
  aggregation;
- Budget accounting remained non-routing with no provider/model/effort/workflow
  fallback;
- hash-verified usage, budget, write-set, validation, review,
  provider-provenance and acceptance artifacts were observed;
- configured pytest completed with 26 passing tests and independent review
  approved;
- on `claude-code 2.1.284`, Start -> Execution -> Acceptance all completed as
  separate correlated HumanGates and the task reached `succeeded`.

Host interoperability is tracked separately from v0.10 kernel completion:

- `codex-mcp-client 0.160.0` showed intermittent no-response timeouts at
  Execution or Acceptance across separate runs despite the same protocol,
  one-field form schema and approximately 1.4–1.6 KiB wire forms. v0.10.4
  content-free diagnostics preserve correlation, size/shape and timing evidence;
  current evidence makes a host-specific issue likely but cannot distinguish UI
  non-presentation from an unanswered/lost response.
- `antigravity-client 1.0.0` advertises MCP form/url elicitation and receives
  `elicitation/create`, but returned `action=cancel` in live testing.

Non-blocking follow-up observations:

- attempt aggregation currently uses numeric attempt keys across phases, so a
  Supervisor `attempt=1` and task execution `attempt=1` may share one
  `by_attempt` bucket; a phase/owner-qualified grouping could improve audit
  readability without changing raw call evidence;
- usage `controller_elapsed_seconds` is the sum of provider-call controller
  measurements, while budget/task elapsed is wall-clock controller consumption;
  small differences are expected and should remain explicitly documented rather
  than forced to match.

Completion output: normalized usage/cost contracts; adapter telemetry boundaries for
Claude/Codex/AGY; TaskState v7 and IntakeState v4 accounting provenance;
deterministic task/node/attempt/provider/model aggregation; trusted call/time/
token/cost budgets; exact provider/model pricing provenance; pre-dispatch and
post-call fail-closed enforcement; MCP/task/artifact inspection; and budget-aware
HumanGate previews. Budget enforcement is non-routing: v0.10.2 contains no
automatic provider/model/effort/workflow fallback.

### v0.10 non-goals

v0.10 does **not** include:

- automatic cheapest-model/provider selection;
- silent quality/effort degradation to satisfy a budget;
- guessed token/cost values when providers do not report enough information;
- billing-system reconciliation or financial-ledger guarantees;
- provider-side attestation beyond evidence actually returned by the provider;
- general recovery/resume of interrupted execution;
- automatic replay of ambiguous effects;
- weakening HumanGate, provider-permission or workspace isolation boundaries.

## v0.11 — Recovery & Durability hardening (completed 2026-10-03)

Recovery remains deliberately separate from usage/budget enforcement. v0.11
implements the conservative boundary rather than broad resume semantics:

- guarded/isolated execution persists a pre-provider-dispatch root-snapshot
  checkpoint;
- interrupted `running` tasks are classified read-only before recovery;
- only a checkpointed, unchanged-root, pre-dispatch interruption is retry-safe;
- safe recovery releases only provably un-dispatched call reservations, cleans
  disposable workspaces, atomically revokes old execution/provider-permission
  approvals and returns to `awaiting_approval` for a fresh HumanGate;
- provider dispatch, validator execution, shared writes, integration start,
  workspace drift and pre-v0.11 interrupted rows are treated as uncertain and
  are terminalized without replay or automatic root-worktree rollback;
- every recovery writes immutable recovery evidence plus transition events;
- HumanGate `applying` / `uncertain` states expose their effect ambiguity and
  remain non-replayable;
- Codex/Claude/AGY provider failures carry content-free
  authentication/quota/permission/configuration/protocol/provider-process
  categories where the adapter can establish them without retaining raw output;
- persisted TaskState v1-v7 and runtime database versions remain readable; v0.11
  does not require a TaskState or SQLite schema-version bump, and old interrupted
  rows lacking the new checkpoint deliberately fail closed;
- crash-injection regressions cover pre-dispatch recovery, post-dispatch
  ambiguity, post-integration interruption, approval invalidation and
  no-rollback behavior across the offline CI matrix;
- owner-reported Claude Code live E2E repeated the same boundaries with real
  worker/provider process kills and restart: safe pre-dispatch recovery required
  fresh authority and completed, ambiguous post-dispatch/post-integration cases
  did not replay, and normal Start -> Execution -> Acceptance reached
  `succeeded`.

The invariant remains: interrupted or uncertain effects are inspected, not
blindly replayed. v0.11 does not add provider-side idempotency keys, external
effect replay, distributed transactions, or general rollback.

## Provisional roadmap to v1.0

The milestones below are a **provisional sequencing plan**, not a frozen release
contract. v0.16 is the next intended milestone; the exact boundaries of
v0.16-v0.17 may be adjusted when implementation, compatibility testing or live
host evidence shows a better split. Architectural authority and durability
principles should remain stable even if milestone packaging changes.

### v0.12 — Contract & Migration Hardening — implemented

Primary goal: make the persisted control-plane contracts safe to evolve before
declaring stable APIs.

Implemented:

- explicit versioning/read-write rules for TaskState, IntakeState, HumanGate,
  workflow/runtime state, events, artifacts, usage/budget, provider provenance
  and recovery evidence;
- retained representative TaskState v1-v7, IntakeState v1-v4, HumanGate v1,
  legacy Artifact v1 and v0.11 recovery fixtures with continuous compatibility
  tests;
- non-mutating read compatibility: supported historical state is interpreted
  without rewriting persisted rows or immutable artifact bytes;
- fail-closed handling for malformed, non-integer and unknown schema versions
  and unsupported runtime/HumanGate SQLite versions;
- migration regressions that preserve legacy authority defaults, exact artifact
  hashes and conservative recovery semantics;
- Artifact metadata schema v2 with stable artifact ID, owner and creation time;
- runtime event envelope schema v1 with stable sequence-derived identity while
  retaining the original payload;
- versioned new recovery evidence plus hash-first in-memory compatibility for
  legacy v0.11 unversioned recovery artifacts;
- `orchestrator persistence` and `inspect_project.persistence_compatibility`
  inspection surfaces;
- explicit upgrade, forward-compatibility and downgrade/backup rules in
  `docs/PERSISTENCE.md` and `docs/MIGRATION.md`.

Completion target achieved: representative v0.x persisted states remain
inspectable under the current kernel, schema changes have explicit migration
rules, unknown versions fail closed, and software upgrade alone does not mutate
authority semantics or historical evidence.

Live in-place upgrade E2E on 2026-10-04 additionally verified unchanged
historical file/row digests and a complete single-terminal write-task regression.
That run exposed one legacy usage-display gap: pre-v0.10 durable calls without
usage records appeared as known zero. v0.12.1 closes that gap with explicit
incomplete call coverage and unknown aggregate telemetry, without rewriting old
state or evidence. The run also re-confirmed that installed Skill copies must be
explicitly re-exported after package upgrades.

The final v0.12.1 read-only closure E2E then verified that fix and Skill
synchronization in the live accumulated runtime. It also found that opening an
already-current SQLite store restamped the same `user_version`, changing only
the SQLite header change counter. v0.12.2 removes that unnecessary physical
write for runtime, HumanGate and jobs databases while preserving real supported
version upgrades. The v0.12 line is therefore closed before v0.13.

Final v0.12.2 live read-only E2E subsequently confirmed the fix against the
accumulated runtime: repeated state/task/intake/artifact/job/gate inspection left
the full SHA-256, SQLite header counters, user versions, mtimes, schema digests
and row digests of all three current databases unchanged. Legacy usage semantics
and installed Skill synchronization also remained correct, with no provider,
HumanGate, job, event or workspace side effects. v0.12 is fully closed; no
further v0.12 E2E is required before v0.13.

### v0.13 — Provider Adapter / Plugin SDK — implemented

Primary goal achieved: the provider extension boundary is now a documented,
compatibility-tested interface rather than an internal convention.

Implemented:

- publish the Provider Adapter core contract and distinguish required lifecycle
  methods from optional runtime-option, usage and compatibility features;
- formalize capability, model-variant/runtime-option, usage, sanitized
  diagnostics and provider-failure contracts;
- define one versioned provider-plugin SDK and deterministic packaging/discovery
  convention for third-party adapters;
- treat an in-process provider plugin as controller code in the trusted
  computing base: merely installing a package must not activate it;
- require an exact project-owned plugin pin (adapter ID, distribution, version
  and entry point) inside the profile, and load external plugin code only after
  that exact profile digest has been explicitly trusted;
- fail closed on missing/mismatched pins, duplicate adapter IDs, built-in
  collisions, unsupported SDK/API versions and plugin load/conformance failure;
- retain plugin package/version/entry-point identity in provider resolution and
  dispatch provenance so an in-place package change cannot silently continue a
  frozen task;
- provide a compatibility/conformance test kit for third-party adapters;
- keep provider-specific CLI/protocol behavior outside kernel policy;
- prove the SDK with a non-core test adapter loaded through the same entry-point
  path, without weakening HumanGate, workspace, budget or recovery guarantees;
- keep v0.13 scoped to **provider adapters**. Workflow, validator, policy and
  knowledge extension authority remain separate contracts rather than a generic
  executable plugin API.

Trust boundary:

- package/version/entry-point pinning establishes project/operator intent, not a
  cryptographic code-integrity guarantee. A hostile same-OS-user installation
  remains outside the trusted-local threat model;
- plugin installation or discovery does not grant provider selection, tools,
  permissions, write scope, validators, external effects, budget changes or
  project trust. Existing profile/HumanGate/task authority still applies.

Completion boundary: adding a provider adapter is routine SDK work; incompatible
or untrusted plugins fail before provider dispatch, and structural contract
failures are detected by conformance tests rather than kernel changes. The
offline CI matrix covers Python 3.11/3.12/3.13 on Linux plus Python 3.13 on
macOS, including a non-core entry-point fixture.

Owner-reported live closure additionally passed a Fresh-Write isolated
integration with 43 pytest tests and independent review, plus a real temporary
external distribution lifecycle:
`installed/unpinned/inert -> exact-pin/untrusted/inert -> exact-pin/trusted/loaded`.
The loaded fixture remained unselected and undispatched, and cleanup restored the
original project/environment state. Cleanup also confirmed that restoring an old
profile digest does not restore its prior trust automatically; the single current
trusted-profile binding requires explicit re-trust.

v0.13 does not claim that distribution/version pinning cryptographically attests
package bytes or that third-party in-process adapter code is sandboxed from the
controller.

### v0.14 — Knowledge Distillation / Project Learning

Primary goal: make accumulated execution evidence improve future orchestration
without turning historical model output into implicit project authority.

The project already persists task/intake state, artifacts, validation/review
evidence, provider provenance, usage/budget observations, events and
human-governed knowledge/policy/skill candidates. Accepted Markdown under
`.orchestrator/knowledge/accepted/`, policies and skills is loaded into future
project context, and successful task-scoped workflows can already be promoted
explicitly into reusable trusted templates. v0.14 completes the missing
distillation layer between accumulated evidence and those governed promotion
mechanisms.

Planned scope:

- define a versioned Project Learning / Distillation contract that consumes
  controller-owned historical evidence without treating provider prose as
  authorization;
- detect recurring evidence-backed patterns across successful tasks, validation,
  review findings, recovery outcomes, provider provenance and usage/budget
  records;
- define typed, controller-resolvable evidence references for task/artifact/
  event/validation/review/recovery sources before automated distillation;
- propose bounded knowledge, policy, skill and reusable-workflow candidates with
  explicit source evidence, inspectable support metadata (for example independent
  task/support counts and contradiction status) and stable provenance; opaque
  model self-confidence is not authority or evidence;
- distinguish observations from recommendations and authority-bearing promoted
  project context;
- support deduplication, supersession and contradiction detection so repeated
  runs do not simply accumulate redundant or mutually inconsistent knowledge;
- make candidate generation inspectable and reproducible enough to explain why a
  project-learning proposal exists;
- allow operators to accept, reject or revise candidates through explicit
  promotion/trust flows; rejected candidates must not silently reappear without
  materially new evidence;
- separate the accepted project-knowledge universe from the bounded context
  selected for one intake/task; accepted does not mean inject everything;
- feed only accepted project knowledge/policy/skills and explicitly trusted
  workflow templates into future orchestration, with deterministic bounded
  context selection;
- retain an influence manifest showing exactly which accepted context entered an
  intake/task and which historical evidence supported it;
- add semantic consolidation/compaction rules so long-lived projects can preserve
  provenance while keeping selected active context within deterministic size
  limits; physical artifact/job/workspace retention remains v0.15 work;
- expose diagnostics showing which accepted project knowledge influenced an
  intake/task and which historical evidence supported it;
- test that project learning cannot grant providers, permissions, validator
  commands, external effects, write scope, model/runtime policy, budget policy or
  project trust by itself.

Example target behavior:

```text
repeated execution/review/validation evidence
  -> deterministic evidence selection
  -> distillation proposal
  -> knowledge / policy / skill / workflow candidate
  -> operator review
  -> explicit promotion + trust where required
  -> accepted project context
  -> future Supervisor / Planner / Implementer / Reviewer reuse
```

The intended product property is that ai-orchestrator becomes more
project-specific with use, but the durable learning remains reviewable,
version-controlled and evidence-backed rather than hidden in model memory.

Completion boundary: implemented in v0.14.0. Project Learning v1 now provides
typed/hash-verifiable evidence references, deterministic multi-source
distillation, stable support/provenance, knowledge/policy/skill/workflow
recommendation candidates, rejection/revision/promotion governance,
deduplication/supersession/contradiction handling, bounded accepted-context
selection and persisted intake/task influence manifests. New TaskState v8 and
IntakeState v5 carry influence provenance while historical versions remain
readable without rewrite. Post-acceptance distillation is advisory and cannot
roll back task acceptance. Promotion changes project context and therefore still
requires explicit profile re-trust; workflow recommendations do not install a
workflow template. Offline CI covers the full behavior across supported Linux
and macOS/Python matrices. Owner-reported live v0.14/v0.14.1 closure also passed
the complete lifecycle over an accumulated project: 45 historical tasks
distilled to 12 inactive candidates; identical evidence was idempotent; exact
promotion changed the profile digest and failed closed until explicit trust;
promoted learning was selected into IntakeState v5 / TaskState v8
ContextInfluence for a real write task that finished with 46 pytest tests and
independent review; Acceptance created new superseding candidates without
automatic authority; cleanup restored the original authority while preserving
24 inactive candidates and historical influence provenance. The live run also
found and v0.14.1 fixed the non-empty MCP candidate-inspection `digest` import
regression.

The remaining long-lived-storage work is physical retention/backup/restore in
v0.15; v0.14 semantic consolidation deliberately does not garbage-collect
historical evidence.

### v0.15 — Operational Hardening — implemented

Primary goal achieved: long-lived trusted-local installations can now be
diagnosed, backed up, restored and physically cleaned through explicit
controller contracts without introducing unsafe automatic repair.

Implemented:

- expand `doctor` with read-only runtime SQLite quick/foreign-key integrity,
  persisted TaskState/IntakeState decoding, artifact existence/hash/evidence
  verification, stale job/worker diagnosis, HumanGate ledger diagnosis,
  disposable-worktree classification and maintenance-log inspection;
- diagnose a structurally unreadable runtime database before normal Engine
  construction so inspection does not depend on startup mutation or hidden state
  surgery;
- add backup manifest schema v1 with exact file hashes/sizes, source version,
  source profile/trust provenance and deterministic restore scope;
- support both runtime-evidence backup and complete controller/project-authority
  backup, including config, policies, skills, accepted knowledge, Project
  Learning candidates, workflow templates and durable runtime/gate/job state;
- snapshot SQLite through its backup API while excluding disposable worktrees,
  process locks and WAL/SHM/journal sidecars from backup authority;
- require exact verified scope, quiescence and explicit `--replace` for
  restore; full authority restore additionally requires
  `--ack-authority-restore`, verifies the restored profile digest and stages
  pre-restore managed state for rollback on failure;
- separate runtime-only restore from project authority: current config/context
  is never overwritten by a runtime archive, and profile mismatch is surfaced
  as `retrust_required` rather than silently granting trust;
- add read-only physical retention planning plus exact-scope cleanup. Initial
  deletion is deliberately narrow: stale disposable worktrees, old terminal
  job/job-event rows and old orphan runtime JSON only;
- retain canonical task/intake/runtime-event/HumanGate history, every artifact
  referenced by TaskState or IntakeState (including immutable Supervisor
  evidence) and evidence referenced by accepted or retained Project Learning
  candidates, so semantic learning provenance is not silently garbage-collected;
- append bounded provenance records for successful restore/cleanup operations to
  `.orchestrator/runtime/maintenance.jsonl`;
- expose operational diagnostics in read-only `inspect_project` while keeping
  backup/restore/cleanup/database repair out of the agent-facing MCP mutation
  surface;
- keep runtime/HumanGate/jobs SQLite versions and TaskState/IntakeState schema
  versions unchanged. v0.15 adds operational contracts rather than rewriting
  execution-history contracts.

Completion boundary: an operator can inspect, back up, verify, restore and clean
a long-lived installation through documented commands and exact scopes. Runtime
diagnosis remains read-only, restore/cleanup remain explicit and
provenance-recorded, interrupted effects still use the v0.11 conservative
recovery contract, and no v0.15 maintenance path grants normal agent execution
authority or performs automatic repair/replay. Offline CI covers physical
read-only diagnosis, malformed persisted-state detection, full/runtime restore
authority boundaries, scope drift and Project Learning-aware retention.

Owner-reported live closure then exercised the accumulated project runtime.
v0.15.0 exposed a real retention-root defect for Supervisor artifacts referenced
only by IntakeState; v0.15.1 fixed it. The final live run passed read-only doctor,
full/runtime backup verification, exact-scope full restore, unreadable-state
restore, runtime-only authority separation, retention scope drift, exact-scope
cleanup, IntakeState artifact preservation, MCP maintenance-authority separation
and final original-project non-interference. v0.15 is therefore fully closed at
v0.15.1.

See `docs/OPERATIONS.md` for the operator contract and command flow and
`docs/E2E.md` for the live closure evidence.

### v0.16 — Exploration / Deliberation Sessions — implemented and live-closed

Primary goal: support ambiguous, exploratory and specification-forming work
without weakening the execution authority model that protects concrete tasks.

Design principle:

> Exploration may change understanding; only an explicit transition may change authority.

The current kernel is strongest after a task can be expressed as a bounded
TaskSpec with acceptance criteria, effect/write scope, workflow and validators.
That is intentionally conservative, but it makes open-ended work awkward when
the user still needs to inspect the repository, compare approaches, revise
assumptions or clarify the goal over multiple turns. v0.16 adds a pre-authority
exploration layer rather than making TaskSpec/HumanGate semantics looser.

Target lifecycle:

```text
ambiguous user goal
  -> versioned ExplorationState
  -> read-only inspection / questions / hypotheses / options
  -> repeated user refinement
  -> explicit decision / task proposal transition
  -> bounded TaskSpec
  -> existing Start HumanGate
  -> existing execution / validation / review / acceptance
```

Implemented scope (the live external-host exercise below remains a separate closure target):

- define a versioned `ExplorationState` / session contract that can survive
  multiple conversational turns without pretending the goal or acceptance
  criteria are already final;
- retain bounded provenance for user clarifications, inspected repository state,
  hypotheses, options, assumptions, open questions, trade-offs and decisions;
- permit read-oriented repository analysis on disposable/read-only snapshots and
  normal provider reasoning under the existing usage/budget/provenance rules;
- allow the user to revise or discard assumptions and proposed directions
  repeatedly without creating executable tasks or stale approval scopes;
- keep acceptance criteria, allowed paths, workflow shape and implementation
  strategy optional while the session is exploratory;
- keep exploration non-authoritative: it cannot grant write scope, external
  effects, validator registration/execution authority, provider permissions,
  provider/plugin activation, model/runtime policy, budgets, workflow
  installation, accepted Project Learning context or project trust;
- require an explicit exploration-to-task transition that produces a concrete,
  inspectable TaskDraft/TaskSpec proposal and binds the relevant exploration
  provenance into that proposal;
- keep the existing Start HumanGate as the point where a proposed concrete task
  becomes executable controller authority; completing exploration alone must
  never start planning/implementation;
- prevent stale exploration branches or superseded decisions from later becoming
  executable without a fresh explicit transition;
- distinguish exploratory prose from durable Project Learning authority.
  Exploration output may inform a later task proposal, but should not become
  accepted project knowledge merely because a model stated it; durable learning
  should continue to depend on explicit governance and/or later controller
  evidence such as validation/review;
- define bounded context selection/compaction for long exploration sessions so
  repeated discussion does not require replaying an unbounded transcript;
- expose read-only diagnostics showing which exploration decisions/evidence were
  carried into a resulting TaskSpec and which were discarded or superseded;
- add failure/abandonment semantics so an abandoned exploration leaves no
  executable authority, pending effect or hidden reusable approval behind;
- exercise multi-round live E2E where the initial goal is intentionally
  underspecified, the user changes direction at least once, and only the final
  explicit transition becomes a normal guarded task.

Non-goals:

- exploration is not a second implementation mode;
- it does not bypass HumanGate because the work is called research or planning;
- it does not make model hypotheses equivalent to deterministic validation;
- it does not silently run arbitrary project commands or experiments against the
  user's root worktree;
- it does not auto-promote exploration conclusions into Project Learning or
  trusted workflow/configuration authority.

Completion target: a user can begin with "I am not yet sure what we should
change", inspect and refine the problem over multiple turns, compare alternatives,
change assumptions, and eventually produce one concrete task proposal. Until
that explicit transition and the normal Start HumanGate, project execution
authority does not increase.

Implementation evidence: v0.16.0 provides ExplorationState v1, immutable
turn/transition artifacts, revision-bound session operations, deterministic
latest-understanding context selection, read-only Supervisor-provider reasoning,
cumulative budget/usage transfer, stale-proposal invalidation, atomic Start
consumption and inspection/abandonment without automatic replay. Runtime SQLite
v3, IntakeState v6 and TaskState v9 carry the new provenance; historical shapes
remain readable and hash-compatible. Operational retention includes exploration
history and evidence. Offline regressions include real subprocess MCP/managed
worker transport through all three normal HumanGates with deterministic shims.
Owner-reported live closure subsequently exercised a real multi-turn session,
direction change, stale-revision rejection, explicit transition, Start/Execution/
Acceptance HumanGates, isolated implementation, deterministic pytest, fresh
independent review, abandonment, read-only doctor/retention integration and final
project non-interference. A separate proposal also verified a declined Start:
no task was registered and no automatic replay occurred. Exploratory prose did
not become accepted Project Learning or change profile/provider/workflow trust.
v0.16.0 therefore closes the Exploration / Deliberation milestone.

See `docs/EXPLORATION.md` for exact contracts and `docs/E2E.md` for the live
closure evidence. The next implementation milestone is v0.17.

### v0.17 — Release Candidate Hardening

Primary goal: freeze the candidate v1.0 surface and remove remaining
cross-version/host ambiguities after the exploration/deliberation contract is
implemented.

Planned scope:

- run the supported upgrade/migration matrix over retained persisted-state
  fixtures;
- run repeatable offline, subprocess/wire and live host/provider E2E across the
  supported matrix;
- resolve or explicitly document remaining Claude Code / Codex / Antigravity
  host interoperability boundaries and freeze a supported / conditional /
  known-incompatible host-provider matrix;
- freeze public MCP, HumanGate, workflow, provider/plugin, artifact, Project
  Learning/promotion and Exploration/Deliberation contracts intended for v1.0;
- complete security-boundary, deployment-mode, migration and extension
  documentation;
- remove accidental alpha-only APIs or mark them intentionally unstable before
  the v1.0 contract is declared.

Completion target: the release candidate has no known undocumented authority,
migration, exploration-transition or recovery behavior, and all intended stable
surfaces have explicit compatibility tests.

## v1.0 — Stable Control Plane

v1.0 is primarily a contract-stability release, not a promise of unrestricted
distributed or remote execution semantics.

Candidate stable surfaces:

- TaskSpec and effect/write contracts;
- Capability Registry;
- Provider Adapter / Plugin API;
- Workflow/DAG schema;
- HumanGate contract;
- Artifact/evidence model;
- MCP agent-facing API;
- policy/budget configuration;
- recovery/durability diagnosis contracts;
- persistence and migration guarantees;
- provider/plugin compatibility tests;
- Project Learning evidence/candidate/promotion/influence contracts; candidate
  discovery/distillation heuristics may evolve without becoming stable authority;
- Exploration/Deliberation session, supersession and explicit
  exploration-to-task transition contracts;
- documented trusted-local security boundary and supported deployment modes.

A v1.0 release should have versioned extension points, tested upgrade/migration
guarantees, repeatable live E2E coverage for supported frontends/providers, and
clear statements of what remains outside the control-plane guarantee (for
example provider-side exactly-once execution, hostile same-user isolation or
distributed transactions).

## Sequencing constraints

The order above is intentional.

- **Do not implement the general DAG before the capability abstraction.** Doing
  so risks encoding today's planner/implementer/reviewer roles as permanent DAG
  semantics.
- **Do not introduce writable parallelism before workspace isolation.**
- **Do not hard-code domain orchestration into the kernel.** Domain packages
  should normally be templates, skills, policies and capability requirements.
- **Do not confuse provider registry work with automatic model ranking.**
  Provider Resolution answers who; Model Variant Resolution answers how.
  Deterministic policy, explicit overrides and adapter-advertised runtime options
  remain inspectable.
- **Do not hard-code vendor model names or effort enums into semantic
  capabilities.** Runtime choices are provider-local adapter data and policy.
- **Do not weaken HumanGate authority boundaries for convenience.**
- **Do not solve exploratory UX by making TaskSpec authority fuzzy.** Keep
  ambiguity in a non-authoritative ExplorationState and cross into execution only
  through an explicit proposal transition plus the normal HumanGate.
- **Do not treat model-generated plans, hypotheses or reviews as deterministic validation.**
- **Do not automatically replay ambiguous interrupted effects.**
- **Do not add a new provider merely to demonstrate extensibility.** Adapter
  contracts should be stable enough that adding one is routine first.
- **Do not confuse provider-process isolation with plugin-code isolation.** An
  in-process third-party adapter is trusted controller code; package discovery
  alone must never activate it.
- **Do not equate accumulated evidence with learned authority.** Project
  Learning may propose knowledge/policy/skill/workflow candidates, but only
  explicit promotion/trust may make them active project context or authority.
- **Do not hide project learning in model memory.** Durable learned context must
  remain inspectable, evidence-backed and project-owned.

## How the roadmap evolves

Each milestone should be driven by:

1. offline contract/security/regression tests;
2. subprocess/wire E2E;
3. live frontend/provider E2E where relevant;
4. recorded limitations and observed redundant behavior;
5. migration compatibility with persisted projects.

When evidence contradicts this roadmap, update the roadmap explicitly rather
than silently changing architectural principles in implementation commits.
