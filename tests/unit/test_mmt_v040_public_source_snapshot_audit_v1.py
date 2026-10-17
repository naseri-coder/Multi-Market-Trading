"""Real local Git tests for a complete 226-module public source inventory."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts import mmt_v040_public_source_snapshot_audit_v1 as gate


def git(repository: Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(repository), *args],
                       capture_output=True, text=True, check=True)
    return p.stdout.strip()


@pytest.fixture
def repository(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    (root / "naseri_markets").mkdir()
    module_names = ["__init__.py", "platform_cli.py"] + [
        f"module_{i:03}.py" for i in range(224)
    ]
    assert len(module_names) == gate.EXPECTED_MODULES
    for name in module_names:
        (root / "naseri_markets" / name).write_bytes(
            (f'"""Synthetic source for {name}."""\n').encode()
        )
    git(root, "init", "-q")
    git(root, "add", "naseri_markets")
    git(root, "-c", "user.name=Snapshot Test", "-c", "user.email=a@example.invalid",
        "commit", "-qm", "Lock source")
    source_commit = git(root, "rev-parse", "HEAD")
    tree = git(root, "rev-parse", "HEAD:naseri_markets")
    modules = []
    for name in sorted(module_names):
        file = root / "naseri_markets" / name
        raw = file.read_bytes()
        modules.append({
            "path": "naseri_markets/" + name,
            "git_blob_sha1": hashlib.sha1(
                b"blob " + str(len(raw)).encode() + b"\0" + raw
            ).hexdigest(),
            "size": len(raw),
        })
    lock = {
        "schema_version": 1,
        "distribution": "multi-market-trading",
        "release_candidate": "v0.4.0",
        "provenance": "GITHUB_TREE_SNAPSHOT__NOT_RELEASE_APPROVAL",
        "github_repository": "naseri-coder/Multi-Market-Trading",
        "snapshot_commit": source_commit,
        "public_subtree_sha1": tree,
        "expected_module_count": 226,
        "source_bytes": sum(m["size"] for m in modules),
        "modules": modules,
    }
    file = root / gate.SNAPSHOT_PATH
    file.write_text(json.dumps(lock, indent=2) + "\n")
    git(root, "add", "docs")
    git(root, "-c", "user.name=Snapshot Test", "-c", "user.email=a@example.invalid",
        "commit", "-qm", "Pinned snapshot")
    def params():
        return {
            "repository": root,
            "expected_source_commit": git(root, "rev-parse", "HEAD"),
            "expected_public_tree_sha1": tree,
            "expected_lock_sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
        }
    return root, file, params


def commit(root: Path, reason="test"):
    git(root, "add", ".")
    git(root, "-c", "user.name=Snapshot Test", "-c", "user.email=a@example.invalid",
        "commit", "-qm", reason)


def test_all_226_real_git_blob_bytes_match_snapshot(repository):
    _, _, params = repository
    report = gate.audit(**params())
    assert report["public_modules_verified"] == 226
    assert report["source_bytes_verified"] > 0
    assert report["public_release_authorized"] is False
    assert report["install_authorized"] is False
    assert report["live_trading_authorized"] is False
    assert report["writes_performed"] is False


def test_any_explicit_production_env_denied_first(repository, monkeypatch):
    _, _, params = repository
    monkeypatch.setenv("MMT_PRODUCTION", "0")
    with pytest.raises(gate.PublicSnapshotRefused, match="V040_NONPRODUCTION_REQUIRED"):
        gate.audit(**params())


def test_wrong_external_commit_pin_denied(repository):
    _, _, params = repository
    args = params()
    args["expected_source_commit"] = "0" * 40
    with pytest.raises(gate.PublicSnapshotRefused, match="V040_GIT_COMMIT_PIN_MISMATCH"):
        gate.audit(**args)


def test_wrong_external_public_subtree_pin_denied(repository):
    _, _, params = repository
    args = params()
    args["expected_public_tree_sha1"] = "0" * 40
    with pytest.raises(gate.PublicSnapshotRefused, match="V040_PUBLIC_TREE_PIN_MISMATCH"):
        gate.audit(**args)


def test_external_snapshot_digest_mismatch_denied(repository):
    _, _, params = repository
    args = params()
    args["expected_lock_sha256"] = "0" * 64
    with pytest.raises(gate.PublicSnapshotRefused, match="V040_SNAPSHOT_EXTERNAL_SHA256_MISMATCH"):
        gate.audit(**args)


def test_dirty_tracked_module_denied(repository):
    root, _, params = repository
    (root / "naseri_markets/module_101.py").write_text("# altered\n")
    with pytest.raises(gate.PublicSnapshotRefused, match="V040_GIT_NOT_CLEAN"):
        gate.audit(**params())


def test_extra_untracked_public_module_denied(repository):
    root, _, params = repository
    (root / "naseri_markets/unsigned.py").write_text("# unreviewed\n")
    with pytest.raises(gate.PublicSnapshotRefused, match="V040_GIT_NOT_CLEAN"):
        gate.audit(**params())


def test_clean_commit_cannot_redefine_module_count(repository):
    root, file, params = repository
    data = json.loads(file.read_text())
    data["expected_module_count"] = 225
    file.write_text(json.dumps(data, indent=2) + "\n")
    commit(root, "modify source inventory count")
    with pytest.raises(gate.PublicSnapshotRefused, match="V040_SNAPSHOT_IDENTITY_INVALID"):
        gate.audit(**params())


def test_clean_commit_cannot_change_just_one_blob_hash(repository):
    root, file, params = repository
    data = json.loads(file.read_text())
    data["modules"][9]["git_blob_sha1"] = "0" * 40
    file.write_text(json.dumps(data, indent=2) + "\n")
    commit(root, "forge one blob pin")
    with pytest.raises(gate.PublicSnapshotRefused, match="V040_SNAPSHOT_MODULE_BLOB_MISMATCH"):
        gate.audit(**params())


def test_clean_commit_cannot_mutate_source_tree_under_old_pin(repository):
    root, _, params = repository
    (root / "naseri_markets/module_101.py").write_text("# new version\n")
    commit(root, "new module version")
    with pytest.raises(gate.PublicSnapshotRefused, match="V040_PUBLIC_TREE_PIN_MISMATCH"):
        gate.audit(**params())


def test_clean_commit_cannot_reorder_inventory_entries(repository):
    root, file, params = repository
    data = json.loads(file.read_text())
    data["modules"][0], data["modules"][1] = data["modules"][1], data["modules"][0]
    file.write_text(json.dumps(data, indent=2) + "\n")
    commit(root, "reorder snapshot")
    with pytest.raises(gate.PublicSnapshotRefused, match="V040_SNAPSHOT_MEMBER_ORDER_INVALID"):
        gate.audit(**params())
