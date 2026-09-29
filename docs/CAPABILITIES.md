# Capability Registry and Provider Adapter v2

v0.5 separates **semantic capabilities** from provider names and from low-level
adapter/runtime features.

A semantic capability describes what a role needs to accomplish, for example:

- `repository_analysis`
- `planning`
- `code_edit`
- `test_authoring`
- `review`
- `supervision`
- `research`

The current built-in Claude and Codex adapters advertise the first six. Neither
advertises `research` because web/external research is deliberately disabled in
the current worker configuration.

Runtime adapter capabilities such as `read_files`, `write_files`,
`structured_output`, `fresh_session`, `shell` or `native_sandbox` remain
separate. A provider must satisfy both semantic and runtime requirements.

## Resolution policy

Resolution is deterministic and inspectable.

1. If a role has `provider:`, that fixed provider is the override.
2. Otherwise, a non-empty ordered `candidates:` list is tried in order.
3. Otherwise, providers are sorted by `priority` (lower first), then provider name.
4. The first provider satisfying semantic + runtime requirements is selected.
5. With `cross_provider_review: true`, reviewer resolution excludes the
   implementation provider family.

There is no automatic quality ranking, benchmark feedback loop or hidden
provider selection.

Example dynamic role:

```yaml
providers:
  reasoning:
    adapter: claude
    priority: 20
    capabilities: [repository_analysis, planning, code_edit, test_authoring, review, supervision]
  engineering:
    adapter: codex
    priority: 10
    capabilities: [repository_analysis, planning, code_edit, test_authoring, review, supervision]

roles:
  implementer:
    provider: null
    capabilities: [code_edit]
    candidates: [engineering, reasoning]
```

A fixed `provider` and `candidates` cannot be configured together.

## Provider Adapter v2

Adapters expose:

- `api_version = 2`
- provider family;
- runtime `capabilities`;
- semantic `semantic_capabilities`;
- existing doctor/execute behavior.

Provider configuration can restrict an adapter's semantic capability set with
`providers.<name>.capabilities`, but it cannot invent capabilities the v2
adapter does not advertise.

Legacy Adapter v1 remains supported only for an existing **fixed** role with no
new semantic declarations. Dynamic routing and explicit semantic requirements
require Adapter v2. This compatibility path is recorded as
`legacy_fixed_compat` provenance rather than represented as a v2 capability
attestation.

## Role and task requirements

Each role has controller defaults:

| Role | Base semantic requirements |
| --- | --- |
| supervisor | supervision, repository_analysis |
| planner | planning, repository_analysis |
| implementer | code_edit |
| reviewer | review, repository_analysis |

Profiles can add role-level requirements with `roles.<role>.capabilities`.

Natural-language Supervisor proposals can add task-level requirements for
planner/implementer/reviewer. Requirements can only narrow eligibility; they do
not grant tools, write paths, external effects or approval authority.

Manual task creation can add a requirement without changing TaskSpec v1:

```bash
orchestrator create --task-file task.yaml \
  --require implementer=test_authoring
```

Repeat `--require ROLE=CAPABILITY` as needed.

## Frozen task resolution and provenance

New tasks use TaskState schema version 3. Before the first billable provider
call, the controller resolves the required roles and persists:

- effective capability requirements;
- selected provider;
- adapter/family;
- adapter API version;
- offered semantic capabilities;
- resolution source (fixed/candidates/priority);
- candidates considered.

The resolution appears in task state, events, prompts and HumanGate previews.
Execution approval scopes bind it. A later adapter/configuration change that
materially changes the frozen resolution causes the task to fail closed instead
of silently switching providers.

Use:

```bash
orchestrator capabilities
orchestrator doctor
orchestrator status TASK_ID
```

The MCP `inspect_project` result also includes the registry, provider
descriptors and baseline role resolutions.

## Compatibility

Existing v0.4.x profile digests remain stable when new capability fields are
absent or at their empty/default values. Upgrading software alone does not
require re-trust.

Adding non-empty provider/role capabilities, candidates or non-default priority
is a real profile change and therefore requires normal inspection/re-trust.

Existing persisted TaskState v1/v2 records remain readable and keep their old
wire/result behavior. They are not retroactively assigned semantic requirements
or rerouted through the new dynamic resolver.

## Security boundary

Capabilities are routing constraints, not permissions.

They never bypass:

- HumanGate;
- registered validators;
- allowed_paths/write-set enforcement;
- protected paths;
- external-effect blocking;
- cross-provider review policy;
- task/profile/worktree scope checks.

A model may propose additional task requirements, but cannot name a provider,
change priorities, add capabilities to a provider or use requirements to weaken
authority boundaries.
