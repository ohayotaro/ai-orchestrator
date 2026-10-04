# Provider Adapter / Plugin SDK

v0.13 makes the provider adapter boundary a public, compatibility-tested
extension surface. It does **not** create a generic executable plugin system for
workflows, validators, policies or knowledge.

## Trust model

A provider entry point is Python code that runs inside the controller process.
Accordingly, an enabled provider plugin is part of the trusted computing base.
Worker sandbox/worktree controls constrain provider execution; they do not
sandbox the adapter implementation itself.

Installing a distribution is not activation. AI Orchestrator enumerates
`ai_orchestrator.providers` entry-point metadata without importing plugin code.
External code is loaded only when all of the following are true:

1. the project profile contains an exact pin for the adapter ID;
2. the pin matches distribution name, distribution version and entry-point
   target exactly;
3. the exact current profile digest has already been explicitly trusted;
4. the adapter passes the SDK/API conformance checks.

A package update under a different version therefore fails closed until the
project pin is changed and the resulting profile is inspected/trusted. Package
pins express operator intent; they are not cryptographic integrity attestation
against a hostile same-OS-user installation.

## Packaging

Third-party distributions register one or more provider adapters:

```toml
[project.entry-points."ai_orchestrator.providers"]
acme = "acme_orchestrator.adapter:Adapter"
```

The entry-point name is the adapter ID. The target may be an adapter instance,
a zero-argument adapter class, or a zero-argument factory.

The project then pins the exact package identity in
`.orchestrator/config.yaml`:

```yaml
provider_plugins:
  acme:
    schema_version: 1
    distribution: acme-orchestrator-provider
    version: "1.2.3"
    entry_point: acme_orchestrator.adapter:Adapter
```

Changing this block changes profile authority and therefore requires the normal
profile inspection/trust ceremony. The MCP agent surface cannot add or trust a
plugin pin. After a trusted pin is active, the ordinary bounded provider-change
flow may select that adapter for an existing provider slot.

Use:

```bash
orchestrator --project /path/to/project provider-plugins
orchestrator --project /path/to/project trust --by "$USER" --ack-local-execution
orchestrator --project /path/to/project doctor
```

On an untrusted profile, `provider-plugins` is metadata-only and must not
import configured plugin code. On a trusted profile, constructing the controller
may load an exactly pinned adapter first; the command then reports both installed
metadata and its load/conformance status.

## Required core adapter contract

External adapters use Provider SDK v1 and Provider Adapter API v2:

```python
from ai_orchestrator.provider_sdk import (
    ProviderExecutionError,
    RunRequest,
    RuntimeOptionsDescriptor,
    UsageDescriptor,
)

class Adapter:
    provider_sdk_version = 1
    api_version = 2
    family = "acme"

    capabilities = frozenset({
        "read_files", "write_files", "fresh_session", "structured_output"
    })
    semantic_capabilities = frozenset({
        "repository_analysis", "planning", "code_edit", "review", "supervision"
    })

    def doctor(self, config, workspace):
        return {"version": "1.2.3", "family": self.family}

    def execute(self, request: RunRequest):
        ...
```

`doctor` and `execute` are the required lifecycle methods.
`describe_runtime_options`, `describe_usage` and `role_compatibility` are
optional features. Absence must remain explicit; the kernel does not invent
model catalogs, token counts, costs or compatibility claims.

The adapter receives the same `RunRequest` used by built-in adapters. Provider
specific protocol/CLI handling belongs in the adapter. HumanGate, write/effect
scope, deterministic validators, budget policy, recovery and task authority
remain kernel contracts.

## Conformance kit

Third-party packages can exercise the public structural contract in their own
tests:

```python
from ai_orchestrator.provider_sdk import assert_provider_adapter_conforms

def test_adapter_contract():
    report = assert_provider_adapter_conforms("acme", Adapter())
    assert report["provider_sdk_version"] == 1
```

Passing `config=` and `workspace=` additionally validates the adapter's
`doctor` result and any optional runtime/usage descriptors. The conformance
helper deliberately never invokes `execute`, because provider dispatch may be
billable or effectful.

Provider failures should raise `ProviderExecutionError` when the adapter has
safe structured diagnostics to retain. The plugin wrapper normalizes external
execution diagnostics before they can enter durable controller state: mappings,
lists and nesting are bounded; string values must be identifier-like labels; the
public failure categories are `authentication`, `quota`, `permission`,
`configuration`, `protocol` and `provider_process`. Unsafe diagnostics are
omitted and replaced with a content-free protocol-failure marker.

Raw prompts, credentials, commands/arguments, provider response bodies and
arbitrary stderr must never be placed in diagnostics. External execution
exception text and doctor/optional-probe exception text are not surfaced
verbatim by the wrapper. The kernel never treats a failure category as
authorization for retry or fallback.

The repository regression suite also contains a non-core fixture adapter loaded
through the same metadata/pin path. This verifies that a new provider adapter can
be added without editing the resolver, workflow engine, HumanGate, usage/budget
or recovery code.

## Failure semantics and provenance

Missing packages, version/entry-point mismatch, built-in ID collision,
unsupported SDK/API version, import/factory failure and contract failure all
exclude the adapter from the active registry. Provider resolution then fails
closed rather than falling back implicitly.

Loaded plugin identity is attached to provider descriptors/resolutions and
controller dispatch provenance. Frozen tasks revalidate that identity. This is
controller-side provenance of the selected installed plugin contract; it is not
provider-side attestation that a remote service honored a request.
