# Changelog

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
