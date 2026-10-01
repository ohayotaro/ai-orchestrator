# Changelog

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
