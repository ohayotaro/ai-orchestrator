# Exploration / Deliberation Sessions (v0.16)

Exploration is a durable, non-authoritative conversation before a concrete task.
It exists for requests such as “I am not sure what should change yet.” It is not
an alternative implementation mode and does not loosen TaskSpec or HumanGate.

> Exploration may change understanding; only an explicit transition may change authority.

## Lifecycle

```text
explore(request)
  -> ExplorationState v1, revision 1
  -> read-only provider reasoning, immutable turn evidence
  -> active
  -> explore(new clarification, exact expected_revision)
  -> active, revision + 1
  -> propose_from_exploration(exact revision, explicit user decision)
  -> Supervisor produces an IntakeState v6 proposal
  -> existing Start HumanGate
  -> TaskState v9, planning
  -> existing Execution HumanGate / validators / fresh review / Acceptance
```

Neither a completed exploration turn nor a completed proposal creates an
executable task. Start remains the registration/planning authority boundary.
Execution and Acceptance remain separate confirmations.

A turn contains a current summary, hypotheses, assumptions, options, trade-offs,
open questions, model-interpreted decisions, discarded ideas and reported payload
paths. No acceptance criteria, allowed paths, validator list or workflow is
required in the exploration contract. Those become concrete only in the normal
Supervisor proposal. Extra authority-bearing result/input fields are rejected.

States are `running`, `active`, `proposing`, `proposed`, `transitioned`, `failed`
and `abandoned`. `running`/`proposing` may mean active work or an interrupted
operation; read-only inspection does not assume that a process has died.
The project lock prevents an abandon/revision from racing a cooperating active
provider call.

## Revision and stale proposals

Revising an existing session requires its exact current revision. The controller
serializes mutations under the project lock. A revision of a `proposed` session
supersedes its unconsumed intake before the next provider call. A pending Start
confirmation for that intake can no longer authorize registration.

An explicit `abandon_exploration` withdraws the linked, unconsumed proposal and
retains history. Once Start has consumed the source, the session is
`transitioned`; revision/abandonment cannot undo an already-registered task.
The source transition and task registration commit in one runtime transaction.

`propose_task(reply_to=...)` cannot revise an exploration-linked intake behind
its source's back. Revise the exploration, then make a new explicit transition.
A stale queued revision/transition fails rather than rebasing itself onto newer
understanding.

Repository drift may be inspected in a new exploration turn. The new turn records
the new snapshot and marks prior understanding as historical. A transition
requires the exact current exploration snapshot, and Start rechecks the usual
profile/worktree/scope bindings. Profile/provider/model identity drift fails
closed; it never silently reroutes an ongoing session.

## Context and evidence

`runtime/state.sqlite3` owns the `explorations` table. Each session retains
immutable `exploration_turn` and `exploration_transition` artifacts. Turn
artifacts record the user clarification, source snapshot, selected accepted
project context, result, provider-dispatch/workspace provenance and usage.

The deterministic `latest-understanding-v1` selector passes the current
understanding and latest user clarification, not an ever-growing transcript.
Its manifest names the selected turn artifact and the number of omitted older
turns. All omitted/discarded turns remain available through hash-verified
inspection. Sessions are bounded to 64 turns, structured results to 12 KiB and
the complete provider prompt to 64 KiB. Existing project policy can impose a
lower call/time limit. Oversized work fails before dispatch rather than silently
cutting authority-bearing input.

`reported_paths` is a provider claim about selected source material. The
controller verifies that each path exists in the inspected payload snapshot and
records its hash. This is not independent proof that the provider actually read
that path. Hypotheses and model-interpreted decisions likewise are not validated
facts or authenticated human authorization.

An explicit transition freezes the selected understanding, source revision,
snapshot and exact user decision in a hash-verified transition artifact.
`IntakeState.exploration` and `TaskState.exploration` carry its typed provenance.
The Start preview shows the source session/revision; full scope binds the complete
reference. Task inspection can read `get_artifact(kind=exploration_transition)`
without rehydrating an unbounded discussion.

Exploration does not promote Project Learning, write accepted Markdown, install
a workflow, register validators, or alter profile trust. Later accepted task
results may enter the normal governed learning process; exploratory prose alone
is not such evidence.

## Providers, usage and interruption

Reasoning uses the existing Supervisor capability/provider binding, with its
read-only `supervise` execution phase and disposable project snapshot. That
snapshot omits orchestration control and ignored ambient content, and writes to
it are rejected. This is the existing trusted-local boundary, not a new hostile
same-user OS sandbox.

An explicit provider-local model/effort override may be supplied at session
creation. Resolution is frozen and checked on later turns and the proposal call.
Mid-session overrides, hidden fallback and automatic intensity increases are not
supported. Normal adapter-native permissions apply; exploration cannot request
broad provider permission.

Calls, measured provider-call elapsed time, token/cost evidence and strict budget
checks accumulate across turns, proposal and the resulting task. User think time
between turns is not provider-call elapsed time. Unknown telemetry remains
unknown. A strict budget lacking the required adapter evidence blocks dispatch.
There is no budget-driven provider/model/workflow fallback.

The session's call reservation is durable before provider dispatch. During the
proposal call, intake accounting and the source-session link/counters commit
together. A process loss cannot erase the reservation or make an unrecorded call
appear as known zero. Interrupted `running`/`proposing` states are not retried by
inspection or worker restart. Inspect the evidence and explicitly abandon the
session; remote completion/cost may still be uncertain. Abandonment neither
asserts remote cancellation nor replays the effect.

## MCP and CLI

MCP adds six bounded surfaces:

| Tool | Contract |
| --- | --- |
| `explore` | Queue first turn or exact-revision refinement; stable request ID |
| `get_exploration` | Read current understanding, evidence references, usage and status |
| `list_explorations` | Bounded session summaries |
| `get_exploration_artifact` | Read one owned, hash-verified artifact, never an arbitrary path |
| `propose_from_exploration` | Queue a proposal from an exact revision and explicit decision |
| `abandon_exploration` | Withdraw an unconsumed source/proposal without deleting history |

Single-terminal clients use the managed worker and `wait_job` for both reasoning
and proposal. The host must explain the current uncertainty and wait for the
user's explicit decision before requesting a task proposal. A tool argument is
not a HumanGate answer.

For deliberate operator CLI use:

```bash
orchestrator --project "$PROJECT" explore "Compare alternatives; do not implement"
orchestrator --project "$PROJECT" exploration X-...
orchestrator --project "$PROJECT" explore "Change direction; prefer a smaller change" \
  --session X-... --revision 1
orchestrator --project "$PROJECT" exploration-propose X-... --revision 2 \
  --decision "Propose the bounded implementation and tests"
# Read the returned intake, then use the existing Start/Execution/Acceptance flow.
orchestrator --project "$PROJECT" exploration-abandon X-... --revision 2
```

`explore --model ... --effort ...` is creation-only. Normal host sessions must
not run provider-spawning exploration CLI commands to bypass the MCP worker
boundary. The recursion guard rejects those commands in a marked host/worker.

## Operational compatibility and verification

v0.16 introduces runtime SQLite user_version 3 (adds the exploration table),
TaskState v9, IntakeState v6 and exploration Job v2. Older supported rows and
artifact bytes remain readable without rewriting them; legacy TaskState/IntakeState
serialized shapes omit the new field so historical evidence digests remain
stable. Normal ask/run jobs remain Job v1. Gate and jobs database versions do
not change.

Back up the complete control/runtime state and stop controllers/workers before
upgrading. Older kernels cannot interpret the new runtime DB version. Downgrade
requires the retained pre-upgrade backup, not manually lowering a schema marker.
See [Migration](MIGRATION.md) and [Persistence](PERSISTENCE.md).

Doctor includes exploration state/evidence. Retention protects every retained
session and turn/transition artifact, including abandoned sessions. Runtime and
full backups include them; restore preserves the existing explicit authority
acknowledgement rules. No new MCP maintenance permission is introduced.

Offline tests cover multi-turn direction changes, frozen context/usage,
interrupted dispatch, stale Start, invalid authority fields, budgets, migration,
backup/retention and a real subprocess MCP-to-managed-worker-to-three-HumanGate
flow with deterministic provider shims. This is not a live external-provider or
human-click attestation. A live host run remains a separate release-closure check.
