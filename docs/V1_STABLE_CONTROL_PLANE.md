# v1.0 — Stable Control Plane: finalized design

Status: **DESIGN FINALIZED — implementation, final-artifact qualification and
publication are separate gates, not completed by this document.**
Decision date: **2026-10-06 JST**.
Audited baseline: `aa2697e79f181a252aff6d775e3aede07fd93248`, package `0.17.1`.
Findings and measured scope: [V1_DESIGN_AUDIT.md](V1_DESIGN_AUDIT.md).

This is the normative v1.0 elaboration of [ROADMAP](../ROADMAP.md). v0.17 remains
formally closed using its recorded combined 0.17.0/0.17.1 evidence. That closure
is not an assertion that a 1.0 artifact has been tested or that a conditional
host is supported. [RC_HARDENING.md](RC_HARDENING.md) continues to govern the
underlying safety boundaries; the decisions below govern stable-contract and
v1.0 release qualification. A conflicting old status sentence is not a waiver.

## 1. Product decision and non-goals

v1.0 is a provider-neutral, trusted-local POSIX execution **control plane**, not
a claim that every provider/host/model combination is interchangeable. It makes
the existing safety and public compatibility promises explicit and testable.
Do not turn this milestone into a new orchestration feature cycle.

Retain independent Start, Execution and Acceptance; exact-scope, fresh,
correlated HumanGates; explicit persistent trust changes; isolated writable
worktrees and deterministic integration; measured validators and independent
review; conservative cancellation/recovery; durable request identity; complete
historical evidence roots; and explicit operator-only maintenance. Reading must
not restamp history. Cancellation intent is not proof that a remote effect
stopped. Unknown usage is not zero or a complete cost. Learning and exploration
accumulate understanding and evidence, never implicit authority.

Exclude new providers/model catalogs, automatic provider/model/budget fallback,
automatic repair or ambiguous replay, autonomous learning promotion, a new DAG
or exploration model, remote/distributed execution, Windows execution support,
hostile same-OS-user isolation and cryptographic human-presence claims. A CLI
approval is not a workaround for a refused, unsupported or timed-out host form.
No owner runtime upgrade, live probe, permission change, tag or publication is
authorized merely by approving this design.

## 2. V1-01 — A sound, independently testable contract inventory

The current candidate inventory is not an adequate stable baseline: its schema
normalizer can erase real property names/literal data, and its CLI inventory
omits behavior-changing arguments. Fix these before declaring contracts stable.

Replace recursive key-name deletion with a schema-position-aware traversal.
Distinguish a schema object from maps of named schemas (`properties`, `$defs`,
`patternProperties`, etc.) and literal instance data (`const`, `enum`, `default`,
etc.). Preserve named keys and literal data exactly apart from explicitly
justified JSON-value normalization. Unsupported vocabulary must be preserved
conservatively or rejected, never silently simplified. Removing presentation
annotations is permitted only at actual schema positions. Preserve existing
minimum/reference dependency equivalences with dedicated positive tests.

Inventory CLI root and parent arguments as well as leaf commands, including
option aliases, positional order, value types, defaults/default factories,
action/constant semantics, requiredness, arity, choices and mutual-exclusion
rules. Represent environment-derived defaults symbolically (for example,
`current_working_directory`), not as the auditor's absolute path. Runtime
validation limits, exit-code categories, stream placement and authority class
also need fixtures; parser reflection alone does not capture them.

Use an explicitly versioned inventory **v2** with a named canonicalizer version.
Retain the old v1 inventory as historical evidence; do not overwrite its hashes
and call it the old baseline. This changes the inventory contract, not TaskState,
artifact or authority fingerprint algorithms. Historical state/evidence hashes
must stay byte-compatible. `contracts` must report its actual inventory format
and target package identity without the current hard-coded candidate label.

CI must both compare generated surfaces with an independently retained baseline
and test that deliberately incompatible mutations are detected. Regenerating a
snapshot and obtaining equality is not sufficient. Required mutation cases
include named `title`/`description`/`$comment` properties, named definitions,
literal defaults/const/enums, CLI defaults/types/constants/global options and
mutual exclusion, plus response-field and SDK-signature mutations. Genuine
annotation-only changes must not create a semantic false positive. HumanGate
presentation order and absence of an affirmative default retain separate wire
and actual-host tests even where validation semantics alone are equivalent.

## 3. V1-02 — Explicit stable surfaces, in both directions

Publish a reviewed allowlist mapping every stable entry to its public access
path, input and output contract, behavioral/authority rules, supported versions
and positive/negative fixtures. Reflection may check completeness, but must not
silently promote every Python class to a supported import API.

| Surface | Stable v1 promise | Not automatically frozen |
| --- | --- | --- |
| TaskSpec, profile/effect/write policy, capabilities and workflow | Documented data, defaults, scope, validation and resolution semantics; Workflow Schema v1 | Selection ranking or generated prose within those bounds |
| MCP | Documented tool names, inputs, success/refusal/error results, discovery/annotations, negotiation and authority semantics | An assertion of support for untested clients or newer protocols |
| CLI | Documented commands, global/parent options, JSON responses, stream/exit-code categories and operator boundaries | Help wrapping, descriptive prose and private parser helpers |
| HumanGate | Seven current gate kinds, strict affirmative response, binding, expiry/staleness, refusal and no-replay semantics | Host rendering fidelity, human-presence attestation |
| Provider SDK/plugin | SDK v1 / adapter API v2; documented imports, RunRequest fields/defaults, adapter protocol, optional descriptors, return/exception/diagnostic semantics, exact pins | Built-in adapter internals, vendor catalogs or undocumented Python imports |
| Persisted evidence and operations | Versioned readers/writers, no read-side rewriting, migration, backup/restore/retention, receipts and conservative recovery | Direct SQL layout access or mutation as a public extension API |
| Usage, learning and exploration | Unknown-value handling, budget enforcement, provenance, governance, revision-bound exploration-to-intake/task semantics | Exact model text, knowledge selection scores or automatic promotion |

Freeze response behavior as well as request validation. Retain the distinction
between JSON-RPC errors, MCP tool `isError` results, gate statuses, queued-job
outcomes and final task acceptance. Do not replace existing envelopes solely to
make them easier to inventory. Document and fixture operation-specific
success/refusal/error shapes and existing machine-readable identifiers. Generic
error-message prose is not a stable machine interface; clients must not parse
English messages to decide authority or replay. Any added error code must be an
explicit, tested contract change, not an undocumented catch-all rewrite.

Keep current protocol negotiation (`2024-11-05`, `2025-03-26`, `2025-06-18`), with
single-terminal forms qualified on the existing `2025-06-18` contract. A newer
published MCP specification does not silently extend this supported set. Never
mix newer form fields into an older negotiated protocol without a reviewed,
versioned compatibility change.

## 4. V1-03 — Compatibility, versioning and upgrade policy

Adopt SemVer for the package's declared public API after 1.0.0. Compatible fixes
are patch changes; compatible additions and deprecations are minor changes;
incompatible stable behavior requires a major change. A safety fix may reject
previously invalid/unauthorized behavior, but must not be used as a blanket
excuse to silently break previously valid documented inputs. Deprecations have
at least one documented minor release before removal in a major release.

Package versions, individual wire/persisted schema versions, SDK/adapter API
versions and inventory format versions are separate. Do not renumber every
schema to 1 merely because the package reaches 1.0.

Initial freeze retains TaskState writer v9/readers v1-v9; IntakeState writer
v6/readers v1-v6; Artifact writer v2/readers v1-v2; Job writer v2/readers v1-v2;
Exploration v1; Workflow v1; SDK v1/adapter API v2; runtime/gate/jobs SQLite
writers **3/1/2**. Retain the complete additional reader/version set in the
packaged persistence report, including legacy in-memory recovery views. The
v1.0 plan requires no further runtime/gate/jobs database migration.

All readers promised by 1.0 remain supported throughout 1.x. Unknown versions,
corrupt evidence, invalid authority and unsupported protocol behavior fail
closed. Read compatibility does not promise that an older executable can open
a newer writer format. A new schema/version in 1.x must preserve promised
readers and have a documented, explicitly compatible negotiation/upgrade path;
otherwise it requires a major package change. Adding a field is not automatically
compatible when strict consumers reject it or its presence changes a hash.

Retain golden serialized artifacts and typed-reader outputs from the historical
baseline, independently of the new inventory. Test Task/Intake/Artifact history,
permissions/cancellation, receipts, maintenance and learning/exploration
provenance on new and migrated databases. Current-version reads must remain
physically non-restamping. Restore must preserve known request identity and
never revive approvals or pending work by implication.

The supported rollback path is a verified matching full/pre-change backup and
the matching executable. Do not edit PRAGMA markers, fabricate missing receipts,
or advertise a lossy in-place downgrade. A backup is scoped controller recovery,
not a universal backup of the user's worktree or provider-side effects.

## 5. V1-04 — Qualified support, without relabeling evidence

Make support machine-checkable on separate **host-transport** and
**provider-role-execution** axes. Each operation-scoped entry records exact
kernel/artifact/build identity, host/CLI versions, negotiated protocol and
capabilities, OS/Python, roles, explicit versus adapter-default model/effort,
native permission assumptions, evidence date, run IDs and limitations. An
`adapter_default` value is not proof of a resolved model name. Unknown values
remain explicit. Use a versioned matrix format for the independent axis and
qualification semantics; retain the current v1 matrix as historical evidence.

Statuses remain `supported`, `conditional`, `known-incompatible` and
`unverified`. Evidence result is a different field: PASS, FAIL, NOT TESTED and
NOT APPLICABLE cannot be collapsed into support status. Historical evidence may
explain a decision but cannot pretend to be a run on the final 1.0 artifact.
A global `live_qualified` flag or `required_positive_baseline` flag is insufficient
to satisfy an operation/artifact-specific release gate.

**v1.0 requires at least one supported end-to-end single-terminal baseline**:
Claude Code host, Claude reasoning/planning/review and Codex implementation on
the qualified local deployment. Its full positive Fresh-Write flow, genuine
Start refusal and idle cancellation/finalization must each pass twice on fresh
IDs at the same final artifact/build. Repeat cancelled provider-permission
prepare refusal before any form/row/effect. Test the actual supported host's
untouched submission, explicit No, cancel, explicit Yes, timeout and stale/
duplicate response boundaries, and preserve independent SDK/wire regressions.

The recorded Claude Code 2.1.284 combination remains **conditional** today. Its
Yes-intent/No-wire anomaly needs an evidence-backed disposition before that
same combination can be promoted; unexplained anomalies are not cleared by
changing a label or counting only selected successful retries. Another exact
host version may qualify with its own complete evidence. A mandatory supported
baseline cannot be satisfied by the current conditional entry. This is a v1.0
release gate, not a retroactive reversal of v0.17's recorded closure. The older
wording and actual RC classification mismatch is explicitly recorded in the
audit rather than silently waived.

Codex-host and Antigravity-host combinations can remain conditional or
unverified outside the supported baseline. No full Cartesian-product promise
is required. Provider execution support is not host form support. A timeout or
intent/wire mismatch alone does not establish which component is at fault.
No host hook, CLI fallback, broader permission or automatic retry may manufacture
qualification evidence. Paid retries require explicit user intent. Corruption,
retention/restore and crash probes operate on scratch copies only.

## 6. V1-05 — Final-artifact proof and durable release evidence

Keep all six current dependency/OS/Python CI lanes: Linux Python 3.11/3.12/3.13
reference, macOS Python 3.13 reference, and Linux Python 3.11 minimum plus
core-only minimum. Record exact resolved dependencies and runner/platform
identity. The intentionally core-only lane excludes the two SDK cases; all
interop lanes run the independent SDK cases and reject skips. Installation
metadata `>=3.11` does not promise qualification of every newer interpreter.

Build wheel and sdist and install outside the editable checkout in fresh
reference environments. Verify packaged Skill/contract assets, CLI/worker/import
smoke, source-distribution rebuild payload equality, upgrade/read compatibility
and source-versus-loaded/host-Skill identity. Ambient/offline checks are useful
but are not reference/minimum dependency qualification.

Retain a release evidence manifest containing the full source commit and tree,
full kernel build digest, inventory/canonicalizer identity, wheel/sdist SHA-256,
packaged and checked host-Skill hashes, exact environment/dependencies, CI run
and test counts/scope, live matrix/fixture/gate IDs, limitations, migration and
rollback instructions, and the release decision. A digest prefix or package
version alone does not identify the qualified artifact. A source digest does
not cover external provider binaries or the entire dependency environment.

CI's current 7-day source and 14-day result artifacts are not the long-term
release record. Before publication, preserve verifiable evidence in durable
release records/assets or a controlled evidence archive with digest references.
Public summaries must omit credentials, raw prompts and unnecessary personal
paths. Keep sensitive raw live evidence in the appropriate controlled location;
redaction must not be misrepresented as the original byte-identical evidence.
Do not rewrite historical task evidence to sanitize a release report.

Final metadata/packaged-contract changes happen **before** final qualification.
Separate contract stability from publication state: the v2 inventory reports
its target version/stability, while publication approval is an external release
record, not a mutable `v1_release_declared` bit flipped inside a tested artifact.
This avoids invalidating build identity immediately after testing. A prepared
1.0.0 artifact is not a published release. Qualify the exact final bytes and
publish those bytes; do not rebuild or edit them after approval. Version-only
changes still change identity and require applicable final qualification.

Update Alpha/version/help labeling, aligned English/Japanese installation and
support documentation, release/upgrade/rollback notes and publication metadata
in the release-preparation change. Record the owner's chosen distribution
terms/channel; this design does not select a license or authorize publication.
Repository branch protection or publishing permissions are separate owner
configuration, not changes implicitly granted here.

## 7. Implementation order and acceptance gates

| Stage | Required work | Exit evidence |
| --- | --- | --- |
| A — design | This design, audit, reproducible checker probes, roadmap handoff | Design is fixed; not a release PASS |
| B — checker correctness | V1-01 normalizer/CLI fixes and mutation-sensitive regressions | Every reproduced checker gap closed; historical hashes unchanged |
| C — public freeze | V1-02/03 explicit surfaces, outputs/errors/SDK fixtures, inventory v2 and compatibility policy | Stable allowlist complete; no unexplained baseline changes |
| D — release preparation | V1-04/05 versioned support semantics, exact artifact identity, packaging and durable evidence | Six required CI lanes complete and green; clean installation and migration checks |
| E — live qualification | Supported final-artifact baseline and negative/scratch cases | Fresh positive/refusal/cancel flows twice, targeted permission refusal, honest matrix |
| F — release decision | Review blockers, limitations, evidence and exact artifact/source identity | Explicit owner publication approval; no queued/failed required CI or open blocker |

Use 0.17.x for corrective work until candidate preparation is explicitly begun;
a 1.0.0 release-candidate label is not stability or publication evidence. Do not
implement unrelated features between freeze and qualification. A discovered
authority, evidence-loss, replay, migration, recovery or contract-checker defect
returns to the relevant corrective gate. It cannot be waived as documentation.

Final-head CI must finish successfully before merging an implementation or
release PR. If head/base changes the tested source tree, rerun applicable checks.
If the packaged build changes, do not reuse old live results as final-artifact
evidence. Documentation-only evidence additions must identify both the tested
source/artifacts and their own record revision without pretending they are the
same commit. No automatic merge-on-queued-CI, tag creation, publication or owner
runtime upgrade is part of this design task.

## 8. External contract references

[Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html) defines the public
API/versioning distinction. [JSON Schema objects](https://json-schema.org/understanding-json-schema/reference/object)
and [annotations](https://json-schema.org/understanding-json-schema/reference/annotations)
explain why named property maps and literal data are not annotation positions.
The qualified form contract remains [MCP 2025-06-18 elicitation](https://modelcontextprotocol.io/specification/2025-06-18/client/elicitation).
The existence of [MCP 2026-07-28](https://modelcontextprotocol.io/specification/2026-07-28)
does not expand this kernel's negotiated/qualified protocol set.
