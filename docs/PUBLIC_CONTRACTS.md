# Public contracts — v1 target

The v1 target surface is explicitly listed in the packaged
`assets/public-surface.json`. Version 0.17.2 is preparation, not a stable-release
or live-qualification declaration. The normative boundary is
[V1_STABLE_CONTROL_PLANE.md](V1_STABLE_CONTROL_PLANE.md).

## Inventory and independent comparison

`orchestrator contracts` returns inventory format **2**, canonicalizer
`json-schema-positions-v2`, the package and target versions, public data model
hashes, MCP input/response/error references, CLI parser descriptors, SDK
signatures and behavior/version policy. The inventory digest identifies that
whole inventory. Publication approval is not a mutable flag inside the package.

Schema annotation keys are removed only at schema positions. Named properties,
definitions and literal values under `const`, `enum`, `default`, or an unknown
extension keep every key. Supported Pydantic free-mapping representation
normalization is narrowly applied. The normalizer does not touch TaskState,
IntakeState, artifact, approval or evidence serialization/hashes.

CLI descriptors cover the complete root-to-leaf parser path, inherited options,
actions, defaults, constants, types, ordering, mutual exclusion and parsing
settings. Shared parser nodes have explicit path references, never lossy
last-writer-wins merging. Current-working-directory and package-version defaults
have symbolic representations instead of machine-specific values. A different
literal default still changes the contract.

From a source checkout with the package installed:

```bash
python tools/check_contracts.py
python tools/export_contract_schemas.py > public-schemas.json
```

The first command compares the generated inventory with both the packaged
snapshot and the independent reviewed `tests/fixtures/v1/stable-baseline.json`.
CI does not regenerate either expected file. Mutations exercise the comparator
and real request/response validation. The exporter emits complete model, MCP
input and response schemas whose normalized hashes appear in the inventory.

The previous v0.17 inventory is retained unchanged in
`tests/fixtures/v1/contracts-v017-v1.json`; it is not upgraded in place.
Historical Task/Intake/Artifact fixtures remain unchanged and independently
validate old serialized hashes.

## Public does not mean every Python helper

The 78 explicitly enumerated model records promise documented data semantics,
not supported imports of Engine, Store or other internal helpers. The SDK import
allowlist separately identifies `RunRequest`, adapter protocol, failure type,
optional runtime/usage descriptors, conformance and diagnostic helpers, and the
configuration/contract types required by those signatures. SDK v1 / adapter API
v2, exact trusted plugin pins and optional-descriptor negotiation are preserved.

MCP and CLI input and result contracts are bidirectional. The exported schemas
include success, refusals and existing classified errors; test-time wrappers
validate actual service/CLI results throughout the existing regression suite.
Transport tests separately verify discovery, annotations, protocol-specific
`structuredContent`, JSON-RPC errors and tool-error envelopes. These wrappers
are tests, not new runtime validation/authorization behavior.

Operation-specific report subobjects intentionally permit documented dynamic
entries such as provider diagnostics and event payloads. That is not a promise
that all such text is a stable machine interface. English error prose and help
layout remain unstable; structured classifications, authority and replay rules
are not. `wait_job` cancellation terminates a wait, not the durable job.

## Compatibility

Package SemVer begins at 1.0.0. Compatible fixes are patch releases, compatible
additions/deprecations are minor releases, and incompatible stable changes
require a major release. Deprecation lasts at least one documented minor release
before removal in a major release. Rejecting previously invalid authority is a
safety correction, not permission to break valid documented inputs silently.

Package, inventory, protocol, SDK and persisted schema versions are independent.
TaskState writer 9/readers 1–9, IntakeState writer 6/readers 1–6, Artifact writer
2/readers 1–2, Job writer 2/readers 1–2, Exploration/Workflow 1 and runtime/gate/
jobs SQLite **3/1/2** remain unchanged. The complete persistence report remains
normative for other supported readers. A database schema bump is not part of
0.17.2. Readers promised by 1.0 remain supported throughout 1.x.

Strict consumers make even an added field potentially incompatible. Unknown
versions fail closed. Current-version reads do not restamp history. Upgrade and
rollback require matching software and verified backups; never edit a PRAGMA
marker or fabricate receipts. See [migration](MIGRATION.md),
[persistence](PERSISTENCE.md) and [recovery](RECOVERY.md).
