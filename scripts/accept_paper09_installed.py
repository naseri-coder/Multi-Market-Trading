"""Real installed-wheel, offline Brooks PAPER release backup/rollback/soak rehearsal.

Purpose: validate ONLY the two existing Stage10 simulated SQLite stores,
against the genuine historical pinned Brooks V5 and synthetic closed bars.
All state created under a fresh, owner-private disposable test parent.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
from pathlib import Path

import naseri_markets
from naseri_markets.brooks_stage10_recovery_v1 import reconcile_stage10_paper
from naseri_markets.paper09_snapshot_v1 import (
    Paper09SnapshotRefused,
    restore_pair,
    snapshot_pair,
)

N_SOAK = 32


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def accept(parent: Path, frozen: Path) -> dict:
    if (os.geteuid() == 0 or os.environ.get("MMT_NONPRODUCTION") != "1"
            or "MMT_PRODUCTION" in os.environ):
        raise ValueError("P09_DISPOSABLE_NONROOT_ONLY")
    module = Path(naseri_markets.__file__).resolve()
    if Path(sys.prefix).resolve() not in module.parents:
        raise ValueError("P09_INSTALLED_WHEEL_REQUIRED")
    parent = parent.absolute()
    if (not parent.is_dir() or parent.is_symlink()
            or parent.stat().st_uid != os.geteuid()
            or stat.S_IMODE(parent.stat().st_mode) != 0o700
            or any(parent.iterdir())):
        raise ValueError("P09_FRESH_EXCLUSIVE_OWNER_PARENT_REQUIRED")
    # Run the already accepted real pinned Brooks V5 two-process journey.
    previous = Path(__file__).with_name("accept_paper07_installed.py")
    if not previous.is_file() or previous.is_symlink():
        raise ValueError("P09_REVIEWED_PRIOR_STAGE_SCRIPT_REQUIRED")
    spec = importlib.util.spec_from_file_location("_p07_acceptance", previous)
    if spec is None or spec.loader is None:
        raise ValueError("P09_BASE_ACCEPTANCE_IMPORT_REFUSED")
    a07 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(a07)
    outcome = a07.accept(parent, frozen)
    if outcome["verdict"] != "PINNED_BROOKS_INSTALLED_OFFLINE_PAPER_PASS":
        raise ValueError("P09_TRUE_FROZEN_ENGINE_REQUIRED")
    state = parent / "p07-cleanwheel"
    names = ("custom_paper.db", "brooks_stage10_paper.sqlite")
    # Historical Stage10's generic simulator inherits operator umask.
    # The only auto-adjustment here is to a disposable fixture created
    # exclusively by this rehearsal, NEVER to an existing user state.
    paper = state / "brooks_stage10_paper.sqlite"
    if paper.is_symlink() or paper.stat().st_nlink != 1:
        raise ValueError("P09_OWNED_PAPER_LEDGER_REQUIRED")
    paper.chmod(0o600)
    before = {n: _sha(state / n) for n in names}
    original_reconciliation = reconcile_stage10_paper(state)
    if original_reconciliation["status"] not in (
        "MATCHED_PAPER_ORDER", "CLEAN_NO_SIGNALS",
    ):
        raise ValueError("P09_EXISTING_PAIR_UNHEALTHY")

    bundle_parent = parent / "private-archive"
    restore_parent = parent / "isolated-restore"
    tamper_parent = parent / "refused-restore"
    for place in (bundle_parent, restore_parent, tamper_parent):
        place.mkdir(mode=0o700)
    snapshot = snapshot_pair(state, bundle_parent)
    bundle = bundle_parent / "p09-backup"
    if {p.name for p in bundle.iterdir()} != set(names) | {"manifest.json"}:
        raise ValueError("P09_BUNDLE_UNEXPECTED_FILE_OR_WAL_SIDECAR")
    result = restore_pair(bundle, restore_parent)
    restored = restore_parent / "p09-restored"
    if result["reconciliation_status"] != original_reconciliation["status"]:
        raise ValueError("P09_RESTORE_RECONCILIATION_DRIFT")
    manifest = json.loads((bundle / "manifest.json").read_text())
    if any(_sha(restored / n) != manifest["files"][n]["sha256"] for n in names):
        raise ValueError("P09_RESTORE_BYTES_MISMATCH")

    # Simulate an abandoned candidate upgrade, DELETE ONLY the isolated
    # candidate and recover again from the already verified static bundle.
    with (restored / "incompatible-upgrade.marker").open("x") as broken:
        broken.write("deliberate injected failure; no real upgrade performed")
    shutil.rmtree(restored)
    if restored.exists():
        raise ValueError("P09_ROLLBACK_CANDIDATE_NOT_REMOVED")
    restored = restore_parent / "p09-restored"
    again = restore_pair(bundle, restore_parent)
    if again["manifest_sha256"] != snapshot["manifest_sha256"]:
        raise ValueError("P09_CANDIDATE_ROLLBACK_DIGEST_CHANGED")

    # Integrity-check rejects a separately copied, tampered archive before
    # creating any target. Never mutate the canonical, original bundle.
    malicious = parent / "tampered-copy"
    shutil.copytree(bundle, malicious)
    target = malicious / "custom_paper.db"
    with target.open("r+b") as data:
        data.seek(200)
        data.write(b"bad backup bytes!")
    try:
        restore_pair(malicious, tamper_parent)
    except Paper09SnapshotRefused as exc:
        if (tamper_parent / "p09-restored").exists():
            raise ValueError("P09_PARTIAL_RESTORE_NOT_ROLLED_BACK") from exc
    else:
        raise ValueError("P09_CORRUPT_BACKUP_MUST_BE_REFUSED")

    # Bounded no-network SOAK: each check is a NEW process; the original
    # writer is stopped. Check no source or restored DB mutation.
    for _ in range(N_SOAK):
        proc = subprocess.run(
            [sys.executable, "-I", "-m", "naseri_markets.brooks_stage10_cli",
             "--reconcile", "--state-dir", str(restored)],
            cwd=parent, env={
                "HOME": str(parent), "PYTHONDONTWRITEBYTECODE": "1",
            }, capture_output=True, text=True, check=False, timeout=20,
        )
        if proc.returncode or not proc.stdout or proc.stderr:
            raise ValueError("P09_SOAK_READONLY_SUBPROCESS_REFUSED")
        report = json.loads(proc.stdout)
        if (report["status"] != result["reconciliation_status"]
                or report["can_automatically_resume"]
                or report["live_orders_authorized"]
                or report["telegram_publication_authorized"]):
            raise ValueError("P09_RESTART_STATUS_OR_AUTHORIZATION_DRIFT")
    if any(_sha(state / n) != before[n] for n in names):
        raise ValueError("P09_SOURCE_MODIFIED_DURING_OFFLINE_REHEARSAL")
    if any(_sha(restored / n) != manifest["files"][n]["sha256"] for n in names):
        raise ValueError("P09_RESTORED_LEDGER_DRIFT")
    return {
        "verdict": "MMT_PAPER09_CLEAN_WHEEL_OFFLINE_RC_ACCEPTED",
        "installed_wheel": True,
        "frozen_brooks_genuine": True,
        "decision": outcome["decision"],
        "backup_verified": True,
        "isolated_restore_verified": True,
        "injected_candidate_rollback_verified": True,
        "corrupt_archive_refused": True,
        "soak_processes": N_SOAK,
        "restored_status": result["reconciliation_status"],
        "production_authorized": False,
        "automatic_recovery_authorized": False,
        "live_orders_authorized": False,
        "broker_orders_sent": False,
        "telegram_sent": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-parent", type=Path, required=True)
    parser.add_argument("--legacy-source", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = accept(args.state_parent, args.legacy_source)
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error,
            subprocess.TimeoutExpired):
        print("P09_ISOLATED_RELEASE_REHEARSAL_REFUSED", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
