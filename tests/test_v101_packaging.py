"""v1.0.1 packaging/documentation maintenance invariants."""
from pathlib import Path
import tomllib
import ai_orchestrator

ROOT = Path(__file__).resolve().parents[1]

def test_v101_versions_and_pep639_metadata():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert ai_orchestrator.__version__ == "1.0.1"
    assert data["project"]["version"] == "1.0.1"
    assert data["project"]["license"] == "Apache-2.0"
    assert data["project"]["license-files"] == ["LICENSE"]
    assert not any(x.startswith("License ::") for x in data["project"]["classifiers"])
    assert "setuptools>=77.0.3" in data["build-system"]["requires"]

def test_v101_readme_is_distribution_description():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert data["project"]["readme"] == "README.md"
    value = (ROOT / "README.md").read_text()
    assert "documentation/packaging maintenance release" in value
    assert "ai-orchestrator-kernel[interop]==1.0.1" in value
