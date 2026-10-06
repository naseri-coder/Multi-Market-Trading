#!/usr/bin/env python3
"""Run the pre-registered MARC R2 causal setup search and untouched holdout."""

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
from research_layer.marc_r2_search.engine import R2Variant, backtest_r2_variant_window
from research_layer.marc_r2_search.report import (
    build_causal_search_report,
    select_development_variant,
    summarize_windows,
)

DEVELOPMENT_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT")
UNTOUCHED_HOLDOUT_SYMBOLS = (
    "ADAUSDT",
    "DOGEUSDT",
    "LINKUSDT",
    "LTCUSDT",
    "BCHUSDT",
)
VARIANTS = (
    R2Variant.R1_BASELINE,
    R2Variant.EARLY_MA99_LOSS_3,
    R2Variant.EARLY_OPPOSITE_BAND_3,
    R2Variant.HOLD_MA99_3_THEN_ENTER,
)


def _date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MARC R2 causal setup search")
    parser.add_argument("--start", type=_date, default=_date("2022-01-01"))
    parser.add_argument("--end", type=_date, default=_date("2026-10-01"))
    parser.add_argument("--base-cost-bps", type=float, default=6.0)
    parser.add_argument("--stress-cost-bps", type=float, default=10.0)
    parser.add_argument("--request-delay", type=float, default=0.05)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("research_output/marc_r2_causal_search_v0_1"),
    )
    parser.add_argument("--base-url", default="https://data.binance.vision")
    return parser


def _segmented_variant(
    *,
    candles,
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    config: BacktestConfig,
    variant: R2Variant,
) -> BacktestWindowResult:
    pieces = []
    for segment in split_contiguous_candles(candles, timeframe=timeframe):
        if len(segment) < 103:
            continue
        if segment[-1].open_time < start or segment[0].open_time >= end:
            continue
        try:
            pieces.append(
                backtest_r2_variant_window(
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
                "not enough candles for MARC R2 experiment",
            }:
                continue
            raise

    trades = []
    rejections: dict[str, int] = {}
    candidate_count = 0
    rejected_count = 0
    for piece in pieces:
        candidate_count += piece.candidate_count
        rejected_count += piece.rejected_plan_count
        trades.extend(piece.trades)
        for reason, count in piece.rejection_reasons:
            rejections[reason] = rejections.get(reason, 0) + count
    trades.sort(key=lambda trade: (trade.entry_time, trade.source_signal_id))
    return BacktestWindowResult(
        symbol=symbol.upper(),
        timeframe=timeframe,
        start=start,
        end=end,
        candidate_count=candidate_count,
        rejected_plan_count=rejected_count,
        rejection_reasons=tuple(sorted(rejections.items())),
        trades=tuple(trades),
    )


async def _load_symbol(
    *,
    symbol: str,
    start: datetime,
    end: datetime,
    args: argparse.Namespace,
):
    archive = await fetch_binance_vision_monthly_klines(
        symbol=symbol,
        start=start - timedelta(days=4),
        end=end,
        timeframe="15m",
        request_delay_seconds=args.request_delay,
        base_url=args.base_url,
    )
    candles_15m = archive.candles
    candles_30m = resample_15m_to_30m(candles_15m)
    print(
        f"MARC_R2_DATA_PASS symbol={symbol} "
        f"candles15m={len(candles_15m)} candles30m={len(candles_30m)} "
        f"archives={archive.verified_archives}",
        flush=True,
    )
    return candles_15m, candles_30m


async def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.end <= args.start:
        raise ValueError("end must be after start")
    if args.base_cost_bps < 0 or args.stress_cost_bps < args.base_cost_bps:
        raise ValueError("invalid execution-cost assumptions")

    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    config = BacktestConfig(
        base_cost_bps_per_side=args.base_cost_bps,
        stress_cost_bps_per_side=args.stress_cost_bps,
    )

    development: dict[str, list[BacktestWindowResult]] = {
        variant.value: [] for variant in VARIANTS
    }

    for symbol in DEVELOPMENT_SYMBOLS:
        candles_15m, candles_30m = await _load_symbol(
            symbol=symbol,
            start=args.start,
            end=args.end,
            args=args,
        )
        for timeframe, candles in (("15m", candles_15m), ("30m", candles_30m)):
            for variant in VARIANTS:
                result = _segmented_variant(
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
                    f"MARC_R2_DEV_STREAM variant={variant.value} "
                    f"symbol={symbol} timeframe={timeframe} "
                    f"trades={len(result.trades)}",
                    flush=True,
                )

    development_frozen = {
        name: tuple(windows) for name, windows in development.items()
    }
    dev_summaries = {
        name: summarize_windows(windows)
        for name, windows in development_frozen.items()
    }
    selected = select_development_variant(dev_summaries)
    print(f"MARC_R2_SELECTED variant={selected}", flush=True)

    holdout = None
    if selected is not None:
        selected_variant = R2Variant(selected)
        holdout_items = []
        # Holdout archives are fetched only after the development selector is frozen.
        for symbol in UNTOUCHED_HOLDOUT_SYMBOLS:
            candles_15m, candles_30m = await _load_symbol(
                symbol=symbol,
                start=args.start,
                end=args.end,
                args=args,
            )
            for timeframe, candles in (("15m", candles_15m), ("30m", candles_30m)):
                result = _segmented_variant(
                    candles=candles,
                    symbol=symbol,
                    timeframe=timeframe,
                    start=args.start,
                    end=args.end,
                    config=config,
                    variant=selected_variant,
                )
                holdout_items.append(result)
                print(
                    f"MARC_R2_HOLDOUT_STREAM variant={selected} "
                    f"symbol={symbol} timeframe={timeframe} "
                    f"trades={len(result.trades)}",
                    flush=True,
                )
        holdout = tuple(holdout_items)

    protocol = {
        "development_symbols": list(DEVELOPMENT_SYMBOLS),
        "untouched_cross_sectional_holdout_symbols": list(UNTOUCHED_HOLDOUT_SYMBOLS),
        "date_range": {
            "start": args.start.isoformat(),
            "end_exclusive": args.end.isoformat(),
        },
        "variants": [variant.value for variant in VARIANTS],
        "entry_and_exit_actions": "NEXT_BAR_OPEN_WHEN_SIGNAL_REQUIRES_CLOSED_BAR",
        "costs": {
            "base_bps_per_side": args.base_cost_bps,
            "stress_bps_per_side": args.stress_cost_bps,
        },
        "anti_overfit": (
            "Only four pre-registered variants are compared. Holdout data is fetched "
            "only after development selection and never participates in selection."
        ),
    }
    report = build_causal_search_report(
        development=development_frozen,
        selected_variant=selected,
        holdout=holdout,
        protocol=protocol,
    )
    report_path = output_dir / "marc_r2_causal_search_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    for name, summary in report["development"]["summaries"].items():
        overall = summary["overall"]
        print(
            f"MARC_R2_DEV_RESULT variant={name} trades={overall['trades']} "
            f"base_exp={overall['base']['expectancy_r']} "
            f"base_pf={overall['base']['profit_factor']} "
            f"stress_exp={overall['stress']['expectancy_r']} "
            f"stress_pf={overall['stress']['profit_factor']}",
            flush=True,
        )

    verdict = report["untouched_cross_sectional_holdout"]["verdict"]
    if report["untouched_cross_sectional_holdout"]["summary"] is not None:
        overall = report["untouched_cross_sectional_holdout"]["summary"]["overall"]
        print(
            f"MARC_R2_HOLDOUT_RESULT selected={selected} "
            f"trades={overall['trades']} "
            f"base_exp={overall['base']['expectancy_r']} "
            f"base_pf={overall['base']['profit_factor']} "
            f"stress_exp={overall['stress']['expectancy_r']} "
            f"stress_pf={overall['stress']['profit_factor']} "
            f"classification={verdict['classification']}",
            flush=True,
        )
    else:
        print(
            "MARC_R2_HOLDOUT_SKIPPED reason=NO_DEVELOPMENT_VARIANT_PASSED",
            flush=True,
        )
    print(f"MARC_R2_FINAL_CLASSIFICATION {report['final_classification']}", flush=True)
    print(f"MARC_R2_REPORT_PATH {report_path}", flush=True)
    return report


def main() -> int:
    args = _parser().parse_args()
    asyncio.run(_run(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
