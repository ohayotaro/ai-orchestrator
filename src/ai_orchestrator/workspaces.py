"""Isolated Git-worktree lifecycle and deterministic v0.7 integration."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .models import OrchestratorError, Profile, identifier
from .project import Project, confined
from .validators import changed_paths


def _git(cwd: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        result = subprocess.run(
            ["git", *arguments], cwd=cwd, env=env, capture_output=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise OrchestratorError("Git is unavailable or timed out during isolated workspace operation") from exc
    if check and result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise OrchestratorError("isolated workspace Git operation failed" + (f": {detail[:1000]}" if detail else ""))
    return result


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


class WorkspaceManager:
    """Own temporary worktrees for one task attempt.

    Provider workers never share a writable worktree. Integration is prepared
    off to the side and the user's worktree is touched only by one aggregate
    patch after every isolated branch has passed ownership checks.
    """

    def __init__(self, project: Project, profile: Profile, task_id: str, attempt: int):
        identifier(task_id)
        self.project = project
        self.profile = profile
        self.task_id = task_id
        self.attempt = attempt
        self.task_dir = confined(
            project.root, f".orchestrator/runtime/worktrees/{task_id}/attempt-{attempt}"
        )
        self.integration = self.task_dir / "integration"
        self.patch_dir = self.task_dir / "patches"
        self.seed_sha: str | None = None
        self.seed_snapshot: str | None = None
        self.seed_manifest: dict[str, tuple[str, int]] | None = None
        self.node_paths: dict[str, Path] = {}

    def _assert_head(self) -> str:
        result = _git(self.project.root, "rev-parse", "--verify", "HEAD", check=False)
        if result.returncode:
            raise OrchestratorError(
                "isolated parallel execution requires at least one Git commit; "
                "commit the repository baseline before using isolated workflow nodes"
            )
        return result.stdout.decode().strip()

    def _sync_root_state(self, destination: Path) -> None:
        manifest = self.project.manifest()
        # Start from an empty worktree payload (keeping only Git's administrative
        # file). This avoids following stale/symlinked parents from HEAD while
        # materializing a dirty root snapshot and deliberately withholds ignored
        # and .orchestrator content from provider workers.
        for child in destination.iterdir():
            if child.name != ".git":
                _remove_path(child)
        for relative, (value, mode) in manifest.items():
            if value == "deleted":
                continue
            source = self.project.root / relative
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if value.startswith("link:"):
                target.symlink_to(os.readlink(source))
            else:
                shutil.copy2(source, target, follow_symlinks=False)
                current = target.stat().st_mode
                target.chmod((current & ~0o111) | mode)

    def prepare(self, node_ids: list[str]) -> dict[str, Path]:
        if self.task_dir.exists():
            raise OrchestratorError(
                "stale isolated workspaces exist for this task attempt; "
                "use recover after inspection instead of replaying interrupted effects"
            )
        self._assert_head()
        self.task_dir.mkdir(parents=True, exist_ok=False)
        self.patch_dir.mkdir()
        try:
            _git(self.project.root, "worktree", "add", "--detach", str(self.integration), "HEAD")
            self._sync_root_state(self.integration)
            integration_project = Project(self.integration)
            _git(self.integration, "add", "-A")
            _git(
                self.integration,
                "-c", "user.name=AI Orchestrator",
                "-c", "user.email=orchestrator@localhost",
                "-c", "commit.gpgsign=false",
                "-c", "core.hooksPath=/dev/null",
                "commit", "--allow-empty", "-m",
                f"ai-orchestrator isolated seed {self.task_id} attempt {self.attempt}",
            )
            self.seed_sha = _git(self.integration, "rev-parse", "HEAD").stdout.decode().strip()
            self.seed_snapshot = integration_project.snapshot()
            self.seed_manifest = integration_project.manifest()
            if self.seed_snapshot != self.project.snapshot():
                raise OrchestratorError("isolated seed does not match the approved project snapshot")

            for node_id in node_ids:
                identifier(node_id)
                path = self.task_dir / f"node-{node_id}"
                _git(self.project.root, "worktree", "add", "--detach", str(path), self.seed_sha)
                node_project = Project(path)
                if node_project.snapshot() != self.seed_snapshot:
                    raise OrchestratorError(f"workflow node {node_id}: isolated workspace seed mismatch")
                self.node_paths[node_id] = path
            return dict(self.node_paths)
        except Exception:
            self.cleanup()
            raise

    def finalize_node(self, node_id: str, owned_paths: list[str]) -> dict[str, Any]:
        if self.seed_sha is None or self.seed_snapshot is None or self.seed_manifest is None:
            raise OrchestratorError("isolated workspace manager was not prepared")
        path = self.node_paths[node_id]
        node_project = Project(path)
        after_manifest = node_project.manifest()
        changed = changed_paths(self.seed_manifest, after_manifest)
        violations = [item for item in changed if item not in set(owned_paths)]
        if violations:
            raise OrchestratorError(
                f"workflow node {node_id}: isolated worker changed paths outside write_paths: "
                + ", ".join(violations[:20])
            )
        _git(path, "add", "-A", "--", *owned_paths)
        patch = _git(path, "diff", "--cached", "--binary", self.seed_sha, "--", *owned_paths).stdout
        patch_path = self.patch_dir / f"{node_id}.patch"
        patch_path.write_bytes(patch)
        return {
            "node": node_id,
            "workspace": "isolated",
            "owned_paths": list(owned_paths),
            "changed_paths": changed,
            "violations": violations,
            "seed_snapshot": self.seed_snapshot,
            "isolated_snapshot": node_project.snapshot(),
            "patch_sha256": hashlib.sha256(patch).hexdigest(),
            "patch_path": patch_path,
        }

    def integrate(self, patches: list[dict[str, Any]]) -> dict[str, Any]:
        if self.seed_sha is None or self.seed_snapshot is None:
            raise OrchestratorError("isolated workspace manager was not prepared")
        integration_project = Project(self.integration)
        for record in patches:
            patch_path = Path(record["patch_path"])
            if not patch_path.read_bytes():
                continue
            checked = _git(self.integration, "apply", "--check", "--index", "--binary", str(patch_path), check=False)
            if checked.returncode:
                detail = checked.stderr.decode("utf-8", "replace").strip()
                raise OrchestratorError(
                    f"isolated integration conflict at node {record['node']}"
                    + (f": {detail[:1000]}" if detail else "")
                )
            _git(self.integration, "apply", "--index", "--binary", str(patch_path))
        integrated_snapshot = integration_project.snapshot()
        aggregate = _git(self.integration, "diff", "--cached", "--binary", self.seed_sha).stdout
        aggregate_path = self.patch_dir / "integrated.patch"
        aggregate_path.write_bytes(aggregate)
        return {
            "seed_snapshot": self.seed_snapshot,
            "integrated_snapshot": integrated_snapshot,
            "aggregate_patch": aggregate_path,
            "aggregate_patch_sha256": hashlib.sha256(aggregate).hexdigest(),
            "nodes": [record["node"] for record in patches],
        }

    def apply_integrated(self, integration: dict[str, Any]) -> str:
        if self.seed_snapshot is None:
            raise OrchestratorError("isolated workspace manager was not prepared")
        if self.project.snapshot() != self.seed_snapshot:
            raise OrchestratorError(
                "project worktree changed while isolated workers were running; "
                "integration was not applied"
            )
        patch = Path(integration["aggregate_patch"])
        if patch.read_bytes():
            checked = _git(self.project.root, "apply", "--check", "--binary", str(patch), check=False)
            if checked.returncode:
                detail = checked.stderr.decode("utf-8", "replace").strip()
                raise OrchestratorError(
                    "integrated patch no longer applies to the project worktree"
                    + (f": {detail[:1000]}" if detail else "")
                )
            _git(self.project.root, "apply", "--binary", str(patch))
        actual = self.project.snapshot()
        if actual != integration["integrated_snapshot"]:
            raise OrchestratorError(
                "post-integration snapshot mismatch; inspect the worktree manually before continuing"
            )
        return actual

    def cleanup(self) -> list[str]:
        removed: list[str] = []
        prefix = self.task_dir.resolve()
        listed = _git(self.project.root, "worktree", "list", "--porcelain", check=False)
        if listed.returncode == 0:
            paths: list[Path] = []
            for raw in listed.stdout.decode("utf-8", "replace").splitlines():
                if not raw.startswith("worktree "):
                    continue
                path = Path(raw[len("worktree "):]).resolve()
                if path != self.project.root and path.is_relative_to(prefix):
                    paths.append(path)
            for path in sorted(paths, key=lambda item: len(item.parts), reverse=True):
                _git(self.project.root, "worktree", "remove", "--force", str(path), check=False)
                removed.append(str(path))
        _git(self.project.root, "worktree", "prune", check=False)
        if self.task_dir.exists():
            shutil.rmtree(self.task_dir, ignore_errors=True)
        # Keep the runtime tree free of misleading empty task directories.
        task_root = self.task_dir.parent
        try:
            task_root.rmdir()
        except OSError:
            pass
        return removed

    @classmethod
    def cleanup_task(cls, project: Project, task_id: str) -> list[str]:
        identifier(task_id)
        base = confined(project.root, f".orchestrator/runtime/worktrees/{task_id}")
        removed: list[str] = []
        listed = _git(project.root, "worktree", "list", "--porcelain", check=False)
        if listed.returncode == 0:
            for raw in listed.stdout.decode("utf-8", "replace").splitlines():
                if not raw.startswith("worktree "):
                    continue
                path = Path(raw[len("worktree "):]).resolve()
                if path != project.root and path.is_relative_to(base.resolve()):
                    _git(project.root, "worktree", "remove", "--force", str(path), check=False)
                    removed.append(str(path))
        _git(project.root, "worktree", "prune", check=False)
        if base.exists():
            shutil.rmtree(base, ignore_errors=True)
        return removed
