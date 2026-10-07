# Single-terminal setup and operation

Start with the complete [English](../README.md#quick-start-claude-code--codex) or [Japanese](../README_ja.md) walkthrough. This page covers connection scope and existing projects. The original implementation narrative is retained verbatim in [SINGLE_TERMINAL_HISTORY.md](SINGLE_TERMINAL_HISTORY.md); its old versions, personal paths and commands are historical, not current installation advice.

## Three separate locations

An optional source repository is for development. A dedicated venv contains the installed kernel executable. The project directory is the Git worktree the kernel will manage; it contains `.orchestrator/`. These paths are not interchangeable. A source checkout is not needed for normal PyPI installation.

A stdio registration starts one kernel at a fixed absolute `--project` path. Inspect `claude mcp get ai-orchestrator` from the intended project and compare its command/path with the executable and project you mean to use. Do not put protocol JSON into an interactively started `orchestrator serve`; the host owns that process's stdin/stdout.

## Connect a project

In a normal terminal, set ORCH to your installed executable and PROJECT to the intended absolute Git worktree. The README uses real demo paths and creates them before connecting.

```bash
cd "$PROJECT" && claude mcp add --transport stdio --scope local ai-orchestrator -- "$ORCH" --project "$PROJECT" serve
```

For an existing registration, first inspect it. Remove only the verified obsolete entry in its actual scope, then add the replacement. Do not use unconditional deletion as routine setup or touch unrelated servers.

```bash
cd "$PROJECT" && claude mcp get ai-orchestrator
```

Export the packaged Skill explicitly. Without `--replace`, an existing file is refused. After inspection, `--replace` preserves an adjacent backup before replacement. A global Skill path is shared by that host's projects; consider other installations before replacing it. `identity --skill PATH` compares bytes but does not sync them.

Restart the project's host/MCP connection after changing the executable, project binding or Skill. For the qualified Claude Code workflow, start a new session from the intended project. A previous session bound to an old fixture does not become a new-fixture session by issuing cd in an agent shell.

## Normal operation and authority

`serve` defaults to single-terminal mode and managed separate workers. `--single-terminal` remains a compatibility flag; `--legacy-terminal` opts into the older manual-worker flow. The host's form capability is negotiated, not inferred from its name. Normal operation is proposal → Start → planning → Execution → implementation/validation/fresh review → Acceptance → succeeded.

Start registers and queues planning. Execution authorizes an exact attempt, including writes; root integration can happen before Acceptance. Acceptance records acceptance of the reviewed result, not initial write permission. No/cancel/missing/timeout/stale does not authorize another effect. Form cancellation is not task terminalization and does not revert files. `cancel TASK_ID` records cooperative task cancellation; `cancel --finalize` is a distinct exact-scope operator operation. No task-cancel MCP tool is provided in v1.0.0.

Setup, validator registration, project trust and maintenance are deliberate CLI operations. Marked agent shells are not a substitute for an operator terminal; do not unset recursion markers to bypass guards. Chat Yes, tool allowlists and ordinary permission prompts are not HumanGate answers. Hook-generated answers are not proof of human presence.

## Upgrading and existing projects

Do not run init on an existing `.orchestrator/`, erase runtime history or clean a dirty worktree as an upgrade shortcut. Inspect active work, stop/quiesce affected controllers/workers, and use the **old executable before upgrading** to create and verify a full backup. Preserve Git/worktree files separately: controller backup is not a universal source-file or remote-effect backup.

Install the chosen version into a separate venv, verify distribution/build/Skill identities, inspect compatibility, then deliberately rebind and restart the host. Update only the host Skill copies actually in use. An unchanged profile does not require a new trust grant merely because the package changed; profile, validator, policy or accepted-context changes do.

Do not use editable main to claim an exact published artifact. Rollback requires a verified matching backup plus matching executable; changing SQLite PRAGMA markers or reinstalling an older package alone is not a supported downgrade. [Migration](MIGRATION.md) · [Operations](OPERATIONS.md) · [Recovery](RECOVERY.md).

## Host limitations

[Support](SUPPORT.md) separates the tested Claude Code host from Codex provider execution and other unqualified hosts. Form timeout/cancel is not solved by CLI fallback or broader permissions. `--gate-timeout` controls the server deadline but cannot force a host to render UI. Inspect task, job and gate evidence before considering any retry.

[Claude Code's MCP documentation](https://code.claude.com/docs/en/mcp) describes stdio syntax and scope. Its current features are not automatically part of the v1.0.0 qualified host configuration. For command-entry problems and diagnostics, see [Troubleshooting](TROUBLESHOOTING.md).
