# v1.0.0 final-artifact owner-live E2E

**Owner-reported qualification closed on 2026-10-07; publication completed the same day.** This is a public summary of the reports and approved release, not newly executed probes or a substitute for raw evidence. [Artifact identity](releases/v1.0.0.json) · [Verification](V1_VERIFICATION.md) · [Support](SUPPORT.md).

## Campaign separation

The first campaign began in a new calculator fixture and was reported on 2026-10-06. Its accepted changes were subtract and multiply. A second, independent fresh fixture supplied only Execution cancel and actual stale-response on 2026-10-07. Both used the exact published 1.0.0 wheel/build and the same host/provider versions. The owner subsequently checked that the two fixture configurations differed only by project name.

Reported original task IDs are retained below. Gate IDs shown with an ellipsis are only observed prefixes, not complete identifiers. Full IDs and observation windows remain in the controlled archive; no prefixes are expanded here.

## Accepted positive and refusal cases

| Case | Observed result |
| --- | --- |
| `v1q-A1-subtract`, intake `I-cf86c05110ea` | Three independent affirmative gates, permitted two-file write set, measured 3 passed, fresh review approved, succeeded; four provider calls |
| `v1q-A2-multiply`, intake `I-61645bc3cfa8` | Three independent gates, permitted two-file write set, measured 5 passed, fresh review approved, succeeded; four provider calls |
| Start refusal B2, intake `I-4b19c5dbe110` | Explicit No; no task registration or subsequent provider/validator/file effect |
| Start refusal B1R, intake `I-8d1fde7b707b` | Explicit No on the valid retry; declined without applying, no extra authority/effects |
| C2 `v1q-C2-absolute-cancel` | Durable repeated cancel produced one request; Execution/permission/Acceptance refused before forms; exact-scope operator finalization cancelled the task; repeated finalize was a no-op |
| C3 `v1q-C3-square-cancel` | Same idle-finalization properties on a fresh task; history, usage and files preserved |
| Cancelled permission prepare C2/C3 | Refused before form/gate/grant, with unchanged provider, validator and file counts |

The first campaign observed three inactive learning candidates after acceptance. They were not promoted and did not change trust. Baseline validation during fixture setup is distinct from campaign validators.

## Actual-host boundary coverage

| Kind | Valid PASS records / required | Scope and limits |
| --- | --- | --- |
| fresh_write | 2 / 2 | Full accepted flows above |
| start_refusal | 2 / 2 | Valid explicit-No cases only |
| cancel_finalize | 2 / 2 | Idle operator finalization, not remote-effect cancellation proof |
| cancelled_provider_permission_prepare | 2 / 1 | Zero new forms/rows/authority/effects |
| explicit_yes | 1 / 1 | Genuine affirmative form from a positive flow |
| explicit_no | 1 / 1 | Genuine No path |
| cancel | 2 / 1 | Start cancel and follow-up Execution cancel |
| untouched_submission | 1 / 1 | Host prevented unselected submission; Esc returned cancel. No live malformed-content injection |
| timeout | 1 / 1 | No reply within about 120 seconds, expired without effects; observed timeout, not a timed affirmative replay |
| duplicate_response | 1 / 1 | Same request_id resent; existing declined outcome reused. Not a recorded duplicate host-wire response |
| stale_response | 1 / 1 | Form already displayed, cancellation drift, actual reply, response-time rejection |

Total: **16 owner-reported PASS records**. These records are not 16 independent full end-to-end tasks; some classifications reference different aspects of an already observed form path. Negative deltas refer to their measured windows, excluding disclosed proposal/planning setup calls.

## Follow-up 1: Execution cancel

Task `final-probe1-exec-cancel-task-001`, intake `I-317eccdbc12e`. Start `G-10f446b4…` applied and planning completed. Execution `G-5848e511…` received action=cancel, content absent, and moved pending → cancelled without applying. No new implementation job, Codex call, validator, Acceptance gate, approval, grant, replay or project file change. The task remained awaiting_approval as intended; it was not finalized to make the fixture appear clean.

## Follow-up 2: real stale response

Task `final-probe2-stale-task-001`, intake `I-0d1eb093d473`. Execution form `G-055876d2…` was sent after Start/planning. At +13.2 seconds the operator issued ordinary task cancellation without finalize in another terminal. At +28.8 seconds the old form returned action=accept. The resolver revalidated scope, observed the durable cancellation request and moved pending → stale with `task has a cancellation request`.

This was not pre-submit staleness or a timeout. The gate never applied; approvals stayed zero, grants stayed empty, and no provider/validator/file effect occurred in the response window. Diagnostics do not retain the content body. Decision=yes was inferred from the frozen resolver's affirmative-only path to this stale outcome, not asserted as captured raw content.

## Excluded attempts and retained effects

B1's accidental Yes was not Start-refusal evidence. C1's accidental Execution Yes dispatched Codex and integrated negate; it remained awaiting_acceptance. E's reply before its timeout was legitimately applied, not stale-response evidence. These attempts remain in history and supporting notes; successful replacements did not erase them.

Execution authorizes writing and integration before Acceptance. Acceptance records acceptance of the reviewed result; it is not a deferred first-write barrier. Task cancellation/finalization does not automatically undo integrated files. C1 was not accepted merely to tidy the test. The original fixture retained three unfinished tasks and the follow-up retained two. Those retained states do not mean the negative probes dispatched unexpectedly, and these fixtures must not be reused as clean preflight baselines.

C2 recorded actor `ohayotaro~` as reported, while C3 recorded `ohayotaro`. The apparent operator-input typo is retained rather than silently corrected. These are local audit labels, not verified identity attestations.

## Usage and assurance

First campaign: 22 provider calls, three campaign validations, known Claude cost subtotal $1.33488460. Codex cost and provider elapsed were unsupported, so complete total cost remained unknown. Follow-up proposal/planning setup used two calls per task; neither negative response window added calls. This summary does not fabricate a combined final cost.

The historical Claude Code 2.1.284 anomaly was not reproduced as a product-side mismatch in the final campaign. Its cause remains unknown. The owner approved a configuration-bound disposition retaining that limitation. No-first ordering and absent auto-answer hooks do not establish cryptographic human presence.

Reports received: main campaign 2026-10-06T08:45:13Z; follow-up 2026-10-07T02:17:03Z; evidence assembly 2026-10-07T04:29:38Z. Raw snapshots, extracted transcript segments, calculation scripts and 16 ProbeRecords remain in the controlled archive, not this public Markdown. Earlier [E2E history](E2E.md) is unchanged.
