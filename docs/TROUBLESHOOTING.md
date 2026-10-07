# Troubleshooting first use

Use a normal operator terminal for setup. Do not restart a paid task merely to diagnose installation. [README](../README.md) · [日本語README](../README_ja.md) · [connection guide](SINGLE_TERMINAL.md).

## Terminal says “process completed” / 「プロセスが完了しました」

That message alone is not success evidence. Read the preceding error and check that the executable and project actually exist. Do not paste `exit` or enable shell-wide `set -e` as a troubleshooting step in your interactive terminal. Stop at the first failed command rather than continuing in the old directory.

```bash
ls -ld "$PROJECT" "$VENV"
"$VENV/bin/orchestrator" --version
```

If either path is missing, resume the corresponding setup step; do not delete a partially created environment without inspection. Avoid restarting an entire initialization script over existing files.

## A `>` / `quote>` / `heredoc>` prompt appears

The shell is waiting for the end of a quote, heredoc or continued line; it is not necessarily Claude Code. For an incomplete command, press Ctrl-C to return to the normal shell prompt, then paste a complete small block. This does not roll back commands already executed. A trailing backslash requests another line; it must not be the last line of an incomplete paste.

## `zsh: command not found: #` or `cdset`

Interactive zsh may not treat pasted `#` lines as comments. The README's executable blocks omit comment-only lines and heredocs. `cdset` indicates concatenated input, not a valid command; start from a fresh prompt. Copy ordinary ASCII spaces/quotes, not formatted Unicode whitespace. These messages do not establish whether later commands succeeded.

## `cd` failed, but Git reports changed files

A failed cd leaves you in the previous directory. `git status` may therefore describe an old fixture. Never reset/clean those files to repair the new setup. Use a guarded change of directory:

```bash
cd "$PROJECT" && git status --short
```

## Package name or executable is missing

The PyPI distribution is `ai-orchestrator-kernel`, the import package is `ai_orchestrator`, and the command is `orchestrator`. Check the same venv the MCP registration starts, not an unrelated global Python. Use `"$VENV/bin/python" -m pip show ai-orchestrator-kernel` and `"$VENV/bin/orchestrator" --version`.

## Wrong project or stale MCP/Skill

Run `claude mcp get ai-orchestrator` from the intended project. The registration must use the correct absolute executable and `--project`. Inspect an existing entry before replacing it. Then restart the affected host session from the new project. Do not reuse the old session or unset internal-worker/CLAUDECODE markers.

Use `orchestrator identity --skill PATH` to compare loaded/disk builds and exported Skill. On mismatch, inspect active work before restarting; never update live source underneath running workers. Global Skill replacement can affect more than one project.

## A fresh jobs/gates database is absent

Lazy creation is normal. Read-only operational diagnosis may report `present: false`. Once created, v1.0.0 writers are runtime=3, gates=1 and jobs=2. Do not create rows or edit schema markers to satisfy a checklist.

## Validation, trust or forms fail

Use the exact Python containing your test dependencies for validator registration. Registration does not execute the test; `validator check pytest` does, and its output is measured evidence. Inspect config/policy before trust. Plain `doctor` may probe providers; use `doctor --operational-only` for provider-free diagnosis.

For a declined, cancelled, expired or stale form, inspect the task/job/gate and preserve the outcome. Do not switch to CLI approval, widen permissions, auto-answer or retry paid calls without intent. A form Yes can legitimately have caused work even when it was a mis-click.

## Files changed before Acceptance / controller files appear

Execution authorizes writes. Acceptance is result acceptance, not first-write permission. Cancellation and finalization do not undo integrated files. Controller-created `.orchestrator/tasks/` and knowledge candidates may appear as untracked files after work; do not blanket-ignore, delete or commit them without reviewing your evidence/privacy policy. A setup preflight's clean baseline does not mean a completed campaign must have no retained history.
