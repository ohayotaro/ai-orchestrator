"""Validator configuration, non-executing preflight, and guarded execution."""

from __future__ import annotations

import difflib
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

import yaml

from .models import OrchestratorError, Profile, ValidatorConfig, identifier
from .process import redact, run_process, validator_environment
from .project import Project, atomic_write, confined, load_yaml


def within(path: str, directory: str) -> bool:
    return path == directory or path.startswith(directory + "/")


def changed_paths(before: dict, after: dict) -> list[str]:
    return sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))


def resolve_executable(argv0: str, project: Project) -> str:
    """Keep virtualenv symlinks intact: resolving them can bypass the venv."""
    if "/" in argv0:
        path = Path(argv0)
        if not path.is_absolute():
            path = project.root / path
        executable = os.path.abspath(path)
    else:
        path_value = os.environ.get("PATH", os.defpath)
        # Relative PATH entries have the same project-root meaning as child cwd.
        path_value = os.pathsep.join(os.path.abspath(project.root / entry) if not os.path.isabs(entry) else entry for entry in path_value.split(os.pathsep))
        executable = shutil.which(argv0, path=path_value) or ""
    if not executable or not Path(executable).is_file() or not os.access(executable, os.X_OK):
        raise OrchestratorError(f"validator executable not found or not executable: {argv0!r}; checked {executable or 'PATH'} (project={project.root})")
    return os.path.abspath(executable)


def generated_roots(project: Project, profile: Profile, config: ValidatorConfig) -> list[str]:
    tracked = [os.fsdecode(value) for value in project.git("ls-files", "-z", "--cached").split(b"\0") if value]
    for directory in config.generated_paths:
        path = confined(project.root, directory)
        if path.exists() and not path.is_dir():
            raise OrchestratorError(f"generated path must be a directory: {directory}")
        if any(within(name, directory) or within(directory, name) for name in tracked):
            raise OrchestratorError(f"generated path overlaps a Git-tracked path: {directory}")
        if any(within(name, directory) or within(directory, name) for name in profile.policy.protected_paths):
            raise OrchestratorError(f"generated path overlaps a protected path: {directory}")
        if path.exists():
            for count, entry in enumerate(path.rglob("*"), start=1):
                if count > 20000:
                    raise OrchestratorError(f"generated directory exceeds the 20,000-entry limit: {directory}")
                confined(project.root, entry.relative_to(project.root).as_posix())
    return config.generated_paths


def inspect_validator(project: Project, profile: Profile, name: str) -> dict[str, Any]:
    if name not in profile.validators:
        raise OrchestratorError(f"unknown validator: {name}")
    config = profile.validators[name]
    executable = resolve_executable(config.argv[0], project)
    generated_roots(project, profile, config)
    warnings = []
    for argument in config.argv:
        if argument.startswith("no:"):
            plugin = argument[3:]
            if plugin != "cacheprovider" and difflib.SequenceMatcher(None, plugin, "cacheprovider").ratio() >= 0.8:
                warnings.append(f"possible pytest plugin typo: {argument!r}; the cache plugin is disabled with 'no:cacheprovider'")
    return {"ok": True, "executable": executable, "argv": [executable, *config.argv[1:]], "generated_paths": config.generated_paths, "warnings": warnings, "execution": "not checked"}


class ValidationFailure(OrchestratorError):
    def __init__(self, message: str, record: dict[str, Any]):
        super().__init__(message)
        self.record = record


def run_validator(project: Project, profile: Profile, name: str, *, timeout: float, cancel: Callable[[], bool] = lambda: False) -> dict[str, Any]:
    from .safety import assert_ready
    assert_ready(project)
    if cancel():
        raise OrchestratorError("validator cancelled before dispatch")
    report = inspect_validator(project, profile, name)
    config = profile.validators[name]
    before = project.manifest()
    protected = project.protected_snapshot(profile)
    controls = project.control_snapshot()
    record: dict[str, Any] = {"name": name, "argv": [redact(arg) for arg in report["argv"]], "exit_code": None, "duration_seconds": 0.0, "stdout_tail": "", "stderr_tail": "", "warnings": report["warnings"], "changed_paths": [], "allowed_generated_paths": [], "error": None}
    start = time.monotonic()
    error = None
    try:
        with tempfile.TemporaryDirectory(prefix="orchestrator-validator-") as home:
            env = validator_environment(home)
            env.update(config.env)
            result = run_process(report["argv"], cwd=project.root, env=env, timeout=min(timeout, config.timeout_seconds), cancel=cancel)
        record.update(exit_code=result.returncode, stdout_tail=redact(result.stdout[-4000:]), stderr_tail=redact(result.stderr[-4000:]))
    except (OrchestratorError, OSError) as exc:
        error = str(exc)
    finally:
        record["duration_seconds"] = time.monotonic() - start
    try:
        after = project.manifest()
        changed = changed_paths(before, after)
        roots = generated_roots(project, profile, config)
        allowed = [path for path in changed if any(within(path, directory) for directory in roots)]
        forbidden = sorted(set(changed) - set(allowed))
        record.update(changed_paths=changed[:100], changed_path_count=len(changed), allowed_generated_paths=allowed[:100])
        if project.control_snapshot() != controls:
            error = "validator modified orchestration control files; inspect manually"
        elif project.protected_snapshot(profile) != protected:
            error = "validator modified protected files; inspect manually"
        elif forbidden:
            error = "validator modified project files: " + ", ".join(forbidden[:20]) + "; inspect manually"
    except (OrchestratorError, OSError) as exc:
        error = "validator integrity check failed: " + str(exc)
    if error:
        record["error"] = redact(error)
        raise ValidationFailure(record["error"], record)
    return record


def register_validator(root: Path, name: str, argv: list[str], *, timeout: int = 120, env: dict[str, str] | None = None, generated_paths: list[str] | None = None, replace: bool = False) -> dict[str, Any]:
    identifier(name)
    project = Project(root)
    with project.lock(_wait=True):
        project.load()
        path = confined(project.root, ".orchestrator/config.yaml")
        data = load_yaml(path)
        if name in data.get("validators", {}) and not replace:
            raise OrchestratorError(f"validator already exists: {name}; inspect it and use --replace explicitly")
        config = ValidatorConfig(argv=argv, timeout_seconds=timeout, env=env or {}, generated_paths=generated_paths or [])
        data.setdefault("validators", {})[name] = config.model_dump()
        profile = Profile.model_validate(data)
        report = inspect_validator(project, profile, name)
        atomic_write(path, yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
        return {"validator": name, **report, "profile_retrust_required": True}
