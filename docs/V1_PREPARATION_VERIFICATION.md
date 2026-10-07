# V1-01 through V1-05 preparation — verification record

Baseline: `eb046e27bb0de1f07413111d8e0ba48c5c444cea` (tree
`36bfea74a7e6b01e257ca7ada3dd0a46f3adab29`). Working package: **0.17.2**.
This record describes preparatory implementation, not completion of final-v1
live qualification, support promotion or release approval.

## Mapping and explicit remaining gates

| Workstream | Implemented preparation | Still required before v1 release |
| --- | --- | --- |
| V1-01 | Position-aware normalization, complete CLI parser paths, inventory v2, mutation tests and independent comparison | Final candidate identity/CI; reviewed future baseline changes |
| V1-02 | Explicit data/import boundary, response/error schemas, SDK signatures, actual-response conformance and export | Review final surface; no promotion of internal helpers |
| V1-03 | SemVer/schema policy, unchanged historical fixtures/readers/writers, documented upgrade/rollback boundaries | Final upgrade/rollback guidance with chosen software/artifact |
| V1-04 | Matrix v2, separate support axes, full artifact/configuration-bound probe checks, historical matrix retained | Actual owner final-artifact E2E, anomaly disposition, supported baseline |
| V1-05 | Build-once six-lane CI, exact wheel/sdist/Skill identity, measured/completed evidence separation, archive/approval checker | Final 1.0.0 metadata/bytes, completed CI, durable archive, owner terms/channel and scoped approval |

The preparatory public inventory contains 78 reviewed data records, 28 MCP tools
and 51 CLI leaf commands. The original 0.17 inventory, legacy evidence hashes,
E2E history and original support matrix bytes are retained. No TaskState,
IntakeState, runtime/gate/jobs DB writer version, runtime authority rule, host
form response, provider adapter or persistence implementation is changed.
The generic CLI help still describes trusted-local alpha hardening; stable
release labeling is intentionally deferred with final release metadata.

## Local ambient verification

Environment: Linux, Python 3.13.5, Pydantic 2.13.4, PyYAML 6.0.3,
pytest 9.0.2 and jsonschema 4.26.0. Installed the local package without downloading
or upgrading dependencies. This is neither the reference nor minimum matrix.

- Focused inventory mutations: 40 passed.
- Focused public/inventory/release/legacy tests: 128 passed.
- Adding the original contracts file to that focused scope: 165 passed.
- Full explicitly core-only suite: **764 passed, 1 deselected, zero failures or
  skips**, 206.78 seconds. The SDK interoperability file and named SDK wire test
  were explicitly excluded locally because MCP SDK was not installed; this is
  NOT TESTED locally, not a hidden SDK PASS.
- Offline installed-wheel/sdist smoke: PASS outside the checkout, packaged
  contracts/Skill/import/CLI/worker checked, reconstructed package payloads equal.
  Dependencies were reused from the ambient environment (`ambient-offline`),
  not a claimed clean dependency qualification.
- Packaged/generated inventory and independent reviewed baseline: equal.

Machine JSON snapshots were subsequently compact-formatted without changing
parsed values. Final-head CI must validate the exact committed package bytes;
local pre-format distribution digests are not the final CI artifact identity.
No local distribution is represented as a published/final-live-qualified build.

Reproduction:

```bash
python tools/check_contracts.py
python -m pytest -q \
  --ignore=tests/test_v03_sdk_interop.py \
  --deselect=tests/test_v04_wire.py::test_official_sdk_native_elicitation_decline \
  --junitxml=test-results.xml
python tools/check_no_skips.py test-results.xml
python -m compileall -q src tests tools
python tools/check_distribution.py --offline
```

## Intermediate failures, not hidden qualifications

The first focused run reported 83 passed and one failure in a test fixture:
`deepcopy` cannot copy dataclass Field mapping-proxy metadata. Replacing only the
field objects using shallow copies fixed the mutation test; no production SDK
signature was changed to make it pass.

An early full run was invalidated by editing/adding package source while its
long-lived test process was running. The loaded-build guard correctly refused
later operations. That run had 62 failures, five errors, 653 passes and one
deselection and is not product qualification. Subsequent full runs held package
bytes fixed. An actual conformance failure then exposed omitted fields in the
new event response schema (schema_version, event_id, source); the existing event
output was correct and unchanged. That run was 762 passed, one failure, one
deselection. The schema was corrected, and the full successful run above followed.

Synthetic release evidence fixtures test READY/BLOCKED decisions without any
real host, provider, CI run, archive or publication. They are marked synthetic
and never appear in the support matrix as observed live evidence.

## Remote and live evidence

The implementation PR is the source of final-head CI run IDs, exact source
commit/tree, seven completed jobs (build once plus six dependency/platform
lanes), distribution artifacts and resolved dependencies. Do not merge on queued
or failed CI. Verify the reviewed head, tested merge tree and merged source tree
before recording completion. A later push run is distinct from pre-merge proof.

No owner-runtime operation, provider dispatch, genuine host form, trust or
permission change, license/channel selection, tag or publication was performed.
Follow [the final live procedure](V1_LIVE_E2E.md) only after final 1.0.0 candidate
preparation. See [release preparation](V1_RELEASE_PREPARATION.md) and
[Japanese guide](V1_PREPARATION_ja.md).
