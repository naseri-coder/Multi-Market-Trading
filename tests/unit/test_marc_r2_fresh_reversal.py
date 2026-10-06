"""Tests for MARC R2 Fresh Reversal Transition setup."""

from __future__ import annotations

from decimal import Decimal

from research_layer.marc_r2_pure.engine import (
    FRT_MAX_CROSS_AGE_BARS,
    FRT_MIN_INITIAL_RISK_PCT,
    _risk_pct,
)
from research_layer.marc_r2_pure.report import _development_passes

D = Decimal


def test_frt_frozen_thresholds_are_explicit():
    assert FRT_MAX_CROSS_AGE_BARS == 3
    assert FRT_MIN_INITIAL_RISK_PCT == D("0.008")
    assert _risk_pct(D("100"), D("99.2")) == D("0.008")


def _summary(
    *,
    trades: int,
    base_exp: float,
    base_pf: float,
    stress_exp: float,
    stress_pf: float,
    positive_streams: int,
    positive_stress_streams: int = 3,
):
    return {
        "overall": {
            "trades": trades,
            "base": {
                "expectancy_r": base_exp,
                "profit_factor": base_pf,
            },
            "stress": {
                "expectancy_r": stress_exp,
                "profit_factor": stress_pf,
            },
        },
        "stream_count": 5,
        "positive_base_streams": positive_streams,
        "by_stream": {
            f"S{i}": {
                "stress": {
                    "expectancy_r": 0.05 if i < positive_stress_streams else -0.05
                }
            }
            for i in range(5)
        },
    }


def test_development_gate_requires_stress_robustness_and_stream_consistency():
    assert _development_passes(
        _summary(
            trades=250,
            base_exp=0.12,
            base_pf=1.20,
            stress_exp=0.05,
            stress_pf=1.08,
            positive_streams=4,
        )
    )
    assert not _development_passes(
        _summary(
            trades=250,
            base_exp=0.12,
            base_pf=1.20,
            stress_exp=-0.01,
            stress_pf=0.99,
            positive_streams=5,
        )
    )
