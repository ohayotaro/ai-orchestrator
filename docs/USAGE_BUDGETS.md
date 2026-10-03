# Usage Observability & Budget Policy

v0.10 adds resource accounting after Provider Resolution and Model Variant
Resolution without turning cost into a routing signal.

```text
Task -> Node -> Provider -> Model Variant -> Execution -> Usage -> Budget -> Evidence
```

The four control-plane questions remain separate:

- capability: what work is required;
- provider: who executes it;
- model variant: how that provider runs;
- budget: how much attributable resource may be consumed.

A budget never grants capabilities, changes provider/model/effort, weakens a
validator, selects a different workflow, or answers a HumanGate.

## Usage evidence

Each provider call appends a normalized record to a hash-verified `usage`
artifact. Records bind:

- task or intake owner;
- call index and attempt;
- workflow node, role and phase;
- resolved provider, adapter and family;
- resolved model and effort;
- controller-measured call elapsed time;
- provider-reported elapsed time when exposed;
- input/output/reasoning/cache-read/cache-write/total token dimensions;
- cost evidence and provenance;
- adapter limitations.

Every provider field has one of three states:

- `known`: the provider supplied a valid attributable value;
- `unknown`: the adapter contract expects a value but this call did not provide
  one;
- `unsupported`: the adapter does not claim reliable support for the field.

Unknown or unsupported values have no numeric value. They are not converted to
zero and are not estimated from prompt/response length. Hidden reasoning is not
inferred.

Aggregation is deterministic from call records into task summaries and
`by_node`, `by_attempt`, `by_provider` and `by_model` groups. A metric is
`known` only when every contributing call is known. Mixed or missing evidence
therefore remains incomplete, with a separate `known_subtotal` for inspection.

Current built-in adapter boundaries are intentionally conservative:

- Codex: structured `turn.completed` JSONL token counters are accepted for
  input/output/reasoning/cache-read/cache-write when present. Total cost and
  provider elapsed time are not claimed by the adapter contract.
- Claude: JSON output counters are accepted for input/output/cache-read/
  cache-write, plus explicit API duration and provider-reported USD cost.
  Separately attributable reasoning/total token counters are not claimed.
- Antigravity (AGY): the current stream-json contract is not treated as a stable
  usage schema. Explicit counters may be retained opportunistically for
  observation, but strict token/cost/provider-duration budgets fail closed
  before dispatch.

Controller elapsed time is always measured independently with a monotonic clock.
Provider elapsed time is a separate field and is known only when the provider
reports it.

## Budget policy

v0.10 budget configuration is trusted project profile authority.

```yaml
policy:
  # Existing hard ceilings remain in force.
  max_agent_calls: 12
  task_timeout_seconds: 3600

  budget:
    schema_version: 1

    # Optional stricter ceilings.
    max_provider_calls: 8
    max_controller_elapsed_seconds: 1800
    max_provider_seconds: 1200

    max_input_tokens: 200000
    max_output_tokens: 80000
    max_reasoning_tokens: 50000
    max_total_tokens: null

    max_cost: "15.00"
    currency: USD

    # fail_closed is the default.
    unknown_usage: fail_closed

    call_limits:
      - provider: engineering
        model: gpt-example-exact-id
        max_calls: 4
      - provider: reasoning
        max_calls: 5
```

All fields are optional except `schema_version`, `currency`,
`unknown_usage` and the contents of any configured call-limit entry.

Existing `max_agent_calls` and `task_timeout_seconds` remain hard ceilings.
`budget.max_provider_calls` and `max_controller_elapsed_seconds` can only
tighten them; the effective limit is the smaller value.

`max_controller_elapsed_seconds` uses the task/intake controller elapsed
counter, which includes provider execution and registered validator time already
accounted by the kernel. `max_provider_seconds` uses only separately
provider-reported duration evidence and therefore requires adapter support under
strict enforcement.

Supervisor usage is cumulative across clarification rounds. When a Supervisor
proposal is confirmed, its calls, elapsed time, normalized usage and budget
status are carried into TaskState rather than reset. Manual TaskSpec creation
starts without a Supervisor intake ledger.

### Strict unknown handling

`unknown_usage: fail_closed` means a configured token/cost/provider-duration
dimension must be provable for the selected provider/model before dispatch. If
the adapter cannot reliably supply the needed field, the call is not made.

If an adapter advertises a field but a particular completed call omits it, the
record becomes `unknown`. The task fails closed before another effect. No value
is guessed.

`unknown_usage: allow` is an explicit operator choice to continue when a
constrained metric cannot be observed. Known values still enforce their limits.
It is not the default.

### Limit timing

Before a provider dispatch, the controller checks:

- effective task/provider call ceilings;
- exact provider/model call limits;
- current elapsed/token/cost consumption;
- whether strict constrained metrics are supported by the selected adapter/model.

After every provider call, actual returned evidence is normalized and persisted.
Exact exhaustion is valid for the call that consumed the remaining allowance and
blocks the next provider dispatch. A numeric overrun or a strict metric becoming
unprovable after a completed call fails the task before the next effect.

Parallel write batches reserve call allowance before worker dispatch, including
provider/model-specific caps. Per-call timing/usage is collected in worker
threads but persisted from the controller thread.

## Cost attribution

The kernel contains no unversioned vendor price table.

Cost evidence has three useful cases:

1. `provider_reported`: an explicit provider cost is returned and validated;
2. `controller_computed`: an exact provider-slot/model pricing rule exists and
   every rate-bearing usage dimension is known;
3. unavailable: evidence remains `unknown` or `unsupported`.

Provider-reported cost takes precedence over controller calculation.

Controller pricing is configured under the profile root:

```yaml
providers:
  reasoning:
    adapter: claude
    model: claude-example-exact-id
  engineering:
    adapter: codex
    model: gpt-example-exact-id

pricing:
  - schema_version: 1
    provider: engineering
    model: gpt-example-exact-id
    currency: USD
    source: "operator-maintained vendor pricing reference"
    version: "2026-10-03"
    effective_from: "2026-10-03T00:00:00Z"
    input_per_million: "1.25"
    output_per_million: "5.00"
    reasoning_per_million: "5.00"
    cache_read_per_million: "0.125"
    cache_write_per_million: null
```

Rules match the exact provider **slot** and exact resolved model ID. At most one
rule may exist for that pair. Only explicitly configured rate dimensions
participate in controller calculation, and each such dimension must be known.
No global/vendor wildcard is used.

Amounts use decimal arithmetic and are persisted to eight decimal places. A
budget has one explicit three-letter currency; mixed or mismatched known cost
currencies are unprovable for that budget.

Changing a provider slot's adapter through the bounded provider-change
HumanGate clears pricing rules for that slot, along with adapter-specific
executable/model/effort settings, so stale vendor pricing cannot silently cross
an adapter boundary.

## Inspection and artifacts

`inspect_project` exposes:

- `usage_observability`: adapter usage descriptors and limitations;
- `budget_policy`: legacy hard limits, v0.10 budget policy and pricing
  provenance.

`get_task` exposes current `usage` and `budget` state.

For immutable evidence:

```text
get_artifact(task_id=..., kind=usage)
get_artifact(task_id=..., kind=budget)
```

HumanGate start/execution/acceptance previews include a compact budget summary.
Execution and acceptance previews also bind the current normalized usage/budget
objects into the exact scope digest. The full task state, profile digest,
workspace/protected/control snapshots and normal approval invariants remain in
force.

## Non-goals and evidence boundary

v0.10 does not provide:

- automatic cheapest-provider/model selection;
- budget-driven model/effort degradation;
- provider billing reconciliation;
- provider-side attestation that a selected model/effort was honored;
- hidden-reasoning estimation;
- financial-ledger guarantees;
- general interrupted-execution recovery or replay.

Usage evidence states what the controller observed at the adapter boundary. It
does not claim that provider invoices or internal accounting systems will be
identical.
