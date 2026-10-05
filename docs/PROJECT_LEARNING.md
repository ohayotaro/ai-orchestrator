# Project Learning / Knowledge Distillation (v0.14)

v0.14 lets accumulated controller evidence improve future orchestration without
turning historical model output into implicit authority.

## Authority model

The lifecycle is deliberately split:

```text
durable evidence
  -> deterministic candidate
  -> operator inspection
  -> reject / revise / promote exact candidate
  -> accepted Markdown
  -> explicit profile re-trust
  -> bounded selected context for future work
```

A candidate does not change the effective profile fingerprint, provider routing,
permissions, validators, effects, allowed paths, model/effort, budgets, workflow
templates or project trust. Promotion writes active project context and therefore
does change the profile digest.

Post-acceptance distillation is best-effort. If it fails, the already accepted
task stays accepted.

## Evidence contract

Proposal schema v2 uses `EvidenceRef` values with:

- `source`: `task`, `intake`, `artifact` or `event`;
- stable controller ID;
- SHA-256/deterministic digest;
- optional owner/kind metadata.

Distillation uses task acceptance, write-set, validation, review, recovery,
provider provenance, usage and budget records. Promotion re-resolves every
schema-v2 reference. Artifact bytes are hash-verified before use; task/intake/event
envelopes are checked against the recorded deterministic digest.

This is integrity/provenance evidence, not semantic truth. A valid review may be
wrong and a passing validator proves only its configured check.

## Candidate contract

Candidates are JSON under
`.orchestrator/knowledge/candidates/`. Schema v2 records:

- observation vs recommendation;
- canonical key and stable evidence digest;
- independent task IDs and evidence count;
- validation/review corroboration counts;
- contradiction count;
- a bounded deterministic sample of typed evidence references;
- supersession and contradiction relationships.

For long-lived projects, Proposal v2 retains at most 32 typed evidence
references and 32 example task IDs in the candidate payload. The full recurrence
still affects the stable candidate identity and is preserved as
`evidence_count` / `independent_task_count`. This prevents candidate and
promoted Markdown from growing without bound while ensuring materially new
evidence changes identity. Promotion verifies every retained typed reference.

Repeated identical evidence produces the same candidate identity. Rejecting that
candidate suppresses it on later identical distillation. Materially new evidence
changes the identity and may create a new candidate that supersedes the earlier
one.

Current deterministic patterns can produce:

- `knowledge`: validated/reviewed path recurrence, review observations,
  provider provenance, validator/recovery history, usage telemetry status;
- `skill`: repeated accepted-review observations as reusable-guidance
  recommendations;
- `policy`: repeated budget-blocker patterns as explicit operator-review
  recommendations;
- `workflow`: repeated successful task-scoped workflow use as a recommendation
  to inspect the separate workflow-save path.

A workflow candidate never installs a workflow template.

## Operator commands

Read status:

```bash
orchestrator --project "$PROJECT" learning report
orchestrator --project "$PROJECT" learning context --query "update parser behavior"
```

Generate/re-run deterministic candidates:

```bash
orchestrator --project "$PROJECT" learning distill
```

Inspect an exact candidate and its scope:

```bash
orchestrator --project "$PROJECT" proposal P-...
```

Then choose one explicit governance action:

```bash
orchestrator --project "$PROJECT" promote P-... --scope SHA256 --by "$USER"
orchestrator --project "$PROJECT" proposal-reject P-... --scope SHA256 --by "$USER" --reason "..."
orchestrator --project "$PROJECT" proposal-revise P-... --scope SHA256 --by "$USER" --statement "..."
```

Promotion changes active context and requires normal profile inspection/re-trust.
Reject/revise do not grant execution authority. A revision creates a new
candidate and marks the source candidate rejected/superseded.

## Accepted universe vs selected context

`Project.load()` retains the accepted project-context universe from:

- `.orchestrator/policies/**/*.md`;
- `.orchestrator/skills/**/*.md`;
- `.orchestrator/knowledge/accepted/**/*.md`.

The universe is bounded to 4 MiB and 2048 Markdown items. It remains part of the
profile fingerprint.

For each new intake/task, v0.14 deterministically selects at most 24 KiB from
that universe. Selection scores policy before skill before knowledge and adds
lexical query relevance, with deterministic path ordering as the tie-break.
Duplicate content is collapsed. Learning items marked superseded, or accepted
positive/negative learning with the same canonical key, are retained on disk but
excluded from automatic injection.

The selector records `ContextInfluence` with:

- selector/query digest;
- selection budget and selected byte count;
- universe/excluded item counts;
- exact selected paths, hashes, byte sizes, kind and score;
- typed evidence references embedded in promoted schema-v2 learning.

New IntakeState v5 and TaskState v8 freeze that manifest. Task state also carries
a `context_influence` artifact. Planner/Implementer/Reviewer use the task's
frozen selection; they do not independently expand the universe.

## MCP boundary

Agents may use read-only:

- `inspect_project.project_learning`;
- `list_learning_candidates` (bounded to 200 summaries per response, with
  `total` / `truncated` metadata);
- `get_learning_candidate`;
- `preview_learning_context`;
- `get_task` / `get_artifact(kind=context_influence)`.

MCP does not expose candidate generation, promotion, rejection, revision or
project trust. Those remain operator actions.

## Compatibility and retention

v0.14 does not bump SQLite user versions. Historical TaskState v1-v7 and
IntakeState v1-v4 remain readable without rewrite; new state uses v8/v5.

Existing pre-v0.14 tasks have no manufactured influence manifest and retain their
historical compatibility behavior. Candidate files do not affect trust until
promotion writes active context.

v0.14 performs semantic consolidation (dedupe, supersession, contradiction
exclusion). It does not delete historical artifacts/tasks/events. Physical
retention, backup/restore and garbage collection remain v0.15 scope.
