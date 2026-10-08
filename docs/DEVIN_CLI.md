# Devin CLI integration

Status: **DESIGN / NOT LIVE-QUALIFIED**. Researched on 2026-10-08. Proposed feature line: **v1.1.0 — Devin CLI Integration**; this document does not bump a version, implement an adapter, or declare support.

## DV-01 / DV-02 observed read-only preflight — 2026-10-08

**Owner-reported, not independently rerun in this PR.** The operator ran the
version/help/Skill-path commands on their Mac, then asked Devin CLI to invoke
only `inspect_project` against a fresh disposable
`devin-host-probe` project. No task, provider call, validator, HumanGate,
configuration/trust mutation, or workspace edit was performed.

| Axis | Measured result | Classification |
| --- | --- | --- |
| Official local CLI | `devin 3000.11.3 (9c803229faa4)` | DV-01 PASS |
| Binary | `~/.local/bin/devin` on owner's Mac | OBSERVED (local path, not packaged identity) |
| stdio MCP transport | Connected, `inspect_project` returned | DV-02 PASS |
| MCP client / protocol | `rmcp 3.1.0`, negotiated `2025-06-18` | PASS |
| Form elicitation | `advertised=false`, `form=false`, `url=false`, `host_confirmation.form_supported=false` | **UNSUPPORTED for this exact host version/configuration** |
| Start/Execution/Acceptance Yes/No/Cancel | No form request attempted | NOT TESTED |
| Single-terminal | `enabled=true`, worker automatic but `manager_started=false` | Configuration only; not authorization |
| Controller | `ai-orchestrator-kernel 1.0.0`, loaded=disk build `eb25ca9a5873b0a4ee6fc63159129a5917b6bb741bae9660f14782ba840255e4` | PASS identity; **not** a v1.0.1 test |
| Packaged Skill | reported SHA-256 `6fd02ef76fb6d5128d2fb571df7d2edf8ae13d6483deff540301ead8729f1f8f` | Reported identity; no independent Skill-content audit |
| Project trust | `trusted=false`, profile digest `4e2e0ceda82785c31609096f06b0948669fc7ac9780b9ee8a031782591eb661e` | Expected independent setup gate |
| Provider roles | Claude supervision/planning/review, Codex implementation; no external plugin pin | Existing configuration only |
| Product defect | None observed | No failing invocation claimed |

**Decision:** no single-terminal Devin-host support claim. Current host does not
advertise the required MCP form-elicitation capability, so the controller must
fail closed. Trusting the profile does **not** change that transport capability.
Do not try a HumanGate as a workaround, let Devin answer for the owner, or
substitute CLI approval. Keep host support blocked until a different exact
Devin version/configuration demonstrates real correlated form responses.

The next workstream is a **separate** Devin provider adapter under the already
supported Claude Code host. It does not convert this host result into PASS.

## Scope and release boundary

Target Cognition's official local `devin` CLI, not a similarly named unofficial wrapper for the Devin Cloud API. Keep two independent integration axes:

| Axis | Initial configuration | Exit evidence |
| --- | --- | --- |
| Host | Devin CLI conversation -> existing orchestrator MCP server -> Claude reasoning/planning/review + Codex implementation | Actual negotiated form capability and real correlated HumanGate responses |
| Provider | Already qualified host -> orchestrator -> separately pinned Devin provider plugin | Exact-version noninteractive process, result validation, permission, cancellation and write-scope evidence |

Start with the host axis because it may work through the existing MCP/Skill interface without a kernel change. Do not change the provider roles at the same time; that would obscure which integration failed. Only qualify Devin-host plus Devin-provider after each axis works independently.

This is feature work, not part of the frozen v1.0.1 documentation/packaging maintenance candidate. Preserve its approved commit, tree, distributions and approval evidence. Do not merge this proposal into a release candidate or rebuild/relabel its artifacts to include it. The existing [v1.0.1 plan](V1_0_1_RELEASE.md) remains separate.

## Verified documentation versus open questions

Official documentation provides a stdio MCP registration command, project/local/user scopes, and native Skill discovery [D1, D2]. It also describes `devin -p`, `--prompt-file`, explicit model selection, configuration, session continuation and an ACP server [D3]. These are integration entry points, not qualification evidence.

The reviewed MCP documentation does **not establish** support for the orchestrator's `elicitation/create` form exchange. The reviewed command reference also does not establish a schema-constrained final-result contract equivalent to the existing adapters. Neither omission proves the feature is absent. Capture the installed CLI's exact version/help and test the relevant behavior before selecting flags or advertising capabilities.

The sandbox documentation describes fail-closed startup but writable workspace paths, configurable command exclusions, and unstable network filtering [D4]. Do not infer strict read-only or complete network isolation merely from `--sandbox`.

Model aliases can resolve to newer models and the CLI supports configurable thinking levels [D5]. An alias is not proof of the resolved model, and interactive thinking controls are not proof of a headless effort flag. Record requested and observed values separately.

## DV-01: installed CLI contract inventory

Run local metadata inspection before any delegated model execution:

```bash
command -v devin
devin --version
devin --help
devin mcp add --help
devin skills paths
```

Stop on an unexpected error and retain the version/help result rather than trying unrelated similarly named CLIs. Authentication remains operator-owned; do not print credentials, export sessions, or scrape home-directory history. `devin models list --format json` is a documented optional account-dependent discovery command, not an offline probe [D3]. Do not invoke it merely to manufacture a static catalog.

Record OS/architecture, CLI executable identity, version, relevant flags and configuration sources. Do not copy arbitrary environment values or secrets into diagnostics. A local inspection cannot attest the human-facing host transport.

## DV-02: host integration first

Use a new dedicated disposable project, not the old v1.0.0 qualification fixtures. Prepare the fixture and operator trust before the read-only preflight. Use an already verified orchestrator wheel/venv; do not switch to an editable candidate accidentally. Inventory the baseline after setup, including known validator-check evidence and controller files.

The documented registration shape below assumes `PROJECT` and `ORCH` have already been set to inspected absolute paths. It is an operator setup action, not part of the read-only preflight:

```bash
cd "$PROJECT" && devin mcp add --transport stdio --scope local ai-orchestrator -- "$ORCH" --project "$PROJECT" serve
```

Inspect an existing registration rather than deleting or replacing it blindly. Use the CLI command instead of guessing an MCP JSON filename: the official configuration page describes a version-dependent migration to dedicated MCP configuration files [D1]. Restart in the intended project after registration.

Export the unchanged packaged Skill to a native Devin Skill location, inspect any existing file before replacement, and verify its hash through `orchestrator identity --skill ...`. Global `~/.config/devin/skills/<name>/SKILL.md` and project `.devin/skills/<name>/SKILL.md` are documented locations [D2]. Check actual discovery and precedence; do not silently edit the Skill to make the host accept it.

Use [the read-only Japanese preflight prompt](DEVIN_CLI_PREFLIGHT_ja.md) first. Confirm the actual server's project binding, package/build/Skill identity, negotiated protocol, and form capability. An MCP tool list or ordinary tool permission dialog is not a HumanGate. No advertisement, negotiation failure, or missing form means fail closed, not CLI/chat approval fallback.

After separate authorization for the live campaign, preserve actual evidence for Start/Execution/Acceptance Yes, genuine No, Start and Execution cancel, no-decision handling, timeout, response-time stale rejection, and idempotent request replay. Keep unsupported UI cases explicitly NOT TESTED; distinguish controller-side stale checks from a stale response after form display, and request replay from duplicate wire responses. The host model's own conversation may incur cost even when orchestrator provider-call deltas are zero.

Do not create paid proposals merely to test metadata. When live tests are authorized, reuse one declared campaign's valid evidence across coverage categories where justified, never call it a fresh independent rerun. Scope effect counters to the gate interval so setup Supervisor/Planner calls are not confused with forbidden implementation dispatch.

## DV-03: provider integration through the existing SDK

Prefer a separately distributed, opt-in `devin` adapter using [Provider SDK v1 / Adapter API v2](PROVIDER_SDK.md). A tentative distribution name is `ai-orchestrator-provider-devin`; it has not been created, reserved or published. Pin the exact distribution/version/entry point and require operator profile review and trust before activation. Do not subclass private adapter helpers or make kernel resolver/authority changes merely to add a vendor.

Before implementation is declared runnable, close these adapter contracts:

- **Invocation and identity:** resolve the official executable, require supported flags, use a fresh process/session, and never continue/resume another task's session. Keep task prompts out of argv where the CLI permits file/stdin transport; protect temporary files and clean them without deleting evidence.
- **Completion and output:** establish a bounded authoritative final response channel for the exact CLI version; validate against `RunRequest.result_model`. An exit code of zero, arbitrary text, a partial stream, or an ATIF transcript is not a validated result. Do not invent a JSON-schema flag or salvage malformed output into success. ACP is an alternative only after an explicit adapter/protocol design; ACP is not MCP form support.
- **Permissions and isolation:** inspect effective native configuration, imports, hooks, MCP tools, sandbox exclusions and writable roots. For planning/review/supervision, establish read-only behavior rather than trusting a prompt or mode label. For implementation, permit only the approved isolated workspace and retain kernel write-set checks. Unattended permission/trust prompts must fail closed; do not automatically add bypass or trust-skipping flags. Both native trust and orchestrator trust matter, especially for newly created worktrees.
- **No recursive orchestration or cloud effects:** a delegated Devin process must not inherit an active ai-orchestrator MCP connection and re-enter its controller. No automatic `/handoff`, cloud session creation, commit/push/deployment, or recursive autonomous loop. Use verified configuration isolation; refuse the role if it cannot be established. The model service remains remote; local execution is not offline inference.
- **Runtime options and usage:** preserve Devin as the adapter identity even when it selects a model from another vendor. Pass only confirmed model/effort options; unsupported explicit effort is an error, not a silently dropped option. Initial qualification uses a fixed observed selection where available. Adaptive/Fusion require separately disclosed routing/provenance, not hidden fallback. Unavailable usage/cost stays unknown; never estimate a precise provider cost to satisfy a strict budget.
- **Cancellation and failures:** cancellation must stop the process tree and prevent later dispatch; test timeout, malformed output, authentication/quota failures and interrupted execution. Keep safe bounded diagnostics and preserve the kernel's conservative recovery/no-automatic-paid-retry semantics.

Enable only roles whose contracts pass. In particular, implementation-only support does not imply planning/review support, and a provider plugin does not qualify Devin as a host.

## DV-04: automated and live evidence

Build provider tests with fake CLI processes and synthetic protocol fixtures, marked as automated rather than owner-live evidence. Cover argument injection, missing flags, version mismatch, bad/oversized/partial results, unsupported effort, imported broad permissions, recursive MCP access, cancellation, timeout and plugin pin/trust failures. Preserve existing Claude/Codex/AGY contracts and persistence versions.

Run applicable contract/regression/distribution checks in CI before owner-live verification. Start the provider-live campaign with the already qualified host and Devin implementation only. Add read-only roles and the combined Devin-host/provider configuration only when independently evidenced. Do not require a complete paid campaign for every intermediate edit; freeze the actual tested artifact/plugin/configuration before the final campaign.

## DV-05: support and release records

Track host transport and each provider role separately by exact CLI/kernel/plugin, Skill, model/effort mode, OS/Python and native permission assumptions. Initial Devin status is **unverified** on both axes. Do not alter the published v1.0.0 support record or claim its tests exercised Devin.

The existing v1.0.0 release checker encodes a Claude-host/Claude-reasoning/Codex-implementation baseline. A future Devin release needs a reviewed evidence contract for additional deployments, with negative tests; do not relabel a Devin deployment as Claude or bypass the original checker to obtain READY. Preserve historical manifests and all publication authority boundaries. No model-provider account changes, credentials, release tag, publication or real-host approval are authorized by this design document.

## Sources

Official pages reviewed on 2026-10-08; the deployed CLI still requires measurement.

- [D1: Devin MCP configuration](https://docs.devin.ai/cli/extensibility/mcp/configuration)
- [D2: Devin Skill locations and discovery](https://docs.devin.ai/cli/extensibility/skills/overview)
- [D3: Devin commands and flags](https://docs.devin.ai/cli/reference/commands)
- [D4: Devin sandbox](https://docs.devin.ai/cli/sandbox)
- [D5: Devin model selection](https://docs.devin.ai/cli/models)
- [Kernel Provider SDK](PROVIDER_SDK.md)
- [Current HumanGate integration](SINGLE_TERMINAL.md)
- [Current support boundaries](SUPPORT.md)
