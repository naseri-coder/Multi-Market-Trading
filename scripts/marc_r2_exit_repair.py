#!/usr/bin/env python3
"""Run MARC R2 exit-repair development search and untouched holdout."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from research_layer.marc_backtest.data import (
    fetch_binance_vision_monthly_klines,
    resample_15m_to_30m,
    split_contiguous_candles,
)
from research_layer.marc_backtest.engine import BacktestConfig
from research_layer.marc_backtest.entities import BacktestWindowResult
from research_layer.marc_r2_repair.engine import (
    RepairVariant,
    backtest_repair_variant_window,
)
from research_layer.marc_r2_repair.report import build_repair_report, select_variant
from research_layer.marc_r2_search.report import summarize_windows

DEV = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
HOLD = ("ADAUSDT", "DOGEUSDT", "LINKUSDT", "LTCUSDT", "BCHUSDT")
VARIANTS = (
    RepairVariant.R1_BASELINE,
    RepairVariant.PARTIAL25_BE_AFTER_1R,
    RepairVariant.FULL_BE_AFTER_1R_TP2_50_RUNNER50,
    RepairVariant.FULL_BE_TP2_50_RUNNER50_COST_BUDGET,
)


def _date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=_date, default=_date("2022-01-01"))
    parser.add_argument("--end", type=_date, default=_date("2026-10-01"))
    parser.add_argument("--base-cost-bps", type=float, default=6.0)
    parser.add_argument("--stress-cost-bps", type=float, default=10.0)
    parser.add_argument("--request-delay", type=float, default=0.05)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("research_output/marc_r2_exit_repair_v0_1"),
    )
    parser.add_argument("--base-url", default="https://data.binance.vision")
    return parser


def _segmented(
    *,
    candles,
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    config: BacktestConfig,
    variant: RepairVariant,
) -> BacktestWindowResult:
    pieces = []
    for segment in split_contiguous_candles(candles, timeframe=timeframe):
        outside_window = (
            segment[-1].open_time < start or segment[0].open_time >= end
        )
        if len(segment) < 103 or outside_window:
            continue
        try:
            pieces.append(
                backtest_repair_variant_window(
                    candles=segment,
                    symbol=symbol,
                    timeframe=timeframe,
                    start=start,
                    end=end,
                    variant=variant,
                    config=config,
                )
            )
        except ValueError as exc:
            if str(exc) in {
                "window has no evaluable candles",
                "not enough candles for MARC backtest",
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
        timeframe=timeframe,
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
    candles_15m = archive.candles
    candles_30m = resample_15m_to_30m(candles_15m)
    print(
        f"MARC_R2_REPAIR_DATA symbol={symbol} "
        f"c15={len(candles_15m)} c30={len(candles_30m)}",
        flush=True,
    )
    return candles_15m, candles_30m


async def _run(args: argparse.Namespace) -> dict[str, object]:
    config = BacktestConfig(
        base_cost_bps_per_side=args.base_cost_bps,
        stress_cost_bps_per_side=args.stress_cost_bps,
    )
    development = {variant.value: [] for variant in VARIANTS}

    for symbol in DEV:
        candles_15m, candles_30m = await _load(symbol, args)
        for timeframe, candles in (("15m", candles_15m), ("30m", candles_30m)):
            for variant in VARIANTS:
                result = _segmented(
                    candles=candles,
                    symbol=symbol,
                    timeframe=timeframe,
                    start=args.start,
                    end=args.end,
                    config=config,
                    variant=variant,
                )
                development[variant.value].append(result)
                print(
                    f"MARC_R2_REPAIR_DEV variant={variant.value} "
                    f"symbol={symbol} tf={timeframe} trades={len(result.trades)}",
                    flush=True,
                )

    frozen = {name: tuple(items) for name, items in development.items()}
    summaries = {
        name: summarize_windows(items)
        for name, items in frozen.items()
    }
    selected = select_variant(summaries)
    print(f"MARC_R2_REPAIR_SELECTED variant={selected}", flush=True)

    holdout = None
    if selected is not None:
        holdout_items = []
        chosen = RepairVariant(selected)
        for symbol in HOLD:
            candles_15m, candles_30m = await _load(symbol, args)
            for timeframe, candles in (("15m", candles_15m), ("30m", candles_30m)):
                result = _segmented(
                    candles=candles,
                    symbol=symbol,
                    timeframe=timeframe,
                    start=args.start,
                    end=args.end,
                    config=config,
                    variant=chosen,
                )
                holdout_items.append(result)
                print(
                    f"MARC_R2_REPAIR_HOLDOUT variant={selected} "
                    f"symbol={symbol} tf={timeframe} "
                    f"trades={len(result.trades)}",
                    flush=True,
                )
        holdout = tuple(holdout_items)

    protocol = {
        "development_symbols": list(DEV),
        "untouched_cross_sectional_holdout_symbols": list(HOLD),
        "variants": [variant.value for variant in VARIANTS],
        "date_range": {
            "start": args.start.isoformat(),
            "end_exclusive": args.end.isoformat(),
        },
        "base_cost_bps_per_side": args.base_cost_bps,
        "stress_cost_bps_per_side": args.stress_cost_bps,
        "break_even_timing": (
            "TP1 trigger is known at candle close/intrabar; "
            "BE protection becomes active next candle"
        ),
        "cost_budget": "stress round-trip entry-notional estimate <= 0.25R",
        "holdout_fetch": (
            "only after one development variant passes frozen selector"
        ),
    }
    report = build_repair_report(
        development=frozen,
        selected_variant=selected,
        holdout=holdout,
        protocol=protocol,
    )

    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "marc_r2_exit_repair_report.json"
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    for name, summary in report["development"]["summaries"].items():
        overall = summary["overall"]
        print(
            f"MARC_R2_REPAIR_RESULT variant={name} "
            f"trades={overall['trades']} "
            f"base_exp={overall['base']['expectancy_r']} "
            f"base_pf={overall['base']['profit_factor']} "
            f"stress_exp={overall['stress']['expectancy_r']} "
            f"stress_pf={overall['stress']['profit_factor']}",
            flush=True,
        )

    holdout_summary = report["untouched_cross_sectional_holdout"]["summary"]
    if holdout_summary is None:
        print("MARC_R2_REPAIR_HOLDOUT_SKIPPED", flush=True)
    else:
        overall = holdout_summary["overall"]
        verdict = report["untouched_cross_sectional_holdout"]["verdict"]
        print(
            f"MARC_R2_REPAIR_HOLDOUT_RESULT selected={selected} "
            f"trades={overall['trades']} "
            f"base_exp={overall['base']['expectancy_r']} "
            f"base_pf={overall['base']['profit_factor']} "
            f"stress_exp={overall['stress']['expectancy_r']} "
            f"stress_pf={overall['stress']['profit_factor']} "
            f"classification={verdict['classification']}",
            flush=True,
        )

    print(
        f"MARC_R2_REPAIR_FINAL {report['final_classification']}",
        flush=True,
    )
    print(f"MARC_R2_REPAIR_REPORT {path}", flush=True)
    return report


def main() -> int:
    asyncio.run(_run(_parser().parse_args()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
