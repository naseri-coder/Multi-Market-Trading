"""Explicit operator-only Stage-10 local Brooks -> Stage-3 PAPER risk link.

This CLI NEVER connects to a broker or Telegram, runs Brooks analysis,
injects a synthetic fill, or provisions risk policies. Use a separately
preconfigured offline Stage-3 risk account and a committed Brooks receipt.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .brooks_stage10_paper_bridge import (
    BrooksStage10PaperBridge,
    BrooksStage10Refused,
    panel_stage10_overview,
)


def run_once(args: argparse.Namespace, *, environment: dict[str, str]) -> dict:
    if args.status:
        return panel_stage10_overview(args.state_dir)
    if (
        not args.ack_nonproduction_stage10_paper
        or environment.get("MMT_NONPRODUCTION") != "1"
        or environment.get("MMT_PRODUCTION") == "1"
    ):
        raise BrooksStage10Refused("STAGE10_OPERATOR_NONPRODUCTION_OPTIN_REQUIRED")
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
