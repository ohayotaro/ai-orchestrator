"""Workflow Schema v1 compilation and deterministic DAG semantics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import OrchestratorError, Profile, WorkflowArtifactSpec, WorkflowInputSpec, WorkflowNodeSpec, WorkflowSpec
from .project import digest


def builtin_build_review() -> WorkflowSpec:
    return WorkflowSpec(
        id="build-review",
        nodes=[
            WorkflowNodeSpec(
                id="plan", kind="agent", role="planner", run_for="all",
                outputs=[WorkflowArtifactSpec(name="plan", type="plan")],
            ),
            WorkflowNodeSpec(
                id="implement", kind="agent", role="implementer", run_for="write",
                depends_on=["plan"],
                inputs=[WorkflowInputSpec(artifact="plan", type="plan")],
                outputs=[
                    WorkflowArtifactSpec(name="execute", type="implementation"),
                    WorkflowArtifactSpec(name="write_set", type="write_set"),
                ],
                gate_before="execution", writes="task_allowed_paths",
            ),
            WorkflowNodeSpec(
                id="validate", kind="validator", run_for="write",
                depends_on=["implement"],
                inputs=[
                    WorkflowInputSpec(artifact="execute", type="implementation"),
                    WorkflowInputSpec(artifact="write_set", type="write_set", optional=True),
                ],
                outputs=[WorkflowArtifactSpec(name="validation", type="validation")],
            ),
            WorkflowNodeSpec(
                id="review", kind="agent", role="reviewer", run_for="write",
                depends_on=["validate"],
                independent_of=["implement"],
                inputs=[
                    WorkflowInputSpec(artifact="validation", type="validation"),
                    WorkflowInputSpec(artifact="write_set", type="write_set", optional=True),
                ],
                outputs=[WorkflowArtifactSpec(name="review", type="review")],
            ),
        ],
        repair_on="review",
        repair_from="implement",
    )


def builtin_branched_review() -> WorkflowSpec:
    """Two complementary read-only analyses converge on one gated implementation."""
    return WorkflowSpec(
        id="branched-review",
        nodes=[
            WorkflowNodeSpec(
                id="analyze_a", kind="agent", role="planner", run_for="all",
                instructions="Analyze the implementation approach, repository impact and constraints.",
                outputs=[WorkflowArtifactSpec(name="analysis_a", type="plan")],
            ),
            WorkflowNodeSpec(
                id="analyze_b", kind="agent", role="planner", run_for="all",
                instructions="Independently analyze edge cases, validation strategy and regression risks.",
                outputs=[WorkflowArtifactSpec(name="analysis_b", type="plan")],
            ),
            WorkflowNodeSpec(
                id="implement", kind="agent", role="implementer", run_for="write",
                depends_on=["analyze_a", "analyze_b"],
                inputs=[
                    WorkflowInputSpec(artifact="analysis_a", type="plan"),
                    WorkflowInputSpec(artifact="analysis_b", type="plan"),
                ],
                outputs=[
                    WorkflowArtifactSpec(name="execute", type="implementation"),
                    WorkflowArtifactSpec(name="write_set", type="write_set"),
                ],
                gate_before="execution", writes="task_allowed_paths",
            ),
            WorkflowNodeSpec(
                id="validate", kind="validator", run_for="write",
                depends_on=["implement"],
                inputs=[
                    WorkflowInputSpec(artifact="execute", type="implementation"),
                    WorkflowInputSpec(artifact="write_set", type="write_set", optional=True),
                ],
                outputs=[WorkflowArtifactSpec(name="validation", type="validation")],
            ),
            WorkflowNodeSpec(
                id="review", kind="agent", role="reviewer", run_for="write",
                depends_on=["validate"], independent_of=["implement"],
                inputs=[
                    WorkflowInputSpec(artifact="validation", type="validation"),
                    WorkflowInputSpec(artifact="write_set", type="write_set", optional=True),
                ],
                outputs=[WorkflowArtifactSpec(name="review", type="review")],
            ),
        ],
        repair_on="review",
        repair_from="implement",
    )


@dataclass(frozen=True)
class CompiledWorkflow:
    spec: WorkflowSpec
    order: tuple[str, ...]
    digest: str
    nodes: dict[str, WorkflowNodeSpec]
    artifact_producers: dict[str, str]
    artifact_types: dict[str, str]
    descendants: dict[str, frozenset[str]]
    ancestors: dict[str, frozenset[str]]

    def active_ids(self, *, advisory: bool) -> tuple[str, ...]:
        mode = "advisory" if advisory else "write"
        return tuple(node_id for node_id in self.order if self.nodes[node_id].run_for in ("all", mode))

    def report(self) -> dict[str, Any]:
        return {
            "schema_version": self.spec.schema_version,
            "id": self.spec.id,
            "digest": self.digest,
            "order": list(self.order),
            "repair_on": self.spec.repair_on,
            "repair_from": self.spec.repair_from,
            "nodes": [self.nodes[node_id].model_dump() for node_id in self.order],
            "artifacts": {name: {"producer": self.artifact_producers[name], "type": self.artifact_types[name]}
                          for name in sorted(self.artifact_producers)},
        }


def _topological_order(nodes: list[WorkflowNodeSpec]) -> list[str]:
    positions = {node.id: index for index, node in enumerate(nodes)}
    ids = set(positions)
    indegree = {node.id: 0 for node in nodes}
    outgoing: dict[str, list[str]] = {node.id: [] for node in nodes}
    for node in nodes:
        for dependency in node.depends_on:
            if dependency not in ids:
                raise OrchestratorError(f"workflow node {node.id}: unknown dependency {dependency}")
            if dependency == node.id:
                raise OrchestratorError(f"workflow node {node.id}: self-dependency is not allowed")
            indegree[node.id] += 1
            outgoing[dependency].append(node.id)
        for other in node.independent_of:
            if other not in ids:
                raise OrchestratorError(f"workflow node {node.id}: unknown independent_of node {other}")
    ready = sorted((node_id for node_id, count in indegree.items() if count == 0), key=positions.get)
    order: list[str] = []
    while ready:
        node_id = ready.pop(0)
        order.append(node_id)
        for child in sorted(outgoing[node_id], key=positions.get):
            indegree[child] -= 1
            if indegree[child] == 0:
                ready.append(child)
                ready.sort(key=positions.get)
    if len(order) != len(nodes):
        raise OrchestratorError("workflow contains a dependency cycle")
    return order


def _closure(order: list[str], nodes: dict[str, WorkflowNodeSpec]) -> tuple[dict[str, frozenset[str]], dict[str, frozenset[str]]]:
    ancestors: dict[str, set[str]] = {node_id: set() for node_id in order}
    for node_id in order:
        for dependency in nodes[node_id].depends_on:
            ancestors[node_id].add(dependency)
            ancestors[node_id].update(ancestors[dependency])
    descendants: dict[str, set[str]] = {node_id: set() for node_id in order}
    for node_id in reversed(order):
        for child in order:
            if node_id in nodes[child].depends_on:
                descendants[node_id].add(child)
                descendants[node_id].update(descendants[child])
    return ({key: frozenset(value) for key, value in descendants.items()},
            {key: frozenset(value) for key, value in ancestors.items()})


def _validate_mode(spec: WorkflowSpec, order: list[str], nodes: dict[str, WorkflowNodeSpec], *, advisory: bool, cross_provider_review: bool) -> None:
    mode = "advisory" if advisory else "write"
    active = {node_id for node_id in order if nodes[node_id].run_for in ("all", mode)}
    if not active:
        raise OrchestratorError(f"workflow {spec.id}: no active nodes for {mode} tasks")
    for node_id in active:
        node = nodes[node_id]
        missing = [dep for dep in node.depends_on if dep not in active]
        if missing:
            raise OrchestratorError(f"workflow node {node_id}: active node depends on skipped node(s): {', '.join(missing)}")
    if advisory:
        for node_id in active:
            node = nodes[node_id]
            if node.kind != "agent" or node.writes != "none" or node.gate_before is not None:
                raise OrchestratorError(f"workflow {spec.id}: advisory path must contain read-only agent nodes only")
        return
    writable = [node_id for node_id in active if nodes[node_id].writes == "task_allowed_paths"]
    validators = [node_id for node_id in active if nodes[node_id].kind == "validator"]
    reviewers = [node_id for node_id in active if nodes[node_id].kind == "agent" and nodes[node_id].role == "reviewer"]
    if not writable or not validators or not reviewers:
        raise OrchestratorError(f"workflow {spec.id}: write path requires writable agent, validator and reviewer nodes")
    if cross_provider_review:
        for reviewer in reviewers:
            missing = [node_id for node_id in writable if node_id not in nodes[reviewer].independent_of]
            if missing:
                raise OrchestratorError(f"workflow reviewer {reviewer}: cross-provider policy requires independent_of {', '.join(missing)}")


def compile_workflow(spec: WorkflowSpec, *, cross_provider_review: bool) -> CompiledWorkflow:
    ids = [node.id for node in spec.nodes]
    if len(ids) != len(set(ids)):
        raise OrchestratorError(f"workflow {spec.id}: duplicate node IDs")
    nodes = {node.id: node for node in spec.nodes}
    order = _topological_order(spec.nodes)
    descendants, ancestors = _closure(order, nodes)

    artifact_producers: dict[str, str] = {}
    artifact_types: dict[str, str] = {}
    for node_id in order:
        node = nodes[node_id]
        expected = {
            ("agent", "planner"): {"plan"},
            ("agent", "implementer"): {"implementation", "write_set"} if node.writes == "task_allowed_paths" else {"implementation"},
            ("agent", "reviewer"): {"review"},
            ("validator", None): {"validation"},
        }[(node.kind, node.role)]
        actual = {output.type for output in node.outputs}
        if actual != expected:
            raise OrchestratorError(f"workflow node {node_id}: output types {sorted(actual)} must equal {sorted(expected)}")
        for output in node.outputs:
            if output.name in artifact_producers:
                raise OrchestratorError(f"workflow {spec.id}: duplicate artifact output {output.name}")
            artifact_producers[output.name] = node_id
            artifact_types[output.name] = output.type

    for node_id in order:
        node = nodes[node_id]
        for input_spec in node.inputs:
            producer = artifact_producers.get(input_spec.artifact)
            if producer is None:
                if input_spec.optional:
                    continue
                raise OrchestratorError(f"workflow node {node_id}: unknown input artifact {input_spec.artifact}")
            if artifact_types[input_spec.artifact] != input_spec.type:
                raise OrchestratorError(f"workflow node {node_id}: artifact type mismatch for {input_spec.artifact}")
            if producer not in ancestors[node_id]:
                raise OrchestratorError(f"workflow node {node_id}: input {input_spec.artifact} is not produced by a dependency ancestor")
        for independent in node.independent_of:
            if independent not in ancestors[node_id]:
                raise OrchestratorError(f"workflow node {node_id}: independent_of node {independent} must be an ancestor")

    if spec.repair_on is not None:
        if spec.repair_on not in nodes or spec.repair_from not in nodes:
            raise OrchestratorError(f"workflow {spec.id}: repair nodes must exist")
        if nodes[spec.repair_on].role != "reviewer":
            raise OrchestratorError(f"workflow {spec.id}: repair_on must be a reviewer node")
        if nodes[spec.repair_from].writes != "task_allowed_paths":
            raise OrchestratorError(f"workflow {spec.id}: repair_from must be a writable node")
        if spec.repair_from not in ancestors[spec.repair_on]:
            raise OrchestratorError(f"workflow {spec.id}: repair_from must be an ancestor of repair_on")

    _validate_mode(spec, order, nodes, advisory=True, cross_provider_review=cross_provider_review)
    _validate_mode(spec, order, nodes, advisory=False, cross_provider_review=cross_provider_review)
    return CompiledWorkflow(
        spec=spec, order=tuple(order), digest=digest(spec.model_dump()), nodes=nodes,
        artifact_producers=artifact_producers, artifact_types=artifact_types,
        descendants=descendants, ancestors=ancestors,
    )


def workflow_registry(profile: Profile) -> dict[str, CompiledWorkflow]:
    """Compile every workflow authority already trusted by the project/package."""
    if "build-review" in profile.workflows:
        raise OrchestratorError("custom workflows cannot override built-in build-review")
    specs: dict[str, WorkflowSpec] = {
        "build-review": builtin_build_review(),
        "branched-review": builtin_branched_review(),
    }
    # Project workflows are trusted profile authority. A project may retain a
    # pre-v0.6.2 branched-review definition; it intentionally shadows the
    # package template without requiring a migration.
    specs.update(profile.workflows)
    compiled = {
        name: compile_workflow(spec, cross_provider_review=profile.policy.cross_provider_review)
        for name, spec in specs.items()
    }
    if profile.workflow not in compiled:
        raise OrchestratorError(f"unknown default workflow: {profile.workflow}")
    return compiled


def workflow_registry_report(profile: Profile, registry: dict[str, CompiledWorkflow] | None = None) -> dict[str, Any]:
    registry = registry or workflow_registry(profile)
    return {
        "schema_version": 1,
        "default": profile.workflow,
        "workflows": {
            name: {
                "id": name,
                "source": "project" if name in profile.workflows else "builtin",
                "digest": compiled.digest,
                "order": list(compiled.order),
                "repair_on": compiled.spec.repair_on,
                "repair_from": compiled.spec.repair_from,
            }
            for name, compiled in sorted(registry.items())
        },
    }


def workflow_for_profile(profile: Profile, workflow_ref: str | None = None) -> CompiledWorkflow:
    registry = workflow_registry(profile)
    selected = workflow_ref or profile.workflow
    compiled = registry.get(selected)
    if compiled is None:
        raise OrchestratorError(
            f"unknown trusted workflow: {selected}; select one from the workflow registry"
        )
    return compiled
