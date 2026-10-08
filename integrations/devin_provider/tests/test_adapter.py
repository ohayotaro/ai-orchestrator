"""Offline fixtures only. No real devin CLI, network, or provider invocation."""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import time
import tomllib

import pytest

PLUGIN = pathlib.Path(__file__).resolve().parents[1]
CORE = PLUGIN.parents[1]
sys.path.insert(0, str(PLUGIN / "src"))
sys.path.insert(0, str(CORE / "src"))

from ai_orchestrator.models import Contract, ProviderConfig, OrchestratorError
from ai_orchestrator.provider_sdk import RunRequest, ProviderExecutionError, assert_provider_adapter_conforms
from ai_orchestrator.runtime_options import RuntimeOptionsDescriptor
from ai_orchestrator_provider_devin.adapter import Adapter, ProtocolHarness, _run_bounded, _Result


class Result(Contract):
    value: int


def request(tmp_path, *, phase="execute", model=None, effort=None, permission=frozenset(), cancel=lambda:False):
    return RunRequest(
        phase=phase, prompt="Fixture prompt: do not reveal", workspace=tmp_path,
        config=ProviderConfig(adapter="devin", model=model, effort=effort),
        timeout=3, cancel=cancel, result_model=Result, provider_permissions=permission,
    )


def fake_cli(tmp_path, body: str):
    path=tmp_path/"fake-devin"
    path.write_text(f"#!{sys.executable}\n"+body)
    path.chmod(0o755)
    return str(path)


def test_metadata_is_conformant_but_never_claims_support(tmp_path):
    adapter=Adapter()
    report=assert_provider_adapter_conforms("devin",adapter)
    assert report["provider_sdk_version"]==1 and report["adapter_api_version"]==2
    assert report["runtime_capabilities"]==[] and report["semantic_capabilities"]==[]
    desc=adapter.describe_runtime_options(ProviderConfig(adapter="devin"),tmp_path)
    assert isinstance(desc,RuntimeOptionsDescriptor)
    assert desc.model.mode=="passthrough" and desc.effort.mode=="unsupported"
    assert adapter.describe_usage(ProviderConfig(adapter="devin"),tmp_path).provider_cost=="unsupported"
    for role in ("implementer","planner","reviewer","supervisor"):
        assert adapter.role_compatibility(role)["status"]=="unverified"


def test_entrypoint_metadata_is_separate_distribution():
    data=tomllib.loads((PLUGIN/"pyproject.toml").read_text())
    assert data["project"]["name"]=="ai-orchestrator-provider-devin"
    assert data["project"]["version"]=="0.1.0"
    assert data["project"]["entry-points"]["ai_orchestrator.providers"]["devin"]=="ai_orchestrator_provider_devin:Adapter"


def test_execute_refuses_before_any_provider_call(tmp_path,monkeypatch):
    def bomb(*args,**kwargs):
        pytest.fail("a real process must not be launched")
    monkeypatch.setattr(subprocess,"Popen",bomb)
    with pytest.raises(ProviderExecutionError) as raised:
        Adapter().execute(request(tmp_path))
    assert raised.value.diagnostics=={"failure_category":"configuration","stage":"unqualified"}
    assert "Fixture prompt" not in str(raised.value)


def test_doctor_verifies_exact_cli_version_and_flags_without_provider_execution(tmp_path):
    binary=fake_cli(tmp_path,"import sys\n"+
        'if "--version" in sys.argv: print("devin 3000.11.3 (9c803229faa4)")\n'+
        'elif "--help" in sys.argv: print("--print --prompt-file --permission-mode --sandbox --model --config --respect-workspace-trust")\n'+
        'else: raise SystemExit(42)\n')
    config=ProviderConfig(adapter="devin",executable=binary)
    got=Adapter().doctor(config,tmp_path)
    assert got["version"].startswith("devin 3000.11.3")
    assert got["execution"]=="blocked_pending_native_qualification"
    wrong=fake_cli(tmp_path,"print('devin 9999.9.9')\n")
    with pytest.raises(OrchestratorError,match="version differs"):
        Adapter().doctor(ProviderConfig(adapter="devin",executable=wrong),tmp_path)


def test_harness_argv_keeps_prompts_private_and_denies_bypass(tmp_path):
    harness=ProtocolHarness()
    r=request(tmp_path,model="claude-opus-4.6")
    cmd=harness.argv(r,binary="/fixture/devin",prompt=tmp_path/"prompt.txt",config=tmp_path/"config.json")
    assert cmd[0]=="/fixture/devin"
    assert "--prompt-file" in cmd and "--print" in cmd
    assert "--sandbox" in cmd and "autonomous" in cmd
    assert "--respect-workspace-trust" in cmd and "true" in cmd
    assert "--cloud" not in cmd and "--continue" not in cmd and "--resume" not in cmd
    assert "--respect-workspace-trust false" not in " ".join(cmd)
    assert r.prompt not in " ".join(cmd)
    for kwargs in (dict(phase="plan"),dict(effort="high"),dict(permission=frozenset({"devin_override"})),dict(model="--cloud")):
        with pytest.raises(ProviderExecutionError):
            harness.argv(request(tmp_path,**kwargs),binary="devin",prompt=tmp_path/"prompt",config=tmp_path/"conf")


def test_harness_fixture_accepts_only_exact_json(tmp_path):
    runner_calls=[]
    def fake(argv,cwd,*,timeout,cancel):
        runner_calls.append((argv,cwd))
        p=pathlib.Path(argv[argv.index("--prompt-file")+1])
        assert p.read_text()=="Fixture prompt: do not reveal"
        assert p.stat().st_mode & 0o777 == 0o600
        conf=pathlib.Path(argv[argv.index("--config")+1])
        assert conf.stat().st_mode & 0o777 == 0o600
        assert '"mcp__*"' in conf.read_text()
        return _Result(0,'{"value": 7}')
    value=ProtocolHarness().run_fixture(request(tmp_path),binary="fake-devin",runner=fake)
    assert value.value==7 and len(runner_calls)==1
    prompt_path=pathlib.Path(runner_calls[0][0][runner_calls[0][0].index("--prompt-file")+1])
    assert not prompt_path.exists()


@pytest.mark.parametrize("raw",["", "accepted", chr(96)*3 + 'json\n{"value": 7}\n' + chr(96)*3, "[]", '{"value":"text"}', '{"value": 7} trailing'])
def test_harness_malformed_result_never_becomes_success(tmp_path,raw):
    with pytest.raises(ProviderExecutionError) as raised:
        ProtocolHarness().run_fixture(request(tmp_path),binary="fake",runner=lambda *a,**kw:_Result(0,raw))
    assert raised.value.diagnostics["failure_category"]=="protocol"


def test_harness_nonzero_exit_never_becomes_success(tmp_path):
    with pytest.raises(ProviderExecutionError) as raised:
        ProtocolHarness().run_fixture(request(tmp_path),binary="fake",runner=lambda *a,**kw:_Result(42,'{"value": 7}'))
    assert raised.value.diagnostics["failure_category"]=="provider_process"


def test_harness_cancellation_before_spawn(tmp_path):
    with pytest.raises(ProviderExecutionError) as raised:
        ProtocolHarness().run_fixture(request(tmp_path,cancel=lambda:True),binary="fake",runner=lambda *a,**kw:pytest.fail("spawn"))
    assert raised.value.diagnostics["stage"]=="cancelled"


@pytest.mark.skipif(os.name!='posix',reason="POSIX process-group kill test")
def test_synthetic_process_cancellation_and_timeout(tmp_path):
    sleeper=fake_cli(tmp_path,"import time\ntime.sleep(30)\n")
    started=time.monotonic()
    with pytest.raises(ProviderExecutionError) as raised:
        _run_bounded([sleeper],tmp_path,timeout=5,cancel=lambda:time.monotonic()-started>.07)
    assert raised.value.diagnostics["stage"]=="cancelled"
    with pytest.raises(ProviderExecutionError) as raised:
        _run_bounded([sleeper],tmp_path,timeout=.07,cancel=lambda:False)
    assert raised.value.diagnostics["stage"]=="timeout"


def test_synthetic_real_subprocess_strict_result_without_devin(tmp_path):
    binary=fake_cli(tmp_path,"print('{\"value\": 9}')\n")
    value=ProtocolHarness().run_fixture(request(tmp_path),binary=binary)
    assert value.value==9


def test_harness_does_not_convert_process_exceptions_to_success(tmp_path):
    def timeout(*args,**kwargs):
        raise ProviderExecutionError("no raw content",{"failure_category":"provider_process","stage":"timeout"})
    with pytest.raises(ProviderExecutionError,match="no raw content"):
        ProtocolHarness().run_fixture(request(tmp_path),binary="fake",runner=timeout)
