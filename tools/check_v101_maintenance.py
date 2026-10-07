"""Fail closed if v1.0.1 expands runtime scope beyond packaging/version identity."""
from __future__ import annotations
import argparse
import email
import json
import re
import subprocess
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def git_show(ref: str, path: str) -> bytes:
    result = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=ROOT, capture_output=True)
    if result.returncode:
        raise ValueError(f"cannot read {ref}:{path}; fetch the baseline tag first")
    return result.stdout

def tracked(ref: str, prefix: str) -> list[str]:
    out = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", ref, prefix], cwd=ROOT, text=True)
    return [p for p in out.splitlines() if p]

def normalized(path: str, data: bytes) -> bytes:
    if path == "src/ai_orchestrator/__init__.py":
        return re.sub(br'__version__ = "[^"]+"', b'__version__ = "<VERSION>"', data)
    if path == "src/ai_orchestrator/assets/contracts.json":
        value = json.loads(data)
        value["package_version"] = "<VERSION>"
        return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return data

def source_check(baseline: str) -> None:
    current = set(tracked("HEAD", "src/ai_orchestrator"))
    previous = set(tracked(baseline, "src/ai_orchestrator"))
    if current != previous:
        raise ValueError("runtime package path set differs from v1.0.0")
    changed = []
    for path in sorted(current):
        if normalized(path, (ROOT / path).read_bytes()) != normalized(path, git_show(baseline, path)):
            changed.append(path)
    if changed:
        raise ValueError("runtime behavior/assets changed beyond version identity: " + ", ".join(changed))

    import tomllib
    now = tomllib.loads((ROOT / "pyproject.toml").read_text())
    old = tomllib.loads(git_show(baseline, "pyproject.toml").decode())
    for key in ("name", "description", "requires-python", "dependencies", "optional-dependencies", "scripts"):
        if now["project"].get(key) != old["project"].get(key):
            raise ValueError("non-maintenance project metadata changed: " + key)
    if now["project"]["version"] != "1.0.1":
        raise ValueError("project version is not 1.0.1")
    if now["project"].get("license") != "Apache-2.0" or now["project"].get("license-files") != ["LICENSE"]:
        raise ValueError("PEP 639 license metadata is not exact")
    if any(str(x).startswith("License ::") for x in now["project"].get("classifiers", [])):
        raise ValueError("deprecated License classifier retained")
    if "setuptools>=77.0.3" not in now["build-system"]["requires"]:
        raise ValueError("build backend floor does not guarantee PEP 639 support")

def metadata(raw: bytes, label: str) -> None:
    msg = email.message_from_bytes(raw)
    if msg["Version"] != "1.0.1":
        raise ValueError(label + ": wrong Version")
    if msg["License-Expression"] != "Apache-2.0":
        raise ValueError(label + ": missing License-Expression")
    if msg["License"]:
        raise ValueError(label + ": legacy License field must be absent")
    if not any(v.endswith("LICENSE") for v in (msg.get_all("License-File") or [])):
        raise ValueError(label + ": LICENSE not declared")
    body = msg.get_payload()
    if "Give your existing AI coding tools a shared workflow" not in body:
        raise ValueError(label + ": reorganized README is not the long description")

def dist_check(wheel: Path, sdist: Path) -> None:
    with zipfile.ZipFile(wheel) as z:
        names = z.namelist()
        meta = [n for n in names if n.endswith(".dist-info/METADATA")]
        if len(meta) != 1:
            raise ValueError("wheel METADATA missing/ambiguous")
        metadata(z.read(meta[0]), "wheel")
        if not any("/licenses/LICENSE" in n for n in names):
            raise ValueError("wheel LICENSE missing from dist-info/licenses")
    with tarfile.open(sdist, "r:gz") as t:
        names = t.getnames()
        pkg = [n for n in names if n.endswith("/PKG-INFO") and n.count("/") == 1]
        if len(pkg) != 1:
            raise ValueError("sdist root PKG-INFO missing/ambiguous")
        f = t.extractfile(pkg[0])
        if f is None:
            raise ValueError("sdist PKG-INFO unreadable")
        metadata(f.read(), "sdist")
        if not any(n.endswith("/LICENSE") and n.count("/") == 1 for n in names):
            raise ValueError("sdist LICENSE missing")

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--baseline", default="v1.0.0")
    p.add_argument("--wheel", type=Path)
    p.add_argument("--sdist", type=Path)
    a = p.parse_args()
    source_check(a.baseline)
    if (a.wheel is None) != (a.sdist is None):
        raise ValueError("--wheel and --sdist must be supplied together")
    if a.wheel:
        dist_check(a.wheel, a.sdist)
    print(json.dumps({"result": "PASS", "baseline": a.baseline, "version": "1.0.1",
                      "runtime_semantics": "unchanged"}))

if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"result": "FAIL", "error": str(exc)}))
        raise SystemExit(1)
