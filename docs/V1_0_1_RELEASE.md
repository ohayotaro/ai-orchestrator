# v1.0.1 — Documentation / Packaging Maintenance

Status: **CANDIDATE — not tagged or published by this document.**

v1.0.1 exists to publish the current onboarding README to PyPI and modernize packaging metadata without expanding the v1 Stable Control Plane. The live-supported baseline remains the deployment qualified for v1.0.0 unless separate new live evidence is collected.

## Allowed package changes

- version: 1.0.0 -> 1.0.1
- embedded README / long description
- PEP 639 metadata: `License-Expression: Apache-2.0` and packaged `LICENSE`
- build-backend floor required for PEP 639
- release/Trusted Publishing workflow and maintenance documentation/tests
- generated contract inventory package-version field

No controller authority, workflow/provider behavior, HumanGate semantics, persistence schemas, SDK semantics, Skill content or runtime limits may change in this patch.

`tools/check_v101_maintenance.py` compares `src/ai_orchestrator` with annotated tag `v1.0.0`. After normalizing only `__version__` and the contract inventory's `package_version`, every runtime package byte must match.

## Qualification

Before owner approval:

1. Build wheel/sdist once from the candidate.
2. Run the existing six CI lanes with zero failures/errors/skips in their defined scopes.
3. Pass contract generation/checks.
4. Pass the v1.0.1 maintenance source-equivalence check against `v1.0.0`.
5. Inspect wheel and sdist metadata: Version 1.0.1, `License-Expression: Apache-2.0`, explicit `License-File`, no legacy long-text `License`, and the reorganized README as long description.
6. Install/smoke the exact primary wheel outside the checkout.
7. Record exact source tree, build identity, Skill/contracts and distribution SHA-256.

A new paid owner-live E2E campaign is not required merely to change documentation/packaging when the equivalence check proves runtime behavior bytes unchanged. Conversely, v1.0.0 ProbeRecords must not be relabeled as v1.0.1 final-artifact live probes.

## Publication

Publication remains an explicit owner decision after candidate evidence is reviewed.

GitHub Releases remains the canonical release record. Attach the exact qualified wheel/sdist plus identity/approval evidence. PyPI must receive those same wheel/sdist bytes.

`.github/workflows/publish-pypi.yml` is intentionally a publish-only workflow: it downloads an already-created approved GitHub Release, verifies the artifact identity and owner-approved manifest, stages only the exact wheel/sdist, and uses PyPI OIDC Trusted Publishing. It never builds.

Before first use, configure PyPI Trusted Publishing for:

- owner/repository: `ohayotaro/ai-orchestrator`
- workflow: `publish-pypi.yml`
- GitHub environment: `pypi`

Protect the `pypi` environment as appropriate. Do not store a long-lived PyPI token in repository secrets merely to make this workflow work.

If publication succeeds, verify PyPI filenames and SHA-256 against the GitHub Release and then record the release in a separate post-release commit.
