from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.modules.brooks_core.books_full_patterns import detect_breakout_family
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.brooks_core.context_classifier import (
    is_bear_reversal_bar_minimum,
    is_bull_reversal_bar_minimum,
)
from app.modules.brooks_core.pattern_expansion import scan_generic_breakout_attempt_observations
from app.modules.market_data.entities import Candle, MarketSnapshot

BASE = datetime(2026, 1, 2, tzinfo=UTC)


def bar(i, o, h, l, c):
    t = BASE + timedelta(minutes=15 * i)
    return Candle(open_time=t, close_time=t + timedelta(minutes=15), open=Decimal(o), high=Decimal(h), low=Decimal(l), close=Decimal(c), volume=Decimal("1"))


def snap(candles):
    items = tuple(candles)
    return MarketSnapshot(exchange="binance", market_type="spot", symbol="BTCUSDT", timeframe="15m", candles=items, captured_at=items[-1].close_time, source="W01_SCENARIO")


def ctx(regime="AMBIGUOUS"):
    return SimpleNamespace(regime=regime, structure_direction="AMBIGUOUS", always_in="UNRESOLVED", breakout_direction="UNRESOLVED", breakout_streak=0, metrics=SimpleNamespace(bar_overlap_rate=Decimal("0.2")))


def sw(kind, idx):
    return SimpleNamespace(kind=kind, candle_index=idx)


@pytest.mark.parametrize("c,bull,bear", [
    (bar(0,"99","110","90","100"), True, False),
    (bar(1,"104","110","90","104"), True, False),
    (bar(2,"101","110","90","100"), False, True),
    (bar(3,"96","110","90","96"), False, True),
    (bar(4,"100","110","90","100"), False, False),
])
def test_wave01_scenario_reversal_matrix(c,bull,bear):
    assert is_bull_reversal_bar_minimum(c) is bull
    assert is_bear_reversal_bar_minimum(c) is bear


def base(final):
    return [bar(0,"100","102","98","101"),bar(1,"101","103","99","102"),bar(2,"102","105","100","103"),bar(3,"103","104","101","102"),bar(4,"102","104","100","103"),bar(5,"103","104","101","102"),final]


@pytest.mark.parametrize("direction,final,kind,index,expect_closed", [
    ("LONG", bar(6,"103","106","102","104"), "HIGH", 2, "false"),
    ("SHORT", bar(6,"102","103","99","101"), "LOW", 2, "false"),
])
def test_wave01_scenario_wick_attempt_symmetry(direction, final, kind, index, expect_closed):
    candles = base(final)
    with patch("app.modules.brooks_core.pattern_expansion.confirm_swings_causally", return_value=SimpleNamespace(swings=(sw(kind,index),))):
        obs = scan_generic_breakout_attempt_observations(snap(candles), ctx(), BrooksFullCorePolicy())
    item = next(x for x in obs if x.pattern_id == f"BREAKOUT_ATTEMPT_{direction}")
    assert dict(item.metadata)["closed_beyond"] == expect_closed


def test_wave01_scenario_no_breakout_attempt():
    candles = base(bar(6,"103","104.5","102","104"))
    with patch("app.modules.brooks_core.pattern_expansion.confirm_swings_causally", return_value=SimpleNamespace(swings=(sw("HIGH",2),))):
        obs = scan_generic_breakout_attempt_observations(snap(candles), ctx(), BrooksFullCorePolicy())
    assert not obs


@pytest.mark.parametrize("direction,final,kind,index", [
    ("LONG", bar(6,"103","109","102","108.5"), "HIGH", 2),
    ("SHORT", bar(6,"102","103","96","96.5"), "LOW", 2),
])
def test_wave01_scenario_one_bar_decisive_breakout(direction, final, kind, index):
    candles = base(final)
    with patch("app.modules.brooks_core.books_full_patterns._latest_swing_before", side_effect=lambda *a, **kw: sw(kind,index) if kw["kind"] == kind else None):
        found = detect_breakout_family(snap(candles), ctx("TRADING_RANGE"), BrooksFullCorePolicy())
    item = next(x for x in found if x.direction == direction and x.family == "BREAKOUT")
    assert "decisive_single_bar_breakout" in item.reasons


def test_wave01_scenario_two_bar_follow_through_is_distinct():
    candles = base(bar(6,"106","109","105","108.5"))
    candles[5] = bar(5,"102","107","101.5","106.5")
    with patch("app.modules.brooks_core.books_full_patterns._latest_swing_before", side_effect=lambda *a, **kw: sw("HIGH",1) if kw["kind"] == "HIGH" else None):
        found = detect_breakout_family(snap(candles), ctx("BULL_TREND"), BrooksFullCorePolicy())
    item = next(x for x in found if x.direction == "LONG" and x.family == "BREAKOUT")
    assert "breakout_follow_through_confirmed" in item.reasons
    assert "two_consecutive_strong_bars_beyond_breakout_level" in item.reasons


def test_wave01_scenario_weak_penetration_does_not_become_breakout_trade():
    candles = base(bar(6,"103","106","102","104"))
    with patch("app.modules.brooks_core.books_full_patterns._latest_swing_before", side_effect=lambda *a, **kw: sw("HIGH",2) if kw["kind"] == "HIGH" else None):
        found = detect_breakout_family(snap(candles), ctx("TRADING_RANGE"), BrooksFullCorePolicy())
    assert not any(x.family == "BREAKOUT" for x in found)
