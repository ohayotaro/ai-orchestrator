"""DV-04B synthetic subprocess boundary experiment. No Devin invocation.

All writes are within one freshly created tempfile root. A fake program
attempts a write to a sibling of its workspace, demonstrating why environment
scrubbing is NOT filesystem confinement. This is a measured limitation of an
unconfined Python fixture, not a Devin sandbox test.
"""
from __future__ import annotations

import json
import os
import pathlib
import signal
import subprocess
import sys
import tempfile

REQUIRED_UNKNOWN = (
    "native_direct_edit_write_scope",
    "native_team_session_policy",
    "native_config_import_and_hooks",
    "native_network_egress",
    "native_headless_trust",
    "native_schema_bound_terminal_result",
    "native_cancel_remote_effects",
)

FAKE_SOURCE = '''import json, os, pathlib, sys
workspace = pathlib.Path(sys.argv[1]).resolve()
home = pathlib.Path(sys.argv[2]).resolve()
outside = pathlib.Path(sys.argv[3]).resolve()
outside.write_text('synthetic escape', encoding='utf-8')
print(json.dumps({
    'cwd_correct': pathlib.Path.cwd().resolve() == workspace,
    'home_disposable': pathlib.Path(os.environ.get('HOME', '/')).resolve() == home,
    'xdg_disposable': pathlib.Path(os.environ.get('XDG_CONFIG_HOME', '/')).resolve() == home / '.config',
    'credential_environment_scrubbed': all(x not in os.environ for x in (
        'DV04B_TEST_SECRET', 'DEVIN_PERMISSION_MODE', 'DEVIN_SANDBOX',
        'TWINE_PASSWORD', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY')),
    'synthetic_outside_write_observed': outside.read_text(encoding='utf-8') == 'synthetic escape',
}, sort_keys=True))
'''


def fixture_child_env(home: pathlib.Path) -> dict[str, str]:
    """Whitelist, not inheritance. Used ONLY by the fake interpreter child."""
    return {
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local" / "share"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "TMPDIR": str(home / "tmp"),
        "PATH": os.defpath,
        "LANG": "C",
        "GIT_TERMINAL_PROMPT": "0",
        "PYTHONNOUSERSITE": "1",
    }


def _run_synthetic(script: pathlib.Path, workspace: pathlib.Path,
                   home: pathlib.Path, outside: pathlib.Path) -> dict:
    argv = [sys.executable, "-I", str(script), str(workspace), str(home), str(outside)]
    proc = subprocess.Popen(
        argv, cwd=workspace, env=fixture_child_env(home),
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=4)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.communicate()
        raise RuntimeError("synthetic fixture timeout") from None
    if proc.returncode != 0 or len(stdout) > 8192 or len(stderr) > 8192:
        raise RuntimeError("synthetic fixture failed or exceeded output bound")
    return json.loads(stdout)


def run() -> dict:
    if os.name != "posix":
        raise RuntimeError("DV-04B fixture requires POSIX process groups")
    with tempfile.TemporaryDirectory(prefix="dv04b-synthetic-") as dirname:
        root = pathlib.Path(dirname)
        workspace = root / "workspace"
        home = root / "home"
        workspace.mkdir(mode=0o700)
        home.mkdir(mode=0o700)
        for name in (".config", ".cache", ".local/share", "tmp"):
            (home / name).mkdir(mode=0o700, parents=True, exist_ok=True)
        script = workspace / "fake_child.py"
        script.write_text(FAKE_SOURCE, encoding="utf-8")
        outside = root / "outside-sentinel.txt"
        outside.write_text("untouched", encoding="utf-8")
        before = outside.read_bytes()
        result = _run_synthetic(script, workspace, home, outside)
        observed = outside.read_bytes() != before
        required_true = (
            "cwd_correct", "home_disposable", "xdg_disposable",
            "credential_environment_scrubbed", "synthetic_outside_write_observed",
        )
        if not observed or any(result.get(key) is not True for key in required_true):
            raise RuntimeError("synthetic boundary observation incomplete")
        return {
            "schema_version": 1,
            "kind": "dv04b_synthetic_fixture_boundary",
            "status": "REVIEW_REQUIRED",
            "result": "PASS_SYNTHETIC_DETECTION_ONLY",
            "provider_calls": 0,
            "execution_authorized": False,
            "task_or_gate_mutations": 0,
            "checks": {key: result[key] for key in required_true},
            "sandbox_claim": "none; no Devin process or native sandbox used",
            "finding": "an unconfined synthetic child can modify a temporary sibling outside cwd",
            "still_unverified": list(REQUIRED_UNKNOWN),
        }


def main() -> int:
    try:
        print(json.dumps(run(), sort_keys=True, indent=2))
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"schema_version": 1, "kind": "dv04b_synthetic_fixture_boundary",
                          "status": "BLOCKED", "error_type": type(exc).__name__,
                          "execution_authorized": False}, sort_keys=True))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
