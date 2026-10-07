"""Post-release documentation checks; never publish or perform live probes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess

import pytest

from ai_orchestrator import release_evidence as evidence
from ai_orchestrator.cli import parser

ROOT = Path(__file__).resolve().parents[1]
ACTIVE = [
    "README.md", "README_ja.md", "CHANGELOG.md", "ROADMAP.md",
    "docs/SUPPORT.md", "docs/V1_VERIFICATION.md", "docs/E2E_V1.md",
    "docs/V1_RELEASE_PREPARATION.md", "docs/V1_LIVE_E2E.md",
    "docs/V1_PREPARATION_ja.md", "docs/SINGLE_TERMINAL.md",
    "docs/TROUBLESHOOTING.md",
]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def shell_blocks(path: str) -> list[str]:
    return re.findall(r"```bash\n(.*?)\n```", text(path), re.S)


def test_readme_shell_walkthrough_is_identical_in_both_languages():
    en = shell_blocks("README.md")
    assert en and en == shell_blocks("README_ja.md")
    combined = "\n".join(en)
    assert "ai-orchestrator-kernel[interop]==1.0.0" in combined
    assert combined.index("validator add pytest") < combined.index("trust --by")
    assert combined.index("trust --by") < combined.index("validator check pytest")
    assert 'cd "$PROJECT" && claude' in combined
    assert "mcp remove" not in combined
    assert "--replace" not in combined
    assert not re.search(r"^\s*(exit|set -e|#)", combined, re.M)
    assert "<<" not in combined


@pytest.mark.parametrize("path", ACTIVE)
def test_active_document_shell_blocks_parse_and_have_no_continuation_tail(path):
    for block in shell_blocks(path):
        assert not block.rstrip().endswith("\\"), path
        result = subprocess.run(["bash", "-n"], input=block, text=True, capture_output=True)
        assert result.returncode == 0, (path, result.stderr)


@pytest.mark.parametrize("path", ACTIVE)
def test_active_document_relative_links_resolve(path):
    for link in re.findall(r"(?<!!)\[[^\]]*\]\(([^)]+)\)", text(path)):
        if "://" in link or link.startswith(("#", "mailto:")):
            continue
        target = link.split("#", 1)[0]
        assert (ROOT / path).parent.joinpath(target).exists(), (path, link)


@pytest.mark.parametrize("path", ACTIVE)
def test_active_docs_do_not_embed_owner_paths_or_bootstrap_identity(path):
    value = text(path)
    assert "/Users/ohayotaro" not in value
    assert "bootstrap@users.noreply.github.com" not in value
    assert "TWINE_PASSWORD=" not in value


def test_documented_cli_setup_shapes_are_accepted_without_dispatch():
    cli = parser()
    commands = [
        ["--project", "/tmp/demo", "init", "--name", "calculator-demo"],
        ["--project", "/tmp/demo", "validator", "add", "pytest", "--timeout", "120",
         "--", "/tmp/venv/bin/python", "-m", "pytest", "-q"],
        ["--project", "/tmp/demo", "trust", "--by", "example-owner", "--ack-local-execution"],
        ["--project", "/tmp/demo", "validator", "check", "pytest"],
        ["--project", "/tmp/demo", "identity", "--skill", "/tmp/SKILL.md"],
        ["--project", "/tmp/demo", "doctor", "--operational-only"],
        ["--project", "/tmp/demo", "serve"],
    ]
    for command in commands:
        cli.parse_args(command)


def test_public_summary_identities_are_consistent_but_not_an_approval_bundle():
    record = json.loads(text("docs/releases/v1.0.0.json"))
    artifact = evidence.ArtifactIdentity.model_validate(record["artifact"])
    matrix = evidence.SupportMatrix.model_validate(json.loads(text("docs/support-matrix.json")))
    assert record["record_kind"] == "post-release-summary-not-ReleaseManifest"
    assert record["evidence_custody"]["raw_evidence_imported_by_this_edit"] is False
    assert matrix.kernel_version == artifact.package_version == "1.0.0"
    assert len(matrix.deployments) == 1
    deployment = matrix.deployments[0]
    assert deployment.artifact == artifact
    assert deployment.host.transport.status == "supported"
    assert set(evidence.PROBE_REPETITIONS) == set(deployment.host.transport.operations)
    assert deployment.probes == [] and deployment.anomaly_disposition is None
    assert deployment.anomalies
    assert deployment.configuration_digest() != record["approved_deployment_configuration_sha256"]
    # Public classification is reported from the release; this deliberately
    # incomplete projection must never itself manufacture qualification READY.
    errors = evidence.qualify_deployment(deployment, artifact, ROOT)
    assert errors and "unresolved host anomaly" in errors
    assert any("valid fresh runs" in error for error in errors)
    assets = {item["name"]: item["sha256"] for item in record["public_assets"]}
    assert assets["ai_orchestrator_kernel-1.0.0-py3-none-any.whl"] == artifact.wheel_sha256
    assert assets["ai_orchestrator_kernel-1.0.0.tar.gz"] == artifact.sdist_sha256
    assert record["owner_reported_pass_records"] == 16


@pytest.mark.parametrize("path,expected", [
    ("CHANGELOG_HISTORY.md", "e932df44075c7ee839e66ca21aed2bb2ce150276"),
    ("ROADMAP_V1_PRE_RELEASE.md", "d6c497a64d65336e06e36956aad97fbfb7ed8c49"),
    ("docs/V1_PREPARATION_VERIFICATION.md", "7d1ae27ad1dbe098d389d630bcba73c5f9c759d3"),
    ("docs/SINGLE_TERMINAL_HISTORY.md", "d2cce155ee7dcdb2e66dc6bbdd19cee5051d09e1"),
    ("docs/support-matrix-pre-release.json", "7bbbeeea9b019a527871a3769f11cb3ea6bd2fa4"),
    ("docs/support-matrix-v017.json", "80587e0fbc413d10322415fd4eb4efead8e1da5a"),
])
def test_historical_git_blobs_remain_exact(path, expected):
    raw = (ROOT / path).read_bytes()
    assert hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest() == expected
