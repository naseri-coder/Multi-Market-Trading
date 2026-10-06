"""Frozen walk-forward directional morphology qualification for MARC R4."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import UTC, datetime
from typing import Iterable

from research_layer.marc_r4_morphology.features import MorphologyFRTTrade
from research_layer.statistics import max_drawdown, profit_factor

TEST_YEARS = (2023, 2024, 2025, 2026)
MORPHOLOGY_MIN_TRADES = 40
MORPHOLOGY_MIN_SUPPORTED_SYMBOLS = 3
MORPHOLOGY_SYMBOL_MIN_TRADES = 5


def _finite(value: float) -> float | None:
    return float(value) if math.isfinite(float(value)) else None


def _summary(records: Iterable[MorphologyFRTTrade]) -> dict[str, object]:
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


def _groups(records, key):
    grouped = defaultdict(list)
    for record in records:
        grouped[str(key(record))].append(record)
    return {
        name: tuple(sorted(items, key=lambda item: item.entry_time))
        for name, items in sorted(grouped.items())
    }


def _positive_supported_symbols(
    records: tuple[MorphologyFRTTrade, ...],
) -> int:
    count = 0
    for items in _groups(records, lambda item: item.symbol).values():
        if len(items) < MORPHOLOGY_SYMBOL_MIN_TRADES:
            continue
        summary = _summary(items)
        expectancy = summary["base"]["expectancy_r"]
        if expectancy is not None and expectancy > 0:
            count += 1
    return count


def _eligible_morphologies(
    train: tuple[MorphologyFRTTrade, ...],
) -> tuple[str, ...]:
    eligible = []
    for name, items in _groups(train, lambda item: item.morphology_class).items():
        summary = _summary(items)
        base = summary["base"]
        stress = summary["stress"]
        supported = _positive_supported_symbols(items)
        stress_pf_ok = (
            stress.get("profit_factor_infinite", False)
            or (
                stress["profit_factor"] is not None
                and stress["profit_factor"] >= 1.03
            )
        )
        if (
            summary["trades"] >= MORPHOLOGY_MIN_TRADES
            and base["expectancy_r"] is not None
            and base["expectancy_r"] > 0.05
            and stress["expectancy_r"] is not None
            and stress["expectancy_r"] > 0
            and stress_pf_ok
            and supported >= MORPHOLOGY_MIN_SUPPORTED_SYMBOLS
        ):
            eligible.append(name)
    return tuple(sorted(eligible))


def _year_start(year: int) -> datetime:
    return datetime(year, 1, 1, tzinfo=UTC)


def _year_end(year: int) -> datetime:
    return datetime(year + 1, 1, 1, tzinfo=UTC)


def _train_before(records, year: int):
    cutoff = _year_start(year)
    return tuple(item for item in records if item.entry_time < cutoff)


def _test_year(records, year: int):
    start = _year_start(year)
    end = _year_end(year)
    return tuple(item for item in records if start <= item.entry_time < end)


def _fold(
    *,
    year: int,
    train: tuple[MorphologyFRTTrade, ...],
    test: tuple[MorphologyFRTTrade, ...],
    eligible: tuple[str, ...],
) -> tuple[dict[str, object], tuple[MorphologyFRTTrade, ...]]:
    selected = tuple(item for item in test if item.morphology_class in eligible)
    return (
        {
            "test_year": year,
            "training_trades": len(train),
            "eligible_morphologies": list(eligible),
            "baseline_test": _summary(test),
            "eligible_test": _summary(selected),
        },
        selected,
    )


def _aggregate(
    *,
    folds: list[dict[str, object]],
    selected: tuple[MorphologyFRTTrade, ...],
    symbols: tuple[str, ...],
) -> dict[str, object]:
    by_symbol = {
        symbol: _summary(item for item in selected if item.symbol == symbol)
        for symbol in symbols
    }
    by_direction = {
        direction: _summary(item for item in selected if item.direction == direction)
        for direction in ("LONG", "SHORT")
    }
    by_morphology = {
        name: _summary(items)
        for name, items in _groups(selected, lambda item: item.morphology_class).items()
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
        "by_direction": by_direction,
        "by_morphology": by_morphology,
        "positive_base_symbols": positive_symbols,
        "symbol_count": len(symbols),
        "positive_base_folds": positive_folds,
        "fold_count": len(folds),
    }


def run_development_walkforward(
    *,
    records: tuple[MorphologyFRTTrade, ...],
    symbols: tuple[str, ...],
) -> dict[str, object]:
    folds = []
    selected_all = []
    policy_by_year: dict[str, list[str]] = {}

    for year in TEST_YEARS:
        train = _train_before(records, year)
        test = _test_year(records, year)
        eligible = _eligible_morphologies(train)
        payload, selected = _fold(
            year=year,
            train=train,
            test=test,
            eligible=eligible,
        )
        folds.append(payload)
        selected_all.extend(selected)
        policy_by_year[str(year)] = list(eligible)

    return {
        "folds": folds,
        "aggregate": _aggregate(
            folds=folds,
            selected=tuple(selected_all),
            symbols=symbols,
        ),
        "morphology_policy_by_year": policy_by_year,
    }


def run_holdout_walkforward(
    *,
    records: tuple[MorphologyFRTTrade, ...],
    symbols: tuple[str, ...],
    morphology_policy_by_year: dict[str, list[str]],
) -> dict[str, object]:
    folds = []
    selected_all = []

    for year in TEST_YEARS:
        train = _train_before(records, year)
        test = _test_year(records, year)
        del train  # holdout outcomes never select morphology policy
        eligible = tuple(morphology_policy_by_year.get(str(year), []))
        payload, selected = _fold(
            year=year,
            train=(),
            test=test,
            eligible=eligible,
        )
        folds.append(payload)
        selected_all.extend(selected)

    return {
        "folds": folds,
        "aggregate": _aggregate(
            folds=folds,
            selected=tuple(selected_all),
            symbols=symbols,
        ),
    }


def _pf_at_least(stats: dict[str, object], threshold: float) -> bool:
    return bool(
        stats.get("profit_factor_infinite", False)
        or (
            stats["profit_factor"] is not None
            and stats["profit_factor"] >= threshold
        )
    )


def development_gate(payload: dict[str, object]) -> dict[str, object]:
    aggregate = payload["aggregate"]
    overall = aggregate["overall"]
    checks = {
        "trades_at_least_150": overall["trades"] >= 150,
        "base_expectancy_positive": (
            overall["base"]["expectancy_r"] is not None
            and overall["base"]["expectancy_r"] > 0
        ),
        "base_pf_at_least_1_10": _pf_at_least(overall["base"], 1.10),
        "stress_expectancy_positive": (
            overall["stress"]["expectancy_r"] is not None
            and overall["stress"]["expectancy_r"] > 0
        ),
        "stress_pf_at_least_1_03": _pf_at_least(overall["stress"], 1.03),
        "positive_folds_at_least_3_of_4": aggregate["positive_base_folds"] >= 3,
        "positive_symbols_at_least_6_of_10": aggregate["positive_base_symbols"] >= 6,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "failed_checks": [name for name, passed in checks.items() if not passed],
    }


def holdout_gate(payload: dict[str, object]) -> dict[str, object]:
    aggregate = payload["aggregate"]
    overall = aggregate["overall"]
    checks = {
        "trades_at_least_75": overall["trades"] >= 75,
        "base_expectancy_positive": (
            overall["base"]["expectancy_r"] is not None
            and overall["base"]["expectancy_r"] > 0
        ),
        "base_pf_at_least_1_10": _pf_at_least(overall["base"], 1.10),
        "stress_expectancy_positive": (
            overall["stress"]["expectancy_r"] is not None
            and overall["stress"]["expectancy_r"] > 0
        ),
        "stress_pf_at_least_1_03": _pf_at_least(overall["stress"], 1.03),
        "positive_folds_at_least_3_of_4": aggregate["positive_base_folds"] >= 3,
        "positive_symbols_at_least_3_of_5": aggregate["positive_base_symbols"] >= 3,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "failed_checks": [name for name, passed in checks.items() if not passed],
    }


def build_r4_report(
    *,
    development: dict[str, object],
    holdout: dict[str, object] | None,
    protocol: dict[str, object],
) -> dict[str, object]:
    dev_gate = development_gate(development)
    if dev_gate["passed"] and holdout is None:
        raise ValueError("passing R4 development requires untouched holdout")
    if not dev_gate["passed"] and holdout is not None:
        raise ValueError("R4 holdout must remain unopened after development failure")

    hold_gate = None
    classification = "MARC_R4_DEVELOPMENT_FAILED"
    if holdout is not None:
        hold_gate = holdout_gate(holdout)
        classification = (
            "MARC_R4_MORPHOLOGY_CANDIDATE"
            if hold_gate["passed"]
            else "MARC_R4_HOLDOUT_NOT_CONFIRMED"
        )

    return {
        "schema": "MARC_R4_MORPHOLOGY_DIRECTIONAL_QUALIFICATION_V1",
        "protocol": protocol,
        "development": {**development, "gate": dev_gate},
        "untouched_cross_sectional_holdout": (
            None if holdout is None else {**holdout, "gate": hold_gate}
        ),
        "final_classification": classification,
        "runtime_approval": "DENIED_RESEARCH_ONLY",
    }
