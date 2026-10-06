"""Tests for the pre-registered MARC R2 causal search."""

from __future__ import annotations

from decimal import Decimal

from app.modules.marc_core.policy import MARCPolicy
from research_layer.marc_r2_search.engine import R2Variant, _failure_on_close
from research_layer.marc_r2_search.report import select_development_variant

D = Decimal


def test_early_ma99_loss_and_opposite_band_are_distinct_causal_rules():
    policy = MARCPolicy()

    assert _failure_on_close(
        variant=R2Variant.EARLY_MA99_LOSS_3,
        direction="LONG",
        close=D("99.95"),
        ma99=D("100"),
        atr14=D("1"),
        policy=policy,
    )
    assert not _failure_on_close(
        variant=R2Variant.EARLY_OPPOSITE_BAND_3,
        direction="LONG",
        close=D("99.95"),
        ma99=D("100"),
        atr14=D("1"),
        policy=policy,
    )
    assert _failure_on_close(
        variant=R2Variant.EARLY_OPPOSITE_BAND_3,
        direction="LONG",
        close=D("99.89"),
        ma99=D("100"),
        atr14=D("1"),
        policy=policy,
    )


def test_short_failure_rules_are_exact_mirrors():
    policy = MARCPolicy()

    assert _failure_on_close(
        variant=R2Variant.EARLY_MA99_LOSS_3,
        direction="SHORT",
        close=D("100.01"),
        ma99=D("100"),
        atr14=D("1"),
        policy=policy,
    )
    assert _failure_on_close(
        variant=R2Variant.EARLY_OPPOSITE_BAND_3,
        direction="SHORT",
        close=D("100.11"),
        ma99=D("100"),
        atr14=D("1"),
        policy=policy,
    )


def _summary(*, trades: int, base_exp: float, base_pf: float, stress_exp: float, stress_pf: float):
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
        }
    }


def test_selector_never_selects_baseline_and_prefers_stress_robustness():
    summaries = {
        R2Variant.R1_BASELINE.value: _summary(
            trades=3000,
            base_exp=1.0,
            base_pf=2.0,
            stress_exp=0.9,
            stress_pf=1.9,
        ),
        R2Variant.EARLY_MA99_LOSS_3.value: _summary(
            trades=1500,
            base_exp=0.15,
            base_pf=1.20,
            stress_exp=0.05,
            stress_pf=1.08,
        ),
        R2Variant.EARLY_OPPOSITE_BAND_3.value: _summary(
            trades=1600,
            base_exp=0.12,
            base_pf=1.18,
            stress_exp=0.08,
            stress_pf=1.10,
        ),
        R2Variant.HOLD_MA99_3_THEN_ENTER.value: _summary(
            trades=600,
            base_exp=0.30,
            base_pf=1.40,
            stress_exp=0.20,
            stress_pf=1.30,
        ),
    }

    selected = select_development_variant(summaries)

    assert selected == R2Variant.EARLY_OPPOSITE_BAND_3.value


def test_selector_returns_none_when_no_variant_passes_frozen_gate():
    summaries = {
        R2Variant.R1_BASELINE.value: _summary(
            trades=3000,
            base_exp=0.2,
            base_pf=1.2,
            stress_exp=0.1,
            stress_pf=1.1,
        ),
        R2Variant.EARLY_MA99_LOSS_3.value: _summary(
            trades=1000,
            base_exp=0.1,
            base_pf=1.1,
            stress_exp=-0.01,
            stress_pf=0.99,
        ),
        R2Variant.EARLY_OPPOSITE_BAND_3.value: _summary(
            trades=1000,
            base_exp=-0.01,
            base_pf=0.99,
            stress_exp=-0.1,
            stress_pf=0.8,
        ),
        R2Variant.HOLD_MA99_3_THEN_ENTER.value: _summary(
            trades=700,
            base_exp=0.3,
            base_pf=1.4,
            stress_exp=0.2,
            stress_pf=1.3,
        ),
    }

    assert select_development_variant(summaries) is None
