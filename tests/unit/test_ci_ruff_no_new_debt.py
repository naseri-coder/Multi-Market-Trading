"""Security and end-to-end contracts for exact new-path legacy lint debt."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/ci_ruff_no_new_debt.py"
SPEC = importlib.util.spec_from_file_location("tested_ruff_ratchet", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
RATCHET = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RATCHET)
LEGACY_PATH = "production_source/legacy.py"


def write_registry(head, entries, **extra):
    registry = head / RATCHET.LEGACY_REGISTRY
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(json.dumps({"schema_version": 1, "entries": entries, **extra}))


def record(head, findings):
    counts = RATCHET._counter(findings, tree=head)
    return {
        "path": LEGACY_PATH,
        "sha256": hashlib.sha256((head / LEGACY_PATH).read_bytes()).hexdigest(),
        "findings": [
            {"code": key[1], "message": key[2], "context": list(key[3]), "count": count}
            for key, count in sorted(counts.items())
        ],
    }


@pytest.fixture
def trees(tmp_path):
    base, head = tmp_path / "base", tmp_path / "head"
    base.mkdir()
    source = head / LEGACY_PATH
    source.parent.mkdir(parents=True)
    source.write_text("import os\n")
    findings = [{
        "filename": str(source), "code": "F401", "message": "unused import",
        "location": {"row": 1, "column": 1},
    }]
    return base, head, findings


def exemptions(base, head, findings):
    return RATCHET._legacy_exemptions(
        RATCHET._legacy_registry(head), base=base, head=head,
        head_counts=RATCHET._counter(findings, tree=head),
    )


def test_empty_registry_preserves_new_debt(trees):
    base, head, findings = trees
    write_registry(head, [])
    allowed, paths = exemptions(base, head, findings)
    assert allowed == Counter() and paths == []
    assert sum((RATCHET._counter(findings, tree=head) - allowed).values()) == 1


def test_exact_new_path_accepts_multiplicity(trees):
    base, head, findings = trees
    findings *= 2
    write_registry(head, [record(head, findings)])
    allowed, paths = exemptions(base, head, findings)
    assert sum(allowed.values()) == 2 and paths == [LEGACY_PATH]


@pytest.mark.parametrize("mutation", ["hash", "fingerprint", "extra", "missing", "count"])
def test_new_path_mismatch_fails_closed(trees, mutation):
    base, head, findings = trees
    entry = record(head, findings)
    if mutation == "hash":
        entry["sha256"] = "0" * 64
    elif mutation == "fingerprint":
        entry["findings"][0]["context"] = ["changed context"]
    elif mutation == "extra":
        findings.append({**findings[0], "code": "E501", "message": "extra finding"})
    elif mutation == "missing":
        findings.clear()
    else:
        entry["findings"][0]["count"] = 2
    write_registry(head, [entry])
    with pytest.raises(ValueError):
        exemptions(base, head, findings)


@pytest.mark.parametrize("same_findings", [False, True])
def test_existing_base_path_never_receives_exemption(trees, same_findings):
    base, head, findings = trees
    source = base / LEGACY_PATH
    source.parent.mkdir(parents=True)
    source.write_text("pass\n")
    entry = record(head, findings)
    if same_findings:
        source.write_bytes((head / LEGACY_PATH).read_bytes())
        entry["sha256"] = "0" * 64  # Stale historical hash is intentionally inert.
    write_registry(head, [entry])
    allowed, paths = exemptions(base, head, findings)
    assert not allowed and not paths
    head_counts = RATCHET._counter(findings, tree=head)
    base_counts = head_counts if same_findings else Counter()
    assert sum(((head_counts - base_counts) - allowed).values()) == (0 if same_findings else 1)


@pytest.mark.parametrize("path", [
    "../escape.py", "/production_source/x.py", "tests/new.py",
    "production_source/../x.py", "production_source//x.py",
    "production_source/./x.py", "production_source", "production_source/evil\\x.py",
])
def test_invalid_paths_are_rejected(trees, path):
    _, head, findings = trees
    entry = record(head, findings)
    entry["path"] = path
    write_registry(head, [entry])
    with pytest.raises(ValueError):
        RATCHET._legacy_registry(head)


@pytest.mark.parametrize("mutation", [
    "schema", "boolean_schema", "entries_type", "duplicate_path", "duplicate_fingerprint",
    "zero_count", "negative_count", "boolean_count", "sha", "context_type",
    "context_item", "context_long", "context_newline", "empty_findings", "code",
    "message", "extra_field", "entry_type",
])
def test_malformed_registry_rejected(trees, mutation):
    _, head, findings = trees
    entry = record(head, findings)
    data = {"schema_version": 1, "entries": [entry]}
    if mutation == "schema":
        data["schema_version"] = 2
    elif mutation == "boolean_schema":
        data["schema_version"] = True
    elif mutation == "entries_type":
        data["entries"] = {}
    elif mutation == "duplicate_path":
        data["entries"].append(entry)
    elif mutation == "duplicate_fingerprint":
        entry["findings"].append(entry["findings"][0])
    elif mutation in {"zero_count", "negative_count", "boolean_count"}:
        entry["findings"][0]["count"] = {
            "zero_count": 0, "negative_count": -1, "boolean_count": True,
        }[mutation]
    elif mutation == "sha":
        entry["sha256"] = "A" * 64
    elif mutation.startswith("context"):
        entry["findings"][0]["context"] = {
            "context_type": "source", "context_item": [1],
            "context_long": ["line"] * 6, "context_newline": ["a\nb"],
        }[mutation]
    elif mutation == "empty_findings":
        entry["findings"] = []
    elif mutation == "code":
        entry["findings"][0]["code"] = None
    elif mutation == "message":
        entry["findings"][0]["message"] = []
    elif mutation == "extra_field":
        entry["ignore_all"] = True
    else:
        data["entries"] = [None]
    write_registry(head, [])
    (head / RATCHET.LEGACY_REGISTRY).write_text(json.dumps(data))
    with pytest.raises(ValueError):
        RATCHET._legacy_registry(head)


def test_duplicate_json_fields_rejected(trees):
    _, head, _ = trees
    write_registry(head, [])
    (head / RATCHET.LEGACY_REGISTRY).write_text(
        '{"schema_version":1,"schema_version":1,"entries":[]}'
    )
    with pytest.raises(ValueError):
        RATCHET._legacy_registry(head)


@pytest.mark.parametrize("object_type", ["missing", "symlink", "directory"])
def test_new_path_requires_regular_file(trees, object_type):
    base, head, findings = trees
    write_registry(head, [record(head, findings)])
    counts = RATCHET._counter(findings, tree=head)
    source = head / LEGACY_PATH
    source.unlink()
    if object_type == "symlink":
        source.symlink_to(head / "not-present")
    elif object_type == "directory":
        source.mkdir()
    with pytest.raises(ValueError):
        RATCHET._legacy_exemptions(
            RATCHET._legacy_registry(head), base=base, head=head, head_counts=counts,
        )


def test_zero_findings_need_no_baseline(trees):
    base, head, _ = trees
    write_registry(head, [])
    assert exemptions(base, head, []) == (Counter(), [])


@pytest.mark.parametrize("scenario", [
    "exact", "changed", "existing", "unregistered", "extra", "malformed", "zero",
])
def test_synthetic_cli_integration(tmp_path, scenario):
    repo = tmp_path / "synthetic"
    (repo / "scripts").mkdir(parents=True)
    shutil.copyfile(SCRIPT, repo / "scripts/ci_ruff_no_new_debt.py")
    (repo / "pyproject.toml").write_text(
        '[tool.ruff]\nline-length=100\n[tool.ruff.lint]\nselect=["E501","F401"]\n'
    )
    write_registry(repo, [])
    source = repo / LEGACY_PATH
    source.parent.mkdir()
    if scenario == "existing":
        source.write_text("pass\n")
    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=Ratchet Test", "-c", "user.email=test@example.invalid",
         "commit", "-qm", "synthetic base"], cwd=repo, check=True, capture_output=True,
    )
    base_sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    source.write_text("pass\n" if scenario == "zero" else "import os\n")
    findings = RATCHET._ruff_findings(repo, repo / "pyproject.toml")
    if scenario not in {"unregistered", "zero"}:
        write_registry(repo, [record(repo, findings)])
    if scenario == "changed":
        source.write_text("import sys\n")
    elif scenario == "extra":
        (repo / "production_source/unregistered.py").write_text("import sys\n")
    elif scenario == "malformed":
        write_registry(repo, [], schema_version=9)
    result = subprocess.run(
        [sys.executable, str(repo / "scripts/ci_ruff_no_new_debt.py"), "--base-sha", base_sha],
        cwd=repo, text=True, capture_output=True,
    )
    assert (result.returncode == 0) == (scenario in {"exact", "zero"})
    if scenario == "exact":
        assert "RUFF_LEGACY_BASELINE_PATHS_APPLIED=1" in result.stdout
        assert "RUFF_LEGACY_BASELINE_FINDINGS_APPLIED=1" in result.stdout
    elif scenario in {"existing", "unregistered", "extra"}:
        assert "RUFF_NEW_FINDINGS=1" in result.stdout
    if result.returncode == 0:
        assert "RUFF_NO_NEW_FINDINGS_PASS" in result.stdout
