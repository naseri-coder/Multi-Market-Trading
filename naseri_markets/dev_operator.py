"""Single entry point for an ISOLATED DEVELOPMENT product preview.

The preview intentionally does not change the legacy v0.3.2 launcher,
production DB/Compose, enable channel delivery or authorize broker orders.
A worker/Telegram process requires an explicit operator action; the default
status/check path makes no network requests.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

from .engine_control_store import BROOKS_ENGINE_ID, EngineControlStore
from .iran_futures_eligibility import (
    iran_futures_approved, resident_paper_feed_ready,
)
from .trusted_custom import LocalCustomRefused


class DevPreviewRefused(ValueError):
    """Nonproduction permission, state or lifecycle fence rejected request."""


def _require_dev() -> None:
    if (os.environ.get("MMT_NONPRODUCTION") != "1"
            or "MMT_PRODUCTION" in os.environ):
        raise DevPreviewRefused("MMT_ISOLATED_NONPRODUCTION_ONLY")


def _state_dir(folder: Path, *, create: bool = False) -> Path:
    root = folder.absolute()
    if root.is_symlink():
        raise DevPreviewRefused("DEV_STATE_SYMLINK_DENIED")
    if create and not root.exists():
        if not root.parent.is_dir() or root.parent.is_symlink():
            raise DevPreviewRefused("DEV_STATE_PARENT_UNSAFE")
        root.mkdir(mode=0o700)
    if not root.is_dir() or root.is_symlink():
        raise DevPreviewRefused("DEV_STATE_NOT_INITIALIZED")
    metadata = root.stat()
    if (not stat.S_ISDIR(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o700
            or metadata.st_uid != os.geteuid()):
        raise DevPreviewRefused("DEV_STATE_OWNER_OR_PERMISSIONS_UNSAFE")
    return root


def _admin_args(admins: str, owners: str) -> None:
    def parse(value: str) -> set[int]:
        if not value:
            return set()
        parts = value.split(",")
        if not all(part.isascii() and part.isdecimal()
                   and str(int(part)) == part and int(part) > 0
                   for part in parts):
            raise DevPreviewRefused("DEV_ADMIN_IDS_INVALID")
        return {int(part) for part in parts}
    admin_ids, owner_ids = parse(admins), parse(owners)
    if not admin_ids or not owner_ids.issubset(admin_ids):
        raise DevPreviewRefused("DEV_ADMIN_IDS_INVALID")


def _panel_env() -> None:
    _require_dev()
    token = os.environ.get("MMT_DEV_BOT_TOKEN", "")
    if (not token or not 15 <= len(token) <= 250
            or not token.split(":", 1)[0].isascii()
            or not token.split(":", 1)[0].isdigit()
            or any(c in token for c in "\r\n")):
        raise DevPreviewRefused("DEV_EXPLICIT_TEST_BOT_TOKEN_REQUIRED")


def _source(path: Path) -> Path:
    from .brooks_replay import verify_legacy_source
    root = path.absolute()
    if not root.is_dir() or root.is_symlink():
        raise DevPreviewRefused("DEV_PINNED_SOURCE_REQUIRED")
    verify_legacy_source(root)
    return root


def _status(state: Path) -> dict:
    with EngineControlStore(state) as host:
        engine = host.get(BROOKS_ENGINE_ID)
        prefs = host.preferences(BROOKS_ENGINE_ID)
        worker = host.brooks_worker_status()
        approved = iran_futures_approved(prefs["futures_exchange"])
        ready = resident_paper_feed_ready(
            prefs["futures_exchange"], prefs["futures_symbol"])
        return {
            "product": "Multi Market Trading",
            "mode": "ISOLATED_DEVELOPMENT_ONLY",
            "engine_id": BROOKS_ENGINE_ID,
            "operator_enabled_request": engine.requested_enabled,
            "signal_environment": prefs["signal_environment"],
            "exchange": prefs["futures_exchange"],
            "pair": prefs["futures_symbol"],
            "timeframe": prefs["timeframe"],
            "iran_futures_eligibility_verified": approved,
            "selected_feed_eligible": ready,
            "worker_phase": worker["phase"],
            "worker_connected": worker["connected"],
            "last_closed_candle": worker["last_closed_candle"],
            "completed_cycles": worker["completed_cycles"],
            "refused_cycles": worker["refused_cycles"],
            "last_error": worker["last_error"],
            "paper_signal_count": host.brooks_replay_status()["paper_signals"],
            "paper_receipt_count": host.brooks_replay_status()["receipts"],
            "most_recent_receipt": (
                host.brooks_paper_receipts(limit=1)[0]
                if host.brooks_replay_status()["receipts"] else None),
            "effective_channel_publication": host.publication(
                BROOKS_ENGINE_ID)["effective_publication"],
            "legacy_database_attached": False,
            "real_orders_enabled": False,
            "telegram_connected_by_status": False,
        }


def _run_pair(state: Path, source: Path, admins: str, owners: str) -> int:
    """Explicit foreground-only supervisor, signal-safe stop for both peers."""
    _panel_env()
    _admin_args(admins, owners)
    source = _source(source)
    base = [sys.executable, "-m", "naseri_markets.dev_operator",
            "--state-dir", str(state)]
    worker = base + ["worker", "--legacy-source", str(source),
                     "--ack-nonproduction-worker"]
    panel = base + ["panel", "--admin-ids", admins,
                    "--owner-ids", owners, "--ack-nonproduction-panel"]
    processes: list[subprocess.Popen] = []
    stopped = False
    prior = {}

    def stop(_sig, _frame):
        nonlocal stopped
        stopped = True

    try:
        # Foreground ownership: never daemonize, write a unit or persist token.
        for signum in (signal.SIGTERM, signal.SIGINT):
            prior[signum] = signal.getsignal(signum)
            signal.signal(signum, stop)
        processes.append(subprocess.Popen(worker))
        processes.append(subprocess.Popen(panel))
        print(json.dumps({
            "status": "DEV_FOREGROUND_SUPERVISOR_STARTED",
            "telegram_delivery_enabled": False,
            "broker_orders_enabled": False,
        }, sort_keys=True), flush=True)
        while not stopped:
            if any(proc.poll() is not None for proc in processes):
                break
            time.sleep(0.25)
        return 0 if stopped else 2
    finally:
        # Terminate and reap BOTH children on panel auth failure, worker
        # failure, SIGINT or SIGTERM. Never leave a hidden background service.
        for proc in processes:
            if proc.poll() is None:
                proc.terminate()
        for proc in processes:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        for signum, handler in prior.items():
            signal.signal(signum, handler)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    actions = parser.add_subparsers(dest="command", required=True)
    initialize = actions.add_parser("init", help="Initialize private isolated PAPER state")
    initialize.add_argument("--ack-nonproduction-init", action="store_true")
    actions.add_parser("status", help="Local health inspection; no Telegram/HTTPS")
    actions.add_parser("venues", help="Offline non-executable operator research priority")
    receipts = actions.add_parser(
        "receipts", help="Local immutable PAPER scan and risk receipts, no network")
    receipts.add_argument("--limit", type=int, default=8)
    contracts = actions.add_parser(
        "contracts", help="Official futures instrument metadata; READ-ONLY research")
    contracts.add_argument("--venue", required=True, choices=("kraken", "kucoin"))
    contracts.add_argument("--max-results", type=int, default=100)
    contracts.add_argument("--ack-public-metadata-research", action="store_true")
    panel = actions.add_parser("panel", help="Explicit foreground development bot")
    panel.add_argument("--admin-ids", required=True)
    panel.add_argument("--owner-ids", default="")
    panel.add_argument("--ack-nonproduction-panel", action="store_true")
    worker = actions.add_parser("worker", help="Explicit standalone PAPER worker")
    worker.add_argument("--legacy-source", type=Path, required=True)
    worker.add_argument("--max-steps", type=int, default=0)
    worker.add_argument("--ack-nonproduction-worker", action="store_true")
    suite = actions.add_parser("run", help="Foreground panel and worker, shared state")
    suite.add_argument("--admin-ids", required=True)
    suite.add_argument("--owner-ids", default="")
    suite.add_argument("--legacy-source", type=Path, required=True)
    suite.add_argument("--ack-nonproduction-suite", action="store_true")
    args = parser.parse_args(argv)
    try:
        _require_dev()
        if args.command == "init":
            if not args.ack_nonproduction_init:
                raise DevPreviewRefused("DEV_INIT_ACK_REQUIRED")
            state = _state_dir(args.state_dir, create=True)
            print(json.dumps({
                "status": "ISOLATED_NONPRODUCTION_STATE_INITIALIZED",
                **_status(state),
            }, sort_keys=True))
            return 0
        state = _state_dir(args.state_dir)
        if args.command == "status":
            print(json.dumps(_status(state), sort_keys=True))
            return 0
        if args.command == "venues":
            from .futures_research_priority import (
                RANKING_BASIS, RESEARCHED_AT, operator_futures_research,
            )
            print(json.dumps({
                "mode": "OFFLINE_RESEARCH_ONLY",
                "ranking_basis": RANKING_BASIS,
                "researched_at": RESEARCHED_AT,
                "venues": operator_futures_research(),
                "resident_futures_access_granted": False,
                "signal_delivery_enabled": False,
                "orders_enabled": False,
            }, sort_keys=True))
            return 0
        if args.command == "receipts":
            with EngineControlStore(state) as host:
                data = host.brooks_paper_receipts(limit=args.limit)
            print(json.dumps({"mode": "OFFLINE_PAPER_AUDIT_ONLY",
                              "receipts": data, "telegram_sent": False,
                              "orders_placed": False}, sort_keys=True))
            return 0
        if args.command == "contracts":
            if not args.ack_public_metadata_research:
                raise DevPreviewRefused("DEV_PUBLIC_RESEARCH_ACK_REQUIRED")
            from .public_futures_contracts import discover_public_contracts
            print(json.dumps(discover_public_contracts(
                args.venue, max_results=args.max_results), sort_keys=True))
            return 0
        if args.command == "panel":
            if not args.ack_nonproduction_panel:
                raise DevPreviewRefused("DEV_PANEL_ACK_REQUIRED")
            _panel_env()
            _admin_args(args.admin_ids, args.owner_ids)
            from .bot_admin_app import main as admin_main
            return admin_main([
                "--state-dir", str(state), "--nonproduction-poll",
                "--admin-ids", args.admin_ids, "--owner-ids", args.owner_ids])
        if args.command == "worker":
            if not args.ack_nonproduction_worker or args.max_steps < 0:
                raise DevPreviewRefused("DEV_WORKER_ACK_REQUIRED")
            src = _source(args.legacy_source)
            from .brooks_paper_service import main as worker_main
            return worker_main([
                "--state-dir", str(state),
                "--legacy-source", str(src),
                "--max-steps", str(args.max_steps),
                "--ack-nonproduction-standalone-paper"])
        if not args.ack_nonproduction_suite:
            raise DevPreviewRefused("DEV_SUPERVISOR_ACK_REQUIRED")
        return _run_pair(state, args.legacy_source, args.admin_ids, args.owner_ids)
    except (DevPreviewRefused, LocalCustomRefused, ValueError, OSError) as exc:
        print("MMT_DEV_REFUSED:" + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
