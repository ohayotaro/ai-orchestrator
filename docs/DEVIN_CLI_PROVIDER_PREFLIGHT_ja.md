# Devin CLI provider — read-only qualification preflight (Japanese)

Status: **PROVIDER EXECUTION NOT ENABLED / NOT OWNER-LIVE QUALIFIED**. Scope:
Devin CLI 3000.11.3 (build 9c803229faa4) as a *delegated implementation provider*
behind a separately qualified Claude Code HumanGate host. This is not a Devin-host
MCP form test; the owner measured Devin host `form_supported=false`.

## Purpose and release separation

The draft independent distribution
`integrations/devin_provider/ai-orchestrator-provider-devin` contains Provider
SDK v1 / Adapter API v2 metadata and an offline fixture protocol harness. Its
actual `Adapter.execute()` **always refuses before dispatch**, with
`failure_category=configuration`. It deliberately advertises no
`code_edit` or `write_files` capability. Do not pin, trust, route paid tasks
to, or publish this prototype expecting working Devin implementation.

Keep v1.0.1's approved source tree, release manifest, CI evidence, tags and
artifacts unchanged. No experimental plugin execution is qualified by a
successful core/fixture CI run.

## Phase 0 — read-only terminal inspection, no agent calls

Use a **normal terminal**, not a nested Claude/Devin agent shell, on a clean
disposable project. Before running any command, verify that you are not inside
a previous v1.0.0/v1.0.1 qualification fixture.

Capture only command versions and presence/path metadata. Do not display tokens,
secret values, full user/project configurations or historic session content.

```bash
command -v devin
devin --version
devin --help
devin sandbox setup
```

The user previously observed `devin 3000.11.3 (9c803229faa4)`, with
`--print`, `--prompt-file`, `--config`, `--sandbox`,
`--permission-mode`, `--model` and
`--respect-workspace-trust`. If an update changed the version or help
contract, classify as **REVIEW REQUIRED**, not implicitly supported.

With the project root and user home resolved, inspect only **presence and
file-type** of relevant config paths; do not dump contents:

```bash
for path in \
  "$HOME/.config/devin/config.json" \
  "$HOME/.config/devin/mcp_config.json" \
  ".devin/config.json" \
  ".devin/config.local.json" \
  ".devin/mcp_config.json" \
  ".devin/mcp_config.local.json"; do
  if test -e "$path"; then stat -f '%N %HT' "$path"; else printf '%s absent\n' "$path"; fi
done
```

Inspect whether imported configurations, hooks, native permission grants,
MCP servers and sandbox exclusions are present through an operator-controlled
redacted report. Merely passing `--config` with a temporary file does not
erase higher-precedence project settings and additive hooks. If their effects
cannot be established, keep execution blocked.

## Required next design/evidence gates

1. **Native response:** establish an authoritative, bounded final response
   for `devin --print` and demonstrate exact schema conformance. Printed
   prose, markdown code fences, a partially valid transcript, or exit code
   zero without validated payload are failures. Do not fabricate a
   `--json-schema` flag.
2. **Isolation:** demonstrate actual implementation write behavior in a fresh
   isolated worktree; negative checks cover root/outside-worktree files and
   external effects. Devin's sandbox excludes direct file-edit tools from
   sandbox confinement, and network filtering is not a proven blockade.
3. **Permissions:** verify all merged user/project/local policy layers,
   imported other-client settings, MCP servers and hooks. Never add
   `--permission-mode dangerous` or
   `--respect-workspace-trust false` as an unattended workaround.
4. **Fresh session and recursion:** no `--continue`, `--resume`,
   `--cloud`, auto-handoff, recursive ai-orchestrator MCP invocation,
   commit/push or deployment; verify with bounded real-host observation.
5. **Failure discipline:** timeout, cancellation, child process-group cleanup,
   permission denial, invalid output, rate limit/authentication and malformed
   version all refuse without retry or fallback. Unknown usage/cost stays
   unknown.
6. **Release identity:** pin plugin distribution/version/entry-point only after
   review, explicitly re-trust the project, then qualify the exact
   kernel/CLI/plugin/configuration with real owner-live permission gates.

## Stop here

The above is *read-only preflight*. Even a clean report is **not permission
to execute `devin -p`** or to create a task/HumanGate. Request a separate
explicit owner authorization for a bounded paid/live experiment. Until then,
retain the plugin's fail-closed `execute` implementation and leave the host
axis unsupported.
