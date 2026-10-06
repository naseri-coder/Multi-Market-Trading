#!/usr/bin/env python3
"""Run the frozen MARC v0.1 research-only validation against public futures data."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from research_layer.marc_backtest.data import (
    candle_series_sha256,
    fetch_binance_vision_monthly_klines,
    resample_15m_to_30m,
    split_contiguous_candles,
)
from research_layer.marc_backtest.engine import BacktestConfig, backtest_window
from research_layer.marc_backtest.entities import BacktestWindowResult
from research_layer.marc_backtest.report import build_validation_report, trade_rows


def _date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)


def _symbols(value: str) -> tuple[str, ...]:
    items = tuple(item.strip().upper() for item in value.split(",") if item.strip())
    if not items:
        raise argparse.ArgumentTypeError("at least one symbol is required")
    if len(set(items)) != len(items):
        raise argparse.ArgumentTypeError("symbols must be unique")
    return items


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MARC frozen OOS backtest")
    parser.add_argument(
        "--symbols",
        type=_symbols,
        default=_symbols("BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT"),
    )
    parser.add_argument("--start", type=_date, default=_date("2022-01-01"))
    parser.add_argument("--split", type=_date, default=_date("2025-01-01"))
    parser.add_argument("--end", type=_date, default=_date("2026-10-01"))
    parser.add_argument("--base-cost-bps", type=float, default=6.0)
    parser.add_argument("--stress-cost-bps", type=float, default=10.0)
    parser.add_argument("--request-delay", type=float, default=0.10)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("research_output/marc_oos_v0_1"),
    )
    parser.add_argument(
        "--base-url",
        default="https://data.binance.vision",
    )
    return parser


def _segmented_backtest(
    *,
    candles,
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    config: BacktestConfig,
) -> BacktestWindowResult:
    results = []
    for segment in split_contiguous_candles(candles, timeframe=timeframe):
        if len(segment) < 100:
            continue
        if segment[-1].open_time < start or segment[0].open_time >= end:
            continue
        try:
            result = backtest_window(
                candles=segment,
                symbol=symbol,
                timeframe=timeframe,
                start=start,
                end=end,
                config=config,
            )
        except ValueError as exc:
            if str(exc) in {
                "window has no evaluable candles",
                "not enough candles for MARC backtest",
            }:
                continue
            raise
        results.append(result)

    rejection_counts: dict[str, int] = {}
    trades = []
    candidate_count = 0
    rejected_plan_count = 0
    for result in results:
        candidate_count += result.candidate_count
        rejected_plan_count += result.rejected_plan_count
        trades.extend(result.trades)
        for reason, count in result.rejection_reasons:
            rejection_counts[reason] = rejection_counts.get(reason, 0) + count

    trades.sort(key=lambda trade: (trade.entry_time, trade.source_signal_id))
    return BacktestWindowResult(
        symbol=symbol.upper(),
        timeframe=timeframe,
        start=start,
        end=end,
        candidate_count=candidate_count,
        rejected_plan_count=rejected_plan_count,
        rejection_reasons=tuple(sorted(rejection_counts.items())),
        trades=tuple(trades),
    )


def _series_provenance(candles, timeframe: str) -> dict[str, object]:
    segments = split_contiguous_candles(candles, timeframe=timeframe)
    return {
        "timeframe": timeframe,
        "candles": len(candles),
        "first_open": candles[0].open_time.isoformat(),
        "last_close": candles[-1].close_time.isoformat(),
        "sha256": candle_series_sha256(candles),
        "gap_count": max(0, len(segments) - 1),
        "segment_count": len(segments),
    }


async def _run(args: argparse.Namespace) -> dict[str, object]:
    if not args.start < args.split < args.end:
        raise ValueError("expected start < split < end")
    if args.base_cost_bps < 0 or args.stress_cost_bps < args.base_cost_bps:
        raise ValueError("invalid execution cost assumptions")

    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    config = BacktestConfig(
        base_cost_bps_per_side=args.base_cost_bps,
        stress_cost_bps_per_side=args.stress_cost_bps,
    )
    warmup_start = args.start - timedelta(days=4)

    validation = []
    oos = []
    dataset_rows = []

    for symbol in args.symbols:
        print(
            f"MARC_DATA_FETCH_BEGIN symbol={symbol} "
            f"start={warmup_start.date()} end={args.end.date()}",
            flush=True,
        )
        archive_series = await fetch_binance_vision_monthly_klines(
            symbol=symbol,
            start=warmup_start,
            end=args.end,
            timeframe="15m",
            request_delay_seconds=args.request_delay,
            base_url=args.base_url,
        )
        candles_15m = archive_series.candles
        candles_30m = resample_15m_to_30m(candles_15m)
        dataset_rows.append(
            {
                "symbol": symbol,
                "source": "BINANCE_VISION_USDM_MONTHLY_ARCHIVES",
                "verified_archives": archive_series.verified_archives,
                "archive_manifest_sha256": archive_series.archive_manifest_sha256,
                "archive_gap_count": archive_series.gap_count,
                "archive_segment_count": archive_series.segment_count,
                "15m": _series_provenance(candles_15m, "15m"),
                "30m": _series_provenance(candles_30m, "30m"),
            }
        )
        print(
            f"MARC_DATA_FETCH_PASS symbol={symbol} "
            f"candles15m={len(candles_15m)} candles30m={len(candles_30m)}",
            flush=True,
        )

        for timeframe, candles in (("15m", candles_15m), ("30m", candles_30m)):
            validation_result = _segmented_backtest(
                candles=candles,
                symbol=symbol,
                timeframe=timeframe,
                start=args.start,
                end=args.split,
                config=config,
            )
            oos_result = _segmented_backtest(
                candles=candles,
                symbol=symbol,
                timeframe=timeframe,
                start=args.split,
                end=args.end,
                config=config,
            )
            validation.append(validation_result)
            oos.append(oos_result)
            print(
                f"MARC_STREAM_PASS symbol={symbol} timeframe={timeframe} "
                f"validation_trades={len(validation_result.trades)} "
                f"oos_trades={len(oos_result.trades)}",
                flush=True,
            )

    protocol = {
        "signal_baseline": "MARC_R1_V0_1_FROZEN",
        "validation_window": {
            "start": args.start.isoformat(),
            "end_exclusive": args.split.isoformat(),
        },
        "out_of_sample_window": {
            "start": args.split.isoformat(),
            "end_exclusive": args.end.isoformat(),
        },
        "timeframes": ["15m", "30m"],
        "source_timeframe": "15m",
        "resample_30m": "UTC_ALIGNED_TWO_15M_CANDLES",
        "entry": "NEXT_BAR_OPEN",
        "position_rule": "ONE_ACTIVE_TRADE_PER_SYMBOL_TIMEFRAME",
        "intrabar_ambiguity": "STOP_FIRST",
        "exit": {
            "tp1": "25_PERCENT_AT_1R",
            "tp2": "25_PERCENT_AT_2R",
            "runner": (
                "50_PERCENT_CHANDELIER_22_3ATR; PRIOR_CLOSED_BAR_TRAIL_APPLIES_"
                "IMMEDIATELY_AFTER_TP2_OPEN_GAP; OTHERWISE_NEXT_BAR"
            ),
        },
        "base_cost_bps_per_side": args.base_cost_bps,
        "stress_cost_bps_per_side": args.stress_cost_bps,
        "funding": "NOT_MODELED_V0_1",
    }
    provenance = {
        "exchange": "binance",
        "market_type": "usd_m_futures",
        "archive_base_url": args.base_url,
        "symbols": list(args.symbols),
        "datasets": dataset_rows,
    }
    report = build_validation_report(
        validation=tuple(validation),
        oos=tuple(oos),
        provenance=provenance,
        protocol=protocol,
    )

    report_path = output_dir / "marc_backtest_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    rows = trade_rows(validation, window_name="VALIDATION")
    rows.extend(trade_rows(oos, window_name="OUT_OF_SAMPLE"))
    csv_path = output_dir / "marc_backtest_trades.csv"
    fieldnames = [
        "window",
        "symbol",
        "timeframe",
        "direction",
        "source_signal_id",
        "entry_time",
        "entry_price",
        "stop_loss",
        "exit_time",
        "duration_bars",
        "gross_r",
        "base_net_r",
        "stress_net_r",
        "tp1_hit",
        "tp2_hit",
        "terminal_reason",
        "fills",
    ]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            row = dict(row)
            row["fills"] = json.dumps(row["fills"], sort_keys=True)
            writer.writerow({name: row[name] for name in fieldnames})

    oos_base = report["out_of_sample"]["pooled_base_cost"]
    oos_stress = report["out_of_sample"]["pooled_stress_cost"]
    print(
        "MARC_OOS_RESULT "
        f"classification={report['research_classification']} "
        f"trades={oos_base['trades']} "
        f"expectancy_r={oos_base['expectancy_r']} "
        f"profit_factor={oos_base['profit_factor']} "
        f"stress_expectancy_r={oos_stress['expectancy_r']} "
        f"positive_streams={report['out_of_sample']['positive_streams_base_cost']}/"
        f"{report['out_of_sample']['stream_count']}",
        flush=True,
    )
    print(f"MARC_REPORT_PATH {report_path}", flush=True)
    print(f"MARC_TRADES_PATH {csv_path}", flush=True)
    return report


def main() -> int:
    args = _parser().parse_args()
    asyncio.run(_run(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
