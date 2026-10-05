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

Provider-adapter HumanGate changes may now produce a temporarily same-family
profile with no model differentiation. This is intentional: adapter changes
reset vendor-specific model/effort fields, and review independence is enforced
later at task preflight after task/node runtime overrides have resolved.

New intakes use schema version 3 when created by the upgraded Supervisor and may
record `supervisor_runtime_override`, exact Supervisor provider resolution,
Model Variant Resolution and content-free dispatch/workspace provenance. Existing
schema-v1/v2 intake artifacts remain verified with their historical shape; no
database migration or rewrite is required.

No TaskState schema bump is required for task dispatch provenance. It is stored as
ordinary immutable `provider_provenance` artifacts and is available through the
existing `get_artifact` interface.

Supervisor, Planner and Reviewer now execute in disposable manifest-backed
workspaces that omit `.orchestrator` and ignored ambient files. Provider code
that incorrectly depended on reading controller runtime/task files will fail and
must use the supplied prompt/context instead.


## v0.9.1 to v0.9.2

No database migration or profile re-trust is required solely for the software
upgrade. Existing provider bindings remain unchanged.

The package now reports provider-role execution compatibility separately from
capability/provider resolution. AGY Supervisor, Planner and Reviewer bindings
report `conditional_native_permissions`: they remain routable and may work when
the operator's AGY native scoped permission policy is sufficient, but
Orchestrator does not modify or attest that provider-native policy.

A permission denial still fails closed. The portable Skill no longer retries
automatically by rewriting the task with provider-specific shell/tool
prohibitions. Adjust AGY native scoped permissions outside Orchestrator if
desired, then create a fresh intake. `--dangerously-skip-permissions` remains a
separate task/attempt-scoped high-risk authority and is not a read-only intake
workaround.

Re-export the packaged Skill after upgrade so the host learns the conditional
compatibility and no-auto-retry contract. Plain `orchestrator serve` remains the
default single-terminal registration.

## v0.10.x to v0.11.0

Stop active controllers/workers and back up the complete
`.orchestrator/runtime/` directory before upgrading. Reinstall the package and
run the offline test suite as usual.

There is no TaskState or runtime-database schema migration in v0.11. TaskState
v1-v7 remains readable, SQLite `user_version=2` remains current, and completed
task/event/artifact history is not rewritten. An unchanged trusted profile does
not need re-trust solely because the package version changed.

Recovery evidence is new and intentionally cannot be synthesized for an old
interrupted execution. A task already left in `status=running` by v0.10 or
earlier lacks the v0.11 guarded/isolated root-snapshot checkpoint. It is therefore
classified `uncertain_effect`; operator recovery cleans disposable workspaces and
terminalizes it without replay or automatic root-worktree rollback. Do not edit
SQLite/events to add a fake checkpoint.

New v0.11 guarded/isolated writable attempts persist the checkpoint before
provider dispatch. Only when the root snapshot is unchanged and no durable
provider-dispatch/integration marker exists can `orchestrator recover` return a
task to `awaiting_approval`. Old execution and provider-permission approvals are
revoked atomically, so a new execution HumanGate is mandatory.

Re-export the packaged Skill after upgrading so single-terminal hosts understand
the read-only `get_task.recovery` diagnostics and do not try to replay an
interrupted task. See `docs/RECOVERY.md`.

## v0.11.0 to v0.12.0

Stop active controllers/workers and back up the complete
`.orchestrator/runtime/` directory before upgrading. Reinstall v0.12 and run
the offline suite before resuming work.

v0.12 keeps the runtime database at SQLite `user_version=2` and the HumanGate
database at `user_version=1`; there is no mandatory in-place database rewrite.
Persisted TaskState v1-v7, IntakeState v1-v4, HumanGate v1 and legacy Artifact v1
metadata remain readable. Merely reading them does not rewrite their JSON rows or
artifact files and does not require profile re-trust.

New controller-written Artifact metadata uses schema v2 and records a stable
artifact ID, owner ID and creation timestamp in addition to kind/path/hash/attempt.
Existing Artifact v1 values embedded in old TaskState/IntakeState rows remain
valid. Runtime event rows are not rewritten; the reader exposes an additive
schema-v1 event envelope with a stable ID derived from the SQLite sequence.

New recovery evidence is written with `schema_version=1`. v0.11 recovery
artifacts did not carry that field. v0.12 first verifies the immutable artifact
hash and then exposes such legacy recovery evidence through an in-memory
schema-v1 compatibility view. The artifact bytes and stored hash are unchanged,
so historical recovery proof is not manufactured or rewritten.

Unknown, malformed or non-integer persisted schema versions fail closed before
the kernel interprets authority/effects. Do not hand-edit a version number to
force compatibility. Use `orchestrator persistence` or
`inspect_project.persistence_compatibility` to inspect the supported matrix.

There is no supported lossy in-place downgrade. If an older executable cannot
read state produced after upgrade, stop controllers and restore the complete
pre-upgrade runtime backup together with the matching older executable and
configuration. Restoring SQLite without its runtime artifact files is not a
valid downgrade.



## v0.12.2 to v0.13.0

Stop active controllers/workers and back up the complete runtime before upgrade
as usual. v0.13 does not change runtime/HumanGate/jobs SQLite user versions and
does not require a TaskState or IntakeState schema bump. Historical state and
artifacts remain under the v0.12 compatibility rules.

An unchanged project requires no profile re-trust solely because the package was
upgraded. The new empty `provider_plugins` field is omitted from effective
profile fingerprints, preserving historical trusted digests.

Installing a third-party provider distribution alone is inert. To enable it,
add an exact `provider_plugins` pin to project configuration, inspect the
resulting profile, and explicitly trust the new digest. The pin contains adapter
ID, distribution, version and entry-point target. On the next controller start,
the plugin is loaded only if installed metadata matches that trusted pin and the
adapter passes Provider SDK/API conformance.

Changing/upgrading the pinned distribution version or entry-point changes project
authority and requires a new profile digest/trust cycle. If installed package
metadata drifts without a matching trusted pin update, the adapter is excluded
and provider resolution fails closed; there is no implicit fallback. A configured
external plugin that collides with a built-in adapter ID also makes that adapter
ID unavailable until the ambiguity is removed.

After upgrading, re-export the packaged Agent Skill so connected hosts receive
the v0.13 provider-plugin authority guidance. Use `orchestrator
provider-plugins` and `orchestrator doctor` before selecting a newly enabled
external adapter.


## v0.13.0 to v0.14.0

Stop active controllers/workers and back up the complete runtime plus project
authority files before upgrading. Reinstall v0.14 and re-export the packaged
Skill.

There is no SQLite user-version migration in v0.14. Runtime state remains
`user_version=2`, HumanGate remains `1`, and jobs remains `1`. Historical
TaskState v1-v7 and IntakeState v1-v4 rows stay readable without rewrite. Newly
created tasks use TaskState v8 and new intakes use IntakeState v5 so they can
freeze deterministic `context_influence` provenance.

An unchanged project does not require re-trust solely for installing v0.14.
Candidate JSON under `.orchestrator/knowledge/candidates/` is inactive and is
not part of the effective profile fingerprint. Automatic or manual distillation
may therefore create/update non-authoritative candidate files without changing
project trust.

Promotion is different: accepted knowledge/policy/skill Markdown is active
project context. Promoting a candidate changes the effective profile digest and
requires normal explicit operator inspection/re-trust before new work can run.
Schema-v2 promotion first resolves and hash-verifies the candidate's typed
controller evidence. A workflow recommendation candidate does not install a
workflow; reusable workflow authority still uses `workflow-save`.

v0.14 separates the accepted-context universe from prompt injection. Projects may
retain up to 4 MiB / 2048 active Markdown items, while each new intake/task binds
a deterministic selected subset (24 KiB context budget inside the existing
64 KiB complete-prompt ceiling). Existing pre-v0.14 persisted tasks/intakes keep
their historical context behavior; they are not rewritten to manufacture an
influence manifest.

Rejected schema-v2 candidates with identical evidence remain suppressed.
Materially new evidence creates a new stable candidate identity and may link it
as superseding the prior one. Accepted contradictory/superseded learning remains
durable but is excluded from automatic selected context until explicitly
resolved.

After upgrade, run:

```bash
orchestrator --project "$PROJECT" learning report
orchestrator --project "$PROJECT" persistence
```

Then re-export the packaged Skill so MCP clients understand the new read-only
Project Learning inspection surfaces and the operator-only promotion boundary.

## v0.14.1 to v0.15.0

Stop active controllers/workers before upgrading. Because pre-v0.15 installations
do not yet have the versioned backup command, take a complete copy of
`.orchestrator/` (not only runtime) before replacing the package. This preserves
both controller evidence and project authority.

v0.15 does not change the SQLite user versions:

- runtime `state.sqlite3`: 2;
- HumanGate `gates.sqlite3`: 1;
- jobs `jobs.sqlite3`: 1.

It also does not bump TaskState v8, IntakeState v5, Artifact v2, Project Learning
candidate v2 or ContextInfluence v1. Existing bytes remain readable without an
upgrade rewrite.

An unchanged project does not require re-trust solely because v0.15 is installed.
The new maintenance audit log lives under `.orchestrator/runtime/` and is not
part of the project profile fingerprint. Backup/retention manifests are
operator-side operational contracts, not profile authority.

After installing v0.15, verify the installation and accumulated state:

```bash
orchestrator --project "$PROJECT" doctor
orchestrator --project "$PROJECT" persistence
orchestrator --project "$PROJECT" learning report
```

For subsequent backups prefer the versioned operator flow:

```bash
orchestrator --project "$PROJECT" backup create \
  --mode full --output "$HOME/backups/project-full.zip"
orchestrator backup inspect "$HOME/backups/project-full.zip"
```

Runtime-only backup/restore preserves durable runtime evidence but never replaces
current config/policies/skills/accepted knowledge. `retrust_required` reflects
the actual restored single `trusted_profile` binding and is true whenever that
binding does not equal the current project digest.

Full restore is intentionally stronger: it can restore project authority and the
single archived `trusted_profile` binding. It therefore requires an exact
verified backup scope, a quiescent project, `--replace`,
`--ack-authority-restore` and an operator actor string. Replacing unreadable
current runtime or malformed current project authority additionally requires
`--ack-unreadable-current-state`. It is not an automatic migration step.

Physical retention is also opt-in. `retention` first returns an exact read-only
plan/scope; `cleanup` applies only the same recomputed plan. Canonical
task/intake/runtime-event/HumanGate history, TaskState-referenced artifacts and
typed Project Learning evidence roots are not garbage-collected by v0.15
cleanup. Legacy/untyped learning evidence disables orphan-artifact collection
rather than inferring an unsafe identity mapping.

Re-export the packaged Agent Skill after upgrade so connected hosts learn that
operational diagnostics are inspectable but backup/restore/cleanup remain
operator-only.



## v0.15.1 to v0.16.0

Stop MCP servers/controllers and workers before upgrading. Preserve a verified
full `.orchestrator/` backup using v0.15.1 first; keep the project worktree and
Git state backed up separately. Do not use a running old MCP process with a new
editable-installed CLI when verifying the upgrade.

v0.16 adds runtime SQLite user_version 3 (`explorations` table), TaskState v9,
IntakeState v6 and exploration Job v2. Existing TaskState v1-v8, IntakeState v1-v5,
ordinary Job v1, gates and artifact bytes remain readable. Legacy serialized
state shapes do not gain an `exploration: null` field, preserving their evidence
hashes. The profile fingerprint and trust are unchanged by installing the code.

The gate/jobs database versions stay 1. After the runtime schema is upgraded,
v0.15.1 will fail closed on that DB. Downgrade by restoring the complete retained
pre-upgrade backup with its matching software; never lower PRAGMA user_version
or strip state fields manually.

After reinstalling, re-export both host Skills as applicable:

```bash
ORCH="$HOME/ai-orchestrator/.venv/bin/orchestrator"
"$ORCH" skill --output "$HOME/.claude/skills/ai-orchestrator/SKILL.md" --replace
"$ORCH" skill --output "$HOME/.agents/skills/ai-orchestrator/SKILL.md" --replace
```

Restart/reload the connected hosts/MCP servers and verify `orchestrator --version`,
`orchestrator persistence`, `doctor` and MCP `inspect_project`. An unchanged
profile does not need a new trust grant. New exploration work remains
non-authoritative until an explicit proposal and the existing Start HumanGate.
