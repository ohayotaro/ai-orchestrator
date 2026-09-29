"""Regression coverage for worktree integrity snapshots."""

import subprocess

from ai_orchestrator.project import Project


def _git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def test_snapshot_ignores_orchestrator_state_and_macos_metadata(tmp_path):
    _git(tmp_path, "init")
    (tmp_path / "source.txt").write_text("stable")
    (tmp_path / ".DS_Store").write_bytes(b"finder-a")
    _git(tmp_path, "add", "source.txt", ".DS_Store")
    baseline = Project(tmp_path).snapshot()

    control = tmp_path / ".orchestrator" / "tasks"
    control.mkdir(parents=True)
    (control / "task.json").write_text("{}")
    (tmp_path / ".DS_Store").write_bytes(b"finder-b")

    assert Project(tmp_path).snapshot() == baseline


def test_snapshot_still_detects_project_mutation(tmp_path):
    _git(tmp_path, "init")
    path = tmp_path / "source.txt"
    path.write_text("before")
    _git(tmp_path, "add", "source.txt")
    project = Project(tmp_path)
    baseline = project.snapshot()
    path.write_text("after")
    assert project.snapshot() != baseline
