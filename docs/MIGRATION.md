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
