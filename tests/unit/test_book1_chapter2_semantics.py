from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

from app.modules.brooks_core.books_full_engine import BrooksTrilogyFullCoreEngine
from app.modules.brooks_core.books_full_patterns import detect_climactic_reversal
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.brooks_core.books_policy import BrooksBooksPolicy
from app.modules.brooks_core.context_classifier import (
    assess_books_context,
    assess_chapter2_bar_context,
    is_strong_bull_bar,
)
from app.modules.market_data.entities import Candle, MarketSnapshot

BASE = datetime(2026, 1, 1, tzinfo=UTC)
POLICY = BrooksBooksPolicy()
FULL_POLICY = BrooksFullCorePolicy()


def bar(i: int, o, h, low, c) -> Candle:
    opened = BASE + timedelta(minutes=15 * i)
    return Candle(
        opened, opened + timedelta(minutes=15),
        D(str(o)), D(str(h)), D(str(low)), D(str(c)), D("1"),
    )

def snapshot(candles: list[Candle]) -> MarketSnapshot:
    items = tuple(candles)
    return MarketSnapshot(
        exchange="binance",
        market_type="futures",
        symbol="BTCUSDT",
        timeframe="15m",
        candles=items,
        captured_at=items[-1].close_time,
        source="BOOK1_CH2_TEST",
    )


def prior_body_context(body: D, count: int = 10) -> list[Candle]:
    rows = []
    for i in range(count):
        base = D("100")
        rows.append(bar(i, base, base + D("1"), base - D("1"), base + body))
    return rows


def trending_dojis(direction: str, count: int = 40) -> list[Candle]:
    rows = []
    for i in range(count):
        if direction == "LONG":
            base = D("100") + D(i) * D("0.5")
            rows.append(bar(i, base, base + D("1.1"), base - D("0.1"), base + D("0.12")))
        else:
            base = D("120") - D(i) * D("0.5")
            rows.append(bar(i, base, base + D("0.1"), base - D("1.1"), base - D("0.12")))
    return rows

def range_history_with_final_strong_bar() -> list[Candle]:
    rows = []
    for i in range(39):
        base = D("100.3") if i % 2 == 0 else D("99.7")
        close = base + (D("0.1") if i % 2 == 0 else D("-0.1"))
        rows.append(bar(i, base, D("101"), D("99"), close))
    rows.append(bar(39, D("100"), D("104"), D("99.8"), D("103.7")))
    return rows


def strong_bull_run() -> list[Candle]:
    rows = range_history_with_final_strong_bar()[:-4]
    for i in range(36, 40):
        opened = D("100") + D(i - 36) * D("3")
        rows.append(bar(i, opened, opened + D("3.2"), opened - D("0.1"), opened + D("3")))
    return rows


def test_relative_small_body_is_contextual_not_absolute():
    final = bar(10, "100", "101", "99", "100.2")
    large_context = tuple(prior_body_context(D("0.8")) + [final])
    tiny_context = tuple(prior_body_context(D("0.05")) + [final])

    doji = assess_chapter2_bar_context(large_context, POLICY)
    trend = assess_chapter2_bar_context(tiny_context, POLICY)
    assert doji and doji.bar_state == "DOJI_LIKE"
    assert trend and trend.bar_state == "BULL_TREND_BAR_LIKE"

def test_perfect_doji_is_balance_state():
    rows = prior_body_context(D("0.4"))
    rows.append(bar(10, "100", "101", "99", "100"))
    ctx = assess_chapter2_bar_context(tuple(rows), POLICY)
    assert ctx and ctx.bar_state == "DOJI_LIKE"
    assert ctx.direction == "UNRESOLVED"


def test_trending_dojis_establish_bull_context_without_always_in():
    ctx = assess_books_context(snapshot(trending_dojis("LONG")), policy=POLICY)
    assert ctx.regime == "BULL_TREND"
    assert ctx.always_in == "UNRESOLVED"
    assert ctx.chapter2_bar_context
    assert ctx.chapter2_bar_context.trending_doji_direction == "LONG"
    assert ctx.chapter2_bar_context.trending_doji_run_length >= 3


def test_trending_dojis_bear_mirror():
    ctx = assess_books_context(snapshot(trending_dojis("SHORT")), policy=POLICY)
    assert ctx.regime == "BEAR_TREND"
    assert ctx.always_in == "UNRESOLVED"
    assert ctx.chapter2_bar_context
    assert ctx.chapter2_bar_context.trending_doji_direction == "SHORT"

def test_one_strong_trend_bar_does_not_by_itself_establish_trend():
    rows = range_history_with_final_strong_bar()
    assert is_strong_bull_bar(rows[-1], POLICY)
    ctx = assess_books_context(snapshot(rows), policy=POLICY)
    assert ctx.regime not in {"BULL_TREND", "BEAR_TREND"}
    assert ctx.always_in == "UNRESOLVED"


def test_consecutive_strong_bars_preserve_follow_through_semantics():
    ctx = assess_books_context(snapshot(strong_bull_run()), policy=POLICY)
    assert ctx.regime == "BULL_TREND"
    assert ctx.always_in == "LONG"
    assert ctx.breakout_streak >= 2


def test_cumulative_body_pressure_is_context_only():
    rows = []
    for i in range(10):
        if i < 7:
            rows.append(bar(i, "100", "102", "99", "101.2"))
        else:
            rows.append(bar(i, "101", "102", "99", "100.8"))
    ctx = assess_chapter2_bar_context(tuple(rows), POLICY)
    assert ctx and ctx.pressure_direction == "LONG"
    assert ctx.bull_body_total > ctx.bear_body_total

def test_generic_climax_run_is_separate_from_reversal():
    rows = [bar(i, "100", "101", "99", "100") for i in range(10)]
    rows.extend([
        bar(10, "100", "103", "99.9", "102.8"),
        bar(11, "102.8", "106", "102.7", "105.8"),
        bar(12, "105.8", "109", "105.7", "108.8"),
    ])
    ch2 = assess_chapter2_bar_context(tuple(rows), POLICY)
    assert ch2
    assert ch2.climax_state == "ACTIVE_BUY_CLIMAX"
    assert ch2.climax_run_length == 3

    full_rows = rows + [bar(13, "108.8", "109.5", "108.1", "108.8")]
    paused = assess_chapter2_bar_context(tuple(full_rows), POLICY)
    assert paused
    assert paused.climax_state == "BUY_CLIMAX_ENDED_AT_PAUSE"
    assert paused.climax_run_length == 3
    assert paused.climax_pause_index == 13
    assert paused.climax_pause_kind == "DOJI"

def test_climax_context_does_not_automatically_create_reversal_candidate():
    rows = [bar(i, "100", "101", "99", "100") for i in range(37)]
    rows.extend([
        bar(37, "100", "103", "99.9", "102.8"),
        bar(38, "102.8", "106", "102.7", "105.8"),
        bar(39, "105.8", "109", "105.7", "108.8"),
    ])
    snap = snapshot(rows)
    context = assess_books_context(snap, policy=POLICY)
    assert context.chapter2_bar_context
    assert context.chapter2_bar_context.climax_state == "ACTIVE_BUY_CLIMAX"
    assert detect_climactic_reversal(snap, context, FULL_POLICY) == ()


def test_chapter2_prefix_causality_is_stable():
    rows = trending_dojis("LONG", 12)
    prefix = tuple(rows[:8])
    full = tuple(rows + [
        bar(12, "120", "121", "115", "116"),
        bar(13, "116", "117", "110", "111"),
    ])
    at_t = assess_chapter2_bar_context(full, POLICY, evaluated_index=7)
    from_prefix = assess_chapter2_bar_context(prefix, POLICY)
    assert at_t == from_prefix

def test_bar_geometry_and_relative_strength_evidence_are_exposed():
    rows = prior_body_context(D("0.2"))
    rows.append(bar(10, "100", "104", "99.8", "103.8"))
    ctx = assess_chapter2_bar_context(tuple(rows), POLICY)
    assert ctx
    assert ctx.bar_state == "BULL_TREND_BAR_LIKE"
    assert ctx.body_at_or_above_recent_median
    assert ctx.relative_body_multiple and ctx.relative_body_multiple > 1
    assert ctx.strong_geometry_proxy
    assert ctx.close_location > ctx.open_location
    assert ctx.upper_tail_fraction < ctx.body_fraction
    assert ctx.directional_prior_close_count > 0
    assert ctx.directional_prior_extreme_count > 0
    assert ctx.directional_prior_extreme_close_count > 0


def test_engine_exposes_chapter2_context_in_runtime_evidence():
    result = asyncio.run(
        BrooksTrilogyFullCoreEngine(policy=FULL_POLICY).evaluate(
            snapshot(trending_dojis("LONG"))
        )
    )
    evidence = next(
        item for item in result.rule_evidence
        if item.rule_id == "BB-TRD-19-TREND-STRENGTH"
    )
    metadata = dict(evidence.evidence)
    assert metadata["chapter2_bar_state"] == "DOJI_LIKE"
    assert metadata["chapter2_trending_doji_direction"] == "LONG"
    assert "chapter2_bull_body_total" in metadata
    assert "chapter2_lower_tail_fraction_total" in metadata
    assert "chapter2_directional_prior_close_count" in metadata
    assert "chapter2_climax_pause_kind" in metadata
    assert "chapter2_climax_body_progression" in metadata
    assert metadata["chapter2_semantic_role"] == "CONTEXT_ONLY_NO_DIRECT_ENTRY"

def test_relative_body_boundary_at_recent_median_stays_doji_like():
    rows = prior_body_context(D("0.2"))
    rows.append(bar(10, "100", "101", "99", "100.2"))
    ctx = assess_chapter2_bar_context(tuple(rows), POLICY)
    assert ctx
    assert ctx.recent_median_body == D("0.2")
    assert ctx.bar_state == "DOJI_LIKE"


def test_mixed_doji_sequence_does_not_invent_directional_trend():
    rows = trending_dojis("LONG", 8)
    rows[-2] = bar(6, "103", "105", "101", "103.12")
    rows[-1] = bar(7, "103", "104", "100.5", "103.12")
    ctx = assess_chapter2_bar_context(tuple(rows), POLICY)
    assert ctx
    assert ctx.trending_doji_direction == "UNRESOLVED"


def test_bear_and_ambiguous_body_pressure_are_distinct():
    bear_rows = [
        bar(i, "101", "102", "99", "99.8") if i < 7
        else bar(i, "100", "102", "99", "100.2")
        for i in range(10)
    ]
    bear = assess_chapter2_bar_context(tuple(bear_rows), POLICY)
    assert bear and bear.pressure_direction == "SHORT"

    mixed = [bar(i, "100", "102", "98", "101" if i % 2 == 0 else "99") for i in range(10)]
    neutral = assess_chapter2_bar_context(tuple(mixed), POLICY)
    assert neutral and neutral.pressure_direction == "UNRESOLVED"

def _climax_rows() -> list[Candle]:
    rows = [bar(i, "100", "101", "99", "100") for i in range(10)]
    rows.extend([
        bar(10, "100", "103", "99.9", "102.8"),
        bar(11, "102.8", "106", "102.7", "105.8"),
        bar(12, "105.8", "109", "105.7", "108.8"),
    ])
    return rows


def test_opposite_trend_bar_ends_prior_climax_without_implying_reversal():
    rows = _climax_rows()
    rows.append(bar(13, "108.8", "109.2", "104.8", "105.2"))
    ctx = assess_chapter2_bar_context(tuple(rows), POLICY)
    assert ctx
    assert ctx.climax_direction == "LONG"
    assert ctx.climax_state == "BUY_CLIMAX_ENDED_AT_PAUSE"
    assert ctx.climax_pause_kind == "OPPOSITE_TREND_BAR"
    assert ctx.climax_pause_index == 13


def test_inside_bar_ends_prior_climax():
    rows = _climax_rows()
    rows.append(bar(13, "107.2", "108.9", "107.0", "108.4"))
    ctx = assess_chapter2_bar_context(tuple(rows), POLICY)
    assert ctx
    assert ctx.climax_direction == "LONG"
    assert ctx.climax_state == "BUY_CLIMAX_ENDED_AT_PAUSE"
    assert ctx.climax_pause_kind == "INSIDE_BAR"


def test_small_same_direction_bar_with_prominent_trend_side_tail_ends_climax():
    rows = [
        bar(i, 100 + i * 2, 102.5 + i * 2, 99.8 + i * 2, 102 + i * 2)
        for i in range(10)
    ]
    rows.extend([
        bar(10, "120", "123.2", "119.9", "123"),
        bar(11, "123", "126.2", "122.9", "126"),
        bar(12, "126", "129.2", "125.9", "129"),
    ])
    rows.append(bar(13, "129", "133", "128.5", "130.8"))
    ctx = assess_chapter2_bar_context(tuple(rows), POLICY)
    assert ctx
    assert ctx.climax_direction == "LONG"
    assert ctx.climax_state == "BUY_CLIMAX_ENDED_AT_PAUSE"
    assert ctx.climax_pause_kind == "SAME_DIRECTION_TAIL_PAUSE"


def test_climax_body_progression_distinguishes_increasing_and_decreasing_strength():
    base = [bar(i, "100", "101", "99", "100") for i in range(10)]
    increasing = base + [
        bar(10, "100", "100.2", "98.8", "99"),
        bar(11, "99", "99.2", "96.8", "97"),
        bar(12, "97", "97.2", "93.8", "94"),
    ]
    inc = assess_chapter2_bar_context(tuple(increasing), POLICY)
    assert inc
    assert inc.climax_direction == "SHORT"
    assert inc.climax_body_progression == "INCREASING"

    decreasing = base + [
        bar(10, "100", "100.2", "96.8", "97"),
        bar(11, "97", "97.2", "94.8", "95"),
        bar(12, "95", "95.2", "93.8", "94"),
    ]
    dec = assess_chapter2_bar_context(tuple(decreasing), POLICY)
    assert dec
    assert dec.climax_direction == "SHORT"
    assert dec.climax_body_progression == "DECREASING"
