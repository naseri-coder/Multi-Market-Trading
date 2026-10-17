"""Installed, explicit two-binding synthetic PAPER journey and read-only reopen.

Reuses the existing Stage-20 pilot and Stage-13/19/9 evidence checkers.
No implicit restart, retry, database creation on inspect, network or broker.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import stat
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from urllib.parse import quote

from .job_effect_reconciliation_v1 import (
    EffectEvidencePaths,
    evaluate_recovery_decisions,
)
from .reliability_acceptance_v1 import (
    LedgerPaths,
    evaluate_offline_reliability,
)
from .unified_paper_pilot_stage20_v1 import run_paper_pilot
from .platform_version_policy_v1 import require_offline_platform_version

_SQLITE_FILES = (
    "control.sqlite", "paper.sqlite", "signals.sqlite",
    "runtime.sqlite", "effects.sqlite",
)
_EXPECTED_SIGNAL_KINDS = ("DRY_SIGNAL", "PAPER_PLAN", "PAPER_RESERVE")
_EXPECTED_PAPER_KINDS = ("PAPER_PLAN", "PAPER_RESERVE")


class InstalledPilotRefused(ValueError):
    """Use fixed codes only, never echo source paths or stored data."""


def _gate(*, ack: bool, installed: bool = True) -> None:
    if (ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        raise InstalledPilotRefused("EXPLICIT_NONPRODUCTION_ACK_REQUIRED")
    if installed:
        try:
            dist = version("multi-market-trading")
        except PackageNotFoundError as exc:
            raise InstalledPilotRefused("INSTALLED_PREVIEW_WHEEL_REQUIRED") from exc
        try:
            require_offline_platform_version(dist)
        except ValueError as exc:
            raise InstalledPilotRefused("PREVIEW_VERSION_MISMATCH") from exc


def _existing_state(directory: Path) -> dict[str, Path]:
    """Reject symlink, shared, non-owner, nonprivate and missing state roles."""
    if (not isinstance(directory, Path) or not directory.is_absolute()
            or directory.is_symlink() or not directory.is_dir()
            or directory.stat().st_uid != os.geteuid()
            or stat.S_IMODE(directory.stat().st_mode) != 0o700):
        raise InstalledPilotRefused("OWNER_PRIVATE_STATE_DIR_REQUIRED")
    files = {}
    identities = set()
    for basename in _SQLITE_FILES:
        child = directory / basename
        if child.is_symlink() or not child.is_file():
            raise InstalledPilotRefused("COMPLETE_PRIVATE_STATE_REQUIRED")
        st = child.stat()
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid()
                or st.st_nlink != 1 or stat.S_IMODE(st.st_mode) & 0o077
                or not 128 <= st.st_size <= 512 * 1024 * 1024):
            raise InstalledPilotRefused("UNSAFE_STATE_FILE")
        identity = (st.st_dev, st.st_ino)
        if identity in identities:
            raise InstalledPilotRefused("SHARED_SQLITE_FILE_ROLE")
        identities.add(identity)
        files[basename] = child
    return files


def _read_jobs(path: Path) -> list[tuple[str, str]]:
    """Read a second process' recorded jobs without initializing a ledger."""
    address = "file:" + quote(str(path), safe="/") + "?mode=ro"
    db = sqlite3.connect(address, uri=True, isolation_level=None, timeout=2)
    try:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        if db.execute("PRAGMA quick_check(1)").fetchone()[0] != "ok":
            raise InstalledPilotRefused("RUNTIME_SQLITE_INTEGRITY_FAILED")
        jobs = db.execute(
            "SELECT job_id,status FROM runtime17_jobs ORDER BY job_id LIMIT 3"
        ).fetchall()
    finally:
        db.close()
    if len(jobs) != 2 or len({r[0] for r in jobs}) != 2:
        raise InstalledPilotRefused("TWO_UNIQUE_RUNTIME_JOBS_REQUIRED")
    return jobs


def inspect_installed_paper(
    directory: Path, *, expected_dry_signals: bool,
    operator_ack: bool = False, all_writers_stopped: bool = False,
) -> dict:
    """No DB writes or restart attempt; operator asserts stop-and-snapshot custody."""
    _gate(ack=operator_ack, installed=False)
    if type(expected_dry_signals) is not bool or all_writers_stopped is not True:
        raise InstalledPilotRefused("WRITER_STOP_AND_MODE_ACK_REQUIRED")
    paths = _existing_state(directory)
    jobs = _read_jobs(paths["runtime.sqlite"])
    if any(status != "DONE" for _, status in jobs):
        raise InstalledPilotRefused("JOB_NOT_DONE_REQUIRES_MANUAL_RECOVERY")
    gate = evaluate_offline_reliability(LedgerPaths(
        paths["control.sqlite"], paths["paper.sqlite"],
        paths["signals.sqlite"],
    ))
    if (gate.integrity_verdict != "PASS"
            or gate.release_verdict != "BLOCKED_NONPRODUCTION_UNATTESTED"):
        raise InstalledPilotRefused("REOPEN_INTEGRITY_GATE_BLOCKED")
    expected = (_EXPECTED_SIGNAL_KINDS if expected_dry_signals
                else _EXPECTED_PAPER_KINDS)
    evidence = evaluate_recovery_decisions(
        EffectEvidencePaths(
            paths["effects.sqlite"], paths["runtime.sqlite"],
            paths["paper.sqlite"], paths["signals.sqlite"],
        ),
        expected_effect_kinds_by_job={job_id: expected for job_id, _ in jobs},
        operator_ack=True, all_writers_stopped=True,
    )
    if (evidence.operator_review_required or evidence.blocking_decisions
            or any(d.classification != "EXACT_TARGET_AND_RECEIPT"
                   for d in evidence.decisions)
            or len(evidence.decisions) != 2 * len(expected)):
        raise InstalledPilotRefused("EFFECT_RECONCILIATION_BLOCKED")
    counts = gate.counts
    if (counts["control_instances"] != 1
            or counts["control_bindings"] != 2
            or counts["paper_orders"] != 2
            or counts["paper_plans"] != 2
            or counts["cross_stage_bindings"] != 2
            or counts["paper_exits"] < 2
            or counts["signal_states"] != (2 if expected_dry_signals else 0)
            or counts["signal_commands"] != (2 if expected_dry_signals else 0)):
        raise InstalledPilotRefused("INCOMPLETE_PAPER_JOURNEY_EVIDENCE")
    return {
        "mode": "INSTALLED_TWO_BINDING_SYNTHETIC_PAPER_REOPEN_ONLY",
        "schema_version": 1,
        "runtime_jobs_done": 2,
        "paper_orders": 2,
        "paper_plans": 2,
        "paper_exits": counts["paper_exits"],
        "dry_signal_commands": counts["signal_commands"],
        "exact_initial_effects": len(evidence.decisions),
        "reliability_sha256": gate.evidence_digest,
        "recovery_decision_sha256": evidence.decision_sha256,
        "integrity_verdict": gate.integrity_verdict,
        "release_verdict": gate.release_verdict,
        "source_authenticated": False,
        "real_feed_used": False,
        "profitability_proven": False,
        "live_trading_enabled": False,
        "broker_order_sent": False,
        "telegram_sent": False,
        "public_release_authorized": False,
        "automatic_recovery_authorized": False,
        "exactly_once_guaranteed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--run", action="store_true")
    choice.add_argument("--inspect", action="store_true")
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--first-symbol", default="ABCUSD")
    parser.add_argument("--second-symbol", default="XYZUSD")
    parser.add_argument("--first-timeframe", default="5m")
    parser.add_argument("--second-timeframe", default="15m")
    parser.add_argument("--no-dry-run-signals", action="store_true")
    parser.add_argument("--ack-synthetic-offline", action="store_true")
    parser.add_argument("--ack-writers-stopped", action="store_true")
    args = parser.parse_args(argv)
    try:
        _gate(ack=args.ack_synthetic_offline)
        if args.run:
            if args.ack_writers_stopped:
                raise InstalledPilotRefused("RUN_MODE_CANNOT_ASSUME_STOPPED_WRITERS")
            output = run_paper_pilot(
                args.state_dir, first_symbol=args.first_symbol,
                second_symbol=args.second_symbol,
                first_timeframe=args.first_timeframe,
                second_timeframe=args.second_timeframe,
                dry_run_signals=not args.no_dry_run_signals,
            )
        else:
            if (not args.ack_writers_stopped
                    or (args.first_symbol, args.second_symbol,
                        args.first_timeframe, args.second_timeframe)
                    != ("ABCUSD", "XYZUSD", "5m", "15m")):
                raise InstalledPilotRefused("INSPECT_PREDECLARED_MODE_REQUIRED")
            output = inspect_installed_paper(
                args.state_dir,
                expected_dry_signals=not args.no_dry_run_signals,
                operator_ack=True, all_writers_stopped=True,
            )
    except (OSError, ValueError, RuntimeError, sqlite3.DatabaseError, KeyError):
        print("STAGE10_INSTALLED_PAPER_REFUSED", file=sys.stderr)
        return 2
    print(json.dumps(output, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
