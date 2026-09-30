from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from app.modules.brooks_core.books_full_engine import _RULE_SOURCE
from app.modules.brooks_core.books_full_patterns import (
    detect_double_top_bottom,
    detect_wedge_reversal,
)
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.brooks_core.evidence_weighting import all_rule_profiles
from app.modules.brooks_core.pattern_catalog import (
    CoverageRole,
    pattern_coverage_catalog,
)
from app.modules.brooks_core.pattern_expansion import (
    _extended_entry_count,
    detect_candle_pattern_breakouts,
    detect_double_top_bottom_pullback,
    detect_expanding_triangle,
    detect_micro_wedge,
    detect_reversal_bar_failure,
    scan_failed_hl_entry_observations,
    scan_signal_bar_observations,
    scan_structure_observations,
)
from app.modules.market_data.entities import Candle, MarketSnapshot

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def bar(i: int, o: str, h: str, l: str, c: str, v: str = "10") -> Candle:
    opened = BASE + timedelta(minutes=15 * i)
    return Candle(
        open_time=opened,
        close_time=opened + timedelta(minutes=15),
        open=Decimal(o), high=Decimal(h), low=Decimal(l), close=Decimal(c),
        volume=Decimal(v),
    )


def snapshot(candles, timeframe: str = "15m") -> MarketSnapshot:
    items = tuple(candles)
    return MarketSnapshot(
        exchange="binance", market_type="spot", symbol="BTCUSDT", timeframe=timeframe,
        candles=items, captured_at=items[-1].close_time, source="PHASE2_UNIT",
    )


def context(regime="AMBIGUOUS", structure="AMBIGUOUS", always_in="UNRESOLVED"):
    metrics = SimpleNamespace(bar_overlap_rate=Decimal("0.7"))
    return SimpleNamespace(
        regime=regime, structure_direction=structure, always_in=always_in,
        breakout_direction="UNRESOLVED", breakout_streak=0, metrics=metrics,
    )


def swing(kind: str, index: int):
    return SimpleNamespace(kind=kind, candle_index=index)


def test_pattern_catalog_has_no_missing_or_duplicate_operational_entries():
    items = pattern_coverage_catalog()
    ids = [item.pattern_id for item in items]
    assert len(ids) == len(set(ids))
    assert len(items) >= 45
    assert all(item.implementation.strip() for item in items)
    assert all(item.role in set(CoverageRole) for item in items)


def test_every_engine_source_rule_has_weight_profile():
    weighted = {item.rule_id for item in all_rule_profiles()}
    assert set(_RULE_SOURCE).issubset(weighted)


def test_iii_is_observed_and_not_downgraded_for_breakout_trigger():
    candles = [
        bar(0, "5", "10", "0", "6"),
        bar(1, "5", "9", "1", "6"),
        bar(2, "5", "8", "2", "6"),
        bar(3, "5", "7", "3", "6"),
    ]
    obs = scan_signal_bar_observations(snapshot(candles), context(), BrooksFullCorePolicy())
    assert any(item.pattern_id == "III" for item in obs)

    candles.append(bar(4, "6", "9.5", "5.8", "9.4"))
    found = detect_candle_pattern_breakouts(snapshot(candles), context(), BrooksFullCorePolicy())
    assert any(item.setup_type == "III_BREAKOUT_LONG" for item in found)


def test_reversal_bar_failure_is_with_trend_candidate():
    candles = [
        bar(0, "100", "102", "99", "101"),
        bar(1, "101", "102", "98", "99"),
        bar(2, "99", "103", "98.5", "102.5"),
    ]
    found = detect_reversal_bar_failure(
        snapshot(candles), context("BULL_TREND", "BULL_TREND", "LONG"), BrooksFullCorePolicy()
    )
    assert len(found) == 1
    assert found[0].setup_type == "BEAR_REVERSAL_BAR_FAILURE_LONG"


def test_session_patterns_are_explicitly_not_applicable_without_anchor():
    candles = [bar(i, str(100+i), str(101+i), str(99+i), str(100.5+i)) for i in range(20)]
    obs = scan_structure_observations(snapshot(candles), context(), BrooksFullCorePolicy())
    session = [x for x in obs if x.role.startswith("NOT_APPLICABLE")]
    ids = {x.pattern_id for x in session}
    assert {"TREND_FROM_OPEN", "REVERSAL_DAY", "TREND_RESUMPTION_DAY", "OPENING_REVERSAL", "GAP_OPENING"}.issubset(ids)


def test_extended_bar_count_recognizes_final_h4_only():
    candles = [
        bar(0, "8", "10", "5", "9"),
        bar(1, "8", "9", "4", "5"),
        bar(2, "5", "10", "4.5", "9"),
        bar(3, "8", "9", "3", "4"),
        bar(4, "4", "10", "3.5", "9"),
        bar(5, "8", "9", "2", "3"),
        bar(6, "3", "10", "2.5", "9"),
        bar(7, "8", "9", "1", "2"),
        bar(8, "2", "10", "1.5", "9"),
    ]
    count, event_index = _extended_entry_count(tuple(candles), direction="LONG", start=0)
    assert count == 4
    assert event_index == len(candles) - 1


def test_double_top_in_bear_trend_is_continuation_flag_not_reversal():
    candles = [bar(i, "100", "105", "95", "100") for i in range(20)]
    candles[5] = bar(5, "104", "110", "100", "105")
    candles[10] = bar(10, "104", "110", "100", "105")
    candles[-1] = bar(19, "108", "110", "101", "102")
    fake = SimpleNamespace(swings=(swing("HIGH", 5), swing("LOW", 7), swing("HIGH", 10)))
    with patch("app.modules.brooks_core.books_full_patterns.confirm_swings_causally", return_value=fake):
        found = detect_double_top_bottom(
            snapshot(candles), context("BEAR_TREND", "BEAR_TREND", "SHORT"), BrooksFullCorePolicy()
        )
    assert any(x.setup_type == "DOUBLE_TOP_BEAR_FLAG_SHORT" for x in found)
    assert not any(x.setup_type == "DOUBLE_TOP_REVERSAL_SHORT" for x in found)


def test_wedge_pullback_in_bull_trend_is_h3_flag():
    candles = [bar(i, "100", "105", "95", "100") for i in range(20)]
    candles[4] = bar(4, "100", "104", "95", "100")
    candles[8] = bar(8, "99", "103", "94", "99")
    candles[12] = bar(12, "98", "102", "93", "98")
    candles[-1] = bar(19, "97", "104", "96", "103")
    fake = SimpleNamespace(swings=(swing("LOW", 4), swing("LOW", 8), swing("LOW", 12)))
    with patch("app.modules.brooks_core.books_full_patterns.confirm_swings_causally", return_value=fake):
        found = detect_wedge_reversal(
            snapshot(candles), context("BULL_TREND", "BULL_TREND", "LONG"), BrooksFullCorePolicy()
        )
    assert any(x.setup_type == "H3_WEDGE_BULL_FLAG_LONG" for x in found)


def test_expanding_triangle_requires_five_swing_expansion_and_reversal():
    candles = [bar(i, "100", "105", "95", "100") for i in range(20)]
    candles[2] = bar(2, "101", "104", "100", "102")
    candles[4] = bar(4, "105", "110", "102", "108")
    candles[6] = bar(6, "99", "103", "95", "100")
    candles[8] = bar(8, "108", "115", "103", "112")
    candles[-1] = bar(19, "92", "96", "90", "95")
    swings = (swing("LOW", 2), swing("HIGH", 4), swing("LOW", 6), swing("HIGH", 8))
    with patch("app.modules.brooks_core.pattern_expansion._alternating_recent_swings", return_value=swings):
        found = detect_expanding_triangle(snapshot(candles), context(), BrooksFullCorePolicy())
    assert any(x.setup_type == "EXPANDING_TRIANGLE_BOTTOM_LONG" for x in found)


def test_double_bottom_pullback_is_distinct_breakout_pullback_setup():
    candles = [bar(i, "100", "104", "96", "100") for i in range(20)]
    candles[5] = bar(5, "94", "99", "90", "96")
    candles[10] = bar(10, "94", "99", "90.5", "96")
    candles[12] = bar(12, "99", "108", "98", "106")
    candles[-1] = bar(19, "93", "100", "91", "99")
    fake = SimpleNamespace(swings=(swing("LOW", 5), swing("HIGH", 8), swing("LOW", 10)))
    with patch("app.modules.brooks_core.pattern_expansion.confirm_swings_causally", return_value=fake):
        found = detect_double_top_bottom_pullback(snapshot(candles), context(), BrooksFullCorePolicy())
    assert any(x.setup_type == "DOUBLE_BOTTOM_PULLBACK_LONG" for x in found)


def test_micro_wedge_is_first_class_and_not_faded_against_always_in():
    candles = [
        bar(0, "8", "10", "7", "9"),
        bar(1, "9", "11", "8", "10"),
        bar(2, "10", "12", "9", "11"),
        bar(3, "11", "13", "10", "12"),
        bar(4, "13", "14", "11", "11.5"),
    ]
    found = detect_micro_wedge(snapshot(candles), context(), BrooksFullCorePolicy())
    assert any(x.setup_type == "MICRO_WEDGE_TOP_SHORT" for x in found)
    blocked = detect_micro_wedge(
        snapshot(candles), context("BULL_TREND", "BULL_TREND", "LONG"), BrooksFullCorePolicy()
    )
    assert not any(x.direction == "SHORT" for x in blocked)


def test_failed_h1_is_observation_not_automatic_reverse_trade():
    candles = [
        bar(0, "8", "10", "5", "9"),
        bar(1, "8", "9", "4", "5"),
        bar(2, "7", "8", "3", "4"),
        bar(3, "6", "8", "2", "3"),
        bar(4, "5", "7", "2", "3"),
        bar(5, "4", "7", "1", "2"),
        bar(6, "2", "8", "1.5", "7"),
        bar(7, "7", "7.5", "0.5", "1"),
    ]
    fake = SimpleNamespace(swings=(swing("HIGH", 0),))
    with patch(
        "app.modules.brooks_core.pattern_expansion.confirm_swings_causally",
        return_value=fake,
    ):
        found = scan_failed_hl_entry_observations(
            snapshot(candles),
            context("BULL_TREND", "BULL_TREND", "LONG"),
            BrooksFullCorePolicy(),
        )
    assert len(found) == 1
    assert found[0].pattern_id == "H1_OUTCOME_CONTEXT"
    assert found[0].role == "FAILURE_CONTEXT"
    assert found[0].direction == "SHORT"
    assert "BB-REV-09-FAILURES" in found[0].source_rule_ids
    metadata = dict(found[0].metadata)
    assert metadata["failure_confirmed"] == "false"
    assert metadata["lifecycle_state"] == "SIGNAL_INVALIDATED_BEFORE_TRIGGER"
    assert metadata["trade_eligible"] == "false"
