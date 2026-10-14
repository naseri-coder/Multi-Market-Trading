"""Operator-invoked DATA-A1 read-only intake of pinned local CSV / Parquet files."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .contracts import Market
from .core_api_v1 import CoreEventType
from .data_a1_file_intake import inspect_historical_for_paper
from .historical_data_loader_a1 import HistoricalDataRefused
from .market_data_engine_v1 import PriceBasis, VolumeSemantics


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument("--sha256", required=True,
                        help="Previously verified 64-character lowercase file SHA256")
    parser.add_argument("--market", choices=[x.value for x in Market], required=True)
    parser.add_argument("--provider", required=True, help="Operator-claimed source label")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timezone", required=True, help="Explicit IANA market timezone")
    parser.add_argument("--quote-currency", required=True)
    parser.add_argument("--timeframe", choices=(
        "1m", "5m", "15m", "30m", "1h", "4h", "12h", "1d",
    ), required=True)
    parser.add_argument("--event", choices=[
        CoreEventType.CLOSED_CANDLE.value, CoreEventType.QUOTE_TICK.value,
    ], required=True)
    parser.add_argument("--price-basis", choices=[x.value for x in PriceBasis],
                        required=True)
    parser.add_argument("--volume-semantics",
                        choices=[x.value for x in VolumeSemantics], required=True)
    parser.add_argument("--availability-lag-seconds", type=int, default=0)
    parser.add_argument("--max-rows", type=int, default=5_000_000)
    parser.add_argument("--ack-offline-paper-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = inspect_historical_for_paper(
            args.file, sha256=args.sha256,
            market=Market(args.market), provider=args.provider,
            symbol=args.symbol, timezone=args.timezone,
            quote_currency=args.quote_currency, timeframe=args.timeframe,
            event=CoreEventType(args.event),
            price_basis=PriceBasis(args.price_basis),
            volume_semantics=VolumeSemantics(args.volume_semantics),
            availability_lag_seconds=args.availability_lag_seconds,
            max_rows=args.max_rows, operator_ack=args.ack_offline_paper_only,
        )
    except (HistoricalDataRefused, ValueError, OSError, RuntimeError):
        # File paths, timestamps, row values, source assertions and parser
        # exceptions must not leak into console audit logs on rejection.
        print("DATA_A1_LOCAL_INTAKE_REFUSED", file=sys.stderr)
        return 2
    details = asdict(report)
    for key, value in details.items():
        if isinstance(value, datetime):
            details[key] = value.isoformat()
    print(json.dumps(details, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
