# Migration and upgrade

## v0.1 -> v0.2

Stop active controllers. Back up each project's complete `.orchestrator/runtime/` directory while it is stopped, along with the tracked profile/policies/task specs. Do not delete or reinitialize an existing `.orchestrator/` directory to upgrade.

Update the orchestrator checkout and reinstall it using that checkout's Python 3.11+ virtualenv:

```bash
git pull --ff-only
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/orchestrator --version
.venv/bin/python -m pytest -q
```

The runtime database adds an intakes table and advances to version 2. Old task rows, event history and artifact bytes are not rewritten. The old executable will reject the upgraded database; there is no supported in-place downgrade. Restoring a backup requires matching runtime artifacts and the prior executable/configuration, not merely changing the reported package version.

Unchanged v0.1 profiles remain valid. Empty new validator env/generated-path defaults are omitted from effective fingerprints, and a missing supervisor role uses the planner binding without editing configuration. There is no reason to retrust an unchanged profile solely to change software version. Adding nonempty settings, a new role, or approved context still requires inspection/retrust and invalidates existing task bindings as before.

Existing tasks keep schema version 1 and legacy AgentResult wire outputs; accepted task artifacts remain readable. Newly created tasks use state schema version 2 and dedicated PlanResult, ImplementationResult and ReviewResult. Do not manually change stored task versions or edit SQLite to turn a failed task into a completed one.

## Remove fragile manual setup

The actual validator field is `argv`, not `command`. Registration now avoids manual YAML spelling mistakes:

```bash
orchestrator validator add pytest --replace -- .venv/bin/python -B -m pytest -q -p no:cacheprovider
orchestrator doctor --validators-only
orchestrator trust --by "$USER" --ack-local-execution
orchestrator validator check pytest
```

This assumes the target project's `.venv/bin/python` already exists and has pytest installed. The executable is resolved against the project root even when the controller uses another environment. An absolute interpreter path is also supported. Environment filtering never meant that relative executable paths were inherently invalid; the earlier E2E failure involved a missing target virtualenv. Preflight now makes that distinction before model calls.

The validator check runs executable test code and is not an implicit doctor dry run. Bytecode is disabled by default during controller validation; pytest caching is a separate user command option. Register only narrow generated-output directories when a test tool legitimately writes results. Do not use blanket ignore rules or broad allowances to suppress unknown changes.

## Natural-language usage on an existing project

Existing create/run/approve/accept commands remain. Use ask for a new task without writing YAML:

```bash
orchestrator ask "Add a subtract function and regression tests" --task-id subtract-v02
orchestrator intake '<intake-id>'
orchestrator start '<intake-id>' --scope '<intake_scope>' --by "$USER"
orchestrator approve subtract-v02 --interactive --by "$USER"
orchestrator run subtract-v02
# Only after inspecting the diff, validation and review:
orchestrator accept subtract-v02 --by "$USER"
```

Task proposal confirmation and execution approval are different gates. Start invokes planning by default and stops before writes. Use `--no-run` to register without planning. No command automatically trusts a profile, grants execution approval or accepts a result based on Supervisor text.

## Existing project templates, not predefined domains

The `claude-finance`, `claude-research` and `claude-fullstack` repositories remain unchanged. They are sources of practical patterns and migration cases, not complete domain specifications automatically imported by v0.2.

A finance-inspired project can bind planning/implementation to Claude and review to Codex, while user-defined validators check actual invariants/backtests. Live trading is not a supported execution path. A research project can retain project-specific citation/result-ledger rules and explicit validation without claiming the built-in build-review graph covers the entire scientific process. A fullstack project can bind Codex implementation with Claude review, or deliberately opt out of cross-family checking for a fresh same-family reviewer. Visual/browser acceptance and production deployment remain separate controls.

Migrate one small low-risk task in a disposable worktree. Audit every existing hook, permission restriction and approval requirement. A Markdown policy is not a replacement for a deterministic hook or OS control. Keep controls external or block migration when the alpha cannot enforce them. Extract reusable profile content only after repeated project experience; do not lower safeguards to make an example pass.

Automated imports, old runner-state migration, arbitrary research/deployment workflows and additional provider-native subagents are not included.


## v0.2 to v0.3

Stop all active controllers and back up the full runtime directory first. Pull
main and reinstall to refresh the 0.3.0 package metadata. Existing TaskSpec,
profile digests, completed task rows and approval scopes are not migrated or
rewritten. A separate jobs.sqlite3 appears when the MCP/job interfaces are used.
No queued work is automatically resumed during installation.

Install/export client skills and MCP configuration before creating scoped work.
Start the worker from a separate normal terminal; do not unset CLAUDECODE to nest
workers inside a conversational agent. Keep using direct ask/start/run if MCP is
not needed. See MCP.md for setup and the remaining explicit human gates.


## v0.4.1 to v0.5

Stop active workers and back up runtime state before upgrading. Reinstall the
package and run the test suite. Existing profile digests remain stable when the
new provider/role capability fields are absent or default/empty; no re-trust is
needed solely for the package update. Adding capabilities, candidates or provider
priority is an intentional profile change and requires inspection/re-trust.

Persisted TaskState v1/v2 remains readable. New tasks use state schema v3 to
freeze capability requirements and provider-resolution provenance. Existing tasks
are not silently rerouted. See CAPABILITIES.md.


## v0.5 to v0.6

Stop active workers and back up runtime state before upgrading. Existing projects
using `workflow: build-review` need no config migration and, because an empty
custom-workflow registry is excluded from the fingerprint, do not need re-trust
solely for this package upgrade.

New tasks use TaskState schema v4 and the compiled built-in workflow. Persisted
v1-v3 tasks remain readable/runnable through the legacy path. Adding or selecting
a custom `workflows:` definition is a real profile change and requires normal
inspection/re-trust.

Run `orchestrator workflow` after upgrade to inspect the compiled graph before
testing live E2E.


## v0.6.1 to v0.6.2

An unchanged profile does not require re-trust merely because the package now
advertises the built-in `branched-review` template. Built-in registry entries
are package authority; profile fingerprints remain based on project configuration
and accepted context.

Existing projects that already defined `branched-review` continue to use their
trusted project definition. To adopt the package template later, remove the
project definition only as an intentional profile change and re-trust normally.

New task-scoped workflow selection is persisted in intake/TaskState provenance;
older persisted TaskState v4 rows without a selection-source field remain
readable and use their frozen workflow ID/digest.


## v0.6.2 to v0.7

Stop active workers/controllers and back up runtime state before upgrading.
Existing shared workflows remain sequential. The new
`policy.max_parallel_workers` default is `1`, and default
`workspace: shared` / empty `write_paths` workflow fields are omitted from
effective profile/workflow fingerprints, so an otherwise unchanged v0.6.2
project does not require re-trust solely for the software upgrade.

Opting into writable isolation is a trusted authority change. Add
`workspace: isolated` and exact `write_paths` to writable implementer nodes,
ensure every owned file is also included in each task's exact `allowed_paths`,
and set `policy.max_parallel_workers` above one only after inspecting the
workflow. Those non-default changes alter the effective profile fingerprint and
require normal re-trust.

Isolated execution requires an existing Git commit. It uses disposable runtime
Git metadata and does not migrate TaskState or the runtime database schema; new
tasks continue to use TaskState v4. Interrupted parallel batches are never
replayed automatically. Use `recover` to clean stale runtime workspaces and
mark the task failed, then inspect the project worktree before creating a new
task.

Run the offline suite and inspect `orchestrator workflow --ref <id>` before a
live-provider smoke test. See PARALLEL_EXECUTION.md for ownership, integration,
cancellation and security boundaries.


## v0.7 to v0.8

Stop active workers/controllers and back up runtime state before upgrading.
Reinstall the package and run the offline suite. An unchanged v0.7 project does
not require re-trust solely for the software update: default workflow-template
metadata (`template_version: 1` and null provenance) is excluded from the
effective compatibility fingerprint.

Existing persisted TaskState v1-v4 rows remain readable. Existing manual tasks
and tasks using built-in/project-trusted workflows continue to be created as
TaskState v4. TaskState v5 is used only when a confirmed intake embeds a
Supervisor-authored task-scoped workflow.

No runtime database migration is required. Adaptive workflow content is persisted
inside intake/task state and immutable artifacts. It does not edit
`.orchestrator/config.yaml` and therefore does not change project trust.

If the operator later chooses to persist a successful adaptive workflow using
`workflow-save`, that is an intentional project-authority mutation. Inspect the
candidate scope and saved workflow/provenance, then run the normal `trust`
ceremony before queueing additional work. Do not treat successful execution as
implicit permission to save a template.

The packaged Agent Skill should be re-exported after upgrade so connected clients
learn the v0.8 default: omit workflow/provider choices unless the user explicitly
requests a trusted template, and let the Supervisor propose bounded task-scoped
structure when needed.


## v0.8 to v0.8.1

No persisted state or runtime database migration is required. Existing Claude
and Codex provider configurations keep the same behavior.

v0.8.1 adds the built-in `agy` adapter. Merely upgrading the package does not
modify a project profile or require re-trust. Replacing a configured provider
adapter (for example changing the engineering provider from `codex` to `agy`)
is an intentional profile authority change and requires normal inspection and
re-trust before new work can be queued.

Install and authenticate Antigravity CLI separately before selecting it. The
adapter probes `agy --version` and `agy --help` for required headless flags.
It does not auto-login, modify Antigravity settings, or use the
`--dangerously-skip-permissions` override.

After changing a provider, run `orchestrator doctor` and
`orchestrator capabilities` before live E2E. Existing tasks retain their frozen
provider resolution and should not be silently rerouted.


## v0.8.3 to v0.8.4

No runtime database or profile migration is required. Exact-scope Workflow
Schema write tasks gain stronger execution isolation automatically: shared
implementers run in temporary runtime worktrees and are integrated only after
provider result and ownership checks succeed.

This does not change the project profile fingerprint and does not require
re-trust solely for the software upgrade. Legacy/manual tasks without exact
`allowed_paths` retain previous shared-worktree semantics.

A failed task from v0.8.3 or earlier that may already have mutated the project
must not be replayed. Inspect/restore that project to the desired baseline first,
then create a fresh task after upgrading.


## v0.8.5 to v0.8.6

No runtime database migration or profile re-trust is required solely for the
software upgrade. Existing task rows load with an empty provider-permission grant
map.

Single-terminal mode gains bounded provider authority controls. A provider
adapter change performed through its HumanGate intentionally changes the project
profile and, within the same confirmed operation, records trust only for the
newly verified digest. Direct/manual profile edits continue to invalidate trust
normally.

Task-scoped AGY broad-permission grants are new task-state metadata. They are not
persistent profile settings and are never inferred for existing tasks. A task
must already be awaiting execution approval, the user must explicitly confirm
the provider-permission form, and a separate execution confirmation remains
required afterwards.


## v0.8.6 to v0.8.7

No database migration or profile re-trust is required solely for the upgrade.
Existing TaskState rows remain valid; the new `abandoned` status is used only by
an explicit binding-cleanup HumanGate. Existing intakes gain the optional
`withdrawn` terminal state through the same schema reader.

Provider-change preview now reports unfinished blockers structurally rather than
raising immediately. This does not weaken provider-change safety: the actual
provider-change HumanGate still refuses to prepare while blockers remain.

Binding cleanup is not rollback. Historical projects with unfinished tasks that
may already have modified files should inspect/retain those files separately;
cleanup only retires the orchestration binding so later authority changes can
proceed.


## v0.8.7 to v0.8.8

No database migration, profile change or re-trust is required. Existing events
are unchanged; new provider calls may append `provider.tool_telemetry` events.

Historical provider calls cannot be retroactively reconstructed because raw AGY
tool traces were intentionally not persisted. Re-run a safe E2E after upgrading
when tool-level provenance is needed.


## v0.8.8 to v0.8.9

No profile, task, event database or trust migration is required. HumanGate scope
semantics are unchanged. Only the client-facing confirmation message becomes
compact and operation-specific.

Large binding cleanups that previously fit one form may now need multiple
confirmations because v0.8.9 caps one cleanup form at 12 exact IDs to keep all
targets visible.


## v0.8.9 to v0.8.10

No database migration, profile re-trust or task migration is required solely for
the upgrade.

Single-slot provider change tools keep their existing schema and behavior.
Clients that want provider swaps or multiple simultaneous changes should use
`preview_provider_change_set` and `request_provider_change_set` rather than
issuing sequential single-slot changes. This avoids transient policy failures and
ensures the user approves the complete final provider mapping in one HumanGate.


## v0.8.10 to v0.9.0

No runtime database migration or automatic profile rewrite is required solely for
this upgrade. Existing persisted TaskState versions 1-5 remain readable; newly
created tasks use TaskState v6 and freeze model/effort/runtime-option provenance.

Existing trusted profiles keep their ordinary profile-digest semantics. A profile
that already sets provider `model` or `effort` now has those values resolved
through the adapter runtime-option contract before provider execution. Built-in
adapters use honest pass-through metadata when they cannot enumerate a complete
vendor catalog, so upgrading does not require pinning a kernel-owned model list.

New task-scoped runtime overrides are ephemeral task authority. They are persisted
in the task/intake state and HumanGate scope, not written back to project config.
Changing a persistent provider model/effort remains a normal profile-authority
change and requires the existing inspect/re-trust path.

Provider Adapter v2 implementations that do not yet implement
`describe_runtime_options` remain usable only when no explicit model/effort is
requested through the new resolver; their runtime-option status is reported as
unsupported rather than guessed. Adapter authors should implement the versioned
descriptor before advertising explicit model/effort selection.


## v0.9.0 to v0.9.1

No task/event database migration is required. Existing profile field
`cross_provider_review` remains valid and keeps its default. Its enforcement is
broadened: different provider families still qualify, while explicit unequal
provider-local model IDs can now establish review independence within one family.
If same-family implementation/review previously relied on null/default model
identity, configure explicit distinct model IDs or use different families.

Supervisor, Planner and Reviewer now execute in disposable manifest-backed
workspaces that omit `.orchestrator` and ignored ambient files. Provider code
that incorrectly depended on reading controller runtime/task files will fail and
must use the supplied prompt/context instead.
