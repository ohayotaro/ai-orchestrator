# v0.17 implementation and verification record

Status: **v0.17 Release Candidate Hardening implemented and live-closed at
v0.17.1**. Package version 0.17.1 is not a v1.0 release declaration. The historical baseline/design findings remain unchanged
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
| RC-07 | Versioned host/provider matrix and repeatable owner live procedure | Owner full 0.17.0 RC matrix + targeted 0.17.1 recheck; Claude Code transport conditional; untested hosts remain unverified |

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

## RC live gate result

Gate D is complete for v0.17. The owner qualified the required Fresh-Write,
genuine refusal and idle cancellation/finalization flows twice on v0.17.0, then
ran the single targeted v0.17.1 follow-up required by the live-discovered RC-01
prepare-time gap. The follow-up refused provider-permission preparation before
any gate/form/effect. Claude Code 2.1.284 transport remains conditional because
of one fail-safe Yes-intent/No-wire anomaly; this does not promote untested
Codex/Antigravity hosts to supported.

The remaining decision is the separate v1.0 release decision, not a v0.17
qualification gate.


## 0.17.0 owner live qualification and 0.17.1 follow-up

The owner-reported 0.17.0 run completed the required positive Fresh-Write flow
twice, genuine Start refusal twice, and idle cancellation/finalization twice.
RC-03/04/05 scratch cases and the final original-project comparison also passed.
One Claude Code 2.1.284 Yes-intent/No-wire anomaly remained unexplained but
failed safe; controlled positive retries succeeded and the host transport was
therefore classified conditional rather than unsupported.

The same run identified one controller inconsistency against the approved RC-01
wording: provider-permission form preparation did not reject a task with an
existing cancellation request, although the resolve/apply path did reject it and
no authority increase occurred. 0.17.1 closed that entry point before the form
is created.

The targeted owner recheck then passed on main
`13f0b43839c10e30e3ba68bcb5aec793f6779fde`: fresh task
`task-caeeda5eb97b` was cancelled, and request ID
`v0171-closure-perm-after-cancel-1` was refused with
`task has a cancellation request` before any gate/form was created. Gate rows,
gate events, provider/validator counters, grants, approvals and project files
were unchanged by the permission request. Combined with the full 0.17.0 matrix,
this closes v0.17 at v0.17.1.
