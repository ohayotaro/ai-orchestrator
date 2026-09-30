# AI Orchestrator Roadmap

This document describes the intended path from the current v0.6 declarative-workflow control-plane
foundation toward stable v1.0 contracts. Version numbers describe sequencing and
design boundaries, not promised release dates. Live E2E evidence, security
findings and implementation experience may change the details or order.

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

v0.6 does **not** introduce unsafe same-worktree parallel editing. The next implementation milestone is v0.7 isolated parallel execution.

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

## v0.7 — Isolated parallel execution

Parallelism comes only after workflow dependencies and effect contracts exist.

Goals:

- isolated Git worktrees or equivalent sandboxes per writable branch/node;
- explicit ownership of writable paths/workspaces;
- bounded concurrent worker scheduling;
- controlled integration/merge phase;
- validation after integration, not merely per branch;
- conflict handling and provenance;
- cancellation/recovery across concurrent nodes.

The invariant is:

> No two independent workers concurrently mutate the same unisolated worktree.

Parallel execution should be opt-in until isolation and recovery are well
tested.

## v0.8 — Adaptive and user-defined orchestration

Once capabilities and workflows are explicit contracts, allow orchestration to
grow from actual use instead of baking a fixed domain taxonomy into the kernel.

Target flow:

```text
User task
  -> Supervisor identifies capabilities
  -> existing workflow/template lookup
  -> propose a workflow when no suitable template exists
  -> human confirmation
  -> execution
  -> evidence/provenance retained for later refinement
```

Goals:

- user-defined workflow templates;
- reusable skills/policies/templates derived from finance, research, fullstack
  and other domain experience;
- workflow proposal and revision through the same HumanGate principles;
- template versioning and provenance;
- explicit operator control over whether learned/proposed templates are saved.

The system should learn reusable structure, not silently mutate its kernel or
permissions.

## v0.9 — Observability, budgets and recovery hardening

Before declaring public contracts stable, improve operational visibility and
resource controls.

Goals:

- structured per-node/provider timing and call provenance;
- token/cost information where providers expose reliable data;
- configurable call/time/cost budgets;
- validator/reviewer/repair statistics;
- audit-friendly evidence graph;
- improved resume/recovery semantics for safe pre-effect failures;
- queue/workflow diagnostics and failure attribution;
- migration and compatibility testing across persisted versions.

Metrics are initially provenance, not an automatic leaderboard. Any later
routing policy based on measurements must be explicit and inspectable.

## v1.0 — Stable control-plane contracts

v1.0 is primarily a contract-stability milestone.

Candidate stable surfaces:

- TaskSpec and effect/write contracts;
- Capability Registry;
- Provider Adapter API;
- Workflow/DAG schema;
- HumanGate contract;
- Artifact/evidence model;
- MCP agent-facing API;
- policy/budget configuration;
- persistence and migration guarantees;
- provider/plugin SDK and compatibility tests;
- documented trusted-local security boundary and supported deployment modes.

A v1.0 release should have upgrade/migration documentation, repeatable live E2E
coverage for supported frontends/providers and a clearly versioned extension
model.

## Sequencing constraints

The order above is intentional.

- **Do not implement the general DAG before the capability abstraction.** Doing
  so risks encoding today's planner/implementer/reviewer roles as permanent DAG
  semantics.
- **Do not introduce writable parallelism before workspace isolation.**
- **Do not hard-code domain orchestration into the kernel.** Domain packages
  should normally be templates, skills, policies and capability requirements.
- **Do not confuse provider registry work with automatic model ranking.**
  Deterministic operator policy and explicit bindings remain supported.
- **Do not weaken HumanGate authority boundaries for convenience.**
- **Do not treat model-generated plans or reviews as deterministic validation.**
- **Do not automatically replay ambiguous interrupted effects.**
- **Do not add a new provider merely to demonstrate extensibility.** Adapter
  contracts should be stable enough that adding one is routine first.

## How the roadmap evolves

Each milestone should be driven by:

1. offline contract/security/regression tests;
2. subprocess/wire E2E;
3. live frontend/provider E2E where relevant;
4. recorded limitations and observed redundant behavior;
5. migration compatibility with persisted projects.

When evidence contradicts this roadmap, update the roadmap explicitly rather
than silently changing architectural principles in implementation commits.
