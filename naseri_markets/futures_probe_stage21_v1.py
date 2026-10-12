"""Opt-in Stage 21 public Futures read-only probe.

Never runs automatically; no private credentials, broker trades or Telegram.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime

from .kucoin_futures_replay_stage21_v1 import (
    FuturesKlineRequest, VenueReplayRefused, observe_public_futures_klines,
)


def _date(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("ISO_UTC_DATE_REQUIRED") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise argparse.ArgumentTypeError("UTC_OFFSET_REQUIRED")
    return result.astimezone(UTC)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframe", choices=(
        "1m", "5m", "15m", "30m", "1h", "4h", "12h", "1d"), required=True)
    parser.add_argument("--start", type=_date, required=True)
    parser.add_argument("--end", type=_date, required=True)
    parser.add_argument("--ack-public-readonly-get", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.ack_public_readonly_get:
            raise VenueReplayRefused("EXPLICIT_NETWORK_CONSENT_REQUIRED")
        query = FuturesKlineRequest(
            args.symbol, args.timeframe, args.start, args.end)
        capture = observe_public_futures_klines(
            query, observed_at=datetime.now(UTC), operator_ack=True)
    except (ValueError, RuntimeError, OSError):
        print("STAGE21_PUBLIC_DATA_REFUSED", file=sys.stderr)
        return 2
    # A hash of public raw bytes is evidence of local identity only.
    report = capture.report()
    report["paper_pilot_executed"] = False
    report["telegram_sent"] = False
    report["broker_order_sent"] = False
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
