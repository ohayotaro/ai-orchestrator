"""Role-specific v0.2 outputs. Every model-facing property is required."""

from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field, StrictBool, field_validator, model_validator

from .models import AgentResult, Artifact, Contract, TaskSpec, allowed_paths, identifier


class PlanResult(Contract):
    outcome: Literal["completed", "blocked"]
    summary: str = Field(min_length=1, max_length=20000)
    steps: list[str]
    uncertainties: list[str]
    evidence: list[str]


class ImplementationResult(Contract):
    outcome: Literal["completed", "blocked"]
    summary: str = Field(min_length=1, max_length=20000)
    changes: list[str]
    uncertainties: list[str]
    evidence: list[str]


class ReviewResult(Contract):
    outcome: Literal["approved", "changes_required", "blocked"]
    summary: str = Field(min_length=1, max_length=20000)
    blocking_findings: list[str] = Field(description="Defects that prevent acceptance. Empty when none exist.")
    observations: list[str] = Field(description="Non-blocking notes and confirmations; never a repair trigger.")
    evidence: list[str]


class TaskDraft(Contract):
    """No IDs, executable commands, approvals, tool grants, or policy mutations."""

    goal: str = Field(min_length=1, max_length=20000)
    acceptance: list[str] = Field(min_length=1)
    risk: Literal["T0", "T1", "T2", "T3"]
    validators: list[str] = Field(description="Names from the controller-supplied validator registry only.")
    external_effects: StrictBool

    @field_validator("acceptance")
    @classmethod
    def nonblank(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("acceptance criteria must not be blank")
        return values


class TaskDraftScoped(TaskDraft):
    """Current model-facing task draft; legacy persisted TaskDraft stays readable."""

    allowed_paths: list[str] = Field(description="Exact project-relative files this task may create or modify. Empty only for advisory work.")
    _allowed_paths = field_validator("allowed_paths")(allowed_paths)


class SupervisorResultScoped(Contract):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, title="SupervisorResult")

    outcome: Literal["proposed", "needs_clarification", "blocked"]
    summary: str = Field(min_length=1, max_length=20000)
    task: TaskDraftScoped | None
    questions: list[str]

    @model_validator(mode="after")
    def coherent(self) -> SupervisorResultScoped:
        if self.outcome == "proposed" and (self.task is None or self.questions):
            raise ValueError("proposed requires a task and no unanswered questions")
        if self.outcome != "proposed" and self.task is not None:
            raise ValueError("blocked/needs_clarification must not supply an executable task")
        if self.outcome == "needs_clarification" and not any(q.strip() for q in self.questions):
            raise ValueError("needs_clarification requires a concrete question")
        return self


class SupervisorResult(Contract):
    outcome: Literal["proposed", "needs_clarification", "blocked"]
    summary: str = Field(min_length=1, max_length=20000)
    task: TaskDraft | None
    questions: list[str]

    @model_validator(mode="after")
    def coherent(self) -> SupervisorResult:
        if self.outcome == "proposed" and (self.task is None or self.questions):
            raise ValueError("proposed requires a task and no unanswered questions")
        if self.outcome != "proposed" and self.task is not None:
            raise ValueError("blocked/needs_clarification must not supply an executable task")
        if self.outcome == "needs_clarification" and not any(q.strip() for q in self.questions):
            raise ValueError("needs_clarification requires a concrete question")
        return self


class IntakeState(Contract):
    schema_version: Literal[1] = 1
    id: str
    task_id: str
    profile_digest: str
    workspace_snapshot: str
    request: str = Field(min_length=1, max_length=20000)
    advisory: StrictBool = False
    reply_to: str | None = None
    round: int = Field(default=1, ge=1, le=3, strict=True)
    status: Literal["running", "proposed", "needs_clarification", "blocked", "failed", "cancelled", "consumed"] = "running"
    result: SupervisorResult | None = None
    task: TaskSpec | None = None
    allowed_paths: list[str] | None = None
    artifact: Artifact | None = None

    _allowed_paths = field_validator("allowed_paths")(allowed_paths)
    # Cumulative across clarification rounds; carried into the created task budget.
    calls: int = Field(default=0, ge=0, strict=True)
    elapsed_seconds: float = Field(default=0.0, ge=0)
    notes: list[str] = Field(default_factory=list)
    error: str | None = None

    @field_validator("id", "task_id")
    @classmethod
    def valid_id(cls, value: str) -> str:
        return identifier(value)


def result_contract(phase: str, version: int = 2) -> type[Contract]:
    if version == 1:
        return AgentResult
    return {"plan": PlanResult, "execute": ImplementationResult, "review": ReviewResult, "supervise": SupervisorResult}[phase]
