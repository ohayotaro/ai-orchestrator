import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from ai_orchestrator.cli import main, parser
from ai_orchestrator.engine import Engine
from ai_orchestrator.models import OrchestratorError, ValidatorConfig
from ai_orchestrator.project import Project
from ai_orchestrator.validators import ValidationFailure, inspect_validator, register_validator, resolve_executable, run_validator
from conftest import FakeAdapter, approve_and_run, spec


def configure(workspace, argv, **options):
    path = workspace / ".orchestrator/config.yaml"
    data = yaml.safe_load(path.read_text())
    data["validators"]["check"] = {"argv": argv, **options}
    path.write_text(yaml.safe_dump(data))
    project = Project(workspace)
    return project, project.load()[0]


def test_missing_validator_blocks_before_model_calls(workspace):
    configure(workspace, ["./missing-venv/bin/python", "-m", "pytest"])
    reasoning, engineering = FakeAdapter("anthropic"), FakeAdapter("openai")
    controller = Engine(workspace, {"claude": reasoning, "codex": engineering})
    try:
        controller.trust("operator")
        controller.create(spec())
        state = controller.run("task-1")
        assert state.status == "blocked"
        assert state.calls == 0
        assert not reasoning.requests and not engineering.requests
        assert str(workspace) in state.error
        assert "validator executable" in state.error
    finally:
        controller.close()


def test_relative_executable_is_project_relative_even_from_other_cwd(workspace, tmp_path, monkeypatch):
    tools = workspace / "tools"
    tools.mkdir()
    script = tools / "check"
    script.write_text("#!/bin/sh\nexit 0\n")
    script.chmod(0o755)
    project, profile = configure(workspace, ["tools/check"])
    monkeypatch.chdir(workspace.parent)
    report = inspect_validator(project, profile, "check")
    assert report["executable"] == str(script)
    result = run_validator(project, profile, "check", timeout=5)
    assert result["exit_code"] == 0


def test_virtualenv_python_symlink_is_not_dereferenced(workspace):
    directory = workspace / ".venv/bin"
    directory.mkdir(parents=True)
    python = directory / "python"
    python.symlink_to(sys.executable)
    assert resolve_executable(".venv/bin/python", Project(workspace)) == str(python)


def test_path_and_absolute_executables(workspace, monkeypatch):
    project = Project(workspace)
    monkeypatch.setenv("PATH", str(Path(sys.executable).parent))
    assert Path(resolve_executable(Path(sys.executable).name, project)).is_absolute()
    assert resolve_executable(sys.executable, project) == os.path.abspath(sys.executable)


def test_doctor_does_not_execute_validator_code(workspace):
    marker = workspace / "should-not-run"
    configure(workspace, [sys.executable, "-c", "from pathlib import Path; Path('should-not-run').touch()"])
    controller = Engine(workspace, {})
    try:
        report = controller.doctor(validators_only=True)["validator:check"]
        assert report["ok"] and report["execution"] == "not checked"
        assert not marker.exists()
    finally:
        controller.close()


def test_doctor_reports_likely_pytest_typo(workspace):
    project, profile = configure(workspace, [sys.executable, "-m", "pytest", "-p", "no:casheprovider"])
    report = inspect_validator(project, profile, "check")
    assert report["ok"]
    assert "no:cacheprovider" in report["warnings"][0]


def test_python_import_does_not_create_bytecode(workspace):
    (workspace / "module_for_check.py").write_text("value = 1\n")
    project, profile = configure(workspace, [sys.executable, "-c", "import module_for_check; assert module_for_check.value == 1"])
    result = run_validator(project, profile, "check", timeout=5)
    assert result["exit_code"] == 0
    assert not (workspace / "__pycache__").exists()


def test_real_pytest_without_cache_leaves_worktree_unchanged(workspace):
    (workspace / "test_one.py").write_text("def test_one():\n    assert 2 * 3 == 6\n")
    project, profile = configure(workspace, [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], env={"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"})
    before = project.snapshot()
    record = run_validator(project, profile, "check", timeout=15)
    assert record["exit_code"] == 0
    assert "1 passed" in record["stdout_tail"]
    assert before == project.snapshot()
    assert not list(workspace.rglob("*.pyc"))


def test_declared_generated_directory_allowed(workspace):
    script = "from pathlib import Path; p=Path('test-output'); p.mkdir(exist_ok=True); (p/'report.txt').write_text('ok')"
    project, profile = configure(workspace, [sys.executable, "-c", script], generated_paths=["test-output"])
    record = run_validator(project, profile, "check", timeout=5)
    assert record["exit_code"] == 0
    assert record["allowed_generated_paths"] == ["test-output/report.txt"]


def test_undeclared_mutation_records_exact_path(workspace):
    project, profile = configure(workspace, [sys.executable, "-c", "from pathlib import Path; Path('input.txt').write_text('wrong')"])
    with pytest.raises(ValidationFailure, match="input.txt") as caught:
        run_validator(project, profile, "check", timeout=5)
    assert caught.value.record["exit_code"] == 0
    assert caught.value.record["changed_paths"] == ["input.txt"]


def test_allowed_directory_cannot_mask_other_source_mutation(workspace):
    script = "from pathlib import Path; Path('test-output').mkdir(); Path('test-output/log').touch(); Path('input.txt').write_text('bad')"
    project, profile = configure(workspace, [sys.executable, "-c", script], generated_paths=["test-output"])
    with pytest.raises(ValidationFailure, match="input.txt"):
        run_validator(project, profile, "check", timeout=5)


def test_generated_directory_cannot_contain_tracked_files(workspace):
    (workspace / "src").mkdir()
    (workspace / "src/module.py").write_text("pass\n")
    subprocess.run(["git", "add", "src/module.py"], cwd=workspace, check=True)
    project, profile = configure(workspace, [sys.executable, "-c", "pass"], generated_paths=["src"])
    with pytest.raises(OrchestratorError, match="Git-tracked"):
        inspect_validator(project, profile, "check")


def test_generated_directory_cannot_overlap_protected_paths(workspace):
    project, profile = configure(workspace, [sys.executable, "-c", "pass"], generated_paths=[".env"])
    with pytest.raises(OrchestratorError, match="protected"):
        inspect_validator(project, profile, "check")


def test_generated_directory_cannot_escape_via_symlink(workspace):
    (workspace / "output").symlink_to(workspace.parent, target_is_directory=True)
    project, profile = configure(workspace, [sys.executable, "-c", "pass"], generated_paths=["output"])
    with pytest.raises(OrchestratorError, match="symlink"):
        inspect_validator(project, profile, "check")


def test_control_file_mutation_is_not_a_generated_artifact(workspace):
    project, profile = configure(workspace, [sys.executable, "-c", "from pathlib import Path; Path('.orchestrator/tasks/unexpected.json').write_text('{}')"])
    with pytest.raises(ValidationFailure, match="control files"):
        run_validator(project, profile, "check", timeout=5)


def test_explicit_environment_works_without_inherited_credentials(workspace, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "should-not-propagate")
    script = "import os; assert os.environ['TEST_MODE']=='strict'; assert 'OPENAI_API_KEY' not in os.environ; assert os.environ['PYTHONDONTWRITEBYTECODE']=='1'"
    project, profile = configure(workspace, [sys.executable, "-c", script], env={"TEST_MODE": "strict"})
    assert run_validator(project, profile, "check", timeout=5)["exit_code"] == 0


def test_validator_check_requires_trust_and_keeps_evidence(workspace):
    controller = Engine(workspace, {})
    try:
        with pytest.raises(OrchestratorError, match="trust"):
            controller.check_validator("check")
        controller.trust("operator")
        report = controller.check_validator("check")
        assert report["ok"]
        assert (workspace / report["artifact"]["path"]).exists()
        assert controller.store.events()[-1]["kind"] == "validator.checked"
    finally:
        controller.close()


def test_timeout_still_has_validator_evidence(workspace):
    project, profile = configure(workspace, [sys.executable, "-c", "import time; time.sleep(5)"])
    with pytest.raises(ValidationFailure, match="timed out") as caught:
        run_validator(project, profile, "check", timeout=0.1)
    assert caught.value.record["duration_seconds"] > 0
    assert caught.value.record["exit_code"] is None


def test_register_validator_and_replace_are_explicit(workspace):
    before = Project(workspace).load()[1]
    result = register_validator(workspace, "new-check", [sys.executable, "-c", "pass"])
    assert result["profile_retrust_required"]
    assert Project(workspace).load()[1] != before
    with pytest.raises(OrchestratorError, match="already exists"):
        register_validator(workspace, "new-check", [sys.executable, "-c", "pass"])
    assert register_validator(workspace, "new-check", [sys.executable, "-c", "print(1)"], replace=True)["ok"]


def test_failed_registration_does_not_change_configuration(workspace):
    path = workspace / ".orchestrator/config.yaml"
    before = path.read_bytes()
    with pytest.raises(OrchestratorError):
        register_validator(workspace, "bad", ["/nonexistent/python"])
    assert path.read_bytes() == before


def test_cli_registration_parses_options_before_separator(workspace, capsys):
    args = ["--project", str(workspace), "validator", "add", "check", "--replace", "--env", "TEST_MODE=strict", "--", sys.executable, "-c", "pass"]
    assert parser().parse_args(args).replace
    assert main(args) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["validator"] == "check"
    assert Project(workspace).load()[0].validators["check"].env == {"TEST_MODE": "strict"}
