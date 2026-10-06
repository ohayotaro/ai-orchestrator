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
| Runtime SQLite `state.sqlite3` | user_version 0, 1, 2, 3 | 3 | versions outside this set fail closed |
| HumanGate SQLite `gates.sqlite3` | user_version 0, 1 | 1 | terminal gate history is never replayed |
| Jobs SQLite `jobs.sqlite3` | user_version 0, 1 | 1 | current-version read/open does not restamp the header |
| TaskState | 1-9 | 9 | v9 adds exploration provenance; pre-v9 serialized shapes remain unchanged |
| IntakeState | 1-6 | 6 | v6 adds exploration provenance; pre-v6 serialized shapes remain unchanged |
| HumanGate | 1 | 1 | unknown gate schema cannot be applied |
| Artifact metadata | 1-2 | 2 | v2 adds stable `id`, `owner_id`, and `created_at` |
| Runtime event envelope | 1 | 1 | SQLite sequence yields stable `event_id`; payload stays unchanged |
| Usage evidence | 1 | 1 | missing telemetry remains unknown/unsupported |
| Budget evidence | 1 | 1 | no policy or limit is inferred during migration |
| Provider provenance | 1 | 1 | append-only, content-free dispatch evidence |
| Project Learning candidate | 1-2 | 2 | v1 manual proposals remain readable; v2 adds typed evidence/support/provenance |
| Context influence | 1 | 1 | frozen selected-context provenance; unknown versions fail closed |
| Recovery evidence | legacy unversioned v0, 1 | 1 | v0.11 recovery JSON is exposed as v1 in memory only |
| Backup manifest | 1 | 1 | v0.15 archive inventory/scope; hashes and sizes are verified before restore |
| Maintenance event | 1 | 1 | operator restore/cleanup JSONL provenance; not execution authority |
| Retention plan | 1 | 1 | read-only physical-cleanup scope; exact digest required to apply |

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

Before the first upgrade from a pre-v0.15 installation, stop active
controllers/workers and copy the complete `.orchestrator/` control/runtime
state. Once v0.15 is installed, prefer a verified full backup:

```bash
orchestrator --project "$PROJECT" backup create --mode full --output "$BACKUP"
orchestrator backup inspect "$BACKUP"
```

Upgrade the checkout/package, run the offline suite, then run `doctor` and
inspect existing tasks/intakes/gates before resuming work.

v0.15 does not change runtime/HumanGate/jobs SQLite user versions and does not
bump TaskState or IntakeState. TaskState v1-v8 and IntakeState v1-v5 keep their
existing read semantics; no row is rewritten merely because v0.15 operational
diagnostics inspected it. Existing v0.11 recovery artifacts remain hash-verified
and presented through the same in-memory schema-v1 compatibility view.

Backup manifest v1, maintenance event v1 and retention plan v1 are separate
operational contracts. They do not alter TaskState approval scope, profile
fingerprints or normal execution authority. A runtime-only restore never replaces
config/policy/skill/accepted-context authority; a full restore may restore those
files and its archived `trusted_profile` binding only after the explicit full
authority-restore acknowledgement.

If any report shows an unsupported version, do not edit the version number by
hand. Use the software version that created the state, restore a verified
matching backup, or add an explicit reviewed migration in a newer release.

## Downgrade boundary

An in-place downgrade is unsupported whenever the target executable does not
recognize the database/contract versions present. Restoring only SQLite without its artifact files (or only artifacts without
SQLite) is not a valid rollback; runtime state is one evidence set. Use the
v0.15 verified backup/restore contract or restore the complete pre-upgrade
control/runtime backup together with the matching executable/configuration.


## v0.16 exploration persistence

Runtime SQLite user_version 3 adds `explorations(id,data)` and preserves all
existing rows/events/approvals/trust metadata. Read-only operational diagnostics
accept a supported v2 DB with no exploration table without creating it. Store
opening performs the explicit v2 -> v3 schema upgrade; future versions fail closed.

ExplorationState, exploration_turn and exploration_transition are schema v1.
New TaskState v9 / IntakeState v6 carry typed ExplorationProvenance. A serializer
omits the new field for old TaskState/IntakeState versions; this preserves
historical Project Learning task/intake digests rather than introducing `null`.

Exploration queue actions use Job schema v2; normal ask/run jobs remain v1.
The jobs SQLite layout/user_version 1 and HumanGate schema/layout are unchanged.
Exploration artifacts are immutable and retained even after abandonment. Reads
never resume an interrupted session. See [Exploration](EXPLORATION.md).


## v0.17 candidate additions

Jobs SQLite readable versions are 0/1/2 and the write version is 2. Migration
creates the compact `request_receipts` table transactionally; a current DB2 missing
that table is an error, not permission to silently reset request history. Receipt
creation and terminal job/event removal are atomic. Receipts survive cleanup and
merge compatibly on restore; unavailable earlier/remote history is not invented.

Runtime state stays3, HumanGate DB stays1, TaskState stays9, IntakeState stays6 and
Exploration stays1. Supported historical samples retain baseline canonical hashes.
Cancellation view1, request receipt1 and maintenance intent1 are independent
contracts in the packaged `assets/contracts.json` inventory, available through
`orchestrator contracts`. Unknown versions fail closed. New views do not inject
fields into historical TaskState/IntakeState dumps.

The controller-only runtime maintenance journal is excluded from archive members
and normal retention/replacement. Incomplete intent/recovery material remains
persistent and blocks new work until explicitly reconciled or recovered. This
journal is not canonical project authority and does not change profile trust.
See [RC operations](RC_OPERATIONS.md) and [verification](RC_VERIFICATION.md).
