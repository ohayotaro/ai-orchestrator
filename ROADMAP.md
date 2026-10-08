# AI Orchestrator Roadmap

Current record date: **2026-10-08**. **v1.0.0 Stable Control Plane — RELEASED / CLOSED.**

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

## v1.0.1 documentation / packaging maintenance — current candidate

The next patch is **v1.0.1**, limited to packaging and documentation maintenance. It packages the reorganized README, migrates to SPDX/PEP 639 license metadata, and introduces a Trusted Publishing path that uploads exact approved GitHub Release assets without rebuilding them.

Runtime control-plane behavior and public contract semantics must remain unchanged from v1.0.0. CI must mechanically compare the package source against the v1.0.0 tag and permit only version identity changes under `src/ai_orchestrator`: `__init__.py` and the package-version field in `assets/contracts.json`. The six existing CI lanes still run. v1.0.0 owner-live evidence remains historical evidence for that artifact; it must not be relabeled as live evidence for 1.0.1.

See [the v1.0.1 maintenance release plan](docs/V1_0_1_RELEASE.md).

## Proposed v1.1.0 — Devin CLI Integration

Requested on 2026-10-08. This is a separate feature line, not an extension of the frozen v1.0.1 maintenance scope. Implementation and owner-live qualification are pending; no Devin deployment is supported by this proposal alone.

Start with **Devin CLI as host**, keeping Claude reasoning/planning/review and Codex implementation unchanged. Verify the actual MCP form exchange, not merely tool discovery or Skill loading. Then add **Devin as a provider** through the existing exact-pinned, explicitly trusted Provider SDK, enabling roles only after their output/permission/cancellation contracts are demonstrated. Qualify the combined host/provider configuration last.

| Step | Exit condition |
| --- | --- |
| DV-01 | Identify the official installed CLI and capture exact version/help/contract evidence; no delegated provider execution. |
| DV-02 | Devin-host read-only preflight, then separately authorized real HumanGate boundary tests on a dedicated fixture. |
| DV-03 | Opt-in Devin provider plugin; validated final results, native permission/trust handling, no recursive orchestration or implicit cloud handoff. |
| DV-04 | Fake-CLI/contract/regression tests, then targeted owner-live verification of each changed axis on fixed artifacts. |
| DV-05 | Version/configuration-bound support and reviewed release evidence, preserving historical v1.0.0/v1.0.1 identities. |

See [Devin CLI design and unresolved contracts](docs/DEVIN_CLI.md) and the [read-only preflight prompt](docs/DEVIN_CLI_PREFLIGHT_ja.md). Existing MCP/SDK extension points are preferred; no new approval authority or weaker gate is implied. The proposed kernel version is not required for a separately versioned provider plugin or a configuration-only host probe.

## Post-release documentation — completed

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

## Devin CLI integration — observed preflight and next work

The independently scoped draft [Devin integration design](docs/DEVIN_CLI.md) targets
a future feature release, not the frozen v1.0.1 documentation/packaging artifact.
Operator-reported read-only inspection on 2026-10-08 confirmed
`devin 3000.11.3` stdio MCP + `inspect_project` with protocol `2025-06-18`,
but **no advertised form elicitation** (`form_supported=false`). Host
Start/Execution/Acceptance interaction was NOT TESTED, not a PASS; the exact
Devin host is therefore unsupported for single-terminal HumanGates.

Proceed separately with DV-04: a pinned external Provider SDK v1/API v2
Devin adapter, initially restricted to implementation under the already
qualified Claude Code host. Require independent non-billable protocol/scope/
cancellation/refusal tests before any owner-live provider call. Unsupported
native permission, output or trust boundaries fail closed; no implicit
fallback, bypass, cloud handoff, or recursion. Preserve package and supported
matrix for the frozen v1.0.1 release.

## Deferred product work

Cancellation-request UX in the conversational client and safer form interaction deserve a separately scoped design. v1.0 retains CLI task cancellation and operator-only finalization; No-first is not a mis-click guarantee. Additional hosts/CLI versions/models need their own support evidence. New execution authority, fallback, learning promotion or external effects are not implied by the roadmap.

No release date is promised here. v1.1.0 is a proposed feature-line label, not a version bump or publication decision. Review safety, API/persistence compatibility and applicable tests before expanding scope.

## Historical continuity

[ROADMAP_V1_PRE_RELEASE.md](ROADMAP_V1_PRE_RELEASE.md) preserves the exact roadmap from the v1.0.0 source tree, including earlier pending-status language. [ROADMAP_HISTORY.md](ROADMAP_HISTORY.md) preserves the older pre-audit roadmap. Neither historical status overrides this release record. Earlier E2E evidence remains in [docs/E2E.md](docs/E2E.md); final-v1 evidence is summarized in [docs/E2E_V1.md](docs/E2E_V1.md).
