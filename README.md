# AI Orchestrator

A project-driven, provider-neutral orchestration kernel with natural-language task intake, explicit human gates, deterministic validators, and evolving project knowledge.

**v0.3.0 alpha — trusted local execution, not a production security boundary.** Claude Code and Codex CLI adapters are included. Gemini, distributed workers, arbitrary DAGs and native subagents are not implemented. Read [Security](docs/SECURITY.md) before connecting credentials or executing repository code.

## v0.3: use your existing conversational agent

Claude Code, Codex and other compatible stdio MCP clients can now delegate through
`orchestrator serve`. A separate operator-started `orchestrator worker` processes
queued requests using the same Supervisor, state machine and provider adapters.
The frontend never recursively launches a model inside the conversational client.

```text
User <-> Agent + portable Skill -> MCP frontend -> durable job queue
                                                     |
                                      separate operator-started worker
                                                     |
                              Supervisor -> Planner -> Implementer -> Reviewer
```

Human intake confirmation, execution approval and final acceptance remain in the
operator terminal. There is **no MCP trust/start/approve/accept tool**; chat text
or model-supplied actor labels do not grant authority. The separate process is an
operational boundary, not protection from a hostile process with the same OS user.

See **[MCP and Skill setup](docs/MCP.md)** for complete Claude Code/Codex commands,
worker startup, queue semantics and the conversation-to-acceptance walkthrough.
The `ask`/`start` direct CLI below is retained unchanged. `skill --output` exports
the packaged portable skill without overwriting existing files or client settings.

v0.3 adds protocol-wire tests, both provider-role permutations through separate
worker processes, and an optional independent MCP SDK interop test. These use
model shims, not authenticated live models; v0.3 real-client E2E remains to be run.

## Direct CLI workflow (introduced in v0.2)

Users no longer need to write a TaskSpec YAML file for ordinary work:

```bash
orchestrator ask "Add a subtract function and regression tests" --task-id add-subtract
```

A configurable **Supervisor** inspects the request and project, then proposes a structured task or asks clarification questions. It does not approve or execute that task. The operator reviews the proposal, then the existing deterministic kernel runs it:

```text
natural-language request
  -> Supervisor -> task proposal / clarification
  -> operator confirms proposal
  -> Planner -> execution approval
  -> Implementer -> registered validators -> fresh Reviewer
  -> human acceptance
```

The Supervisor can select existing validator names and propose acceptance criteria/risk. It cannot register commands, change policies, grant permissions, or call the controller's trust/approve/accept APIs. Normal `ask` tasks have a minimum T2 risk and always retain execution approval, even if a project relaxes the default. `--advisory` is explicitly read-only T0; external-effect requests remain unsupported.

Other v0.2 additions are role-specific result schemas, validator executable checks before model calls, explicit generated-output directories, Python bytecode suppression during validation, mutation-path diagnostics, `validator add/check`, and terminal-only interactive execution approval. Existing TaskSpec YAML/JSON input remains supported.

## Install or upgrade

Use **Python 3.11 or newer**. On macOS, check the actual interpreter before creating a virtual environment; an old `python3` may still be Python 3.9. Existing environments do not become newer Python environments by upgrading pip.

```bash
python3.13 --version                 # 3.11/3.12 also supported
python3.13 -m venv .venv             # a NEW environment, not an old Python 3.9 venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/orchestrator --version
.venv/bin/python -m pytest -q
```

Install/authenticate Claude Code and Codex CLI separately. Models are not hard-coded; `model: null` uses the CLI's configured default. Linux and macOS are supported; the process/lock implementation requires POSIX.

For an existing checkout, stop active runs and back up each project's entire `.orchestrator/runtime/` directory before upgrading. Then:

```bash
git pull --ff-only
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/orchestrator --version      # 0.3.0
```

Reinstall after a version bump to refresh package metadata even with editable installation. Use the orchestrator checkout's `.venv/bin/...`, not an unrelated environment that remains activated in your shell. Database upgrade is additive, but downgrading a v0.2 runtime database to the v0.1 executable is not supported. See [Migration](docs/MIGRATION.md).

## Prepare a project once

Start in a disposable Git project without production credentials. Run direct model-executing commands from a normal terminal. For conversational clients, use the v0.3 MCP frontend with a separately started worker.

```bash
cd /path/to/your-project
# git init                          # only if this is a new repository
/path/to/ai-orchestrator/.venv/bin/orchestrator init --name my-project
```

For the remaining examples, `orchestrator` means that installed CLI (activate its environment, use its absolute path, or define a shell alias). `init` never overwrites an existing `.orchestrator/` directory.

Register the project's **actual** test interpreter and command. The following assumes this project already has `.venv/bin/python` with pytest installed:

```bash
orchestrator validator add pytest -- .venv/bin/python -B -m pytest -q -p no:cacheprovider
orchestrator doctor --validators-only
```

To replace an existing definition, do it explicitly:

```bash
orchestrator validator add pytest --replace -- .venv/bin/python -B -m pytest -q -p no:cacheprovider
```

Registration uses argument vectors rather than a `command:` field or shell string. It checks that the executable exists but does not execute or trust it. Relative executable paths resolve against the **project root**; absolute paths and PATH commands also work. Virtualenv interpreter symlinks are preserved so they continue to use the correct environment.

After inspecting the profile, command, test code, and local provider configuration:

```bash
orchestrator trust --by "$USER" --ack-local-execution
orchestrator doctor
orchestrator validator check pytest
```

`doctor` detects provider flags and validator executables without running the validators or checking model authentication. `validator check` is an explicit operator action: it executes the trusted command with the same environment/mutation guard used by task validation and stores evidence. It can catch missing pytest modules and actual test failures before model calls. A test command is executable repository code, not an inherently safe operation.

## Natural-language workflow

```bash
orchestrator ask "Add subtract(a, b) to calculator.py and add regression tests" \
  --task-id add-subtract
```

The JSON result contains an intake `id`, `status`, proposed `task`, model `result`, and, when ready, an `intake_scope`. No task has been registered yet and no implementation is authorized.

If the status is `needs_clarification`, read `result.questions` and answer:

```bash
orchestrator ask "Limit the function to integers and keep existing APIs unchanged" \
  --reply-to '<intake-id>'
```

Clarification is limited to three Supervisor calls per chain. Calls/time are carried into the eventual task budget. Each reply is a fresh provider invocation with bounded explicit history, not a hidden persistent model session.

Inspect a ready proposal and confirm its **exact** scope:

```bash
orchestrator intake '<intake-id>'
orchestrator start '<intake-id>' --scope '<intake_scope>' --by "$USER"
```

`start` consumes that proposal once, registers its TaskSpec and Supervisor artifact, then invokes the planner. For a write task it stops at `awaiting_approval`. `start --no-run` registers only. If the workspace or active profile changed after intake, ask again rather than confirming stale material.

Inspect the plan and worktree, then approve in a real terminal:

```bash
orchestrator approve add-subtract --interactive --by "$USER"
# Read the displayed plan/feedback and type: approve
orchestrator run add-subtract
```

Alternatively, retain the exact-scope scriptable interface:

```bash
orchestrator status add-subtract
orchestrator approve add-subtract --scope '<approval_scope>' --by "$USER"
orchestrator run add-subtract
```

The interactive option refuses piped input and rechecks the scope after confirmation. It does not imply authenticated human identity; this remains a trusted-local application.

Validation or blocking review feedback can request bounded rework, with another scoped execution approval. After `awaiting_acceptance`, inspect the real diff and all review findings before accepting:

```bash
git diff
orchestrator status add-subtract
orchestrator accept add-subtract --by "$USER"
orchestrator events --task-id add-subtract
```

A normal v0.2 `ask` path uses four model calls: Supervisor, Planner, Implementer and Reviewer. Final acceptance stays human-controlled. A successful simple fixture does not establish general model quality or production safety.

## Review contracts

New tasks request `PlanResult`, `ImplementationResult` and `ReviewResult`. Reviews distinguish:

```json
{
  "outcome": "approved",
  "summary": "Acceptance criteria met",
  "blocking_findings": [],
  "observations": ["A non-blocking note or confirmation"],
  "evidence": ["Concrete source or runner evidence"]
}
```

Observations never cause rework. `changes_required` or nonempty `blocking_findings` do; blockers override an inconsistent `approved`. `blocked` stops execution. v0.1 task rows retain their legacy `AgentResult` wire format/outcome semantics instead of reinterpreting old artifacts. `schema task` remains the stable v1 TaskSpec contract.

```bash
orchestrator schema supervisor
orchestrator schema plan
orchestrator schema implementation
orchestrator schema review
orchestrator schema task
```

## Validators and generated files

The controller supplies a filtered environment with temporary HOME and `PYTHONDONTWRITEBYTECODE=1`. It never shell-parses generated prose. Pytest caching is independently controlled by the operator's `-p no:cacheprovider` option. Common misspellings get a diagnostic warning; static checks cannot validate arbitrary tool arguments.

A validator may explicitly declare **literal untracked output directories**, not glob exclusions:

```yaml
validators:
  tests:
    argv: [.venv/bin/python, -B, -m, pytest, -q, -p, "no:cacheprovider"]
    timeout_seconds: 120
    env:
      TEST_MODE: strict
    generated_paths:
      - test-output
```

Generated roots must stay inside the project, may not contain symlinks or overlap tracked/protected/control files, and are only allowed during that validator. They do not grant agents permission to modify files during read-only phases. Ordinary source changes still fail and the diagnostic lists changed paths. Git-ignored files remain outside the general worktree fingerprint; choose `.gitignore` and these declarations deliberately.

## Project-driven knowledge and role bindings

There is no built-in finance/research/fullstack taxonomy. Projects own their policies, skills, validators and accumulated knowledge. Default role bindings are:

```yaml
roles:
  supervisor: {provider: reasoning}
  planner: {provider: reasoning}
  implementer: {provider: engineering}
  reviewer: {provider: reasoning}
```

`reasoning` defaults to the Claude adapter and `engineering` to Codex. Existing profiles without `supervisor` reuse the planner binding without a rewrite. Changing bindings is a user-owned profile change requiring review/retrust. Routing by performance, additional vendor adapters and automatic extension loading are future work.

Evidence-linked memory remains separate from permissions:

```bash
orchestrator propose --kind policy \
  --statement 'Update schema snapshots when migrations change the schema.' \
  --evidence 'task:T-42'
orchestrator proposal '<proposal-id>'
orchestrator promote '<proposal-id>' --scope '<scope>' --by "$USER"
```

Candidates are inactive. Operator promotion adds approved Markdown, not executable rules, validator commands or permissions. Evidence references are recorded, not automatically verified. Active-context changes invalidate profile trust and task bindings. `intake` is a task proposal; `proposal/promote` is project knowledge promotion — they are separate lifecycles.

## State, limits and verification

SQLite is canonical and events commit with state updates. Artifacts are durable, SHA-256 checked and stored under gitignored `.orchestrator/runtime/`. The kernel serializes cooperating controllers with a workspace lock. Failure, cancellation and interrupted execution do not silently replay side effects; inspect the workspace and create a new task where necessary. `recover` only marks a stale running task failed.

The owner reported a completed live v0.1 calculator E2E and a live v0.2 Supervisor-to-review path reaching `awaiting_acceptance` on 2026-09-29. The latter output alone does not prove final acceptance. **v0.3's MCP/client/worker integration still requires authenticated real-client E2E.** Offline tests cover stdio, separate workers, both provider-role configurations and real pytest with model shims. See [E2E evidence and smoke testing](docs/E2E.md).

```bash
python -m pytest -q
python -m compileall -q src tests
python -m pip wheel . --no-deps -w dist
```

[Architecture](docs/ARCHITECTURE.md) describes contracts and persistence. [Security](docs/SECURITY.md) explains same-user limitations, snapshot coverage and validator risks. [Migration](docs/MIGRATION.md) covers v0.1 upgrades and existing project templates. [Changelog](CHANGELOG.md) lists implemented changes and non-goals.

License to be determined. Public visibility does not itself grant an open-source license.
