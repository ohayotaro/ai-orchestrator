# AI Orchestrator

[日本語](README_ja.md) · [PyPI](https://pypi.org/project/ai-orchestrator-kernel/) · [Release](https://github.com/ohayotaro/ai-orchestrator/releases) · [Support](docs/SUPPORT.md)

**Give your existing AI coding tools a shared workflow: plan, approve, implement, test, review, and accept.**

AI Orchestrator is a local coordinator, not another model or hosted agent service. You talk to a supported AI client; it delegates work through the orchestrator to separately managed workers. The default roles use Claude for reasoning, planning and review, and Codex for implementation. After setup, ordinary tasks do not require you to write a workflow/DAG or name providers every time.

**v1.0.1 is a documentation/packaging maintenance release for the v1 Stable Control Plane.** It embeds this post-release README in the distribution and updates license metadata and the PyPI publication path. It does not expand control-plane runtime behavior, public contracts, or the supported live baseline established by v1.0.0. Start with the Claude Code walkthrough below. Other host/provider combinations do not inherit its qualification; see [tested support and limitations](docs/SUPPORT.md).

## Why use it?

- **Separate work from approval.** Review a proposal, an execution plan, and a completed result at three distinct confirmation forms.
- **Use evidence, not a model's claim of success.** Inspect measured test results, a fresh independent review, write-set records and available usage telemetry.
- **Keep context without accumulating authority.** Explore unclear requirements conversationally; retain project knowledge through explicit governance, not automatic permission changes.

It fits bounded repository changes with reviewable acceptance criteria and runnable checks. It can also support discussion before implementation. It is **trusted-local software**, not a sandbox against a hostile process running as your OS user, and not a production deployment or external-transaction approval service.

## Quick start: Claude Code + Codex

### Before you start

Use a normal terminal, outside an agent shell. You need Git, Python 3.11 or newer, and separately installed/authenticated Claude Code and Codex CLIs. The walkthrough uses `python3.13`; substitute another installed, compatible interpreter where appropriate. Automated coverage is Linux Python 3.11/3.12/3.13 and macOS Python 3.13. The exact real-host baseline is narrower: [macOS / Claude Code 2.1.284 / Codex 0.160.0](docs/SUPPORT.md).

You do **not** need an orchestrator API key or a source checkout. Provider credentials/subscriptions belong to the provider CLIs. Delegated reasoning, planning, implementation and review may incur provider charges; a Start refusal does not erase proposal-generation cost. Missing cost telemetry is not zero cost.

Run each block in order in the same terminal. Stop on an error. The two paths below must be new; existing installations/projects should use the [upgrade guidance](docs/SINGLE_TERMINAL.md#upgrading-and-existing-projects), not reinitialization.

### 1. Install into a dedicated environment

```bash
VENV="$HOME/.venvs/ai-orchestrator-demo"
PROJECT="$HOME/ai-orchestrator-demo"
```

```bash
test ! -e "$VENV" && python3.13 -m venv "$VENV" && "$VENV/bin/python" -m pip install 'ai-orchestrator-kernel[interop]==1.0.1' 'pytest>=8,<10'
```

```bash
ORCH="$VENV/bin/orchestrator"
"$ORCH" --version
```

Expected: `1.0.1`. The distribution name is `ai-orchestrator-kernel`; the command is `orchestrator`. The extra includes the MCP SDK used for interoperability; pytest is for this demo's validator. Keep the absolute venv path: no activation is needed.

### 2. Create a small Git project

```bash
mkdir "$PROJECT" && cd "$PROJECT" && git init -b main
```

```bash
printf 'def add(a, b):\n    return a + b\n' > calculator.py
mkdir tests
printf 'from calculator import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n' > tests/test_calculator.py
printf '__pycache__/\n.pytest_cache/\n.DS_Store\n' > .gitignore
```

```bash
"$ORCH" --project "$PROJECT" init --name calculator-demo
```

Expected: `initialized: true`, `trusted: false`. This creates `.orchestrator/`; it does not authorize work. Default roles already select Claude and Codex.

### 3. Register validation, inspect, and explicitly trust

```bash
"$ORCH" --project "$PROJECT" validator add pytest --timeout 120 -- "$VENV/bin/python" -m pytest -q
```

```bash
cat .orchestrator/config.yaml
cat .orchestrator/policies/baseline.md
```

Inspect the provider bindings, command and policy before granting trust. Validator registration is configuration, not execution. Trust permits this local configuration to be used; it is not approval for every task.

```bash
git add .gitignore calculator.py tests/test_calculator.py .orchestrator/config.yaml .orchestrator/.gitignore .orchestrator/policies/baseline.md && git commit -m "demo: initial calculator and orchestration profile"
```

Git needs an author identity. If the commit fails, configure your own identity and complete it before continuing; do not copy someone else's name/email.

```bash
"$ORCH" --project "$PROJECT" trust --by "$USER" --ack-local-execution
```

```bash
"$ORCH" --project "$PROJECT" validator check pytest
```

Expected: `ok: true`, `exit_code: 0`, and **1 passed** in the measured validator output. This explicitly runs a local test and stores validation evidence; it does not call a model.

### 4. Connect Claude Code and export the Skill

```bash
cd "$PROJECT" && claude mcp add --transport stdio --scope local ai-orchestrator -- "$ORCH" --project "$PROJECT" serve
```

```bash
"$ORCH" skill --output "$HOME/.claude/skills/ai-orchestrator/SKILL.md"
```

An existing Skill is not overwritten. Inspect it first, then deliberately use `--replace` to back it up and replace it. An existing MCP registration should likewise be inspected, not blindly deleted. Local MCP scope applies to **this project**; switching chat directories is not a way to rebind a running server. See [connection setup](docs/SINGLE_TERMINAL.md).

```bash
"$ORCH" --project "$PROJECT" identity --skill "$HOME/.claude/skills/ai-orchestrator/SKILL.md"
"$ORCH" --project "$PROJECT" doctor --operational-only
```

Expect matching loaded/disk builds and `matches_packaged: true`. A fresh project's jobs/gates databases may not exist yet. `doctor --operational-only` is the provider-free diagnostic; plain `doctor` can perform provider probes.

Close any old Claude Code session for this project, then start a new one:

```bash
cd "$PROJECT" && claude
```

### 5. Make your first request

Paste this into Claude Code, not your shell:

```text
Use ai-orchestrator in single-terminal mode to add subtract(a, b) to
calculator.py and add pytest tests in tests/test_calculator.py.
Preserve add(a, b). Limit changes to those two files and use the registered
pytest validator. Delegate the change; do not edit the files directly.
Use the host's separate Start, Execution and Acceptance confirmation forms.
Do not answer the forms for me or substitute CLI approvals.
```

Read each form and select Yes only for the displayed scope. The expected outcome is a `succeeded` task with actual passing validation and an approved independent review. A completed worker job or a model saying “done” is not the same as accepted task completion. Do not configure hooks to answer HumanGates automatically.

## What the three confirmations mean

```text
Your request -> proposal -> [Start] -> plan -> [Execution]
             -> implementation -> tests -> fresh review -> [Acceptance]
             -> succeeded
```

| Gate | What Yes permits |
| --- | --- |
| Start | Register the proposed task and queue planning. Proposal reasoning can already have incurred cost. |
| Execution | Execute this exact implementation attempt and its validation. This can change files in the root worktree. |
| Acceptance | Accept the reviewed result and record task success. It is not a deferred first-write gate. |

**Files may already be changed before Acceptance.** Rejecting a form, cancelling a task or finalizing cancellation does not automatically roll back integrated changes. No/cancel/missing/timeout/stale responses do not grant new authority. Ordinary tool permissions and chat text are not HumanGate responses. These gates do not authorize commit, push, deployment or arbitrary external actions.

Setup, trust, validator registration, cancellation/finalization and maintenance remain deliberate CLI operations; “single-terminal” describes the normal proposal-to-acceptance flow, not every administrative operation. [Details](docs/RC_OPERATIONS.md).

## Explore, adapt, and learn

For an unclear task, ask: “Use ai-orchestrator to explore the options without implementing anything yet.” Exploration can revise assumptions over multiple turns. An explicit transition creates a proposal; the three gates still apply.

Trusted workflow templates and bounded task-specific DAG proposals let the host select a suitable workflow without requiring you to design one for every request. Isolated writable parallelism is opt-in, not automatic shared-worktree concurrency. Provider/model/effort changes remain explicit; there is no hidden fallback.

Project Learning distills candidate knowledge from retained evidence. Candidates do not change permissions or trust. Promoting accepted context is an operator action and requires re-trust. See [exploration](docs/EXPLORATION.md), [workflows](docs/WORKFLOWS.md), [parallel execution](docs/PARALLEL_EXECUTION.md), and [Project Learning](docs/PROJECT_LEARNING.md).

## Support and safety boundaries

The qualified v1.0.0 real-host deployment is Claude Code 2.1.284 with Claude reasoning/planning/review and Codex CLI 0.160.0 implementation, MCP 2025-06-18, macOS 26.6.2 arm64 and Python 3.13.12. Model/effort were adapter defaults, not verified resolved model names. Provider-role support is not host-form support. Codex and Antigravity hosts are not promoted by this release. [Support matrix and evidence limits](docs/SUPPORT.md).

HumanGate responses are client-mediated, not cryptographic proof of a human click. No-first ordering cannot guarantee host focus or prevent mis-clicks. In-process provider plugins are trusted controller code. Unknown usage remains unknown, and recovery does not replay uncertain effects automatically. Stable contracts do not imply universal interoperability or a new security boundary. [Security](docs/SECURITY.md).

## Documentation and development

| Need | Start here |
| --- | --- |
| Setup, existing projects, upgrades | [Single-terminal guide](docs/SINGLE_TERMINAL.md) |
| Missing executable, wrong project, shell continuation, failed form | [Troubleshooting](docs/TROUBLESHOOTING.md) |
| Backup, cancellation, maintenance, recovery | [Operations](docs/OPERATIONS.md), [RC operations](docs/RC_OPERATIONS.md), [recovery](docs/RECOVERY.md) |
| Public API, persistence, SemVer | [Public contracts](docs/PUBLIC_CONTRACTS.md), [persistence](docs/PERSISTENCE.md), [migration](docs/MIGRATION.md) |
| Extend an adapter / integrate a host | [Provider SDK](docs/PROVIDER_SDK.md), [MCP](docs/MCP.md), [architecture](docs/ARCHITECTURE.md) |
| Release evidence and history | [v1 verification](docs/V1_VERIFICATION.md), [live E2E](docs/E2E_V1.md), [changelog](CHANGELOG.md), [roadmap](ROADMAP.md) |

For development, use a **separate** source checkout/environment, install `.[dev,interop]`, run `python tools/check_contracts.py` and `python -m pytest -q`. The six CI lanes distinguish reference, minimum and core-only dependency coverage. An editable checkout or a new CI build from post-release main is not the published v1.0.0 distribution, even if its version string is unchanged.

## License and releases

[Apache License 2.0](LICENSE). [GitHub Releases](https://github.com/ohayotaro/ai-orchestrator/releases/tag/v1.0.0) is the canonical public release record; PyPI distributes the same qualified wheel/sdist. The [release record](docs/releases/v1.0.0.json) identifies exact hashes and the approved manifest.

This README was reorganized after publication. It does not replace the README embedded in the already-published v1.0.0 package, move its tag, or change its artifacts.
