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

## v0.8 adaptive workflow authority boundary

v0.8 allows a model to propose task structure, not permissions. A
Supervisor-authored DAG cannot add providers, executables, models, validator
commands, semantic capabilities absent from the registry, protected-path policy,
external effects or project trust. It is compiled and capability-resolved under
the current trusted profile before a human sees the Start confirmation.

The exact proposed graph is immutable intake evidence and part of the HumanGate
scope. If a user revises an unconfirmed proposal, the old intake becomes
`superseded` only after a new bounded result is produced; a stale Start request
therefore cannot register the superseded proposal.

Persistent workflow learning is intentionally not exposed as an MCP agent tool.
Only the local operator CLI can create an evidence-backed candidate and save it,
and only after the source adaptive task is finally `succeeded` with a reviewed
snapshot. The candidate scope binds source intake/task, source DAG digest,
reviewed snapshot, target template/version and current profile digest. Saving
that template invalidates the prior profile trust and requires normal re-trust.

This remains a trusted-local application. An agent with independent unrestricted
same-user shell access could still invoke local operator commands despite Skill
instructions; v0.8 does not claim OS-level separation between the conversational
host and the operator account. The control-plane guarantee is that the MCP
surface itself does not expose template save/trust authority and the kernel does
not infer persistent authority from model output or task success.


## v0.8.1 Antigravity provider boundary

The built-in `agy` adapter uses Antigravity's official non-interactive
stream-json interface, JSON Schema output, and terminal sandbox. Prompts are sent
over stdin rather than process argv. The adapter never passes
`--dangerously-skip-permissions` and accepts a provider result only when the
terminal event reports `status=SUCCESS` and includes schema-valid
`structured_output`.

For implementation turns the adapter uses `--mode=accept-edits` so workspace
file writes can complete without an interactive diff prompt. Non-write phases use
`--mode=plan`. Orchestrator's own protected-path, control-snapshot,
allowed-path/write-set, validator and independent-review checks remain mandatory
after provider execution.

Antigravity also has user/global permission, MCP, plugin and web settings.
The adapter deliberately does not rewrite or delete those user settings. Under
Antigravity's normal headless/default permission behavior, workspace file access
is allowed while web/MCP or unsandboxed operations that require approval are
soft-denied when no interactive confirmation is available. However, an operator
who has globally configured broader Antigravity authority (for example Turbo,
explicit web/MCP allow rules, or trusted plugins) has broadened the provider
process itself. ai-orchestrator does not claim to revoke that external authority.

Accordingly, AGY remains inside the project's trusted-local provider boundary.
Use conservative Antigravity permissions for orchestrated workers, keep terminal
sandboxing available, and do not treat the Orchestrator prompt rule against
external effects as a substitute for provider-native permission policy.


## v0.8.4 guarded shared writes

For Workflow Schema tasks with an exact `allowed_paths` contract, a writable
implementer declared as `workspace: shared` is now executed in a private
runtime worktree. The provider never receives the user's project worktree as its
writable cwd. Its structured result is validated first, then changed paths are
checked against the exact allowed set, then a deterministic binary patch is
prepared/integrated and finally applied to the project only if root/control/
protected snapshots are still unchanged.

Consequently, provider result parsing failure, blocked output, cancellation, or
write ownership violations do not leave provider edits in the user's project.
Temporary runtime worktrees are removed on both success and ordinary failure.
Interrupted running tasks remain recoverable through the existing conservative
worktree cleanup path.

This guarantee applies to scoped Workflow Schema execution. Legacy persisted
manual/state-machine tasks without exact `allowed_paths` remain compatible with
their prior shared-worktree semantics.

Provider failure diagnostics stored in events are intentionally content-free:
status, envelope field names, value types, JSON field names and byte counts only.
Raw prompts and provider response bodies are never copied into diagnostic events.


## v0.8.5 Antigravity headless permission limitation

Live AGY 1.2.14 testing confirmed that `--mode=accept-edits` does not itself
authorize `write_file` in headless mode. A denied write can still produce
process exit 0 and terminal `status=SUCCESS`, with the actual denial reported
only through `denied_actions`. The adapter therefore treats any non-empty
`denied_actions` list as terminal failure before considering structured output.

The controller does not add `--dangerously-skip-permissions`: that switch
auto-approves every AGY tool category, not merely writes inside the private
worktree. AGY's documented persistent `permissions.allow` lives in provider
settings rather than a verified per-run settings path, so ai-orchestrator does
not rewrite that user-global authority automatically.

Operators may configure Antigravity's native scoped permissions themselves and
then explicitly trust/select that provider. Until such permission is present,
AGY is suitable for read-only/plan use but a writable headless turn will fail
closed. Guarded worktree isolation still guarantees that a failed writable turn
does not mutate the project worktree.


## v0.8.6 authority-control boundaries

Provider switching is no longer implemented as arbitrary model-driven YAML
editing. The agent-facing preview accepts only an existing provider slot and an
installed adapter ID. The resulting profile is fully validated before a
HumanGate can be prepared. The gate scope binds the current trusted profile,
exact before/after provider configuration, resulting profile digest, project
snapshot, protected snapshot and orchestration-control snapshot. Approval writes
only that provider slot, clears adapter-specific executable/model/effort
overrides, verifies the resulting digest and then records trust for exactly that
digest. A crash after config replacement but before trust leaves the new profile
untrusted.

Provider adapter changes are rejected while nonterminal tasks or unconsumed
intakes exist so frozen task/intake authority cannot be silently invalidated.

AGY `--dangerously-skip-permissions` is a distinct high-risk authority. It is
never inferred from execution approval, provider choice, a failed permission
request, or a model statement. A dedicated HumanGate stores a grant bound to the
task ID, attempt, resolved AGY node set, profile digest, pre-permission execution
scope and exact project snapshot. The normal execution HumanGate must then be
confirmed separately. Repair clears grants. Worktree drift makes a grant stale.

Even with this broad AGY permission, the controller retains `--sandbox`,
guarded private worktrees, exact allowed-path ownership, deterministic patch
integration, validators, cross-provider review and final acceptance. These
controls do not turn `--dangerously-skip-permissions` into a narrow file-write
permission; the provider may auto-approve all of its native tools during that
scoped session, which is why the separate gate is mandatory.


## v0.8.7 binding cleanup boundary

Binding cleanup is an authority-state transition, not a filesystem rollback.
The read-only preview enumerates exact selected unfinished task/intake IDs and
hashes their current persisted state. The dedicated HumanGate binds those states,
the current trusted profile, project snapshot, protected snapshot and control
snapshot. Any drift makes the form stale.

On confirmation, all selected rows are revalidated and updated in one SQLite
transaction. Tasks become `abandoned`; proposed/clarification intakes become
`withdrawn`. Audit events are retained. Task files, artifacts, accepted or
unaccepted workspace edits and Git state are not deleted or restored.

Running bindings and already-terminal bindings are rejected. Cleanup never
implicitly changes provider configuration or grants execution/provider
permissions. Provider-change confirmation must be requested separately after
the blocker set is empty.


## v0.8.8 content-free provider telemetry

AGY stream-json contains tool parameters and outputs that may include source
paths, commands, file contents or other sensitive task data. The controller does
not persist those fields. The telemetry extractor reads only `step_type=tool`,
`tool_name`, `step_index` and `state` in memory; step indexes are used only
to collapse AGY's ACTIVE -> DONE/ERROR updates and are not stored.

The resulting event contains the provider identifier, sorted tool names and
aggregate DONE/ERROR/other counts. Raw stream-json, tool_info, parameters,
commands, target paths, outputs, tool errors, prompts, response text and
conversation IDs are excluded by construction.

Telemetry is emitted for both successful and failed calls but has no authority
semantics. Denied actions remain terminal failures, broad AGY permission still
requires its dedicated HumanGate, and guarded worktree/write-set enforcement is
unchanged.


## v0.8.9 confirmation presentation

HumanGate display is no longer a serialization of the entire authority-bound
preview. The persisted gate still contains the complete preview and the scope
still binds exact task/intake state, kernel scope, trusted profile, worktree,
protected paths and orchestration controls. Before applying a Yes response the
controller recomputes those values exactly as before.

The client-facing form is a bounded summary intended to keep decision-critical
facts visible even in clients that collapse long elicitation messages. Compact
presentation must never be interpreted as reduced authority binding.

Binding-cleanup forms are limited to 12 exact IDs per confirmation so every
abandoned/withdrawn target can remain visible. High-risk provider-permission
forms must display the broad AGY permission effect and separate-execution-gate
requirement explicitly.


## v0.8.10 atomic provider change-set boundary

A provider change-set is still a bounded authority mutation, not arbitrary
configuration editing. The agent may supply only a mapping from existing provider
slot IDs to installed adapter IDs. The controller rejects empty sets, unknown
provider slots, unknown adapters and no-op entries, and resets vendor-specific
`executable`, `model` and `effort` fields on every changed slot.

All requested adapter changes are applied to an in-memory profile copy first.
Capability resolution, workflow compilation and cross-provider review separation
are evaluated only on that final combined profile. Intermediate single-slot
profiles are never written, trusted or treated as authority.

The dedicated HumanGate binds the exact change-set, current trusted profile,
resulting profile digest, project/worktree snapshot, protected paths and
orchestration controls. Active task/intake bindings block the change-set just as
they block a single provider change. Binding retirement requires its own separate
HumanGate.

On confirmation the controller re-previews the exact set under the project lock,
revalidates the final profile, atomically replaces `.orchestrator/config.yaml`,
verifies the resulting digest and records trust only for that digest. A crash
between filesystem replacement and trust remains fail-closed because the new
profile is left untrusted.


## v0.9.0 model/effort authority boundary

A model or effort label is execution policy, not a semantic capability and not
provider authority. Model Variant Resolution runs only after Provider Resolution;
a task override cannot select a different provider or grant a capability,
permission, executable, validator, external effect or persistent policy change.

Task/node runtime overrides are ephemeral and scope-bound. The Supervisor is told
to emit them only when the user explicitly requests model/effort/execution
intensity and never to raise cost/effort autonomously. Start confirmation shows
the requested override; execution confirmation shows the exact resolved
provider/adapter/model/effort. The full state remains bound even when the compact
form omits verbose provenance.

Enumerated runtime-option domains are validated fail-closed. Pass-through domains
are intentionally weaker: they mean the adapter can place the provider-local
value on a controlled invocation but cannot prove a complete set of valid model
IDs or effort values. A pass-through descriptor must disclose that limitation,
and a provider CLI may still reject the value before work completes. The kernel
does not convert that failure into an implicit downgrade or fallback.

The descriptor itself is provenance. Once a task binds a node, its descriptor
digest and resolved settings are frozen. Adapter metadata drift, profile drift or
runtime override drift requires fresh task/approval authority rather than silent
continuation. This consistency mechanism still does not defend against a hostile
same-OS-user actor rewriting installed controller/provider code.


## v0.9.1 read-only provider hardening

Supervisor, Planner and Reviewer are given disposable project snapshots outside
the controller worktree. `.orchestrator` and ignored ambient files are not
materialized, project symlinks fail closed rather than being followed, and
provider writes to the snapshot cause the call to fail. This
reduces accidental control-plane discovery such as inspecting task/runtime files;
it is not an OS security boundary. A provider command can still be subject to its
own native permission policy and sandbox behavior.

In particular, the controller does not automatically grant AGY
`--dangerously-skip-permissions` to make headless read-only calls succeed.
Provider-native permission denials remain fail-closed. Operators should not
progressively widen global provider command permissions merely to accommodate
model-generated shell syntax.

Review independence is an error-diversity policy, not a security proof.
Different provider families qualify. Same-family review qualifies only when both
resolved provider-local model IDs are explicit and unequal. Aliases are compared
literally, so two different strings can still refer to related or equivalent
vendor models; operators remain responsible for model selection.


## Provider dispatch provenance boundary

`provider_provenance` and Supervisor dispatch provenance are generated by the
controller from the exact `RunRequest` handed to an adapter. They prove what the
controller attempted to dispatch under cooperating-process assumptions. They do
not cryptographically prove that a remote provider received, honored or executed
those settings, and they are not a substitute for provider-side audit logs.

The provenance is content-free by design: it does not retain prompts, tool
arguments, shell commands, model response text or workspace paths. Read-only
workspace evidence records only structural booleans/mode plus the seed snapshot
digest.


## Provider permission-denial diagnostics

AGY permission-denial evidence is adapter-sanitized before it reaches durable
state. The controller may retain the action type, a command executable basename,
boolean shell-shape indicators (pipe/redirection/chaining/subshell), simple
identifier-like permission/rule/policy/reason codes, denial counts and tool names.
It does not retain denied command text, argv, paths, arguments, provider messages,
free-form reason text, prompts or response content.

Supervisor failures expose this metadata directly on the intake because no
TaskState exists yet. Task-node failures store the same sanitized metadata in a
hash-verified `provider_failure` artifact. The diagnostics also record whether
the task-scoped AGY dangerous-skip permission was requested; a denial never
silently enables that permission.
