from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from app.modules.brooks_core.books_full_engine import BrooksTrilogyFullCoreEngine
from app.modules.brooks_core.books_full_entities import BrooksPatternCandidate
from app.modules.brooks_core.books_full_patterns import detect_major_trend_reversal
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.brooks_core.pattern_expansion import (
    detect_moving_average_pullback_setups,
    scan_structure_observations,
)
from app.modules.market_data.entities import Candle, MarketSnapshot

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def bar(i: int, o: str, h: str, l: str, c: str) -> Candle:
    opened = BASE + timedelta(minutes=15 * i)
    return Candle(
        open_time=opened,
        close_time=opened + timedelta(minutes=15),
        open=Decimal(o), high=Decimal(h), low=Decimal(l), close=Decimal(c),
        volume=Decimal("10"),
    )


def snapshot(candles) -> MarketSnapshot:
    items = tuple(candles)
    return MarketSnapshot(
        exchange="binance", market_type="futures", symbol="BTCUSDT", timeframe="15m",
        candles=items, captured_at=items[-1].close_time, source="MASTER_BROOKS_TEST",
    )


def context(regime="BULL_TREND", always_in="LONG", breakout_direction="LONG", breakout_streak=2):
    return SimpleNamespace(
        regime=regime,
        structure_direction=regime,
        always_in=always_in,
        breakout_direction=breakout_direction,
        breakout_streak=breakout_streak,
        metrics=SimpleNamespace(bar_overlap_rate=Decimal("0.7")),
    )


def swing(kind: str, index: int, price: str):
    return SimpleNamespace(kind=kind, candle_index=index, confirmed_at_index=index, price=Decimal(price))


def test_second_moving_average_gap_long_is_first_class_second_attempt():
    candles = [bar(i, "103", "105", "101", "104") for i in range(21)]
    candles += [
        bar(21, "95", "98", "93", "97"),       # first gap-bar reversal attempt
        bar(22, "97", "99", "95", "98.5"),    # attempt toward EMA, still below it
        bar(23, "98", "98.5", "92", "93"),    # failure / move away resumes
        bar(24, "93", "97", "91", "96"),      # second reversal toward EMA
    ]
    with patch(
        "app.modules.brooks_core.pattern_expansion._ema20",
        return_value=tuple(Decimal("100") for _ in candles),
    ):
        found = detect_moving_average_pullback_setups(
            snapshot(candles), context(), BrooksFullCorePolicy()
        )
    assert any(x.setup_type == "SECOND_MA_GAP_BAR_LONG" for x in found)


def test_second_moving_average_gap_short_is_first_class_second_attempt():
    candles = [bar(i, "97", "99", "95", "96") for i in range(21)]
    candles += [
        bar(21, "105", "107", "102", "103"),
        bar(22, "103", "105", "101", "102"),
        bar(23, "102", "108", "101.5", "107"),
        bar(24, "107", "109", "103", "104"),
    ]
    with patch(
        "app.modules.brooks_core.pattern_expansion._ema20",
        return_value=tuple(Decimal("100") for _ in candles),
    ):
        found = detect_moving_average_pullback_setups(
            snapshot(candles),
            context("BEAR_TREND", "SHORT", "SHORT"),
            BrooksFullCorePolicy(),
        )
    assert any(x.setup_type == "SECOND_MA_GAP_BAR_SHORT" for x in found)


def test_ordinary_nontrending_six_swings_are_not_mislabeled_as_stairs():
    candles = [bar(i, "100", "103", "97", "100") for i in range(20)]
    fake_swings = (
        swing("LOW", 2, "95"), swing("HIGH", 4, "105"),
        swing("LOW", 6, "96"), swing("HIGH", 8, "104"),
        swing("LOW", 10, "94"), swing("HIGH", 12, "106"),
    )
    with patch("app.modules.brooks_core.pattern_expansion._alternating_recent_swings", return_value=fake_swings), \
         patch("app.modules.brooks_core.pattern_expansion.confirm_swings_causally", return_value=SimpleNamespace(swings=())):
        obs = scan_structure_observations(snapshot(candles), context(), BrooksFullCorePolicy())
    assert not any(x.pattern_id == "BROAD_CHANNEL_STAIRS" for x in obs)


def test_valid_broad_stairs_and_shrinking_stairs_are_distinguished():
    candles = [bar(i, "100", "103", "97", "100") for i in range(20)]
    # Three higher highs / higher lows. Each pullback after a new high overlaps
    # back through the preceding breakout high. Breakout extensions shrink 6 -> 4.
    fake_swings = (
        swing("LOW", 2, "90"), swing("HIGH", 4, "100"),
        swing("LOW", 6, "95"), swing("HIGH", 8, "106"),
        swing("LOW", 10, "99"), swing("HIGH", 12, "110"),
        swing("LOW", 14, "104"),
    )
    with patch("app.modules.brooks_core.pattern_expansion._alternating_recent_swings", return_value=fake_swings), \
         patch("app.modules.brooks_core.pattern_expansion.confirm_swings_causally", return_value=SimpleNamespace(swings=())):
        obs = scan_structure_observations(snapshot(candles), context(), BrooksFullCorePolicy())
    ids = {x.pattern_id for x in obs}
    assert "BROAD_CHANNEL_STAIRS" in ids
    assert "SHRINKING_STAIRS" in ids


def test_confirmed_two_bar_breakout_is_not_vetoed_only_because_prior_bars_were_barbwire():
    candles = [
        bar(0, "100", "102", "98", "100.2"),
        bar(1, "100.1", "102.1", "98.2", "100"),
        bar(2, "100", "101.9", "98.1", "100.1"),
        bar(3, "100.2", "102", "98.3", "100"),
        bar(4, "100", "102.2", "98.4", "100.1"),
        bar(5, "100.1", "102", "98.2", "100.2"),
        bar(6, "103", "108", "102.5", "107"),
    ]
    candidate = BrooksPatternCandidate(
        direction="LONG", setup_type="BREAKOUT_LONG", family="BREAKOUT", signal_index=6,
        reasons=("two_consecutive_strong_bars_beyond_breakout_level", "breakout_follow_through_confirmed"),
        source_rule_ids=("BB-RNG-02-BREAKOUT-FOLLOWTHROUGH",), taxonomy="SOURCE_INTERPRETATION",
        priority=20, context_required="BREAKOUT_OR_TREND",
    )
    engine = BrooksTrilogyFullCoreEngine()
    assert engine._barbwire_stop_entry_veto(snapshot(candles), candidate) is False


def test_mtr_context_contract_does_not_require_ema_cross_as_hard_book_witness():
    candidate = BrooksPatternCandidate(
        direction="SHORT", setup_type="MAJOR_TREND_REVERSAL_SHORT",
        family="MAJOR_TREND_REVERSAL", signal_index=49,
        reasons=("prior trend", "trend line break", "old extreme retest", "strong reversal"),
        source_rule_ids=("BB-REV-03-MAJOR-TREND-REVERSAL",), taxonomy="SOURCE_INTERPRETATION",
        priority=25, context_required="REVERSAL_MATURITY",
        metadata=(("prior_trend", "true"), ("trend_line_break", "true"),
                  ("ema_break", "false"), ("extreme_retest", "true"),
                  ("second_reversal", "true")),
    )
    assert BrooksTrilogyFullCoreEngine()._context_contract_status(candidate, context())[0] == "PASS"


def test_mtr_detector_accepts_strong_trendline_break_and_retest_without_mandatory_ema_cross():
    candles = [bar(i, "140", "142", "138", "140") for i in range(50)]
    candles[37] = bar(37, "110", "111", "104", "105")  # strong TL break; still above EMA=100
    candles[49] = bar(49, "129", "130", "124", "125")  # retest old high and strong reversal
    swings = (
        swing("LOW", 5, "90"), swing("HIGH", 10, "110"),
        swing("LOW", 20, "100"), swing("HIGH", 25, "120"),
        swing("HIGH", 35, "130"), swing("LOW", 42, "108"),
    )
    with patch("app.modules.brooks_core.books_full_patterns.confirm_swings_causally", return_value=SimpleNamespace(swings=swings)), \
         patch("app.modules.brooks_core.books_full_patterns._ema20_values", return_value=tuple(Decimal("100") for _ in candles)), \
         patch("app.modules.brooks_core.books_full_patterns.is_strong_bear_bar", return_value=True):
        found = detect_major_trend_reversal(snapshot(candles), context(), BrooksFullCorePolicy())
    assert any(x.setup_type == "MAJOR_TREND_REVERSAL_SHORT" for x in found)
    item = next(x for x in found if x.setup_type == "MAJOR_TREND_REVERSAL_SHORT")
    assert dict(item.metadata)["ema_break"] == "false"


def test_second_ma_gap_requires_prior_first_attempt():
    candles = [bar(i, "103", "105", "101", "104") for i in range(25)]
    candles += [
        bar(25, "98", "99", "94", "95"),
        bar(26, "95", "98", "92", "93"),
        bar(27, "93", "97", "91", "96"),
    ]
    with patch("app.modules.brooks_core.pattern_expansion._ema20",
               return_value=tuple(Decimal("100") for _ in candles)):
        found = detect_moving_average_pullback_setups(
            snapshot(candles), context(), BrooksFullCorePolicy()
        )
    assert not any(x.setup_type == "SECOND_MA_GAP_BAR_LONG" for x in found)


def test_second_ma_gap_requires_first_attempt_to_fail_before_second():
    candles = [bar(i, "103", "105", "101", "104") for i in range(25)]
    candles += [
        bar(25, "94", "97", "93", "96"),
        bar(26, "96", "98", "94", "97"),
        bar(27, "97", "99", "95", "98"),
        bar(28, "96", "99", "95", "98.5"),
    ]
    with patch("app.modules.brooks_core.pattern_expansion._ema20",
               return_value=tuple(Decimal("100") for _ in candles)):
        found = detect_moving_average_pullback_setups(
            snapshot(candles), context(), BrooksFullCorePolicy()
        )
    assert not any(x.setup_type == "SECOND_MA_GAP_BAR_LONG" for x in found)


def test_second_ma_gap_sequence_is_prefix_causal():
    candles = [bar(i, "103", "105", "101", "104") for i in range(25)]
    candles += [
        bar(25, "95", "98", "93", "97"),
        bar(26, "97", "99", "95", "98.5"),
        bar(27, "98", "98.5", "92", "93"),
        bar(28, "93", "97", "91", "96"),
    ]
    policy = BrooksFullCorePolicy()
    for end in (26, 27, 28):
        prefix = candles[:end]
        with patch("app.modules.brooks_core.pattern_expansion._ema20",
                   return_value=tuple(Decimal("100") for _ in prefix)):
            found = detect_moving_average_pullback_setups(snapshot(prefix), context(), policy)
        assert not any(x.setup_type == "SECOND_MA_GAP_BAR_LONG" for x in found)
    with patch("app.modules.brooks_core.pattern_expansion._ema20",
               return_value=tuple(Decimal("100") for _ in candles)):
        found = detect_moving_average_pullback_setups(snapshot(candles), context(), policy)
    item = next(x for x in found if x.setup_type == "SECOND_MA_GAP_BAR_LONG")
    meta = dict(item.metadata)
    assert int(meta["first_attempt_index"]) < int(meta["failure_index"]) < item.signal_index


def test_valid_nonshrinking_stairs_stays_broad_channel_only():
    candles = [bar(i, "100", "103", "97", "100") for i in range(20)]
    fake_swings = (
        swing("LOW", 2, "90"), swing("HIGH", 4, "100"),
        swing("LOW", 6, "95"), swing("HIGH", 8, "104"),
        swing("LOW", 10, "98"), swing("HIGH", 12, "110"),
        swing("LOW", 14, "103"),
    )
    with patch("app.modules.brooks_core.pattern_expansion._alternating_recent_swings", return_value=fake_swings), \
         patch("app.modules.brooks_core.pattern_expansion.confirm_swings_causally", return_value=SimpleNamespace(swings=())):
        obs = scan_structure_observations(snapshot(candles), context(), BrooksFullCorePolicy())
    ids = {x.pattern_id for x in obs}
    assert "BROAD_CHANNEL_STAIRS" in ids
    assert "SHRINKING_STAIRS" not in ids


def test_stairs_requires_sufficient_three_swing_breakout_structure():
    candles = [bar(i, "100", "103", "97", "100") for i in range(20)]
    fake_swings = (
        swing("LOW", 2, "90"), swing("HIGH", 4, "100"),
        swing("LOW", 6, "95"), swing("HIGH", 8, "106"),
        swing("LOW", 10, "99"),
    )
    with patch("app.modules.brooks_core.pattern_expansion._alternating_recent_swings", return_value=fake_swings), \
         patch("app.modules.brooks_core.pattern_expansion.confirm_swings_causally", return_value=SimpleNamespace(swings=())):
        obs = scan_structure_observations(snapshot(candles), context(), BrooksFullCorePolicy())
    assert not any(x.pattern_id in {"BROAD_CHANNEL_STAIRS", "SHRINKING_STAIRS"} for x in obs)


def test_stairs_not_emitted_in_wrong_trading_range_context():
    candles = [bar(i, "100", "103", "97", "100") for i in range(20)]
    fake_swings = (
        swing("LOW", 2, "90"), swing("HIGH", 4, "100"),
        swing("LOW", 6, "95"), swing("HIGH", 8, "106"),
        swing("LOW", 10, "99"), swing("HIGH", 12, "110"),
        swing("LOW", 14, "104"),
    )
    with patch("app.modules.brooks_core.pattern_expansion._alternating_recent_swings", return_value=fake_swings), \
         patch("app.modules.brooks_core.pattern_expansion.confirm_swings_causally", return_value=SimpleNamespace(swings=())):
        obs = scan_structure_observations(
            snapshot(candles),
            context("TRADING_RANGE", "UNRESOLVED", "UNRESOLVED", 0),
            BrooksFullCorePolicy(),
        )
    assert not any(x.pattern_id in {"BROAD_CHANNEL_STAIRS", "SHRINKING_STAIRS"} for x in obs)


def test_active_barbwire_still_vetoes_unconfirmed_stop_entry_breakout():
    candles = [
        bar(0, "100", "102", "98", "100.2"),
        bar(1, "100.1", "102.1", "98.2", "100"),
        bar(2, "100", "101.9", "98.1", "100.1"),
        bar(3, "100.2", "102", "98.3", "100"),
        bar(4, "100", "102.2", "98.4", "100.1"),
        bar(5, "100.1", "102", "98.2", "100.2"),
        bar(6, "101", "103", "99", "102.1"),
    ]
    candidate = BrooksPatternCandidate(
        direction="LONG", setup_type="BREAKOUT_LONG", family="BREAKOUT", signal_index=6,
        reasons=("close_beyond_level", "first_stop_entry_attempt"), source_rule_ids=("BB-RNG-02-BREAKOUT-FOLLOWTHROUGH",),
        taxonomy="SOURCE_INTERPRETATION", priority=20, context_required="BREAKOUT_OR_TREND",
    )
    assert BrooksTrilogyFullCoreEngine()._barbwire_stop_entry_veto(snapshot(candles), candidate) is True


def test_breakout_pullback_is_not_subject_to_first_barbwire_stop_entry_veto():
    candles = [bar(i, "100", "102", "98", "100.1") for i in range(7)]
    candidate = BrooksPatternCandidate(
        direction="LONG", setup_type="BREAKOUT_PULLBACK_LONG", family="BREAKOUT_PULLBACK", signal_index=6,
        reasons=("small_one_to_five_bar_pullback", "final_bar_resumes_breakout_direction"),
        source_rule_ids=("BB-RNG-05-BREAKOUT-PULLBACK",), taxonomy="SOURCE_INTERPRETATION",
        priority=12, context_required="BREAKOUT_RESUMPTION",
    )
    assert BrooksTrilogyFullCoreEngine()._barbwire_stop_entry_veto(snapshot(candles), candidate) is False


def _mtr_short_fixture():
    candles = [bar(i, "140", "142", "138", "140") for i in range(50)]
    candles[37] = bar(37, "110", "111", "104", "105")
    candles[49] = bar(49, "129", "130", "124", "125")
    swings = (
        swing("LOW", 5, "90"), swing("HIGH", 10, "110"),
        swing("LOW", 20, "100"), swing("HIGH", 25, "120"),
        swing("HIGH", 35, "130"), swing("LOW", 42, "108"),
    )
    return candles, swings


def test_mtr_with_ema_cross_remains_valid_supporting_evidence():
    candles, swings = _mtr_short_fixture()
    with patch("app.modules.brooks_core.books_full_patterns.confirm_swings_causally", return_value=SimpleNamespace(swings=swings)), \
         patch("app.modules.brooks_core.books_full_patterns._ema20_values", return_value=tuple(Decimal("120") for _ in candles)), \
         patch("app.modules.brooks_core.books_full_patterns.is_strong_bear_bar", return_value=True):
        found = detect_major_trend_reversal(snapshot(candles), context(), BrooksFullCorePolicy())
    item = next(x for x in found if x.setup_type == "MAJOR_TREND_REVERSAL_SHORT")
    assert dict(item.metadata)["ema_break"] == "true"


def test_mtr_without_meaningful_trendline_break_is_rejected():
    candles, swings = _mtr_short_fixture()
    candles[37] = bar(37, "120", "123", "118", "121")
    with patch("app.modules.brooks_core.books_full_patterns.confirm_swings_causally", return_value=SimpleNamespace(swings=swings)), \
         patch("app.modules.brooks_core.books_full_patterns._ema20_values", return_value=tuple(Decimal("100") for _ in candles)), \
         patch("app.modules.brooks_core.books_full_patterns.is_strong_bear_bar", return_value=True):
        found = detect_major_trend_reversal(snapshot(candles), context(), BrooksFullCorePolicy())
    assert not any(x.setup_type == "MAJOR_TREND_REVERSAL_SHORT" for x in found)


def test_mtr_without_old_extreme_retest_is_rejected():
    candles, swings = _mtr_short_fixture()
    # WAVE_08: test and second reversal are no longer required on the same bar.
    # Remove every post-break retest, not only the final-bar retest.
    for i in range(38, 49):
        candles[i] = bar(i, "116", "118", "111", "116")
    candles[49] = bar(49, "116", "118", "111", "112")
    with patch("app.modules.brooks_core.books_full_patterns.confirm_swings_causally", return_value=SimpleNamespace(swings=swings)), \
         patch("app.modules.brooks_core.books_full_patterns._ema20_values", return_value=tuple(Decimal("100") for _ in candles)), \
         patch("app.modules.brooks_core.books_full_patterns.is_strong_bear_bar", return_value=True):
        found = detect_major_trend_reversal(snapshot(candles), context(), BrooksFullCorePolicy())
    assert not any(x.setup_type == "MAJOR_TREND_REVERSAL_SHORT" for x in found)


def test_minor_reversal_structure_is_not_promoted_to_mtr():
    candles = [bar(i, "100", "103", "97", "100") for i in range(50)]
    candles[-1] = bar(49, "102", "103", "96", "97")
    swings = (
        swing("LOW", 5, "95"), swing("HIGH", 10, "105"),
        swing("LOW", 20, "96"), swing("HIGH", 25, "106"),
    )
    with patch("app.modules.brooks_core.books_full_patterns.confirm_swings_causally", return_value=SimpleNamespace(swings=swings)):
        found = detect_major_trend_reversal(snapshot(candles), context(), BrooksFullCorePolicy())
    assert found == ()


def test_master_completion_strategy_identity_is_rule_catalog_v6():
    engine = BrooksTrilogyFullCoreEngine(
        policy=BrooksFullCorePolicy(enable_trade_decisions=True)
    )
    assert engine.engine_version == "brooks-trilogy-full-core-v5-context-structural"
    assert engine.rule_set_version == "brooks-trilogy-full-source-catalog-v6"
    # This mission changed Brooks rule semantics, not numeric policy configuration.
    assert engine.policy.configuration_version.startswith("books-full-v3-ctx[")
