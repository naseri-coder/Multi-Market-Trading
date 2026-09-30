"""One-shot read-only Phase 8 shadow replay CLI.

Example:
python -m app.modules.shadow_replay.cli \
  --exchange binance --market-type spot --symbol BTCUSDT \
  --timeframe 15m --candles 500 --window 100 \
  --output /tmp/btc-15m-shadow.json
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
from pathlib import Path

from app.modules.brooks_core.fundamentals_engine import (
    BrooksFundamentalsH2L2Engine,
)
from app.modules.brooks_core.fundamentals_policy import (
    FundamentalsExecutionPolicy,
)
from app.modules.shadow_replay.historical import (
    BinanceHistoricalCandleSource,
    BybitHistoricalCandleSource,
)
from app.modules.shadow_replay.json_report import report_to_json
from app.modules.shadow_replay.service import CausalShadowReplayService


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only causal Brooks shadow replay")
    parser.add_argument("--exchange", choices=("binance", "bybit"), required=True)
    parser.add_argument("--market-type", default="spot")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--timeframe", required=True)
    parser.add_argument("--candles", type=int, default=500)
    parser.add_argument("--window", type=int, default=100)
    parser.add_argument(
        "--end-at",
        help="UTC/offset-aware ISO-8601 end time; defaults to current UTC time",
    )
    parser.add_argument("--output", help="optional JSON output path")
    return parser


def _parse_end_at(raw: str | None) -> datetime:
    if raw is None:
        return datetime.now(UTC)
    value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if value.tzinfo is None:
        raise ValueError("--end-at must include timezone or Z")
    return value.astimezone(UTC)


async def _run(args: argparse.Namespace) -> int:
    policy = FundamentalsExecutionPolicy()
    if policy.enable_trade_decisions:
        raise RuntimeError("Phase 8 refuses enabled autonomous trade decisions")

    if args.exchange == "binance":
        source = BinanceHistoricalCandleSource()
    else:
        source = BybitHistoricalCandleSource()

    try:
        candles = await source.get_closed_candles(
            symbol=args.symbol,
            timeframe=args.timeframe,
            limit=args.candles,
            market_type=args.market_type,
            end_at=_parse_end_at(args.end_at),
        )
        service = CausalShadowReplayService(
            engine=BrooksFundamentalsH2L2Engine(policy=policy),
            window_size=args.window,
        )
        report = await service.replay(
            exchange=source.exchange,
            market_type=args.market_type,
            symbol=args.symbol,
            timeframe=args.timeframe,
            candles=candles,
        )
    finally:
        await source.aclose()

    payload = report_to_json(report)
    if args.output:
        Path(args.output).write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)

    metrics = report.metrics
    print(
        "PHASE8_SHADOW_SUMMARY "
        f"evaluated={metrics.evaluated_snapshots} "
        f"h2={metrics.h2_count} "
        f"l2={metrics.l2_count} "
        f"ambiguous={metrics.ambiguous_count} "
        f"blocked={metrics.blocked_count} "
        f"no_signal={metrics.no_signal_count} "
        f"detections_per_1000={metrics.detections_per_1000_snapshots}"
    )
    return 0


def main() -> int:
    return asyncio.run(_run(_parser().parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
