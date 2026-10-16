"""R32 deterministic local kit fixture tests; no actual install/DB/credentials."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from naseri_markets import mmt_r32_stopped_recovery_review_v1 as recovery
from naseri_markets.operational_reconciliation_v1 import RecoveryPaths
from scripts import mmt_r32_offline_review_kit_v1 as kit


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), *args], stderr=subprocess.DEVNULL,
        text=True, timeout=10,
    ).strip()


@pytest.fixture
def fixture_checkout(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("local git required")
    checkout = tmp_path / "source"
    checkout.mkdir()
    git(checkout, "init")
    git(checkout, "config", "user.name", "R32 Fixture")
    git(checkout, "config", "user.email", "r32@example.invalid")
    for rel in kit.FILES:
        path = checkout / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("EXPLICIT R32 SYNTHETIC TEST FILE: " + rel).encode())
    git(checkout, "add", "--all")
    git(checkout, "commit", "-m", "isolated stubbed review source fixture")
    output_parent = tmp_path / "private"
    output_parent.mkdir(mode=0o700)
    return checkout, git(checkout, "rev-parse", "HEAD"), output_parent


def make(checkout, sha, parent):
    return kit.prepare_r32_review_kit(
        source_root=checkout, expected_head=sha,
        destination=parent / "kit", operator_ack=True,
    )


def test_r32_pinned_checkout_private_review_kit_roundtrip(fixture_checkout):
    root, sha, parent = fixture_checkout
    report = make(root, sha, parent)
    assert report["review_commit"] == sha
    assert report["review_files"] == len(kit.FILES)
    assert report["standalone_install_ready"] is False
    assert report["live_trading_authorized"] is False
    checked = kit.verify_r32_review_kit(parent / "kit", operator_ack=True)
    assert checked == report
    assert not (parent / "kit" / ".env").exists()
    assert not (parent / "kit" / "production_source").exists()
    assert (parent / "kit" / "manifest.json").stat().st_mode & 0o077 == 0
    assert len(list((parent / "kit" / "review-files").rglob("*.py"))) >= 5


def test_r32_dirty_head_and_missing_operator_approval_refused(fixture_checkout):
    root, sha, parent = fixture_checkout
    with pytest.raises(kit.R32KitRefused, match="OFFLINE_ACK"):
        kit.prepare_r32_review_kit(
            source_root=root, expected_head=sha,
            destination=parent / "one",
        )
    with pytest.raises(kit.R32KitRefused, match="SHA_MISMATCH"):
        kit.prepare_r32_review_kit(
            source_root=root, expected_head="f" * 40,
            destination=parent / "one", operator_ack=True,
        )
    (root / "local_untracked.txt").write_text("uncommitted")
    with pytest.raises(kit.R32KitRefused, match="DIRTY_CHECKOUT"):
        kit.prepare_r32_review_kit(
            source_root=root, expected_head=sha,
            destination=parent / "one", operator_ack=True,
        )
    assert not (parent / "one").exists()


def test_r32_refuses_output_inside_git_tree_and_no_overwrite(fixture_checkout):
    root, sha, parent = fixture_checkout
    with pytest.raises(kit.R32KitRefused, match="NEVER_WRITE_WITHIN_CHECKOUT"):
        kit.prepare_r32_review_kit(
            source_root=root, expected_head=sha,
            destination=root / "forbidden", operator_ack=True,
        )
    make(root, sha, parent)
    with pytest.raises(kit.R32KitRefused, match="NEW_DESTINATION_ONLY"):
        make(root, sha, parent)


def test_r32_symlink_source_rejected_even_when_committed(fixture_checkout):
    root, _, parent = fixture_checkout
    chosen = root / kit.FILES[0]
    chosen.unlink()
    chosen.symlink_to(root / kit.FILES[1])
    git(root, "add", "-A")
    git(root, "commit", "-m", "symlinked file fixture")
    sha = git(root, "rev-parse", "HEAD")
    with pytest.raises(kit.R32KitRefused, match="SYMLINK"):
        make(root, sha, parent)


def test_r32_mutated_payload_and_unexpected_file_fail(fixture_checkout):
    root, sha, parent = fixture_checkout
    make(root, sha, parent)
    target = parent / "kit" / "review-files" / kit.FILES[1]
    target.write_bytes(target.read_bytes() + b"tampered")
    with pytest.raises(kit.R32KitRefused, match="PACKAGE_CONTENT_MISMATCH"):
        kit.verify_r32_review_kit(parent / "kit", operator_ack=True)
    target.write_bytes((root / kit.FILES[1]).read_bytes())
    (parent / "kit" / "unexpected.txt").write_text("secret?")
    with pytest.raises(kit.R32KitRefused, match="UNEXPECTED_TOP_LEVEL"):
        kit.verify_r32_review_kit(parent / "kit", operator_ack=True)


def test_r32_manifest_false_permission_invariant(fixture_checkout):
    root, sha, parent = fixture_checkout
    make(root, sha, parent)
    manifest = parent / "kit" / "manifest.json"
    obj = json.loads(manifest.read_bytes())
    obj["production_install_allowed"] = True
    manifest.write_bytes(kit._canon(obj))
    with pytest.raises(kit.R32KitRefused, match="REVIEW_ONLY_MANIFEST"):
        kit.verify_r32_review_kit(parent / "kit", operator_ack=True)


def test_r32_private_parent_and_production_env_block(fixture_checkout, monkeypatch):
    root, sha, parent = fixture_checkout
    public = parent.parent / "public"
    public.mkdir(mode=0o755)
    with pytest.raises(kit.R32KitRefused, match="PRIVATE_PARENT"):
        kit.prepare_r32_review_kit(
            source_root=root, destination=public / "kit",
            expected_head=sha, operator_ack=True,
        )
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(kit.R32KitRefused, match="OFFLINE_ACK"):
        make(root, sha, parent)


def fake_report(*, authorize=False):
    return SimpleNamespace(
        broker_authorized=authorize, telegram_authorized=False,
        live_authorized=False, replay_authorized=False,
        evidence_sha256="a" * 64,
        cross_ledger_evidence_sha256="b" * 64,
        cross_ledger_verdict="UNATTESTED",
        status="BLOCKED_MANUAL_RECONCILIATION",
        jobs=(
            SimpleNamespace(verdict="BLOCKED_MANUAL_RECONCILIATION"),
            SimpleNamespace(verdict="DONE_UNVERIFIED_CROSS_LEDGER"),
        ),
        blocking_jobs=1, unverified_done_jobs=1,
    )


def snapshots(tmp_path):
    return RecoveryPaths(
        runtime=tmp_path / "runtime.sqlite",
        control=tmp_path / "control.sqlite",
        paper=tmp_path / "paper.sqlite",
        signal=tmp_path / "signal.sqlite",
    )


def test_r32_mock_stage18_review_cannot_authorize_restore(tmp_path, monkeypatch):
    paths = snapshots(tmp_path)
    observed = []
    def fake_eval(p):
        observed.append(p)
        return fake_report()
    monkeypatch.setattr(recovery, "evaluate_operational_recovery", fake_eval)
    report = recovery.review_r32_stopped_snapshots(
        paths, all_writers_stopped=True, operator_ack=True,
    )
    assert observed == [paths]
    assert report["jobs_examined"] == 2
    assert report["operator_review_required"] is True
    assert report["checkpoint_restore_performed"] is False
    assert report["retry_authorized"] is False
    assert report["telegram_send_authorized"] is False
    assert report["live_trading_authorized"] is False
    assert len(report["local_review_sha256"]) == 64
    assert not any(p.exists() for p in (
        paths.runtime, paths.control, paths.paper, paths.signal,
    ))


def test_r32_recovery_ack_production_and_auth_drift_refused(
    tmp_path, monkeypatch,
):
    paths = snapshots(tmp_path)
    with pytest.raises(recovery.R32RecoveryRefused, match="STOP_WRITERS"):
        recovery.review_r32_stopped_snapshots(
            paths, all_writers_stopped=False, operator_ack=True,
        )
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(recovery.R32RecoveryRefused, match="STOP_WRITERS"):
        recovery.review_r32_stopped_snapshots(
            paths, all_writers_stopped=True, operator_ack=True,
        )
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    monkeypatch.setattr(
        recovery, "evaluate_operational_recovery",
        lambda _: fake_report(authorize=True),
    )
    with pytest.raises(recovery.R32RecoveryRefused, match="AUTHORIZATION_DRIFT"):
        recovery.review_r32_stopped_snapshots(
            paths, all_writers_stopped=True, operator_ack=True,
        )


def test_r32_assume_unchanged_source_blob_cannot_evade_pin(fixture_checkout):
    checkout, sha, parent = fixture_checkout
    target = kit.FILES[0]
    git(checkout, "update-index", "--assume-unchanged", target)
    (checkout / target).write_text("ATTACKER CHANGED BYTES, INDEX STILL OLD")
    # Status can be clean when the file is marked assume-unchanged;
    # exact captured bytes MUST be bound to HEAD blob nonetheless.
    assert git(checkout, "status", "--porcelain=v1", "--untracked-files=all") == ""
    with pytest.raises(kit.R32KitRefused, match="PINNED_SOURCE_BLOB_DRIFT"):
        make(checkout, sha, parent)


def test_r32_source_review_kit_never_grants_any_runtime_authority(
    fixture_checkout,
):
    root, sha, parent = fixture_checkout
    make(root, sha, parent)
    manifest = json.loads((parent / "kit" / "manifest.json").read_bytes())
    for field in (
        "independent_signer_verified", "artifact_reproducibility_certified",
        "supply_chain_security_certified", "complete_application_included",
        "real_installer_included", "production_install_allowed",
        "paper_or_live_enabled", "broker_orders_enabled",
        "telegram_sending_enabled", "restore_authorized",
    ):
        assert manifest[field] is False
    assert "production_source" not in str(manifest)
    assert all(not name.startswith(".env") for name in manifest["partial_review_files"])


def test_r32_posixpath_contract_rejects_invalid_types_and_linked_private_parent(
    fixture_checkout,
):
    """A real concrete PosixPath must work; unsafe path inputs must not."""
    root, sha, parent = fixture_checkout
    assert isinstance(root, Path)
    assert type(root) is not Path  # Regression: Path() is PosixPath on Linux.
    kit._source(root, sha)
    assert kit._secure_parent(parent) == parent
    with pytest.raises(kit.R32KitRefused, match="ABSOLUTE_ROOT_AND_PIN"):
        kit._source(str(root), sha)
    with pytest.raises(kit.R32KitRefused, match="PRIVATE_PARENT"):
        kit._secure_parent(str(parent))
    with pytest.raises(kit.R32KitRefused, match="ABSOLUTE_NEW_DESTINATION"):
        kit.prepare_r32_review_kit(
            source_root=root,
            destination=str(parent / "bad-kit"),
            expected_head=sha,
            operator_ack=True,
        )
    assert not (parent / "bad-kit").exists()
    linked = parent.parent / "symlink-to-private"
    linked.symlink_to(parent, target_is_directory=True)
    with pytest.raises(kit.R32KitRefused, match="PRIVATE_PARENT"):
        kit.prepare_r32_review_kit(
            source_root=root,
            destination=linked / "kit",
            expected_head=sha,
            operator_ack=True,
        )
    assert not (linked / "kit").exists()
