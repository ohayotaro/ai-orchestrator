# v1 release procedure and post-release status

Status: **v1.0.0 RELEASED / CLOSED — 2026-10-07**. [Verification](V1_VERIFICATION.md) · [Exact release record](releases/v1.0.0.json) · [Live results](E2E_V1.md).

This document was updated after publication. It is not the frozen document referenced by the approved release manifest. The [v1.0.0-tagged procedure](https://github.com/ohayotaro/ai-orchestrator/blob/v1.0.0/docs/V1_RELEASE_PREPARATION.md) remains unchanged with the published source. Never replace a manifest reference with a newer main-branch document and claim the old approval still applies.

## Completed release

The owner selected Apache-2.0, GitHub Releases as the canonical public record, and PyPI for the identical qualified wheel/sdist. Preparation was followed by build-once CI #330, the main owner-live campaign, two follow-up probes, controlled evidence assembly, qualification-only READY, explicit manifest-bound approval, normal-checker READY, and publication without rebuild/repack. The approval scope is `74411890270252c2cddc5bfd32a7c7615b0296334c6b999f357b1f6ac1d93d6f`.

The public support index is a projection; full evidence stays in the owner's controlled archive. The post-release documentation task does not recreate that archive, change the approved manifest, or claim a new READY run. [Evidence boundaries](SUPPORT.md#public-index-versus-the-approved-evidence-bundle).

## Procedure retained for subsequent release work

Finalize package metadata before qualification. Build the primary wheel/sdist once, record full source commit/tree, kernel build, canonical inventory and Skill identities, and test the same primary artifacts. A rebuilt wheel used for sdist payload comparison is not a replacement release file. All six dependency/platform lanes and their explicit SDK scope remain required unless a reviewed release design changes them.

A running job may record measurements, but cannot certify its own eventual completion. Save actual completed GitHub run/job responses including all pages, then use the existing `tools/collect_release_evidence.py complete` tooling to create completed receipts tied to the exact run/head/artifacts. Do not relabel queued, failing or skipped checks as success.

Keep host-transport and provider-role support separate. Record exact environment/permissions and model/effort modes. New final-artifact live evidence must not be synthesized from old results. Review historical anomalies without claiming that non-reproduction proves a root-cause fix.

Assemble the complete transitive evidence bundle before approval: distributions, matrix, original probe records, anomaly disposition and its references, completed lanes, JUnit, dependencies, completion records, and release/upgrade/rollback documents. Preserve sensitive raw material in controlled storage, not public source. Verify a release-lifetime archive copy and record its full file set. Ninety-day CI retention alone is not durable release custody.

## Check and approve without publishing implicitly

Run the tooling from the intended qualified source/package with the original complete evidence-root:

```bash
python tools/check_release.py evidence/release-manifest.json --evidence-root evidence --qualification-only
```

Qualification-only omits the owner decision, not technical gates. Review the actual evidence and scope, not merely the READY label. The checker is an offline consistency/attestation checker; it cannot authenticate a human click or prove remote archive availability.

The owner decision must bind actor, terms and channels to the emitted approval_scope. Preserve the pending manifest and record approval separately. The decision field is excluded from scope calculation; other bound payload/evidence changes invalidate approval.

```bash
python tools/check_release.py evidence/release-manifest.approved.json --evidence-root evidence
```

Only after the normal check is READY and publication is explicitly authorized may the exact approved files be published. Do not rebuild, repack, move an existing release tag or use ambiguous skip-existing behavior to manufacture success. Verify uploaded file hashes on both channels. Never put tokens in prompts, logs or evidence.

These commands do not publish. A documentation PR or a new CI artifact also does not publish. v1.0.0 has already crossed this process; it must not be rerun with substituted public-summary evidence.

## Follow-ups

The original archive was last reported on one owner Mac; replication and token revocation must not be marked complete without confirmation.

The License-Expression / embedded README / Trusted Publishing work is now scoped as the separate **v1.0.1 documentation/packaging maintenance candidate**. See [V1_0_1_RELEASE.md](V1_0_1_RELEASE.md). It does not retroactively alter v1.0.0 or convert its live evidence into evidence for a different artifact.
