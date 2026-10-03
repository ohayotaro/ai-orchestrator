# Recovery & Durability (v0.11)

v0.11 defines recovery as an evidence problem, not a retry policy. A durable
`running` row proves that an effectful phase was entered; it does not, by itself,
prove whether a provider, validator or root-worktree mutation occurred before a
process or host disappeared. The controller therefore resumes only when durable
evidence proves that replay cannot duplicate an effect.

## Core invariant

**Missing completion evidence is not evidence that an effect did not happen.**

Recovery never automatically replays ambiguous work, grants authority, accepts a
result, or rolls back the user's project worktree. Disposable runtime workspaces
may be deleted because they are controller-owned scratch state; user-visible
project files are not guessed back to an earlier state.

## Durable execution markers

Guarded and explicitly isolated writable batches use these relevant markers:

| Durable marker | Meaning for recovery |
| --- | --- |
| `workflow.guarded_write.preparing` / `workflow.parallel.preparing` | v0.11 stores the current root snapshot before creating/dispatching provider work. No provider dispatch has been acknowledged yet. |
| `call.started` | A controller call-budget reservation exists. Inside this isolated batch it is still releasable if the later batch `.started` marker is absent. |
| `workflow.guarded_write.started` / `workflow.parallel.started` | Provider dispatch may have started. A missing provider result is ambiguous; replay is prohibited. |
| `workspace.integration.prepared` | The aggregate patch is ready and root application may be about to occur. A crash after this marker is ambiguous. |
| `workspace.integrated` | The root effect is durably acknowledged. Later validation/review may still be incomplete, but implementation must not be replayed. |

Planner/reviewer calls and legacy shared-write execution do not have the isolated
pre-dispatch proof needed for safe resume. A validator may execute repository code
or produce generated outputs, so an interrupted validator is also treated as an
uncertain prior effect.

## Classification

`orchestrator status TASK_ID` and agent-facing `get_task` expose a read-only
`recovery` object while a task is durably `running`.

### `safe_pre_effect_retry`

This classification is emitted only when all of the following are true:

1. the current attempt has a v0.11 guarded/isolated `.preparing` checkpoint;
2. that checkpoint records the exact root snapshot;
3. the current root snapshot still matches it;
4. every running node is covered by that checkpoint;
5. the matching batch `.started` marker is absent; and
6. integration has not begun.

Even then, recovery itself does not retry. The operator-only
`orchestrator recover TASK_ID`:

- removes disposable task worktrees;
- releases only call reservations proven not to have been dispatched;
- resets the interrupted workflow node(s) to pending;
- clears task-scoped provider-permission grants;
- atomically deletes prior execution approvals with the recovered task-state
  transition;
- records an immutable `recovery` artifact and recovery audit events; and
- returns the task to `awaiting_approval`.

A fresh execution HumanGate is required before any provider call can occur. If
the user still explicitly requires AGY broad native permission, recovery has
invalidated that grant too: request a fresh provider-permission HumanGate first,
then the fresh execution HumanGate.

### `uncertain_effect`

Any ambiguity fails closed. Examples include:

- provider dispatch may have started;
- validator execution may have started;
- a legacy/shared writer may have changed the project directly;
- aggregate patch integration may have started;
- the root snapshot changed after the checkpoint;
- running nodes are inconsistent with the checkpoint; or
- the interrupted task predates the v0.11 root-snapshot checkpoint.

Operator recovery cleans disposable workspaces, clears stale approvals/grants,
writes recovery evidence, marks running workflow nodes failed, and terminalizes
the task as `failed`. It does **not** roll back the root worktree. Inspect the
worktree/evidence and create a new task if further work is needed.

## HumanGate durability

A host confirmation is moved to `applying` immediately before its bounded kernel
effect. If the process is lost after that point, the gate may remain `applying`
or be recorded `uncertain`. Gate diagnostics report these states as
effect-uncertain, with `automatic_replay=false` and request reuse disabled.

This is deliberate: start/approval/acceptance/configuration effects are separately
durable and must be inspected rather than inferred from a missing final gate
response.

## Durable job queue

The managed job queue already provides request-ID/fingerprint idempotency.
A stale worker-owned `running` job is marked `interrupted`; it is not
automatically re-enqueued. Task recovery and job retry remain separate decisions
because a durable job state cannot prove whether the underlying task effect ran.

## Provider failure attribution

Where an adapter can establish the cause without retaining provider output, v0.11
adds a content-free `failure_category` to provider diagnostics:

- `authentication`
- `quota`
- `permission`
- `configuration`
- `protocol`
- `provider_process`

Raw stderr is used only transiently for classification and is not persisted by
this taxonomy. Existing adapter-sanitized AGY permission diagnostics retain their
stricter content boundary.

These categories improve diagnosis; they do not authorize an automatic retry.

## Migration and compatibility

v0.11 does not bump TaskState schema version or the runtime SQLite user version.
Persisted TaskState v1-v7 rows and database version 2 remain readable.

This compatibility is intentionally asymmetric for interrupted work: an older
`running` row has no v0.11 pre-dispatch root-snapshot checkpoint, so the
controller cannot prove it is safe to retry. It is classified
`uncertain_effect` and fails closed on recovery. Completed/awaiting states do
not need rewriting merely because the package was upgraded.

Back up the complete `.orchestrator/runtime/` directory before upgrades and
never hand-edit SQLite/task JSON to manufacture a recovery classification.

## Non-goals

v0.11 does not provide:

- automatic provider/validator retry;
- provider-side idempotency keys or exactly-once remote execution;
- distributed transactions across provider, filesystem and controller state;
- generic rollback of user worktree changes;
- recovery of external effects (which remain unsupported);
- replay of an `applying` HumanGate; or
- proof against a hostile process running as the same OS user.

The supported guarantee is narrower: the controller either proves a specific
pre-effect isolated interruption can return to a fresh approval gate, or it
refuses to replay it.
