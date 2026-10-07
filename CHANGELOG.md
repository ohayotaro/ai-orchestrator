# Changelog

## Unreleased — post-release documentation

- Reorganize README EN/JA around installation, a complete calculator walkthrough, first request, approval semantics, support and troubleshooting.
- Record v1.0.0 publication and owner-reported qualification without changing the release tag, package source, approved manifest or published wheel/sdist.
- Separate the public support projection from the complete hash-bound owner archive; do not fabricate private probe records.
- Preserve the previous changelog verbatim in [CHANGELOG_HISTORY.md](CHANGELOG_HISTORY.md). Its candidate/pending wording is historical, not current release status.

These are documentation changes on main, not a new package release. CI distributions built from this tree are not replacements for the already-published 1.0.0 files.

## 1.0.0 — Stable Control Plane — 2026-10-07

**RELEASED / CLOSED.** Available on [GitHub Releases](https://github.com/ohayotaro/ai-orchestrator/releases/tag/v1.0.0) and [PyPI](https://pypi.org/project/ai-orchestrator-kernel/1.0.0/).

Establish the reviewed public-contract inventory, schema-position-aware normalization, complete CLI contract coverage, MCP result/error contracts and Provider SDK extension boundary. Retain independent Start / Execution / Acceptance, explicit trust, isolated writable execution, conservative recovery, durable request identity, historical evidence and unknown-usage semantics. Keep runtime/gate/jobs SQLite writers at 3/1/2 and promised legacy readers.

CI #330 (run 37431299160) covered six dependency/platform lanes. The owner reported 16 valid live probe records across two final-artifact campaigns, qualification-only READY, scoped owner approval and normal-checker READY. Publication used the same qualified artifacts without rebuild/repack. The exact tested deployment and assurance limits are in [support](docs/SUPPORT.md) and [verification](docs/V1_VERIFICATION.md).

| Identity | Value |
| --- | --- |
| Tag | annotated v1.0.0 |
| Commit | `a566c5c22be28b942a4c8256ae1bdf56d6182f41` |
| Tree | `56fabb526b55e40e627b39af69d0cae77e0a301f` |
| License | Apache-2.0 |
| Canonical public record | GitHub Release; identical wheel/sdist on PyPI |

Complete SHA-256 values, approval scope and evidence provenance: [release record](docs/releases/v1.0.0.json).

### Known follow-ups, not changes to this release

The published license metadata embeds the Apache license text rather than a License-Expression field. Some frozen help/documentation strings retain alpha/candidate wording. Modernizing metadata, adopting Trusted Publishing and correcting packaged prose belong to a separately versioned release; see [roadmap](ROADMAP.md). The historical host anomaly's cause remains unknown; final-campaign non-reproduction is not a claimed fix.

## Earlier versions

See the [verbatim pre-publication changelog](CHANGELOG_HISTORY.md) for v0.1–v0.17 and the original v1.0.0 candidate entry. [E2E history](docs/E2E.md) retains the earlier owner-run evidence; [v1.0 E2E](docs/E2E_V1.md) records final qualification separately.
