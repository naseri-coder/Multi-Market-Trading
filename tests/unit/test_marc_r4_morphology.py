"""Tests for MARC R4 directional setup morphology qualification."""

from __future__ import annotations

from datetime import UTC, datetime

from research_layer.marc_r4_morphology.features import (
    CONFIRMATION_CLOSE_LOCATION_MIN,
    IMPULSE_MIN_ATR,
    MAX_EXTENSION_ATR,
    SPREAD_MIN_ATR,
    MorphologyFRTTrade,
    _morphology_class,
)
from research_layer.marc_r4_morphology.walkforward import (
    _eligible_morphologies,
    holdout_gate,
    run_development_walkforward,
    run_holdout_walkforward,
)


def _record(
    *,
    symbol: str,
    year: int,
    morphology: str,
    base: float,
    stress: float,
    index: int,
) -> MorphologyFRTTrade:
    direction = morphology.split("_", 1)[0]
    return MorphologyFRTTrade(
        symbol=symbol,
        entry_time=datetime(year, 6, min(index + 1, 28), tzinfo=UTC),
        direction=direction,
        morphology_class=morphology,
        quality_score=4 if morphology.endswith("_A") else 3,
        impulse_3_atr=0.8,
        spread_atr=0.2,
        spread_expansion_2_atr=0.1,
        confirmation_close_location=0.8,
        confirmation_bodies_directional=True,
        extension_atr=0.4,
        initial_risk_pct=0.01,
        gross_r=base + 0.1,
        base_net_r=base,
        stress_net_r=stress,
        source_signal_id=f"{symbol}-{year}-{morphology}-{index}",
    )


def test_morphology_thresholds_and_classes_are_frozen():
    from decimal import Decimal

    assert IMPULSE_MIN_ATR == Decimal("0.50")
    assert SPREAD_MIN_ATR == Decimal("0.10")
    assert CONFIRMATION_CLOSE_LOCATION_MIN == Decimal("0.65")
    assert MAX_EXTENSION_ATR == Decimal("0.75")
    assert _morphology_class("LONG", 4) == "LONG_A"
    assert _morphology_class("LONG", 3) == "LONG_B"
    assert _morphology_class("SHORT", 2) == "SHORT_C"


def test_morphology_requires_cross_symbol_support():
    records = []
    for symbol in ("A", "B"):
        for index in range(25):
            records.append(
                _record(
                    symbol=symbol,
                    year=2022,
                    morphology="LONG_A",
                    base=0.3,
                    stress=0.2,
                    index=index,
                )
            )

    assert _eligible_morphologies(tuple(records)) == ()

    for index in range(5):
        records.append(
            _record(
                symbol="C",
                year=2022,
                morphology="LONG_A",
                base=0.3,
                stress=0.2,
                index=index,
            )
        )

    assert _eligible_morphologies(tuple(records)) == ("LONG_A",)


def test_walkforward_policy_is_fixed_before_test_year():
    records = []
    symbols = ("A", "B", "C")

    for symbol in symbols:
        for index in range(15):
            records.append(
                _record(
                    symbol=symbol,
                    year=2022,
                    morphology="LONG_A",
                    base=0.3,
                    stress=0.2,
                    index=index,
                )
            )

    for symbol in symbols:
        for index in range(5):
            records.append(
                _record(
                    symbol=symbol,
                    year=2023,
                    morphology="LONG_A",
                    base=-1.0,
                    stress=-1.1,
                    index=index,
                )
            )

    result = run_development_walkforward(
        records=tuple(records),
        symbols=symbols,
    )
    fold = next(item for item in result["folds"] if item["test_year"] == 2023)

    assert fold["eligible_morphologies"] == ["LONG_A"]
    assert fold["eligible_test"]["trades"] == 15
    assert fold["eligible_test"]["base"]["expectancy_r"] == -1.0


def test_holdout_uses_development_frozen_policy_without_adaptation():
    records = []
    for index in range(10):
        records.append(
            _record(
                symbol="H",
                year=2023,
                morphology="SHORT_B",
                base=0.5,
                stress=0.4,
                index=index,
            )
        )
        records.append(
            _record(
                symbol="H",
                year=2023,
                morphology="LONG_A",
                base=-1.0,
                stress=-1.1,
                index=index + 10,
            )
        )

    result = run_holdout_walkforward(
        records=tuple(records),
        symbols=("H",),
        morphology_policy_by_year={
            "2023": ["LONG_A"],
            "2024": [],
            "2025": [],
            "2026": [],
        },
    )
    fold = next(item for item in result["folds"] if item["test_year"] == 2023)

    assert fold["eligible_morphologies"] == ["LONG_A"]
    assert fold["eligible_test"]["trades"] == 10
    assert fold["eligible_test"]["base"]["expectancy_r"] == -1.0


def test_holdout_gate_accepts_true_infinite_profit_factor():
    payload = {
        "aggregate": {
            "overall": {
                "trades": 100,
                "base": {
                    "expectancy_r": 0.2,
                    "profit_factor": None,
                    "profit_factor_infinite": True,
                },
                "stress": {
                    "expectancy_r": 0.1,
                    "profit_factor": None,
                    "profit_factor_infinite": True,
                },
            },
            "positive_base_folds": 4,
            "fold_count": 4,
            "positive_base_symbols": 5,
            "symbol_count": 5,
        }
    }

    assert holdout_gate(payload)["passed"] is True
