"""Tests for MARC R2 FRT v0.2 execution viability."""

from __future__ import annotations

from decimal import Decimal

from research_layer.marc_backtest.engine import BacktestConfig
from research_layer.marc_r2_frt_v2.engine import (
    FRT_MAX_STRESS_DRAG_R,
    _execution_viable,
    _stress_roundtrip_drag_r,
)

D = Decimal


def test_frt_v2_cost_budget_is_frozen_at_quarter_r():
    assert FRT_MAX_STRESS_DRAG_R == D("0.25")
    assert _stress_roundtrip_drag_r(
        entry=D("100"),
        stop=D("99.20"),
        stress_cost_bps_per_side=10.0,
    ) == D("0.25")


def test_frt_v2_execution_gate_rejects_too_tight_stop():
    config = BacktestConfig(stress_cost_bps_per_side=10.0)

    assert _execution_viable(
        entry=D("100"),
        stop=D("99.20"),
        config=config,
    )
    assert not _execution_viable(
        entry=D("100"),
        stop=D("99.21"),
        config=config,
    )
