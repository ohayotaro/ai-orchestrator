# Architecture: v0.1

## Boundaries

The kernel is project-driven rather than domain-driven. `Profile` owns provider bindings, role instructions/requirements, declarative machine policy, and named validators. Approved Markdown supplies bounded project context. No domain is required or inferred.

`models.py` is the versioned contract source. `orchestrator schema` exports JSON Schema directly from the validation models rather than maintaining a second hand-written schema. Unknown fields, unsupported versions, duplicate YAML keys, invalid IDs and traversal paths fail closed.

`engine.py` is a sequential state machine, not an LLM planner of arbitrary transitions. Logical roles remain separate from adapters. `ProviderAdapter` supplies a family label, declared capabilities, a diagnostic probe, and `execute(RunRequest) -> AgentResult`. Inject a registry into `Engine(root, registry=...)` to test or add adapters. CLI plugin discovery and arbitrary extension loading are intentionally absent.

## State machine

The phase is `plan`, `execute`, `validate`, `review`, or `accept`. Execution status is independently `ready`, `running`, `awaiting_approval`, `awaiting_acceptance`, `succeeded`, `blocked`, `failed`, or `cancelled`.

T0 goes from a non-writing planner to operator acceptance. T1-T3 go through all phases. T3 cannot disable execution approval. Lower-tier write tasks also require approval unless the operator explicitly changes and trusts the profile. Validation failure or review rejection re-enters execution with an incremented attempt and bounded feedback. All successful write paths must pass validation and explicit review before operator acceptance.

Provider launch failure, malformed output, timeout, protected-path mutation, or ambiguous interrupted execution does not trigger automatic replay. Only an explicit validation failure/review rejection enters the bounded repair loop. `max_attempts` limits implementations; `max_agent_calls` and cumulative execution seconds bound model calls and validators. Approval wait time is not execution time. CLI preflight probes have their own short timeout. There is no dollar or token budget enforcement.

The profile's `workflow` currently accepts only `build-review`. Editing roles and constraints is supported; arbitrary YAML graphs, parallel dispatch and nested subagents are not.

## Approval and acceptance

An execution-approval scope hashes the frozen task specification, effective profile/context digest, plan artifact, implementation attempt, and current worktree snapshot. A different scope needs a new approval. Final acceptance verifies the entire artifact chain and compares the worktree against the reviewed snapshot.

A project-level POSIX `flock` prevents cooperating controllers from mutating the same workspace concurrently. SQLite commits each state transition and its event in one transaction. Running tasks cannot be resumed blindly. An operator can recover a stale run only after the lock is free; recovery records failure, not success or rollback.

An `--by` label records who the operator says they are. It is not authentication. See SECURITY.md before interpreting these approvals as an access-control boundary.

## Artifacts and reviewer context

The controller stores schema-validated result artifacts as immutable uniquely named JSON files with SHA-256 digests. A plan, implementation result, runner validation record, review, and acceptance remain distinguishable by artifact kind and attempt. The database is authoritative; JSON event export is a read view, not a second writable state store.

Reviewer requests contain the task, approved project context, and runner-produced validation evidence. They intentionally omit implementation summaries, plans, and conversational transcripts. Every adapter call starts a new invocation without resume. Reviewers still inspect the same project files, which may contain model-written text; context construction is not proof of epistemic independence or isolation from every on-disk artifact.

## Project evolution

Candidates require evidence references and remain outside active prompt context. An operator promotes an exact content digest into `knowledge/accepted`, `policies`, or `skills`. Those directories are included in the effective profile digest. Promotion therefore invalidates prior profile trust and existing task bindings.

Approved policy Markdown is model-facing guidance. Only structured `Policy` fields implement machine gates. Promotion never installs a validator, enables a tool, changes risk classifications, or edits the kernel. Operators define validator commands manually and retrust configuration after review.

v0.1 records evidence references but does not fetch them, determine truth, infer confidence, aggregate observations, or automatically generalize between projects. These mechanisms require future evaluation, provenance and conflict-resolution design.

## Adapter contracts and sources

Codex uses `exec`, ephemeral sessions, a phase-specific sandbox, explicit noninteractive approval settings, schema output, an output file, and stdin prompts. Claude uses print-mode structured output, no session persistence, explicit file-tool sets, noninteractive denial, empty explicit MCP configuration, and disabled optional customization sources. Runtime settings and administrative policy remain relevant; declared capabilities are not interchangeable security guarantees.

Upstream documentation reviewed on 2026-09-29:

- https://developers.openai.com/codex/noninteractive
- https://developers.openai.com/codex/cli/reference
- https://code.claude.com/docs/en/headless
- https://code.claude.com/docs/en/cli-reference

Adapters are unit-tested against documented envelope/command shapes. They have not been authenticated against live CLIs in the initial development environment. The diagnostic probe checks required flag availability, not every model option or end-to-end compatibility.
