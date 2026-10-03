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

