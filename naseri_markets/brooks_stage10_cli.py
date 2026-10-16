"""Explicit operator-only Stage-10 local Brooks -> Stage-3 PAPER risk link.

This CLI NEVER connects to a broker or Telegram, runs Brooks analysis,
injects a synthetic fill, or provisions risk policies. Use a separately
preconfigured offline Stage-3 risk account and a committed Brooks receipt.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path

from .brooks_replay import MAX_REPLAY_BYTES, replay_once
from .brooks_stage10_paper_bridge import (
    BrooksStage10PaperBridge,
    BrooksStage10Refused,
    panel_stage10_overview,
)


def _replay_and_link(args: argparse.Namespace) -> dict:
    """Opt-in verified frozen V5 analysis -> already configured Stage10 risk.

    NO_SIGNAL is recorded as a scan, never turned into a fictitious intent.
    The source and PAPER SQLite transactions are separate; a crash or
    rejection must be reconciled by the operator, not silently retried.
    """
    if (not args.ack_real_brooks_offline or not args.replay_file
            or not args.legacy_source):
        raise BrooksStage10Refused("P07_EXPLICIT_FROZEN_REPLAY_ACK_REQUIRED")
    if os.geteuid() == 0:
        raise BrooksStage10Refused("P07_UNPRIVILEGED_REPLAY_REQUIRED")
    replay_path = Path(args.replay_file).absolute()
    if replay_path.is_symlink() or not replay_path.is_file():
        raise BrooksStage10Refused("P07_REPLAY_FILE_REGULAR_REQUIRED")
    info = replay_path.stat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or info.st_size <= 0 or info.st_size > MAX_REPLAY_BYTES):
        raise BrooksStage10Refused("P07_REPLAY_FILE_BOUNDS_OR_LINK_REFUSED")
    # Local offline source only; replay_once independently SHA-pins all
    # historical engine sources and validates every finalized OHLCV bar.
    with replay_path.open("rb") as source:
        payload = source.read(MAX_REPLAY_BYTES + 1)
    if not payload or len(payload) > MAX_REPLAY_BYTES:
        raise BrooksStage10Refused("P07_REPLAY_FILE_BOUNDS_OR_LINK_REFUSED")
    scan = replay_once(
        state_dir=args.state_dir, legacy_source=Path(args.legacy_source),
        replay_json=payload,
    )
    signal_id = scan["signal_id"]
    result = {
        "mode": "PINNED_BROOKS_OFFLINE_TO_STAGE10_PAPER",
        "engine_decision": scan["decision"],
        "scan_id": scan["scan_id"],
        "scan_outcome": scan["outcome"],
        "signal_id": signal_id,
        "paper_order_created": False,
        "paper": None,
        "broker_order_sent": False,
        "telegram_sent": False,
        "real_market_feed_used": False,
        "stage20_core_integrated": False,
        "public_release_authorized": False,
        "live_orders_authorized": False,
    }
    if signal_id is not None:
        paper = BrooksStage10PaperBridge(args.state_dir).link(
            signal_id=signal_id, account_id=args.account_id,
            quantity=args.quantity, ack_paper_risk=True,
        )
        result["paper"] = paper
        result["paper_order_created"] = paper["status"] == "PAPER_ORDER_CREATED"
    return result


def run_once(args: argparse.Namespace, *, environment: dict[str, str]) -> dict:
    if args.status:
        return panel_stage10_overview(args.state_dir)
    if (
        not args.ack_nonproduction_stage10_paper
        or environment.get("MMT_NONPRODUCTION") != "1"
        or environment.get("MMT_PRODUCTION") == "1"
    ):
        raise BrooksStage10Refused("STAGE10_OPERATOR_NONPRODUCTION_OPTIN_REQUIRED")
    if getattr(args, "replay_and_link", False):
        if not args.account_id or not args.quantity:
            raise BrooksStage10Refused("P07_ACCOUNT_AND_EXPLICIT_QUANTITY_REQUIRED")
        return _replay_and_link(args)
    if not args.signal_id or not args.account_id or not args.quantity:
        raise BrooksStage10Refused("STAGE10_SIGNAL_ACCOUNT_QUANTITY_REQUIRED")
    return BrooksStage10PaperBridge(args.state_dir).link(
        signal_id=args.signal_id, account_id=args.account_id,
        quantity=args.quantity, ack_paper_risk=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    ops = parser.add_mutually_exclusive_group(required=True)
    ops.add_argument("--status", action="store_true")
    ops.add_argument("--link", action="store_true")
    ops.add_argument("--replay-and-link", action="store_true")
    parser.add_argument("--replay-file", type=Path)
    parser.add_argument("--legacy-source", type=Path)
    parser.add_argument("--ack-real-brooks-offline", action="store_true")
    parser.add_argument("--signal-id")
    parser.add_argument("--account-id")
    parser.add_argument("--quantity")
    parser.add_argument("--ack-nonproduction-stage10-paper", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run_once(args, environment=dict(os.environ))
    except (BrooksStage10Refused, ValueError, OSError) as exc:
        # No broker credentials, Telegram IDs, source payload or account
        # position details are included in the one-line error code.
        print("STAGE10_PAPER_LINK_REFUSED:" + type(exc).__name__, file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
