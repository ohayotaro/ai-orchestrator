# E2E evidence and repeatable smoke testing

## Reported live v0.1 run — 2026-09-29

The repository owner supplied local status output showing `add-multiply-v6` completed on macOS with Python 3.13, Claude Code 2.1.284 and Codex CLI 0.154.0, after updating to commit `20674080b94bdc85b6fdf5b1876cb1671717669f`.

The reported result was `succeeded`, phase `accept`, attempt 1, model calls 3, cumulative execution time approximately 55.46 seconds and no error. Plan, execution, validation, review and human acceptance artifacts were recorded. The task added multiplication to a minimal calculator and retained its addition behavior. The reviewed snapshot reported was `1ad5783cd14d2a8016e91b3eb7454ff3f161098265685dc771f56550e0921b4d`.

This is an owner-reported live happy-path result, not a run performed in the implementation environment. Raw runtime artifacts remain in the owner's local fixture; they were not independently fetched in this v0.2 implementation session. Actual model IDs were not recorded in the supplied status; the CLI defaults should not be presented as a known model identity. The measured duration is one run's execution accounting, not a performance benchmark.

The sequence demonstrated Claude planning, an explicit execution gate, Codex edits, deterministic pytest evidence, a fresh Claude review invocation and human acceptance. It did not establish production isolation, general correctness, provider-independence statistics, model diversity benefits or v0.2 Supervisor compatibility.

## What the live iterations exposed

Finder `.DS_Store` changes could affect a worktree fingerprint. The kernel already compared content snapshots before/after a call and excluded its `.orchestrator` namespace; an untracked task JSON file alone was not evidence of a planner mutation. `.DS_Store` was explicitly excluded in a v0.1 fix; v0.2 also names mutated paths and checks non-runtime control files separately.

One validator interpreter path referred to a virtualenv that did not exist. It was not proof that filtered environments cannot execute relative paths. v0.2 resolves/diagnoses project-relative, PATH and absolute executables before model calls while preserving virtualenv symlinks.

Python imports/pytest created bytecode in nonignored directories. v0.2 disables Python bytecode in the validator environment, retains explicit pytest cache configuration, and provides constrained generated-output declarations. Typos such as `no:casheprovider` can leave a plugin enabled even when tests pass; a passing test alone does not prove every requested option took effect.

A real Claude reviewer returned approved plus informational findings. The v0.1 outcome-only fix allowed completion. v0.2 separates blocking findings from observations and tests both non-blocking approval and contradictory approval-with-blockers.

## Offline v0.2 wire E2E

`tests/test_v02_cli_e2e.py` runs executable CLI shims via the real adapters, argument builders, stdin, structured schemas, persistence, approvals and subprocess runner. It also executes real pytest in a temporary Git project. Both Codex-implementation/Claude-review and the inverted implementation/review configuration go through ask, proposal confirmation, planning, explicit execution approval, validation, review and human acceptance.

The shims are deterministic test fixtures, not Claude/Codex models. No credentials or billable calls are used. Unit/integration tests additionally cover malformed output, untrusted/stale proposals, unknown validators, unsafe environment/path declarations, file mutations, budget/clarification limits, old task compatibility and interactive approval refusal for pipes.

## Live v0.2 smoke test still required

Do not mark the new Supervisor and role schemas live-verified solely because the offline suite or v0.1 run passed. Use a fresh disposable Git fixture, the actual installed provider CLIs and nonproduction credentials. Keep the orchestrator checkout itself outside the fixture.

Prepare a minimal `calculator.py`, an initial addition test, a project-local Python 3.11+ environment with pytest, and a `.gitignore` covering `.venv/`, Python/pytest caches and `.DS_Store`. Initialize the profile once, then register and explicitly check its actual validator:

```bash
orchestrator validator add pytest -- .venv/bin/python -B -m pytest -q -p no:cacheprovider
orchestrator doctor
orchestrator trust --by "$USER" --ack-local-execution
orchestrator validator check pytest
orchestrator ask "Add multiply(a,b) and regression tests; preserve add" --task-id multiply-v02
```

Inspect the proposed task. Confirm its exact intake scope, inspect the plan and approve execution. Continue to review/acceptance only if the runner and concrete diff support it. A straight-through ask path normally records four model calls (Supervisor plus three execution roles) and six artifact kinds (Supervisor, plan, execute, validation, review, acceptance). A valid repair/clarification may use more within budget; call count alone is not a pass/fail oracle.

Record CLI versions, commit, effective profile digest, final status, runner evidence, review blockers/observations and acceptance snapshot. Never publish credential values or raw confidential prompts. Keep explicit negative-path tests separate from the live happy-path claim; do not deliberately trigger destructive external actions to test a local guard.


## Owner-reported v0.2 live path

The conversation on 2026-09-29 supplied output for `subtract-v02-e2e` showing
schema_version 2, intake `I-56d553a7527e`, four agent calls, one attempt,
`awaiting_acceptance`, no error, Supervisor/plan/execute/validation/review artifacts,
and a separate manual pytest run reporting three passed. This verifies the shown
live path through review; that output alone does not prove final acceptance.

## v0.3 verification scope

New offline tests launch the actual MCP stdio frontend and a separate worker as
processes, with deterministic CLI-shaped provider shims and real pytest. Both
Claude-implementation/Codex-review and the reverse bindings are exercised. Human
gates are simulated by explicit operator CLI invocations, not exposed as MCP tools.
Protocol-wire and queue tests cover invalid inputs, authority rejection, scoped
state changes, idempotency, cancellation, limits and interruption. An optional
independent official MCP SDK client smoke test is included and enabled in CI.

This does not certify authenticated v0.3 operation from the real Claude Code or
Codex interactive clients. Antigravity/Grok integration is not validated. Do not
replace this limitation with a generic claim that all MCP clients were tested.


## Owner-reported live v0.4 single-terminal E2E (2026-09-30)

The owner reported a Claude Code single-terminal run for
`absolute_difference(a,b)`: start, execution and acceptance were confirmed in
host forms; the automatic worker completed implementation; deterministic pytest
reported 14 passing tests; the fresh reviewer approved without blockers; and the
canonical task reached `succeeded`. No manual worker/start/approve/accept
terminal was needed for the successful path.

The first three start attempts were declined while the boolean form remained
effectively false, motivating v0.4.1's explicit enum Yes/No selection. The
frontend also ran a read-only shell diff because the reviewer lacked git access;
v0.4.1 adds controller write_set evidence so that extra shell verification is
unnecessary.


## Owner-reported live v0.4.1 frontend E2E — Claude Code and Codex (2026-09-30)

The owner subsequently ran the v0.4.1 single-terminal path from both supported
frontends against the same calculator fixture, sequentially rather than in
parallel. These are owner-reported live-client observations; the repository did
not independently capture the host sessions or authenticate who selected the
forms.

### Claude Code

Claude Code delegated a `clamp(value, minimum, maximum)` change through the
portable Skill and MCP server. The start, execution and acceptance gates rendered
the new explicit Yes/No choice and were accepted in the host. The managed worker
completed implementation, the registered pytest validator reported **22 passed**,
the fresh reviewer reported no blocking findings, the write-set was limited to
`calculator.py` and `tests/test_calculator.py`, and canonical task status
reached `succeeded`.

The run no longer required a manual worker, operator-terminal start/approve/accept,
or a user `continue` turn after bounded waiting. Claude Code did, however, run
one redundant read-only shell inspection using `sed` against the two target
files after Orchestrator evidence was already available. It did not rerun pytest
or perform a git diff/status audit.

### Codex

Codex delegated a `sign(value)` change through the same single-terminal flow.
It used `wait_job` for proposal/planning/execution waits, all three host gates
were accepted, the managed worker completed the change, pytest reported
**25 passed**, the independent reviewer reported no blockers, and the final task
status reached `succeeded`.

The acceptance form visibly included the task/acceptance criteria, registered
pytest validator, exact `allowed_paths`, and the controller-generated
`write_set`. The reported write-set matched exactly:
`calculator.py` and `tests/test_calculator.py`. Codex nevertheless ran one
redundant read-only `git status --short && git diff -- calculator.py
tests/test_calculator.py` after the acceptance request.

### Result and follow-up

Together these runs provide live evidence that v0.4.1's explicit Yes/No gates,
automatic separate worker, bounded `wait_job`, exact allowed-path contract,
write-set evidence, deterministic validation, fresh review and final acceptance
work from both Claude Code and Codex frontends. They do not establish a
cryptographic human identity boundary, certify other MCP hosts, or prove that
frontends will never use unrelated shell capabilities.

The redundant Claude `sed` and Codex `git status/diff` checks showed that the
earlier Skill wording was too narrow. The packaged Skill now explicitly treats
write_set + validation + review as canonical Orchestrator evidence and forbids
Read/sed/grep/git/shell/test re-inspection solely to double-check that evidence,
unless the user explicitly asks for independent verification.


## v0.6 verification target

Offline tests cover Workflow Schema validation, deterministic topological order,
advisory-node skipping, built-in build-review compatibility, bounded downstream
repair, per-node provider provenance, typed artifact passing and a small branched
DAG executed sequentially.

The first live v0.6 E2E should verify that an unchanged calculator project still
reaches `succeeded` through the built-in DAG and exposes TaskState schema v4
workflow provenance. A subsequent custom branched workflow E2E can demonstrate
two read-only planning nodes converging on one gated implementation. Neither test
should claim parallel execution.


## v0.6.2 live E2E target

After offline CI, verify from an unchanged trusted calculator profile that
`inspect_project.workflows` lists package `branched-review`, then submit a
single-terminal task with `workflow_ref=branched-review` **without editing
config.yaml or re-running trust**. Expected provenance is TaskState v4 with
`workflow_id=branched-review`, selection source `requested`, sequential
`analyze_a -> analyze_b -> implement -> validate -> review`, one execution
HumanGate, write-set/validator/reviewer evidence and final `succeeded`.


## Owner-reported live v0.6 / v0.6.2 workflow E2E (2026-09-30)

The owner completed the sequential workflow/DAG live E2E series from Claude Code
against the calculator fixture. These observations are owner-reported host runs;
the repository does not cryptographically authenticate who selected the forms.

### v0.6 built-in and custom DAG

A built-in `build-review` task reached `succeeded` with TaskState schema v4.
The implementer dynamically resolved to the engineering/Codex provider with
`source: candidates`, and start/execution/acceptance HumanGates, write-set,
pytest validation and independent Claude review all completed.

That run exposed one approval-scope regression: revalidating the frozen dynamic
provider temporarily surfaced `source: fixed` in the role-level compatibility
view. v0.6.1 fixed the provenance rewrite. A repeat live run then showed one
execution approval flowing directly into implementation while both role-level
and node-level implementer provenance remained `source: candidates`.

The owner then installed a temporary project-defined `branched-review` workflow
for v0.6 DAG testing. The live task executed deterministically and sequentially:

```text
analyze_a -> analyze_b -> execution approval -> implement -> validate -> review
```

Both analysis artifacts were persisted, the Codex implementer changed only the
two allowed calculator paths, validation passed, Claude review approved, and all
five workflow nodes plus final acceptance reached `succeeded`. This validates
branched DAG semantics but does not claim parallel execution.

### v0.6.2 task-scoped trusted workflow selection

After restoring the project default to the built-in `build-review` and
re-establishing that baseline once, the registry reported:

- `build-review`: built-in, default;
- `branched-review`: built-in, non-default.

A new single-terminal task explicitly passed
`workflow_ref=branched-review` without editing `.orchestrator/config.yaml`
and without re-running trust. The task recorded:

- workflow ID: `branched-review`;
- workflow selection source: `requested`;
- project default: still `build-review`;
- node order: `analyze_a -> analyze_b -> implement -> validate -> review`;
- one execution HumanGate after both analyses;
- write-set limited to the two allowed calculator files;
- pytest: **45 passed**;
- independent review: approved;
- final task status: `succeeded`.

The reported profile digest stayed constant through the task. After the run the
registry still showed `build-review` as the built-in default and
`branched-review` as a built-in non-default template. The post-run
`.orchestrator/config.yaml` SHA-256 was
`4edb310347f2efa0824610b58a3473a42071c680faf7251967513f891eb47fbd`.
A pre-run byte hash was not retained in the transcript, so this hash is recorded
as post-run evidence rather than claimed as an independently verified before/after
byte comparison.

### v0.6 baseline before v0.7

Together with the offline CI suite, the live runs establish the v0.6.x baseline
needed before isolated parallel execution:

- Workflow Schema v1 / TaskState v4;
- deterministic sequential DAG execution;
- typed branched analysis artifacts;
- per-node Provider Resolution and frozen provenance;
- stable execution approval scope across provider revalidation;
- HumanGate/write-set/validator/independent-review/acceptance boundaries;
- task-scoped selection of already-trusted workflow authority without profile
  mutation or re-trust.

v0.7 may build parallel scheduling on this baseline, but must preserve these
authority and provenance properties while adding workspace isolation.


## Owner-reported live v0.7 isolated parallel E2E (2026-09-30)

The owner completed the first live v0.7 isolated writable-parallel E2E from
Claude Code 2.1.284 against the calculator fixture. The selected trusted
`parallel-review` workflow used Claude for planning/review and Codex CLI 0.159.0
for two independent implementation nodes.

The task `is-even-v07-parallel` added `is_even(value)` and its pytest coverage.
TaskState schema v4 recorded `workflow_id=parallel-review`,
`workflow_selection_source=requested`, exact task `allowed_paths` for
`calculator.py` and `tests/test_calculator.py`, and
`max_parallel_workers=2`. Start, execution and acceptance were all applied
through Claude Code host elicitation.

After the execution HumanGate, the controller prepared one isolated workspace
for `implement_code` owning only `calculator.py` and another for
`implement_tests` owning only `tests/test_calculator.py`. Both nodes shared
the same seed snapshot
`ee06c704ddc13ff28a2f257763a3549809307da75418fa1b8dd1c16794751b79`.
Their controller start events were approximately 0.6 ms apart. A separate
operator observation at 2026-09-30 22:23:30 local time saw two simultaneous real
`codex exec` processes (PIDs 30865 and 30866), providing direct live evidence
that the provider calls overlapped rather than merely executing two isolated
nodes sequentially.

Each worker produced a disjoint verified patch with no ownership violations:
`implement_code` changed only `calculator.py`, while `implement_tests`
changed only `tests/test_calculator.py`. The controller then prepared and
applied one aggregate integration patch, producing integrated snapshot
`c9d8081e7bf504a023a9f6a32c7e8d7aaaca84a7f7970c59b30683a292acaff5`.
Both write-set artifacts and subsequent review provenance refer to that integrated
state.

The isolated node worktrees and integration workspace were cleaned before
validation. The registered pytest validator then ran against the integrated
project and recorded `passed: true`. A fresh Claude reviewer subsequently
approved the same integrated snapshot. The task completed on attempt 1 with no
repair, no error, five model calls, and final status `succeeded` after the
acceptance HumanGate.

This live run verifies the intended v0.7 happy-path invariant for cooperating
workers: two writable provider calls can overlap without sharing a writable
worktree; exact per-node ownership is enforced; successful branch patches are
integrated deterministically; deterministic validation and independent review
occur only after integration; temporary workspaces are cleaned; and the existing
HumanGate/acceptance boundaries remain in force.

The observation is owner-reported rather than independently captured by the
repository, and host elicitation still does not cryptographically attest human
presence. It does not establish OS-level isolation against a hostile same-user
process, failure/cancellation recovery under real providers, conflict behavior
under live concurrent edits, or performance/scaling beyond this two-worker run.

## Owner-reported live v0.8 completion E2E (2026-10-01)

The owner completed the v0.8 live series from Claude Code against the calculator
fixture through v0.8.10. Together with the offline suite, these runs close the
v0.8 milestone for the intended trusted-local alpha scope. The observations
below are owner-reported host runs; host elicitation remains client-mediated and
does not cryptographically authenticate human presence.

### Adaptive orchestration and isolated execution

The v0.8 series preserved the v0.7 isolated-workspace/write-ownership baseline
while moving workflow/provider decisions behind the conversational control
plane. The user did not need to edit `config.yaml`, select DAG mechanics, or
manually start workers for normal tasks. Start, execution and acceptance remained
separate HumanGates, deterministic pytest validation ran after integration, and
a separate provider family performed review.

The live series also exercised provider changes conversationally rather than by
direct config editing. Stale active bindings initially blocked provider
authority changes. v0.8.7 added a dedicated cleanup HumanGate; the owner then
abandoned `add-multiply-v4` and `add-multiply-v5` and withdrew intake
`I-3e3228409722` without rolling back workspace files or deleting history.
After cleanup, the engineering adapter changed from AGY to Codex through its own
provider-change HumanGate and the exact resulting profile digest was trusted.

### AGY headless authority and guarded writes

AGY 1.2.14 exposed two distinct live behaviors. Without extra authority,
headless tool operations such as `write_file`, replacement edits and commands
were denied even though AGY's terminal envelope could report `SUCCESS`.
v0.8.5 made non-empty `denied_actions` terminal failures rather than accepting
that ambiguous success.

The owner then explicitly authorized
`agy_dangerously_skip_permissions` for one task/attempt through the dedicated
provider-permission HumanGate. That grant did not include execution approval; a
separate execution HumanGate was still required. Task
`add-is-positive-or-zero-20261001b` subsequently completed through AGY guarded
write, pytest (**9 passed**), independent review and acceptance.

The v0.8.8 content-free telemetry was live-verified on that same task. Event
sequence 872 recorded 11 successful AGY tool calls:

- `view_file`: 6;
- `replace_file_content`: 4;
- `run_command`: 1;
- tool errors: 0.

The telemetry contained tool names and aggregate states/counts but no command
body, target path, file contents, prompt, tool output or provider response.
The same run recorded `workflow.guarded_write.finished`,
`validation.finished passed=true` and final `task.accepted`.

A separate AGY happy-path task, `add-is-odd-agy`, also demonstrated guarded
private-worktree execution with exact ownership: only `calculator.py` and
`tests/test_calculator.py` changed, the verified patch was integrated, pytest
passed, Claude review approved and acceptance reached `succeeded`.

### HumanGate presentation

Claude Code was observed folding long elicitation payloads while Codex could
display them expanded. v0.8.9 changed only the presentation layer: full exact
preview/state/snapshots remain scope-bound in the controller, while the host form
shows a compact operation-specific summary. A subsequent live Claude Code form
showed the compact operation/task summary and an explicit client expansion
control rather than making authority details depend on an inaccessible folded
JSON dump.

High-risk AGY permission forms now put the dangerous flag, scoped
task/attempt/provider, broad native-tool auto-approval effect, retained
controller protections and the separate-execution-gate requirement in the
bounded summary. Binding-cleanup forms are capped so exact target IDs remain
visible.

### Atomic provider swap

The final live finding was a provider-swap authority gap. From
`reasoning=Claude / engineering=AGY`, the requested final arrangement
`reasoning=AGY / engineering=Claude` was policy-valid, but either sequential
half-swap temporarily collapsed implementer/reviewer onto the same provider
family and was correctly rejected.

v0.8.10 added atomic provider change-sets. After upgrade, the owner issued only
the natural-language request to make Claude the implementer and AGY the
Supervisor/planner/reviewer. The frontend used one change-set preview and one
HumanGate to apply both changes:

```text
engineering: AGY    -> Claude
reasoning:   Claude -> AGY
```

No intermediate provider profile was materialized. The final combined profile
was validated, config was replaced atomically, and only the resulting digest was
trusted. The frontend reported the requested final role assignment with no
binding cleanup required because no unfinished task/intake bindings were active.

### v0.8 completion boundary

The v0.8 live series therefore provides evidence for the intended alpha
milestone:

- single-terminal host-mediated start/execution/acceptance;
- conversational Supervisor task proposals and trusted/task-scoped workflows;
- DAG and isolated writable-parallel execution inherited from the verified v0.7
  baseline;
- capability/provider resolution with independent-family review policy;
- guarded private worktrees, exact write ownership and deterministic integration;
- validator + independent review + explicit final acceptance;
- conversational persistent provider switching without direct config editing;
- explicit stale-binding abandonment/withdrawal with no implicit rollback;
- scoped AGY broad-permission authority separate from execution approval;
- fail-closed AGY denied-action and structured-output handling;
- content-free provider tool telemetry;
- compact HumanGate presentation that preserves full controller scope binding;
- atomic multi-slot provider swaps with final-profile-only validation and
  resulting-digest trust.

This completion claim is intentionally limited. It does not claim cryptographic
proof of a human click, OS-level isolation against a hostile same-user process,
support for arbitrary agent-authored policy/config edits, unrestricted provider
permissions, production multi-host durability, or stable v1.0 APIs. One Claude
Code auto-mode run also temporarily blocked `wait_job` as "Create Unsafe
Agents"; the durable worker continued and a later explicit result check
succeeded. That frontend heuristic is recorded as a client UX limitation rather
than an Orchestrator authority failure.

With those boundaries, v0.8 is recorded as complete. Further work belongs to the
post-v0.8 roadmap rather than being required to substantiate this milestone.


## Owner-reported live v0.9 completion E2E (2026-10-03)

The owner completed the v0.9 live series from Claude Code against the calculator
fixture. Together with the offline suite, these runs close the v0.9 milestone
for its trusted-local alpha scope. The observations remain owner-reported host
runs; HumanGate elicitation is client-mediated and provider dispatch provenance
is controller evidence rather than provider-side attestation.

### Claude-only model-variant and Fresh-Write path

A Claude-only configuration used Opus for Supervisor/Planner/Reviewer and
Sonnet for implementation, all within the Anthropic family. Explicit unequal
model IDs established independent implementation/review identity while effort
remained `high` for both roles. The start, execution and acceptance HumanGates
all completed.

The final Fresh-Write task `clamp-v091-fresh-write-e2e` added `clamp` to
`calculator.py` and six pytest cases to `tests/test_calculator.py`. The
controller write-set contained exactly those two paths, no violations, and a
non-empty patch hash. Validation reported **20 passed**. Reviewer outcome was
`approved` with no blocking findings, and the task reached `succeeded`.

Official provenance showed Supervisor/Planner/Reviewer in
`read_only_disposable` workspaces with `.orchestrator` omitted, unchanged
verification and cleanup. Implementer provenance reported `isolated_write`
with ownership limited to the two allowed files. Controller RunRequest evidence
recorded the requested model/effort/runtime values and explicit-override sources.

### AGY + Claude interoperability boundary

The profile was then changed through a provider-change HumanGate to
`reasoning=agy / engineering=claude`, making AGY the intended
Supervisor/Planner/Reviewer and Claude the Implementer.

A first AGY Supervisor attempt failed closed on a provider-native command
permission denial before task registration. After the host independently retried
with a prompt-level instruction to avoid shell use, the Supervisor happened to
produce a proposal, but the AGY Planner later selected `run_command` and was
permission-denied. Safe diagnostics identified a denied `command` action and
tool use including `run_command` / `view_file` without retaining the raw command.

This demonstrated that prompt wording such as "do not use shell" is not a
reliable provider-permission boundary and should not be used as an automatic
retry strategy. It did **not** demonstrate that AGY read-only roles are
universally unsupported: an operator whose AGY native scoped permission policy
authorizes the provider's chosen read-only tools may still complete the same
flow.

v0.9.2 therefore records AGY Supervisor/Planner/Reviewer as
`conditional_native_permissions`. Routing/provider changes remain allowed;
Orchestrator does not modify or attest AGY native permission sufficiency, and a
denial fails closed with sanitized diagnostics. Broad
`--dangerously-skip-permissions` remains explicit high-risk task/attempt
authority and is not automatically inferred as an intake workaround.

### v0.9 completion boundary

The v0.9 series is recorded as complete with evidence for:

- provider-local model/effort/runtime-option resolution and provenance;
- task/intake-scoped explicit runtime overrides without persistent profile edits;
- same-family, explicit-different-model independent review;
- read-only disposable provider workspaces and isolated writable execution;
- content-free controller dispatch provenance and sanitized provider failures;
- single-terminal default operation with three explicit HumanGates;
- user-language presentation separated from English control-plane protocol;
- fail-closed AGY native permission behavior with conditional compatibility
  metadata rather than either unsafe bypass or categorical rejection.

The completion claim does not attest provider-side receipt/compliance with
model settings, cryptographic human identity, OS-level isolation, or universal
AGY headless permission compatibility. Future AGY CLI permission improvements can
be adopted at the adapter boundary without reopening the v0.9 architecture.


### Antigravity host MCP / HumanGate interoperability

After installing the packaged project Skill under
`.agents/skills/ai-orchestrator/SKILL.md` and configuring the fixed-project MCP
server, Antigravity was restarted and successfully used ai-orchestrator as the
user-facing host.

The live host run verified:

- Skill discovery;
- `inspect_project`, `propose_task`, `wait_job`, `get_intake`,
  provider-change preview and HumanGate request tools through MCP;
- client identity `antigravity-client v1.0.0`;
- negotiated MCP protocol `2025-06-18`;
- advertised `elicitation.form` and `elicitation.url`;
- ai-orchestrator `form_supported=true`;
- server emission of a correlated `elicitation/create` request.

The provider-change HumanGate did not complete. Transport diagnostics recorded:

```text
elicitation_sent: true
response_received: true
response_action: cancel
outcome: response
host_error_code: none
```

No timeout, disconnect or JSON-RPC host error occurred. The client returned an
explicit MCP elicitation `cancel` response. ai-orchestrator therefore left the
provider change unapplied and did not downgrade authority to CLI commands, direct
config editing or chat-text approval.

This narrows the current Antigravity host boundary: MCP connectivity and
elicitation negotiation/delivery work, while the tested client did not complete
the HumanGate form interaction. The transport record is interoperability
evidence only and does not prove whether a user-facing dialog was rendered.

This limitation does not reopen the v0.9 milestone. Future Antigravity host
changes can be re-tested through the same HumanGate transport diagnostics without
weakening the authorization contract.

## Owner-reported live v0.11 Recovery & Durability E2E (2026-10-04 JST)

The owner completed the v0.11 live recovery series from Claude Code against the
calculator fixture using single-terminal mode. These runs used actual worker /
provider process termination and subsequent controller/worker restart behavior,
rather than only synthetic in-process exceptions. Together with the offline
crash-injection suite, this closes the v0.11 Recovery & Durability milestone for
its trusted-local alpha scope.

### Case 1 — pre-dispatch interruption: safe recovery

Task: `v011-c2-postdispatch-cube` (the original case labels were swapped after
the first monitor attempt missed the pre-dispatch window).

The crash monitor observed `workflow.guarded_write.preparing` and froze/killed
the worker approximately 35 ms later. No later durable workflow event was
recorded. Recovery diagnosis reported:

- `classification=safe_pre_effect_retry`;
- `provider_dispatch_started=false`;
- root snapshot equal to the checkpoint snapshot;
- no automatic replay.

After the operator ran `orchestrator recover`, the task returned to
`awaiting_approval`. The old execution approval was no longer usable and the
next Execution HumanGate had a different scope. After fresh approval, execution
completed normally: the guarded write produced no write-set violations, pytest
reported **29 passed**, independent review returned `approved`, Acceptance was
confirmed, and the task reached `succeeded`.

This verifies that a proven pre-effect interruption can survive a real process
kill/restart and return only to a fresh authority boundary, not directly to
execution.

### Case 2 — post-dispatch interruption: replay prohibited

Task: `v011-c1-predispatch-square`.

The initial pre-dispatch monitor could not open the SQLite/WAL state under the
host sandbox, so this task had already reached provider execution. The worker /
provider process tree was then killed while Codex was running, after the durable
batch `.started` marker existed.

Recovery diagnosis reported `classification=uncertain_effect` because provider
dispatch may already have occurred. After operator recovery:

- task state became `failed`;
- the prior approval was revoked;
- disposable worktrees were removed;
- the root worktree remained unchanged; and
- no automatic provider re-execution occurred.

This verifies that missing provider completion evidence is not treated as proof
that dispatch had no effect.

### Case 3 — interruption after root integration: no replay and no rollback

Task: `v011-c3-postintegration-double-b`.

The monitor killed the worker approximately 27 ms after
`workspace.integrated`; validation had not yet started. The root snapshot
matched the integrated snapshot and contained the new `double` implementation.

Recovery diagnosis reported `classification=uncertain_effect`, with integration
already started/acknowledged. After operator recovery:

- task state became `failed`;
- no automatic implementation replay occurred;
- disposable runtime workspaces were cleaned; and
- the integrated `double` change remained in the root worktree.

This directly verifies the v0.11 invariant that recovery never guesses a
root-worktree rollback after an ambiguous or already-applied effect.

### Case 4 — normal-path regression

Task: `v011-c4-normal-negate-b`.

No crash was injected. The task completed the normal flow:

`Start -> Execution -> pytest -> independent review -> Acceptance -> succeeded`.

The write set covered the two intended calculator/test files with zero
violations, pytest reported **35 passed**, and Claude review returned
`approved`.

The first Acceptance HumanGate timed out after roughly 120 seconds with
`elicitation_sent=true`, `response_received=false`, and no authorization
effect. The task correctly remained `awaiting_acceptance`. A new Acceptance
request ID was then issued against the unchanged task/worktree scope; the user
confirmed it and the task reached `succeeded`. This also reconfirms the
HumanGate timeout/retry boundary: expiration authorizes nothing, and retry is a
new host request rather than replay of the expired gate.

### Worker / job durability observations

For every crash case, the managed `serve` process started a replacement worker
after the killed worker disappeared. The interrupted job was recorded as
`interrupted` and was not automatically re-queued. Task recovery remained a
separate explicit operator action.

`recover` was exercised only from a separate normal terminal because it remains
operator-only and is intentionally absent from the agent-facing mutation
surface.

### v0.11 live completion boundary

The live series therefore verifies the four acceptance cases targeted for
v0.11:

| Case | Recovery classification | Result |
| --- | --- | --- |
| Pre-dispatch crash | `safe_pre_effect_retry` | fresh Execution approval required, then `succeeded` |
| Post-dispatch crash | `uncertain_effect` | `failed`, no replay |
| Post-integration crash | `uncertain_effect` | `failed`, no replay and no rollback |
| Normal path | n/a | `succeeded` |

The observed result is consistent with the v0.11 design: only a durable,
unchanged-root, pre-provider-dispatch checkpoint is recoverable to a fresh
approval gate. Any uncertain prior effect is terminalized without automatic
replay, and applied root changes are not automatically rolled back.

This completion claim remains within the trusted-local model. It does not claim
provider-side exactly-once execution, distributed transactions, cryptographic
human identity, or recovery of external effects.

One operational follow-up remains outside the kernel milestone: the installed
Skill copies under the tested Claude Code / agent locations were older than the
repository's packaged v0.11 Skill and should be re-exported/synchronized before
future host runs.

## v0.12 Contract & Migration automated acceptance

v0.12 is primarily a persisted-contract compatibility milestone, so its
acceptance evidence is deterministic and does not require billable provider
calls. `tests/test_v012_persistence.py` retains representative TaskState v1-v7,
IntakeState v1-v4, HumanGate v1, Artifact v1 and legacy v0.11 recovery evidence.

The suite verifies that:

- every retained supported state can be inspected by the current kernel without
  rewriting the fixture;
- unknown/future and non-integer schema versions fail closed;
- a bad persisted task row remains byte-for-byte unchanged after a rejected read;
- Artifact v2 writes include stable controller identity/provenance while Artifact
  v1 remains readable;
- legacy v0.11 recovery evidence is hash-verified and normalized only in memory;
- unknown versioned control evidence is rejected rather than guessed; and
- runtime event reads expose stable schema-v1 event identity without changing the
  original payload.

The normal CI matrix continues to run the full offline suite on Python
3.11/3.12/3.13 on Linux plus Python 3.13 on macOS, followed by compileall and
wheel build. This milestone does not claim a new provider/host interoperability
result; provider behavior is intentionally outside the migration proof.

## Owner-reported live v0.12 Contract & Migration E2E (2026-10-04 JST)

The owner upgraded the existing calculator E2E project in place to v0.12.0 at
commit `fd7753bd3628a953bc2c7238f57c583f5a2fdcc9` without deleting,
reinitializing or hand-editing `.orchestrator/runtime/`. The running
single-terminal MCP server used the v0.12.0 source.

### Historical persisted-state compatibility

The current kernel successfully inspected representative historical state,
including TaskState schema v1 through v7, IntakeState v1 through v4, Artifact v1,
legacy unversioned v0.11 recovery evidence and the existing runtime event log.
The project contained 42 historical tasks and 51 historical intakes; the observed
TaskState distribution included v1, v2, v3, v4, v6 and v7 rows.

Before/after integrity checks showed:

- 321 pre-existing task/runtime files retained identical hashes;
- the pre-existing task, intake and event rows through event E-1443 retained
  identical digests;
- pre-existing HumanGate and gate-event rows retained identical digests;
- a representative legacy recovery artifact retained its original SHA-256 while
  the kernel exposed the in-memory schema-v1 compatibility view;
- runtime SQLite remained `user_version=2` and HumanGate SQLite remained
  `user_version=1`.

This directly verifies the v0.12 non-mutating read-migration invariant against a
real accumulated v0.x runtime, not only retained synthetic fixtures.

### Normal single-terminal regression

The task `v012-e2e-abs-diff` added `abs_diff(a, b)` and five pytest cases
through the ordinary build-review workflow. Start, Execution and Acceptance were
all accepted through correlated single-terminal HumanGate forms. Implementation
ran through Codex in an isolated writable workspace; Supervisor, Planner and
Reviewer ran through Claude in disposable read-only workspaces.

Observed result:

- exact write set limited to `calculator.py` and
  `tests/test_calculator.py`;
- deterministic validation: `40 passed`;
- independent review: approved, no blocking findings;
- final task status: `succeeded`;
- new TaskState schema v7 and IntakeState schema v4;
- all 17 new artifacts used Artifact schema v2 with controller-generated
  artifact ID, owner ID and creation time;
- new runtime events E-1444 through E-1492 were exposed through RuntimeEvent
  schema-v1 envelopes;
- usage/budget evidence remained attributable and no budget blocker occurred.

The Planner predicted a different pre-existing pytest count than the validator
later observed. This was non-authoritative planning text; validator evidence and
review were consistent with the actual 40-test result.

### Legacy usage observation and v0.12.1 follow-up

The E2E exposed one semantic compatibility gap outside the migration write path:
a pre-v0.10 TaskState with durable `calls > 0` but no usage artifact was
displayed using the ordinary zero-call `empty_usage()` view. As a result,
missing historical token/cost telemetry appeared as known zero even though the
v0.10 truth policy says missing counters must not be coerced to zero.

v0.12.1 corrects the compatibility view without rewriting historical evidence.
When durable call count exceeds recorded usage calls, aggregate token counts,
provider elapsed time and cost are reported as `unknown`, recorded known
subtotals are preserved, and a `call_coverage` object reports expected,
recorded and missing calls. A genuine new task with zero calls still reports
known zero. Budget call limits continue to use durable TaskState call count, and
strict usage limits can therefore fail closed on unavailable historical
telemetry instead of assuming zero consumption.

The live run also found installed Agent Skill copies under the tested host paths
lagging the packaged source Skill. This did not alter kernel behavior, but it is
an operational deployment drift. Re-export the packaged Skill after upgrading;
do not infer that an installed copy is current merely from the kernel version.

With that v0.12.1 follow-up, the v0.12 milestone has both retained-fixture
compatibility coverage and live in-place upgrade evidence while preserving the
authority/recovery boundaries established in earlier releases.

## Owner-reported v0.12.1 final read-only closure E2E (2026-10-04 JST)

The final closure run was intentionally read-only: it created no task, made no
provider call, requested no HumanGate and performed no workspace write. The
running kernel and MCP server were v0.12.1 at
`7a1cac951c6e99417b50acbf5334aa91eb656f4b`.

All requested release-closure checks passed:

- `inspect_project` returned the expected persistence compatibility policy;
- legacy `add-multiply-v6` (TaskState v1) had durable `calls=3` and no usage
  records, and v0.12.1 correctly reported aggregate token/provider-time/cost
  telemetry as unknown with
  `call_coverage={status: incomplete, expected_calls: 3, recorded_calls: 0,
  missing_calls: 3}`;
- no existing zero-call task was available, so the genuine-zero behavior remained
  covered by the offline regression rather than manufacturing new persisted
  state;
- source, packaged, Claude-installed and Agents-installed Skill copies had the
  same SHA-256;
- no new jobs, job events, gates, gate events or runtime events appeared, and the
  E2E worktree/status remained unchanged.

Logical persistence was unchanged: all table row counts/digests, the complete
`state.sqlite3` dump, SQLite user versions, and non-DB persisted file hashes
matched before/after.

The run did expose a physical read-side write: opening the already-current
runtime Store executed `PRAGMA user_version=2` unconditionally. SQLite therefore
advanced the file change counter even though the value and all logical rows were
unchanged. Two read-only API opens advanced the counter twice. Equivalent
unconditional version stamping also existed in the HumanGate and jobs stores.

This did not invalidate the v0.12.1 semantic-migration PASS, because no persisted
authority/evidence meaning changed. v0.12.2 removes the unnecessary current-
version stamps across all three databases. A supported older DB is still stamped
when an actual version migration is required, while opening an already-current
DB no longer changes its SQLite header merely to restate the same user version.

With v0.12.2, the v0.12 Contract & Migration Hardening line is closed before the
v0.13 Provider / Plugin SDK milestone.

## Owner-reported v0.12.2 final physical read-only E2E — PASS (2026-10-04 JST)

The final v0.12.2 closure run exercised the accumulated live E2E runtime at
`e29325a3d6cdb247d1a9756c9569f8fddb806346` without creating a task,
provider call, HumanGate, job, event or workspace write.

Pre/post snapshots covered all three current SQLite databases. After repeated
kernel/MCP/CLI read paths, every canonical database property remained identical:

| Database | user_version | file change counter | version-valid-for | Result |
| --- | ---: | ---: | ---: | --- |
| `state.sqlite3` | 2 | 798 | 798 | unchanged |
| `gates.sqlite3` | 1 | 167 | 167 | unchanged |
| `jobs.sqlite3` | 1 | 459927 | 459927 | unchanged |

For each database, the full file SHA-256, file size, mtime, schema digest, table
row counts and table-content digests were also identical before and after the
inspection. This directly verifies the v0.12.2 fix against the same accumulated
runtime that exposed the v0.12.1 same-version restamp.

The read-only exercise included `inspect_project` twice, four task reads
(including `add-multiply-v6` twice), two job reads, one intake read, one artifact
read and repeated descriptions of existing applied HumanGates through the public
read-only `orchestrator gate` CLI path. The MCP surface does not currently
provide a dedicated HumanGate read tool.

WAL/SHM observations were stable. `gates.sqlite3-wal` (zero bytes) and its SHM
file were already present because the MCP server held the gate database open and
did not change during the measured interval. State and jobs created no
WAL/SHM/journal files during the test.

The persistence compatibility report included runtime state readable
`[0,1,2]` / write 2, HumanGate readable `[0,1]` / write 1 and jobs readable
`[0,1]` / write 1. The v0.12.1 legacy usage correction also remained intact:
`add-multiply-v6` reported calls 3 / records 0 as unknown aggregate telemetry
with incomplete call coverage 3 / 0 / 3 rather than known zero.

The source, editable-installed package, Git HEAD and both installed host Skill
copies had matching SHA-256. No provider/worker child process appeared, event
sequence remained at E-1492, non-SQLite runtime artifacts retained their hashes,
and git/worktree/workspace state remained unchanged.

One boundary remains explicit: the gate DB mtime predated the measurement at the
MCP server restart time, so this run does not claim that server startup/shutdown
itself is physically read-only. It proves that repeated current-version
inspection while the server is running does not mutate the canonical state,
HumanGate or jobs databases.

**Result: PASS.** The v0.12 Contract & Migration Hardening line, including the
v0.12.1 semantic follow-up and v0.12.2 physical read-only hardening, is fully
closed. No additional v0.12 E2E is required before v0.13.



## Owner-reported live v0.13 Provider Adapter / Plugin SDK closure E2E — PASS (2026-10-05 JST)

The owner completed the v0.13 live closure series on the accumulated calculator
fixture using ai-orchestrator-kernel 0.13.0. These are owner-reported host/local
observations; the repository does not independently capture the interactive host
session or cryptographically attest the operator who answered HumanGates.

### Built-in provider single-terminal and HumanGate fail-closed path

The first v0.13 single-terminal run used the existing trusted profile with
Claude for Supervisor/Planner/Reviewer and Codex for implementation. The
external-provider inspection surface reported Provider SDK v1,
`configured: {}`, no installed third-party provider entry points and
`plugin_identity: null` for all active roles.

The first Start HumanGate expired after its 120-second timeout. The controller
reported no operation authorized, automatic replay remained false and no task
was registered. After the user explicitly requested a retry, a fresh Start gate
was accepted; Execution and Acceptance were also accepted. Because the requested
`clamp` implementation already existed as an uncommitted fixture change, that
run completed with no new file patch, pytest reported **40 passed**, independent
review approved and the task reached `succeeded`. This run therefore verifies
the HumanGate fail-closed/no-auto-replay behavior and normal built-in orchestration
but is not the Fresh-Write proof.

### Fresh-Write / isolated integration path

A second run first confirmed that `square(value)` did not exist, then proposed a
new write task with exact allowed paths `calculator.py` and
`tests/test_calculator.py`. The profile digest remained
`fb35016a912363a81c2d2eef02cde83353befb9978b74bf2fb18e513f2eeaa46`
and trusted throughout the task.

Start, Execution and Acceptance HumanGates all reached `applied` with
`automatic_replay=false`. The Codex implementer ran in `isolated_write`
mode with those two exact write paths. Its non-empty patch changed exactly the
two approved files; the isolated and integrated snapshots matched after
integration, enforcement reported no violations, and the root worktree received
the new `square` implementation plus three tests.

The registered pytest validator then reported **43 passed** (the prior 40 plus
the three new square cases). A fresh Claude reviewer approved without blocking
findings against the integrated snapshot. The task reached `succeeded`.

The fixture already contained multiple unrelated uncommitted calculator changes.
A before/after read-only comparison showed no pre-existing lines were removed and
the prior `is_even`, `clamp`, `outside`, `cube`, `double`, `negate`
and `abs_diff` work remained present. This supplies live evidence that the
guarded isolated integration path preserved the dirty root worktree while adding
only the approved Fresh-Write change. All built-in provider provenance retained
`plugin_identity: null`.

### Real external distribution / entry-point activation lifecycle

The owner then created a harmless temporary external distribution,
`ai-orchestrator-v013-e2e-provider==0.1.0`, outside both repositories. It
registered adapter ID `v013-e2e` through the
`ai_orchestrator.providers` entry-point group, declared Provider SDK v1 /
Adapter API v2 and family `e2e-fixture`, implemented only read-oriented
capabilities, and made `execute()` fail safely instead of dispatching a real
provider. The public conformance helper passed before installation.

The live activation sequence was:

| Phase | Profile / pin state | Observed plugin state | Routing / dispatch |
| --- | --- | --- | --- |
| installed, unpinned | original digest, trusted | metadata discovered; code inert | built-ins unchanged; 0 fixture dispatches |
| exact pin added | new digest, untrusted | `metadata_status=exact_match`; `load_status=profile_untrusted`; code not imported | built-ins unchanged; 0 fixture dispatches |
| exact pin explicitly trusted | pinned digest, trusted | loaded through `LoadedPluginAdapter`; SDK/API conformance and doctor passed; identity established | still unselected; built-in routing unchanged; 0 fixture dispatches |
| pin removed | original digest restored, untrusted | no longer active; package metadata still installed | built-ins unchanged; 0 fixture dispatches |
| original digest explicitly re-trusted, fixture uninstalled | original digest, trusted | configured/installed external entries both empty | initial built-in state restored |

The loaded identity was exactly:

- adapter: `v013-e2e`;
- distribution: `ai-orchestrator-v013-e2e-provider`;
- version: `0.1.0`;
- entry point: `ai_orchestrator_v013_e2e_provider.adapter:Adapter`;
- Provider SDK version: `1`;
- Adapter API version: `2`.

The fixture's optional runtime-options, usage and role-compatibility features
were absent and reported as unsupported/false rather than invented. Loading the
plugin did not alter the existing reasoning/engineering slots, models, effort,
workflow, permissions, budget or active-role provenance. The fixture's
`execute()` was never dispatched.

### Trust restoration invariant discovered during cleanup

The cleanup exposed an important authority invariant. Runtime trust stores one
current `metadata.trusted_profile` digest. Trusting the pinned profile replaced
the previously trusted original digest. Therefore removing the pin restored the
original profile bytes and the exact original digest, but **did not restore its
old trust automatically**. The project correctly reported `trusted: false`
until the operator explicitly trusted the restored digest again.

This behavior is fail-closed:

> same profile content/digest restored != previous trust automatically restored

After explicit re-trust and package uninstall, the profile digest/trust,
configuration bytes, provider registry, Provider Resolution, project files and
kernel environment matched the pre-plugin E2E state. No fixture dispatch
occurred at any point.

### v0.13 live completion boundary

**Result: PASS.** Together with the offline CI/conformance suite, the live series
verifies the intended v0.13 trusted-local boundaries:

- package installation alone is metadata discovery, not authority;
- an exact pin changes profile authority and becomes untrusted;
- exact pin plus explicit trust is required before external in-process code
  loads;
- loaded does not imply selected, routed or dispatched;
- package identity is inspectable after activation;
- existing HumanGate, isolated-write, deterministic validation and independent
  review behavior remains intact;
- restoring a previously trusted digest does not resurrect stale trust; explicit
  operator trust is required again.

The run does not claim cryptographic package-byte attestation, sandboxing of
in-process plugin code, or provider-side attestation of controller dispatch.


## Owner-reported live v0.14 / v0.14.1 Project Learning closure E2E — PASS (2026-10-05 JST)

The owner completed an end-to-end Project Learning lifecycle on the accumulated
calculator fixture. The run began on v0.14.0 and discovered one read-only MCP
inspection regression; v0.14.1 fixed that regression without changing candidate
identity/authority semantics. The final closure ran on
`ai-orchestrator-kernel 0.14.1`.

These are owner-reported host/local observations. The repository does not
independently capture the interactive host confirmations or cryptographically
attest the operator identity behind a HumanGate response.

### Baseline and deterministic first distillation

The initial trusted profile digest was:

`fb35016a912363a81c2d2eef02cde83353befb9978b74bf2fb18e513f2eeaa46`

The accumulated runtime exposed 45 tasks, 54 intakes and 1592 runtime events.
Accepted context contained one 253-byte baseline policy and no accepted Project
Learning Markdown.

An explicit operator `learning distill` completed successfully with:

- `task_count=45`;
- `event_count=1592`;
- `candidate_patterns=12`;
- 12 newly created candidates;
- no retained/rejected-suppressed candidates.

All 12 candidates were `knowledge` observations. The live set included
validated-path recurrence, pytest-validator history, provider-family history and
usage-telemetry-status observations. Candidate generation did not alter the
profile digest, trust state, accepted-context universe, provider/model/effort
resolution, workflow, permissions, budget, task count or intake count.

Representative candidate `P-L72e7ee2ae69d`
(`canonical_key=validator-history:pytest`, positive polarity) carried six
typed references: three task references and three validation Artifact-v2
references. Its support reported three independent tasks and three corroborating
validations. The referenced validation artifact hashes matched their immutable
runtime files.

### v0.14.0 MCP inspection regression and v0.14.1 fix

The first live non-empty-candidate inspection exposed a v0.14.0 regression:
`list_learning_candidates` and `get_learning_candidate` raised an internal
tool error because `service.py` used the candidate scope `digest()` helper
without importing it. Empty candidate sets had hidden the defect.

v0.14.1 fixed the missing import, added non-empty-candidate MCP regression
coverage and added derived `evidence_coverage` diagnostics. After upgrading and
restarting the MCP server, live verification passed:

- `list_learning_candidates` returned all 12 candidates;
- `get_learning_candidate P-L72e7ee2ae69d` returned schema v2 typed
  evidence/support/provenance plus scope;
- no internal error occurred;
- `evidence_coverage` explicitly separated full recurrence counts from the
  bounded retained evidence/task-ID sample.

For example, validated-path candidate `P-L5dac4de5380e` reported 40 total
evidence refs but 32 retained refs, 17 independent tasks, 17 corroborating
validations/reviews, and only two retained validation/review Artifact-v2 refs
each. This correctly reflects legacy Artifact-v1 corroboration plus the bounded
v2 sample rather than pretending complete typed-artifact coverage.

### Idempotence

The owner re-ran `learning distill` against unchanged evidence. The controller
reported:

- `candidate_patterns=12`;
- `created=[]`;
- `retained` equal to the same 12 candidate IDs;
- `rejected_suppressed=[]`.

The 12 candidate files remained byte-for-byte unchanged, the accepted-context
universe remained one item / 253 bytes, the original profile remained trusted,
and no provider/workflow/budget/task/intake authority changed.

**Result:** same evidence produced the same candidate identity and no duplicate
candidate creation.

### Explicit promotion and automatic fail-closed trust invalidation

The owner selected `P-L72e7ee2ae69d` because its complete retained evidence
was typed and hash-verifiable, then promoted its exact pre-promotion scope.

Promotion changed only the candidate status/approved-by fields and created:

`.orchestrator/knowledge/accepted/P-L72e7ee2ae69d.md`

The accepted Markdown preserved the typed evidence references, support metadata,
canonical key, polarity and the pre-promotion proposal digest. Accepted-context
size changed from one item / 253 bytes to two items / 2940 bytes.

The profile digest changed from the original value to:

`a00ab4559b8078f81f24589df248bfcada936c04275085f5d7f07744af3a05a7`

and immediately evaluated `trusted=false`. Configuration, provider slots,
Provider Resolution, model/effort, workflow, permissions and budget remained
unchanged.

**Result:** candidate promotion became project authority only through accepted
context, changed the profile fingerprint and failed closed until explicit
operator trust.

### Explicit trust and ContextInfluence reuse

After the operator explicitly trusted the promoted profile, a read-only context
preview selected both:

- `.orchestrator/policies/baseline.md`;
- `.orchestrator/knowledge/accepted/P-L72e7ee2ae69d.md`.

The accepted learning entry retained its content hash, kind=`knowledge` and all
six typed evidence references. Candidate JSON was not selected.

The owner then proposed the live task `v014-p2c-increment`: add
`increment(value)` to `calculator.py` plus three pytest cases, preserving all
existing dirty-worktree changes and limiting writes to
`calculator.py` / `tests/test_calculator.py`.

The new intake used IntakeState v5 and persisted a `ContextInfluence` manifest
with the same two selected context items. After Start confirmation, the new task
used TaskState v8 and persisted a hash-verified `context_influence` artifact
matching the frozen TaskState manifest. Intake and task query hashes differed, as
expected, because task selection was recomputed from the confirmed TaskSpec; the
selected context itself remained the same.

The task then completed the normal single-terminal lifecycle:

- Start HumanGate: applied;
- Execution HumanGate: applied;
- isolated implementation/integration: exact two-file write set, no violation;
- pytest: **46 passed**;
- independent review: approved, no blocking finding;
- Acceptance HumanGate: applied;
- final TaskState: `succeeded`.

The kernel does not durably store full provider prompt bodies, so the live run
does not claim a byte-for-byte prompt capture. The frozen ContextInfluence,
source implementation path and unchanged manifest provide the controller-side
evidence for which accepted context was selected for those calls.

### Post-Acceptance automatic learning without authority escalation

Acceptance triggered the v0.14 advisory post-acceptance distillation. Candidate
count increased from 12 to 24 without an operator distill command.

Materially new evidence generated new candidate identities. In particular,
`P-Lb5fce708a1d4` represented pytest success across four independent task
records and recorded:

`supersedes=["P-L72e7ee2ae69d"]`

The previously promoted candidate remained approved at that point, while the new
candidate remained inactive. No new candidate was automatically promoted or
added to active accepted context.

**Result:** successful execution accumulated new Project Learning evidence and
semantic supersession without automatic authority escalation.

### Promotion cleanup and trust restoration invariant

The owner then removed only the temporary promotion authority:

1. delete the promoted accepted Markdown;
2. restore `P-L72e7ee2ae69d.json` byte-for-byte to its pre-promotion candidate
   state;
3. preserve all post-Acceptance task/runtime evidence and all newly generated
   candidates.

The original candidate SHA-256 was restored to
`fa6733698212550709322c4d1834c3246b27e644fa7a1f88863edec44e33e17c`.
Accepted context returned to one item / 253 bytes and the profile digest returned
exactly to the original `fb35016a...` value.

As in the v0.13 plugin lifecycle, the prior trust did **not** automatically
return. The single current trusted-profile record still contained the promoted
digest, so the restored original profile correctly evaluated
`trusted=false`. The operator explicitly re-trusted the original digest; the
runtime recorded one new `profile.trusted` event.

The final project state retained:

- original project authority and trusted profile;
- no accepted Project Learning Markdown;
- 24 inactive Project Learning candidates;
- the successful `v014-p2c-increment` task and its immutable evidence;
- the task's historical ContextInfluence pointing to the accepted learning that
  existed at execution time;
- post-Acceptance supersession evidence.

Thus current authority no longer includes the promoted learning, while historical
task provenance still records that the learning influenced the completed task.

### v0.14 / v0.14.1 live completion boundary

**Result: PASS.** The live series verifies:

- controller-owned historical evidence can deterministically produce governed
  candidates;
- candidates are inactive and non-authoritative;
- identical evidence is idempotent and does not duplicate candidates;
- v0.14.1 candidate inspection works on a non-empty real project;
- exact promotion writes accepted context and invalidates trust through the
  profile fingerprint;
- explicit trust is required before that context can govern new work;
- accepted context is deterministically selected and frozen in IntakeState v5 /
  TaskState v8 ContextInfluence provenance;
- normal isolated-write / validator / independent-review / HumanGate execution
  succeeds with the selected context;
- Acceptance can generate materially new candidates and supersession relations
  without automatic promotion;
- removing promoted authority does not delete accumulated learning evidence;
- restoring the old profile digest does not revive stale trust;
- historical ContextInfluence survives after the influencing accepted knowledge
  is later removed.

The two final product properties demonstrated by the live run are:

> learning accumulates; authority does not

and:

> historical influence provenance survives even after current accepted authority changes


## Owner-reported v0.15.1 Operational Hardening live closure E2E — PASS (2026-10-06 JST)

The v0.15 Operational Hardening milestone was closed only after a live E2E
follow-up on the accumulated project runtime. The first v0.15.0 run found a real
retention defect: `retention_plan()` treated six immutable Supervisor artifacts
referenced only by `IntakeState.artifact` as orphan artifacts. Three of those
intakes were still proposed, so cleanup could have deleted evidence required for
later intake inspection/start. v0.15.1 corrected the retention root set and
extended read-only doctor coverage to IntakeState-referenced artifacts.

The final v0.15.1 run used main
`94f960a5db9126dc578a78e841ccadc64c6a9a3f`, profile digest
`fb35016a912363a81c2d2eef02cde83353befb9978b74bf2fb18e513f2eeaa46`,
and an accumulated runtime containing 46 tasks, 55 intakes, 1644 runtime events,
115 HumanGates, 125 jobs, 24 Project Learning candidates and one accepted-context
item.

All release-closure checks passed:

- `doctor` was read-only and reported all runtime SQLite/task/intake/job/gate/
  workspace/maintenance/provider/validator checks OK;
- doctor verified 350 referenced artifacts: 344 referenced by TaskState plus six
  referenced only by IntakeState. A scratch copy with one missing and one
  modified intake artifact was correctly reported as missing/corrupt with exit
  status 1 and no automatic repair;
- v0.15.1 full and runtime-only backups independently passed SHA-256 verification.
  The full archive contained 547 files and the runtime archive 472 files;
  WAL/SHM sidecars, locks and disposable worktrees were excluded;
- full restore on a scratch copy rejected wrong scope, a runtime scope supplied
  for a full archive, missing `--ack-authority-restore` and a tampered archive.
  The exact verified restore succeeded, restored the archived profile digest and
  recorded maintenance provenance without producing new execution events/jobs;
- restore over unreadable current runtime failed without the dedicated
  acknowledgement and succeeded only when both unreadable-state and full-
  authority acknowledgements were supplied;
- runtime-only restore preserved current project authority. A deliberately
  changed policy remained unchanged and the profile mismatch was surfaced as
  `retrust_required=true`; an unchanged copy restored with
  `retrust_required=false`; malformed current `config.yaml` remained
  fail-closed and could not be bypassed by the unreadable-runtime acknowledgement;
- the v0.15.0 false-orphan regression was eliminated: the read-only retention
  plan reported no overlap with any of the 46 IntakeState artifact paths and no
  orphan Supervisor artifacts;
- exact-scope cleanup on scratch state rejected a wrong cutoff and scope drift,
  then removed only one stale worktree, one deliberately created orphan artifact
  and 125 terminal jobs (plus 375 job-event rows). Task/Intake/runtime-event/
  HumanGate canonical history, all 46 Supervisor artifacts, all 24 candidates
  and legacy JSON remained;
- after cleanup, all three proposed intakes remained inspectable and their intake
  scopes could be recomputed, which re-verified their Supervisor artifact
  integrity. `start --no-run` could not be used as an additional proof because
  those historical intakes were already stale from worktree drift; the untouched
  comparison copy failed for the same reason, so this was not a cleanup effect;
- no MCP backup/restore/cleanup/database-repair mutation tool exists. Restore and
  cleanup remained blocked inside Claude Code and were run only by the operator
  in a normal terminal against scratch copies;
- no automatic repair or replay occurred;
- the original project finished with identical database table contents,
  non-sidecar files, Git HEAD/status, worktree state, profile trust and Project
  Learning candidate count. Only empty SQLite WAL/SHM sidecars held/opened by the
  running MCP server differed in presence/mtime.

The final operational invariants are therefore live-verified:

> diagnosis is read-only

> backup does not grant authority

> restore is explicit and scope-bound

> runtime-only restore does not replace project authority

> retention preserves canonical TaskState and IntakeState evidence roots

> cleanup is explicit and scope-bound

> maintenance does not become agent authority

> interrupted/ambiguous effects are never automatically repaired or replayed

**Result: PASS.** v0.15.1 closes the v0.15 Operational Hardening milestone.


## v0.16 Exploration / Deliberation offline verification and live target

The v0.16 regression suite adds an actual stdio MCP -> managed worker ->
deterministic provider-shim flow. It starts with an ambiguous request, changes
direction in a second turn, proves no task/approval exists, explicitly produces
one provenance-bound intake, declines one Start, then confirms fresh Start,
Execution and Acceptance separately. Integrated pytest validation and independent
review complete the task, and usage includes both exploration turns. This is
offline subprocess evidence, not a live external-provider or human-click claim.

Live closure remains to be performed in an updated host/MCP/Skill environment.
Use a fresh fixture exploration: start with an underspecified goal, inspect and
compare alternatives, change one assumption/direction, verify no task or write
appeared, then explicitly request a bounded task proposal. Confirm the source
revision on Start and complete the existing execution/validation/review/acceptance
flow. Also revise/abandon a separate unconsumed proposal and verify its old Start
fails. Check cumulative usage, retained turn/transition evidence, unchanged
profile/trust and exploration-aware retention. Never simulate host approval or
invoke operator-only maintenance from the agent to make a live test pass.


## Owner-reported v0.16.0 Exploration / Deliberation live closure E2E — PASS (2026-10-06 JST)

The owner completed the live v0.16.0 closure run on the accumulated E2E project
with main/origin/main at `e68a3c1a187a0c69a8c6552dc896f7016e423fb6`,
runtime SQLite user_version 3, gates/jobs user_version 1, historical TaskState
v1-v8 and IntakeState v1-v5 still readable, profile
`fb35016a912363a81c2d2eef02cde83353befb9978b74bf2fb18e513f2eeaa46`
still trusted, and source/Claude/Agents Skill copies matching.

The main exploration session `X-717be48f02ab` began from an intentionally
underspecified request. Revision 1 created no task, intake or HumanGate, used a
read-only disposable workspace, changed no project-root file and persisted one
hash-verified `exploration_turn` artifact with `authority: none`. Revision 2
changed direction to a two-value comparison helper. The same session advanced to
revision 2; prior options remained historical/discarded, while
`latest-understanding-v1` selected only the latest understanding and retained
older turns by immutable reference. Usage accumulated across both turns.

Stale refinement and proposal attempts against revision 1 failed before queueing
with `exploration revision changed; inspect the current session`; no automatic
rebase, intake creation or extra job occurred.

The owner explicitly selected `same_sign(a, b) -> bool` with zero treated as
non-negative. The exact decision, source session, revision 2, source snapshot and
selected understanding were frozen into an exploration-transition artifact and
carried into IntakeState v6. At that point no TaskState existed and the normal
Start HumanGate remained required.

The main task then completed the unchanged guarded lifecycle:

```text
Exploration -> explicit transition -> Start -> planning -> Execution
            -> isolated implementation -> pytest -> fresh review -> Acceptance
            -> succeeded
```

The resulting TaskState v9 retained exploration provenance. Codex implemented
only `calculator.py` and `tests/test_calculator.py` inside the approved write
set; pytest reported 52 passed; an independent Claude review approved; Acceptance
completed; and usage accounting carried the exploration, Supervisor, Planner,
Implementer and Reviewer calls forward rather than restarting at task creation.

Start rejection was verified on a separate exploration proposal. The first two
probe forms in the broader exercise were accidentally answered Yes by the
operator, so those particular probes are not rejection evidence. A third session
produced a real declined Start HumanGate: the task remained unregistered, no
automatic replay occurred, and exploration/proposal history remained inspectable.

Abandonment was also exercised separately. An unconsumed exploration/proposal
became abandoned/withdrawn, retained its historical evidence and could no longer
be refined, proposed or started. Attempting to abandon a session already
transitioned to a registered task was rejected; abandonment cannot undo task
authority that has already crossed Start.

Operational checks passed:

- `doctor` reported three exploration sessions and no missing/corrupt
  exploration artifacts; total referenced artifacts increased from 350 to 385;
- the read-only retention plan reported no orphan artifacts and protected
  active/transitioned/abandoned exploration evidence;
- runtime/full backup design includes runtime state and exploration artifacts;
- read-only verification did not rewrite database content;
- exploration exposed no arbitrary path/shell/validator/trust/provider-permission
  mutation authority and did not auto-promote accepted Project Learning;
- accepted knowledge, config, profile digest/trust, provider and workflow
  authority remained unchanged;
- Project Learning candidates increased only after the accepted task through the
  existing governed post-acceptance path; exploratory prose alone created none;
- no automatic replay occurred.

The final project comparison found intended content changes only in
`calculator.py` and `tests/test_calculator.py`, both inside the accepted
task's write set. Historical pre-E2E task/intake/gate/job rows were not
modified/deleted. New runtime/task/evidence rows and inactive learning candidates
were expected outputs of the live run.

One residual non-blocking fixture remains:
`v016-e2e-docstring-probe` is `awaiting_approval` because a probe Start form
was accidentally accepted. No Execution HumanGate was requested and no
implementation effect occurred. It may be explicitly cancelled by the operator
as housekeeping; it is not part of the successful task or the rejection proof.

**Result: PASS.** v0.16.0 satisfies the planned live Exploration / Deliberation
closure boundary and the v0.16 milestone is closed. The next implementation
milestone is v0.17 Release Candidate Hardening.


## v0.17 implementation verification and pending live qualification

v0.17 adds regression cases derived from the retained design audit and actual
subprocess SIGKILL tests on disposable maintenance fixtures. Those checks cover
cancellation/direct-approval parity, atomic safe finalization, recursive and frozen
evidence roots, shared metadata conflicts, request-ID retirement/restore lineage,
incomplete-operation barriers, reconciliation and loaded-build mismatch.

The existing real stdio MCP/managed-worker/three-HumanGate provider-shim tests
continue under No-first presentation. Clean wheel/sdist checks run outside the
editable checkout; minimum/reference dependency CI records resolved versions.
See [RC Verification](RC_VERIFICATION.md) for the final-source evidence mapping.

No owner v0.17 live run is claimed by this implementation. The required normal
flow, genuine refusal and idle cancellation/finalization must each pass twice on
fresh IDs at the same build, as specified in [RC Live E2E](RC_LIVE_E2E.md). Historical
v0.16 evidence and its cancelled-request residual probe do not substitute for those
runs. Do not relabel that residual task terminal without observing finalization.


## Owner-reported v0.17.0 RC live qualification — required flows PASS, host transport conditional (2026-10-06 JST)

The owner ran the final v0.17.0 build on the accumulated E2E project with
Claude Code 2.1.284, MCP protocol 2025-06-18, Claude reasoning/planning/review
and Codex CLI 0.160.0 implementation. Runtime/gates/jobs SQLite versions were
3/1/2 after the expected first v0.17 JobQueue migration. The loaded/disk build,
packaged contract inventory and both exported host Skills matched.

Required positive evidence passed twice on fresh IDs:

- Fresh-Write Run A: `v017-rc-runa-sign`, measured pytest **55 passed**,
  isolated two-file write set, independent Start/Execution/Acceptance gates.
- Fresh-Write Run B: `v017-rc-runb-halve`, measured pytest **59 passed**,
  same guarded lifecycle and write-set constraints.
- Two genuine Start refusals produced no TaskState, no implementation, no new
  execution job/event and no automatic replay.
- Two idle cancellation/finalization runs recorded exactly one
  `cancel.requested`, exposed nonterminal cancellation state, refused new
  execution/acceptance authority, then operator-only exact-scope finalization
  reached terminal `cancelled` without provider/validator/file effects.
  Repeated finalization was a no-op.

Scratch qualification also passed the audited RC boundaries: eleven
cancellation-finalization blocker classes and stale scope refused; terminal job
cleanup retired 147 payloads while preserving 147 request receipts; identical
retired request IDs returned `request_retired` with
`automatic_replay=false`; recursive/frozen evidence roots survived cleanup;
all six conflicting shared-artifact metadata dimensions failed closed; and
SIGKILL interruption at nine maintenance phases left a pending barrier that
blocked normal constructors/dispatch until explicit reconciliation or
acknowledged recovery restore. Restore preserved compatible receipt history,
refused conflicts before mutation, interrupted queued work, cancelled pending
gates and kept terminal TaskState bytes.

Final comparison found intended source changes only in `calculator.py` and
`tests/test_calculator.py` from the two accepted Fresh-Write tasks. Existing
profile digest/trust, accepted knowledge, provider/workflow authority and
historical pre-run rows were unchanged. New inactive learning candidates were
normal post-Acceptance governed output. No original-project cleanup/restore,
automatic replay, automatic trust/promotion or hidden provider fallback occurred.
Known provider cost remained a subtotal because Codex did not report total cost.

### Claude Code transport observation

One Start form produced an unexplained Yes-intent / `decision=no` wire result.
It failed safe and did not increase authority. A controlled retry with the user
confirming Yes on screen delivered `decision=yes`, and both required positive
Fresh-Write flows later completed. The required refusal flows also delivered the
intended No responses. Therefore the 0.17.0 required baseline is PASS while the
Claude Code 2.1.284 host-transport entry is retained as **conditional**, not
universally supported. The observation is not evidence of forged Yes authority.

### Post-run RC-01 follow-up

The live review found one controller inconsistency against the approved RC-01
entry-point wording: a task with an existing cancellation request could still
reach `request_provider_permission` form preparation. The resolve/apply path
already refused it, so no permission or execution authority could be granted.
Nevertheless RC-01 requires cancellation checks at provider-permission approval
entry points, so v0.17 is not formally closed at 0.17.0.

v0.17.1 adds the missing prepare-time refusal before any HumanGate row/form is
created. Formal closure requires one targeted live recheck on the 0.17.1 final
build proving a cancelled task cannot create a provider-permission gate. The
0.17.0 destructive scratch matrix need not be repeated unless that recheck
reveals another core defect.


## Owner-reported v0.17.1 targeted RC-01 closure recheck — PASS (2026-10-06 JST)

The owner upgraded the accumulated E2E project to v0.17.1 at
`13f0b43839c10e30e3ba68bcb5aec793f6779fde` and restarted the MCP host.
Package version, main/origin/main, loaded-versus-disk build identity and the
source/Claude/Agents Skill copies all matched. The MCP server reported loaded
and disk build prefix `33e0f58d`.

A fresh task `task-caeeda5eb97b` from intake `I-caeeda5eb97b` was registered
through Start gate `G-061dd2cf3b5941c4b86af5962f20fd30` and planned to
`awaiting_approval/execute`. No Execution HumanGate was requested. The operator
then recorded one cooperative cancellation request. Runtime event sequence 1940
was `cancel.requested` with empty payload.

After cancellation, the task exposed `cancellation.requested=true`,
`terminal=false` and `automatic_replay=false`. The targeted MCP
`request_provider_permission` call used request ID
`v0171-closure-perm-after-cancel-1` and was refused immediately with
`task has a cancellation request`.

The prepare-time refusal satisfied the missing RC-01 requirement:

- total HumanGate rows stayed 134 -> 134;
- gate_events stayed 383 -> 383;
- pending/applying gates stayed 0 -> 0;
- provider-permission gates stayed 1 existing -> 1;
- rows for the targeted request ID stayed 0;
- provider call started/finished counters stayed 131/120;
- validator started/finished counters stayed 34/32;
- task call count stayed 2;
- provider_permission_grants stayed empty;
- approvals stayed 42;
- project tree SHA / Git status stayed unchanged;
- max runtime event sequence stayed 1940 after the permission request.

No HumanGate form was created or shown, no provider-permission grant appeared,
and no provider, validator, file or authority effect occurred. The post-cancel
snapshot and post-permission-request snapshot were identical.

The fixture task remains cancellation-requested but intentionally not finalized;
that housekeeping state is not execution authority and is not required for this
prepare-time test. Other pre-existing unfinished fixture bindings were not
repurposed to manufacture evidence.

Combined with the full owner-reported v0.17.0 RC qualification, this targeted
v0.17.1 PASS closes the only remaining audited RC-01 gap. Claude Code 2.1.284
host transport remains **conditional** because of the previously recorded
Yes-intent / No-wire anomaly; it failed safe, controlled positive retries worked,
and no authority-increase failure was observed.

**Result: PASS. v0.17 Release Candidate Hardening is formally closed at v0.17.1.**
The next step is a separate v1.0 Stable Control Plane release decision; no v1.0
tag or package publication is implied by this closure.
