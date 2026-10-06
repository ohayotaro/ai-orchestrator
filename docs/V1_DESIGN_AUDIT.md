# v1.0 design audit — baseline findings and decisions

Date: **2026-10-06 JST**.
Baseline main: `aa2697e79f181a252aff6d775e3aede07fd93248` (`0.17.1`).
Tree: `b21f22460b683452a2dc8b25030cd71d082498b3`.
Decision: proceed with [the finalized stable-control-plane design](V1_STABLE_CONTROL_PLANE.md),
**not** a version-only release or a declaration that v1.0 qualification passed.

## 1. Evidence and limits

Reviewed the current roadmap, RC design/verification, support matrix, packaging/CI,
contract generator and tests, SDK/transport/CLI, persistence and installation
identity implementations. Obtained the exact tested source from successful main
CI run **323**, run ID `37408085544`, head equal to the baseline above.
The source artifact ID is `11388210697`; its downloaded ZIP SHA-256 was checked
against GitHub's recorded digest:

```text
ZIP:       15538fde8b73351945defe1372eb5d2e23aec06e1253e9b1abd13fd7b8abc8da
source.gz: 3a1276eea1f46a49dce5d448fcdaf2a46bff4798476940e23a75bd502a090df6
```

The owner-reported full 0.17.0 qualification and targeted 0.17.1 closure remain
valid records of their stated scope. They were read, not rerun by this audit.
No external provider, owner runtime, live HumanGate, trust/permission change,
cleanup/restore of the owner's project or package publication was performed.
This is a design/source audit plus bounded local verification, not exhaustive
proof that the controller has no defects.

Local test scope and measured results are recorded in section 4. Existing CI
success is separate evidence, not a substitute for the newly missing cases.

## 2. Findings

### V1-A01 — Schema normalization can erase contract meaning — BLOCKER for freeze

`src/ai_orchestrator/contract_inventory.py:14-42` recursively removes dictionary
keys named `title`, `description` and `$comment` regardless of schema position.
That includes real names under `properties`/`$defs` and instance data nested
under `const`, `enum` and `default`.

Reproduction changes a `description` property's type from string to integer:
the raw schemas differ and an independent JSON Schema validator accepts the
string instance under one and rejects it under the other, yet their normalized
inventories are equal. Seven schema probes demonstrate the broader class.
This is a compatibility-checker defect, not a demonstrated runtime authorization
bypass or evidence that a current live task was corrupted.

Decision: schema-position-aware canonicalization, a versioned algorithm and
mutation-sensitive regressions before stable freeze. Keep old inventory and
historical state hashes separate; never repair this by rebaselining history.

### V1-A02 — CLI inventory misses behavior-changing arguments — BLOCKER for freeze

`contract_inventory.py:61-76` records only leaf arguments and only dest, flags,
requiredness, nargs and choices. It omits root/parent options, defaults, types,
action/constant values and mutual-exclusion rules. The actual CLI includes the
root `--project`, mutually exclusive terminal modes and a default
`single_terminal=True` (`cli.py:29-51`).

Five probes independently mutate a terminal-mode default, timeout type, flag
constant, root-option requiredness and mutual exclusion. Every mutation leaves
the recorded inventory identical. These are five detection gaps in one checker,
not five observed unsafe live executions.

Decision: inventory the complete parser path and tested behavior; use symbolic
representations for environment-derived defaults. Include output stream and
exit-code contracts, not just flag names.

### V1-A03 — Stable surface is not defined in both directions — BLOCKER for freeze

The generated inventory has 78 candidate model records, 28 MCP tools and 51
CLI leaf commands. `contract_inventory.py:79-110` hashes MCP input models but
has no corresponding output/error schema inventory. It discovers `Contract`
subclasses rather than declaring a complete public SDK/import boundary.
`providers.py:22-34,68-82` defines the public RunRequest dataclass and adapter
protocol, which are not covered by that Contract-subclass scan.

`tests/test_v017_contracts.py` checks generated/packaged equality, historical
sample hashes and important negative behavior. That is useful evidence, but
regenerating both snapshots does not detect an intentionally changed response,
missing SDK parameter or the collisions above.

Decision: reviewed stable allowlist; response/error/CLI/SDK fixtures; old/new
compatibility and deliberate mutation checks. Private Engine/Store helpers do
not become stable Python APIs merely because data types cross the wire.

### V1-A04 — RC closure is not a supported final-v1 host baseline — BLOCKER for release

`docs/support-matrix.json` has a top-level axes list, but a single status per
combined host/provider entry. Both recorded Claude Code entries are conditional;
Codex/Antigravity hosts are unverified. There is no supported entry. The 0.17.1
entry has one targeted refusal run and refers back to the full 0.17.0 runs.

The RC design requires a supported positive baseline and allows conditional
limitations outside that baseline, while the later closure explicitly retained
a conditional Claude Code transport because of a fail-safe intent/wire anomaly.
Do not conceal this difference or retroactively rewrite the owner's result.

Decision: preserve v0.17 closure; require a separately qualified supported v1.0
end-to-end baseline on exact final artifacts. Independently model transport and
provider-role support. Current conditional/unverified entries stay unchanged
until evidence justifies an operation-scoped update. No generic host fault
attribution, automatic retry, form bypass or wider native permissions.

### V1-A05 — Release evidence lacks final-artifact completeness and durability — BLOCKER for release

The live support records retain build prefixes while `build_digest` is null.
`build_identity.py` fingerprints kernel source/assets, not external binaries or
all installed dependencies. `.github/workflows/ci.yml` retains source archives
for seven days and test/dependency artifacts for fourteen days. These are useful
CI diagnostics, not by themselves a durable exact-artifact release record.

The generator still emits `candidate_version=0.17.0` and
`v1_release_declared=False`. A later flag/asset/version edit changes the loaded
build digest; flipping such metadata after qualification cannot preserve exact
artifact identity.

Decision: full-digest, environment- and artifact-bound release manifest; durable
controlled evidence retention; all metadata frozen before qualification;
publication approval recorded outside the tested package. No inference of full
model identity from an adapter-default setting and no reconstruction of missing
full digests from reported prefixes.

### V1-A06 — Stable compatibility/release policy needs a normative handoff — BLOCKER for readiness

The old v1.0 roadmap lists candidate surfaces without the final stable/private
boundary or package/schema compatibility rules. The RC design header still said
live qualification was pending after the separate verification and roadmap
recorded closure. `pyproject.toml` remains 0.17.1/Alpha and contains no license
metadata; this audit does not select distribution terms on the owner's behalf.

Decision: finalize the stable/private and SemVer policies, retain the existing
reader set and 3/1/2 database writers, state exact upgrade/rollback boundaries,
align lifecycle status and English/Japanese release documentation, and make
publication metadata/terms an explicit release-preparation check. The status
header is corrected in this documentation change; that does not imply the
remaining implementation/qualification work has been completed.

## 3. Reproduction

Run against the audited source:

```bash
python docs/audits/v1_baseline_probe.py
```

The retained script verifies Git blob
`af9297e4784a3674718d5cba7c078d08be891b5b` for the inventory module, extracts the
three relevant functions from its AST, and runs synthetic schemas/parsers.
It does not import or open a controller runtime, dispatch a provider or change
project authority. A changed source blob is refused rather than mislabeled as
the historical baseline.

Measured result: **12/12 expected inventory collisions reproduced** — seven
schema cases and five CLI cases. The result label is
`BASELINE_GAPS_REPRODUCED`, not a passing safety qualification. The eventual fix
needs regressions asserting that incompatible cases differ; this historical
reproducer intentionally must not be reinterpreted as expected future behavior.

## 4. Verification record

- Baseline main CI run 323: completed, success on the retrieved exact head.
- Local environment: Linux, Python 3.13.5, Pydantic 2.13.4, pytest 9.0.2;
  ambient dependencies, **not** the pinned reference or minimum matrix.
- Targeted `tests/test_v017_contracts.py`: **34 passed**.
- Initial core attempt before installing the package: **28 failed, 642 passed,
  1 deselected**. Isolated subprocesses could not import the uninstalled package
  (`ModuleNotFoundError`); this was an audit-environment setup failure, not
  evidence of 28 controller defects.
- Installed the unchanged package into the disposable audit environment with
  `pip install --no-index --no-deps --no-build-isolation -e .`; no dependencies
  were downloaded or upgraded. Confirmed an isolated `python -I` import.
- Repeated the same core scope after installation: **670 passed, 1 deselected,
  zero failures and zero skips**, in 214.17 seconds. `check_no_skips.py` accepted
  the JUnit report. This is the ambient core scope, not the clean reference matrix.
- The MCP SDK was not installed locally. The entire SDK interoperability file
  and one SDK-dependent wire test were explicitly excluded, as shown below;
  this is NOT TESTED locally, not an SDK PASS or a hidden skip. Existing baseline
  CI remains the separate reference-lane evidence. No live-host claim follows.

```bash
python -m pytest -q \
  --ignore=tests/test_v03_sdk_interop.py \
  --deselect=tests/test_v04_wire.py::test_official_sdk_native_elicitation_decline \
  --junitxml=/mnt/data/v1-audit-core-installed-results.xml
python tools/check_no_skips.py /mnt/data/v1-audit-core-installed-results.xml
```

Compared the edited tree with the retrieved baseline archive: runtime source,
existing tests, `docs/E2E.md`, `docs/support-matrix.json` and
`ROADMAP_HISTORY.md` were unchanged. Only the roadmap/RC status handoff and the
new design, audit and historical reproducer are part of this documentation change.

The full implementation, exact final six-lane CI, distribution qualification
and owner live E2E required by the finalized design remain separate gates.
