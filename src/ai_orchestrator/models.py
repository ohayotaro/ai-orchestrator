"""Versioned contracts; JSON Schemas are generated from these same models."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_serializer, model_validator


class OrchestratorError(RuntimeError):
    """An actionable configuration, policy, state, or execution error."""


def identifier(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", value):
        raise ValueError("IDs must contain 1-64 ASCII letters, digits, underscores or hyphens")
    return value


def validate_allowed_paths(value: list[str] | None) -> list[str] | None:
    """Exact project-relative files. None preserves legacy/manual task behavior."""
    if value is None:
        return None
    result: list[str] = []
    for item in value:
        parts = item.split("/")
        if (not item or item.startswith(("/", "\\")) or "\x00" in item or
                any(part in ("", ".", "..") for part in parts) or
                parts[0] in (".git", ".orchestrator") or
                any(char in item for char in ("*", "?", "[", "]", "\\"))):
            raise ValueError("allowed_paths must contain exact project-relative files without globs, traversal or control paths")
        result.append(item)
    if len(result) != len(set(result)):
        raise ValueError("allowed_paths must not contain duplicates")
    return result


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    @field_validator("schema_version", mode="before", check_fields=False)
    @classmethod
    def version_is_integer(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("schema_version must be an integer, not a string or boolean")
        return value


class ProviderConfig(Contract):
    adapter: str
    executable: str | None = None
    model: str | None = None
    effort: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    priority: int = Field(default=100, ge=0, le=10000, strict=True)

    @field_validator("adapter")
    @classmethod
    def valid_adapter(cls, value: str) -> str:
        return identifier(value)

    @field_validator("capabilities")
    @classmethod
    def valid_capabilities(cls, values: list[str]) -> list[str]:
        normalized = [identifier(value) for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("provider capabilities must not contain duplicates")
        return normalized


class RoleConfig(Contract):
    provider: str | None = None
    instructions: str = ""
    # Legacy/runtime adapter requirements. New semantic requirements use capabilities.
    requires: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    candidates: list[str] = Field(default_factory=list)

    @field_validator("requires", "capabilities", "candidates")
    @classmethod
    def valid_identifiers(cls, values: list[str]) -> list[str]:
        normalized = [identifier(value) for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("role requirements/candidates must not contain duplicates")
        return normalized

    @model_validator(mode="after")
    def unambiguous_binding(self) -> RoleConfig:
        if self.provider is not None and self.candidates:
            raise ValueError("role.provider is a fixed override; do not also set candidates")
        return self


class ValidatorConfig(Contract):
    argv: list[str] = Field(min_length=1)
    timeout_seconds: int = Field(default=120, ge=1, le=3600, strict=True)
    env: dict[str, str] = Field(default_factory=dict)
    generated_paths: list[str] = Field(default_factory=list)

    @field_validator("env")
    @classmethod
    def safe_environment(cls, values: dict[str, str]) -> dict[str, str]:
        reserved = {"PATH", "HOME", "USERPROFILE", "TMPDIR", "PYTHONPATH", "PYTHONHOME", "BASH_ENV", "ENV"}
        for key, value in values.items():
            if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", key) or "\x00" in value:
                raise ValueError("validator environment requires uppercase names and NUL-free strings")
            if key in reserved or key.startswith(("GIT_", "LD_", "DYLD_")) or any(word in key for word in ("SECRET", "TOKEN", "PASSWORD", "API_KEY")):
                raise ValueError(f"validator environment key is reserved or credential-like: {key}")
        return values

    @field_validator("generated_paths")
    @classmethod
    def literal_generated_paths(cls, values: list[str]) -> list[str]:
        for value in values:
            parts = value.split("/")
            if not value or any(part in ("", ".", "..", ".git", ".orchestrator") for part in parts) or any(char in value for char in "*?[]\\\x00"):
                raise ValueError("generated_paths must be literal project-relative directories, without globs or control paths")
        return sorted(set(values))

    @field_validator("argv")
    @classmethod
    def valid_argv(cls, value: list[str]) -> list[str]:
        if any(not arg or "\x00" in arg for arg in value):
            raise ValueError("validator arguments must be nonempty and contain no NUL")
        return value


class BudgetCallLimit(Contract):
    provider: str
    model: str | None = None
    max_calls: int = Field(ge=1, le=10000, strict=True)

    @field_validator("provider")
    @classmethod
    def valid_provider(cls, value: str) -> str:
        return identifier(value)

    @field_validator("model")
    @classmethod
    def valid_model(cls, value: str | None) -> str | None:
        if value is not None and (not value.strip() or len(value) > 256):
            raise ValueError("budget model must be a nonblank provider-local identifier")
        return value


class BudgetPolicy(Contract):
    schema_version: Literal[1] = 1
    max_provider_calls: int | None = Field(default=None, ge=1, le=10000, strict=True)
    max_controller_elapsed_seconds: float | None = Field(default=None, gt=0, le=86400)
    max_provider_seconds: float | None = Field(default=None, gt=0, le=86400)
    max_input_tokens: int | None = Field(default=None, ge=1, strict=True)
    max_output_tokens: int | None = Field(default=None, ge=1, strict=True)
    max_reasoning_tokens: int | None = Field(default=None, ge=1, strict=True)
    max_total_tokens: int | None = Field(default=None, ge=1, strict=True)
    max_cost: str | None = Field(default=None, pattern=r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    unknown_usage: Literal["fail_closed", "allow"] = "fail_closed"
    call_limits: list[BudgetCallLimit] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_call_limits(self) -> "BudgetPolicy":
        keys = [(item.provider, item.model) for item in self.call_limits]
        if len(keys) != len(set(keys)):
            raise ValueError("budget call_limits must be unique per provider/model")
        return self


class PricingRule(Contract):
    schema_version: Literal[1] = 1
    provider: str
    model: str = Field(min_length=1, max_length=256)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    source: str = Field(min_length=1, max_length=500)
    version: str = Field(min_length=1, max_length=200)
    effective_from: str = Field(min_length=1, max_length=100)
    input_per_million: str | None = Field(default=None, pattern=r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
    output_per_million: str | None = Field(default=None, pattern=r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
    reasoning_per_million: str | None = Field(default=None, pattern=r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
    cache_read_per_million: str | None = Field(default=None, pattern=r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")
    cache_write_per_million: str | None = Field(default=None, pattern=r"^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")

    @field_validator("provider")
    @classmethod
    def valid_provider(cls, value: str) -> str:
        return identifier(value)

    @model_validator(mode="after")
    def has_rate(self) -> "PricingRule":
        rates = (
            self.input_per_million,
            self.output_per_million,
            self.reasoning_per_million,
            self.cache_read_per_million,
            self.cache_write_per_million,
        )
        if not any(value is not None for value in rates):
            raise ValueError("pricing rule requires at least one explicit rate")
        return self


class Policy(Contract):
    require_execution_approval: StrictBool = True
    # Compatibility name: True now requires an independent execution identity:
    # different provider family, or explicit distinct model IDs within one family.
    cross_provider_review: StrictBool = True
    protected_paths: list[str] = Field(default_factory=lambda: [".env"])
    max_attempts: int = Field(default=3, ge=1, le=10, strict=True)
    max_agent_calls: int = Field(default=12, ge=1, le=100, strict=True)
    call_timeout_seconds: int = Field(default=600, ge=1, le=3600, strict=True)
    task_timeout_seconds: int = Field(default=3600, ge=1, le=86400, strict=True)
    # v0.7 parallelism is explicitly opt-in. A value of 1 preserves v0.6 scheduling.
    max_parallel_workers: int = Field(default=1, ge=1, le=8, strict=True)
    # v0.10 adds explicit resource budgets. Legacy max_agent_calls/task_timeout_seconds
    # remain hard ceilings; a budget can only tighten them.
    budget: BudgetPolicy = Field(default_factory=BudgetPolicy)

    @field_validator("protected_paths")
    @classmethod
    def relative_paths(cls, values: list[str]) -> list[str]:
        for value in values:
            if not value or value.startswith(("/", "\\")) or ".." in value.split("/") or "\\" in value:
                raise ValueError("protected_paths must be project-relative paths without traversal")
            if value == "." or value.startswith(".orchestrator") or value.startswith(".git"):
                raise ValueError("control paths are handled separately; do not list .git or .orchestrator")
        return values


WorkflowArtifactType = Literal["plan", "implementation", "write_set", "validation", "review", "json"]


class WorkflowArtifactSpec(Contract):
    name: str
    type: WorkflowArtifactType

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        return identifier(value)


class WorkflowInputSpec(Contract):
    artifact: str
    type: WorkflowArtifactType
    optional: StrictBool = False

    @field_validator("artifact")
    @classmethod
    def valid_artifact(cls, value: str) -> str:
        return identifier(value)


class WorkflowNodeSpec(Contract):
    id: str
    kind: Literal["agent", "validator"]
    role: Literal["planner", "implementer", "reviewer"] | None = None
    depends_on: list[str] = Field(default_factory=list)
    inputs: list[WorkflowInputSpec] = Field(default_factory=list)
    outputs: list[WorkflowArtifactSpec] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    gate_before: Literal["execution"] | None = None
    writes: Literal["none", "task_allowed_paths"] = "none"
    run_for: Literal["all", "write", "advisory"] = "all"
    instructions: str = ""
    independent_of: list[str] = Field(default_factory=list)
    # Writable nodes may opt into a private Git worktree. Ownership is exact-file
    # based so integration can fail closed before touching the user's worktree.
    workspace: Literal["shared", "isolated"] = "shared"
    write_paths: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def valid_id(cls, value: str) -> str:
        return identifier(value)

    @field_validator("depends_on", "capabilities", "independent_of")
    @classmethod
    def valid_identifier_list(cls, values: list[str]) -> list[str]:
        normalized = [identifier(value) for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("workflow identifier lists must not contain duplicates")
        return normalized

    @field_validator("write_paths")
    @classmethod
    def valid_write_paths(cls, values: list[str]) -> list[str]:
        normalized = validate_allowed_paths(values)
        return normalized or []

    @model_validator(mode="after")
    def coherent_node(self) -> WorkflowNodeSpec:
        if self.kind == "agent":
            if self.role is None:
                raise ValueError("agent workflow nodes require a role")
            if self.role != "implementer" and self.writes != "none":
                raise ValueError("only implementer nodes may write project files")
            if self.writes == "task_allowed_paths" and self.gate_before != "execution":
                raise ValueError("writable workflow nodes require an execution gate")
            if self.workspace == "isolated":
                if self.role != "implementer" or self.writes != "task_allowed_paths":
                    raise ValueError("isolated workspaces are supported only for writable implementer nodes")
                if not self.write_paths:
                    raise ValueError("isolated writable nodes require nonempty exact write_paths")
            elif self.write_paths:
                raise ValueError("write_paths are only valid for isolated writable nodes")
        else:
            if (self.role is not None or self.capabilities or self.gate_before is not None or
                    self.writes != "none" or self.independent_of or self.workspace != "shared" or self.write_paths):
                raise ValueError("validator workflow nodes cannot declare agent role/capabilities/gates/writes/independence/workspace ownership")
        return self


class WorkflowProvenance(Contract):
    source: Literal["supervisor_evidence"]
    intake_id: str
    task_id: str
    source_workflow_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewed_snapshot: str = Field(pattern=r"^[a-f0-9]{64}$")
    saved_by: str = Field(min_length=1, max_length=200)
    parent_template_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @field_validator("intake_id", "task_id")
    @classmethod
    def valid_ids(cls, value: str) -> str:
        return identifier(value)


class WorkflowSpec(Contract):
    schema_version: Literal[1] = 1
    id: str
    nodes: list[WorkflowNodeSpec] = Field(min_length=1)
    repair_on: str | None = None
    repair_from: str | None = None
    template_version: int = Field(default=1, ge=1, le=1000000, strict=True)
    provenance: WorkflowProvenance | None = None

    @field_validator("id")
    @classmethod
    def valid_id(cls, value: str) -> str:
        return identifier(value)

    @field_validator("repair_on", "repair_from")
    @classmethod
    def valid_optional_id(cls, value: str | None) -> str | None:
        return identifier(value) if value is not None else None

    @model_validator(mode="after")
    def repair_pair(self) -> WorkflowSpec:
        if (self.repair_on is None) != (self.repair_from is None):
            raise ValueError("workflow repair_on and repair_from must be configured together")
        return self


class WorkflowNodeState(Contract):
    status: Literal["pending", "running", "succeeded", "skipped", "failed"] = "pending"
    attempt: int = Field(default=0, ge=0, strict=True)
    required_capabilities: list[str] = Field(default_factory=list)
    provider_resolution: dict[str, object] | None = None
    model_variant_resolution: dict[str, object] | None = None
    artifact_kinds: list[str] = Field(default_factory=list)
    error: str | None = None


class Profile(Contract):
    schema_version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=200)
    providers: dict[str, ProviderConfig]
    roles: dict[str, RoleConfig]
    policy: Policy = Field(default_factory=Policy)
    validators: dict[str, ValidatorConfig] = Field(default_factory=dict)
    workflow: str = "build-review"
    workflows: dict[str, WorkflowSpec] = Field(default_factory=dict)
    # Exact provider-slot/model pricing. No global vendor price table is embedded
    # in the kernel; source/version/effective-time provenance is mandatory.
    pricing: list[PricingRule] = Field(default_factory=list)

    @model_validator(mode="after")
    def bindings(self) -> Profile:
        for key in [*self.providers, *self.roles, *self.validators, *self.workflows]:
            identifier(key)
        identifier(self.workflow)
        for key, workflow in self.workflows.items():
            if key != workflow.id:
                raise ValueError(f"workflow key/id mismatch: {key} != {workflow.id}")
        for role in ("planner", "implementer", "reviewer"):
            if role not in self.roles:
                raise ValueError(f"missing role: {role}")
        for role in self.roles.values():
            if role.provider is not None and role.provider not in self.providers:
                raise ValueError(f"unknown provider binding: {role.provider}")
            for candidate in role.candidates:
                if candidate not in self.providers:
                    raise ValueError(f"unknown provider candidate: {candidate}")
            if role.provider is None and not role.candidates and not self.providers:
                raise ValueError("dynamic role resolution requires at least one provider")
        price_keys: list[tuple[str, str]] = []
        for rule in self.pricing:
            if rule.provider not in self.providers:
                raise ValueError(f"pricing references unknown provider slot: {rule.provider}")
            price_keys.append((rule.provider, rule.model))
        if len(price_keys) != len(set(price_keys)):
            raise ValueError("pricing must contain at most one rule per exact provider/model")
        for limit in self.policy.budget.call_limits:
            if limit.provider not in self.providers:
                raise ValueError(f"budget call limit references unknown provider slot: {limit.provider}")
        return self


class TaskSpec(Contract):
    schema_version: Literal[1] = 1
    id: str
    goal: str = Field(min_length=1, max_length=20000)
    acceptance: list[str] = Field(min_length=1)
    risk: Literal["T0", "T1", "T2", "T3"] = "T2"
    validators: list[str] = Field(default_factory=list)
    external_effects: StrictBool = False

    @field_validator("id")
    @classmethod
    def valid_id(cls, value: str) -> str:
        return identifier(value)

    @field_validator("acceptance")
    @classmethod
    def nonempty_criteria(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("acceptance criteria must not be blank")
        return value


class AgentResult(Contract):
    outcome: Literal["completed", "approved", "changes_required", "blocked"]
    summary: str = Field(min_length=1, max_length=20000)
    findings: list[str]
    evidence: list[str]


class Artifact(Contract):
    # v2 adds stable controller-owned identity/provenance while v1 metadata
    # remains readable without rewriting historical task rows.
    schema_version: Literal[1, 2] = 1
    id: str | None = None
    owner_id: str | None = None
    created_at: str | None = None
    kind: str
    path: str
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    attempt: int = Field(ge=0)

    @model_validator(mode="after")
    def stable_identity(self) -> "Artifact":
        if self.schema_version >= 2:
            if self.id is None or self.owner_id is None or self.created_at is None:
                raise ValueError("Artifact schema v2 requires id, owner_id and created_at")
            identifier(self.id)
            identifier(self.owner_id)
        return self

    @model_serializer(mode="wrap")
    def preserve_v1_wire_shape(self, handler):
        data = handler(self)
        if self.schema_version == 1:
            # These fields did not exist in Artifact v1. Omitting them is
            # authority-relevant because Artifact metadata participates in
            # Workflow Schema v1 approval scopes.
            data.pop("id", None)
            data.pop("owner_id", None)
            data.pop("created_at", None)
        return data


class ProviderPermissionGrant(Contract):
    permission: Literal["agy_dangerously_skip_permissions"]
    scope: str = Field(pattern=r"^[a-f0-9]{64}$")
    attempt: int = Field(ge=1, strict=True)
    profile_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    execution_scope: str = Field(pattern=r"^[a-f0-9]{64}$")
    workspace_snapshot: str = Field(pattern=r"^[a-f0-9]{64}$")
    nodes: list[str]
    actor: str = Field(min_length=1, max_length=256)

    @field_validator("nodes")
    @classmethod
    def valid_nodes(cls, values: list[str]) -> list[str]:
        normalized = [identifier(value) for value in values]
        if not normalized or len(normalized) != len(set(normalized)):
            raise ValueError("provider permission grant requires unique workflow nodes")
        return normalized


class TaskState(Contract):
    # Existing rows remain readable; v5 adds task-scoped Supervisor-authored workflows,
    # v6 freezes provider-local model/effort/runtime-option provenance, and v7
    # binds usage/budget evidence.
    schema_version: Literal[1, 2, 3, 4, 5, 6, 7] = 1
    intake_id: str | None = None
    require_execution_approval: StrictBool = False
    allowed_paths: list[str] | None = None
    capability_requirements: dict[str, list[str]] | None = None
    task_capability_requirements: dict[str, list[str]] | None = None
    provider_resolutions: dict[str, dict[str, object]] | None = None
    model_variant_resolutions: dict[str, dict[str, object]] | None = None
    runtime_overrides: dict[str, dict[str, object]] | None = None
    workflow_id: str | None = None
    workflow_digest: str | None = None
    workflow_selection_source: Literal["profile_default", "task", "requested", "supervisor", "supervisor_proposed"] | None = None
    workflow_spec: WorkflowSpec | None = None
    workflow_order: list[str] | None = None
    workflow_current: str | None = None
    workflow_nodes: dict[str, WorkflowNodeState] | None = None
    provider_permission_grants: dict[str, ProviderPermissionGrant] = Field(default_factory=dict)
    spec: TaskSpec

    _allowed_paths = field_validator("allowed_paths")(validate_allowed_paths)
    profile_digest: str
    status: Literal["ready", "running", "awaiting_approval", "awaiting_acceptance", "succeeded", "blocked", "failed", "cancelled", "abandoned"] = "ready"
    phase: Literal["plan", "execute", "validate", "review", "accept"] = "plan"
    attempt: int = 0
    calls: int = 0
    elapsed_seconds: float = 0.0
    artifacts: list[Artifact] = Field(default_factory=list)
    feedback: str = ""
    reviewed_snapshot: str | None = None
    error: str | None = None


class Proposal(Contract):
    schema_version: Literal[1] = 1
    id: str
    kind: Literal["knowledge", "policy", "skill"]
    statement: str = Field(min_length=1, max_length=20000)
    evidence: list[str] = Field(min_length=1)
    status: Literal["candidate", "approved", "rejected"] = "candidate"
    approved_by: str | None = None

    @field_validator("id")
    @classmethod
    def valid_id(cls, value: str) -> str:
        return identifier(value)
