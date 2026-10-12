"""Manual Stage21C ARM -> (later) SEAL -> (separately) PAPER REPLAY.

All actions require explicit acknowledgment. In particular SEAL cannot run
before the two bounded, aligned windows are fully closed. No polling daemon.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from .kucoin_futures_replay_stage21_v1 import FuturesKlineRequest
from .public_forward_capture_stage21c_v1 import (
    arm_forward_capture, replay_sealed_bundle, seal_forward_capture,
)


def _date(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("ISO_DATETIME_REQUIRED") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise argparse.ArgumentTypeError("UTC_OFFSET_REQUIRED")
    return result.astimezone(UTC)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    arm = sub.add_parser("arm", help="One public metadata GET; arm before bars")
    arm.add_argument("--bundle-dir", type=Path, required=True)
    arm.add_argument("--first-symbol", required=True)
    arm.add_argument("--second-symbol", required=True)
    arm.add_argument("--ack-public-readonly-get", action="store_true")
    seal = sub.add_parser("seal", help="Two closed-candle public GETs, later")
    seal.add_argument("--bundle-dir", type=Path, required=True)
    for prefix in ("first", "second"):
        seal.add_argument("--" + prefix + "-symbol", required=True)
        seal.add_argument("--" + prefix + "-timeframe", required=True)
        seal.add_argument("--" + prefix + "-start", type=_date, required=True)
        seal.add_argument("--" + prefix + "-end", type=_date, required=True)
    seal.add_argument("--ack-public-readonly-get", action="store_true")
    replay = sub.add_parser("replay", help="No-network modeled PAPER; toy economics")
    replay.add_argument("--bundle-dir", type=Path, required=True)
    replay.add_argument("--state-dir", type=Path, required=True)
    replay.add_argument("--dry-run-signals", action="store_true")
    replay.add_argument("--contracts", type=str, default="1",
                        help="Exact number of futures contracts, never base-asset units")
    replay.add_argument("--ack-offline-paper", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.operation == "arm":
            result = arm_forward_capture(
                args.bundle_dir, symbols=(args.first_symbol, args.second_symbol),
                operator_ack=args.ack_public_readonly_get)
        elif args.operation == "seal":
            requests = tuple(FuturesKlineRequest(
                getattr(args, prefix + "_symbol"),
                getattr(args, prefix + "_timeframe"),
                getattr(args, prefix + "_start"),
                getattr(args, prefix + "_end"))
                for prefix in ("first", "second"))
            result = seal_forward_capture(
                args.bundle_dir, requests=requests,
                operator_ack=args.ack_public_readonly_get)
        else:
            result = replay_sealed_bundle(
                args.bundle_dir, args.state_dir,
                operator_ack=args.ack_offline_paper,
                dry_run_signals=args.dry_run_signals,
                contract_quantity=Decimal(args.contracts))
    except (ValueError, OSError, RuntimeError, KeyError, TypeError):
        print("STAGE21C_NONPRODUCTION_REFUSED", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
