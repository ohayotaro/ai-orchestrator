# Security and operational limitations

## Trusted-local alpha, not a production security boundary

Use a disposable Git worktree, trusted repository code and trusted local CLI configuration. Keep production credentials and confidential data out of the first tests. Do not use this release to enforce live-trading, deployment, publication, regulated-data or other external-action approvals. `external_effects: true` is rejected, but a flag and an LLM cannot discover every possible external consequence of arbitrary code.

The controller, validator commands and model CLIs run as the same OS user. Such a user, or a sufficiently capable subprocess, can potentially modify the database, approvals, installed controller code, credentials or files outside the intended workspace. A `--by` label is not authentication. Hashes/locks are consistency measures for cooperating processes, not protection against a hostile same-user actor.

A hardened deployment needs a separately authenticated controller/approval service, isolated workers, protected state, scoped credentials and OS-enforced filesystem/network policy. None of those guarantees is implied by this alpha.

## Supervisor authority

The Supervisor receives no controller tools for trust, approve, accept, policy editing or validator registration. Its typed output cannot encode those operations. It can inspect and propose a task or clarification questions. The application checks existing validator names and external-effect flags and applies a T2 floor plus a mandatory execution-approval flag to normal ask tasks. Explicit advisory requests remain T0 and cannot enter implementation/validation.

The operator must inspect the proposed goal, scope, risk, validators and acceptance criteria before `start`, and inspect the plan/worktree before execution approval. Do not treat model risk classification as a security decision. An instruction embedded in source material or a proposal is not authorization. Natural-language review results are not proofs of correctness.

The native provider tools still operate under their own runtime restrictions. Claude's Supervisor is offered read tools, not Bash or file writes; Codex requests its read-only sandbox. Because the system is trusted-local, these settings plus after-the-fact checks are not equivalent to a separately protected approval service.

Interactive execution approval requires a TTY and exact affirmative text, shows escaped task/plan/feedback, and rechecks scope after confirmation. It reduces copy/paste errors and accidental pipe confirmation, but does not attest that a real human is controlling that TTY.

## Provider controls and review

Codex receives explicit noninteractive approval settings, phase-specific read-only/workspace-write sandboxing, disabled workspace command networking, ephemeral sessions and a result schema. Local configuration, endpoints, platform support and administrative policy remain relevant. Model-service network requests are different from shell/network access inside a sandbox.

Claude receives read tools for Supervisor/Planner/Reviewer and file-edit tools for implementation. Optional configuration/MCP sources are constrained. A tool allowlist is not an OS sandbox. Managed configuration and CLI releases can change behavior; help/version checks do not prove sandbox correctness or model compatibility.

Adapter family labels do not attest the model behind a proxy/custom endpoint. Fresh invocations reduce conversation coupling but do not establish statistically independent errors, prevent all shared misinformation, or forbid reading every on-disk artifact. The application omits implementation/transcript context from reviewer prompts, and preserves concrete validation evidence.

v2 explicit blockers always prevent acceptance even if the reviewer also says approved. Observations are non-blocking by contract. v1 tasks retain legacy outcome semantics for compatibility. Operators should read all findings before final acceptance rather than treating either contract as a security audit.

## Validators are executable code

Named validators are operator-owned argv vectors, not commands produced by an agent. Nevertheless, pytest/build tools/scripts execute arbitrary repository code. Both task validation and `validator check` run locally, without their own OS/network sandbox. Filtered environment and temporary HOME do not prevent access to credentials elsewhere on disk.

`doctor` does not execute validator commands, import arbitrary packages, or perform a universal dry run. It checks executable existence/execution permission and configuration constraints, and warns about a few common pytest plugin misspellings. `validator check` explicitly runs the command after profile trust, under the normal mutation guard; it is not a safe dry run.

The default validator environment disables Python bytecode writes. Explicit environment entries are not a secret-storage mechanism; reserved PATH/HOME/loader/Git and credential-like keys are rejected. Redaction covers only common patterns and output tails. Do not put secrets in arguments, task text, profiles, proposals, validator output or model artifacts.

## Generated-output declarations and fingerprints

Worktree fingerprints cover Git-tracked files and nonignored untracked files, including executable bits and symlink targets. They exclude `.DS_Store` and `.orchestrator`; active context has its own digest and control files outside runtime have a separate before/after fingerprint. Runtime remains outside this check so the controller can record events/artifacts.

Git-ignored content, all Git metadata, submodules and external storage are not recursively audited. Large/special worktrees fail explicitly instead of silently taking a partial fingerprint. Do not broadly ignore source or sensitive outputs just to make a validator pass.

A generated-output root must be a literal untracked directory inside the project. Globs, traversal, control paths, symlinks, protected-path overlaps and tracked-file overlaps are rejected. Constraints are checked again after validation. This is a narrow opt-in for known outputs, not permission to ignore all workspace changes. Only that validator gets the allowance; read-only agents do not. Operator-declared output can still contain malicious or sensitive content and must not be trusted just because it is allowed to exist.

Mutation failures are detected after execution and do not automatically undo writes. A successful subprocess exit or pytest run never overrides a failed integrity check. Changes are recorded in validation evidence for manual inspection.

## Persistence, cancellation and recovery

SQLite task transitions/events commit together; intake consumption/task registration is also transactional. Artifact files are written before references, so interruption can leave unreferenced output. Runtime backups must include artifacts and a consistent database/WAL; back up with all controllers stopped or use a proper SQLite backup workflow. v0.2 upgrades the database version additively and does not support downgrade.

Cancellation terminates ordinary descendants in the subprocess process group. A process that deliberately escapes its group/session is outside that guarantee. Already completed external effects are never undone. Do not automatically replay an interrupted implementation. Inspect the worktree/evidence, recover a stale running task to failed, and create a new task if appropriate.

An interrupted Supervisor produces no runnable task. If interrupted after start has registered the task, inspect the consumed intake and run the existing ready task rather than trying to consume it again. Ordinary user edits after proposal or review invalidate the corresponding confirmation/acceptance check. Failed, cancelled and unaccepted tasks must not be represented as complete.

## Project memory and verification status

Knowledge candidates are untrusted and inactive until an operator approves their exact digest. Approved Markdown influences model behavior; evidence is not fetched or automatically proven, and promotion never installs commands or grants permissions. Wrong generalizations and prompt injection remain risks.

The owner reported a successful live v0.1 calculator E2E. v0.2's new Supervisor/result schemas are tested offline, including real local CLI shim processes, Git and pytest. Those tests are not live-provider certification, a penetration test or an independent audit. See E2E.md for the evidence boundary and next smoke test.


## v0.3 MCP and worker boundary

The stdio frontend is fixed to one project and exposes no operator authorization,
arbitrary file-read, shell, configuration mutation or policy promotion tools.
Tool input schemas reject extra fields such as `approved`, `actor`, `argv` and
`project`. A returned scope hashes content; it is public information, not a token.
The portable skill forbids using the host agent's shell to impersonate the human.
These restrictions apply to this MCP surface, not every capability of the host.

The worker must be started in a normal operator terminal. Existing CLAUDECODE
nesting protection is not removed. A worker marker rejects accidental recursive
MCP startup from worker descendants. Do not treat environment markers as an
adversarial security boundary: a same-user shell can remove them, rewrite runtime
SQLite files, invoke the operator CLI, or alter installed code. Isolated workers
and an independently authenticated approval authority remain future work.

Job requests are idempotent by required caller key. Queue size/expiry bounds
reduce accidental duplication or delayed dispatch; they are not spend limits.
Only the exclusive worker owner may mark abandoned jobs interrupted. Interrupted
jobs are never automatically replayed. A client disconnect does not cancel a job;
use explicit cancellation. Cancellation does not roll back existing file effects.

No network listener or OAuth implementation is introduced. MCP stdout contains
only bounded newline-delimited JSON-RPC responses. The optional official SDK is
used for interoperability testing only; runtime transports do not depend on it.
Artifacts and proposed text remain untrusted, may contain sensitive information,
and must not be promoted to permissions or executed as instructions. Use only
trusted clients and non-production credentials for this local alpha.


## v0.5 capabilities are constraints, not permissions

Semantic capability resolution does not grant tools, write paths, external
effects or approval. HumanGate, protected paths, write-set enforcement,
validators and cross-provider review remain independent controls. Dynamic
routing is deterministic profile policy, not model scoring. A model can request
additional task requirements but cannot mutate provider capability declarations
or provider priority. Provider Adapter v1 compatibility is limited to existing
fixed bindings without new semantic declarations.


## v0.6 workflow security boundary

Workflow configuration is trusted profile data, never model-authored authority.
The compiler rejects cycles, unknown/type-invalid artifact dependencies, unsafe
advisory nodes and write graphs lacking gated writes, deterministic validation
or independent review. Models cannot install a new graph through TaskSpec.

DAG topology does not grant concurrency. v0.6 executes exactly one ready node in
the shared worktree. This intentionally avoids introducing same-worktree write
races before v0.7 isolation.

Typed artifact edges reduce unnecessary transcript/data propagation: downstream
nodes receive declared artifacts, not every upstream conversation. Artifact
hashing, protected paths, allowed_paths/write-set enforcement, external-effect
blocking and HumanGate scopes remain independent controls.


## v0.6.2 workflow selection authority

`workflow_ref` is selection, not permission expansion. It can reference only a
workflow already present in the package/project trusted registry. Unknown IDs
fail before model execution. The Supervisor cannot submit workflow definitions,
modify config, or create trust.

The selected workflow digest is included in intake/start and task execution
provenance. Selecting a trusted entry leaves the profile digest unchanged;
installing/removing/changing a project workflow remains a profile change and
requires the existing trust ceremony.


## v0.7 isolated parallel write boundary

v0.7 removes the cooperating-worker same-worktree race for opt-in writable DAG
nodes. Each concurrent writer receives a distinct Git worktree and exact
`write_paths`; independent isolated nodes with overlapping ownership are
rejected before execution. The task's `allowed_paths` remains the outer effect
contract.

A worker result is not applied directly to the user's worktree. The controller
creates seed/worktree Git metadata inside a disposable runtime-local shared
clone rather than registering temporary worktrees in the user's repository. It
first checks protected/control state and exact changed paths, records patch
provenance, integrates all branch patches in deterministic workflow order in the
disposable integration worktree, rechecks the project root, and only then
applies one aggregate patch. Validators and fresh review run after that integration. Provider failure,
ownership violation or integration conflict prevents partial sibling application.

`max_parallel_workers` defaults to one. Increasing it is trusted profile policy
and therefore changes the effective profile fingerprint/requires the existing
trust ceremony. Execution approval additionally binds the current isolated batch
and ownership.

This is **not** an OS security sandbox. Git worktrees separate cooperating file
writes but provider processes still run as the same local user and can in
principle attack paths outside their cwd, Git metadata, controller state or other
processes. Existing native provider sandbox/tool restrictions and post-execution
integrity checks remain defense in depth, not an adversarial boundary.

A hard controller interruption can leave temporary Git worktrees. The task is
persisted as running before those effects begin; `recover` removes stale
worktrees and marks the task failed without replay. Automatic conflict repair,
rebase or interrupted-batch resume is deliberately unsupported.
