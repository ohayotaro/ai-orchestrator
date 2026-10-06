# AI Orchestrator Roadmap

Current decision date: **2026-10-06 JST**.
Implementation baseline: **0.17.1**, with v0.17 Release Candidate Hardening
formally live-closed. The owner-reported 0.17.0 qualification passed the full RC
matrix; v0.17.1 then closed the remaining RC-01 provider-permission prepare gap
with a targeted live recheck showing refusal before any HumanGate row/form or
provider/validator/file effect. The v1.0 release decision remains separate.

The approved v0.17 scope and exit criteria are normative in
[RC Hardening](docs/RC_HARDENING.md). The source audit and reproduced baseline
findings are retained in [v0.17 Design Audit](docs/V017_DESIGN_AUDIT.md).
Design approval is not implementation completion or permission to publish v1.0.

## Vision and invariants

AI Orchestrator is a provider-neutral execution control plane between a
user-facing agent and cooperating worker providers. Capabilities describe what
work is needed; provider resolution selects who; model/runtime resolution
selects how; policy and budgets limit effects and resources.

The architectural invariants remain:

- Agent intent, exploratory prose and model confidence are not human authority.
  Concrete proposals still cross Start, Execution and Acceptance independently.
- Existing trusted authority can be selected task-locally; expanding persistent
  provider/plugin, validator, workflow, policy or accepted-context authority
  requires the existing explicit governance and trust path.
- Deterministic validation and fresh independent review are evidence, not a
  replacement for acceptance. Predictions are not measured test results.
- Writable concurrency uses isolated ownership and deterministic integration;
  independent workers never share an unisolated writable worktree.
- Learning may accumulate evidence and candidates; authority does not accumulate
  silently. Exploration changes understanding, not execution permission.
- Unknown usage remains unknown. No hidden provider/model/budget fallback,
  automatic replay of uncertain effects, automatic repair or host-form bypass.
- Historical evidence remains readable and inspectable. Reading does not rewrite
  it, invent provenance, or promote it into accepted knowledge.
- This remains trusted-local POSIX execution, not remote exactly-once,
  cryptographic human presence or isolation from a hostile same-OS-user process.

## Completed implementation milestones

| Milestone | Established boundary | Primary reference |
| --- | --- | --- |
| v0.1-v0.4 | Local execution, durable tasks/intakes/jobs, single-terminal HumanGates | [Single terminal](docs/SINGLE_TERMINAL.md) |
| v0.5 | Semantic capabilities and deterministic provider resolution | [Capabilities](docs/CAPABILITIES.md) |
| v0.6 | Versioned workflow/DAG and task-scoped trusted workflow selection | [Workflows](docs/WORKFLOWS.md) |
| v0.7 | Isolated parallel writes and deterministic integration | [Parallel execution](docs/PARALLEL_EXECUTION.md) |
| v0.8 | Adaptive task-scoped workflows, bounded authority controls | [Adaptive orchestration](docs/ADAPTIVE_ORCHESTRATION.md) |
| v0.9 | Provider-local model/runtime policy, isolation and host diagnostics | [Model variants](docs/MODEL_VARIANTS.md) |
| v0.10 | Attributable usage and explicit budgets | [Usage/budgets](docs/USAGE_BUDGETS.md) |
| v0.11 | Conservative interruption/recovery without ambiguous replay | [Recovery](docs/RECOVERY.md) |
| v0.12 | Persisted contracts and physically non-restamping current-version reads | [Persistence](docs/PERSISTENCE.md) |
| v0.13 | Explicitly pinned trusted Provider SDK / plugin activation | [Provider SDK](docs/PROVIDER_SDK.md) |
| v0.14 | Governed Project Learning, typed evidence and frozen influence | [Project Learning](docs/PROJECT_LEARNING.md) |
| v0.15 | Operational diagnosis, scoped backup/restore/retention; intake-root fix in 0.15.1 | [Operations](docs/OPERATIONS.md) |
| v0.16 | Durable non-authoritative exploration and explicit task transition | [Exploration](docs/EXPLORATION.md) |

Detailed owner-reported runs and their limitations are in [E2E](docs/E2E.md).
A passed milestone records its tested scope; newly discovered defects are still
eligible RC blockers. It is not a claim of universal host compatibility.

The complete pre-audit roadmap is preserved byte-for-byte as
[ROADMAP_HISTORY.md](ROADMAP_HISTORY.md), using the original Git blob
`781990660235800fea351dfa8cab3b16142c381c`. It retains all historical sub-version
plans and rationale, including superseded pending-status wording. The current
roadmap and approved RC design, not that historical snapshot, govern future work.

## v0.17 — Release Candidate Hardening — implemented and live-closed at v0.17.1

Primary goal: correct the demonstrated lifecycle/evidence gaps, freeze candidate
v1.0 public contracts, and qualify exact supported deployment combinations.
This is not a new provider, permission, workflow or exploration feature cycle.

### Mandatory scope

| Workstream | Fixed decision | Required evidence |
| --- | --- | --- |
| RC-01 Cancellation | Preserve durable cancel intent; expose cancellation state; add exact-scope operator-only safe finalization; reject cancelled requests consistently | No extra provider/validator/file effects; atomic finalization; live idle-probe closure |
| RC-02 HumanGate UX | No-first required enum; exact affirmative wire response still necessary; no untested enum default on the current protocol | Actual-host No/cancel/untouched/Yes/stale/timeout tests and independent schema/wire checks |
| RC-03 Evidence roots | Shared complete recursive reference inventory; reject conflicting metadata before file-I/O deduplication | Nested learning, all task/intake/exploration roots, legacy and frozen historical references, scratch cleanup survival |
| RC-04 Idempotent retirement | Keep durable request receipts when terminal job payloads are cleaned | Same ID never becomes a new job; transactional retirement; migration and restore-lineage tests |
| RC-05 Maintenance interruption | Durable intent, persistent recovery material and fail-closed startup; explicit reconciliation only | Crash injection across replacement/deletion/audit boundaries; no automatic repair/replay |
| RC-06 Contract/install freeze | Versioned public inventory, historical hash/wire fixtures, build/install and loaded-code/Skill identity checks | Compatibility matrix and clean wheel/sdist installation outside the editable checkout |
| RC-07 Qualified release | Separate host transport from provider-role support; exact versions, scope and evidence | Supported baseline passes twice on fresh IDs; conditional and unverified combinations labelled honestly |

Implementation mapping, regression/build evidence and the completed qualification
boundary are in [RC Verification](docs/RC_VERIFICATION.md). Operator commands are
specified in [RC Operations](docs/RC_OPERATIONS.md). The versioned
[support matrix](docs/support-matrix.json) records the exact qualified/conditional
host-provider evidence; untested combinations remain unverified.

### Audited baseline findings that cannot be waived by documentation

The pre-implementation 0.16.0 audit reproduced four cases in temporary repositories:
cancellation intent remains invisible/nonterminal and direct approval can still
be recorded; doctor can hide conflicting metadata for a shared artifact path;
nested accepted learning roots can be omitted from a cleanup plan; and deleting
terminal jobs allows the same request ID to be accepted as new queued work.
No external provider was dispatched by these negative probes. The audit also
identified maintenance-crash validation and release-matrix gaps by source review.

RC-03 and RC-04 are mandatory correctness fixes, not optional polish. The previous
v0.15/v0.16 live fixtures did not cover those additional cases. A core authority,
data-loss, replay, migration or recovery defect blocks release even if described
in a known-issues file.

The owner-reported `v016-e2e-docstring-probe` follow-up set cancellation intent
and recorded event E-1748 but left status `awaiting_approval`. It must not be
reported as terminal `cancelled`. RC-01 addresses this distinction; the design
audit does not operate on that live task.

### Compatibility decisions

Keep TaskState v9, IntakeState v6, Exploration v1, runtime SQLite v3 and gate
SQLite v1 unless a reviewed design amendment proves another change necessary.
The implemented receipt addition deliberately advances jobs SQLite v1 to v2;
it does not reinterpret an old marker or rewrite historical state merely on read.
New cancellation-view, receipt and maintenance-intent contracts are separately
versioned. Retain supported historical readers and exact evidence hashes.

Preserve the existing Linux Python 3.11/3.12/3.13 and macOS Python 3.13 execution
verification baseline. Installation minimums do not imply every newer Python
version is tested. Keep a minimal/reference dependency matrix and independent
MCP SDK tests. Provider-local model values remain adapter data, not a kernel
vendor catalog.

Claude Code host with Claude reasoning/review and Codex implementation is the
required positive live baseline. Codex/Antigravity host combinations need their
own fresh evidence before `supported` status; safe conditional or exact
known-incompatible boundaries may remain. Universal Cartesian-product support,
remote exactly-once and authenticated human clicks are not release promises.

### Exit gates

1. **Design:** approved scope, findings and acceptance conditions recorded.
2. **Correctness:** mandatory defects fixed with new regressions; crash/lifecycle
   boundaries demonstrated, not assumed.
3. **Freeze:** versioned inventory, compatibility fixtures and clean installation
   checks pass on the exact candidate source.
4. **Live qualification:** required supported flows pass twice on fresh fixture
   IDs at the final build, including genuine refusal and safe cancellation.
5. **Release decision:** all required final-head CI is complete and green; no
   unresolved blocking finding; limitations, upgrade/downgrade and support
   evidence are reviewed. No merge-on-queued-CI or automatic publication.

v0.17 is closed at 0.17.1. The v1.0 candidate/tag is a separate explicit
release decision after this qualification. PASS, FAIL, NOT TESTED and
NOT APPLICABLE remain distinct; closure does not promote unverified host/provider
combinations to supported.

The exact operation contracts, failure handling, implementation sequencing and
scope exclusions are in [RC_HARDENING.md](docs/RC_HARDENING.md).

## v1.0 — Stable Control Plane — design finalized; implementation/qualification pending

The normative scope, stable/private boundary, compatibility policy and release
criteria are finalized in [Stable Control Plane](docs/V1_STABLE_CONTROL_PLANE.md).
The source audit, evidence limits and reproduced contract-checker gaps are in
[v1.0 Design Audit](docs/V1_DESIGN_AUDIT.md). This is not a version-only release,
a v1.0 publication approval or a reversal of the recorded v0.17 closure.

| Workstream | Fixed v1.0 decision | Required evidence |
| --- | --- | --- |
| V1-01 Sound inventory | Schema-position-aware canonicalization; complete CLI behavior; versioned inventory v2 | Reproduced collisions fixed; mutation-sensitive tests; historical hashes unchanged |
| V1-02 Public surfaces | Explicit stable allowlist covering inputs, outputs/errors, CLI and SDK signatures | Independent compatibility/behavior fixtures; no accidental private Python API freeze |
| V1-03 Compatibility | Package SemVer separate from schema/SDK versions; retain current readers and database writers 3/1/2 | Golden history, migration/restore and documented rollback boundaries |
| V1-04 Qualified support | Separate transport/provider-role axes; at least one supported final-artifact single-terminal baseline | Positive/refusal/cancellation twice on fresh IDs; conditional hosts are not relabeled |
| V1-05 Release proof | Full artifact/environment identity, durable evidence, clean packaging and explicit publication decision | Final-head six-lane CI, clean wheel/sdist checks, final-artifact live qualification |

The existing candidate checker can hide schema and CLI changes; those are
mandatory correctness fixes before stable freeze. The current Claude Code host
entry remains conditional and cannot alone satisfy the v1.0 supported-baseline
gate. Existing 0.17.0/0.17.1 runs remain historical evidence for their tested scope.
Do not infer a full build digest from its reported prefix, alter tested package
metadata after qualification, or use expiring CI artifacts as the only release
record.

v1.0 adds no new provider, permission, workflow, learning-promotion or exploration
feature family. Start/Execution/Acceptance, explicit trust, isolated writes,
unknown-usage semantics, conservative recovery and non-authoritative exploration
remain invariant. Design completion, implementation, live qualification and
publication are four different facts.

## v1 implementation batching and current preparation

V1-01 through V1-05 preparatory changes are delivered as one 0.17.2 implementation
batch, with focused automated regression/contract/installation checks between
workstreams. A separate owner live E2E is not required after each workstream.
Final live qualification is one campaign on the frozen final 1.0.0 artifact,
with the required fresh positive/refusal/cancellation repetitions and all
negative host/scratch cases. Preparation does not complete the live or release
exit gates. Do not relabel the preparatory artifact after testing.

See [public contracts](docs/PUBLIC_CONTRACTS.md),
[release preparation](docs/V1_RELEASE_PREPARATION.md),
[final live E2E](docs/V1_LIVE_E2E.md) and
[Japanese preparation guide](docs/V1_PREPARATION_ja.md).

## v1.0 distribution decision

Owner decision on **2026-10-06 JST**: release under **Apache License 2.0**.
GitHub Releases is the canonical release record; PyPI is the package distribution
channel and must receive the same qualified wheel/sdist bytes. This decision does
not itself authorize a tag or publication; the final manifest-bound owner release
approval remains a separate gate.

## Change control

Version sequencing is not a promised calendar schedule. New evidence may require
a reviewed amendment. Do not widen v0.17 into unrelated features, redefine
HumanGate to hide host limitations, equate a known subtotal with complete cost,
or use model output instead of measured validation. Record implementation
completion separately from live qualification and package publication.
