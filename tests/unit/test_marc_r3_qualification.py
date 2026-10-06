"""Tests for MARC R3 walk-forward qualification."""

from __future__ import annotations

from datetime import UTC, datetime

from research_layer.marc_r3_qualification.features import (
    EFFICIENCY_TREND_THRESHOLD,
    _volatility_bucket,
)
from research_layer.marc_r3_qualification.walkforward import (
    _development_gate,
    run_development_walkforward,
)
from research_layer.marc_r3_qualification.features import QualifiedFRTTrade


def _record(
    *,
    symbol: str,
    year: int,
    regime: str,
    base: float,
    stress: float,
    gross: float | None = None,
) -> QualifiedFRTTrade:
    vol, structure = regime.split("_", 1)
    return QualifiedFRTTrade(
        symbol=symbol,
        entry_time=datetime(year, 6, 1, tzinfo=UTC),
        direction="LONG",
        regime_cell=regime,
        volatility_bucket=vol,
        atr_percentile=0.5,
        structure_bucket=structure,
        efficiency_ratio=0.5,
        initial_risk_pct=0.01,
        gross_r=base + 0.1 if gross is None else gross,
        base_net_r=base,
        stress_net_r=stress,
        source_signal_id=f"{symbol}-{year}-{regime}-{base}",
    )


def test_regime_thresholds_are_frozen():
    from decimal import Decimal

    assert EFFICIENCY_TREND_THRESHOLD == Decimal("0.35")
    assert _volatility_bucket(Decimal("0.10")) == "LOW"
    assert _volatility_bucket(Decimal("0.50")) == "MID"
    assert _volatility_bucket(Decimal("0.90")) == "HIGH"


def test_walkforward_never_uses_test_year_to_choose_policy():
    records = []
    symbols = ("A", "B")

    # 2022 training makes HIGH_TREND eligible and both symbols eligible.
    for symbol in symbols:
        for index in range(20):
            records.append(
                _record(
                    symbol=symbol,
                    year=2022,
                    regime="HIGH_TREND",
                    base=0.3,
                    stress=0.2,
                    gross=0.4,
                )
            )

    # 2023 has disastrous outcomes. They must not alter the policy used for 2023.
    for symbol in symbols:
        for index in range(10):
            records.append(
                _record(
                    symbol=symbol,
                    year=2023,
                    regime="HIGH_TREND",
                    base=-1.0,
                    stress=-1.1,
                    gross=-0.9,
                )
            )

    result = run_development_walkforward(
        records=tuple(records),
        universe_symbols=symbols,
    )
    fold_2023 = next(fold for fold in result["folds"] if fold["test_year"] == 2023)

    assert fold_2023["eligible_regime_cells"] == ["HIGH_TREND"]
    assert fold_2023["eligible_symbols"] == ["A", "B"]
    assert fold_2023["eligible_test"]["trades"] == 20
    assert fold_2023["eligible_test"]["base"]["expectancy_r"] == -1.0


def test_development_gate_requires_cross_fold_and_cross_symbol_robustness():
    payload = {
        "aggregate": {
            "overall": {
                "trades": 200,
                "base": {"expectancy_r": 0.1, "profit_factor": 1.2},
                "stress": {"expectancy_r": 0.03, "profit_factor": 1.06},
            },
            "positive_base_folds": 3,
            "fold_count": 4,
            "positive_base_symbols": 6,
            "symbol_count": 10,
        }
    }

    assert _development_gate(payload)["passed"] is True

    payload["aggregate"]["positive_base_symbols"] = 5
    gate = _development_gate(payload)
    assert gate["passed"] is False
    assert "positive_symbols_at_least_6_of_10" in gate["failed_checks"]



def test_holdout_gate_accepts_true_infinite_profit_factor():
    from research_layer.marc_r3_qualification.walkforward import _holdout_gate

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

    assert _holdout_gate(payload)["passed"] is True
