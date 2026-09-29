# Changelog

## 0.5.0 — alpha

- Add a versioned semantic Capability Registry and Provider Descriptor/Resolution contracts.
- Add Provider Adapter v2 semantic capability declarations while retaining runtime capability checks.
- Add deterministic resolution policy: fixed provider override, ordered role candidates, then provider priority/name.
- Enforce cross-provider review during dynamic reviewer resolution.
- Allow profile role requirements and Supervisor task-level capability requirements; manual create supports repeated `--require ROLE=CAPABILITY`.
- Persist effective requirements and frozen provider resolutions in new TaskState schema v3 and bind them into approval scopes/events/prompts/HumanGate previews.
- Fail unsupported/changed capability resolution before billable model work; do not silently fallback or rank models.
- Preserve v0.4.x profile digests when new capability fields are absent/default and retain legacy fixed Adapter v1 compatibility.
- Add `orchestrator capabilities`, MCP inspection output, JSON schemas and capability-resolution regression tests.
- Keep v0.5 intentionally sequential: no arbitrary DAG, writable parallelism or domain-specific kernel branching.


## 0.4.1 — alpha

- Replace the boolean checkbox with an explicit Yes/No enum confirmation.
- Require exact allowed_paths in new Supervisor write proposals and enforce their implementation write-set.
- Persist write_set evidence and include it in reviewer and acceptance context.
- Add bounded wait_job with MCP progress notifications; cancelling the wait does not cancel the durable job.
- Update the Skill to avoid shell diff/status, duplicate validators and repeated job polling.
- Record the owner-reported live v0.4 Claude Code run: all three host gates applied, 14 tests passed, review approved and final task succeeded.


## 0.4.0 — alpha

- Explicit `serve --single-terminal` opt-in; default v0.3 transport/manual mode stays compatible.
- `request_start`, `request_execution`, `request_acceptance` request native host forms through correlated MCP elicitation, not tool permission heuristics.
- Scoped HumanGate ledger with expiry, session ownership, local audit labels, exact previews, negative/cancel/error handling, stale-state checks inside kernel locks and no automatic replay of uncertain effects.
- Automatic separate worker processes with a freshly constructed environment, existing single-worker locking, private logs, bounded failed startups and idle exit. Initial trust remains operator-only.
- Direct nested start/ask/run from Claude Code rejected before state mutation; previous registration-before-planner-failure UX is avoided.
- Portable Skill updated for native gates, no home/history searches, no shell polling, no redundant validator execution and explicit manual fallback.
- `skill --replace` preserves a backup and refuses symlinks; `gate G-ID` provides read-only audit inspection.
- New form/protocol/worker tests and actual single-terminal wire E2E with model shims; optional official MCP SDK elicitation interoperability test.
- Existing profile/task schemas, approved artifacts and trust digests unchanged. Separate gates.sqlite3 is additive.

Confirmation remains client-mediated. Neither a local actor label nor elicitation
proves a human clicked; client hooks/settings can auto-answer. No automatic trust,
cryptographically signed user approvals, external-effect authorization, OS worker
isolation, additional providers, DAGs or parallel workspaces are implemented.
Authenticated live v0.4 host UI verification remains outstanding.

## 0.3.0 — alpha

Fixed-project stdio MCP tools, idempotent bounded ask/run jobs, operator-started
separate worker, portable Skill, CLI/client setup documentation and protocol-wire
E2E. Explicit human start/approve/accept stayed in the operator terminal. Owner
subsequently reported completed live flows from Claude Code and Codex frontends.

## 0.2.0 — alpha

Natural-language Supervisor intake, scoped proposal confirmation, role-specific
results with blockers separated from observations, validator preflight/check/
registration, generated-output controls and compatibility for v0.1 task rows.

## 0.1.0 — alpha

Project-driven sequential workflow kernel, Claude/Codex CLI adapters, SQLite
state/events, artifact hashes, explicit execution approval and final acceptance,
validator runner and operator-governed project knowledge promotion.
