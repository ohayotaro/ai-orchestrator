# Devin CLI provider prototype (NOT LIVE-QUALIFIED)

This is a separately packaged, **inactive-by-design** Provider SDK v1 / Adapter
API v2 integration prototype. Its entry point is `devin`. It is not the Devin
MCP host and does not add HumanGate support to Devin CLI.

The owner observed Devin CLI 3000.11.3 (`9c803229faa4`) with working MCP stdio
and `inspect_project`, but the Devin host advertised **no form elicitation**.
No live provider execution, native permission or result contract has been
qualified for this CLI. Therefore `Adapter.capabilities` and
`semantic_capabilities` are empty, and `Adapter.execute` always fails *before*
launching Devin. An installed plugin is neither automatic activation nor a
supported provider: explicit distribution/version/entry-point pin and project
re-trust are required by the kernel, and `code_edit` resolution still fails.

`ProtocolHarness` exercises only fake local commands. It demonstrates a
candidate implementation-only invocation with a private prompt file, no CLI
prompt in argv, `--sandbox`, strict JSON/result-model parsing and bounded
child-process cancellation. The initial prototype used
`--permission-mode autonomous`, which the owner's exact Devin CLI 3000.11.3
does **not** advertise. The fixture now uses the **observed** `auto` option,
checks its explicit help advertisement, and rejects direct real-`devin`
binary execution in the default test runner. `auto` permits read-only tools
without automatically granting workspace edits; it is **not** unattended
Implementer authorization. This harness is deliberately **not wired to
Adapter.execute**.

Reasons not to enable it yet:

- `devin --print` documents plain printed output, not a native schema-bound
  terminal result. A prompt asking for JSON is not a guarantee.
- The operator's read-only preflight on 2026-10-09 returned
  `REVIEW_REQUIRED`: 8 possible imported config sources were not explicitly
  disabled, one project-local MCP registration existed in the reused host
  fixture, and team/session policy, direct write scopes, network isolation,
  trusted headless execution and terminal-result authority remained unknown.
  None of these findings is resolved merely by switching the fixture flag to
  `auto`. Even the all-false import switches in the **synthetic** config are
  not evidence that native effective config was isolated.
- Devin merges user/project/local config and hooks, can import other tools'
  settings and MCP servers, and its sandbox does not enclose direct edit/write
  tools; the harness's temporary config is therefore **not** an attested
  isolation boundary.
- `--sandbox` network filtering is documented as unstable. A local CLI process
  still uses a remote model service, and no cloud handoff/remote effect
  isolation has been measured.
- Headless workspace-trust handling, child cancellation, imported permissions,
  fresh-session isolation, usage/cost fields and model IDs require actual
  owner-local evidence on the intended CLI revision.

Next step: run the read-only preflight from `docs/DEVIN_CLI_PROVIDER_PREFLIGHT_ja.md`
then independently authorize a tightly scoped live campaign with Claude Code
as HumanGate host and Devin *only* as Implementer. Future activation must be a
reviewed new adapter version, not a runtime flag bypassing this refusal.
