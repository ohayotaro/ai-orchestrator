# Security and operational limitations

## This is a trusted-local alpha, not a production isolation boundary

Use a disposable Git worktree, a trusted project and trusted CLI configuration. Do not attach production credentials. Do not use v0.1 to enforce live-trading, deployment, regulated-data, submission or other external-action approval requirements. The task flag `external_effects: true` is rejected, but the controller cannot infer every possible external consequence from a natural-language goal or from arbitrary code.

The controller and provider CLIs run as the same local OS user. That user, a malicious subprocess, or an agent with sufficient file/shell access could modify the runtime database, trust records, approvals, installed controller code, or files outside the expected workspace. Hashes and locks protect consistency between cooperating processes, not against a hostile same-user actor. Approval actor strings are audit labels, not authenticated human identities.

A future hardened mode needs a separately authenticated controller/approval service, isolated workers, protected control state, narrowly scoped credentials, OS filesystem/network restrictions, and enforcement outside agent-writable files. Do not claim those guarantees for this release.

## What is enforced by the controller

Unknown schemas/fields and unsafe control paths are rejected. Untrusted or changed active profiles cannot start normal workflows. Required adapters/capabilities must be present. T3 execution requires explicit approval, and successful writes cannot skip runner validation or review. Scope changes invalidate approval; worktree changes after review prevent acceptance. Repair loops, model calls, execution duration and output capture are bounded. Prompts go through stdin and subprocesses use argument arrays, never `shell=True`.

An exclusive project lock serializes cooperating mutating commands. Artifact hashes are checked before reuse and acceptance. Detected out-of-scope/read-only modifications stop the workflow without a destructive automatic rollback. These after-the-fact checks are detection, not prevention.

## Provider controls differ

Codex requests native `read-only` or `workspace-write` sandboxing with approvals set to `never` and workspace command networking disabled. Its CLI authentication, configured endpoints, project/user integrations and platform support still matter. Model-service network requests are not the same as subprocess network access.

Claude receives only read tools during plan/review and file-edit tools during execution. Shell, web and agent-delegation tools are not requested. Optional MCP/setting sources are constrained, but an allowlist is not an OS sandbox. Managed configuration and CLI implementation changes can affect behavior. Inspect the effective CLI environment before trusting it. A new unsupported CLI version must not be treated as verified solely because `--help` contains expected flags.

Provider-family labels belong to adapter declarations. They do not attest which model a proxy, custom endpoint, or CLI configuration ultimately serves. Fresh sessions do not guarantee independent errors or prevent exposure to the same misleading project content.

## Validators execute code

Validators are exact, user-registered argv vectors. They are never generated from model output or shell-parsed from prose. Nevertheless, `pytest`, build tools and scripts can execute arbitrary repository code. They run locally, not in a separate OS sandbox. The environment is filtered and uses a temporary HOME, but filesystem/network access is not isolated and credentials elsewhere on disk remain accessible to malicious code.

Validator output tails receive best-effort common-secret redaction. This cannot detect every secret. Do not put secrets in arguments, task briefs, project context, proposals, test output, or result artifacts. Provider authentication may be available to provider tools under the CLI's own security model; the controller does not provide a credential broker.

## Snapshot and recovery boundaries

Worktree fingerprints cover Git-tracked files and non-ignored untracked files, including executable bits and symlink targets. They do not recursively audit submodules, ignored output, all Git metadata, or external storage. Protected paths additionally fingerprint explicitly listed files/directories, such as `.env`. Large files, special entries and very large worktrees fail with an explicit v0.1 limit instead of producing a misleading partial snapshot.

Runtime state is gitignored. Back it up through a consistent SQLite backup or with controllers stopped; copying an active database without its WAL can lose state. Artifacts and local CLI configuration can still contain sensitive data. Events are append-only through the public controller methods, not cryptographically tamper-proof against the local user.

Cancellation kills the subprocess process group, including ordinary descendants. It is not containment against a process deliberately escaping its group/session, nor does it undo already completed effects. Never automatically retry an interrupted execution. Inspect the worktree and recorded evidence, recover a stale `running` task to failed, and create a new task after understanding the partial effects.

A rejected/cancelled/failed task cannot be accepted. Cancelling a paused task sets a request flag; its last phase/status may remain visible until the next run. Acceptance also checks the flag.

## Project memory

Candidate statements and evidence are untrusted data. Promotion requires operator review of the exact digest. Approved Markdown influences model behavior, so prompt injection and incorrect generalization remain possible. Promotions do not grant machine permissions or create executable validators. A crash during promotion may leave the approved Markdown written before candidate metadata is updated; this changes the profile digest, requires retrust, and must be resolved manually rather than replayed over an existing target.

## Verification status

The initial test suite uses offline adapter doubles and real local Git/subprocess fixtures. It covers normal lifecycle, gate freshness, mutation detection, bounded retries, cancellation/timeouts, descendant cleanup, schema rejection, artifact integrity, and explicit promotion. It is not a penetration test, an external audit, or proof of safe real-provider execution. Authenticated Claude/Codex smoke tests and independently reviewed threat-model work remain required before broader use.
