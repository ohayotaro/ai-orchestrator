# v1.0.0 — verification and publication record

**RELEASED / CLOSED — 2026-10-07.** This post-release summary separates owner-reported live/checker results from checks performed while editing documentation. It does not rerun live qualification or replace the approved evidence bundle.

## Release identity

[Machine-readable public release record](releases/v1.0.0.json) · [GitHub Release](https://github.com/ohayotaro/ai-orchestrator/releases/tag/v1.0.0) · [PyPI](https://pypi.org/project/ai-orchestrator-kernel/1.0.0/).

| Item | Exact value |
| --- | --- |
| Package | ai-orchestrator-kernel 1.0.0 |
| Annotated tag object | `5d3c31b72019c0d9deb8509d2f1d011980c0296e` |
| Tagged source commit | `a566c5c22be28b942a4c8256ae1bdf56d6182f41` |
| CI checkout commit | `cecf86b8ab749150453a6079f6dbe8acd7f67eaa` (PR synthetic merge) |
| Shared source tree | `56fabb526b55e40e627b39af69d0cae77e0a301f` |
| Kernel build | `eb25ca9a5873b0a4ee6fc63159129a5917b6bb741bae9660f14782ba840255e4` |
| Wheel SHA-256 | `18a1b2a4eb73bc1b58b88a8be4953032bb12be3705db43305152c000d819372a` |
| Sdist SHA-256 | `3a5de9f47627a55e956da1a92678d30fc1269e258e4951eecc2d0d23cc9433ad` |

The different CI/tag commit IDs identify different Git commits with the same tested tree; they are not interchangeable labels. A new post-release main tree is also distinct, even if source-code-only build identity stays the same.

## Digest names are not interchangeable

`orchestrator identity.contract_inventory_sha256` hashes packaged `contracts.json` bytes:
`6bc6374b863e2cd775f7fd6188b00088b278ee4bc67205422d0e085d52825e9f`.

`artifact-identity.json.inventory_digest` hashes the inventory's canonical JSON value, using `json-schema-positions-v2` as the recorded schema canonicalizer:
`31988330fc42f783923dd0582b83b303983aa4cc670d1933c8c84d290796bc9d`.

The two values intentionally differ. Neither a package version nor a kernel-source hash alone identifies distribution metadata, external provider binaries or the dependency environment. Skill SHA-256:
`6fd02ef76fb6d5128d2fb571df7d2edf8ae13d6483deff540301ead8729f1f8f`.

## Final CI, not post-release CI

Release CI [#330 / 37431299160](https://github.com/ohayotaro/ai-orchestrator/actions/runs/37431299160) completed successfully, including build-distribution and six lanes. The owner assembled completion receipts from run/job metadata and verified them against measured JUnit and dependency files.

| Lane | Python | Tests |
| --- | --- | --- |
| linux-3.11-reference | 3.11.16 | 766 |
| linux-3.12-reference | 3.12.14 | 766 |
| linux-3.13-reference | 3.13.15 | 766 |
| macos-3.13-reference | 3.13.15 | 766 |
| linux-3.11-minimum | 3.11.16 | 766 |
| linux-3.11-core-minimum | 3.11.16 | 764 |

All failures, errors and skips were zero in the owner-assembled final record. Only the core-only lane excluded the two named SDK cases. The other five lanes ran independent SDK tests. Four reference lanes installed the same primary wheel outside the checkout and compared sdist-rebuilt payloads; minimum build checks are not relabeled as reference installation checks.

## Final owner-live qualification

The owner reported the main campaign on 2026-10-06 and two follow-up probes on 2026-10-07. Together they produced 16 valid PASS records. The main campaign's incomplete Execution-cancel/stale-response cases were not counted as PASS until the new fixture follow-up. [E2E summary and exact coverage limits](E2E_V1.md).

The released supported deployment is Claude Code 2.1.284, Claude reasoning/planning/review, Codex 0.160.0 implementation, MCP 2025-06-18, macOS 26.6.2 arm64, Python 3.13.12, adapter-default model/effort. The approved configuration digest is `b8c3147fa6b6d976bb6bc6372390ccae6c7fcd2047a431a84c9891e359d17d4d`.

The historical host anomaly remains recorded. Its final-configuration disposition uses the successful final campaign, with unknown historical root cause and client-mediated assurance expressly retained. This is not a claim of a newly fixed host defect.

## Owner decision and publication

The owner reported qualification-only READY, followed by a separate approved manifest and normal-checker READY in both the working evidence-root and durable archive. Approval scope:
`74411890270252c2cddc5bfd32a7c7615b0296334c6b999f357b1f6ac1d93d6f`.

Actor: `ohayotaro`. Terms: Apache-2.0. Channels: GitHub Releases + PyPI. The pending manifest was retained. The approved manifest's file SHA-256 is `49589501c5e5efb7bbdfcb7b21ded568b20fe8d10b42f323ae513ce358fc78f1`; it is not the same kind of digest as approval_scope. The decision section is excluded from scope calculation; changing referenced evidence or other bound payload invalidates the existing approval.

GitHub Release publication: 2026-10-07 04:54:29 UTC (13:54:29 JST). Owner-reported PyPI uploads: wheel at 05:18:32 UTC, sdist at 05:18:34 UTC. The owner compared both services' digests and downloaded bytes with the qualified artifacts; no rebuild/repack occurred. The post-release documentation work re-read GitHub release metadata/asset digests and inspected the retained CI distribution/source archives. It did not independently redownload PyPI files or rerun the private manifest checker.

## Evidence custody and historical records

The full archive is owner-controlled and was last reported as 78 files / approximately 5.6 MB before the later decision/publication additions, read-only at file level and retained outside temporary directories. A second-machine copy has not been reported. Local file permissions do not establish immutable or redundant archival storage.

This repository provides a public projection, not the private archive. Full gate IDs, raw transcripts, database copies and private file references are not synthesized from abbreviated reports. Use the original controlled evidence-root to reproduce READY. [Support/evidence boundaries](SUPPORT.md).

The [preparation verification record](V1_PREPARATION_VERIFICATION.md) is preserved byte-for-byte. Its 0.17.2 version and pending statuses are historical. Earlier [E2E records](E2E.md), [RC verification](RC_VERIFICATION.md) and the [v0.17 matrix](support-matrix-v017.json) retain their tested scope and do not become new final-v1 runs.
