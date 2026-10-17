"""R39: durable operator-driven synthetic PAPER journey authority.

Only the existing Stage20 public fixture and Stage10 read-only checker run.
The SQLite authority records intent before any downstream PAPER side effect.
Crash/unknown outcomes remain unresolved, never automatically replayed.
No real feeds, public strategy execution, services, Telegram or broker orders.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import stat
import sys
from contextlib import closing
from pathlib import Path
from urllib.parse import quote

from .installed_paper_pilot_stage10_v1 import inspect_installed_paper
from .unified_paper_pilot_stage20_v1 import run_paper_pilot

_AUTHORITY = "authority.sqlite"
_FIXTURE_ID = "r39_trusted_two_binding_fixture_v1"
_MAX_DB = 2_000_000


class PaperAuthorityRefused(ValueError):
    """A constant non-sensitive refusal that never implies safe retry."""


def _canonical(value: object) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True, allow_nan=False)


def _hash(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _gate(*, operator_ack: bool, writers_stopped: bool | None = None) -> None:
    if (operator_ack is not True
            or os.environ.get("MMT_NONPRODUCTION") != "1"
            or "MMT_PRODUCTION" in os.environ
            or sys.version_info[:2] != (3, 12)
            or os.geteuid() == 0):
        raise PaperAuthorityRefused("R39_NONROOT_PY312_NONPRODUCTION_ACK_REQUIRED")
    if writers_stopped is not None and writers_stopped is not True:
        raise PaperAuthorityRefused("R39_ALL_WRITERS_STOPPED_ACK_REQUIRED")


def _workspace(path: Path, *, must_exist: bool) -> None:
    if (not isinstance(path, Path) or not path.is_absolute()
            or path.name in ("", ".", "..")
            or path.parent.is_symlink() or not path.parent.is_dir()
            or path.parent.resolve(strict=True) != path.parent
            or path.parent.stat().st_uid != os.geteuid()
            or stat.S_IMODE(path.parent.stat().st_mode) != 0o700):
        raise PaperAuthorityRefused("R39_PRIVATE_OWNER_PARENT_REQUIRED")
    if must_exist:
        if (path.is_symlink() or not path.is_dir()
                or path.resolve(strict=True) != path
                or path.stat().st_uid != os.geteuid()
                or stat.S_IMODE(path.stat().st_mode) != 0o700):
            raise PaperAuthorityRefused("R39_PRIVATE_WORKSPACE_REQUIRED")
    elif path.exists() or path.is_symlink():
        raise PaperAuthorityRefused("R39_NEW_EXCLUSIVE_WORKSPACE_REQUIRED")


def _db_path(path: Path) -> Path:
    file = path / _AUTHORITY
    if file.is_symlink() or not file.is_file():
        raise PaperAuthorityRefused("R39_AUTHORITY_DATABASE_MISSING")
    info = file.stat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or not 128 <= info.st_size <= _MAX_DB):
        raise PaperAuthorityRefused("R39_AUTHORITY_DATABASE_UNSAFE")
    return file


def _receipt(*, dry_run_signals: bool) -> dict:
    return {
        "fixture": _FIXTURE_ID,
        "first_symbol": "BTCUSD",
        "second_symbol": "ETHUSD",
        "first_timeframe": "5m",
        "second_timeframe": "15m",
        "dry_run_signals": dry_run_signals,
    }


def _read_state(path: Path) -> dict:
    _workspace(path, must_exist=True)
    file = _db_path(path)
    # Immutable read-only SQLite is safe only after the operator declares
    # all writers stopped; R39 owns this journal and never enables WAL.
    address = "file:" + quote(str(file), safe="/") + "?mode=ro&immutable=1"
    try:
        with closing(sqlite3.connect(address, uri=True, timeout=1)) as db:
            db.execute("PRAGMA query_only=ON")
            db.execute("BEGIN")
            if db.execute("PRAGMA quick_check(1)").fetchone()[0] != "ok":
                raise PaperAuthorityRefused("R39_AUTHORITY_INTEGRITY_FAILED")
            rows = db.execute(
                "SELECT fixture_id,request_sha256,status,report_json,report_sha256 "
                "FROM r39_journeys LIMIT 2"
            ).fetchall()
    except sqlite3.DatabaseError as exc:
        raise PaperAuthorityRefused("R39_AUTHORITY_DATABASE_REFUSED") from exc
    if len(rows) != 1 or rows[0][0] != _FIXTURE_ID:
        raise PaperAuthorityRefused("R39_SINGLE_AUTHORITATIVE_FIXTURE_REQUIRED")
    return dict(zip(
        ("fixture_id", "request_sha256", "status", "report_json", "report_sha256"),
        rows[0],
        strict=True,
    ))


def _verify_outputs(report: dict, *, dry_run_signals: bool, directory: Path) -> dict:
    if (type(report) is not dict
            or report.get("mode") != "STAGE20_SYNTHETIC_PAPER_ONLY"
            or report.get("core") != "fixture.contract.check"
            or report.get("completed_jobs") != 2
            or report.get("closed_paper_trades") != 2
            or report.get("dry_run_commands") != (2 if dry_run_signals else 0)
            or report.get("exact_effects") != (6 if dry_run_signals else 4)
            or report.get("restart_verified") is not True
            or report.get("integrity_verdict") != "PASS"
            or report.get("release_verdict") != "BLOCKED_NONPRODUCTION_UNATTESTED"
            or any(report.get(flag) is not False for flag in (
                "telegram_sent", "broker_order_sent", "real_feed_used",
                "live_trading_enabled", "profitability_proven",
                "public_release_authorized", "brooks_core_api_integrated",
            ))):
        raise PaperAuthorityRefused("R39_STAGE20_REPORT_UNSAFE")
    if (type(report.get("bindings")) is not list
            or len(report["bindings"]) != 2
            or any(type(x) is not dict for x in report["bindings"])
            or {x.get("symbol") for x in report["bindings"]} != {"BTCUSD", "ETHUSD"}
            or any(x.get("status") != "CLOSED" for x in report["bindings"])
            or {(x.get("symbol"), x.get("timeframe"))
                for x in report["bindings"]} != {("BTCUSD", "5m"), ("ETHUSD", "15m")}
            or any(type(x.get("binding_id")) is not str or not x["binding_id"]
                   or type(x.get("order_id")) is not str or not x["order_id"]
                   for x in report["bindings"])
            or len({x["binding_id"] for x in report["bindings"]}) != 2
            or len({x["order_id"] for x in report["bindings"]}) != 2):
        raise PaperAuthorityRefused("R39_TWO_COMPLETE_BINDINGS_REQUIRED")
    reopen = inspect_installed_paper(
        directory, expected_dry_signals=dry_run_signals,
        operator_ack=True, all_writers_stopped=True,
    )
    if (reopen.get("runtime_jobs_done") != 2
            or reopen.get("paper_orders") != 2
            or reopen.get("paper_plans") != 2
            or reopen.get("paper_exits", 0) < 2
            or reopen.get("dry_signal_commands") != (2 if dry_run_signals else 0)
            or reopen.get("exact_initial_effects") != (6 if dry_run_signals else 4)
            or reopen.get("integrity_verdict") != "PASS"
            or reopen.get("release_verdict") != "BLOCKED_NONPRODUCTION_UNATTESTED"
            or any(reopen.get(flag) is not False for flag in (
                "source_authenticated", "live_trading_enabled",
                "broker_order_sent", "telegram_sent", "profitability_proven",
                "public_release_authorized", "automatic_recovery_authorized",
                "exactly_once_guaranteed",
            ))):
        raise PaperAuthorityRefused("R39_REOPEN_EVIDENCE_UNSAFE")
    return {
        "stage20_report_sha256": _hash(report),
        "reliability_sha256": reopen["reliability_sha256"],
        "recovery_decision_sha256": reopen["recovery_decision_sha256"],
        "dry_run_signals": dry_run_signals,
    }


def run_new(path: Path, *, dry_run_signals: bool = True,
            operator_ack: bool = False) -> dict:
    """A single *new* non-root fixture journal. NEVER resumes a prior job."""
    _gate(operator_ack=operator_ack)
    if type(dry_run_signals) is not bool:
        raise PaperAuthorityRefused("R39_INVALID_DRY_RUN_MODE")
    _workspace(path, must_exist=False)
    path.mkdir(mode=0o700)
    location = path / _AUTHORITY
    fd = os.open(
        location, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600,
    )
    os.close(fd)
    request_sha = _hash(_receipt(dry_run_signals=dry_run_signals))
    with closing(sqlite3.connect(str(location), isolation_level=None, timeout=2)) as db:
        db.execute("PRAGMA journal_mode=DELETE")
        db.execute("PRAGMA synchronous=FULL")
        db.execute(
            "CREATE TABLE r39_journeys("
            "fixture_id TEXT PRIMARY KEY, request_sha256 TEXT NOT NULL,"
            "status TEXT NOT NULL CHECK(status IN ('PENDING','DONE','QUARANTINED')),"
            "report_json TEXT, report_sha256 TEXT)"
        )
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "INSERT INTO r39_journeys VALUES(?,?,'PENDING',NULL,NULL)",
            (_FIXTURE_ID, request_sha),
        )
        db.execute("COMMIT")
        try:
            report = run_paper_pilot(
                path / "pilot", first_symbol="BTCUSD", second_symbol="ETHUSD",
                first_timeframe="5m", second_timeframe="15m",
                dry_run_signals=dry_run_signals,
            )
            evidence = _verify_outputs(
                report, dry_run_signals=dry_run_signals,
                directory=path / "pilot",
            )
        except Exception:
            # No recovery or retry: downstream ledgers might already be committed.
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "UPDATE r39_journeys SET status='QUARANTINED' "
                "WHERE fixture_id=? AND status='PENDING'", (_FIXTURE_ID,),
            )
            db.execute("COMMIT")
            raise PaperAuthorityRefused("R39_MANUAL_RECONCILIATION_REQUIRED") from None
        receipt = {"report": report, "evidence": evidence}
        encoded = _canonical(receipt)
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "UPDATE r39_journeys SET status='DONE',report_json=?,report_sha256=? "
            "WHERE fixture_id=? AND request_sha256=? AND status='PENDING'",
            (encoded, _hash(receipt), _FIXTURE_ID, request_sha),
        )
        if db.execute("SELECT changes()").fetchone()[0] != 1:
            db.execute("ROLLBACK")
            raise PaperAuthorityRefused("R39_AUTHORITY_COMMIT_CONFLICT")
        db.execute("COMMIT")
    return {
        "verdict": "R39_DURABLE_SYNTHETIC_PAPER_PASS_RELEASE_DENIED",
        "fixture": _FIXTURE_ID, "status": "DONE",
        "report_sha256": _hash(receipt),
        "reliability_sha256": evidence["reliability_sha256"],
        "recovery_decision_sha256": evidence["recovery_decision_sha256"],
        "replay_authorized": False, "real_feed_used": False,
        "broker_order_sent": False, "telegram_sent": False,
        "live_authorized": False, "public_release_authorized": False,
    }


def inspect(path: Path, *, dry_run_signals: bool, operator_ack: bool = False,
            all_writers_stopped: bool = False) -> dict:
    """Read-only reopen, never a license to resume/replay incomplete work."""
    _gate(operator_ack=operator_ack, writers_stopped=all_writers_stopped)
    if type(dry_run_signals) is not bool:
        raise PaperAuthorityRefused("R39_INVALID_DRY_RUN_MODE")
    row = _read_state(path)
    if row["request_sha256"] != _hash(_receipt(dry_run_signals=dry_run_signals)):
        raise PaperAuthorityRefused("R39_IMMUTABLE_REQUEST_MISMATCH")
    if row["status"] != "DONE" or row["report_json"] is None:
        raise PaperAuthorityRefused("R39_UNCERTAIN_JOB_MANUAL_RECOVERY_ONLY")
    try:
        data = json.loads(row["report_json"])
    except (ValueError, TypeError) as exc:
        raise PaperAuthorityRefused("R39_REPORT_CORRUPT") from exc
    if (type(data) is not dict or set(data) != {"report", "evidence"}
            or _canonical(data) != row["report_json"]
            or _hash(data) != row["report_sha256"]):
        raise PaperAuthorityRefused("R39_RECORDED_REPORT_DRIFT")
    evidence = _verify_outputs(
        data["report"], dry_run_signals=dry_run_signals, directory=path / "pilot",
    )
    if evidence != data["evidence"]:
        raise PaperAuthorityRefused("R39_REOPEN_EVIDENCE_DRIFT")
    return {
        "verdict": "R39_READONLY_PAPER_REOPEN_PASS_RELEASE_DENIED",
        "status": "DONE", "fixture": _FIXTURE_ID,
        "report_sha256": row["report_sha256"],
        "reliability_sha256": evidence["reliability_sha256"],
        "recovery_decision_sha256": evidence["recovery_decision_sha256"],
        "files_written": False, "auto_retry_authorized": False,
        "live_authorized": False, "public_release_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run-new", action="store_true")
    mode.add_argument("--inspect", action="store_true")
    parser.add_argument("--without-dry-signals", action="store_true")
    parser.add_argument("--ack-synthetic-offline", action="store_true")
    parser.add_argument("--ack-writers-stopped", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.run_new and args.ack_writers_stopped:
            raise PaperAuthorityRefused("R39_RUN_CANNOT_ACK_STOPPED_WRITERS")
        if args.run_new:
            result = run_new(
                args.workspace, dry_run_signals=not args.without_dry_signals,
                operator_ack=args.ack_synthetic_offline,
            )
        else:
            result = inspect(
                args.workspace, dry_run_signals=not args.without_dry_signals,
                operator_ack=args.ack_synthetic_offline,
                all_writers_stopped=args.ack_writers_stopped,
            )
    except (PaperAuthorityRefused, OSError, sqlite3.DatabaseError, ValueError):
        print("R39_PAPER_AUTHORITY_REFUSED", file=sys.stderr)
        return 2
    print(_canonical(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
