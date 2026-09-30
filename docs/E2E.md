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
