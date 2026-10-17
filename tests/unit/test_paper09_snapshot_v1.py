"""Actual limited two-DB offline PAPER backup, restore, rollback and integrity tests."""
from __future__ import annotations

import hashlib
import shutil
import sqlite3

import pytest

from naseri_markets.brooks_stage10_recovery_v1 import reconcile_stage10_paper
from naseri_markets.paper09_snapshot_v1 import (
    Paper09SnapshotRefused,
    restore_pair,
    snapshot_pair,
)
from test_brooks_paper07_real_replay_link import invoke, fake_positive_transport

pytest_plugins = ["test_brooks_paper07_real_replay_link"]


def _env(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def _parent(tmp_path, name):
    path = tmp_path / name
    path.mkdir(mode=0o700)
    return path


def _pair(ready, tmp_path, monkeypatch):
    _env(monkeypatch)
    fake_positive_transport(monkeypatch, ready[1])
    first = invoke(ready)
    assert first["paper_order_created"]
    # The historical Stage10 core may inherit a permissive process umask.
    # Never chmod an operator's original data implicitly during backup:
    # only this disposable fixture is explicitly made owner-private.
    (ready[0] / "brooks_stage10_paper.sqlite").chmod(0o600)
    archive = _parent(tmp_path, "archive")
    out = _parent(tmp_path, "output")
    result = snapshot_pair(ready[0], archive)
    assert result["verdict"] == "P09_OFFLINE_SNAPSHOT_CREATED"
    return first, archive, out


def test_snapshot_restore_preserves_two_existing_ledgers(ready, tmp_path, monkeypatch):
    first, archive, out = _pair(ready, tmp_path, monkeypatch)
    old = reconcile_stage10_paper(ready[0])
    assert old["status"] == "MATCHED_PAPER_ORDER"
    bundle = archive / "p09-backup"
    assert {x.name for x in bundle.iterdir()} == {
        "manifest.json", "custom_paper.db", "brooks_stage10_paper.sqlite",
    }
    assert all(x.stat().st_mode & 0o777 == 0o600 for x in bundle.iterdir())
    result = restore_pair(bundle, out)
    assert result["reconciliation_status"] == "MATCHED_PAPER_ORDER"
    state = out / "p09-restored"
    assert reconcile_stage10_paper(state)["linked_orders"] == 1
    assert reconcile_stage10_paper(state)["active_paper_reservations"] == 1
    assert all(
        hashlib.sha256((state / name).read_bytes()).digest()
        == hashlib.sha256((bundle / name).read_bytes()).digest()
        for name in ("custom_paper.db", "brooks_stage10_paper.sqlite")
    )
    assert first["paper"]["order_status"] == "CREATED"
    with pytest.raises(Paper09SnapshotRefused, match="NO_OVERWRITE"):
        restore_pair(bundle, out)


@pytest.mark.parametrize("failure", ["bitflip", "partial", "symlink", "missing"])
def test_corrupt_backup_never_creates_target(ready, tmp_path, monkeypatch, failure):
    _, archive, out = _pair(ready, tmp_path, monkeypatch)
    bundle = archive / "p09-backup"
    path = bundle / "custom_paper.db"
    if failure == "bitflip":
        with path.open("r+b") as f:
            f.seek(200)
            f.write(b"not sqlite anymore")
    elif failure == "partial":
        with path.open("r+b") as f:
            f.truncate(80)
    elif failure == "symlink":
        other = bundle / "moved-db"
        path.rename(other)
        path.symlink_to(other)
    else:
        path.unlink()
    with pytest.raises(Paper09SnapshotRefused):
        restore_pair(bundle, out)
    assert not (out / "p09-restored").exists()


def test_mid_restore_copy_failure_rolls_back_only_new_target(
    ready, tmp_path, monkeypatch,
):
    _, archive, out = _pair(ready, tmp_path, monkeypatch)
    from naseri_markets import paper09_snapshot_v1 as module
    original = module.shutil.copyfileobj
    invoked = [0]
    def interrupt(source, target, length=0):
        invoked[0] += 1
        if invoked[0] == 2:
            raise OSError("INJECTED_INTERRUPTED_UPGRADE")
        return original(source, target, length)
    monkeypatch.setattr(module.shutil, "copyfileobj", interrupt)
    with pytest.raises(OSError, match="INJECTED"):
        restore_pair(archive / "p09-backup", out)
    assert invoked[0] == 2
    assert not (out / "p09-restored").exists()
    assert (archive / "p09-backup" / "manifest.json").is_file()
    assert reconcile_stage10_paper(ready[0])["status"] == "MATCHED_PAPER_ORDER"


def test_refuses_live_context_or_privileged_runtime(ready, tmp_path, monkeypatch):
    fake_positive_transport(monkeypatch, ready[1])
    invoke(ready)
    archive = _parent(tmp_path, "archive")
    monkeypatch.setenv("MMT_NONPRODUCTION", "0")
    with pytest.raises(Paper09SnapshotRefused):
        snapshot_pair(ready[0], archive)
    assert not list(archive.iterdir())
    _env(monkeypatch)
    from naseri_markets import paper09_snapshot_v1 as module
    monkeypatch.setattr(module.os, "geteuid", lambda: 0)
    with pytest.raises(Paper09SnapshotRefused):
        snapshot_pair(ready[0], archive)


def test_cross_file_snapshot_fails_on_outstanding_writer(ready, tmp_path, monkeypatch):
    fake_positive_transport(monkeypatch, ready[1])
    invoke(ready)
    _env(monkeypatch)
    (ready[0] / "brooks_stage10_paper.sqlite").chmod(0o600)
    archive = _parent(tmp_path, "archive")
    db = sqlite3.connect(ready[0] / "custom_paper.db", timeout=1, isolation_level=None)
    try:
        db.execute("BEGIN IMMEDIATE")
        with pytest.raises(sqlite3.OperationalError):
            snapshot_pair(ready[0], archive)
    finally:
        db.execute("ROLLBACK")
        db.close()
    assert not (archive / "p09-backup").exists()


def test_rollback_candidate_failed_upgrade_keeps_bundle_and_original(
    ready, tmp_path, monkeypatch,
):
    _, archive, out = _pair(ready, tmp_path, monkeypatch)
    snapshot_hashes = {
        name: hashlib.sha256((ready[0] / name).read_bytes()).hexdigest()
        for name in ("custom_paper.db", "brooks_stage10_paper.sqlite")
    }
    # A failed upgrade rehearsal is a candidate clone, never in-place.
    candidate = restore_pair(archive / "p09-backup", out)
    assert candidate["verdict"] == "P09_OFFLINE_RESTORE_REHEARSAL_PASS"
    draft = out / "p09-restored"
    (draft / "upgrade-in-progress.marker").write_text("injected incompatible upgrade")
    shutil.rmtree(draft)
    assert not draft.exists()
    assert reconcile_stage10_paper(ready[0])["status"] == "MATCHED_PAPER_ORDER"
    assert all(hashlib.sha256((ready[0] / name).read_bytes()).hexdigest() == h
               for name, h in snapshot_hashes.items())
    assert restore_pair(archive / "p09-backup", out)["verdict"] == (
        "P09_OFFLINE_RESTORE_REHEARSAL_PASS"
    )


def test_manifest_no_file_injection_and_no_hardlinks(ready, tmp_path, monkeypatch):
    _, archive, out = _pair(ready, tmp_path, monkeypatch)
    bundle = archive / "p09-backup"
    with (bundle / "manifest.json").open("ab") as f:
        f.write(b'{"extra":"danger"}')
    with pytest.raises(Paper09SnapshotRefused):
        restore_pair(bundle, out)
    assert not (out / "p09-restored").exists()

def test_private_source_required_does_not_chmod_original(ready, tmp_path, monkeypatch):
    fake_positive_transport(monkeypatch, ready[1])
    invoke(ready)
    _env(monkeypatch)
    archive = _parent(tmp_path, "archive")
    db = ready[0] / "brooks_stage10_paper.sqlite"
    db.chmod(0o644)
    with pytest.raises(Paper09SnapshotRefused, match="PRIVATE_BOUNDED"):
        snapshot_pair(ready[0], archive)
    assert db.stat().st_mode & 0o777 == 0o644
    assert not (archive / "p09-backup").exists()


def test_hardlinked_source_refused_with_no_backup(ready, tmp_path, monkeypatch):
    fake_positive_transport(monkeypatch, ready[1])
    invoke(ready)
    _env(monkeypatch)
    archive = _parent(tmp_path, "archive")
    paper = ready[0] / "brooks_stage10_paper.sqlite"
    paper.chmod(0o600)
    link = tmp_path / "shared-ledger"
    link.hardlink_to(paper)
    with pytest.raises(Paper09SnapshotRefused, match="PRIVATE_BOUNDED"):
        snapshot_pair(ready[0], archive)
    assert not (archive / "p09-backup").exists()
    link.unlink()


def test_unexpected_bundle_file_refused_before_restore(ready, tmp_path, monkeypatch):
    _, archive, out = _pair(ready, tmp_path, monkeypatch)
    bundle = archive / "p09-backup"
    (bundle / "unexpected-data.txt").write_text("not in allowlist")
    with pytest.raises(Paper09SnapshotRefused, match="UNEXPECTED_FILE"):
        restore_pair(bundle, out)
    assert not (out / "p09-restored").exists()


def test_empty_valid_brooks_paper_pair_can_be_restored(ready, tmp_path, monkeypatch):
    _env(monkeypatch)
    # Existing Stage10 source/ledger are configured by the shared fixture,
    # but no paper signal, reservation or order has been recorded yet.
    (ready[0] / "brooks_stage10_paper.sqlite").chmod(0o600)
    assert reconcile_stage10_paper(ready[0])["status"] == "CLEAN_NO_SIGNALS"
    archive = _parent(tmp_path, "archive")
    output = _parent(tmp_path, "output")
    snapshot_pair(ready[0], archive)
    result = restore_pair(archive / "p09-backup", output)
    assert result["reconciliation_status"] == "CLEAN_NO_SIGNALS"
    assert reconcile_stage10_paper(output / "p09-restored")["linked_orders"] == 0
