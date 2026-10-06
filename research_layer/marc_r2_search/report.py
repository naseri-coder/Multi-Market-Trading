"""Metrics, pre-registered selection, and untouched-holdout verdict for MARC R2."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Iterable

from research_layer.marc_backtest.entities import BacktestTrade, BacktestWindowResult
from research_layer.statistics import max_drawdown, profit_factor
from research_layer.marc_r2_search.engine import R2Variant


def _finite(value: float) -> float | None:
    return float(value) if math.isfinite(float(value)) else None


def _summary(trades: Iterable[BacktestTrade]) -> dict[str, object]:
    items = tuple(trades)
    gross = [trade.gross_r for trade in items]
    base = [trade.base_net_r for trade in items]
    stress = [trade.stress_net_r for trade in items]

    def stats(values: list[float]) -> dict[str, object]:
        if not values:
            return {
                "expectancy_r": None,
                "profit_factor": None,
                "total_r": None,
                "max_drawdown_r": None,
            }
        return {
            "expectancy_r": sum(values) / len(values),
            "profit_factor": _finite(profit_factor(values)),
            "total_r": sum(values),
            "max_drawdown_r": max_drawdown(values),
        }

    return {
        "trades": len(items),
        "gross": stats(gross),
        "base": stats(base),
        "stress": stats(stress),
        "tp1_rate": (
            None if not items else sum(trade.tp1_hit for trade in items) / len(items)
        ),
        "tp2_rate": (
            None if not items else sum(trade.tp2_hit for trade in items) / len(items)
        ),
        "early_thesis_exit_rate": (
            None
            if not items
            else sum(trade.terminal_reason == "EARLY_THESIS_EXIT" for trade in items)
            / len(items)
        ),
        "long_trades": sum(trade.direction == "LONG" for trade in items),
        "short_trades": sum(trade.direction == "SHORT" for trade in items),
    }


def summarize_windows(
    windows: tuple[BacktestWindowResult, ...],
) -> dict[str, object]:
    ordered = tuple(
        sorted(
            (trade for window in windows for trade in window.trades),
            key=lambda trade: (
                trade.entry_time,
                trade.symbol,
                trade.timeframe,
                trade.source_signal_id,
            ),
        )
    )
    by_stream = {}
    by_timeframe: dict[str, list[BacktestTrade]] = defaultdict(list)
    for window in windows:
        key = f"{window.symbol}:{window.timeframe}"
        by_stream[key] = _summary(window.trades)
        by_timeframe[window.timeframe].extend(window.trades)

    return {
        "overall": _summary(ordered),
        "by_stream": by_stream,
        "by_timeframe": {
            timeframe: _summary(
                sorted(
                    trades,
                    key=lambda trade: (
                        trade.entry_time,
                        trade.symbol,
                        trade.source_signal_id,
                    ),
                )
            )
            for timeframe, trades in sorted(by_timeframe.items())
        },
        "positive_base_streams": sum(
            1
            for value in by_stream.values()
            if value["base"]["expectancy_r"] is not None
            and value["base"]["expectancy_r"] > 0
        ),
        "stream_count": len(by_stream),
    }


def _passes_development(summary: dict[str, object]) -> bool:
    overall = summary["overall"]
    base = overall["base"]
    stress = overall["stress"]
    return bool(
        overall["trades"] >= 750
        and base["expectancy_r"] is not None
        and base["expectancy_r"] > 0
        and base["profit_factor"] is not None
        and base["profit_factor"] > 1.05
        and stress["expectancy_r"] is not None
        and stress["expectancy_r"] > 0
        and stress["profit_factor"] is not None
        and stress["profit_factor"] > 1.0
    )


def select_development_variant(
    summaries: dict[str, dict[str, object]],
) -> str | None:
    """Choose once, from development data only, using a frozen robustness gate."""
    eligible = [
        (name, summary)
        for name, summary in summaries.items()
        if name != R2Variant.R1_BASELINE.value and _passes_development(summary)
    ]
    if not eligible:
        return None
    eligible.sort(
        key=lambda item: (
            item[1]["overall"]["stress"]["expectancy_r"],
            item[1]["overall"]["base"]["expectancy_r"],
            item[0],
        ),
        reverse=True,
    )
    return eligible[0][0]


def _holdout_verdict(summary: dict[str, object]) -> dict[str, object]:
    overall = summary["overall"]
    base = overall["base"]
    stress = overall["stress"]
    tf = summary["by_timeframe"]
    reasons = []

    checks = {
        "trades_at_least_500": overall["trades"] >= 500,
        "base_expectancy_positive": (
            base["expectancy_r"] is not None and base["expectancy_r"] > 0
        ),
        "base_profit_factor_at_least_1_10": (
            base["profit_factor"] is not None and base["profit_factor"] >= 1.10
        ),
        "stress_expectancy_positive": (
            stress["expectancy_r"] is not None and stress["expectancy_r"] > 0
        ),
        "stress_profit_factor_at_least_1_03": (
            stress["profit_factor"] is not None and stress["profit_factor"] >= 1.03
        ),
        "positive_streams_at_least_6_of_10": (
            summary["stream_count"] >= 10 and summary["positive_base_streams"] >= 6
        ),
        "both_timeframes_positive_base": (
            all(
                timeframe in tf
                and tf[timeframe]["base"]["expectancy_r"] is not None
                and tf[timeframe]["base"]["expectancy_r"] > 0
                for timeframe in ("15m", "30m")
            )
        ),
    }
    for name, passed in checks.items():
        if not passed:
            reasons.append(name)
    qualified = all(checks.values())
    return {
        "qualified": qualified,
        "classification": (
            "MARC_R2_PURE_SETUP_CANDIDATE"
            if qualified
            else "MARC_R2_HOLDOUT_NOT_CONFIRMED"
        ),
        "checks": checks,
        "failed_checks": reasons,
        "runtime_approval": "DENIED_RESEARCH_ONLY",
    }


def build_causal_search_report(
    *,
    development: dict[str, tuple[BacktestWindowResult, ...]],
    selected_variant: str | None,
    holdout: tuple[BacktestWindowResult, ...] | None,
    protocol: dict[str, object],
) -> dict[str, object]:
    dev_summaries = {
        name: summarize_windows(windows)
        for name, windows in sorted(development.items())
    }
    expected = select_development_variant(dev_summaries)
    if expected != selected_variant:
        raise RuntimeError("selected variant does not match frozen development selector")

    holdout_summary = None
    holdout_verdict = {
        "qualified": False,
        "classification": "NO_DEVELOPMENT_VARIANT_PASSED",
        "checks": {},
        "failed_checks": ["development_gate"],
        "runtime_approval": "DENIED_RESEARCH_ONLY",
    }
    if selected_variant is not None:
        if holdout is None:
            raise ValueError("selected variant requires untouched holdout results")
        holdout_summary = summarize_windows(holdout)
        holdout_verdict = _holdout_verdict(holdout_summary)

    return {
        "schema": "MARC_R2_CAUSAL_SEARCH_V1",
        "protocol": protocol,
        "development": {
            "summaries": dev_summaries,
            "selection_gate": {
                "minimum_trades": 750,
                "base_expectancy": ">0",
                "base_profit_factor": ">1.05",
                "stress_expectancy": ">0",
                "stress_profit_factor": ">1.00",
                "selection": "highest stress expectancy among passing non-baseline variants",
            },
            "selected_variant": selected_variant,
        },
        "untouched_cross_sectional_holdout": {
            "summary": holdout_summary,
            "verdict": holdout_verdict,
        },
        "final_classification": holdout_verdict["classification"],
        "runtime_approval": "DENIED_RESEARCH_ONLY",
    }
