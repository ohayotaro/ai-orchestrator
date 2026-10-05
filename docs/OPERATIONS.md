# Operational Hardening

v0.15 adds explicit operational maintenance for long-lived trusted-local
projects. The goal is diagnosis and recoverability without turning corruption,
staleness or old evidence into an excuse for automatic repair.

The governing rule is:

> Diagnose automatically; repair only through an explicit operator action bound
> to the exact state being changed.

These commands are local operator CLI surfaces. They are intentionally not
agent-facing MCP mutation tools.

## Doctor and integrity diagnosis

Run:

```bash
orchestrator --project "$PROJECT" doctor
```

In addition to provider/plugin/validator probes, v0.15 reports read-only
operational checks for:

- runtime SQLite version and `PRAGMA quick_check` /
  `foreign_key_check`;
- versioned TaskState and IntakeState decoding;
- referenced artifact existence, SHA-256 and evidence schema validation;
- stale `running` jobs when no worker owns the worker lock;
- expired queued jobs;
- expired pending HumanGates;
- effect-uncertain `applying` HumanGates when no controller owns the project
  lock;
- active versus stale disposable worktree directories;
- the v0.15 maintenance audit log.

The runtime diagnostics open SQLite in read-only/query-only mode. They do not
rewrite old rows, normalize persisted state in place, expire gates, interrupt
jobs, remove workspaces or repair artifacts.

If `state.sqlite3` itself is structurally unreadable, the CLI returns the
runtime diagnosis without constructing the normal Engine/Store. Provider and
validator probing is skipped rather than allowing startup side effects to hide
the underlying state failure.

Typical guidance remains conservative:

- interrupted `running` task -> inspect `status` / recovery classification
  and use the existing explicit `recover` command only when appropriate;
- stale running job -> start an operator worker to classify it as interrupted;
  never replay it automatically;
- pending expired HumanGate -> it authorizes nothing;
- `applying` HumanGate without its controller -> effect-uncertain; never
  replay it;
- missing/corrupt referenced artifact or malformed persisted state -> do not
  edit SQLite or JSON by hand; restore a verified backup or investigate the
  underlying storage failure.

## Backup contracts

v0.15 defines backup manifest schema v1. Every archive contains
`manifest.json` with:

- backup mode;
- source kernel version;
- source profile digest;
- source trusted-profile binding, when present;
- exact file list, byte counts and SHA-256 values;
- explicit exclusions.

The archive scope is the deterministic digest of that manifest. Restore requires
the exact scope returned by inspection.

### Runtime-evidence backup

```bash
orchestrator --project "$PROJECT" backup create \
  --mode runtime \
  --output "$HOME/backups/project-runtime.zip"
```

Runtime mode includes durable controller evidence under
`.orchestrator/runtime/`, including canonical SQLite database snapshots and
artifact JSON. It does **not** include current project authority such as
`config.yaml`, policies, skills or accepted knowledge.

A runtime-only restore therefore never overwrites current project authority. If
the restored runtime was bound to a different profile digest, the result reports
`retrust_required=true`; it does not grant trust to the current profile.

### Full controller/authority backup

```bash
orchestrator --project "$PROJECT" backup create \
  --mode full \
  --output "$HOME/backups/project-full.zip"
```

Full mode snapshots the complete managed `.orchestrator/` tree except
disposable/ephemeral runtime material. This includes:

- `config.yaml`;
- policies;
- skills;
- accepted knowledge;
- Project Learning candidates;
- project workflow templates embedded in configuration;
- task/intake/event/approval/trust state;
- HumanGate and job ledgers;
- immutable runtime artifact evidence.

A full backup can therefore contain authority, including a trusted-profile
binding. Protect it accordingly.

### Snapshot details

Backup acquires both the worker lock and project lock. Because normal task
execution holds the project lock for its execution interval, a backup cannot
race a cooperating provider run.

SQLite databases are copied through SQLite's backup API. WAL content is folded
into the copied database; `-wal`, `-shm` and journal sidecars are not archived
as independent authority.

The following disposable state is excluded:

- `.orchestrator/runtime/worktrees/`;
- `workspace.lock`;
- `worker.lock`;
- SQLite WAL/SHM/journal sidecars.

Use `--replace` only when intentionally replacing an existing archive.

## Backup inspection

Inspection is independent of restore:

```bash
orchestrator backup inspect "$HOME/backups/project-full.zip"
```

It verifies:

- manifest/schema;
- safe relative paths;
- no duplicate or unmanifested archive entries;
- declared byte counts;
- per-file SHA-256;
- total size safety bounds;
- mode/path invariants.

The output contains the exact restore `scope`.

Inspection changes neither the project nor the archive.

## Restore

Restore is deliberately verbose and explicit:

```bash
orchestrator --project "$PROJECT" restore \
  "$HOME/backups/project-runtime.zip" \
  --scope "<scope-from-backup-inspect>" \
  --by "$USER" \
  --replace
```

A full restore additionally requires:

```text
--ack-authority-restore
```

because a full archive may reinstate configuration/context and the
trusted-profile binding recorded in that backup.

Restore rules:

1. the archive is fully verified before mutation;
2. the supplied scope must equal the current verified manifest digest;
3. the project must be quiescent: no running task, queued/running job or
   pending/applying HumanGate;
4. worker and project locks are held throughout the replacement;
5. current managed state is staged for rollback;
6. restored runtime databases and persisted state are structurally checked;
7. a full restore must reproduce the archived profile digest;
8. on success, a `restore` event is appended to
   `.orchestrator/runtime/maintenance.jsonl`.

If restore fails after replacement begins, the staged pre-restore managed state
is restored. The command does not reinterpret unknown schema versions or invent
missing authority.

Restore is not execution recovery. A backup that contains an interrupted
`running` task remains interrupted after restore and must still pass the normal
v0.11 conservative recovery classification.

## Physical retention and cleanup

Project Learning semantic consolidation in v0.14 did not delete historical
evidence. v0.15 adds a separate physical retention contract.

First produce a read-only plan:

```bash
orchestrator --project "$PROJECT" retention --days 30
```

or use an exact timestamp:

```bash
orchestrator --project "$PROJECT" retention \
  --before "2026-09-01T00:00:00+00:00"
```

The plan returns:

- normalized cutoff;
- disposable stale worktree roots;
- terminal job records older than the cutoff;
- orphan artifact JSON older than the cutoff;
- an exact `scope`.

Nothing is deleted by `retention`.

Apply exactly that plan with:

```bash
orchestrator --project "$PROJECT" cleanup \
  --before "<exact-cutoff-returned-by-retention>" \
  --scope "<exact-scope-returned-by-retention>" \
  --by "$USER"
```

The plan is recomputed under the worker/project locks. If anything changed, the
scope changes and cleanup fails. The operator must inspect a new plan.

### Retention roots that are never implicitly deleted

v0.15 cleanup retains:

- TaskState rows;
- IntakeState rows;
- runtime task/event history;
- HumanGate ledger/history;
- every artifact referenced by TaskState;
- evidence referenced by active accepted/promoted Project Learning context;
- evidence referenced by retained Project Learning candidates.

This means the historical support behind accepted context is not garbage
collected merely because it is old.

The initial v0.15 physical cleanup surface is deliberately narrow. It deletes
only:

- disposable worktree roots that are not owned by a running task and are older
  than the cutoff;
- terminal job rows and their job-event rows older than the cutoff;
- old runtime JSON files that are not referenced by canonical task state or
  retained Project Learning evidence.

Cleanup appends a `cleanup` maintenance event with the exact scope and removal
counts. It does not compact or rewrite canonical task/event history.

## Maintenance provenance

Successful `restore` and `cleanup` operations append bounded JSON-lines audit
events to:

```text
.orchestrator/runtime/maintenance.jsonl
```

Each event records:

- schema version;
- stable event ID;
- action;
- operator actor string;
- exact scope;
- UTC timestamp;
- bounded action-specific details.

The actor field is local audit metadata. As elsewhere in this trusted-local
system, it is not cryptographic identity attestation.

## Agent authority boundary

MCP `inspect_project` exposes read-only operational diagnostics and explicitly
reports that restore/cleanup are unavailable to the agent-facing mutation
surface.

v0.15 does not add MCP tools for:

- backup creation;
- restore;
- retention cleanup;
- database repair;
- arbitrary artifact deletion;
- trust restoration.

This is intentional. Operational repair and retention remain operator-owned
maintenance actions, separate from Start/Execution/Acceptance HumanGate
authority.

## Failure model and non-goals

v0.15 does not provide:

- automatic repair of corrupt SQLite or JSON;
- automatic replay of interrupted tasks/jobs/gates;
- automatic rollback of the project worktree;
- distributed transaction/remote object-store backup guarantees;
- provider-side exactly-once execution;
- hostile same-OS-user isolation;
- authenticated human identity.

The supported model remains trusted-local, fail-closed and provenance-first.
