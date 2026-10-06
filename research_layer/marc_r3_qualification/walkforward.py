"""Frozen walk-forward eligibility logic for MARC R3."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import UTC, datetime
from typing import Iterable

from research_layer.marc_r3_qualification.features import QualifiedFRTTrade
from research_layer.statistics import max_drawdown, profit_factor

TEST_YEARS = (2023, 2024, 2025, 2026)
CELL_MIN_TRADES = 30
SYMBOL_MIN_TRADES = 15


def _finite(value: float) -> float | None:
    return float(value) if math.isfinite(float(value)) else None


def _summary(records: Iterable[QualifiedFRTTrade]) -> dict[str, object]:
    items = tuple(sorted(records, key=lambda item: (item.entry_time, item.symbol)))
    gross = [item.gross_r for item in items]
    base = [item.base_net_r for item in items]
    stress = [item.stress_net_r for item in items]

    def stats(values: list[float]) -> dict[str, object]:
        if not values:
            return {
                "expectancy_r": None,
                "profit_factor": None,
                "profit_factor_infinite": False,
                "total_r": None,
                "max_drawdown_r": None,
            }
        pf = profit_factor(values)
        return {
            "expectancy_r": sum(values) / len(values),
            "profit_factor": _finite(pf),
            "profit_factor_infinite": math.isinf(pf),
            "total_r": sum(values),
            "max_drawdown_r": max_drawdown(values),
        }

    return {
        "trades": len(items),
        "gross": stats(gross),
        "base": stats(base),
        "stress": stats(stress),
        "long_trades": sum(item.direction == "LONG" for item in items),
        "short_trades": sum(item.direction == "SHORT" for item in items),
    }


def _groups(
    records: Iterable[QualifiedFRTTrade],
    key,
) -> dict[str, tuple[QualifiedFRTTrade, ...]]:
    output: dict[str, list[QualifiedFRTTrade]] = defaultdict(list)
    for record in records:
        output[str(key(record))].append(record)
    return {
        name: tuple(sorted(items, key=lambda item: item.entry_time))
        for name, items in sorted(output.items())
    }


def _eligible_cells(
    train: tuple[QualifiedFRTTrade, ...],
) -> tuple[str, ...]:
    eligible = []
    for cell, items in _groups(train, lambda item: item.regime_cell).items():
        summary = _summary(items)
        base = summary["base"]
        stress = summary["stress"]
        if (
            summary["trades"] >= CELL_MIN_TRADES
            and base["expectancy_r"] is not None
            and base["expectancy_r"] > 0.05
            and stress["expectancy_r"] is not None
            and stress["expectancy_r"] > 0
            and (
                stress.get("profit_factor_infinite", False)
                or (
                    stress["profit_factor"] is not None
                    and stress["profit_factor"] >= 1.03
                )
            )
        ):
            eligible.append(cell)
    return tuple(sorted(eligible))


def _eligible_symbols(
    train: tuple[QualifiedFRTTrade, ...],
) -> tuple[str, ...]:
    eligible = []
    for symbol, items in _groups(train, lambda item: item.symbol).items():
        summary = _summary(items)
        base = summary["base"]
        stress = summary["stress"]
        if (
            summary["trades"] >= SYMBOL_MIN_TRADES
            and base["expectancy_r"] is not None
            and base["expectancy_r"] > 0
            and (
                base.get("profit_factor_infinite", False)
                or (
                    base["profit_factor"] is not None
                    and base["profit_factor"] >= 1.05
                )
            )
            and stress["expectancy_r"] is not None
            and stress["expectancy_r"] > 0
        ):
            eligible.append(symbol)
    return tuple(sorted(eligible))


def _year_start(year: int) -> datetime:
    return datetime(year, 1, 1, tzinfo=UTC)


def _year_end(year: int) -> datetime:
    return datetime(year + 1, 1, 1, tzinfo=UTC)


def _train_before(
    records: tuple[QualifiedFRTTrade, ...],
    year: int,
) -> tuple[QualifiedFRTTrade, ...]:
    cutoff = _year_start(year)
    return tuple(item for item in records if item.entry_time < cutoff)


def _test_year(
    records: tuple[QualifiedFRTTrade, ...],
    year: int,
) -> tuple[QualifiedFRTTrade, ...]:
    start = _year_start(year)
    end = _year_end(year)
    return tuple(item for item in records if start <= item.entry_time < end)


def _fold_payload(
    *,
    year: int,
    train: tuple[QualifiedFRTTrade, ...],
    test: tuple[QualifiedFRTTrade, ...],
    cells: tuple[str, ...],
    symbols: tuple[str, ...],
) -> tuple[dict[str, object], tuple[QualifiedFRTTrade, ...]]:
    selected = tuple(
        item
        for item in test
        if item.regime_cell in cells and item.symbol in symbols
    )
    return (
        {
            "test_year": year,
            "training_trades": len(train),
            "eligible_regime_cells": list(cells),
            "eligible_symbols": list(symbols),
            "baseline_test": _summary(test),
            "eligible_test": _summary(selected),
        },
        selected,
    )


def _aggregate_payload(
    *,
    folds: list[dict[str, object]],
    selected: tuple[QualifiedFRTTrade, ...],
    universe_symbols: tuple[str, ...],
) -> dict[str, object]:
    by_symbol = {
        symbol: _summary(item for item in selected if item.symbol == symbol)
        for symbol in universe_symbols
    }
    positive_symbols = sum(
        payload["trades"] > 0
        and payload["base"]["expectancy_r"] is not None
        and payload["base"]["expectancy_r"] > 0
        for payload in by_symbol.values()
    )
    positive_folds = sum(
        fold["eligible_test"]["trades"] > 0
        and fold["eligible_test"]["base"]["expectancy_r"] is not None
        and fold["eligible_test"]["base"]["expectancy_r"] > 0
        for fold in folds
    )
    return {
        "overall": _summary(selected),
        "by_symbol": by_symbol,
        "positive_base_symbols": positive_symbols,
        "symbol_count": len(universe_symbols),
        "positive_base_folds": positive_folds,
        "fold_count": len(folds),
    }


def run_development_walkforward(
    *,
    records: tuple[QualifiedFRTTrade, ...],
    universe_symbols: tuple[str, ...],
) -> dict[str, object]:
    """Select regime cells and instruments from past shadow trades only."""
    folds = []
    all_selected: list[QualifiedFRTTrade] = []
    regime_policy_by_year: dict[str, list[str]] = {}

    for year in TEST_YEARS:
        train = _train_before(records, year)
        test = _test_year(records, year)
        cells = _eligible_cells(train)
        symbols = _eligible_symbols(train)
        payload, selected = _fold_payload(
            year=year,
            train=train,
            test=test,
            cells=cells,
            symbols=symbols,
        )
        folds.append(payload)
        all_selected.extend(selected)
        regime_policy_by_year[str(year)] = list(cells)

    aggregate = _aggregate_payload(
        folds=folds,
        selected=tuple(all_selected),
        universe_symbols=universe_symbols,
    )
    return {
        "folds": folds,
        "aggregate": aggregate,
        "regime_policy_by_year": regime_policy_by_year,
    }


def run_holdout_walkforward(
    *,
    records: tuple[QualifiedFRTTrade, ...],
    universe_symbols: tuple[str, ...],
    regime_policy_by_year: dict[str, list[str]],
) -> dict[str, object]:
    """Apply development-frozen regime cells; adapt only symbol eligibility causally."""
    folds = []
    all_selected: list[QualifiedFRTTrade] = []

    for year in TEST_YEARS:
        train = _train_before(records, year)
        test = _test_year(records, year)
        cells = tuple(regime_policy_by_year.get(str(year), []))
        symbols = _eligible_symbols(train)
        payload, selected = _fold_payload(
            year=year,
            train=train,
            test=test,
            cells=cells,
            symbols=symbols,
        )
        folds.append(payload)
        all_selected.extend(selected)

    aggregate = _aggregate_payload(
        folds=folds,
        selected=tuple(all_selected),
        universe_symbols=universe_symbols,
    )
    return {"folds": folds, "aggregate": aggregate}


def _development_gate(payload: dict[str, object]) -> dict[str, object]:
    aggregate = payload["aggregate"]
    overall = aggregate["overall"]
    checks = {
        "trades_at_least_150": overall["trades"] >= 150,
        "base_expectancy_positive": (
            overall["base"]["expectancy_r"] is not None
            and overall["base"]["expectancy_r"] > 0
        ),
        "base_pf_at_least_1_10": (
            overall["base"].get("profit_factor_infinite", False)
            or (
                overall["base"]["profit_factor"] is not None
                and overall["base"]["profit_factor"] >= 1.10
            )
        ),
        "stress_expectancy_positive": (
            overall["stress"]["expectancy_r"] is not None
            and overall["stress"]["expectancy_r"] > 0
        ),
        "stress_pf_at_least_1_03": (
            overall["stress"].get("profit_factor_infinite", False)
            or (
                overall["stress"]["profit_factor"] is not None
                and overall["stress"]["profit_factor"] >= 1.03
            )
        ),
        "positive_folds_at_least_3_of_4": aggregate["positive_base_folds"] >= 3,
        "positive_symbols_at_least_6_of_10": aggregate["positive_base_symbols"] >= 6,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "failed_checks": [name for name, passed in checks.items() if not passed],
    }


def _holdout_gate(payload: dict[str, object]) -> dict[str, object]:
    aggregate = payload["aggregate"]
    overall = aggregate["overall"]
    checks = {
        "trades_at_least_75": overall["trades"] >= 75,
        "base_expectancy_positive": (
            overall["base"]["expectancy_r"] is not None
            and overall["base"]["expectancy_r"] > 0
        ),
        "base_pf_at_least_1_10": (
            overall["base"].get("profit_factor_infinite", False)
            or (
                overall["base"]["profit_factor"] is not None
                and overall["base"]["profit_factor"] >= 1.10
            )
        ),
        "stress_expectancy_positive": (
            overall["stress"]["expectancy_r"] is not None
            and overall["stress"]["expectancy_r"] > 0
        ),
        "stress_pf_at_least_1_03": (
            overall["stress"].get("profit_factor_infinite", False)
            or (
                overall["stress"]["profit_factor"] is not None
                and overall["stress"]["profit_factor"] >= 1.03
            )
        ),
        "positive_folds_at_least_3_of_4": aggregate["positive_base_folds"] >= 3,
        "positive_symbols_at_least_3_of_5": aggregate["positive_base_symbols"] >= 3,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "failed_checks": [name for name, passed in checks.items() if not passed],
    }


def build_r3_report(
    *,
    development: dict[str, object],
    holdout: dict[str, object] | None,
    protocol: dict[str, object],
) -> dict[str, object]:
    dev_gate = _development_gate(development)
    if dev_gate["passed"] and holdout is None:
        raise ValueError("passing R3 development requires untouched holdout")
    if not dev_gate["passed"] and holdout is not None:
        raise ValueError("R3 holdout must remain unopened after development failure")

    hold_gate = None
    classification = "MARC_R3_DEVELOPMENT_FAILED"
    if holdout is not None:
        hold_gate = _holdout_gate(holdout)
        classification = (
            "MARC_R3_ELIGIBILITY_CANDIDATE"
            if hold_gate["passed"]
            else "MARC_R3_HOLDOUT_NOT_CONFIRMED"
        )

    return {
        "schema": "MARC_R3_REGIME_INSTRUMENT_QUALIFICATION_V1",
        "protocol": protocol,
        "development": {
            **development,
            "gate": dev_gate,
        },
        "untouched_cross_sectional_holdout": (
            None
            if holdout is None
            else {
                **holdout,
                "gate": hold_gate,
            }
        ),
        "final_classification": classification,
        "runtime_approval": "DENIED_RESEARCH_ONLY",
    }
