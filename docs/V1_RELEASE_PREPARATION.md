# v1 release preparation and evidence procedure

Status: **1.0.0 final-candidate metadata frozen; live qualification and publication pending**.
The working version is **1.0.0**. The candidate package metadata and distribution
terms are fixed before final CI/live qualification. No supported v1 live baseline,
tag or publication is asserted merely by preparing these bytes. The owner has selected Apache-2.0 and the publication channels below.
The design's stages B–D can be implemented together; stage E is the final live
qualification and stage F is an independent owner release decision.

## Owner distribution decision

The owner decision recorded on **2026-10-06 JST** is:

- **License:** Apache License 2.0.
- **Canonical release record:** GitHub Releases.
- **Package distribution:** PyPI, using the exact wheel/sdist bytes already qualified and attached/referenced by the canonical GitHub release.
- **No rebuild after qualification:** PyPI must receive the same verified artifacts; a rebuild, metadata edit or repack requires applicable requalification.
- **Publication remains gated:** selecting terms/channels is not permission to tag or publish. Stage F still requires an explicit owner approval bound to the final release manifest digest.

## One implementation batch; one final-artifact live campaign

V1-01 through V1-05 need not each interrupt the owner for another full real-host
E2E campaign. Run focused regression, mutation, schema/wire, storage/crash and
installation tests during implementation. After applicable CI is green, finalize
package metadata and build the candidate once. Then qualify those exact bytes.
Normal positive write, genuine Start refusal and idle cancel/finalize each still
require **two fresh fixture IDs**, in addition to the complete host-form and
cancelled-provider-permission checks. "One campaign" does not mean one test.

The 0.17.2 batch provided the checking and evidence tools. The 1.0.0 candidate
freezes the package/version/license/documentation bytes that will be qualified.
Passing automated tests still do not complete V1-04's owner-live support claim or
V1-05's final release record. Any packaged change after qualification changes
identity and requires applicable requalification.

## Build once and retain evidence

The CI `build-distribution` job creates one wheel and sdist, records exact commit,
tree, kernel build, inventory/canonicalizer, Skill and distribution SHA-256, and
uploads `qualified-distributions`. The six existing lanes remain: Linux Python
3.11/3.12/3.13 reference, macOS Python 3.13 reference, and Linux Python 3.11 minimum
and core-only minimum. All four reference lanes install the same primary wheel
outside the checkout, export/check Skill, smoke CLI/worker/imports and compare
package payloads with a wheel rebuilt from the same sdist. The rebuilt wheel is
not a replacement release artifact.

Reference and combined-minimum lanes run independent MCP SDK tests with no
skips. Only the explicitly core-only lane excludes the SDK interoperability file
and the named SDK-dependent wire test. Record full resolved dependency versions,
actual OS/Python and JUnit testcase counts. Installation `>=3.11` is not evidence
for every newer interpreter.

`tools/collect_release_evidence.py build` produces `artifact-identity.json`.
Its `lane` subcommand records measured evidence as **in_progress/pending**:
a job cannot truthfully attest its own later completion. After the whole run has
completed, save the actual GitHub run and all paginated job results together as
`{"run": <run object>, "jobs": {"jobs": [<all job objects>]}}`. The `complete`
subcommand requires completed-success run, build and matching lane jobs, the
exact CI head and run ID before writing a separate completed lane receipt:

```bash
python tools/collect_release_evidence.py complete \
  --lane-file evidence/ci/linux-3.13-reference/measured.json \
  --completion evidence/ci-completion.json --evidence-root evidence \
  --output evidence/ci/linux-3.13-reference/completed.json
```

Keep the run's source identity distinct from a later evidence-document commit.
A synthetic merge commit may differ while its exact source tree and artifacts
match; a changed tree/build is not equivalent. These records are offline
consistency checks of supplied CI evidence, not cryptographic authentication of
who created the JSON files.

CI artifacts are retained for 90 days as working evidence, not forever. Before
release, copy all distribution, CI, dependency, JUnit, live probe, disposition
and documentation bytes to a controlled durable archive. The archive receipt
must identify the complete transitive file set, hashes, exact artifact, location
and release-lifetime retention. Verify access to that archive separately; the
checker cannot establish remote availability from a local receipt.

## Support matrix and live records

The current matrix uses schema **2**, separating `host.transport` from each
provider role's `execution` status and binding probes to the exact deployment
configuration and artifact. Historical v0.17 conditional/unverified records are
retained byte-for-byte in [support-matrix-v017.json](support-matrix-v017.json).
The new matrix initially has **no qualified deployment**. It does not upgrade
historical PASS to a final-v1 result.

Use `ArtifactIdentity`, `Deployment` and `ProbeRecord` schemas in
`ai_orchestrator.release_evidence` when preparing operator evidence. This is an
offline release-tool data contract, not a new MCP operation or runtime authority.
`adapter_default` records an unresolved choice, not a measured model identity.
Host/CLI versions, explicit model/effort, OS/Python, checked Skill and native
permission assumptions all participate in configuration identity.

The required baseline remains Claude Code host, Claude reasoning/planning/review
and Codex implementation. Claude Code 2.1.284 cannot silently omit the known
intent/wire anomaly. Promotion requires a configuration-bound disposition and
supporting evidence, or a different exact host version qualified independently.
A timeout does not establish fault attribution. Never use hidden form answers,
CLI fallback, broader permissions or automatic paid retry to manufacture PASS.

## Manifest and release decision

A release manifest points to the exact wheel/sdist, matrix, six completed lane
receipts and release/upgrade/rollback documentation. Every file reference has a
normalized relative path and full SHA-256. Symlinks, traversal, duplicates,
metadata conflicts, nonfinite JSON, unknown/coerced versions, partial results,
stale identities or insufficient evidence fail closed. JUnit summary counters
must agree with individual testcase failure/skip entries.

```bash
python tools/check_release.py evidence/release-manifest.json \
  --evidence-root evidence --qualification-only
python tools/check_release.py evidence/release-manifest.json \
  --evidence-root evidence
```

The first form omits only the publication decision, not any technical gate.
The second also requires the owner's actor, distribution terms, channel and
approval bound to the entire manifest payload digest. A change to evidence
invalidates that decision. Neither command publishes, probes a provider, opens
a runtime DB, trusts a profile or changes authority. Synthetic tests of `READY`
are not actual owner live qualification.

Before preparing the final candidate, verify the recorded Apache-2.0 / GitHub Releases + PyPI decision, align English/Japanese release/version/installation metadata, review
upgrade/rollback guidance, and freeze all package bytes. Prepare 1.0.0 without
publishing it, complete final CI and live qualification, approve externally,
and publish the already-verified bytes. Do not rebuild after approval.
