# AI Orchestrator

A provider-neutral orchestration kernel for coordinating AI agents, CLI runtimes, project policies, workflows, and evolving project knowledge.

> **Status:** Early development. The architecture is being extracted from practical orchestration patterns developed in `claude-finance`, `claude-research`, and `claude-fullstack`. APIs and schemas are not stable yet.

## Why

Most agent systems bind three concerns too early:

- a specific model or provider,
- a fixed agent role,
- and a predefined application domain.

AI Orchestrator takes a different approach. The kernel should not need to know that Claude is the manager, Codex is the implementer, or that a project belongs to "finance", "research", or "fullstack".

Instead, orchestration is built from orthogonal primitives:

```text
Project
  |
  +-- Constitution / Policies
  +-- Knowledge
  +-- Workflows
  +-- Roles
  +-- Validators
  |
  v
Orchestration Kernel
  |
  +-- Task / DAG / State
  +-- Artifact Protocol
  +-- Policy / Approval Gates
  +-- Capability Routing
  +-- Events / Audit Trail
  |
  v
Provider Adapters
  |
  +-- Anthropic / Claude
  +-- OpenAI / Codex
  +-- Google / Gemini
  +-- Local or future runtimes
```

The goal is to make providers replaceable, project behavior explicit, and useful project-specific knowledge able to evolve over time.

## Design Principles

### Provider-neutral kernel

The core orchestration layer operates on capabilities, roles, tasks, policies, artifacts, and state transitions rather than provider names.

Provider-specific behavior belongs behind adapters.

```text
Role + Requirements
        |
        v
Capability Router
        |
   +----+----+
   |    |    |
Claude Codex Gemini ...
```

A reviewer may therefore be expressed as a constraint such as "fresh session, read-only, independent from the implementer" rather than "run Codex".

### Project-driven, not domain-driven

The project does not assume that domains such as finance, scientific research, or fullstack engineering can be completely specified in advance.

A project begins with a small profile and evolves through use:

```text
Project usage
    |
    v
Observations
    |
    v
Candidate knowledge
    |
    +--> Project knowledge
    +--> Skill / workflow
    +--> Proposed policy
             |
             v
        User approval
```

Reusable profiles may emerge later from mature projects, but they are outputs of experience rather than mandatory top-level abstractions.

### Deterministic control plane

LLMs should perform semantic work: planning, decomposition, implementation, research, critique, and synthesis.

The orchestration kernel should retain deterministic ownership of:

- allowed state transitions,
- permissions and sandboxes,
- approval gates,
- timeouts and retries,
- execution budgets,
- artifact integrity,
- provider constraints,
- fresh-session guarantees,
- validation execution,
- audit events.

Agents should not be able to silently rewrite the control plane that governs them.

### Explicit knowledge promotion

Not every observation should immediately become a rule.

The intended lifecycle is:

```text
Observation
  -> Candidate
  -> Verified / repeated
  -> Project knowledge
  -> Skill or proposed policy
  -> Deterministic validator where appropriate
```

Safety-critical and project-level policies remain human-controlled. Agents may propose changes without silently promoting them.

### Artifacts over transcript coupling

Agents exchange structured task state and durable artifacts instead of depending on another model's full conversation transcript.

This enables independent review, reproducibility, provider replacement, and bounded context.

## Core Concepts

The initial kernel is expected to converge around a small set of primitives:

| Primitive | Responsibility |
|---|---|
| Task | Unit of work with requirements and acceptance criteria |
| Role | Logical responsibility independent of model/provider |
| Capability | Runtime features required to perform a role |
| Provider | Adapter to a CLI, API, or provider-native agent runtime |
| Workflow | Allowed phases and transitions |
| Policy | Constraints, permissions, and approval requirements |
| Artifact | Durable output exchanged between phases |
| Validator | Deterministic verification |
| State | Current lifecycle and execution metadata |
| Event | Append-only audit information |
| Knowledge | Project-specific information accumulated through use |

## Planned Architecture

```text
ai-orchestrator/
├── core/                 # task, state, workflow, policy, artifacts, events
├── providers/            # Claude, Codex, Gemini, future adapters
├── workflows/            # reusable workflow definitions
├── profiles/             # optional reusable project profiles
├── schemas/              # task/artifact/config contracts
└── cli/                  # user-facing orchestration commands

project/
└── .orchestrator/
    ├── config.yaml
    ├── policies/
    ├── workflows/
    ├── roles/
    ├── validators/
    ├── skills/
    └── knowledge/
```

This layout is provisional and will be validated against real migrations before becoming stable.

## Provider Model

Providers expose common capabilities without forcing every runtime into the lowest common denominator.

```text
Common Provider Contract
        +
Provider-specific extensions
```

Examples of capabilities include:

- filesystem read/write,
- shell execution,
- network access,
- fresh or persistent sessions,
- structured output,
- native subagents,
- tool/MCP support,
- sandbox or permission controls.

The kernel can then route by capability and policy rather than hard-coded vendor identity.

## Project Evolution

A new project should require only minimal configuration. Policies, workflows, skills, validators, and knowledge can become more specific as the orchestrator is used.

Conceptually:

```text
Day 1
  minimal profile
      |
      v
real tasks + evidence
      |
      v
project-specific knowledge
      |
      v
mature policies / workflows / validators
      |
      v
optional reusable profile
```

Existing projects such as `claude-finance`, `claude-research`, and `claude-fullstack` are intended to serve as source material and integration cases, not as fixed domain specifications.

## Roadmap

### v0.1 — Kernel extraction

- Task and artifact schemas
- Lifecycle/state engine
- Provider adapter interface
- Claude and Codex CLI adapters
- Role binding
- Deterministic validation
- Approval and policy gates
- Fresh-session independent review
- Project Profile schema
- Knowledge/policy promotion model
- Migration experiments against the existing orchestrators

### Later

- Gemini and additional provider adapters
- Capability-based dynamic routing
- Parallel workers and task DAGs
- Provider-native subagents
- Cost and latency budgets
- Nested orchestration
- Reusable profile import/export
- Cross-provider independence constraints

## Non-goals

At this stage, AI Orchestrator is not intended to:

- define a universal taxonomy of application domains,
- hide all provider-specific capabilities behind an identical API,
- let agents autonomously modify safety-critical orchestration policy,
- maximize the number of agents involved in every task,
- replace deterministic tests and validation with model consensus.

The objective is controlled composition, not agent proliferation.

## Provenance

This project generalizes orchestration patterns developed through:

- `claude-finance`
- `claude-research`
- `claude-fullstack`

Those projects explore different ownership models between Claude and Codex, independent review, risk-tiered approval, artifact-based handoffs, deterministic hooks, and project-specific knowledge. AI Orchestrator extracts the reusable control-plane concepts while keeping provider and project specialization replaceable.

## License

License to be determined.
