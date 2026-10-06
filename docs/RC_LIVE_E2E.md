# v0.17 live qualification procedure — 0.17.0 full run complete; 0.17.1 targeted recheck pending

Implementation/CI success does not satisfy the live release gate. Execute only on
an explicitly selected disposable fixture or on a specifically authorized small
change; never restore/cleanup the original project to manufacture evidence.
Record exact build digest and host/provider CLI versions. Do not change a profile,
permission policy or host approval mechanism to hide a failed case.

## Required positive baseline

The required combination is Claude Code host, Claude reasoning/review and Codex
implementation on the supported local deployment. Runtime model/effort choices
are the user's existing explicit configuration, not a kernel recommendation.
At the same final build, perform each of the following twice on fresh IDs:

1. A small Fresh-Write task absent from the fixture, through independent Start,
   Execution and Acceptance forms, isolated write set, measured deterministic
   validation, fresh review and final succeeded state. Exploration may precede
   the explicit task proposal; it never grants authority. Preserve dirty unrelated
   files and compare all before/after control and historical evidence.
2. A genuine Start refusal. Verify the displayed No-first enum; deliberately
   choose No. Confirm no TaskState, implementation, automatic retry or replay is
   produced. Also exercise cancel/untouched/malformed/stale/expired form behavior
   as appropriate. A missing decision is never converted to Yes. Do not infer
   host focus/default behavior from enum ordering alone.
3. A new idle task for cancellation. Record cancellation once and repeat it;
   verify one request event, visible requested/nonterminal state and refused
   execution/provider-permission/acceptance authority. Inspect the finalization
   scope. The owner then runs `cancel --finalize` in a separate normal terminal,
   not the host agent shell. Verify terminal cancelled, revoked approvals/grants,
   preserved usage/files/history and no new provider/validator calls. Repeat
   finalization to prove a no-op. Queued/pending/ambiguous blockers must refuse.

The host must not answer its own forms, turn chat text into approval, unset
CLAUDECODE/internal-worker markers, use provider-change binding cleanup for
cancellation, or call run just to consume a cancellation request.

## Operational scratch and installation checks

Before upgrading, preserve a verified full pre-v0.17 backup and the worktree/Git
state separately, then stop old controllers/workers. Verify runtime DB3, gates1,
jobs2, historical rows/hashes and matching CLI/MCP/worker/Skill identities. An
unchanged profile needs no new trust grant. A package-only downgrade is unsafe.

On scratch copies only, exercise: conflicting shared metadata; recursive accepted
learning and removed-current-context frozen roots; a genuinely orphan candidate;
a fresh non-stale proposal inspecting and crossing an explicit Start after
cleanup; same-ID/different-argument retries after retirement; overlapping receipt
restore and conflicting receipt refusal; incomplete maintenance inspection,
blocked startup and exact reconciliation/recovery. Keep SIGKILL tests isolated
from live providers and unrelated processes. The repository's subprocess fault
suite supplies reproducible deterministic crash cases.

Record actual selected host responses, gate IDs, exact source revisions, scopes,
validated file/row hashes, usage coverage, measured pytest results and requested
versus effective roles/runtime options. Known cost subtotal is not complete cost
when a provider omits telemetry. Do not treat absence of a hook as proof that a
human personally clicked.

## Evidence and closure

Use `docs/support-matrix.json` as the versioned evidence index. Keep host transport
and provider-role execution separate. Fill exact versions, OS/Python, build,
protocol/capabilities, native permission assumptions, timestamps and both run IDs.
Classify unsupported or untested combinations honestly. Historical v0.16 PASS
cannot be copied into a v0.17 `supported` result.

Report PASS / FAIL / NOT TESTED / NOT APPLICABLE independently. A required NOT
TESTED does not close a gate. A newly discovered authority, data-loss, replay,
migration or recovery defect returns to correctness work; documenting it is not
a waiver. Do not mark v0.17 live-closed, create a v1.0 tag or publish a package
until the separate release decision is explicitly made.


## 0.17.1 targeted closure recheck

The 0.17.0 owner run completed the full required matrix above. A single
prepare-time cancellation inconsistency was then found in
`request_provider_permission`: the form could be prepared for a task whose
cancellation request was already durable, although resolve/apply failed closed.
0.17.1 rejects that request before creating the gate.

After installing the final 0.17.1 build, create one fresh idle task, record
cancellation, and request the provider-permission gate through the normal MCP
surface. Expected result: immediate structured refusal containing
`task has a cancellation request`, zero new HumanGate rows/forms, zero provider
calls, zero validator calls and no file/authority mutation. Also re-check package
/ loaded-build / host-Skill identity. If this targeted case passes and final-head
CI remains green, the full 0.17.0 qualification may be combined with this
0.17.1 follow-up to close the v0.17 milestone. Do not copy the 0.17.0 matrix
entry to 0.17.1 without this evidence.
