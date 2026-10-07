"""Metrics for FM research backtests."""

from __future__ import annotations

import math
from typing import Iterable

from research_layer.fm_backtest.engine import FMTrade


def _pf(values: list[float]) -> float | None:
    gains = sum(v for v in values if v > 0)
    losses = -sum(v for v in values if v < 0)
    if losses == 0:
        return None if gains == 0 else math.inf
    return gains / losses


def _max_dd(values: Iterable[float]) -> float:
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        worst = max(worst, peak - equity)
    return worst


def summarize(trades: tuple[FMTrade, ...]) -> dict[str, object]:
    base = [trade.base_net_r for trade in trades]
    stress = [trade.stress_net_r for trade in trades]
    gross = [trade.gross_r for trade in trades]

    def metrics(values: list[float]) -> dict[str, object]:
        if not values:
            return {
                "expectancy_r": None,
                "profit_factor": None,
                "total_r": 0.0,
                "max_drawdown_r": 0.0,
            }
        pf = _pf(values)
        return {
            "expectancy_r": sum(values) / len(values),
            "profit_factor": None if pf is not None and math.isinf(pf) else pf,
            "profit_factor_infinite": bool(pf is not None and math.isinf(pf)),
            "total_r": sum(values),
            "max_drawdown_r": _max_dd(values),
        }

    return {
        "trades": len(trades),
        "wins_base": sum(v > 0 for v in base),
        "losses_base": sum(v <= 0 for v in base),
        "win_rate_base": (sum(v > 0 for v in base) / len(base)) if base else None,
        "long_trades": sum(t.direction == "LONG" for t in trades),
        "short_trades": sum(t.direction == "SHORT" for t in trades),
        "tp1": sum(t.outcome == "TP1" for t in trades),
        "stops": sum(t.outcome in {"STOP", "STOP_FIRST_AMBIGUOUS"} for t in trades),
        "gross": metrics(gross),
        "base": metrics(base),
        "stress": metrics(stress),
    }
