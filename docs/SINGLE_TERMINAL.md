# v0.4: single-terminal operation with explicit host confirmations

## Design decision: elicitation, not tool-permission heuristics

The previous design discussion suggested using the host's Yes/No tool approval.
The implementation distinguishes ordinary tool permission from a server-requested
confirmation. MCP tool annotations do not compel a client to show a human prompt;
allowlists can skip it. v0.4 therefore uses the supported MCP form-elicitation
channel: a request tool begins a scoped gate, the server sends `elicitation/create`,
and the client responds to that specific server request with accept/decline/cancel.

The form contains one required boolean (`confirm`, default false). Only
`action: accept` with exactly `content: {confirm: true}` can authorize the current
operation. No agent-callable tool accepts `approved`, `actor`, a decision or a
signature/token. User-visible strings and scope digests are not credentials.

**This is client-mediated, not cryptographic human authentication.** The MCP
specification leaves UI behavior to clients. Claude Code supports Elicitation
hooks that may answer without showing a dialog; some host modes auto-decline.
A capable malicious client could also generate a response. The record deliberately
says `client-mediated; human presence not cryptographically verified` instead of
claiming a signed approval. A stricter identity boundary requires a separate
trusted authority service and is not implemented here.

The mode is an explicit operator opt-in, `serve --single-terminal`. Plain `serve`
retains v0.3 behavior. Form capability is detected at initialization rather than
inferred from a client name. If it is unsupported, returns an error, or cannot
present UI, gate requests fail closed. There is no fallback to chat text,
blanket tool permission, shell prompts inside MCP, or automatic authorization.

## What becomes single-terminal

```text
Host agent -> propose_task -> queue -> managed worker -> Supervisor
Host agent -> request_start -> host form -> register + queue planning
Host agent -> request_execution -> host form -> approve + queue implementation
Managed worker -> implementation -> registered validators -> fresh review
Host agent -> request_acceptance -> host form -> task succeeded
```

The human stays in the client for the three gates. Initial software/client
installation, project trust, validator registration and policy/configuration
changes still require deliberate operator setup. They are not new MCP tools.
The mode never authorizes commits, pushes, deployments, trading or external-effect
tasks. Completion and execution are distinct from accepting a reviewed result.

## Upgrade from the current fixture

Stop old workers if you want to exercise automatic startup; an active manual
worker is otherwise reused. Back up each stopped project's whole runtime directory.
Do not reinitialize it, change old TaskSpecs or reset existing arithmetic changes.

```bash
cd /Users/ohayotaro/ai-orchestrator
git pull --ff-only
.venv/bin/python -m pip install -e '.[dev,interop]'
.venv/bin/python -m pytest -q
.venv/bin/orchestrator --version
```

The version is 0.4.0. Existing task/profile/database contracts remain. A new
`runtime/gates.sqlite3` stores host-mediated gate metadata separately. Unchanged
profiles retain their trust digests. `skill --replace` is explicit, refuses
symlinks, and preserves the old regular file in an adjacent `.bak-<random-id>`
backup before writing the new packaged Skill.

Update only the relevant host's existing MCP entry, preserving other servers.
One registration is fixed to one absolute project root. Use the registration's
actual scope; the previous Claude fixture used local project scope.

```bash
ORCH=/Users/ohayotaro/ai-orchestrator/.venv/bin/orchestrator
PROJECT=/Users/ohayotaro/ai-orchestrator-e2e
cd "$PROJECT"

# Claude Code, from a normal terminal:
claude mcp remove ai-orchestrator --scope local
claude mcp add --transport stdio --scope local ai-orchestrator -- \
  "$ORCH" --project "$PROJECT" serve --single-terminal
"$ORCH" skill --output "$HOME/.claude/skills/ai-orchestrator/SKILL.md" --replace

# Codex, if using that client:
codex mcp remove ai-orchestrator
codex mcp add ai-orchestrator -- \
  "$ORCH" --project "$PROJECT" serve --single-terminal
"$ORCH" skill --output "$HOME/.agents/skills/ai-orchestrator/SKILL.md" --replace
```

Restart/reload the host's MCP connection and Skill. Do not enter raw JSON into
`serve`; its stdin/stdout belongs to the client protocol. To configure manually,
the only command change is adding `--single-terminal` after `serve`. Optional
`--gate-timeout 120` sets a 0.1-600 second response deadline. Host timeouts can be
shorter; a cancellation is a cancellation, not implicit consent. Start with
interactive Claude Code/Codex and disable hooks or settings that auto-answer
forms when you require a personal Yes/No.

Ask the host to call `inspect_project`. The response includes
`host_confirmation.enabled`, `form_supported`, assurance, and auto-worker state.
An `enabled` flag alone does not prove a client will display UI: the real gate
must return an explicit form response. Antigravity/Grok and headless clients are
not certified here. Legacy manual fallback remains available but must be chosen
by the user, not silently executed by the host agent.

## A new smoke test (no manual worker/start/approve/accept)

Use a new bounded task, for example:

> Use ai-orchestrator to add absolute_difference(a, b) and pytest tests. Preserve
> all existing functions. Delegate instead of editing directly. Use the host
> confirmation forms for start, execution and acceptance.

The host should retrieve the proposal, then call `request_start` with the intake
ID and a new idempotency key. The native form may render as a boolean toggle plus
Accept/Decline rather than literal two buttons; exact UI is client-specific.
Check the full preview and select Yes/accept. Planning is queued automatically.
At `awaiting_approval`, the next form authorizes the exact implementation attempt.
After real validation and a non-blocking review, a final form accepts the result.
Only `get_task.status == succeeded` and an acceptance artifact establish completion.

No/cancel must leave the operation unapplied. Do not test rejection by approving
and then trying to undo it: cancellation never rolls back completed effects.
The Skill tells the host not to answer for the user, search home/session history
for CLI syntax, create shell polling loops or rerun a successful validator merely
for reassurance. Poll at most 10 times per response and at least two seconds apart.
A transport retry reuses the original request ID; a newly approved repair attempt
uses a new gate request after user review.

## HumanGate persistence and scope

Gate records include server-generated ID/session, local uid, a locally derived
actor label, untrusted client name/version, operation/subject, exact content scope,
expiry, preview, state and outcome. Client metadata and local username are audit
labels, not authenticated end-user identity. Ordinary model-provided parameters
cannot replace them.

The scope covers the full task/intake state and kernel scope, current profile,
worktree, protected files and non-runtime control files. Preview includes the
registered validator definitions, plan/feedback or validation/review evidence.
Previews over 32 KiB are rejected rather than silently truncated. Bidi/format
control characters are escaped, while ordinary Japanese remains readable.

The kernel rechecks that scope under its existing workspace lock immediately
before registration, approval or acceptance. Any changed file/configuration or
expired dialog prevents the operation. Replay, mismatched sessions, parallel gates
for one subject and duplicate request IDs with different operations are refused.
A form Yes does not bypass existing cancellation, trust or external-effect checks.

The ledger records an `applying` intent before the effect. If a process dies in
that gap, the outcome may be uncertain: do not replay it. Inspect task/intake/job
and `orchestrator gate G-ID` first. If authorization succeeded but job queueing
failed, the result explicitly reports `scheduling_error`; the registration or
approval is not falsely described as rolled back. A still-eligible task can be
scheduled with `run_task` after inspection without repeating the gate.

Late, duplicate, malformed or wrong-correlation JSON-RPC responses never authorize.
Host disconnection cancels an unanswered gate. Ping/read/cancel messages remain
responsive while waiting; new mutating operations in that session wait until the
gate is resolved. Deadlines operate even if no more input arrives.

## Managed worker lifecycle and environment

Opt-in mode constructs a fresh runtime environment for a separate Python worker.
It deliberately does not copy `CLAUDECODE`, host CLI pipes, Python import paths,
shell startup/loader variables or the inherited worker marker. The parent host
environment is not modified. This is an intentional launch context selected by
`--single-terminal`, not a change to the provider adapter's direct nested-call
guard. Direct `start`/`ask`/`run` inside Claude Code still fails early; `start` now
fails before creating a terminally failed task. `start --no-run` remains manual
registration only, not a route to silently execute a model in that context.

HOME, normal PATH/locale, provider credentials/endpoints, selected proxy and
certificate settings are carried explicitly so independently launched CLIs can
authenticate. Values are not logged, but provider output can still contain
sensitive data. The worker is not a container or OS sandbox, uses the same local
user and may read user configuration. Threat isolation and cryptographic approval
attestation remain out of scope.

The manager runs no job at initialization or on read-only inspection. Queueing
or an applied start/execution gate activates it. Project worker locking prevents
cooperating managers from running duplicate workers. Children use constant argv,
Python isolated mode (`-I`), detached process sessions, null stdin and private
0600 runtime log files. The worker drains existing durable jobs then exits after
two idle seconds. Healthy idle exits do not trigger startup rate limiting; three
failed starts within a minute disable automatic launching until reconnection and
inspection. No terminal job is automatically requeued.

Disconnecting a host stops its manager but does not cancel already dispatched
jobs. The detached worker finishes and idle-exits; job cancellation is explicit.
A worker crash leaves effects to inspect. Existing v0.3 interrupted-job behavior
is retained and can mark abandoned work interrupted; it does not prove rollback.

## Test and evidence boundary

Local tests exercise affirmative/negative forms, malformed data, stale scope,
timeout, duplicate responses, cancellation, audit states, process environment,
automatic startup/idle exit, and actual stdio/subprocess execution through all
three gates with CLI-shaped model shims and real pytest. Both implementation/
review provider-role configurations are covered. The optional official Python
MCP SDK client test independently verifies elicitation/decline interoperability
in CI. The transport negotiates the supported 2025-06-18 protocol for form mode;
it does not claim implementation of later protocol revisions or elicitation URL
mode, sampling, HTTP/OAuth, MCP tasks, or signed authorization.

The owner supplied completed v0.3 Claude Code and Codex frontend transcripts.
Those are live evidence for the older manual gates, not for v0.4 forms or new
managed-process environment. Real interactive v0.4 client E2E is still required
and must be recorded with actual versions, rendered form behavior and final
state. Do not call offline shims or scripted SDK responses proof of a human UI.

Primary sources reviewed for the design:

- https://modelcontextprotocol.io/specification/2025-06-18/client/elicitation
- https://modelcontextprotocol.io/specification/2025-11-25/client/elicitation
- https://code.claude.com/docs/en/mcp
- https://code.claude.com/docs/en/hooks
- https://developers.openai.com/plugins/build/mcp-server
- https://github.com/openai/codex/blob/main/codex-rs/codex-mcp/src/elicitation.rs
- https://github.com/modelcontextprotocol/python-sdk/tree/v1.x
