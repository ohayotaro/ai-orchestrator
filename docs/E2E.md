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
