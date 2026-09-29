# AI Orchestrator

Project-driven, provider-neutral orchestration for existing AI clients.
**v0.4.0 alpha** adds optional single-terminal host confirmations and automatic
separate workers. This remains a trusted-local application, not authenticated
human identity or an OS-isolated control plane.

```text
User <-> Claude Code / Codex + portable Skill
                    |
           MCP serve --single-terminal
                    |
       propose -> Supervisor -> task proposal
                    |
         host confirmation: start?
                    |
                 Planner
                    |
       host confirmation: execute this attempt?
                    |
       Implementer -> validators -> fresh Reviewer
                    |
         host confirmation: accept result?
                    |
                 succeeded
```

Workers run in separate managed processes, not in the conversational agent's
session. After initial setup and project trust, normal work can remain in the
same client terminal **when the client supports interactive form elicitation**.
Unsupported forms, No/cancel, expired dialogs and changed scopes never auto-approve.

## Important approval distinction

v0.4 uses MCP `elicitation/create`, not ordinary tool permission prompts,
`destructiveHint`, "always allow", an agent boolean or a chat "yes". The host
receives the server-built task/plan/evidence preview and returns an explicit form
response. Every successful response is bound to the session, operation, exact
state, current worktree and expiration, with a local audit record.

**The protocol does not attest that a human personally answered.** Clients or
Claude Code hooks can auto-answer elicitation. Enabling single-terminal mode
therefore explicitly trusts the local client's response channel. Use an
interactive client with approval automation disabled when personal confirmation
is required. No authenticated live v0.4 client test is claimed by the offline suite.
See [Single-terminal design and setup](docs/SINGLE_TERMINAL.md).

## Install / upgrade

Use Python 3.11+ on Linux/macOS. An old Python 3.9 virtualenv must be replaced,
not upgraded by installing a newer pip. Existing users should stop active workers
and back up each project's complete `.orchestrator/runtime/` before upgrading.

```bash
git pull --ff-only
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev,interop]'
.venv/bin/python -m pytest -q
.venv/bin/orchestrator --version  # 0.4.0
```

For a new checkout, first create a new environment with `python3.13 -m venv .venv`
(or Python 3.11/3.12). Install/authenticate Claude Code and Codex CLI separately.
No model name is fixed; configured CLI defaults apply unless the profile specifies
one. Additional provider adapters, arbitrary DAGs and parallel workspaces remain
outside this release.

## Opt in for the existing calculator fixture

Use a normal terminal for this one-time host setup. Do not reinitialize or reset
existing projects, tasks or uncommitted calculator changes.

```bash
ORCH=/Users/ohayotaro/ai-orchestrator/.venv/bin/orchestrator
PROJECT=/Users/ohayotaro/ai-orchestrator-e2e
```

Update your existing MCP entry so its arguments end in `serve --single-terminal`,
or remove/re-add only this server. For Claude Code (local project scope):

```bash
cd "$PROJECT"
claude mcp remove ai-orchestrator --scope local
claude mcp add --transport stdio --scope local ai-orchestrator -- \
  "$ORCH" --project "$PROJECT" serve --single-terminal
"$ORCH" skill --output "$HOME/.claude/skills/ai-orchestrator/SKILL.md" --replace
```

For Codex, update the existing registration:

```bash
codex mcp remove ai-orchestrator
codex mcp add ai-orchestrator -- \
  "$ORCH" --project "$PROJECT" serve --single-terminal
"$ORCH" skill --output "$HOME/.agents/skills/ai-orchestrator/SKILL.md" --replace
```

`skill --replace` makes an adjacent uniquely named backup before replacing a
regular file. It refuses symlinks and never changes client configuration itself.
Inspect registration scope before removing any existing server; do not remove an
unrelated server. Reload/restart the client as needed after configuration changes.

An unchanged profile needs no new trust grant. If configuration changed, inspect
it and explicitly retrust from the operator terminal. v0.4 does not grant trust
through MCP. A manual worker already running is reused; stop it before testing
that automatic startup works. Do not run a second manual worker.

## Ordinary use

Ask the connected client to use ai-orchestrator for a small change. It calls
`inspect_project` then `propose_task`. In opt-in mode, workers start automatically.
The three request tools present native host confirmations:

| Tool | What a confirmed response permits |
| --- | --- |
| `request_start` | Register the proposed task and queue planning only |
| `request_execution` | Authorize the exact implementation attempt and validators, then queue it |
| `request_acceptance` | Accept the exact reviewed result; no commit/push/deployment |

The client must show No/cancel as a real choice and must not answer for the user.
If `inspect_project.host_confirmation.form_supported` is false, remain blocked
or deliberately use the manual operator CLI. There is no silent CLI fallback.

`get_job` reports queue operation state, not task completion. `get_task` is the
canonical task state; `get_artifact` reads hash-verified evidence. A repair requires
a fresh execution confirmation. Do not change files or run additional tests while
an approval scope is pending. Read existing validation evidence instead.

## Compatibility / diagnostics

Plain `orchestrator serve` retains the v0.3 manual-worker/operator-gate behavior.
The existing `ask`, `create`, `start`, `approve`, `run`, `accept`, validator and
knowledge commands remain supported. Task/profile schemas and fingerprints are
unchanged. Gates are stored separately in `runtime/gates.sqlite3`; old artifacts
are not rewritten. `orchestrator gate G-ID` reads the gate/audit metadata.

Managed workers idle-exit after draining the queue. Their private log paths and
startup errors appear in MCP job/inspection output. Repeated failed startups stop
rather than looping indefinitely. Host disconnect does not undo already dispatched
work; it cancels an unanswered confirmation, while the separate worker completes
accepted queue work and idle-exits. Interrupted effects are never automatically
replayed.

## Verification / limitations

Tests cover malformed/negative confirmations, correlation and replay, stale state,
expiration, cancellation, native tool paths, worker lifecycle and subprocess wire
E2E with model shims plus actual pytest. Optional official MCP SDK interoperability
runs in CI via `.[interop]`. Those checks are not live Claude Code/Codex UI tests.
The owner previously reported complete v0.3 flows from both clients; those do not
verify v0.4 elicitation or new worker-environment behavior.

Read [v0.4 design/setup](docs/SINGLE_TERMINAL.md) and [changelog](CHANGELOG.md).
Earlier [architecture](docs/ARCHITECTURE.md), [security](docs/SECURITY.md),
[MCP v0.3 guide](docs/MCP.md) and [migration](docs/MIGRATION.md) describe the
retained legacy mode; the v0.4 document supersedes their manual-only claims for
explicit single-terminal mode. Trust/configuration changes remain operator-only
in both modes. License remains to be determined.
