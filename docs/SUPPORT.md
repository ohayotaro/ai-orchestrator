# v1.0.0 support and evidence boundaries

Status: **RELEASED / CLOSED — 2026-10-07**. This is a post-release public support summary, not a new qualification run.

## Qualified real-host deployment

| Axis | Qualified scope |
| --- | --- |
| Distribution | ai-orchestrator-kernel 1.0.0; exact hashes in [release record](releases/v1.0.0.json) |
| Host transport | Claude Code 2.1.284, MCP 2025-06-18 form elicitation |
| Reasoning / planning / review | Claude CLI 2.1.284 |
| Implementation | Codex CLI 0.160.0 |
| Runtime choices | Model and effort: adapter_default; resolved model names are not attested; no fallback |
| Owner-live environment | macOS 26.6.2 (25G83), arm64; Python 3.13.12 |
| Authority | Trusted-local; separate Start, Execution and Acceptance; explicit setup and operator maintenance |

The approved archive's deployment configuration digest is
`b8c3147fa6b6d976bb6bc6372390ccae6c7fcd2047a431a84c9891e359d17d4d`.
Fixture profile digests differ because the project names differ; they remain historical evidence, not a promise that any other profile is automatically qualified.

## Automated coverage is a different axis

CI run [37431299160](https://github.com/ohayotaro/ai-orchestrator/actions/runs/37431299160) qualified the release source/distributions across Linux Python 3.11/3.12/3.13 reference, macOS Python 3.13 reference, Linux Python 3.11 minimum, and Linux Python 3.11 core-only minimum. These are not six real-host live campaigns. `requires-python >=3.11` is an installation constraint, not proof for every newer interpreter.

## Other hosts and providers

| Combination | v1.0.0 interpretation |
| --- | --- |
| Claude Code host, Claude reasoning/review, Codex implementation | Supported only in the operation/artifact/environment scope above |
| Codex as a host | No final-v1 supported promotion; historical Execution/Acceptance timeouts remain recorded |
| Antigravity as a host | No final-v1 supported promotion; historical advertised-form/cancel behavior remains recorded |
| Antigravity as a provider or external Provider SDK plugins | Existing implementation/extension capability is not a qualified final-v1 deployment |
| Different CLI versions, explicit models/effort, OS or permission assumptions | Require their own evidence before being called the same qualified deployment |

Keep [historical v0.17 classifications](support-matrix-v017.json) intact. Provider execution and host confirmation transport are separate axes. A timeout alone does not assign blame to a component.

## What the observed probes establish

The owner reported 16 PASS records across the main campaign and two follow-up probes. [Live record](E2E_V1.md) distinguishes full flows from negative observation windows. Setup reasoning/planning calls are not hidden by reporting zero calls during a negative window.

Untouched submission was prevented by the host UI, then closed with Esc; malformed missing content was not injected live. Duplicate coverage was an identical request_id retry, not a captured double delivery of the host's response. Stale-response coverage used a displayed Execution form, operator cancellation while it was open, and response-time rejection. Its affirmative decision is inferred from the frozen resolver branch; the diagnostics do not retain the content body.

The historical Claude Code 2.1.284 Yes-intent/No-wire anomaly was retained in the approved, configuration-bound disposition. The final campaign did not reproduce a product-side mismatch; **the historical root cause was not established and no transport fix is claimed**. Operator-confirmed accidental Yes responses were excluded from negative PASS records. Client-mediated assurance and No-first focus limitations remain.

## Public index versus the approved evidence bundle

[docs/support-matrix.json](support-matrix.json) is a schema-v2 **public projection** of the released support claim. It is not a byte-identical copy of the matrix in the approved archive. Its descriptive permission text and public-summary ID must not be used to recompute the approved deployment digest. It deliberately contains no invented ProbeRecords or reconstructed anomaly-disposition file.

The complete matrix, probe records, JUnit files, dependencies, disposition and transitive evidence remain in the owner's controlled release archive. The public [approved manifest](https://github.com/ohayotaro/ai-orchestrator/releases/download/v1.0.0/release-manifest.approved.json), SHA-256 `49589501c5e5efb7bbdfcb7b21ded568b20fe8d10b42f323ae513ce358fc78f1`, is the release-level reference. A clean repository clone plus the four public release assets is **not** the complete evidence-root and cannot independently reproduce the archive's READY check.

Use the original controlled bundle for `tools/check_release.py`; do not substitute the public projection. The post-release edit did not receive the private archive bytes and does not claim to have rerun its checker. See [verification provenance](V1_VERIFICATION.md).
