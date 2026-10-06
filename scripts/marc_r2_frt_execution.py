#!/usr/bin/env python3
"""Run MARC R2 FRT v0.2 development and untouched holdout."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from research_layer.marc_backtest.data import (
    fetch_binance_vision_monthly_klines,
    split_contiguous_candles,
)
from research_layer.marc_backtest.engine import BacktestConfig
from research_layer.marc_backtest.entities import BacktestWindowResult
from research_layer.marc_r2_frt_v2.engine import backtest_frt_execution_viable_window
from research_layer.marc_r2_frt_v2.report import (
    _development_passes,
    build_frt_v2_report,
)
from research_layer.marc_r2_search.report import summarize_windows

DEV = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
HOLD = ("ADAUSDT", "DOGEUSDT", "LINKUSDT", "LTCUSDT", "BCHUSDT")


def _date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MARC R2 FRT v0.2 execution viability")
    parser.add_argument("--start", type=_date, default=_date("2022-01-01"))
    parser.add_argument("--end", type=_date, default=_date("2026-10-01"))
    parser.add_argument("--base-cost-bps", type=float, default=6.0)
    parser.add_argument("--stress-cost-bps", type=float, default=10.0)
    parser.add_argument("--request-delay", type=float, default=0.05)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("research_output/marc_r2_frt_v0_2"),
    )
    parser.add_argument("--base-url", default="https://data.binance.vision")
    return parser


def _segmented(
    *,
    candles,
    symbol: str,
    start: datetime,
    end: datetime,
    config: BacktestConfig,
) -> BacktestWindowResult:
    pieces = []
    for segment in split_contiguous_candles(candles, timeframe="15m"):
        if len(segment) < 100:
            continue
        if segment[-1].open_time < start or segment[0].open_time >= end:
            continue
        try:
            pieces.append(
                backtest_frt_execution_viable_window(
                    candles=segment,
                    symbol=symbol,
                    timeframe="15m",
                    start=start,
                    end=end,
                    config=config,
                )
            )
        except ValueError as exc:
            if str(exc) in {
                "window has no evaluable candles",
                "not enough candles for MARC R2 FRT v0.2",
            }:
                continue
            raise

    trades = []
    rejections: dict[str, int] = {}
    candidates = 0
    rejected = 0
    for piece in pieces:
        candidates += piece.candidate_count
        rejected += piece.rejected_plan_count
        trades.extend(piece.trades)
        for reason, count in piece.rejection_reasons:
            rejections[reason] = rejections.get(reason, 0) + count
    trades.sort(key=lambda trade: (trade.entry_time, trade.source_signal_id))
    return BacktestWindowResult(
        symbol=symbol.upper(),
        timeframe="15m",
        start=start,
        end=end,
        candidate_count=candidates,
        rejected_plan_count=rejected,
        rejection_reasons=tuple(sorted(rejections.items())),
        trades=tuple(trades),
    )


async def _load(symbol: str, args: argparse.Namespace):
    archive = await fetch_binance_vision_monthly_klines(
        symbol=symbol,
        start=args.start - timedelta(days=4),
        end=args.end,
        timeframe="15m",
        request_delay_seconds=args.request_delay,
        base_url=args.base_url,
    )
    print(
        f"MARC_R2_FRT_V2_DATA symbol={symbol} candles={len(archive.candles)} "
        f"archives={archive.verified_archives}",
        flush=True,
    )
    return archive.candles


async def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.end <= args.start:
        raise ValueError("end must be after start")

    config = BacktestConfig(
        base_cost_bps_per_side=args.base_cost_bps,
        stress_cost_bps_per_side=args.stress_cost_bps,
    )

    development = []
    for symbol in DEV:
        candles = await _load(symbol, args)
        result = _segmented(
            candles=candles,
            symbol=symbol,
            start=args.start,
            end=args.end,
            config=config,
        )
        development.append(result)
        print(
            f"MARC_R2_FRT_V2_DEV symbol={symbol} trades={len(result.trades)}",
            flush=True,
        )

    dev_tuple = tuple(development)
    dev_summary = summarize_windows(dev_tuple)
    passes = _development_passes(dev_summary)
    print(
        f"MARC_R2_FRT_V2_DEVELOPMENT passed={passes} "
        f"trades={dev_summary['overall']['trades']} "
        f"base_exp={dev_summary['overall']['base']['expectancy_r']} "
        f"base_pf={dev_summary['overall']['base']['profit_factor']} "
        f"stress_exp={dev_summary['overall']['stress']['expectancy_r']} "
        f"stress_pf={dev_summary['overall']['stress']['profit_factor']} "
        f"positive_streams={dev_summary['positive_base_streams']}/"
        f"{dev_summary['stream_count']}",
        flush=True,
    )

    holdout = None
    if passes:
        items = []
        for symbol in HOLD:
            candles = await _load(symbol, args)
            result = _segmented(
                candles=candles,
                symbol=symbol,
                start=args.start,
                end=args.end,
                config=config,
            )
            items.append(result)
            print(
                f"MARC_R2_FRT_V2_HOLDOUT symbol={symbol} trades={len(result.trades)}",
                flush=True,
            )
        holdout = tuple(items)

    protocol = {
        "setup": "MARC_R2_FRT_EXECUTION_V0_2",
        "timeframe": "15m_only",
        "development_symbols": list(DEV),
        "untouched_holdout_symbols": list(HOLD),
        "date_range": {
            "start": args.start.isoformat(),
            "end_exclusive": args.end.isoformat(),
        },
        "latest_cross_age_bars_max": 3,
        "ma99_slope": "5_bar_slope_must_remain_opposed_to_trade_direction",
        "minimum_initial_risk_pct": 0.006,
        "max_stress_roundtrip_drag_r": 0.25,
        "exit_model": "frozen_R1_25pct_1R_25pct_2R_50pct_chandelier",
        "base_cost_bps_per_side": args.base_cost_bps,
        "stress_cost_bps_per_side": args.stress_cost_bps,
        "anti_overfit": (
            "One additive execution-viability rule on the already frozen FRT v0.1. "
            "Development gate is unchanged. Holdout is fetched only after pass."
        ),
    }
    report = build_frt_v2_report(
        development=dev_tuple,
        holdout=holdout,
        protocol=protocol,
    )

    out = args.output_dir.expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    path = out / "marc_r2_frt_execution_report.json"
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    summary = report["untouched_cross_sectional_holdout"]["summary"]
    if summary is None:
        print("MARC_R2_FRT_V2_HOLDOUT_SKIPPED", flush=True)
    else:
        overall = summary["overall"]
        verdict = report["untouched_cross_sectional_holdout"]["verdict"]
        print(
            f"MARC_R2_FRT_V2_HOLDOUT_RESULT trades={overall['trades']} "
            f"base_exp={overall['base']['expectancy_r']} "
            f"base_pf={overall['base']['profit_factor']} "
            f"stress_exp={overall['stress']['expectancy_r']} "
            f"stress_pf={overall['stress']['profit_factor']} "
            f"positive_streams={summary['positive_base_streams']}/"
            f"{summary['stream_count']} "
            f"classification={verdict['classification']}",
            flush=True,
        )

    print(f"MARC_R2_FRT_V2_FINAL {report['final_classification']}", flush=True)
    print(f"MARC_R2_FRT_V2_REPORT {path}", flush=True)
    return report


def main() -> int:
    asyncio.run(_run(_parser().parse_args()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
