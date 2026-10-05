# Persistence, Contract Versions and Migration (v0.12)

v0.12 makes persistence compatibility an explicit control-plane contract. The
goal is not to rewrite old state into a cosmetically current shape. The goal is
to preserve the authority and evidence semantics that were actually persisted,
while refusing to guess when a future or malformed version is encountered.

## Invariants

1. **Reads do not rewrite persisted state.** Loading an older TaskState,
   IntakeState, HumanGate, event or artifact never upgrades the stored bytes.
   Opening an already-current runtime/HumanGate/jobs SQLite database also does
   not restamp the same `user_version`; version writes occur only when an actual
   supported database-version migration is required.
2. **Unknown versions fail closed before mutation.** A future
   `schema_version` or SQLite `user_version` is an inspection error, not a
   request to coerce fields into the current model.
3. **Compatibility is semantic, not merely syntactic.** Defaults may be supplied
   only where the older contract already defined the absence of a field as
   having that meaning. New authority must never be inferred from a missing old
   field.
4. **Artifact integrity is checked before read migration.** Compatibility views
   are built only after the immutable artifact hash matches the stored metadata.
5. **Downgrade is backup/restore, not lossy conversion.** When an older
   executable cannot read a newer database or contract, restore the complete
   runtime backup taken before upgrade.

## Supported persisted contracts

| Contract | Readable | New writes | Rule |
| --- | --- | --- | --- |
| Runtime SQLite `state.sqlite3` | user_version 0, 1, 2 | 2 | versions outside this set fail closed |
| HumanGate SQLite `gates.sqlite3` | user_version 0, 1 | 1 | terminal gate history is never replayed |
| Jobs SQLite `jobs.sqlite3` | user_version 0, 1 | 1 | current-version read/open does not restamp the header |
| TaskState | 1-8 | 8 | v8 adds frozen Project Learning context influence; older rows are not rewritten |
| IntakeState | 1-5 | 5 | v5 adds intake context influence; older rows remain unchanged |
| HumanGate | 1 | 1 | unknown gate schema cannot be applied |
| Artifact metadata | 1-2 | 2 | v2 adds stable `id`, `owner_id`, and `created_at` |
| Runtime event envelope | 1 | 1 | SQLite sequence yields stable `event_id`; payload stays unchanged |
| Usage evidence | 1 | 1 | missing telemetry remains unknown/unsupported |
| Budget evidence | 1 | 1 | no policy or limit is inferred during migration |
| Provider provenance | 1 | 1 | append-only, content-free dispatch evidence |
| Recovery evidence | legacy unversioned v0, 1 | 1 | v0.11 recovery JSON is exposed as v1 in memory only |

Workflow runtime state remains embedded in TaskState and continues to bind
Workflow Schema v1 digests/provenance. A migration must not recalculate a
workflow digest, provider resolution, model variant resolution, approval scope,
write set, usage value, budget decision or recovery classification merely to
make an old row look current.

## Versioning rules

A persisted contract version must change when a reader would otherwise need to
guess a material semantic difference: authority, approval scope, effect
ownership, provider/model identity, evidence interpretation, recovery safety or
another field that can change what the controller is allowed to do.

An additive field does not require rewriting old rows when its absence already
has a defined legacy meaning. The model may expose that default in a
compatibility view, but the stored `schema_version` and bytes remain the source
of truth.

New code may read every version explicitly listed above. It must reject:

- a non-integer `schema_version`;
- an unknown earlier or future version;
- malformed JSON or a non-object persisted contract;
- a known version whose fields do not validate under that version's retained
  compatibility model.

The error is diagnostic only. It must not grant approval, consume an intake,
transition a gate, modify the workspace or rewrite the bad row.

## Stable identity and provenance

New Artifact metadata uses schema v2. Every controller-written artifact has a
stable random artifact ID, the owning task/intake ID, its attempt/round,
creation timestamp, content hash, kind and confined path. Artifact schema v1
remains readable.

Runtime events are returned through envelope schema v1 with a stable
`event_id` derived from the SQLite sequence, the original task ID/kind/payload
and creation timestamp. Existing event rows do not need a database migration.

These identities are controller metadata. Model-produced artifact content
remains untrusted evidence and never becomes authorization.

## Upgrade procedure

Before upgrading, stop active controllers/workers and back up the complete
`.orchestrator/runtime/` directory. Upgrade the checkout/package, run the
offline suite, then inspect existing tasks/intakes/gates before resuming work.

v0.14 does not automatically rewrite TaskState v1-v7, IntakeState v1-v4,
HumanGate v1, runtime events or legacy Artifact v1 metadata. New v0.14 work
writes TaskState v8 / IntakeState v5 with deterministic Project Learning
`context_influence`; older state is never rewritten to manufacture that
provenance. Existing v0.11 recovery artifacts are hash-verified first and then
presented through an in-memory schema-v1 compatibility view.

If v0.12 reports an unsupported version, do not edit the version number by hand.
Use the software version that created the state, or add an explicit reviewed
migration in a newer release.

## Downgrade boundary

An in-place downgrade is unsupported whenever the target executable does not
recognize the database/contract versions present. Restoring only SQLite without
its artifact files (or only artifacts without SQLite) is not a valid rollback;
the runtime directory is one evidence set. Restore the complete pre-upgrade
backup together with the matching executable/configuration.
