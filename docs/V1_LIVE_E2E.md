# v1 final-artifact live qualification

Use this procedure only against the exact **1.0.0 final-candidate** wheel/sdist
produced by the completed build-once CI and identified by full SHA-256 values.
The owner controls real host-form answers and any provider expense. A source or
package mismatch stops qualification; do not substitute an editable build whose
identity cannot be tied to the qualified artifacts.

Read [release preparation](V1_RELEASE_PREPARATION.md) and preserve the detailed
[RC live procedure](RC_LIVE_E2E.md). Do not rerun all live probes after each V1-01
through V1-05 implementation step. Batch automated changes, freeze the artifact,
then execute this final campaign. A subsequent packaged change invalidates
final-artifact qualification and requires applicable requalification.

## Preflight

On a dedicated disposable E2E project, verify the supplied wheel/sdist SHA-256,
full source/build/inventory/Skill identities and the six completed CI lanes.
Record exact host/CLI/OS/Python, negotiated 2025-06-18 form capabilities,
provider roles/model/effort modes and existing explicit native permissions.
Use `orchestrator identity --skill PATH` and provider-free installation checks.
A mismatch stops the campaign; do not update the owner's live runtime implicitly.

Capture before/after project file hashes, task/intake/job/gate/event observations,
approvals/grants, cancellation state, usage and provider/validator-start counters.
The known usage subtotal is not complete cost if telemetry is missing. Preserve
raw evidence in the appropriate controlled location; public reports omit secrets,
raw prompts and unnecessary personal paths without rewriting canonical history.

## Required probes

| Probe | Repetitions | Evidence |
| --- | --- | --- |
| Fresh-Write | 2 distinct fresh IDs | Requested behavior absent beforehand; genuine Start, Execution and Acceptance Yes; new write; measured validators; independent review; succeeded |
| Genuine Start refusal | 2 distinct fresh IDs | Explicit No and No wire response; no resulting authority, dispatch or file change |
| Idle cancellation/finalization | 2 distinct fresh IDs | Durable cancellation; current exact scope; explicit operator finalization; terminal cancelled; no dispatch/write; no extra authority |
| Cancelled provider-permission prepare | 1 fresh ID | Request refused before a gate row/form/grant; zero provider, validator and file changes |
| Untouched / explicit No / cancel / explicit Yes | 1 each | Record actual selected intent and response; untouched/No/cancel never authorize; valid Yes crosses only its bound gate |
| Timeout / stale / duplicate response | 1 each | No new authority or effects; duplicate has no additional row/dispatch; preserve original response separately |

Fresh IDs matter: reusing a completed request or counting automatic retries does
not provide a second fresh run. HumanGate timeout/duplicate behavior needs the
actual qualified host, alongside independent SDK/wire regression evidence.
The cancellation probe distinguishes a recorded request from terminalization
and never claims remote effect cancellation attestation.

An accidental Yes is real authorization, not refusal evidence. Stop the probe;
do not request Execution as cleanup. Paid retries need new explicit user intent.
No hooks, auto-answer scripts, CLI approval fallback, widened permissions or
runtime row surgery are permitted. Corruption, cleanup/restore and interruption
checks use scratch copies, never the original project.

## Result

Record PASS, FAIL, NOT TESTED and NOT APPLICABLE separately from supported,
conditional, known-incompatible and unverified support statuses. All mandatory
probes must pass for one operation- and artifact-scoped supported baseline.
An unresolved Yes-intent/No-wire anomaly is not removed by selecting successful
retries. Keep historical conditional entries intact.

Check the completed manifest using `tools/check_release.py --qualification-only`.
The result only validates supplied evidence consistency; review the actual host
observations and anomaly disposition before promotion. Final publication still
requires a separate, digest-bound owner decision. No probe or checker publishes.
