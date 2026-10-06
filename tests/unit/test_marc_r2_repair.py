"""Tests for MARC R2 exit-repair experiments."""

from __future__ import annotations

from decimal import Decimal

from research_layer.marc_backtest.engine import BacktestConfig
from research_layer.marc_r2_repair.engine import (
    _cost_budget_passes,
    _stress_roundtrip_drag_r,
)
from research_layer.marc_r2_repair.report import select_variant

D = Decimal


def test_stress_cost_budget_is_pre_entry_and_exact():
    drag = _stress_roundtrip_drag_r(
        entry=D("100"),
        stop=D("99.20"),
        stress_cost_bps_per_side=10.0,
    )

    assert drag == D("0.25")
    assert _cost_budget_passes(
        entry=D("100"),
        stop=D("99.20"),
        config=BacktestConfig(stress_cost_bps_per_side=10.0),
    )
    assert not _cost_budget_passes(
        entry=D("100"),
        stop=D("99.30"),
        config=BacktestConfig(stress_cost_bps_per_side=10.0),
    )


def _summary(
    *,
    trades: int,
    base_exp: float,
    base_pf: float,
    stress_exp: float,
    stress_pf: float,
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
        }
    }


def test_exit_repair_selector_ignores_baseline_and_prefers_stress_edge():
    summaries = {
        "R1_BASELINE": _summary(
            trades=5000,
            base_exp=1.0,
            base_pf=2.0,
            stress_exp=0.9,
            stress_pf=1.9,
        ),
        "PARTIAL25_BE_AFTER_1R": _summary(
            trades=4000,
            base_exp=0.08,
            base_pf=1.10,
            stress_exp=0.02,
            stress_pf=1.02,
        ),
        "FULL_BE_AFTER_1R_TP2_50_RUNNER50": _summary(
            trades=4000,
            base_exp=0.12,
            base_pf=1.15,
            stress_exp=0.06,
            stress_pf=1.08,
        ),
        "FULL_BE_TP2_50_RUNNER50_COST_BUDGET": _summary(
            trades=900,
            base_exp=0.20,
            base_pf=1.25,
            stress_exp=0.10,
            stress_pf=1.15,
        ),
    }

    assert (
        select_variant(summaries)
        == "FULL_BE_TP2_50_RUNNER50_COST_BUDGET"
    )
