# Changelog

## 0.3.0 — alpha

- Fixed-project stdio MCP tools with a bounded JSON-RPC transport and no HTTP listener.
- Durable local ask/run job queue, required idempotency keys, 32 pending-job limit and one-hour start expiry.
- Separate operator-started worker: retained Claude session guards, recursion marker, single-worker locking and no automatic replay after interruption.
- Agent-facing inspection, proposal, artifact retrieval, gated execution and cooperative job cancellation; no trust/start/approve/accept or arbitrary shell/path tools.
- Portable packaged Agent Skill with no-overwrite export, plus Claude Code/Codex connection documentation.
- Queued profile/worktree binding checked before dispatch; cancellation propagated into Supervisor/provider/validator process checks.
- Existing v0.2 profile fingerprints/task schemas remain unchanged; separate job database requires no task-state rewrite.
- Actual stdio/subprocess wire E2E with both provider-role configurations, protocol/error tests and optional official MCP SDK client interoperability test.
- No authenticated interactive-client v0.3 E2E, multi-user identity boundary, automatic human approval, new provider, arbitrary DAG or parallel workspace execution is claimed.

## 0.2.0 — alpha

### Added

- Provider-neutral Supervisor and `ask` natural-language task proposals with explicit clarification, immutable evidence and confirmation scopes.
- `intake` inspection and `start` confirmation; one-time transactional proposal consumption, then optional automatic planning (never execution approval).
- Minimum T2/mandatory execution approval for normal ask tasks; explicit advisory mode, known-validator enforcement, blocked external effects and bounded clarification/call/time accounting.
- PlanResult, ImplementationResult and ReviewResult for new tasks; separate blocking findings and observations.
- Schema-parameterized Claude/Codex requests without changing the existing native CLI permission modes.
- Validator registration/check commands, non-executing doctor/preflight, project-relative/PATH/absolute executable resolution and preserved virtualenv interpreter symlinks.
- Filtered explicit validator environment, default Python bytecode suppression and narrow untracked generated-output roots.
- Mutation path diagnostics, non-runtime control-file checks and retained validation evidence on integrity failures.
- Terminal-only interactive execution approval with scope revalidation and escaped previews.
- Additive runtime database migration and legacy task/result/profile-fingerprint compatibility tests.
- Offline subprocess-based wire E2E for both provider-role configurations and an owner-reported v0.1 live E2E record.

### Compatibility and limits

- TaskSpec YAML/JSON v1 and existing create/run/approve/accept interfaces remain available.
- Existing task rows keep legacy AgentResult semantics. Newly created task state uses version 2.
- Unchanged v0.1 profile fingerprints remain stable; configuration changes still require retrust.
- Back up stopped runtimes before upgrade. Downgrading the upgraded database is unsupported.
- This is trusted-local orchestration, not authenticated human approval or OS-separated control state.
- New v0.2 model schemas and Supervisor require a live authenticated smoke test; offline shims are not model verification.
- Gemini/API adapters, arbitrary DAGs, parallel workers, native subagents, cost/token budgets, automated evidence verification and dynamic workflow selection remain unimplemented.
