# v0.17 — Release Candidate Hardening: approved design

Status: **DESIGN FINALIZED; implementation and release verification pending**.
Decision date: 2026-10-06 JST.
Audited baseline: `b2700fda59b56bad0ced555f3a6e3e7f9badc6b8`
(package 0.16.0; v0.16 live closure recorded).

This is the normative elaboration of the v0.17 section of [ROADMAP](../ROADMAP.md).
It fixes scope, safety decisions and exit criteria; it does not declare v0.17
implemented, release-ready or live-verified. Findings and reproducible baseline
observations are in [the design audit](V017_DESIGN_AUDIT.md).

## 1. Decision and scope boundary

v0.17 stabilizes the existing trusted-local control plane. It is not another
feature-expansion milestone. Fix demonstrated lifecycle/evidence defects first,
then freeze a candidate contract, validate it, and prepare the v1.0 release.
A previously passed live fixture is evidence for the exercised cases, not proof
that every edge case in that version is correct.

The release must distinguish three different facts:

1. A non-authoritative request or cancellation intent exists.
2. The controller has durably observed and applied the requested state change.
3. A provider or other external effect has actually completed or stopped.

None implies the next without evidence. In particular, cancelling a request is
not remote exactly-once/cancellation attestation; a passing schema test is not a
human-click test; and a documented data-loss defect is not an acceptable RC.

Mandatory workstreams are RC-01 through RC-07 below. Findings marked BLOCKER
must be fixed and covered by regressions before RC freeze. Host limitations may
remain conditional only when the affected operation fails closed, the exact
combination is identified, and the required supported baseline still passes.

Non-goals remain: new providers or model catalogs, automatic provider/model or
budget-driven fallback, wider agent permissions, new DAG/exploration features,
automatic learning promotion, distributed controllers, remote exactly-once,
hostile same-user isolation, authenticated human-presence claims, Windows
execution support, automatic repair/replay, and deletion of canonical history.
No host-specific approval fallback or provider-change binding-cleanup workaround
is introduced to make tests pass.

## 2. RC-01 — Cancellation intent and safe finalization

### Preserve the request contract

`orchestrator cancel TASK_ID` remains a provider-free durable cancellation
request. Repeating an already-recorded request must be idempotent: no additional
request event merely because the same command was repeated. It must not invoke
`run`, a validator, provider probing, a model call, or workspace cleanup.
Existing terminal success cannot be converted into cancellation.

CLI `status` and MCP `get_task` must expose an additive, versioned cancellation
view derived from the canonical cancellation column, not manufacture a new
field in historical TaskState serialization. It reports at least:
`requested`, `terminal`, `finalization_eligible`, `blocked_by`, and an exact
`finalization_scope` when eligible. `awaiting_approval` plus `requested=true`
must not be presented as either runnable or already terminal.

Cancellation must be checked consistently at all relevant entries: direct CLI
approval, provider-permission approval, MCP scheduling, HumanGate capture and
resolution, preflight and immediately before a new provider/validator dispatch.
The existing HumanGate cancellation check is retained. No newly granted approval
or new dispatch may follow a cancellation already observed by the controller.
A call already dispatched is best-effort cancellation, not a promise of no cost
or remote effect. Pending results with uncertain effects retain recovery evidence.

### Add one narrow operator operation

The approved public shape is:

```text
orchestrator status TASK_ID
orchestrator cancel TASK_ID --finalize --scope EXACT_SCOPE --by OPERATOR
```

`--finalize` requires a recorded cancellation request and a freshly recomputed
scope. It is operator-only, never a new MCP mutation tool, never inferred from
chat agreement, and never implemented by running an already-cancelled task.
Marked agent/internal-worker contexts must reject it before mutation. These are
trusted-local guards, not cryptographic operator authentication.

Eligibility requires worker/project exclusivity in the established lock order,
readable coherent state, and an idle task in `ready`, `awaiting_approval` or
`awaiting_acceptance`. There must be no running workflow node, unresolved
effect/integration checkpoint, task-owned worktree requiring recovery, queued or
running target job, or pending/applying target gate. All cooperating queue and
gate mutation paths must honor the same project-lock boundary. Failure to prove
eligibility is a refusal, not a force option.

The scope covers the target task, cancellation intent, relevant evidence and
blocking job/gate/workspace observations. A stale scope cannot be rebased.
Successful finalization atomically sets task status to `cancelled`, preserves
the cancellation flag/history, clears task provider-permission grants and
revokes execution approvals, and appends the terminalization event in the same
runtime transaction. It never removes files, rolls back the root worktree,
changes trust, refunds usage, or rewinds a transitioned exploration.

A running/interrupted task still uses conservative recovery. Existing terminal
failed/blocked/abandoned outcomes are not relabelled; already-finalized repeated
calls return the terminal outcome without another mutation. Reads never finalize.

Required tests include cancel-before-approval; cancel while a gate is open;
direct-CLI parity; repeat requests; finalize an idle unexecuted task; refuse
running/ambiguous/queued cases; stale scope; transaction interruption; and prove
zero new provider, validator or workspace effects. Finalized tasks cease to be
unfinished provider-change blockers, without widening binding-cleanup semantics.

## 3. RC-02 — Safer HumanGate presentation without new authority

Keep the existing single required string decision and exact wire values.
Change the presentation order to `enum: ["no", "yes"]` with matching labels.
Use operation-specific titles identifying Start, Execution, Acceptance or the
other existing exact authority request. The bounded summary must make the
operation, subject, write/effect scope and provenance visible.

For the currently supported 2025-06-18 form contract, do not add an enum default
or a new checkbox/second confirmation field. No affirmative value is supplied
by the server. No-first is a usability measure, not proof of an explicit human
choice: the host controls rendering, selection and keyboard focus.

The only affirmative response remains the correlated, unexpired, current-scope
`action=accept` with exactly `content={"decision":"yes"}`. `no`, decline,
cancel, omitted/invalid fields, timeout, disconnect, stale state and duplicate
responses authorize nothing. No code fills in a missing answer, increases a
permission, retries a gate automatically, or uses a CLI fallback.

The server cannot distinguish a human click from a host hook that sends the same
response. Absence of a hook in one settings file is not proof of human presence.
Preserve this limitation in the UI, diagnostics, documentation and test reports.

For each host designated supported, test its untouched/default submission,
explicit No, cancel, explicit Yes, timeout and stale-response behavior using the
actual displayed form. An accidental Yes is a real authorization, not rejection
evidence. Stop that probe and do not request Execution to clean up the mistake.
Do not automatically create more paid probes until the user explicitly retries.
No-first must pass the existing independent SDK/schema and subprocess tests;
unsupported rendering is recorded per host/version rather than worked around.

## 4. RC-03 — Complete evidence roots and non-lossy physical retention

Create one shared canonical reference inventory for diagnosis and retention.
It must enumerate TaskState artifacts and exploration references, IntakeState
artifacts and transition references, all ExplorationState turn/transition
artifacts, typed frozen ContextInfluence evidence, retained learning candidates,
and accepted knowledge/policy/skill metadata. Traverse accepted Markdown using
the same recursive, confined path universe as Project.load(), not top-level
`glob("*.md")`. Historical/abandoned/superseded records remain roots.

Inventory every reference before de-duplicating file I/O. Multiple owners may
legitimately share a Supervisor/transition artifact. Compatible identical
references pass; disagreements in expected SHA, stable identity, kind or other
version-applicable metadata are explicit integrity conflicts. Artifact v1's
absent v2 identity fields must not be invented or treated as conflicts by
absence alone. For the same stable artifact ID, contradictory paths/content
cannot be silently merged. Diagnostics name the owners and disagreement;
`setdefault`/last-writer-wins must never conceal a failing reference.

Each recognized evidence type also receives its versioned semantic checks:
Supervisor evidence agrees with its IntakeState; exploration transition source
and selected revision agree; reported JSON is valid, bounded and contains no
unsupported version. Historical authority-bearing serialized hashes remain
unchanged. Integrity is not a claim that model statements are true.

An incomplete, corrupt, unknown or conflicting inventory blocks cleanup. A
filename ending in a UUID is only a candidate-shape filter, never sufficient
proof that a file is disposable. Legacy/untyped references are conservatively
retained. Identity-resolvable typed evidence remains retained even when its
current accepted Markdown has been removed but frozen historical influence
still refers to it. Never infer evidence identity from model prose.

Before deletion, recompute the inventory and exact plan under locks. Bind
candidate file identity/content and relevant worktree/job inventories into the
scope; names/counts alone are insufficient. Reject symlinks, traversal, special
files, unknown schemas and drift. Canonical task/intake/exploration/event/gate
history and immutable reference roots are never cleanup targets.

Tests must cover all statuses and root types, nested accepted Markdown, shared
identical/mismatched metadata, legacy v1/v2 overlap, removed-current-context
historical references, unreadable state, drift and a genuinely orphan candidate.
A fresh non-stale proposal must still inspect and cross an explicitly approved
Start after scratch cleanup; the historical stale v0.15 fixture is not that proof.

## 5. RC-04 — Retention cannot erase idempotency

Deleting a terminal job payload must not turn a previously used request ID into
a new billable request. Add a compact durable request receipt/tombstone in the
jobs database. This is the one pre-approved database schema increase for the
core RC plan: jobs SQLite v1 -> v2, with supported old versions migrated and
older kernels failing closed on the new version.

A receipt contains version, request ID, the existing action/argument fingerprint,
original job ID, terminal outcome and retirement timestamp; it need not retain
raw prompts or complete results. It is not execution authority. Receipt creation
and corresponding job/job-event removal occur in one jobs SQLite transaction.
Migration preserves currently retained requests; it cannot reconstruct request
IDs already erased by older cleanup.

Every enqueue path checks live records and receipts in the same transaction.
An identical retry of a retained live/terminal job returns that job as before.
An identical retry of a retired request returns a structured `request_retired`
refusal with the original job identity and `automatic_replay=false`, not a new
queued job or a fabricated result. Changed arguments under either used ID fail.
An intentional fresh operation needs a genuinely new request ID.

Receipts are retained by v0.17 cleanup and included in backups. Restore preserves
known current receipts when replacing job payload state, merging only compatible
identities; conflicting records fail closed. An explicit restore into an empty
or unreadable history has a documented lineage/coverage boundary: it cannot
prove requests outside the available evidence never ran remotely. Restored
queued/running jobs and nonterminal gates must not be automatically dispatched
or replayed as a side effect of restoration/restart. Any authority revocation
needed to enforce this is explicit restore audit evidence, not a rewrite on read.

Required tests: same/different-argument retry before/after cleanup, ask/run/
explore/proposal actions, receipt-write/delete crash windows, concurrent enqueue,
backup/restore with overlapping receipts, unknown receipt version, old-kernel
rejection, and zero additional provider calls from retired-ID retries.

## 6. RC-05 — Interrupted maintenance must remain visibly blocked

The current exception rollback path is not a process-crash or power-loss
transaction. Add a durable maintenance intent before the first destructive
restore/cleanup operation. Its versioned record binds operation ID, actor,
verified scope, action, bounded target inventory, recovery evidence and phase.
Persist intent and required parent-directory durability before mutation.

Reserve a controller-only maintenance journal area under runtime. Normal
restore replacement, backup extraction and retention must neither erase nor
import an active intent from an archive. A colliding pre-existing path is a
refusal. Retain verified rollback/reconciliation material across process loss;
an automatically deleted temporary directory cannot be the only copy.

A pending/inconsistent intent blocks normal authority mutation, provider/validator
dispatch and worker auto-start before code-bearing provider loading. Read-only
maintenance diagnosis and archive verification remain available. Invalid markers
also fail closed. All cooperating entry points must check, not only the CLI.

An operation is complete only after data checks and durable audit completion.
Failure to append the completion event must not report clean success or leave an
unmarked partially restored controller. Caught-error rollback remains bounded
by the original explicitly authorized operation; crash recovery never silently
replays work, drops the marker or rolls back the user's root worktree.

Provide read-only `maintenance inspect` with the current incomplete operation
and an exact reconciliation scope. Operator-only
`maintenance reconcile --scope EXACT_SCOPE --by OPERATOR` may clear a completed
or fully rolled-back intent only after all recorded postconditions are verified.
It performs no provider execution or additional deletions. Mixed/incomplete
state stays blocked and requires an explicitly inspected restore using the
existing backup/authority acknowledgements plus an explicit acknowledgement of
the incomplete operation; manual deletion of the marker is not a supported fix.
Recovery operations must preserve the previous intent and verified recovery
material until the new operation is durably reconciled.

Crash-injection gates cover before intent, after intent, after a subset of file
replacement/deletion, after DB commit, before/after audit completion, and during
rollback. Verify that restart is either fully coherent or diagnostically blocked.
Atomicity across arbitrary filesystems, remote services or hostile same-user
processes is not claimed. Full restore's explicitly acknowledged profile-trust
semantics remain distinct from runtime-only restore; no new MCP maintenance
permission is introduced.

## 7. RC-06 — Candidate contracts, compatibility and installation identity

Freeze public behavior and serialized schemas, not every internal Python helper.
Create a machine-readable contract inventory with name, version, authority,
public entry point, compatibility policy, negative tests and stability tier.
Golden tests must cover wire shape, canonical hashes, unknown-version refusal
and the absence of new null fields in legacy models. Versioned additive response
views must not change old TaskState/IntakeState evidence hashes.

Baseline candidates are:

| Surface | Candidate baseline / policy |
| --- | --- |
| TaskSpec, profile/effect/write policy | Existing semantics; unchanged-profile fingerprint compatibility |
| TaskState / IntakeState | v9 / v6; supported historical readers retained |
| Exploration state, turn, transition | v1; explicit transition and stale-source rules stable |
| Artifact | v1 read / v2 write; shared-reference rules above |
| HumanGate | Current schema; affirmative wire values and authority unchanged |
| Workflow | Workflow Schema v1; compiler/effect/independence contracts stable |
| Provider/plugin | SDK v1 / adapter v2; exact pin/load rules stable |
| Usage/budget / learning/influence | Versioned provenance and governance stable; unknown stays unknown |
| Runtime / gate / jobs SQLite | 3 / 1 / planned 2; migrations explicit and tested |
| Job | Existing v1/v2 actions; retired-request refusal separate from Job results |
| Cancellation view / receipt / maintenance intent | New independent v1 contracts; no implicit old-row rewrite |
| MCP / CLI | Inventory all documented entry points; strict inputs, classified errors and authority matrix |
| Heuristics, display prose, private helpers | Intentionally unstable; cannot change safety/fingerprint behavior silently |

Any further persisted-schema change needs a reviewed design amendment before
freeze; do not silently cram incompatible authority semantics into an old version.
Published readable versions must each have retained-fixture evidence or an
explicitly documented unsupported boundary. Restored backups must include the
matching software/schema guidance; downgrade is never a PRAGMA edit.

Keep the current execution support baseline: Linux Python 3.11/3.12/3.13 and
macOS Python 3.13. Distinguish minimum installation requirements from tested
support, and do not infer support for a newer interpreter from `>=3.11` alone.
Test minimum and locked reference dependency sets; record exact versions. Build
sdist and wheel, install the wheel into a clean environment outside the checkout,
and run CLI/Skill/worker/import smoke tests so editable installs cannot hide
missing package data. The independent MCP SDK tests must not be skipped in the
release matrix.

Expose content-free installation/build identity in diagnostics: package version,
contract-inventory digest, packaged Skill hash, process-start/build identity and
provider CLI versions. A long-lived MCP process/worker using a different loaded
build must not silently continue after an editable source update. Diagnose the
mismatch and stop new work; do not kill or replay an in-flight effect. Offline
inspection must not require live provider credentials. Source/installed/host
Skill drift is reported, never repaired or trusted implicitly.

## 8. RC-07 — Qualified support matrix and release evidence

Maintain separate axes for host transport and provider-role execution. Each
matrix entry records host/version, negotiated protocol/capabilities, kernel
build, provider CLI/version/role, explicit runtime options, OS/Python, native
permission assumptions, evidence date and test identifiers. A model name or
client brand alone is not a compatibility result.

Statuses are `supported`, `conditional`, `known-incompatible` for the exact
operation/configuration, and `unverified`. Historical PASS on another release
or role does not automatically confer current support. A transport timeout does
not prove which party is at fault. A No/cancel response is a correct refusal,
not evidence that positive approval works on that host.

Required positive live baseline: Claude Code host with Claude reasoning/review
and Codex implementation on the existing supported local deployment. Preserve
previous same-family explicit-distinct-model and plugin contract regressions.
Codex-host and Antigravity-host positive execution may remain conditional until
fresh full-form evidence exists; reproduce/document their negative boundaries
without broad permissions or hidden host-specific schema rewrites. Do not block
safe core release solely because every Cartesian product is not supported, and
do not label any untested combination supported.

Live probes use a fresh small task/intake and explicit expected outcomes.
Check that the requested behavior is absent before a Fresh-Write test. Record
source revision, exact gate IDs, actual selected response, runtime state, before/
after hashes, usage and measured validator outcome. Never substitute the
Planner's predicted test count for actual pytest output. Known cost subtotal is
not total cost when any provider telemetry is missing.

The reference positive flow, a genuine Start refusal, and an idle-cancellation/
finalization probe must each pass twice on fresh fixture IDs at the same final
build, without automatic retry. A versioned matrix entry includes both runs.
Interrupted maintenance/recovery and negative corruption tests run only on
scratch state. Repeatable offline/subprocess tests remain mandatory even when
live tests pass. No original-project cleanup/restore, runtime row surgery or
host-form auto-answering is permitted to manufacture evidence.

### Release gates and ordering

| Gate | Required evidence | Exit condition |
| --- | --- | --- |
| A — design baseline | This document and audited findings | Approved design; implementation still pending |
| B — correctness | RC-01, RC-03, RC-04, RC-05 regressions and RC-02 wire behavior | Every blocking defect fixed; new failures investigated |
| C — compatibility freeze | RC-06 inventory, migration fixtures, build/install tests | Exact versions/hashes, no silent incompatible behavior |
| D — supported live qualification | RC-02/RC-07 host forms and operational scratch matrix | Required supported entries PASS twice; others honestly classified |
| E — release decision | All required checks on final source tree, reviewed evidence and known-issue register | No open authority, data-loss, replay, migration or recovery blocker |

Sequence implementation PRs as lifecycle/cancellation; canonical evidence and
retention receipts; maintenance interruption guards; HumanGate/installation
identity; contract/build/host matrix; final qualification. Add the regression
before each fix. RC-03/04 may be one atomic storage-focused change. A discovered
core defect goes back to Gate B, not to an unconditional release waiver.

Use 0.17.x for hardening work and follow-ups. A v1.0 release candidate/tag is a
separate explicit release decision after Gates B-D; the v0.17 label is not itself
a v1.0 guarantee. No automatic package publication, tag creation, repository
permission change or upgrade of the owner's live runtime is authorized by this
design. On the final implementation PR, all required CI checks must finish
successfully on the exact head; do not merge first and assume a queued run will
pass. Re-run applicable checks if head/base changes the tested tree.

PASS, FAIL, NOT TESTED and NOT APPLICABLE remain distinct. NOT TESTED cannot
satisfy a mandatory gate. A documented host limitation is permitted only outside
the declared supported baseline. The current owner-reported cancelled-request
probe remains historical evidence until a later explicit operator finalization;
this design audit does not change its runtime status.

## 9. External contract references

The supported form baseline is the official [MCP 2025-06-18 elicitation
specification](https://modelcontextprotocol.io/specification/2025-06-18/client/elicitation).
Its host-defined interaction model is why No-first cannot attest user presence.
The [2025-11-25 form specification](https://modelcontextprotocol.io/specification/2025-11-25/client/elicitation)
describes additional enum/default forms, but adopting that protocol is not an
implicit RC requirement. Do not mix a newer field contract into an older
negotiated version without explicit compatibility tests.

The [SQLite backup API](https://www.sqlite.org/backup.html) describes coherent
individual database snapshots. It does not establish a transaction over the
controller's separate databases, artifact files and authority files; the
maintenance journal and release tests above address that local coordination
boundary explicitly.
