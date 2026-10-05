# v0.3: conversational clients, MCP frontend, separate worker

The orchestrator is a control plane for the AI client you already use. The client
can propose work and observe or resume an existing, human-confirmed task. It
cannot grant itself authority. v0.3 deliberately exposes no trust, start,
approve, accept, validator-registration or policy-promotion MCP tool.

```text
User <-> Claude Code / Codex / compatible MCP client
                    |
              stdio MCP frontend (fixed project, fast queue operations)
                    |
         .orchestrator/runtime/jobs.sqlite3
                    |
       separate operator-started worker
                    |
         Supervisor / existing execution kernel
                    |
          validators / independent review

Human operator terminal: trust -> start -> approve -> accept
```

The frontend never launches a model. This avoids nested Claude sessions and
long-running MCP calls. The worker is started from a normal terminal outside
Claude Code; its session guard is retained, not unset. No HTTP port, unauthenticated
web endpoint, daemon auto-installer or background service is created by setup.

## Upgrade and prepare

Stop running tasks/workers and back up each project's `.orchestrator/runtime/`.
From the orchestrator checkout:

```bash
git pull --ff-only
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m pytest -q
.venv/bin/orchestrator --version   # 0.3.0
```

The MCP runtime uses the existing Python dependencies only. For the optional
independent official-SDK interop test, install `'.[dev,interop]'`. CI installs it.
Existing v0.2 task/profile schemas and trust digests are not rewritten. Job state
lives in a separate SQLite database; retain it together with the existing state
DB and artifacts when backing up. No existing task is automatically restarted.

Use a disposable local Git project first. Define the following in each operator
terminal (replace the paths with your installation):

```bash
ORCH=/Users/ohayotaro/ai-orchestrator/.venv/bin/orchestrator
PROJECT=/Users/ohayotaro/ai-orchestrator-e2e

"$ORCH" --project "$PROJECT" doctor --validators-only
# Only after inspecting the project profile and registered commands:
"$ORCH" --project "$PROJECT" trust --by "$USER" --ack-local-execution
```

## Connect the client

Perform client/skill installation before queueing work; configuration files can
otherwise change an already-scoped workspace snapshot. `serve` intentionally
receives an absolute project path; the agent cannot switch it per tool call.

Claude Code, registered for the current project from your normal terminal:

```bash
cd "$PROJECT"
claude mcp add --transport stdio --scope local ai-orchestrator -- \
  "$ORCH" --project "$PROJECT" serve
claude mcp list
```

Codex:

```bash
codex mcp add ai-orchestrator -- "$ORCH" --project "$PROJECT" serve
codex mcp list
```

A server name refers to one fixed project. Use distinct server names/configuration
when intentionally working with multiple projects. If a server of that name
already exists, inspect its configuration rather than adding duplicates.

For other stdio-capable clients, the equivalent command/arguments are:

```json
{
  "command": "/absolute/path/to/ai-orchestrator/.venv/bin/orchestrator",
  "args": ["--project", "/absolute/path/to/project", "serve"]
}
```

The containing configuration format varies by client. Antigravity/Grok client
compatibility is not certified in this release; no new Gemini/Grok worker adapter
is included. `serve` is stdin/stdout JSON-RPC, not an interactive terminal UI.

## Install the portable Skill

Export the same packaged SKILL.md into the skill directory used by the client.
The command refuses to overwrite any existing file and never edits client config.
For example:

```bash
# Claude Code personal skill directory
"$ORCH" skill --output "$HOME/.claude/skills/ai-orchestrator/SKILL.md"
# Codex personal skill directory
"$ORCH" skill --output "$HOME/.agents/skills/ai-orchestrator/SKILL.md"
```

The skill is guidance, not permission enforcement. It tells the host agent to
stop direct edits after delegation, preserve existing changes, use stable
request IDs on transport retries, and route all human gates to the operator.

## Managed single-terminal mode

Plain `orchestrator serve` is the standard managed mode. When the MCP client
supports interactive form elicitation, the server manages the separate worker
process and Start / Execution / Acceptance HumanGates can remain in the same
client terminal. `--single-terminal` is retained as an explicit compatibility
spelling; `--legacy-terminal` opts out.

Legacy/manual operation may still start a worker in a separate normal terminal:

```bash
"$ORCH" --project "$PROJECT" worker
```

Ctrl+C requests cancellation and stops the worker; it does not roll back
completed effects. To process at most one job:

```bash
"$ORCH" --project "$PROJECT" worker --once
```

Only one worker may own a project. While it executes a task, the existing
workspace lock also excludes other cooperating controllers. Do not edit the
project directly from a host agent while a queued/running job is based on it.

## Conversation-to-acceptance example

Tell the connected client:

> Use ai-orchestrator to add divide(a, b) and regression tests. Preserve the
> existing arithmetic functions. Propose the task first; do not edit directly.

The client calls `inspect_project`, then `propose_task`. The returned `J-...` is
an operation ID, not a task or intake ID. `get_job` reports the result after the
worker finishes the Supervisor call. A proposed intake has `I-...`, a TaskSpec,
and `intake_scope`; clarification is answered through a new `propose_task` with
`reply_to` and a new request ID.

Inspect the proposed work before confirming in the **operator terminal**:

```bash
"$ORCH" --project "$PROJECT" intake I-REPLACE
"$ORCH" --project "$PROJECT" start I-REPLACE \
  --scope 'EXACT_INTAKE_SCOPE' --by "$USER" --no-run
```

The client can now use `run_task` to queue planning. Once the task is
`awaiting_approval`, inspect the worktree/plan and authorize the exact scope:

```bash
"$ORCH" --project "$PROJECT" approve TASK-ID --interactive --by "$USER"
```

The client then queues `run_task` with a **new request ID** and polls `get_job`.
Implementation, validation and review run through the existing kernel. At
`awaiting_acceptance`, inspect the actual diff and evidence before:

```bash
"$ORCH" --project "$PROJECT" accept TASK-ID --by "$USER"
"$ORCH" --project "$PROJECT" status TASK-ID
```

Only task `status: succeeded` means final acceptance. Job `status: succeeded`
means that its queued operation returned successfully; it may return a task
waiting for human approval, not a completed task. An informal chat "yes", a
model-supplied `actor`, or knowledge of a scope never authorizes a gate via MCP.

## Tools and jobs

`inspect_project`, `get_job`, `get_intake`, `get_task` and `get_artifact` inspect
the fixed project. `get_artifact` takes task ID/kind and verifies stored hashes;
it cannot fetch arbitrary paths. `propose_task` and `run_task` enqueue work.
`cancel_job` requests cancellation. All schemas reject extra arguments.

`request_id` is required for queued actions. Identical retries return the original
job, including after completion. Reusing it with different arguments is rejected.
A pending job for the same target is not duplicated. At most 32 operations may be
queued/running; a job not begun within one hour expires rather than running later
surprisingly. These are local resource limits, not financial spend caps.

Profile/worktree changes invalidate queued work before model dispatch. Repair
rounds still need fresh scoped approvals. A stale `running` job left by a crash is
marked `interrupted` on worker restart, never replayed. If a task itself remains
`running`, use the existing operator `recover` procedure after inspecting partial
effects. Model outputs/artifacts are retained rather than rolled back or deleted.

```bash
"$ORCH" --project "$PROJECT" job J-REPLACE
"$ORCH" --project "$PROJECT" cancel-job J-REPLACE
```

Transport disconnect is not business cancellation: the job remains in the local
queue. Use `cancel_job` explicitly. Cancellation is cooperative and cannot undo
completed effects or contain a hostile process that escapes its process group.

## Protocol and verification boundary

This is a small stdio-only MCP server. It implements initialize/initialized, ping,
notifications handling, tools/list and tools/call; protocol negotiation supports
2024-11-05, 2025-03-26 and 2025-06-18, selecting 2025-06-18 for newer clients.
Structured tool output is returned on 2025-06-18. It advertises no resources,
prompts, sampling, elicitation, dynamic tool list, HTTP/OAuth, or experimental MCP
tasks. The application's durable job queue is not the MCP Tasks extension.
JSON-RPC lines are bounded to 2 MiB; diagnostics never go to protocol stdout.

Tests cover a real stdio frontend and separately spawned worker with CLI-shaped
provider shims plus real pytest, for both provider-role configurations. They also
cover authority rejection, duplicate requests, cancellation, expiry, snapshot
invalidation, lock ownership and crash recovery. The optional official MCP SDK
client is a separate interop smoke test, not a replacement for real-client E2E.
No authenticated v0.3 Claude Code/Codex interactive-client E2E is claimed yet.

Protocol/client references consulted for this implementation:

- https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
- https://modelcontextprotocol.io/specification/2025-06-18/server/tools
- https://code.claude.com/docs/en/mcp
- https://code.claude.com/docs/en/skills
- https://developers.openai.com/codex/mcp
- https://developers.openai.com/codex/skills


## v0.14 Project Learning inspection

`inspect_project` now includes a `project_learning` summary: evidence counts,
candidate counts/status/kinds, accepted-context universe size, selection budget
and governance flags.

The MCP surface adds three read-only tools:

- `list_learning_candidates`: list candidate status/support/relationships and
  exact inspection scope;
- `get_learning_candidate`: read typed evidence/support/provenance for one
  candidate;
- `preview_learning_context`: deterministically preview which already-accepted
  context paths would be selected for a query.

These tools do not generate candidates, promote/reject/revise them, edit accepted
Markdown or grant trust. `learning distill`, `promote`,
`proposal-reject`, `proposal-revise` and `trust` remain local
operator actions.

New intakes/tasks retain their selected `context_influence` provenance.
Task influence is additionally available as the hash-verified
`context_influence` artifact. Treat that manifest as evidence of what the
controller selected, not proof that the selected Markdown is correct.
