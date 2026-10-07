# v1 final-artifact live qualification — closed

**v1.0.0 owner-live qualification closed on 2026-10-07; release publication is complete.** Results are in [E2E_V1.md](E2E_V1.md), [V1_VERIFICATION.md](V1_VERIFICATION.md) and the [public release record](releases/v1.0.0.json).

The [procedure frozen at v1.0.0](https://github.com/ohayotaro/ai-orchestrator/blob/v1.0.0/docs/V1_LIVE_E2E.md) and the underlying [RC procedure](RC_LIVE_E2E.md) remain historical inputs. This newer status page does not replace files referenced by the approved manifest.

The main campaign passed Fresh-Write twice, genuine Start refusal twice, idle cancel/finalize twice, and cancelled provider-permission prepare refusal. Two incomplete actual-host cases were closed on a new fixture: Execution cancel and response-time staleness after operator cancellation. The owner assembled 16 valid PASS records. Operator-error attempts and historical anomalies were retained, not erased or counted as successful negative probes.

## Reuse boundaries

Do not rerun paid probes merely to update documentation. Requalification of a changed package/configuration must be scoped explicitly; old PASS results cannot be relabeled as observations on new artifacts. The original fixtures contain intentionally retained nonterminal tasks and controller evidence. They are not clean fixtures for another preflight and must not be cleaned up to manufacture a result.

For any future authorized campaign, use exact artifact/Skill/environment identities, a fresh disposable Git project, separate operator setup/trust, and read-only preflight. New jobs/gates databases may be absent initially; require the expected writer versions when they exist. Preserve before/after windows, setup calls, exact file/row evidence, actual host outcomes and remaining unknown usage. Human answers remain manual; no hooks, injected internal responses, broader permissions or CLI approval fallback.

Execution can integrate root changes before Acceptance; declining acceptance or finalizing cancellation does not roll them back. An accidental Yes is actual authorization, not negative evidence. Stop that probe and preserve its effects; a new paid attempt requires explicit owner intent.

The current public matrix is an index, not the private ProbeRecord bundle. Use the controlled original evidence to reproduce release qualification, and retain the [coverage limits](SUPPORT.md#what-the-observed-probes-establish), including request-id duplicate scope and inferred stale affirmative content.
