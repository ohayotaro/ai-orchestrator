# Changelog

## 0.17.2 — v1 contract and release-evidence preparation

- Correct schema-position normalization and inherited CLI/default/action/mutex
  inventory coverage; add mutation-sensitive checks and retain the v0.17 baseline.
- Add explicit public data/SDK boundaries, input/output/error schemas, full-schema
  export, test-time actual-response conformance and independent inventory v2 checks.
- Preserve persisted readers/writers, authority and historical evidence hashes.
- Separate support axes in matrix v2; preserve the old matrix byte-for-byte and
  leave final-artifact deployments unqualified until owner live evidence exists.
- Build one wheel/sdist in CI and qualify the same artifacts on all reference
  lanes; collect measured receipts without claiming still-running CI is finished.
- Add read-only release evidence validation, transitive digest/archive checks and
  scoped external publication decisions. No tool publishes or grants authority.
- Batch V1-01–05 preparation; retain separate final 1.0.0 live and release gates.
  No license/channel decision, runtime upgrade, support promotion or publication.

## 0.17.1 — RC live-closure follow-up

- Reject `request_provider_permission` during gate preparation when the target
  task already has a durable cancellation request. The apply/resolve path already
  failed closed; this closes the remaining RC-01 entry-point inconsistency so no
  high-risk permission form is shown for a cancelled task.
- Add a regression proving the provider-permission gate is refused before any
  HumanGate row is created.
- Update CLI release labeling and `inspect_project.operator_only` diagnostics to
  include `cancel --finalize` and `maintenance reconcile`.
- Clarify restore semantics: the approvals table is revocable authority state and
  is cleared on restore, including rows associated with terminal tasks; canonical
  historical approval provenance remains in runtime events and immutable task
  evidence.
- Keep the Claude Code 2.1.284 Yes→No anomaly from the 0.17.0 live run as a
  conditional host-transport observation. It failed safe and the controlled
  positive baseline subsequently passed twice, so no authority bypass is claimed.
- Owner-reported 0.17.1 targeted live recheck passed: a cancelled fresh task
  refused `request_provider_permission` at prepare time with no HumanGate row or
  form, no grant, no provider/validator call and no file/authority mutation.
- Close the v0.17 Release Candidate Hardening milestone at v0.17.1.

## 0.17.0 — Release Candidate Hardening (implementation candidate)

- Make cancellation requests idempotent and visible through a separate v1 view.
  Reject cancellation consistently at approval/scheduling/dispatch entry points.
  Add exact-scope operator-only idle finalization without provider, validator,
  file deletion, rollback or trust effects; revoke approvals/grants atomically.
- Render HumanGate decisions as No then Yes with operation-specific titles.
  Keep a single required string decision, no server default, and unchanged exact
  affirmative response, expiration, stale-state and no-replay semantics.
- Share a complete evidence inventory between doctor and retention, including
  recursive accepted context and frozen historical Task/Intake/Exploration
  references. Detect conflicting shared metadata before deduplicating reads;
  retain compatible legacy references and reject incomplete cleanup roots.
- Upgrade jobs SQLite v1 to v2 for durable request receipts. Atomically retain
  request identity while deleting terminal payloads/events. Retired IDs return
  structured refusals, never new queued calls. Restore merges compatible known
  history, suppresses pending restored work and records explicit revocations.
- Persist maintenance intent and recovery staging before destructive changes.
  Block startup/mutation/new dispatch on pending or invalid intents; provide
  read-only inspection and exact-scope operator reconciliation. Preserve crash
  evidence across process loss, reject replaced database handles and keep audit
  completion inside the durable success boundary. Add actual SIGKILL regressions.
- Add candidate schema/API inventory, historical baseline hash fixtures,
  content-free loaded-build/Skill identity, explicit host Skill comparison,
  minimum/reference dependency lanes and clean wheel/sdist qualification.
- Keep TaskState v9, IntakeState v6, Exploration v1, runtime SQLite v3 and gates
  SQLite v1. No automatic old-row rewrite, provider fallback, permission expansion,
  learning promotion, maintenance replay, tag creation or package publication.
- Supply a versioned host/provider support matrix and repeated live qualification
  procedure. v0.17 live entries remain unverified; implementation completion is
  distinct from the separate v1.0 release decision.

## 0.16.0 — Exploration / Deliberation Sessions

- Add durable, non-authoritative ExplorationState v1 with bounded multi-turn
  understanding, hypotheses/options/questions/decisions and immutable evidence.
- Execute reasoning on the existing read-only disposable Supervisor workspace;
  freeze provider/model identity and apply cumulative usage/budget contracts.
- Add deterministic latest-understanding context selection with selected/omitted
  turn provenance; retain historical/discarded turn artifacts.
- Add explicit revision-bound exploration-to-intake proposals. Start still
  requires the normal HumanGate; Execution and Acceptance are not implied.
- Bind source revision/snapshot/decision evidence into IntakeState v6, TaskState
  v9 and Start previews. Atomically consume the source when registering a task.
- Supersede/withdraw old unconsumed intakes on revision/abandonment and reject
  linked intake reply-to bypass. Interrupted reasoning/proposal calls are never
  automatically replayed; durable reservations preserve missing usage as unknown.
- Add six MCP exploration surfaces, managed worker queue integration and operator
  CLI inspection/reasoning/proposal/abandonment commands. No new maintenance,
  permission, validator, accepted-knowledge or profile-trust authority is added.
- Add runtime SQLite v3 exploration storage; Job v2 supports exploration actions
  while ordinary ask/run v1 jobs remain compatible. Legacy TaskState/IntakeState
  model dumps omit new fields so historical learning/evidence hashes stay stable.
- Include exploration rows/turns/transitions in read-only diagnostics and physical
  retention roots, and preserve them through runtime/full backup and restore.
- Add offline lifecycle, negative-authority, budget, interruption, migration and
  retention regressions plus a subprocess MCP/managed-worker/three-gate E2E.
- Owner-reported live closure passed multi-turn direction change, stale-revision
  fail-closed behavior, explicit exploration-to-task transition, normal Start /
  Execution / Acceptance HumanGates, isolated implementation, pytest validation,
  independent review, usage/budget carry-forward, abandonment, doctor/retention
  integration and final project non-interference.
- A separate live proposal verified Start decline leaves no registered task and
  triggers no automatic replay. Exploration prose did not auto-promote accepted
  Project Learning or modify profile/provider/workflow trust.
- Close the v0.16 Exploration / Deliberation milestone at v0.16.0.

## 0.15.1 — Intake artifact retention follow-up

- Fix physical retention so immutable Supervisor artifacts referenced directly
  by retained `IntakeState.artifact` are canonical roots, not orphan candidates.
  This prevents cleanup from deleting evidence required to inspect or start
  still-proposed intakes.
- Extend read-only operational diagnostics to include IntakeState-referenced
  artifact hashes/evidence alongside TaskState artifacts.
- Add regressions proving an intake-referenced Supervisor artifact is excluded
  from `orphan_artifacts`, survives exact-scope cleanup and remains readable
  against the retained IntakeState after cleanup.
- Owner-reported live closure on the accumulated runtime passed read-only doctor,
  verified full/runtime backups, exact-scope full restore, unreadable-state
  restore, runtime-only authority separation, retention scope drift, cleanup and
  final original-project non-interference. The v0.15.0 false-orphan defect was
  no longer reproducible; 46 IntakeState artifact paths had zero overlap with
  `orphan_artifacts`, and cleanup preserved all Supervisor evidence.
- Close the v0.15 Operational Hardening milestone at v0.15.1.

## 0.15.0 — Operational Hardening

- Expand `doctor` with read-only integrity diagnostics for runtime SQLite
  databases, versioned task/intake rows, immutable artifact hashes/evidence
  schemas, stale jobs, HumanGate ledger state, disposable worktrees and the
  maintenance audit log. A structurally unreadable runtime database is diagnosed
  before normal Engine construction; v0.15 does not repair it implicitly.
- Add versioned backup manifest v1 with exact per-file SHA-256/byte provenance,
  deterministic restore scope and bounded archive validation. Runtime-only
  backups preserve controller evidence without project authority; full backups
  include configuration, policies, skills, accepted knowledge, workflow
  templates and trust/runtime state.
- Snapshot SQLite through the SQLite backup API so WAL state is folded into a
  canonical database copy. Disposable worktrees, process locks and SQLite
  sidecars remain excluded from backup authority.
- Add explicit operator-only restore. Restore requires a verified exact scope,
  a quiescent project and `--replace`; full authority restore additionally
  requires `--ack-authority-restore`. Unreadable current runtime/authority
  fails closed unless the operator explicitly supplies
  `--ack-unreadable-current-state` to replace it from a verified backup.
  Current managed state is staged for rollback, restored runtime is
  structurally re-checked, and full restore must reproduce the archived profile
  digest.
- Add read-only physical retention planning and exact-scope cleanup. The initial
  cleanup surface is deliberately narrow: stale disposable worktrees, terminal
  job/job-event rows and old orphan Artifact-v2-shaped runtime JSON only.
  Task/intake rows, runtime event history, HumanGate history,
  TaskState-referenced artifacts and typed evidence referenced by accepted
  knowledge/policy/skill or retained Project Learning candidates are retained.
  Legacy untyped learning evidence disables orphan-artifact GC rather than
  guessing provenance.
- Record successful restore/cleanup maintenance actions with bounded actor,
  scope, timestamp and action details under
  `.orchestrator/runtime/maintenance.jsonl`.
- Expose operational diagnostics through read-only
  `inspect_project.operational_hardening` while adding no MCP backup, restore,
  cleanup or database-repair mutation tools. Maintenance remains separate from
  normal agent/HumanGate execution authority.
- Add offline regressions proving physically read-only diagnosis, unknown-state
  fail-closed behavior, exact-scope/authority-aware restore, runtime-only
  authority separation, retention scope invalidation and Project Learning
  evidence protection.
- Keep runtime/HumanGate/jobs SQLite user versions, TaskState/IntakeState and
  existing evidence schemas unchanged; v0.15 adds operational contracts rather
  than rewriting persisted execution history.

## 0.14.1 — Project Learning inspection follow-up

- Fix the read-only MCP `list_learning_candidates` and
  `get_learning_candidate` surfaces when candidates exist. v0.14.0 referenced
  the candidate scope digest without importing the digest helper, so the bug was
  hidden while the candidate set was empty and surfaced as an internal tool
  error after the first live distillation.
- Add non-empty-candidate MCP regression coverage for both list and get paths.
- Expose derived `evidence_coverage` diagnostics in candidate inspection so
  operators can distinguish full support recurrence counts from the bounded
  retained typed-evidence/task-ID samples. The diagnostics also show retained
  validation/review artifact-reference counts and explicitly note that legacy
  Artifact v1 corroboration has no stable typed artifact ID.
- Keep candidate bytes, IDs, scopes, profile fingerprints and authority
  semantics unchanged; this is an inspection-only compatibility fix.
- Owner-reported live closure then passed the full Project Learning lifecycle:
  deterministic first distillation, non-authoritative candidate inspection,
  idempotent re-distillation, exact-scope promotion, automatic untrust on profile
  change, explicit re-trust, IntakeState-v5/TaskState-v8 ContextInfluence reuse,
  normal isolated execution with `46 passed` and independent review,
  post-Acceptance automatic candidate/supersession generation, promotion cleanup
  and final explicit re-trust.
- The final live state restored the original trusted project authority while
  retaining 24 inactive candidates, the successful task evidence and historical
  ContextInfluence. This demonstrates that learning can accumulate without
  silently accumulating authority.

## 0.14.0 — Knowledge Distillation / Project Learning

- Add versioned Project Learning contracts with typed controller-resolvable
  `EvidenceRef` values for task, intake, artifact and event evidence, plus
  inspectable support/provenance instead of opaque model confidence.
- Add deterministic distillation over durable task acceptance, write-set,
  validation, review, recovery, provider provenance, usage and budget evidence.
  Generated candidates remain non-authoritative observations/recommendations.
- Generate bounded knowledge, policy, skill and workflow-reuse candidates.
  Workflow candidates are recommendations only; reusable workflow installation
  continues to require the existing explicit `workflow-save` authority path.
- Add stable candidate IDs, exact-evidence suppression for rejected candidates,
  material-new-evidence regeneration, supersession links and contradiction
  detection. Bound retained typed evidence/task-ID samples while preserving full
  support counts and identity changes for long-lived projects.
- Add operator-only candidate rejection/revision commands and preserve explicit
  digest-scoped promotion. Schema-v2 promotion re-resolves and hash-verifies all
  typed controller evidence before writing accepted context.
- Separate the accepted project-context universe from per-intake/task prompt
  context. New intakes/tasks bind a deterministic `ContextInfluence` manifest
  and inject only the bounded selected subset into Supervisor/Planner/
  Implementer/Reviewer prompts.
- Preserve accepted but superseded/contradictory learning as durable provenance
  while excluding it from automatic prompt injection until explicitly resolved.
- Raise the accepted-context universe bound to 4 MiB / 2048 Markdown items while
  keeping deterministic prompt selection at 24 KiB and the existing 64 KiB
  complete-prompt ceiling.
- Persist `context_influence` evidence on new TaskState v8 and IntakeState v5,
  while keeping TaskState v1-v7 and IntakeState v1-v4 readable without rewrite.
  Runtime/HumanGate/jobs SQLite user versions do not change.
- Expose Project Learning status in `inspect_project.project_learning`, add
  read-only MCP candidate/context-preview surfaces, and add
  `orchestrator learning report|distill|context` plus proposal
  reject/revise operator commands.
- Run post-acceptance distillation as a best-effort advisory step: a learning
  failure cannot roll back or alter an explicitly accepted task.
- Add v0.14 regression coverage for deterministic generation, typed-evidence
  tamper failure, rejection/new-evidence behavior, contradiction handling,
  bounded context selection, influence persistence, and knowledge/policy/skill/
  workflow candidate classes.
- Preserve the authority boundary: Project Learning cannot select providers,
  grant permissions, register validators, authorize external effects/write
  scope, change model/runtime or budget policy, install workflow templates, or
  grant project trust.

## 0.13.0 — Provider Adapter / Plugin SDK

- Publish Provider SDK v1 with Provider Adapter API v2 as the supported
  third-party provider-extension boundary.
- Split the adapter contract into required core lifecycle methods and optional
  runtime-option, usage and role-compatibility features.
- Discover third-party adapter metadata through the
  `ai_orchestrator.providers` entry-point group without importing plugin code
  merely because a package is installed.
- Add project-owned `provider_plugins` pins for exact adapter ID,
  distribution, version and entry-point target. External code loads only after
  the exact resulting profile digest has been explicitly trusted.
- Fail closed on missing/mismatched pins, unsupported SDK/API versions,
  built-in adapter-ID collisions, plugin import/factory failures and
  conformance failures.
- Preserve loaded plugin package/version/entry-point identity in Provider
  Descriptor/Resolution, workflow frozen-resolution checks, provider probe/call
  events and content-free dispatch provenance.
- Normalize third-party execution failure diagnostics to bounded content-free
  metadata before persistence, genericize external execution/probe exception
  text, and publish the provider failure-category set through the SDK.
- Add `orchestrator provider-plugins`,
  `inspect_project.provider_plugins`, plugin diagnostics in `doctor`, and a
  public `assert_provider_adapter_conforms` compatibility helper.
- Add non-core entry-point fixture coverage proving activation only after trust,
  unpinned-package inertness, version-drift failure, built-in collision failure,
  required-vs-optional SDK features and legacy profile-fingerprint compatibility.
- Clarify that in-process provider plugins are trusted controller code; worker
  isolation does not sandbox adapter implementation code.
- Reconcile roadmap, architecture, recovery and single-terminal documentation
  before closing the milestone.
- No runtime/HumanGate/jobs SQLite migration or TaskState/IntakeState schema bump
  is required solely for v0.13. Empty plugin configuration preserves historical
  profile fingerprints.
- Owner-reported live closure passed with a Fresh-Write isolated integration
  (`43 passed`, independent review, final `succeeded`) and a real temporary
  external Python distribution. The external lifecycle verified
  installed/unpinned inertness, exact-pin/untrusted inertness, explicit-trust
  loading/conformance, and `loaded != selected != dispatched`, with zero fixture
  provider dispatches.
- Cleanup additionally verified that restoring the exact former profile
  bytes/digest does not resurrect its old trust record: trust is a single current
  profile binding and explicit re-trust is required after returning from a
  different trusted digest.

## 0.12.2 — Physical read-only SQLite hardening

- Record the final v0.12.1 read-only closure E2E: legacy usage coverage and
  installed Skill synchronization passed without provider calls, HumanGates or
  logical persisted-state changes.
- Fix unconditional SQLite `PRAGMA user_version` restamping in runtime,
  HumanGate and jobs stores. Opening an already-current database no longer
  advances the SQLite file change counter merely to write the same version.
- Preserve supported database upgrade behavior: older readable databases are
  still stamped to the current version when an actual migration/open upgrade is
  required.
- Add jobs.sqlite3 to the persistence compatibility report and centralize its
  fail-closed version validation with the other runtime databases.
- Add regressions that reopen current state/gates/jobs databases and verify their
  SQLite header change counters remain unchanged.
- Keep persisted TaskState/IntakeState/HumanGate/artifact contracts and authority
  semantics unchanged.

- Final owner-reported v0.12.2 live read-only E2E passed on the accumulated
  runtime: repeated inspection left the complete SHA-256, SQLite header counters,
  user versions, mtimes, schema digests and row digests of state/gates/jobs
  databases unchanged, while legacy usage and Skill synchronization remained
  correct and no new provider/HumanGate/job/event/workspace effect occurred.
## 0.12.1 — Live migration E2E follow-up

- Record successful in-place v0.12 live E2E over an accumulated v0.x runtime:
  historical TaskState/IntakeState/Event/Artifact data remained inspectable and
  pre-existing file/row digests stayed unchanged.
- Preserve the successful single-terminal Start -> Execution -> Acceptance
  regression with isolated Codex implementation, Claude planning/review,
  `40 passed`, Artifact v2/Event v1 evidence and final `succeeded`.
- Fix legacy usage compatibility views: when durable TaskState calls exceed
  recorded usage calls, missing token/provider-time/cost telemetry is now
  `unknown` rather than known zero, while known subtotals are preserved.
- Add explicit usage `call_coverage` diagnostics for incomplete historical
  telemetry without rewriting historical artifacts or state.
- Keep a genuine zero-call task at known-zero usage and retain existing durable
  call-count budget enforcement.
- Document installed Agent Skill drift observed during live E2E and require
  explicit Skill re-export after upgrades.

## 0.12.0 — Contract & Migration hardening

- Add an explicit persisted-contract compatibility registry for TaskState,
  IntakeState, HumanGate, runtime events, Artifact metadata, usage/budget,
  provider provenance and recovery evidence.
- Keep supported historical TaskState v1-v7, IntakeState v1-v4, HumanGate v1 and
  Artifact v1 data readable without rewriting stored rows or immutable artifact
  bytes.
- Fail closed on malformed, non-integer or unknown persisted schema versions and
  unsupported SQLite user versions before authority/effect interpretation.
- Retain representative v0.x persistence fixtures and add compatibility
  regressions for authority defaults, immutable artifacts and recovery evidence.
- Introduce Artifact metadata schema v2 with stable controller-generated artifact
  ID, owner ID and creation timestamp while preserving v1 metadata compatibility.
- Expose runtime events through envelope schema v1 with stable sequence-derived
  event IDs and unchanged event payload semantics.
- Version newly written recovery evidence as schema v1 while read-migrating
  legacy v0.11 unversioned recovery artifacts only in memory after hash
  verification.
- Add `orchestrator persistence` and `inspect_project.persistence_compatibility`
  inspection surfaces, plus explicit upgrade/forward-compatibility/downgrade
  documentation.
- Keep runtime SQLite at user_version 2 and HumanGate SQLite at user_version 1;
  v0.12 does not require an in-place database rewrite.

## 0.11.0 — Recovery & Durability hardening

- Add durable pre-provider-dispatch root-snapshot checkpoints for guarded and
  isolated writable execution.
- Classify interrupted `running` tasks as retry-safe only when the controller can
  prove provider dispatch never started and the root worktree is unchanged.
- Make safe recovery explicit and non-executing: clean disposable workspaces,
  release only un-dispatched call reservations, atomically revoke old execution
  and provider-permission approvals, persist recovery evidence, and require a
  fresh execution approval.
- Fail closed on ambiguous provider/validator/shared-write/integration effects,
  workspace drift, and legacy interrupted rows without a v0.11 checkpoint.
  Recovery never automatically replays or rolls back the user's root worktree.
- Expose read-only recovery diagnosis through CLI task status and agent-facing
  `get_task`; `recover` remains operator-only.
- Mark HumanGate `applying` / `uncertain` records as effect-uncertain and
  explicitly non-replayable in gate diagnostics.
- Add content-free provider failure categories for authentication, quota,
  permission, configuration, protocol and generic provider-process failures
  without persisting raw provider stderr.
- Keep TaskState and runtime SQLite schema versions backward-compatible; harden
  task-row persistence and make recovery approval revocation transactional.
- Add crash-injection regressions for pre-dispatch safe recovery, post-dispatch
  ambiguity and interruption after root integration.
- Complete owner-reported live Claude Code E2E with real worker/provider process
  kills: pre-dispatch recovery returned to a fresh execution gate and succeeded;
  post-dispatch and post-integration interruptions failed closed without replay,
  and the integrated root change was not rolled back. Normal Start -> Execution
  -> Acceptance also succeeded after a timed-out Acceptance was re-requested
  with a new request ID.

## 0.10.4 — HumanGate transport observability

- Persist content-free HumanGate request/correlation metadata so host
  interoperability failures can be diagnosed without retaining form or provider
  content.
- Record gate/request/correlation IDs; serialized request/form/schema/preview
  byte counts; message char/byte counts; schema field/depth/object counts;
  preview field/array/depth counts; timeout duration; and send/response/timeout
  timing with elapsed milliseconds.
- Keep raw form messages, requested-schema bodies, preview bodies, arbitrary host
  error strings and provider/user content out of transport diagnostics.
- Preserve existing fail-closed behavior: timeout/cancel/disconnect never
  authorizes an effect and expired Acceptance leaves TaskState awaiting
  acceptance with no new provider calls or acceptance artifact.
- Add protocol regressions for content-free request-shape metrics and Acceptance
  timeout state integrity.
- Update the single-terminal documentation and packaged Skill so agents report
  the richer diagnostics without treating them as proof of human presence.
- Live A/B verification on 2026-10-03 completed the v0.10 kernel E2E on
  `claude-code 2.1.284`: Start, Execution and Acceptance HumanGates all
  returned correlated `accept` responses; Codex implementation, pytest
  (`26 passed`), independent Claude review, final `succeeded`, usage/budget
  evidence and artifact hash verification all completed successfully.
- The same kernel/profile/form schema showed intermittent host-side HumanGate
  timeouts on `codex-mcp-client 0.160.0` (Execution in one v0.10.4 run;
  Acceptance in an earlier run). Request/form sizes remained about 1.4–1.6 KiB
  with the same one-field schema, while Claude Code completed all three gates.
  Treat Codex as a host-interoperability follow-up rather than a v0.10 kernel
  blocker; current evidence does not distinguish UI non-presentation from a
  lost/unanswered response.
- `antigravity-client 1.0.0` continues to advertise form/url elicitation and
  receive `elicitation/create` but returns `action=cancel`; keep this recorded
  as a separate host-interoperability limitation.
- Close the v0.10 Usage Observability & Budget Policy milestone. Follow-up
  observations are non-blocking: attempt aggregation currently shares numeric
  attempt keys across Supervisor/task phases, and provider-call controller
  elapsed is intentionally distinct from task/budget wall-clock elapsed.

## 0.10.3 — Portable skill contract follow-up

- Bring the packaged `ai-orchestrator` skill in line with the v0.10.2 Usage
  Observability & Budget Policy implementation and reference documentation.
- Document the control-plane sequence from Provider/Model resolution through
  usage evidence and budget evaluation, and prohibit budget-driven provider,
  model, effort, validator or workflow fallback.
- Require preservation of `known` / `unknown` / `unsupported` telemetry
  states; prohibit zero-fill, text-length token estimation and hidden-reasoning
  inference.
- Document provider-reported versus controller-computed cost provenance,
  strict-budget fail-closed semantics and exact-exhaustion behavior.
- Document Codex, Claude and AGY usage evidence boundaries plus inspection via
  `inspect_project`, `get_task` and hash-verified usage/budget artifacts.
- Document stale pricing reset as part of bounded provider-adapter authority
  changes.
- Add regression coverage that pins these safety-critical statements in the
  packaged skill asset.

## 0.10.2 — Usage Observability & Budget Policy

- Add normalized per-call usage evidence with explicit `known` / `unknown` /
  `unsupported` token, provider-duration and cost states. Missing telemetry is
  never inferred from prompt/response length or silently treated as zero.
- Add deterministic aggregation by node, attempt, provider and exact model,
  while retaining per-call Provider Resolution / Model Variant / attempt
  provenance and controller-measured elapsed time.
- Add adapter usage descriptors and conservative extraction boundaries: Codex
  `turn.completed` JSONL token counters, Claude JSON usage/API-duration/
  provider-cost fields, and opportunistic AGY counters without claiming a stable
  strict-budget schema.
- Add trusted `policy.budget` limits for provider calls, controller/provider
  elapsed time, exposed token dimensions, exact provider/model call counts and
  attributable cost. Existing `max_agent_calls` / `task_timeout_seconds`
  remain hard ceilings.
- Fail closed before dispatch when a strict constrained metric cannot be proven
  for the selected provider/model. Exact exhaustion blocks the next provider
  effect; numeric overrun or lost proof after a call fails before the next
  effect. No budget path silently changes provider, model, effort, validator or
  workflow.
- Carry Supervisor usage across clarification rounds and into TaskState v7 so
  task accounting does not reset at Start confirmation. IntakeState v4 freezes
  the same evidence in the immutable Supervisor artifact/scope.
- Add exact provider-slot/model pricing rules with mandatory source, version and
  effective-time provenance. Provider-reported cost takes precedence;
  controller-computed cost uses decimal arithmetic only when all configured
  rate-bearing usage dimensions are known.
- Invalidate pricing metadata for a provider slot when its adapter is changed,
  alongside existing adapter-specific executable/model/effort resets.
- Persist hash-verified `usage` and `budget` artifacts, expose live summaries
  through `get_task` and adapter/policy capability data through
  `inspect_project`.
- Include material usage/budget scope in Start, Execution and Acceptance
  HumanGate previews without weakening existing profile/worktree/control/effect
  bindings.
- Preserve historical profile trust when the new budget/pricing settings are
  absent; explicit budget/pricing changes are normal profile-authority changes.
- Add v0.10 regression coverage for unknown telemetry, pricing provenance,
  aggregation, strict enforcement, no-fallback behavior, adapter parsers and
  HumanGate/MCP visibility.

## 0.9.2 — HumanGate interoperability diagnostics follow-up

- Persist content-free MCP HumanGate transport diagnostics in the gate ledger:
  client name/version, negotiated protocol, advertised form/url elicitation
  capabilities, form-support decision, elicitation-send state and terminal
  response outcome/action.
- Distinguish explicit host cancel/decline, host protocol error, timeout,
  originating-request cancellation and disconnect without storing form content
  or provider/user payloads.
- Expose the diagnostics through HumanGate results and `orchestrator gate G-ID`,
  and include negotiated host capability data in `inspect_project`.
- Remove CLI-authority fallback guidance when form elicitation is unsupported;
  a failed HumanGate must not silently downgrade to another authority channel.

## 0.9.2 — alpha

- Mark AGY Supervisor/Planner/Reviewer headless use as conditional support rather
  than unsupported. These read-only roles may execute when the operator's AGY
  native scoped permission policy is sufficient.
- Add `provider_compatibility` to `inspect_project` and provider-change previews.
  AGY read-only roles report `conditional_native_permissions`, including the
  explicit boundary that Orchestrator does not modify or attest the sufficiency
  of the user's AGY permission policy.
- Keep conditional compatibility non-blocking: provider resolution and provider
  changes remain allowed. Actual AGY native permission denial still fails closed
  with the adapter-sanitized diagnostics introduced in v0.9.1.
- Update the portable Skill/MCP guidance so a permission denial stops the current
  flow. The host must not rewrite the task with phrases such as "do not use shell"
  and automatically retry to work around provider-native permission policy.
- Keep `--dangerously-skip-permissions` explicit, task/attempt-scoped authority;
  it is not inferred from a denial and is not a Supervisor/Planner intake remedy.
- Record v0.9 as complete after live Claude-only Fresh-Write validation and the
  AGY interoperability boundary analysis. Future AGY compatibility improvements
  can be added at the adapter boundary without reopening v0.9 architecture.

## 0.9.1 — alpha

- Run Supervisor, Planner and Reviewer provider calls from disposable project
  snapshots that exclude `.orchestrator` and ignored ambient files; reject writes
  to those read-only snapshots and delete them after each call.
- Keep AGY headless permission failures fail-closed. v0.9.1 does not auto-enable
  `--dangerously-skip-permissions` for read-only phases merely to make a provider
  accept shell commands.
- Expand review independence beyond vendor-family separation: a reviewer is
  independent when it uses a different provider family, or when both same-family
  executions have explicit, unequal provider-local model IDs. Effort differences
  alone do not count.
- Preserve historical dynamic-routing diversity: unbound reviewer routing still
  prefers a different provider family, while fixed/task-scoped bindings may use
  distinct models from the same vendor.
- Align bounded provider-adapter changes with the same contract: profile-change
  preview/apply validates provider capability resolution but defers review
  independence to task preflight, because adapter changes reset model/effort and
  later task/node overrides may supply the distinct model IDs.
- Add regression coverage for same-family/different-model review, same-model
  rejection, and read-only control-directory isolation.
- Add intake-scoped Supervisor model/effort override on `propose_task`, freeze
  its provider/model/effort provenance into schema-v3 intake state and Start
  HumanGate scope, and keep project profile authority unchanged.
- Make Supervisor proposal normalization use the same model-aware review
  independence contract as task preflight instead of excluding a fixed
  same-family reviewer before Model Variant Resolution.
- Add content-free provider dispatch provenance. Task agent calls accumulate a
  hash-verified `provider_provenance` artifact with the exact RunRequest
  model/effort/runtime options plus workspace mode; Supervisor records the
  equivalent evidence on the intake.
- Record read-only workspace isolation evidence: outside-project placement,
  absence of `.orchestrator`, unchanged verification and cleanup completion.
- Add an explicit language boundary to the portable Skill/MCP guidance:
  control-plane interaction stays English while user-facing progress/errors/results
  follow the user's current conversation language.
- Remove the remaining stale family-preexclusion from capability/runtime reports
  and legacy fixed-role resolution. Fixed same-family reviewers are now reported
  as valid candidates and are evaluated for independence only after Model Variant
  Resolution; dynamically routed reviewers retain the different-family preference.
- Make `serve` default to single-terminal operation. `--single-terminal`
  remains backward-compatible; `--legacy-terminal` is the explicit opt-out.
- Add adapter-sanitized AGY permission-denial diagnostics. Supervisor failures
  expose them through `get_intake.provider_failure_diagnostics`; task-node
  failures expose `get_artifact(kind=provider_failure)`. Raw commands, command
  arguments, provider messages and free-form denial reasons are not retained.

## 0.9.0 — alpha

- Add a versioned adapter runtime-option registry and a separate Model Variant
  Resolution stage after deterministic Provider Resolution.
- Resolve provider-local model/effort with explicit precedence:
  task/node override > trusted profile setting > adapter default.
- Freeze exact model/effort/runtime-option provenance per workflow node and in
  TaskState v6, approval scope, provider probes and call-start audit events.
- Add explicit task/node-scoped runtime overrides without mutating persistent
  project profile authority. HumanGate start/execution summaries show requested
  overrides and the exact resolved provider/model/effort before execution.
- Fail closed when an enumerated adapter rejects a requested model/effort or when
  frozen runtime-option metadata changes after task binding.
- Let adapters report enumerated, unsupported or honest pass-through selection.
  Built-in Claude, Codex and Antigravity adapters do not fabricate vendor model
  catalogs; they expose controllable model/effort pass-through with limitations.
- Expose runtime-option and Model Variant schemas through the CLI and include
  runtime-option inspection in the MCP project report.
- Keep model identity and effort out of semantic capabilities, preserve no
  implicit fallback, and keep persistent profile model/effort changes under the
  existing trust/authority boundary.


## 0.8.10 — alpha

- Add atomic multi-slot provider adapter change-sets for conversational swaps.
- Validate only the final combined provider profile, so policy-valid swaps are
  not rejected because either sequential half-swap would temporarily violate
  cross-provider review separation.
- Add read-only `preview_provider_change_set` and dedicated
  `request_provider_change_set` HumanGate. One confirmation binds every
  before/after adapter change and the resulting profile digest.
- Apply the complete provider mapping with one atomic config replacement,
  revalidate the final profile immediately before the effect, verify the exact
  resulting digest, and trust only that digest.
- Reset executable/model/effort overrides independently for every changed
  provider slot so vendor-specific settings never cross adapter boundaries.
- Preserve the existing single-slot provider APIs and audit events as
  compatibility wrappers over the new change-set engine.
- Keep binding cleanup as a separate HumanGate; active task/intake bindings still
  block both single-slot and multi-slot provider authority changes.


## 0.8.9 — alpha

- Render HumanGate forms as compact, operation-specific summaries instead of
  dumping the complete bound preview JSON into the client UI.
- Keep the full preview, task state, evidence and control snapshots unchanged in
  the persisted gate and scope revalidation; only presentation is compacted.
- Make high-risk AGY provider-permission forms show the dangerous flag, scoped
  task/attempt/provider nodes, broad auto-approval effect, remaining controller
  protections, and the fact that execution approval is still separate.
- Keep provider-change before/after adapter, resulting trusted profile digest,
  binding-cleanup exact IDs/no-rollback semantics, start workflow/ownership, and
  execution/acceptance essentials visible without client-side expansion.
- Limit one binding-cleanup confirmation to 12 exact IDs so no target is hidden
  behind UI folding; larger cleanups must be confirmed in batches.


## 0.8.8 — alpha

- Add content-free provider tool telemetry for Antigravity stream-json calls.
  Successful and failed calls record only tool names plus aggregate terminal
  DONE/ERROR/other call counts.
- Never persist AGY tool parameters, target paths, command lines, prompts, tool
  outputs, error messages, response bodies or conversation IDs in telemetry.
- Persist `provider.tool_telemetry` from the controller thread after provider
  execution, including guarded/parallel calls, so telemetry does not introduce
  cross-thread SQLite writes.
- Keep `provider.execution.failed` as the separate failure diagnostic event;
  telemetry is observational and does not weaken denied-action, structured-output,
  sandbox, write-ownership or HumanGate enforcement.
- Add regression coverage for successful and failed guarded calls and for
  redaction-by-construction of sensitive tool fields.


## 0.8.7 — alpha

- Add explicit lifecycle terminal states for unfinished authority bindings:
  tasks may become `abandoned` and unconsumed intakes may become `withdrawn`.
- Add read-only `preview_binding_cleanup` and dedicated
  `request_binding_cleanup` HumanGate. Cleanup is exact-ID scoped, audited and
  atomic across all selected task/intake rows.
- Binding cleanup never deletes task/intake history, artifacts or task files and
  never rolls back existing workspace changes. The confirmation preview states
  this explicitly.
- Reject cleanup of running tasks/intakes and already-terminal bindings.
- Change provider-change preview to return structured `ready` / `blocked_by`
  data instead of forcing agents to parse an exception string. The actual
  provider-change HumanGate remains blocked until all unfinished bindings are
  resolved.
- Preserve dedicated separation between binding-cleanup authority and provider
  configuration authority: cleaning bindings never implicitly changes a
  provider, and provider-change confirmation never implicitly abandons work.
- Add regression coverage that an ordinary approved review with no blockers
  proceeds to acceptance without entering a repair attempt.


## 0.8.6 — alpha

- Add bounded authority-control for provider adapter changes in single-terminal
  mode. Agents may preview one existing provider slot's adapter change, but only
  a dedicated HumanGate may apply the exact diff and trust the resulting profile
  digest.
- Reset adapter-specific executable/model/effort overrides during an adapter
  switch and validate provider capabilities, role resolution, workflow authority,
  current profile trust, and absence of active task/intake bindings before the
  confirmation can be prepared.
- Add a separate task/attempt-scoped HumanGate for explicit AGY
  `--dangerously-skip-permissions`. Execution approval never implies this
  provider-native broad permission.
- Bind broad permission grants to task ID, attempt, resolved AGY workflow nodes,
  profile digest, execution scope, and exact worktree snapshot. A worktree change
  or repair invalidates the grant and requires a fresh permission confirmation.
- Pass the dangerous AGY flag only when the persisted grant and approval record
  match the executing node. Continue using sandbox + guarded private worktrees,
  exact write ownership, validators, review, and final acceptance.
- Keep arbitrary config/policy edits, direct trust, validator registration and
  other authority changes outside the agent-facing mutation surface.


## 0.8.5 — alpha

- Treat a non-empty Antigravity terminal `denied_actions` list as an explicit
  provider permission failure even when AGY reports `status=SUCCESS` and exits
  zero.
- Record only denied action types/counts in safe diagnostics; never persist tool
  parameters, target paths, prompts or provider response content.
- Do not auto-enable `--dangerously-skip-permissions`. Current AGY headless
  permission policy requires native pre-authorization for writable tools, and
  the CLI does not expose a verified per-run scoped settings file that the
  Orchestrator can safely synthesize.


## 0.8.4 — alpha

- Guard every Workflow Schema writable implementer with exact task
  `allowed_paths` in a private runtime worktree, even when the workflow declares
  `workspace: shared`. Provider edits are integrated into the project only
  after result-contract and write-ownership validation succeeds.
- On provider failure, blocked output, malformed structured output, or ownership
  violation, discard the private workspace so project files are not partially
  mutated by the failed attempt.
- Reuse the v0.7 deterministic patch/integration path for single guarded writers;
  legacy/manual tasks without an exact allowed-path contract retain historical
  shared-worktree behavior.
- Extend isolated workspace seeding to Git repositories without an existing HEAD,
  so the safety upgrade does not require a first commit for exact-scope tasks.
- Record provider execution failure diagnostics as content-free shape metadata
  (status, envelope keys, types, JSON keys and byte counts), never raw prompts or
  provider response content.
- For AGY 1.2.14 response fallback, allow only the observed provider-owned
  presentation keys `toolAction` and `toolSummary` to be discarded before
  validating the exact requested result contract.


## 0.8.3 — alpha

- Add a fail-closed compatibility path for Antigravity CLI 1.2.14 live
  headless runs that report `status=SUCCESS` but omit `structured_output`
  despite `--json-schema`.
- When that field is absent, accept `result.response` only if it is strict JSON
  and validates against the exact requested Pydantic result contract.
- Continue rejecting natural-language, malformed JSON, arrays, wrong outcomes,
  and schema-invalid response payloads.
- Preserve the preferred documented `structured_output` path when AGY emits it.


## 0.8.2 — alpha

- Fix provider doctor/preflight compatibility with CLIs that emit successful
  `--help` text on stderr rather than stdout.
- Specifically fixes Antigravity CLI 1.2.14 being incorrectly reported as
  missing all required headless flags even though the flags are present.
- Add a regression reproducing AGY 1.2.x help-on-stderr behavior.


## 0.8.1 — alpha

- Add a built-in Provider Adapter v2 for Google Antigravity CLI (`agy`).
- Use official headless `stream-json` input/output so prompts travel on stdin
  rather than argv and the adapter consumes exactly one terminal result event.
- Enforce AGY `--json-schema` structured output and fail closed unless the
  terminal envelope reports `status=SUCCESS` and includes `structured_output`;
  a zero process exit code alone is never treated as success.
- Run AGY with terminal sandboxing enabled. Implementer calls use
  `--mode=accept-edits`; non-write phases use `--mode=plan`.
- Never use `--dangerously-skip-permissions`; normal Antigravity workspace and
  sandbox permission policy remains in force.
- Expose adapter family `google` and the existing repository-analysis/planning/
  code-edit/test-authoring/review/supervision semantic capability set.
- Keep Codex and Claude adapters unchanged. Projects opt into AGY through normal
  provider/profile configuration and re-trust; no task or workflow needs vendor
  names embedded in its DAG.


## 0.8.0 — alpha

- Let the Supervisor propose a bounded task-scoped Workflow Schema v1 DAG when
  no already-trusted template suitably expresses a non-advisory task.
- Keep model-authored DAGs ephemeral: bind the exact workflow into the immutable
  intake artifact, Start HumanGate and TaskState v5 without mutating
  `.orchestrator/config.yaml` or project trust.
- Validate proposed graphs under existing authority before confirmation:
  registered roles/capabilities/validators only, Workflow Schema invariants,
  cross-provider review policy, node/call limits and isolated `write_paths`
  within exact task `allowed_paths`.
- Make ordinary agent UX workflow/provider-neutral: when the user does not
  explicitly select a trusted workflow, the Supervisor may reuse trusted
  authority or propose task-scoped structure including safe isolated parallelism.
- Allow conversational revision of an unconfirmed proposal through `reply_to`;
  successful revision supersedes the older intake so stale Start confirmation
  cannot register it.
- Add operator-only `workflow-candidate` / `workflow-save` commands for
  promoting a successfully accepted adaptive workflow into project configuration.
  Candidate scope binds accepted task evidence; save records template
  version/provenance and requires normal profile re-trust.
- Separate executable workflow semantic digests from template metadata while
  retaining explicit version/provenance in the trusted profile fingerprint.
- Preserve v0.7 profile fingerprints when new template metadata remains at its
  default; existing trusted/manual tasks continue using TaskState v4.
- Add TaskState v5 only for embedded adaptive workflows and regressions covering
  proposal, HumanGate binding, revision, authority rejection, promotion and
  versioned template replacement.
- Add `docs/ADAPTIVE_ORCHESTRATION.md` and update the packaged Agent Skill/MCP
  instructions so users normally need not manipulate workflow/DAG/parallel or
  provider configuration.


## 0.7.0 — alpha

- Add opt-in isolated Git worktrees for writable Workflow Schema v1 nodes using
  `workspace: isolated` and exact per-node `write_paths`.
- Reject overlapping ownership for independent isolated writers at workflow
  compile time and require every node's ownership to fit the task's
  `allowed_paths` contract at preflight.
- Add bounded concurrent provider scheduling through
  `policy.max_parallel_workers` (default `1` for v0.6-compatible sequential
  behavior) while keeping controller state and SQLite transitions serialized.
- Seed every isolated branch from the exact approved project snapshot, preserve
  dirty/nonignored project state in a temporary seed commit, and record branch
  patch provenance.
- Integrate successful branch patches in deterministic workflow order inside a
  separate worktree; apply one aggregate patch to the user's worktree only if
  the root snapshot/control/protected state is still unchanged.
- Run registered validators and fresh review after integration. A branch-local
  success never substitutes for integrated validation.
- Bind the full isolated execution batch, ownership and worker bound into the
  execution approval scope/HumanGate context.
- Cancel sibling providers on failure where supported, prevent partial sibling
  integration, clean worktrees on completion/failure, and clean stale worktrees
  during conservative `recover` without replay.
- Preserve existing v0.6 profile and workflow digests when only v0.7 default
  fields are present.
- Add regressions for real concurrent overlap, worker bounds, ownership
  violations, fail-closed provider failure, integrated validation and recovery.


## 0.6.2 — alpha

Live verification (owner-reported, Claude Code):

- Verified task-scoped `workflow_ref=branched-review` while the project default remained built-in `build-review`, with no config edit or re-trust during the task.
- Verified selection source `requested`, deterministic five-node execution, one execution HumanGate, allowed-path write-set, **45 passing pytest tests**, independent review and final `succeeded`.
- Recorded the v0.6.1 dynamic-resolution approval-scope fix and custom branched-DAG live runs as the sequential baseline before v0.7 isolation/parallelism.


- Add a trusted workflow registry with built-in `build-review` and `branched-review` templates.
- Allow task/intake-scoped `workflow_ref` selection without mutating `.orchestrator/config.yaml` or changing the profile digest.
- Keep new workflow installation as trusted profile authority; task selection cannot install, modify or trust workflow definitions.
- Freeze selected workflow ID/digest/source into intake/start scope, TaskState provenance and HumanGate previews.
- Let the Supervisor propose only controller-advertised trusted workflows, while an explicit user/controller workflow_ref wins over model suggestions.
- Add `orchestrator workflows`, `workflow --ref`, `ask --workflow`, `create --workflow` and MCP registry inspection.
- Add the built-in sequential branched template: two complementary planner analyses converge on one gated implementation, deterministic validation and independent review.
- Preserve v0.6.1 profile fingerprints and existing custom `branched-review` projects; project-defined trusted workflows may continue to shadow that new package template.


## 0.6.1 — alpha

- Fix execution approval scope drift for dynamically resolved workflow nodes.
- Revalidation of a frozen candidate/priority provider now preserves the original routing provenance instead of exposing the internal `force_provider` check as `source: fixed`.
- Add candidate- and priority-routing regressions asserting repeated preflight keeps the execution approval scope stable and a single approval proceeds to implementation.


## 0.6.0 — alpha

- Add Workflow Schema v1 contracts for agent/validator nodes, typed artifact inputs/outputs, dependencies, execution gates, write semantics, run modes and bounded repair paths.
- Compile/validate DAGs before execution: duplicate/cyclic/unknown dependencies, artifact type/ancestry errors, unsafe advisory paths, missing write/validator/reviewer stages and cross-provider independence fail closed.
- Move new tasks to TaskState schema v4 with workflow ID/digest/order/current node and per-node execution/provider provenance.
- Execute ready DAG nodes deterministically and sequentially; declaration order is the stable tie-breaker for independent nodes.
- Resolve Provider Adapter v2 capabilities per agent node, including branched workflows with multiple nodes using the same role.
- Pass only declared typed artifacts to downstream nodes; preserve validator/write-set/fresh-review semantics.
- Preserve execution HumanGates at writable nodes and final acceptance; every repair resets only the configured downstream subgraph and requires a fresh execution scope.
- Keep `build-review` as a built-in Workflow Schema v1 DAG, preserving existing profile configuration and v1-v3 persisted task compatibility.
- Add `orchestrator workflow`, workflow JSON schemas, MCP workflow inspection, custom branched-DAG tests and provenance tests.
- Keep v0.6 intentionally single-worker/sequential: no writable parallelism, isolated worktree scheduling or automatic workflow generation.


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
