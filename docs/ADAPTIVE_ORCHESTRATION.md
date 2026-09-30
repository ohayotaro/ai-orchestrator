# v0.8 adaptive orchestration

v0.8 separates **task structure** from **persistent project authority**. A user
can describe the desired outcome in natural language without selecting a vendor,
workflow ID, DAG shape or parallelism policy. The Supervisor may reuse trusted
workflow authority or propose a bounded task-scoped Workflow Schema v1 graph.

## User-facing flow

```text
natural-language task
  -> Supervisor identifies task/capabilities
  -> trusted workflow registry lookup
  -> trusted template if suitable
     OR task-scoped workflow proposal
  -> Start HumanGate displays task + exact DAG/effects
  -> existing capability/provider resolution
  -> execution HumanGate
  -> sequential/isolated-parallel execution as declared
  -> deterministic validation + independent review
  -> acceptance HumanGate
```

The default agent UX is therefore to omit `workflow_ref` unless the user
explicitly asks for a particular already-trusted template.

## Task-scoped workflow proposals

A Supervisor-authored workflow is not installed into
`.orchestrator/config.yaml`. It is stored in the intake artifact, included in
the intake confirmation scope and then embedded in TaskState v5 if the user
confirms Start. Reopening the controller recompiles that exact persisted spec and
verifies its ID/digest before execution continues.

The proposal may use only Workflow Schema v1 primitives already implemented by
the controller:

- planner, implementer and reviewer agent roles;
- registered validator nodes;
- typed artifact dependencies;
- existing semantic capabilities;
- execution gates and exact task allowed-path write authority;
- v0.7 isolated writers and bounded parallel scheduling when exact file
  ownership makes the split safe.

The controller rejects a proposed workflow when it collides with a trusted
workflow ID, sets template provenance/version itself, exceeds 16 nodes or the
configured model-call budget, requests unknown semantic capabilities, violates
Workflow Schema invariants, or gives an isolated writer ownership outside the
Supervisor-proposed task `allowed_paths`.

Advisory tasks do not author new workflows. They continue to use trusted
read-only authority.

## Authority boundary

A task-scoped DAG can decide **how already-authorized work is structured**. It
cannot expand what the project is allowed to do. In particular, it cannot add or
change:

- provider executables, vendor/model identities or adapter permissions;
- semantic capabilities absent from the controller registry;
- validator commands;
- project policy, protected paths, budgets or HumanGate requirements;
- external-effect authority;
- trust state.

Capability/provider resolution remains deterministic and operator-controlled.
Every active proposed agent node is resolved against the existing registry
before the Start proposal is shown. Cross-provider reviewer independence is
validated by the normal workflow compiler/policy.

## HumanGate and revision

The Start HumanGate shows whether the workflow came from trusted registry
authority or a task-scoped Supervisor proposal. For an adaptive proposal it
includes the exact compiled DAG, effect/write contracts and the statement that
the workflow is task-scoped only.

An unconfirmed proposal may be revised conversationally by creating a new intake
with `reply_to` set to the proposed intake. The Supervisor receives the prior
proposal as history. Once a revised proposal or clarification is successfully
created, the old proposal is marked `superseded`; its old scope/form can no
longer register work.

A confirmed task cannot have its embedded workflow rewritten in place. Create a
new intake/task if the structure must change after confirmation.

## Optional persistent template save

Evidence may suggest that a successful task-specific structure is worth reusing.
Persistence is deliberately outside the MCP agent authority. After the exact
adaptive task reaches final `succeeded` with a reviewed snapshot, an operator
may inspect a candidate:

```bash
orchestrator workflow-candidate I-... --as reusable-name
```

The candidate binds source intake/task, accepted reviewed snapshot, source
workflow digest, target template ID/version, current profile digest and whether
this is a replacement. Saving requires the exact candidate scope and an actor:

```bash
orchestrator workflow-save I-... --as reusable-name \
  --scope <exact-candidate-scope> --by "$USER"
```

For replacement of an existing project template, both commands require
`--replace`. The version increments and provenance records the parent semantic
digest.

Saving writes project configuration only after validating the complete future
Profile and compiled workflow. The persisted provenance records the source
accepted task, source workflow digest, reviewed snapshot and operator identity.
That configuration mutation changes project authority, so the previous profile
trust no longer matches. The operator must inspect and run normal `trust`
again before new orchestration work.

No MCP tool saves or trusts templates.

## Digests and compatibility

Workflow **semantic digests** intentionally omit template version/provenance so
execution identity depends on the graph rather than promotion metadata. The
project **profile digest**, by contrast, includes explicit non-default template
version/provenance because those are trusted project configuration.

Default v0.8 metadata (`template_version: 1`, null provenance) is excluded from
the effective profile fingerprint so an otherwise unchanged v0.7 project does
not require re-trust solely for the software upgrade. Existing trusted/manual
workflow tasks remain TaskState v4; only tasks carrying an embedded adaptive
workflow need TaskState v5.

## Limitations

v0.8 does not learn or install authority automatically. It does not rank
providers from historical performance, mutate cost/model policy, auto-save a
successful DAG, or resume ambiguous interrupted effects. Evidence-backed routing
metrics and stronger recovery belong to later milestones.
