# v0.17 implementation and verification record

Status: **implementation candidate; final-head CI and required owner live
qualification are tracked separately**. Package version 0.17.0 is not a v1.0
release declaration. The historical baseline/design findings remain unchanged
in [V017_DESIGN_AUDIT.md](V017_DESIGN_AUDIT.md).

## Implementation mapping

| Workstream | Implementation | Retained regression evidence |
| --- | --- | --- |
| RC-01 | `cancellation.py`, Store/Engine entry checks, shared mutation boundaries | `test_v017_hardening.py`; existing cancel-after-prompt gates; zero-call finalization and atomic rollback |
| RC-02 | No-first HumanGate enum, operation-specific title, unchanged response validator | `test_v017_contracts.py`; existing protocol/wire negative tests |
| RC-03 | Shared `evidence.py` inventory, recursive current/frozen roots, metadata conflicts and semantic binding checks | Nested learning, shared v1/v2 refs, frozen influence, fresh Start after scratch cleanup |
| RC-04 | `receipts.py`, jobs DB2 migration and transactional retirement; receipt-aware restore | All four queue actions, changed args, restore lineage, receipt transaction SIGKILL |
| RC-05 | `maintenance.py`, durable intent/recovery staging, blocked startup, exact reconciliation, stale DB handle refusal | Actual subprocess SIGKILL before/after data, partial writes/deletes, DB commit, audit and rollback |
| RC-06 | Packaged `assets/contracts.json`, `contracts`/`identity`, historical hash fixtures, explicit host Skill comparison, clean distribution smoke | Dynamic surface equality, old serialized hashes, build mismatch, SDK wire suite, minimum/reference dependency CI |
| RC-07 | Versioned host/provider matrix and repeatable owner live procedure | [Live procedure](RC_LIVE_E2E.md); mandatory live rows remain unverified |

All local negative/crash tests use disposable repositories and deterministic
adapters. They do not operate on the owner's E2E runtime, dispatch an external
provider, or simulate a human click as live evidence. The old baseline reproducer
intentionally remains limited to 0.16.0; it documents pre-fix observations rather
than serving as an assertion that those behaviors are acceptable in 0.17.

The candidate contract inventory freezes model and MCP schema semantics, public
CLI argument shapes, authority tiers, persistence versions and links to negative
tests. It excludes display prose and private helper APIs. Historical v1-v9 task,
v1-v6 intake and v1/v2 artifact sample hashes were generated with the retained
0.16.0 reader and compared against the new reader, not rebaselined to new output.

## Reproducible commands

```bash
python -m pip install -r requirements/rc-reference.txt
python -m pip install --no-build-isolation -e '.[dev,interop]' -c requirements/rc-reference.txt
python -m pytest -q --junitxml=test-results.xml
python tools/check_no_skips.py test-results.xml
python -m compileall -q src tests tools
python tools/check_distribution.py
```

The reference release matrix is Linux Python 3.11/3.12/3.13 and macOS Python3.13.
Separate Python3.11 jobs check core-only declared minima and the combined SDK
minimum. SDK 1.29 requires Pydantic>=2.11 and jsonschema>=4.20, higher than this
kernel's core-only floors; these are distinct installation scopes, not a reason
to claim the core minima were tested after silently upgrading them. The core-only
lane explicitly excludes the two SDK tests; all five interop/reference lanes run
them and reject any skipped test. Dependency requirements are grounded in the
SDK's versioned `v1.29.0/pyproject.toml` in modelcontextprotocol/python-sdk. Each lane records
its resolved dependency versions; reference lanes install the built wheel in a
fresh environment outside the checkout, smoke CLI/Skill/worker/imports and rebuild
a wheel from the sdist. Optional SDK tests may not be silently skipped in CI.
Local `--offline` distribution checks borrow ambient dependencies and are labelled
accordingly; they do not substitute for clean reference dependency qualification.

Final-source CI evidence is recorded on the implementation PR after all jobs
complete. The merged tree must match that tested tree. No merge on queued or
failed final-head CI, automatic publication, release tag or owner-runtime upgrade
is part of this implementation request.

## Explicit remaining release gate

The owner must still qualify the required normal flow, genuine refusal and idle
cancellation/finalization twice on fresh IDs at the same final build. Current
host/provider rows are `unverified`, not promoted from historical PASS reports.
Therefore Gate D (live qualification) and the final v1.0 release decision remain
open until that evidence is supplied and reviewed.
