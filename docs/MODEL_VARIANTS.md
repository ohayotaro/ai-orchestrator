# Provider Resolution and Model Variant Resolution

Status: **v0.5.x design boundary retained; implementation is now targeted for
v0.9.0-v0.9.2.**

This document fixes the boundary that the workflow/DAG and v0.9 runtime-policy
implementation depend on.

## Decision

AI Orchestrator uses two separate resolution stages:

```text
Task / workflow node
        |
        | semantic capability requirements
        v
Provider Resolution
        |
        | provider identity + adapter + family
        v
Model Variant Resolution
        |
        | provider-local variant + model + effort + execution options
        v
Adapter execution
```

Provider Resolution and Model Variant Resolution are different contracts and
must not be collapsed into one opaque "best model" selector.

## Provider Resolution: who

Provider Resolution is implemented in v0.5.

Inputs include:

- role/workflow-node semantic capability requirements;
- fixed provider override;
- ordered provider candidates;
- deterministic provider priority;
- provider-family policy such as cross-provider review.

Output identifies:

- provider;
- adapter;
- provider family;
- resolution source;
- required/offered semantic capabilities;
- candidates considered;
- adapter API version.

The current resolution is deterministic and inspectable. It does not benchmark,
score or silently rank model quality.

## Model Variant Resolution: how

A provider may expose multiple execution variants. A variant is provider-local
configuration, not a semantic capability. v0.9 implements this resolution layer
after Provider Resolution.

The intended precedence is:

```text
task/node explicit override
        >
trusted profile variant/runtime policy
        >
adapter default
```

An explicit task override is ephemeral task authority and must be frozen into the
task/node approval scope. A persistent default is project profile authority and
must use the bounded profile-change/trust path rather than arbitrary config
editing.

Conceptual configuration:

```yaml
providers:
  engineering:
    adapter: codex
    capabilities: [repository_analysis, planning, code_edit, test_authoring, review]

    variants:
      default:
        model: null
        effort: null

      fast:
        model: <operator-configured-model>
        effort: medium

      deep:
        model: <operator-configured-model>
        effort: high
```

The concrete schema is intentionally not implemented/frozen yet. The invariant
is that a variant resolves only **after** provider selection.

A Model Variant Resolution result should identify at least:

- provider-local variant ID or explicit override;
- concrete model value passed to the adapter;
- effort/reasoning setting where the adapter supports one;
- resolution source/policy;
- fallback decision, if any;
- adapter execution options relevant to the approved scope;
- runtime-option discovery/provenance source.

### Adapter runtime-option discovery

v0.9 must not maintain a kernel-global list of vendor model names or effort
values. Each Provider Adapter is responsible for describing the runtime choices
it can reliably control or verify.

Conceptually:

```text
adapter.describe_runtime_options()
  -> model IDs / selection mode
  -> supported effort values
  -> named execution-option dimensions
  -> discovery source / limitations
```

Discovery may come from a reliable provider CLI/API, a tested adapter contract,
or explicit trusted operator configuration. If a provider does not expose a
reliable list, the adapter must report that limitation rather than claim a
complete catalog. Pass-through model identifiers may be supported only when the
adapter can still validate the invocation contract and record provenance
honestly.

## Capability is not execution intensity

Do not encode execution intensity as semantic capability.

Avoid:

```yaml
requires:
  - code_edit
  - high_reasoning
```

Prefer the conceptual separation:

```yaml
requires:
  capabilities:
    - code_edit

execution:
  class: deep
```

`code_edit` answers whether a provider can perform the semantic work.
`deep` expresses an execution policy for a provider that has already been
selected.

This keeps the Capability Registry stable when vendors rename models or change
reasoning/effort controls.

## DAG boundary

v0.6 workflow nodes should not normally contain concrete vendor model names.

Conceptually:

```yaml
id: implement_backend
requires:
  - code_edit
  - test_authoring
execution:
  class: deep
depends_on:
  - architecture
```

Resolution becomes:

```text
node requirements
  -> Provider Resolver
  -> Model Variant Resolver
  -> worker invocation
```

A workflow therefore survives replacement of one provider/model with another as
long as the required contracts remain satisfiable.

Explicit operator overrides may still pin a provider or variant for debugging,
reproducibility or policy reasons.

## Operator-controlled policy first

Initial variant routing is deterministic trusted policy plus explicit
task/node overrides, not autonomous quality ranking. For example:

```yaml
variant_policies:
  normal:
    prefer: [default]
    allow_fallback: true

  critical:
    prefer: [deep]
    allow_fallback: false
```

This is illustrative, not a committed configuration schema.

The Supervisor must not silently decide that a task is "hard" and increase model
cost/effort outside approved policy. It may propose a trusted execution class or
task-scoped override when the user asks for quality/cost behavior, but the exact
resolved model/effort must be visible in authority provenance. Difficulty
estimation, historical performance routing and learned selection remain later
adaptive features.

## Fallback and fail-closed behavior

Fallback is a policy decision.

If a requested `deep` variant is unavailable:

- a policy with explicit fallback may try its next configured variant;
- a policy without fallback fails before billable work/effects.

There is no implicit downgrade or cross-provider switch hidden inside Model
Variant Resolution. A provider change returns to Provider Resolution and must be
reflected in provenance/scope.

## Freeze, approval and provenance

Provider and variant decisions are independently auditable.

Conceptual task provenance:

```yaml
provider_resolution:
  provider: engineering
  adapter: codex
  family: openai
  source: candidates

variant_resolution:
  variant: deep
  model: <resolved-model>
  effort: high
  source: policy
```

Both resolutions must be frozen before the relevant execution and included in
the HumanGate/approval scope. Changing provider, model, effort or material
execution options after approval invalidates the scope rather than silently
continuing.

This extends v0.5's existing frozen provider-resolution behavior.

## Budget is a separate concern

The intended separation is:

| Question | Contract |
| --- | --- |
| What must be done? | semantic capabilities |
| Who can do it? | Provider Resolution |
| How should that provider run? | Model Variant Resolution |
| How much may it consume? | budget policy |

Time/token/cost budgets therefore remain separate from capabilities and model
variants. v0.9.0 establishes runtime-option/variant provenance, v0.9.1 adds
task/node execution-policy authority, and v0.9.2 layers reliable usage/cost
telemetry and budgets on top of those frozen choices.

## Frontends such as Cursor, OpenCode and Devin

Frontend identity is independent of worker provider/model identity.

A client such as Cursor, OpenCode, Devin or another coding agent can sit **in
front of** AI Orchestrator when it can integrate with the agent-facing contract
(for example MCP plus the portable Skill, or a future equivalent adapter). In
that case it behaves like Claude Code/Codex do as frontends today: it proposes
work and surfaces HumanGates; the Orchestrator independently resolves worker
providers and later model variants.

A product can also be a **worker provider** only if it exposes a sufficiently
controllable non-interactive interface that a Provider Adapter can implement:
fresh invocation/session semantics, bounded filesystem/tool behavior, structured
result contract, cancellation/timeouts, explicit model/effort controls where
claimed, and reliable provenance. Merely having an interactive UI or an internal
model selector is not enough.

Therefore "use Cursor/OpenCode/Devin to call different models" is not assumed to
be equivalent to native model/provider resolution. If such a frontend internally
chooses an opaque model, AI Orchestrator cannot truthfully attest which concrete
model/effort ran. That mode may be supported as an opaque provider capability,
but concrete Model Variant provenance must remain unknown unless the integration
can select and report it reliably.

This distinction preserves the core rule: Orchestrator only records model-level
provenance that its adapter can actually control or verify.

## v0.9 non-goals retained from the original decision

Implementing Model Variant Resolution does **not** imply:

- automatic model-quality ranking;
- opaque task-difficulty scoring;
- learned routing that silently changes model/effort;
- implicit provider/model fallback;
- vendor-specific model names in the Capability Registry;
- treating `high`/`xhigh`/similar effort labels as universal kernel enums when
  an adapter does not support them;
- inventing token/cost numbers when a provider cannot attribute them reliably.

Any later optimization policy must build on explicit provenance and budgets
rather than replacing them.
