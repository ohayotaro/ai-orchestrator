# Workflow Schema v1 and Sequential DAG Execution

v0.6 generalizes workflow topology while preserving the existing authority and
effect boundaries. The workflow graph says **what depends on what**; v0.5
capability resolution still decides **who** runs each agent node.

## Built-in build-review

Existing projects keep:

```yaml
workflow: build-review
```

No migration is required. Internally the controller compiles it to:

```text
plan (planner, read-only)
  |
implement (implementer, execution gate, task allowed_paths)
  |
validate (registered deterministic validators)
  |
review (independent reviewer)
  |
Human acceptance
```

For T0/advisory tasks only the read-only plan node is active. Write-only nodes
are skipped.

## Node schema

Workflow Schema v1 supports two node kinds:

- `agent`: planner, implementer or reviewer role;
- `validator`: executes the task's already-registered validators.

Agent nodes declare semantic capabilities in addition to the role's v0.5 base
requirements. They do not name a provider or concrete model.

Relevant fields:

```yaml
id: implement
kind: agent
role: implementer
depends_on: [analysis_a, analysis_b]
inputs:
  - artifact: analysis_a
    type: plan
  - artifact: analysis_b
    type: plan
outputs:
  - name: execute
    type: implementation
  - name: write_set
    type: write_set
capabilities: [test_authoring]
gate_before: execution
writes: task_allowed_paths
run_for: write
```

Supported artifact types are currently:

- `plan`
- `implementation`
- `write_set`
- `validation`
- `review`
- `json` (reserved for later/general data nodes; current agent roles use their
  role-specific structured output types)

Inputs name the expected type. The compiler verifies that an artifact exists,
its type matches and its producer is a dependency ancestor.

## DAG validation

Before any task can use a workflow, the controller validates:

- unique node IDs and artifact names;
- dependency existence;
- no self-dependencies or cycles;
- deterministic topological order;
- typed artifact producer/consumer compatibility;
- input ancestry;
- `independent_of` ancestry;
- advisory paths contain only read-only agent nodes;
- write paths contain a gated writable agent, validator and reviewer;
- with cross-provider review enabled, reviewers declare independence from all
  writable nodes;
- repair nodes exist and the repair target is downstream from a writable node.

Invalid graphs fail before provider work.

## Deterministic sequential scheduler

A DAG does not imply parallel execution in v0.6.

When multiple nodes are ready, the scheduler uses compiled topological order;
declaration order is the stable tie-breaker. Exactly one node is executed at a
time in the project workspace.

This makes DAG semantics/provenance testable without introducing same-worktree
write races. Isolated parallel execution belongs to v0.7.

## Typed artifact passing

A downstream agent receives only the artifacts declared in its `inputs`, plus
the existing task/project control context.

For example a branched workflow can run two read-only planner nodes:

```text
analysis_a ----\
               +--> implement --> validate --> review
analysis_b ----/
```

The implementer receives both typed plan artifacts. The reviewer can be given
validation and write-set evidence without receiving implementation transcripts
or unrelated planner artifacts.

Artifacts remain immutable/hash-verified through the existing Store.

## Capability resolution per node

Every active agent node is resolved independently through the v0.5 Capability
Resolver.

Effective requirements combine:

1. role base requirements;
2. profile role capabilities;
3. task/Supervisor role requirements;
4. workflow-node capabilities.

The selected Provider Adapter v2 resolution is frozen in that node's
`WorkflowNodeState`. A later capability/configuration change that cannot
reproduce the frozen resolution fails closed.

For built-in workflows with one node per role, the v0.5 role-level
`provider_resolutions` compatibility view remains available. Custom workflows
with multiple planner/reviewer nodes use per-node provenance as the canonical
record.

Model Variant Resolution remains the separate, deferred boundary documented in
`MODEL_VARIANTS.md`.

## HumanGate and write effects

The start HumanGate binds the selected workflow through the trusted profile.
When a writable node becomes ready, it becomes `workflow_current`; its provider
resolution, dependencies, node state and artifact hashes are included in the
execution approval scope.

A confirmed execution gate authorizes that exact node/scope, not every future
write node in a custom graph. A later writable node can therefore require another
execution confirmation.

`writes: task_allowed_paths` uses the existing kernel write-set enforcement.
Supervisor-created tasks have exact allowed paths. Legacy/manual tasks without an
allowed-path contract retain their historical behavior; downstream write-set
inputs may be optional for that compatibility path.

Acceptance is requested only after every active node succeeds. The final reviewed
workspace snapshot remains bound to acceptance.

## Repair

Workflow Schema v1 can specify one bounded repair pair:

```yaml
repair_from: implement
repair_on: review
```

If the matching reviewer requests changes, or a validator fails, the controller
increments the existing bounded attempt counter and resets only `repair_from`
and its downstream subgraph. Upstream analysis/plan nodes remain completed.

The writable node returns to its execution gate, producing a fresh approval
scope before the next attempt. Old artifacts remain immutable evidence; new
artifacts become the latest typed outputs.

This is bounded repair behavior, not an executable cycle in the DAG.

## Custom workflow configuration

Custom workflows live in the trusted project profile:

```yaml
workflow: branched-review

workflows:
  branched-review:
    schema_version: 1
    id: branched-review
    nodes:
      - id: analyze_a
        kind: agent
        role: planner
        run_for: all
        outputs:
          - {name: analysis_a, type: plan}

      - id: analyze_b
        kind: agent
        role: planner
        run_for: all
        outputs:
          - {name: analysis_b, type: plan}

      - id: implement
        kind: agent
        role: implementer
        run_for: write
        depends_on: [analyze_a, analyze_b]
        inputs:
          - {artifact: analysis_a, type: plan}
          - {artifact: analysis_b, type: plan}
        outputs:
          - {name: execute, type: implementation}
          - {name: write_set, type: write_set}
        gate_before: execution
        writes: task_allowed_paths

      - id: validate
        kind: validator
        run_for: write
        depends_on: [implement]
        inputs:
          - {artifact: execute, type: implementation}
          - {artifact: write_set, type: write_set}
        outputs:
          - {name: validation, type: validation}

      - id: review
        kind: agent
        role: reviewer
        run_for: write
        depends_on: [validate]
        independent_of: [implement]
        inputs:
          - {artifact: validation, type: validation}
          - {artifact: write_set, type: write_set}
        outputs:
          - {name: review, type: review}

    repair_from: implement
    repair_on: review
```

Changing custom workflow configuration changes the profile digest and therefore
requires the normal inspect/re-trust step.

## Inspection and provenance

Use:

```bash
orchestrator workflow
orchestrator status TASK_ID
orchestrator events --task-id TASK_ID
```

New TaskState schema v4 persists:

- workflow ID and digest;
- deterministic node order;
- current node;
- status/attempt/artifacts for every node;
- effective per-node capability requirements;
- frozen per-node provider resolution.

MCP `inspect_project` exposes the compiled workflow report. HumanGate previews
for v4 tasks include current workflow/node state and relevant typed evidence.

## Compatibility

- Persisted TaskState v1-v3 remains on the legacy sequential execution path.
- New tasks use schema v4.
- Empty `workflows` is removed from profile fingerprinting, so upgrading an
  unchanged `workflow: build-review` project does not require re-trust.
- The default build-review artifact names and role behavior remain compatible.
- Custom workflows are profile-controlled; models cannot silently install or
  switch them.

## Non-goals for v0.6

v0.6 does not add:

- parallel agent execution;
- multiple writable worktrees;
- automatic workflow generation;
- arbitrary model-authored code nodes;
- external-effect workflow nodes;
- model variant routing;
- hidden fallback around HumanGates.

Those remain later roadmap work.
