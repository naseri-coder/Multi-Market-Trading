#!/usr/bin/env python3
"""Run descriptive MARC R2 root-cause diagnostics on the frozen R1 baseline."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from research_layer.marc_backtest.data import (
    fetch_binance_vision_monthly_klines,
    resample_15m_to_30m,
    split_contiguous_candles,
)
from research_layer.marc_backtest.engine import BacktestConfig, backtest_window
from research_layer.marc_backtest.entities import BacktestWindowResult
from research_layer.marc_diagnostic.analysis import (
    build_diagnostic_report,
    diagnose_trades,
    diagnostic_rows,
    resample_30m_to_1h,
)


def _date(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)


def _symbols(value: str) -> tuple[str, ...]:
    items = tuple(item.strip().upper() for item in value.split(",") if item.strip())
    if not items:
        raise argparse.ArgumentTypeError("at least one symbol is required")
    return items


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MARC R2 diagnostic research")
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
        default=Path("research_output/marc_r2_diagnostic_v0_1"),
    )
    parser.add_argument("--base-url", default="https://data.binance.vision")
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
    pieces = []
    for segment in split_contiguous_candles(candles, timeframe=timeframe):
        if len(segment) < 100:
            continue
        if segment[-1].open_time < start or segment[0].open_time >= end:
            continue
        try:
            pieces.append(
                backtest_window(
                    candles=segment,
                    symbol=symbol,
                    timeframe=timeframe,
                    start=start,
                    end=end,
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

    rejections: dict[str, int] = {}
    trades = []
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


def _contrast_line(name: str, payload: dict[str, object]) -> str:
    return (
        f"{name} uplift={payload.get('gross_expectancy_uplift_r')} "
        f"positive_n={payload['positive']['trades']} "
        f"negative_n={payload['negative']['trades']}"
    )


async def _run(args: argparse.Namespace) -> dict[str, object]:
    if not args.start < args.split < args.end:
        raise ValueError("expected start < split < end")

    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    warmup_start = args.start - timedelta(days=4)
    config = BacktestConfig(
        base_cost_bps_per_side=args.base_cost_bps,
        stress_cost_bps_per_side=args.stress_cost_bps,
    )

    validation_diagnostics = []
    oos_diagnostics = []

    for symbol in args.symbols:
        print(f"MARC_R2_DATA_BEGIN symbol={symbol}", flush=True)
        archive = await fetch_binance_vision_monthly_klines(
            symbol=symbol,
            start=warmup_start,
            end=args.end,
            timeframe="15m",
            request_delay_seconds=args.request_delay,
            base_url=args.base_url,
        )
        candles_15m = archive.candles
        candles_30m = resample_15m_to_30m(candles_15m)
        candles_1h = resample_30m_to_1h(candles_30m)

        for timeframe, candles, htf in (
            ("15m", candles_15m, candles_30m),
            ("30m", candles_30m, candles_1h),
        ):
            validation = _segmented_backtest(
                candles=candles,
                symbol=symbol,
                timeframe=timeframe,
                start=args.start,
                end=args.split,
                config=config,
            )
            oos = _segmented_backtest(
                candles=candles,
                symbol=symbol,
                timeframe=timeframe,
                start=args.split,
                end=args.end,
                config=config,
            )
            validation_diag = diagnose_trades(
                result=validation,
                candles=candles,
                higher_timeframe_candles=htf,
            )
            oos_diag = diagnose_trades(
                result=oos,
                candles=candles,
                higher_timeframe_candles=htf,
            )
            validation_diagnostics.extend(validation_diag)
            oos_diagnostics.extend(oos_diag)
            print(
                f"MARC_R2_STREAM_PASS symbol={symbol} timeframe={timeframe} "
                f"validation={len(validation_diag)} diagnostic_oos={len(oos_diag)}",
                flush=True,
            )

    validation_tuple = tuple(
        sorted(
            validation_diagnostics,
            key=lambda item: (
                item.entry_time,
                item.symbol,
                item.timeframe,
                item.source_signal_id,
            ),
        )
    )
    oos_tuple = tuple(
        sorted(
            oos_diagnostics,
            key=lambda item: (
                item.entry_time,
                item.symbol,
                item.timeframe,
                item.source_signal_id,
            ),
        )
    )
    report = build_diagnostic_report(
        validation=validation_tuple,
        diagnostic_oos=oos_tuple,
    )
    report["protocol"] = {
        "validation_window": {
            "start": args.start.isoformat(),
            "end_exclusive": args.split.isoformat(),
        },
        "diagnostic_oos_window": {
            "start": args.split.isoformat(),
            "end_exclusive": args.end.isoformat(),
        },
        "symbols": list(args.symbols),
        "timeframes": ["15m", "30m"],
        "base_cost_bps_per_side": args.base_cost_bps,
        "stress_cost_bps_per_side": args.stress_cost_bps,
        "note": (
            "The previous OOS window is now used descriptively for R2 diagnosis. "
            "Any R2 rule developed from this report requires a new untouched holdout."
        ),
    }

    report_path = output_dir / "marc_r2_diagnostic_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    rows = []
    for window_name, records in (
        ("VALIDATION", validation_tuple),
        ("DIAGNOSTIC_OOS", oos_tuple),
    ):
        for row in diagnostic_rows(records):
            row = dict(row)
            row["window"] = window_name
            rows.append(row)
    csv_path = output_dir / "marc_r2_trade_diagnostics.csv"
    if rows:
        fieldnames = ["window", *[key for key in rows[0] if key != "window"]]
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    contrasts = report["diagnostic_oos"]["contrasts"]
    print(
        "MARC_R2_DIAGNOSTIC_RESULT "
        f"validation_trades={report['validation']['overall']['trades']} "
        f"diagnostic_oos_trades={report['diagnostic_oos']['overall']['trades']}",
        flush=True,
    )
    for name in (
        "full_ma_alignment",
        "ma99_slope_alignment",
        "htf_alignment_vs_opposed",
        "retest_rejection_within_8",
        "early_ma99_hold",
        "avoid_early_opposite_band_failure",
    ):
        print("MARC_R2_CONTRAST " + _contrast_line(name, contrasts[name]), flush=True)
    print(f"MARC_R2_REPORT_PATH {report_path}", flush=True)
    print(f"MARC_R2_DIAGNOSTICS_PATH {csv_path}", flush=True)
    return report


def main() -> int:
    args = _parser().parse_args()
    asyncio.run(_run(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
