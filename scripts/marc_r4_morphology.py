#!/usr/bin/env python3
"""Run MARC R4 setup morphology and directional qualification."""

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
from research_layer.marc_r2_pure.engine import backtest_fresh_reversal_window
from research_layer.marc_r4_morphology.features import annotate_frt_morphology
from research_layer.marc_r4_morphology.walkforward import (
    build_r4_report,
    development_gate,
    run_development_walkforward,
    run_holdout_walkforward,
)

RESEARCH_SYMBOLS = (
    "BTCUSDT",
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "DOGEUSDT",
    "LINKUSDT",
    "LTCUSDT",
    "BCHUSDT",
)
UNTOUCHED_HOLDOUT_SYMBOLS = (
    "AVAXUSDT",
    "DOTUSDT",
    "TRXUSDT",
    "ATOMUSDT",
    "NEARUSDT",
)


def _date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MARC R4 morphology qualification")
    parser.add_argument("--start", type=_date, default=_date("2022-01-01"))
    parser.add_argument("--end", type=_date, default=_date("2026-10-01"))
    parser.add_argument("--base-cost-bps", type=float, default=6.0)
    parser.add_argument("--stress-cost-bps", type=float, default=10.0)
    parser.add_argument("--request-delay", type=float, default=0.05)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("research_output/marc_r4_morphology_v0_1"),
    )
    parser.add_argument("--base-url", default="https://data.binance.vision")
    return parser


def _segmented_frt(
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
                backtest_fresh_reversal_window(
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
                "not enough candles for MARC R2 FRT",
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
        timeframe="15m",
        start=start,
        end=end,
        candidate_count=candidate_count,
        rejected_plan_count=rejected_count,
        rejection_reasons=tuple(sorted(rejections.items())),
        trades=tuple(trades),
    )


async def _load_and_annotate(
    *,
    symbol: str,
    args: argparse.Namespace,
    config: BacktestConfig,
):
    archive = await fetch_binance_vision_monthly_klines(
        symbol=symbol,
        start=args.start - timedelta(days=4),
        end=args.end,
        timeframe="15m",
        request_delay_seconds=args.request_delay,
        base_url=args.base_url,
    )
    result = _segmented_frt(
        candles=archive.candles,
        symbol=symbol,
        start=args.start,
        end=args.end,
        config=config,
    )
    annotated = annotate_frt_morphology(
        candles=archive.candles,
        trades=result.trades,
        symbol=symbol,
    )
    print(
        f"MARC_R4_DATA_PASS symbol={symbol} candles={len(archive.candles)} "
        f"frt_trades={len(result.trades)} annotated={len(annotated)} "
        f"archives={archive.verified_archives}",
        flush=True,
    )
    return annotated


def _print_aggregate(prefix: str, payload: dict[str, object]) -> None:
    aggregate = payload["aggregate"]
    overall = aggregate["overall"]
    print(
        f"{prefix} trades={overall['trades']} "
        f"base_exp={overall['base']['expectancy_r']} "
        f"base_pf={overall['base']['profit_factor']} "
        f"stress_exp={overall['stress']['expectancy_r']} "
        f"stress_pf={overall['stress']['profit_factor']} "
        f"positive_folds={aggregate['positive_base_folds']}/"
        f"{aggregate['fold_count']} "
        f"positive_symbols={aggregate['positive_base_symbols']}/"
        f"{aggregate['symbol_count']}",
        flush=True,
    )


async def _run(args: argparse.Namespace) -> dict[str, object]:
    if args.end <= args.start:
        raise ValueError("end must be after start")

    config = BacktestConfig(
        base_cost_bps_per_side=args.base_cost_bps,
        stress_cost_bps_per_side=args.stress_cost_bps,
    )

    development_records = []
    for symbol in RESEARCH_SYMBOLS:
        development_records.extend(
            await _load_and_annotate(symbol=symbol, args=args, config=config)
        )
    development_tuple = tuple(
        sorted(development_records, key=lambda item: (item.entry_time, item.symbol))
    )
    development = run_development_walkforward(
        records=development_tuple,
        symbols=RESEARCH_SYMBOLS,
    )
    dev_gate = development_gate(development)
    _print_aggregate(
        f"MARC_R4_DEVELOPMENT passed={dev_gate['passed']}",
        development,
    )
    for fold in development["folds"]:
        print(
            f"MARC_R4_FOLD year={fold['test_year']} "
            f"morphologies={','.join(fold['eligible_morphologies']) or 'NONE'} "
            f"trades={fold['eligible_test']['trades']} "
            f"base_exp={fold['eligible_test']['base']['expectancy_r']} "
            f"stress_exp={fold['eligible_test']['stress']['expectancy_r']}",
            flush=True,
        )

    holdout = None
    if dev_gate["passed"]:
        holdout_records = []
        for symbol in UNTOUCHED_HOLDOUT_SYMBOLS:
            holdout_records.extend(
                await _load_and_annotate(symbol=symbol, args=args, config=config)
            )
        holdout = run_holdout_walkforward(
            records=tuple(
                sorted(
                    holdout_records,
                    key=lambda item: (item.entry_time, item.symbol),
                )
            ),
            symbols=UNTOUCHED_HOLDOUT_SYMBOLS,
            morphology_policy_by_year=development["morphology_policy_by_year"],
        )

    protocol = {
        "base_setup": "MARC_R2_FRESH_REVERSAL_TRANSITION_V0_1",
        "timeframe": "15m_only",
        "research_symbols": list(RESEARCH_SYMBOLS),
        "untouched_holdout_symbols": list(UNTOUCHED_HOLDOUT_SYMBOLS),
        "walk_forward_test_years": [2023, 2024, 2025, 2026],
        "training": "expanding_window_strictly_before_test_year",
        "morphology_score": {
            "point_1": "directional 3-bar impulse >= 0.50 ATR14",
            "point_2": (
                "directional MA7/25 spread >= 0.10 ATR14 and wider than 2 bars ago"
            ),
            "point_3": (
                "both persistence candles have directional bodies and mean "
                "directional close-location >= 0.65"
            ),
            "point_4": "confirmation close extension from MA99 <= 0.75 ATR14",
            "classes": {
                "A": "score=4",
                "B": "score=3",
                "C": "score=0..2",
            },
            "direction": "LONG and SHORT are distinct morphology classes",
        },
        "morphology_eligibility": {
            "minimum_training_trades": 40,
            "base_expectancy_r": ">0.05",
            "stress_expectancy_r": ">0",
            "stress_profit_factor": ">=1.03",
            "cross_symbol_support": (
                "at least 3 symbols with >=5 class trades and positive base expectancy"
            ),
        },
        "holdout_policy": (
            "exact development-frozen direction+morphology classes are applied "
            "by year; holdout outcomes never select or modify the classes"
        ),
        "base_cost_bps_per_side": args.base_cost_bps,
        "stress_cost_bps_per_side": args.stress_cost_bps,
        "anti_overfit": (
            "No MA/exit optimization, no threshold grid search, no symbol selector, "
            "and no use of the untouched holdout before development passes."
        ),
    }
    report = build_r4_report(
        development=development,
        holdout=holdout,
        protocol=protocol,
    )

    output = args.output_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    path = output / "marc_r4_morphology_report.json"
    path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    if holdout is None:
        print("MARC_R4_HOLDOUT_SKIPPED", flush=True)
    else:
        gate = report["untouched_cross_sectional_holdout"]["gate"]
        _print_aggregate(
            f"MARC_R4_HOLDOUT passed={gate['passed']}",
            holdout,
        )

    print(f"MARC_R4_FINAL {report['final_classification']}", flush=True)
    print(f"MARC_R4_REPORT {path}", flush=True)
    return report


def main() -> int:
    asyncio.run(_run(_parser().parse_args()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
