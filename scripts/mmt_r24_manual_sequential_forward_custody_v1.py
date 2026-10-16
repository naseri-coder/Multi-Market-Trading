#!/usr/bin/env python3
"""R24 manually continue an unbroken chain of actual 15m source observations.

No cron, accounts, Telegram, strategy execution, PAPER or orders. A missing
earlier batch folder blocks the following batch. Syntax deliberately requires
ALL previous batch folders in oldest-to-newest order.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, timedelta
from pathlib import Path

from naseri_markets.brooks_forward_source_custody_stage21g_v1 import (
    _read_original_evidence,
)
from naseri_markets.brooks_sequential_forward_custody_mmt_r24_v1 import (
    run_stage24_manual_next_batch,
    stage24_replay_all_previous_batches,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=("Nonproduction one-time next closed BTCUSDT 15m "
                     "source-custody receipt"),
    )
    result.add_argument("--ack-research-only", action="store_true")
    result.add_argument("--witness-dir", type=Path, required=True)
    result.add_argument(
        "--prior-batch-dir", type=Path, required=True, action="append",
        help="Repeat for EVERY previously accepted batch directory in chronological order",
    )
    commands = result.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("inspect", help="Verify full earlier chain OFFLINE")
    inspect.add_argument("--bars", type=int, choices=(1, 4, 16, 32, 96), default=1)
    capture = commands.add_parser(
        "capture",
        help="ONE public HTTPS GET after candle close; expired window logs only",
    )
    capture.add_argument("--bars", type=int, required=True, choices=(1, 4, 16, 32, 96))
    capture.add_argument("--output-dir", type=Path, required=True)
    capture.add_argument(
        "--confirm-one-readonly-public-get",
        required=True,
        choices=("I_APPROVE_ONE_NEXT_READONLY_BINANCE_GET",),
    )
    return result


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    if (args.ack_research_only is not True
            or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        raise SystemExit("R24_NONPRODUCTION_MANUAL_OPERATOR_APPROVAL_REQUIRED")
    prior = tuple(args.prior_batch_dir)
    if args.command == "inspect":
        from naseri_markets.brooks_forward_source_custody_stage21g_v1 import _now
        witness = _read_original_evidence(args.witness_dir)
        state = stage24_replay_all_previous_batches(
            previous_directories=prior, witness=witness, operator_ack=True,
        )
        closing = state.next_open_utc + timedelta(minutes=15*args.bars)
        now = _now()
        print(json.dumps({
            "protocol": "MMT_R24_OFFLINE_CHAIN_INSPECTION_ONLY_V1",
            "verified_number_of_previous_local_batches": state.accepted_batches,
            "next_requested_first_open_utc": state.next_open_utc.isoformat(),
            "next_requested_last_closed_utc": closing.isoformat(),
            "earliest_manual_start_utc": (closing+timedelta(seconds=5)).isoformat(),
            "latest_admissible_completed_response_utc":
                (closing+timedelta(hours=1)).isoformat(),
            "local_unattested_clock_utc": now.astimezone(UTC).isoformat(),
            "prior_batches_verified_against_original_bytes": True,
            "market_source_independently_authenticated": False,
            "future_fetch_started": False,
            "connected_paper_enabled": False,
            "live_order_authorized": False,
        }, sort_keys=True, indent=2))
        return
    os.environ["MMT_R24_EXPLICIT_ONE_READONLY_GET"] = "1"
    report = run_stage24_manual_next_batch(
        witness_directory=args.witness_dir,
        previous_directories=prior,
        destination=args.output_dir,
        number_of_closed_bars=args.bars,
        operator_ack=True,
    )
    print(json.dumps(report, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
