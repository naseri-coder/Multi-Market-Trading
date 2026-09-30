"""Causal Chapter 6 diagnostic observations remain outside executable trade flow."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from app.modules.brooks_core.books_full_patterns import (
    detect_micro_double_top_bottom,
    scan_chapter6_diagnostic_observations,
)
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.market_data.entities import Candle, MarketSnapshot

START = datetime(2026, 9, 1, tzinfo=UTC)
POLICY = BrooksFullCorePolicy()


def bar(index: int, o: int, high: int, low: int, close: int) -> Candle:
    start = START + timedelta(minutes=15 * index)
    return Candle(
        start, start + timedelta(minutes=15),
        D(o), D(high), D(low), D(close), D(1),
    )


def snapshot(bars: tuple[Candle, ...]) -> MarketSnapshot:
    return MarketSnapshot(
        "binance", "futures", "BTCUSDT", "15m", bars,
        bars[-1].close_time, "CH6_TEST",
    )


def context(regime: str = "TRADING_RANGE", always_in: str = "UNRESOLVED"):
    return SimpleNamespace(
        regime=regime,
        always_in=always_in,
        structure_direction=regime,
        breakout_direction="UNRESOLVED",
        breakout_streak=0,
        metrics=SimpleNamespace(bar_overlap_rate=D("0.5")),
    )


def observations(bars: tuple[Candle, ...], ctx):
    return scan_chapter6_diagnostic_observations(snapshot(bars), ctx, POLICY)


def find(bars: tuple[Candle, ...], ctx, name: str):
    return next(x for x in observations(bars, ctx) if x.pattern_name == name)


@pytest.mark.parametrize(
    ("direction", "first", "second"),
    [
        ("LONG", (105, 106, 99, 99), (99, 105, 98, 104)),
        ("SHORT", (99, 105, 98, 104), (104, 105, 98, 99)),
    ],
)
def test_pair_identity_boundaries_and_overlap(direction, first, second):
    bars = tuple(bar(i, *values) for i, values in enumerate((first, second)))
    observation = find(bars, context(), "CH6_TWO_BAR_PAIR")
    data = dict(observation.metadata)
    assert observation.direction == direction
    assert data["pair_identity"] == f"TWO_BAR_REVERSAL:0:1:{direction}"
    assert (data["first_high"], data["first_low"]) == (str(first[1]), str(first[2]))
    assert (data["second_high"], data["second_low"]) == (str(second[1]), str(second[2]))
    assert data["pair_high"] == str(max(first[1], second[1]))
    assert data["pair_low"] == str(min(first[2], second[2]))
    assert data["ranges_overlap"] == "true"
    assert data["trade_eligible"] == "false"
    assert observation.source_rule_ids == ()


@pytest.mark.parametrize(
    ("side", "regime", "always_in", "first", "second"),
    [
        ("TOP", "BULL_TREND", "LONG", (100, 105, 99, 105), (104, 106, 104, 106)),
        ("BOTTOM", "BEAR_TREND", "SHORT", (106, 107, 101, 101), (102, 102, 100, 100)),
    ],
)
def test_micro_double_spike_and_nonspike_roles(
    side, regime, always_in, first, second
):
    bars = tuple(bar(i, *values) for i, values in enumerate((first, second)))
    name = f"CH6_MICRO_DOUBLE_{side}_CONTEXT"
    spike = find(bars, context(regime, always_in), name)
    nonspike = find(bars, context(), name)
    assert dict(spike.metadata)["contextual_role"] == "SPIKE_CONTINUATION_CONTEXT"
    assert dict(nonspike.metadata)["contextual_role"] == "POSSIBLE_REVERSAL_CONTEXT"
    assert spike.role == nonspike.role == "DIAGNOSTIC_ONLY"
    assert spike.source_rule_ids == nonspike.source_rule_ids == ()
    assert detect_micro_double_top_bottom(snapshot(bars), context(regime, always_in), POLICY) == ()


@pytest.mark.parametrize(
    ("regime", "always_in", "direction", "values"),
    [
        (
            "BULL_TREND", "LONG", "LONG",
            ((100, 103, 100, 103), (103, 106, 103, 106)),
        ),
        (
            "BEAR_TREND", "SHORT", "SHORT",
            ((106, 106, 103, 103), (103, 103, 100, 100)),
        ),
    ],
)
def test_shaved_bar_trend_range_qualification(regime, always_in, direction, values):
    bars = tuple(bar(i, *v) for i, v in enumerate(values))
    trend = find(bars, context(regime, always_in), "CH6_SHAVED_BAR_CONTEXT")
    ranged = find(bars, context(), "CH6_SHAVED_BAR_CONTEXT")
    assert trend.direction == ranged.direction == direction
    assert dict(ranged.metadata)["context_qualification"] == "TRADING_RANGE_GEOMETRY"
    assert dict(trend.metadata)["context_qualification"] in {
        "STRONG_MATCHING_TREND", "UNQUALIFIED_GEOMETRY",
    }
    assert trend.source_rule_ids == ranged.source_rule_ids == ()


def test_prefix_causality_and_no_candidate_creation():
    bars = (
        bar(0, 105, 106, 99, 99),
        bar(1, 99, 105, 98, 104),
        bar(2, 104, 110, 90, 95),
    )
    prefix = observations(bars[:2], context())
    assert prefix == observations(tuple(bars[:2]), context())
    assert all(x.signal_index <= 1 for x in prefix)
    assert all(x.role == "DIAGNOSTIC_ONLY" for x in prefix)
    assert all(dict(x.metadata)["trade_eligible"] == "false" for x in prefix)
    assert all(x.source_rule_ids == () for x in prefix)
