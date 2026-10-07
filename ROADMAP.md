# AI Orchestrator Roadmap

Current record date: **2026-10-07**. **v1.0.0 Stable Control Plane — RELEASED / CLOSED.**

The annotated v1.0.0 tag points to `a566c5c22be28b942a4c8256ae1bdf56d6182f41`. The qualified wheel/sdist were published to GitHub Releases and PyPI without rebuild/repack. This roadmap is a post-release record, not a mutation of the tag or approval scope. [Release identity](docs/releases/v1.0.0.json) · [Verification](docs/V1_VERIFICATION.md).

## Product direction and invariants

Coordinate user-facing AI clients and separately managed workers through explicit, inspectable authority. Ordinary users should not need to design a DAG or name a vendor on every request. Unclear work can remain exploratory until an explicit proposal transition.

Agent intent is not human authorization. Learning and exploration accumulate understanding, not permissions. Persistent provider/plugin, workflow, validator, policy and accepted-context changes require explicit governance/trust. Writable concurrency is isolated; uncertain effects are not automatically replayed. Unknown usage is not zero, and reading does not rewrite history. This remains trusted-local POSIX software, not cryptographic human-presence or hostile-same-user isolation.

## Completed milestones

| Milestone | Established capability |
| --- | --- |
| v0.1–v0.4 | Durable tasks/intakes/jobs and single-terminal HumanGates |
| v0.5–v0.9 | Capability/provider resolution, workflow DAGs, isolated parallel writes, adaptive orchestration, provider-local model/effort selection |
| v0.10–v0.12 | Usage/budgets, conservative recovery, persistence and migration compatibility |
| v0.13–v0.15 | Provider SDK, governed Project Learning, operational backup/restore/retention |
| v0.16 | Durable non-authoritative exploration and explicit proposal transition |
| v0.17 | RC hardening; formal combined 0.17.0/0.17.1 owner-live closure |
| v1.0.0 | Stable Control Plane; final-artifact qualification, scoped owner approval and publication |

The [finalized design](docs/V1_STABLE_CONTROL_PLANE.md) and [audit](docs/V1_DESIGN_AUDIT.md) retain the original decisions. V1-01 inventory, V1-02 public surfaces and V1-03 compatibility were implemented in the preparation cycle. V1-04 support and V1-05 release proof were completed through the final-artifact campaigns and owner release decision. Public summaries are distinct from the full controlled evidence bundle.

## Post-release documentation — current work

Rebuild README EN/JA around first use; clarify Execution versus Acceptance, setup versus normal single-terminal operation, host versus provider support, digest types and troubleshooting. Record published identities and preserve historical records. Do not modify runtime source, license metadata, Skill/contracts, the v1.0.0 tag or released files as part of this work.

## Next packaging and release-maintenance candidate — proposed, not released

| Work item | Exit condition |
| --- | --- |
| License metadata | Emit `License-Expression: Apache-2.0`, include LICENSE correctly, review the build-backend floor and verify wheel/sdist metadata. Never replace v1.0.0 bytes. |
| Packaged wording | Align residual alpha/candidate/help wording with the released contract while preserving historical audit statements. Version and qualify any new package. |
| Trusted Publishing | Review a dedicated release workflow and owner-configured publisher/environment protections. Upload only approved exact artifacts; do not grant publishing authority through ordinary CI. |
| Evidence durability | Replicate the owner-controlled archive to another medium/host, verify hashes, and define a privacy-reviewed public evidence subset. No claim that the second copy already exists. |
| Onboarding regression | Keep EN/JA shell steps aligned and smoke-test init, validator registration, trust and local validation separately from provider-live qualification. |

Potential packaging references: [PyPA pyproject metadata](https://packaging.python.org/en/latest/guides/writing-pyproject-toml/#license-and-license-files) and [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/). These are follow-up plans, not changes already implemented or authorization to publish another version.

## Deferred product work

Cancellation-request UX in the conversational client and safer form interaction deserve a separately scoped design. v1.0 retains CLI task cancellation and operator-only finalization; No-first is not a mis-click guarantee. Additional hosts/CLI versions/models need their own support evidence. New execution authority, fallback, learning promotion or external effects are not implied by the roadmap.

No release date or next version number is promised here. Review safety, API/persistence compatibility and applicable tests before expanding scope.

## Historical continuity

[ROADMAP_V1_PRE_RELEASE.md](ROADMAP_V1_PRE_RELEASE.md) preserves the exact roadmap from the v1.0.0 source tree, including earlier pending-status language. [ROADMAP_HISTORY.md](ROADMAP_HISTORY.md) preserves the older pre-audit roadmap. Neither historical status overrides this release record. Earlier E2E evidence remains in [docs/E2E.md](docs/E2E.md); final-v1 evidence is summarized in [docs/E2E_V1.md](docs/E2E_V1.md).
