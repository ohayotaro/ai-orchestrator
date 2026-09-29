# Migration recipes, not domain packs

The existing `claude-finance`, `claude-research`, and `claude-fullstack` repositories remain unchanged. The patterns below are starting points for small migration experiments, not complete compatibility with their runners, hooks, artifacts or safety guarantees.

## Ownership patterns

A finance-inspired profile can bind both planner and implementer to `claude`, and reviewer to `codex`. Validation still belongs to the controller. Put project-specific financial constraints in approved policy prose and register actual backtest/invariant checks explicitly. Do not import live-trading execution into v0.1.

A research-inspired profile can use Claude for planning/authoring instructions and Codex for implementation. Native `scientific-author` subagents, citation tools, evidence-ledger validation and the full literature-to-publication workflow are not automatically migrated. Register the existing ledger checker as a named validator only after inspecting it. The built-in phase graph is not a research-methodology engine.

A fullstack-inspired profile can retain Codex implementation with a fresh Codex reviewer by setting `cross_provider_review: false`. That opts out of cross-family checking; it does not remove fresh invocations or final operator acceptance. Alternatively, bind the reviewer to Claude and retain cross-family checking. Browser/visual acceptance, deployment hooks, production acknowledgments and the old PM's conversation responsibilities remain outside the v0.1 kernel.

## Migration procedure

Choose a disposable local worktree and one low-risk task. Run `orchestrator init`; do not copy an entire provider-specific configuration tree over `.orchestrator`. Map responsibilities to the three executable roles, add the real validation commands, and retain domain-specific semantics as user-owned context.

Review all controls that existed in the old template. A Markdown rule is not equivalent to a deterministic hook or OS restriction. Any control that cannot be represented/enforced in this alpha must remain external or block migration of that workflow. Existing finance/research/production safety controls must not be weakened to make an example pass.

Run the offline tests, then explicitly authenticate and smoke-test the chosen CLI pair in the disposable worktree. Compare acceptance evidence with the original workflow. Only extract reusable profile content after repeated successful project use; do not promote an unverified observation to a universal domain rule.

No automated importer, historical-state migration, external-effect workflow or end-to-end compatibility certification is included in v0.1.
