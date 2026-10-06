# v0.17 operational contracts

This document describes implemented operator operations. It is not a v1.0 release
approval, a human-presence attestation, or permission to modify the owner's live
runtime automatically. Use a normal operator terminal; marked agent/worker
contexts reject finalization, restore, cleanup and maintenance reconciliation.

## Cancellation: request, observe, finalize

`orchestrator cancel TASK_ID` is a durable cooperative request, not immediate
terminalization or remote cancellation proof. Repeating the same request adds no
new `cancel.requested` event. It does not probe/load providers, run validators,
execute the task, clean workspaces or change trust.

`status` and MCP `get_task` include a separate cancellation view v1. The original
TaskState serialization does not gain new fields. The view reports `requested`,
`terminal`, `finalization_eligible`, `blocked_by` and an exact scope only when the
current evidence permits idle finalization. Eligibility is rechecked under
exclusive worker/project locks; it is not a reservation of future availability.
An awaiting-approval task with a cancellation request is not runnable.

After inspecting the exact view, an operator may use:

```bash
orchestrator --project "$PROJECT" status TASK_ID
orchestrator --project "$PROJECT" cancel TASK_ID --finalize \
  --scope "<exact-finalization-scope>" --by "$USER"
```

Finalization requires the existing request, coherent idle state, no running node,
unresolved effect checkpoint, task-owned worktree, queued/running target job, or
pending/applying/uncertain target gate. It atomically records `cancelled`, clears
provider-permission grants and execution approvals, and appends the terminal
state event. It does not delete files, refund usage, rollback an accepted change,
relabel other terminal outcomes or undo a transitioned exploration. Already
finalized requests are no-ops. Running/ambiguous tasks still require conservative
recovery. Do not call `run` merely to change a status display.

Cooperative cancellation remains available while a provider holds the project
lock. A short shared `cancellation.lock` boundary prevents cancellation writes
from racing backup/restore/cleanup replacement; it is an excluded ephemeral lock,
not authority. All other cooperating state/queue/gate mutations share the project
lock and revalidate their state/scope after acquiring it.

## Request payload retention is not request-identity retention

Jobs SQLite v2 adds `request_receipts`: request ID, action/argument fingerprint,
original job ID, terminal outcome and retirement timestamp under receipt v1.
Receipt insertion and terminal job/job-event deletion use one SQLite transaction.
No raw prompt or full result is required in the receipt. v0.17 does not collect
receipts automatically.

A retry of an ordinary retained job returns that job as before. A retired ID
returns a structured `request_retired` refusal with the original identity and
`automatic_replay=false`; different arguments under any used ID also fail. Only
an intentional new operation receives a new ID. Cleanup must never make a
transport retry become another billable ask/exploration call.

A restore merges compatible known current identities with archived history.
Conflicting fingerprints/identities fail before destructive replacement.
Pending restored jobs are explicitly interrupted and pending/applying gates are
made non-replayable. The approvals table is authority state, not the canonical
historical audit ledger: restore revokes every execution-approval row, including
rows associated with terminal tasks, and reports the exact count. Historical
approval provenance remains in append-only runtime events and immutable task
evidence. Nonterminal task provider-permission grants are also revoked, while
terminal TaskState bytes and historical grant metadata remain byte-preserved and
are not reusable authority for another task. Full restore retains its existing
explicitly acknowledged project-profile/trusted-profile behavior; runtime-only
restore still never replaces current config/context. A receipt can still refuse
an old request even when an archived payload for it has been restored.

History already deleted by old software, or absent in an empty/unreadable target,
cannot be reconstructed. Restore reports its available receipt-history coverage;
this is not a claim of remote exactly-once execution or zero missing cost.

## Complete evidence roots

Doctor and retention share the same read-only inventory. It includes all retained
TaskState, IntakeState and ExplorationState references, immutable turn/transition
artifacts, recursively loaded accepted knowledge/policies/skills, retained
candidates and frozen historical ContextInfluence references. Removing current
accepted Markdown does not remove the corresponding historical evidence root.

Every reference is checked before deduplicating file reads. Contradictory hashes,
identities, kinds, owners or timestamps are errors, not a choice of first owner.
Missing v2 identity on compatible v1 metadata is not itself a contradiction.
Supervisor/transition semantic bindings are checked where versioned state carries
them. Unknown/incomplete/corrupt inventories block cleanup. Unrecognized/legacy
JSON and legacy untyped learning are retained conservatively. Eligible orphan
files require a bounded canonical layout and valid JSON plus absence from the
complete root set, age, exact content hash and a quiescent locked recheck; a UUID
suffix alone is never sufficient.

## Interrupted restore or cleanup

Before the first destructive mutation, the operator operation writes and fsyncs
an intent under `.orchestrator/runtime/maintenance-journal/`. The area has a
versioned format marker, `active.json` and per-operation recovery material.
It is not imported from archives, removed by replacement, or collected by normal
retention. Pre-existing unknown/colliding paths are refused. Restoration stages
raw pre-operation files/SQLite sidecars and a verified incoming archive there,
not solely in a temporary directory that disappears on process loss.

A pending or invalid intent blocks normal authority mutation, provider/validator
dispatch and worker startup before provider-plugin loading. An old open database
handle also refuses writes after its underlying database file was replaced.
Read-only operational diagnosis remains available without loading providers:

```bash
orchestrator --project "$PROJECT" maintenance inspect
orchestrator --project "$PROJECT" doctor --operational-only
orchestrator backup inspect "$BACKUP"
```

Inspection reports an exact reconciliation scope and whether the recorded before
or validated after snapshot matches. Reconciliation is explicit:

```bash
orchestrator --project "$PROJECT" maintenance reconcile \
  --scope "<reconciliation-scope>" --by "$USER"
```

It may clear only coherent completed/fully-rolled-back data after checking its
postconditions and appending durable audit evidence. It performs no additional
payload deletion or provider work. Mixed/incomplete state stays blocked. A
verified recovery restore needs the existing restore/authority/unreadable-state
acknowledgements and `--ack-incomplete-operation <current-reconciliation-scope>`.
The predecessor intent and recovery material remain retained. A recovery failure
must not clear the previous barrier. Manual journal deletion is not a supported
repair; automatic reconciliation, replay or worktree rollback is not provided.

An audit append failure cannot report clean success. Successful operations clear
the active marker only after data checks and durable completion audit. Completed
journal material can use significant disk space; v0.17 intentionally does not
provide automatic journal garbage collection. Retain it until an independently
reviewed operator archival policy is established.

Actual subprocess SIGKILL tests cover intent, partial file replacement/deletion,
DB commit, audit boundaries and rollback. They test cooperative POSIX process
loss, not power-loss guarantees on every filesystem or hostile same-user access.

## Installation identity

`orchestrator identity` reports package version, loaded/disk build fingerprints,
process start time/PID and packaged Skill/contract inventory hashes. It neither
requires provider credentials nor modifies host configuration. Optional explicit
`--skill PATH` arguments compare supplied host copies; no home-directory scan or
automatic synchronization occurs. A long-lived MCP/worker detecting loaded-source
or parent/worker identity drift refuses new work rather than mixing builds or
replaying an in-flight effect. Restart only after inspecting active work.
