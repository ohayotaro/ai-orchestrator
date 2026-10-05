# v0.17 design audit — 2026-10-06 JST

## Verdict

The roadmap's Release Candidate Hardening direction is appropriate, but its
previous completion wording was too permissive: documenting a behavior cannot
waive an authority, data-loss, replay or recovery defect. The implementation
scope and measurable release gates are now fixed in
[RC_HARDENING.md](RC_HARDENING.md).

**Design finalized; fixes and v0.17 release qualification are not completed by
this audit.** The previous v0.15/v0.16 live PASS records remain evidence for the
cases they exercised. The additional cases below were not established by those
runs. Do not reinterpret an historical closure as universal defect-freedom.

## Audited source and method

The GitHub main head read for this audit was
`b2700fda59b56bad0ced555f3a6e3e7f9badc6b8`, package 0.16.0, tree
`e68437f29792ff3d600995aa149150d8832c7b2f`.
The code was inspected from the `tested-source` artifact of CI run
`37386044004`, artifact `11379265121`. Its ZIP SHA-256 was
`6c0dda9efb510ee9cd7cc5c40efd10c85b20068a789c32d954fbd7e7415758ea`.
Reconstructing its Git tree locally produced exactly the main tree above.

The audit used source review and four synthetic fixture probes. All mutations
were confined to temporary local audit repositories; the only reasoning call
used a deterministic in-process FakeAdapter. There were no external-provider
calls and no access or mutation to the owner's live E2E runtime. Repository
writes in this design change are documentation and an explicit audit reproducer,
not production implementation changes.

A targeted regression run against that unchanged baseline passed:

```text
python -m pytest -q \
  tests/test_v04_gates.py::test_cancellation_after_execution_prompt_blocks_authority \
  tests/test_v015_operational.py \
  tests/test_v016_exploration.py

43 passed
```

This was not a new full-suite, live-host, remote-provider or SIGKILL qualification.
The four probes expose cases not covered by those passing tests. The runnable
[baseline reproducer](audits/v017_baseline_probe.py) prints observations and does
not claim they are acceptable behavior. Run it with the repository's development
Python; it imports source from the checkout and touches only its temporary
fixtures. It intentionally requires the 0.16.0 baseline.

## Findings and dispositions

| ID | Evidence | Finding | Disposition |
| --- | --- | --- | --- |
| A-01 | Owner report + local reproduction + source | Cancellation is durable but invisible in task view, remains an active binding, can record a direct CLI approval, and duplicate requests add events | RC-01 mandatory lifecycle fix |
| A-02 | Local reproduction + source | First-reference metadata masks a conflicting IntakeState reference in doctor | RC-03 integrity blocker |
| A-03 | Local plan-only reproduction + source | Nested accepted learning metadata is loaded as context but omitted from retention roots | RC-03 data-loss blocker |
| A-04 | Local queue-only reproduction + source | Deleting terminal jobs erases request-ID deduplication; the same request becomes a new queued job | RC-04 replay/idempotency blocker |
| A-05 | Source inspection only | Restore/cleanup rely on sequential mutations, temporary rollback and late completion audit, without a persistent incomplete-operation barrier | RC-05 durable-interruption acceptance requirement |
| A-06 | Owner-reported live UI observations + source | Yes-first form presentation contributed to two unintended positive probe outcomes; no invalid wire answer was needed | RC-02 mandatory presentation hardening, not a claim of forged authority |
| A-07 | Roadmap/docs/CI review | No complete release contract inventory, exact qualified host matrix or mandatory final-head release gate was specified | RC-06/07 verification and freeze requirements |

### A-01 — Cancellation state must be observable and consistently enforced

Relevant baseline paths: `Store.request_cancel` and `active_task_ids` in
`src/ai_orchestrator/store.py`; `ApplicationService.task_view` and `check_run`
in `service.py`; `Engine.approve` / `run` in `engine.py`; HumanGate capture in
`human_gates.py`; the cancellation check in `workflow_runtime.py`.

The synthetic probe created an awaiting-approval task, recorded cancellation,
read the normal task view and tried the direct Engine approval entry point. It
observed:

```json
{
  "status": "awaiting_approval",
  "flag": true,
  "flag_visible_in_task_view": false,
  "still_active_binding": true,
  "direct_approval_recorded_after_cancel": true,
  "repeated_cancel_added_events": 1,
  "additional_provider_calls": 0
}
```

Do not overstate this finding: the existing HumanGate capture/resolve path
rejects cancellation, and its regression passed. The run loop checks cancellation
before its normal dispatch. The reproduced problem is inconsistent entry-point
behavior and incomplete lifecycle visibility, not demonstrated provider execution
after cancellation. Calling `run` merely to obtain a terminal display is not an
acceptable housekeeping design: it enters preflight and may fail for unrelated
profile/evidence reasons before the loop consumes the request.

Owner-reported follow-up for `v016-e2e-docstring-probe` recorded
`cancel_requested=1` and `cancel.requested` event `E-1748`, while status stayed
`awaiting_approval`. Only that row's cancellation column and the new event were
reported changed. This supersedes the earlier suggestion that ordinary cancel
would fully remove an unfinished binding. The task was **not reported terminal
cancelled**, and this audit did not finalize it or inspect the owner's machine.

RC-01 preserves cooperative cancel, adds an explicit safe operator-only
finalization path, makes duplicate requests idempotent, and closes the direct
approval inconsistency without repurposing provider-change binding cleanup.

### A-02 — Shared-path metadata disagreement is concealed

`operational._state_report` builds `artifacts_by_path` from task artifacts and
uses `setdefault` for intake/exploration references. The probe stored a valid
TaskState artifact and an IntakeState pointing to the same path with a different
expected SHA. Doctor returned integrity OK, while the normal artifact reader
using the IntakeState metadata rejected it:

```json
{
  "doctor_integrity_ok": true,
  "intake_artifact_reader_rejected": true
}
```

Sharing an artifact is legitimate; selecting one owner's metadata as the truth
is not. RC-03 must validate reference consistency before deduplicating file I/O,
retain legacy v1 compatibility and fail closed on contradictory expectations.

### A-03 — Recursive context versus shallow retention enumeration

`Project.load` recursively enumerates Markdown under accepted knowledge,
policies and skills. `operational._protected_evidence_ids` uses top-level
`directory.glob("*.md")`. The probe created valid typed learning metadata in
`knowledge/accepted/nested/P-nested.md`, referring to a real immutable artifact
not otherwise rooted by TaskState/IntakeState. Observed result:

```json
{
  "loaded_by_project": true,
  "protected_evidence_ids": 0,
  "referenced_artifact_listed_as_orphan": true,
  "cleanup_executed": false
}
```

No referenced artifact was actually deleted in this probe. The unsafe plan is
sufficient to demonstrate the missing root. The normal generated promotion path
is flat, but the project context loader accepts nested Markdown; the retention
contract must cover that accepted input universe too. The fix must share
recursive confined enumeration and also audit frozen historical evidence roots.
Until addressed, do not treat a production cleanup plan as a proof that all
accepted learning references have been protected.

### A-04 — Cleanup retires payload and request identity together

`JobQueue.existing` looks up request IDs only in `jobs`. `apply_retention`
deletes eligible terminal `jobs` and `job_events`. The probe terminalized one
synthetic ask job without a provider, applied cleanup, and re-enqueued exactly
the same request ID/action/arguments. Observed result:

```json
{
  "terminal_jobs_removed": 1,
  "existing_request_lost": true,
  "same_request_created_new_job": true,
  "new_job_status": "queued",
  "provider_dispatched": false
}
```

This is not a HumanGate bypass: write-task gates still exist, and the probe did
not run the new job. However, a managed worker could treat the same identifier
as new work, including paid ask/exploration reasoning. The RC contract therefore
separates payload retention from durable request receipts. It also qualifies
the history boundary for IDs already deleted by older software and for restoring
a backup that lacks later execution evidence; remote exactly-once is not claimed.

### A-05 — Caught-error rollback is not crash consistency

Source inspection of `restore_backup` found temporary rollback staging, a
sequence of removals/copies, an `except Exception` rollback, and maintenance
completion append outside that replacement block. `apply_retention` similarly
performs physical deletions before completion audit. No durable pending-operation
record is consulted at controller startup in this baseline.

This audit did not run process-kill or disk-failure experiments and does not
claim it observed a real mixed restore. RC-05 makes those experiments mandatory
and defines a fail-closed incomplete-maintenance barrier rather than expanding
the product into distributed transactions or automatic repair.

### A-06 — Default presentation and host attestation are different

The existing form advertises `enum=["yes","no"]` and requires the decision;
resolution already requires a correlated exact affirmative response. The owner
reported unintended Yes selections in two live probes; the later genuine No
probe is the rejection evidence. The backend cannot infer a different intention
from a valid Yes response, or infer a human click solely from its wire shape.

RC-02 selects No-first, keeps explicit affirmative wire validation, and avoids
an unqualified enum default on the current negotiated 2025-06-18 schema.
The MCP specification leaves interaction rendering to hosts. A future protocol's
schema features or the absence of one local settings hook do not establish
current-host compatibility or human-presence attestation.

## Final disposition and verification boundary

The final design adds seven workstreams with no automatic permission widening.
A-02/A-03/A-04 are not deferred as harmless documentation items. Cancellation
finalization is explicit and provider-free. Maintenance safety is established by
crash evidence, not a claim that SQLite alone coordinates every file. The jobs
receipt migration is deliberate, separately versioned and must precede freeze.

The host matrix remains conditional where positive interoperability is not
freshly established. No universal Codex/Antigravity defect or compatibility is
inferred from historical timeouts/cancel responses. Existing v0.16 live success
continues to support its specific tested host/provider configuration.

The design is ready for implementation under RC_HARDENING.md. No new package
version, runtime migration, cancellation finalization, physical cleanup, backup
restore, provider call, release tag or package publication was performed on the
owner's project by this audit.
