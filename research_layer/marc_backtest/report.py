"""Deterministic MARC validation metrics and research classification."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict
from typing import Iterable

from research_layer.marc_backtest.entities import BacktestTrade, BacktestWindowResult
from research_layer.statistics import (
    bootstrap_interval,
    max_drawdown,
    profit_factor,
    sharpe_ratio,
    wilson_interval,
)


def _finite_or_none(value: float) -> float | None:
    return float(value) if math.isfinite(float(value)) else None


def _metric_summary(
    trades: Iterable[BacktestTrade],
    *,
    r_field: str,
) -> dict[str, object]:
    items = tuple(trades)
    values = [float(getattr(trade, r_field)) for trade in items]
    wins = sum(value > 0.0 for value in values)
    count = len(values)
    expectancy = sum(values) / count if count else float("nan")
    median = (
        sorted(values)[count // 2]
        if count % 2 == 1
        else (
            (sorted(values)[count // 2 - 1] + sorted(values)[count // 2]) / 2.0
            if count
            else float("nan")
        )
    )
    ci = bootstrap_interval(values, statistic="mean") if values else None
    win_ci = wilson_interval(wins, count) if count else None
    reasons = Counter(trade.terminal_reason for trade in items)
    return {
        "trades": count,
        "wins": wins,
        "win_rate": None if not count else wins / count,
        "win_rate_ci95": (
            None
            if win_ci is None
            else {"low": win_ci.low, "high": win_ci.high}
        ),
        "expectancy_r": _finite_or_none(expectancy),
        "expectancy_ci95": (
            None
            if ci is None
            else {
                "low": _finite_or_none(ci.low),
                "high": _finite_or_none(ci.high),
            }
        ),
        "median_r": _finite_or_none(median),
        "profit_factor": _finite_or_none(profit_factor(values)),
        "sharpe_per_trade": _finite_or_none(sharpe_ratio(values)),
        "max_drawdown_r": _finite_or_none(max_drawdown(values)),
        "total_r": _finite_or_none(sum(values)),
        "average_holding_bars": (
            None
            if not count
            else sum(trade.duration_bars for trade in items) / count
        ),
        "long_trades": sum(trade.direction == "LONG" for trade in items),
        "short_trades": sum(trade.direction == "SHORT" for trade in items),
        "tp1_rate": (
            None if not count else sum(trade.tp1_hit for trade in items) / count
        ),
        "tp2_rate": (
            None if not count else sum(trade.tp2_hit for trade in items) / count
        ),
        "terminal_reasons": dict(sorted(reasons.items())),
    }


def _stream_summary(result: BacktestWindowResult) -> dict[str, object]:
    return {
        "symbol": result.symbol,
        "timeframe": result.timeframe,
        "start": result.start.isoformat(),
        "end": result.end.isoformat(),
        "candidate_count": result.candidate_count,
        "rejected_plan_count": result.rejected_plan_count,
        "rejection_reasons": dict(result.rejection_reasons),
        "gross": _metric_summary(result.trades, r_field="gross_r"),
        "base_cost": _metric_summary(result.trades, r_field="base_net_r"),
        "stress_cost": _metric_summary(result.trades, r_field="stress_net_r"),
    }


def _research_classification(
    *,
    base: dict[str, object],
    stress: dict[str, object],
) -> str:
    count = int(base["trades"])
    if count < 100:
        return "INSUFFICIENT_OOS_SAMPLE"
    expectancy = base["expectancy_r"]
    profit = base["profit_factor"]
    if expectancy is None or profit is None or expectancy <= 0 or profit <= 1:
        return "OOS_EDGE_NOT_ESTABLISHED"
    ci = base["expectancy_ci95"]
    if not isinstance(ci, dict) or ci.get("low") is None or float(ci["low"]) <= 0:
        return "OOS_POSITIVE_BUT_UNCERTAIN"
    stress_expectancy = stress["expectancy_r"]
    if stress_expectancy is None or float(stress_expectancy) <= 0:
        return "OOS_EDGE_COST_SENSITIVE"
    return "OOS_PROMISING_RESEARCH_ONLY"


def build_validation_report(
    *,
    validation: tuple[BacktestWindowResult, ...],
    oos: tuple[BacktestWindowResult, ...],
    provenance: dict[str, object],
    protocol: dict[str, object],
) -> dict[str, object]:
    """Build a pooled research report without converting results into runtime approval."""
    validation_trades = tuple(
        sorted(
            (trade for result in validation for trade in result.trades),
            key=lambda trade: (
                trade.entry_time,
                trade.symbol,
                trade.timeframe,
                trade.source_signal_id,
            ),
        )
    )
    oos_trades = tuple(
        sorted(
            (trade for result in oos for trade in result.trades),
            key=lambda trade: (
                trade.entry_time,
                trade.symbol,
                trade.timeframe,
                trade.source_signal_id,
            ),
        )
    )

    validation_base = _metric_summary(validation_trades, r_field="base_net_r")
    validation_stress = _metric_summary(validation_trades, r_field="stress_net_r")
    oos_base = _metric_summary(oos_trades, r_field="base_net_r")
    oos_stress = _metric_summary(oos_trades, r_field="stress_net_r")

    return {
        "schema": "MARC_BACKTEST_REPORT_V1",
        "strategy": {
            "core": "MA_REGIME_CORE",
            "short_name": "MARC",
            "setup": "MARC_R1_MA99_REGIME_RECLAIM",
            "engine_version": "marc-core-v0.1.0",
            "rule_set_version": "marc-r1-v0.1",
            "configuration_version": "marc-baseline-v0.1",
        },
        "provenance": provenance,
        "protocol": protocol,
        "validation": {
            "streams": [_stream_summary(item) for item in validation],
            "pooled_base_cost": validation_base,
            "pooled_stress_cost": validation_stress,
        },
        "out_of_sample": {
            "streams": [_stream_summary(item) for item in oos],
            "pooled_base_cost": oos_base,
            "pooled_stress_cost": oos_stress,
            "positive_streams_base_cost": sum(
                (
                    _metric_summary(item.trades, r_field="base_net_r")[
                        "expectancy_r"
                    ]
                    or 0
                )
                > 0
                for item in oos
            ),
            "stream_count": len(oos),
        },
        "research_classification": _research_classification(
            base=oos_base,
            stress=oos_stress,
        ),
        "runtime_approval": "DENIED_BACKTEST_ONLY",
        "limitations": [
            "Funding payments are not modeled in MARC backtest v0.1.",
            (
                "Pooled path metrics use chronological trade-entry order and are not "
                "a capital-weighted multi-asset portfolio simulation."
            ),
            "Intrabar stop/target ambiguity is resolved conservatively as stop-first.",
            (
                "The Chandelier runner activates after TP2. A trail derived from prior "
                "closed bars applies immediately after a deterministic TP2 fill at the "
                "candle open; otherwise a newly activated trail is effective next bar."
            ),
            "Historical results do not establish future profitability.",
        ],
    }


def trade_rows(
    windows: Iterable[BacktestWindowResult],
    *,
    window_name: str,
) -> list[dict[str, object]]:
    rows = []
    for result in windows:
        for trade in result.trades:
            row = asdict(trade)
            row["window"] = window_name
            row["entry_time"] = trade.entry_time.isoformat()
            row["exit_time"] = trade.exit_time.isoformat()
            row["fills"] = [
                {
                    **asdict(fill),
                    "time": fill.time.isoformat(),
                }
                for fill in trade.fills
            ]
            rows.append(row)
    return rows
