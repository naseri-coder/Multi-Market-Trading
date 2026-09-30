"""Book 1 Chapter 5: causal, non-trading reversal and actual-entry diagnostics."""

from __future__ import annotations

import dataclasses
import inspect
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from app.modules.brooks_core.context_classifier import (
    chapter5_reversal_diagnostic,
    is_bear_reversal_bar_minimum,
    is_bull_reversal_bar_minimum,
)
from app.modules.brooks_core.engine_contract import Chapter4SignalEntryLifecycle
from app.modules.market_data.entities import Candle
from app.modules.operations.lifecycle import LiveSignalLifecycleService

START = datetime(2026, 1, 1, tzinfo=UTC)


def candle(minute: int, o: int, c: int, *, high: int, low: int) -> Candle:
    opened = START + timedelta(minutes=minute)
    return Candle(
        open_time=opened,
        close_time=opened + timedelta(minutes=1),
        open=D(o),
        high=D(high),
        low=D(low),
        close=D(c),
        volume=D(10),
    )


def diagnostic(bars: tuple[Candle, ...], direction: str) -> dict[str, str]:
    return dict(chapter5_reversal_diagnostic(bars, direction=direction))


def service() -> LiveSignalLifecycleService:
    return object.__new__(LiveSignalLifecycleService)


def lifecycle(direction: str = "LONG") -> Chapter4SignalEntryLifecycle:
    return Chapter4SignalEntryLifecycle(
        setup_identity_id="SETUP", source_signal_id="SRC",
        economic_opportunity_id="ECON", market_snapshot_id="SNAP",
        market_snapshot_hash="HASH", setup_type="TEST",
        direction=direction, source_timeframe="5m",
        potential_signal_bar_identity_id="POTENTIAL",
        potential_signal_bar_index=10,
        potential_signal_bar_open_time=START.isoformat(),
        potential_signal_bar_close_time=(START + timedelta(minutes=5)).isoformat(),
        state="POTENTIAL_SIGNAL_WAITING_ENTRY",
        entry_intent_confirmation_scope="PRE_FILL_ENTRY_METHOD_OR_PATTERN_CONFIRMATION",
        entry_intent_confirmation_state="CONFIRMED",
    )


def strong_bar(minute: int, direction: str) -> Candle:
    if direction == "LONG":
        opened = 100 + minute - 5
        return candle(minute, opened, opened + 2, high=opened + 2, low=opened)
    opened = 100 - minute + 5
    return candle(minute, opened, opened - 2, high=opened, low=opened - 2)


def test_minimum_reversal_geometry_is_unchanged():
    bull = candle(0, 100, 101, high=102, low=99)
    bear = candle(1, 101, 100, high=102, low=99)
    assert is_bull_reversal_bar_minimum(bull)
    assert is_bear_reversal_bar_minimum(bear)
    assert not is_bear_reversal_bar_minimum(bull)
    assert not is_bull_reversal_bar_minimum(bear)


@pytest.mark.parametrize(
    ("direction", "previous", "current"),
    [
        ("LONG", (105, 100, 106, 99), (100, 103, 104, 95)),
        ("SHORT", (95, 100, 101, 94), (100, 97, 105, 96)),
    ],
)
def test_reversal_quality_is_direction_symmetric(direction, previous, current):
    prev = candle(0, previous[0], previous[1], high=previous[2], low=previous[3])
    bar = candle(1, current[0], current[1], high=current[2], low=current[3])
    data = diagnostic((prev, bar), direction)
    assert data["minimum_reversal_shape"] == "true"
    assert data["directional_body"] == "true"
    assert data["quality"] == "DIRECTIONAL_REJECTION_SUPPORT"
    assert data["previous_close_relation"] == "SUPPORTIVE"
    assert data["trade_eligible"] == "false"


def test_adverse_tail_weakness_is_context_not_universal_veto():
    prior = candle(0, 104, 100, high=105, low=99)
    bar = candle(1, 100, 102, high=108, low=99)
    data = diagnostic((prior, bar), "LONG")
    assert data["minimum_reversal_shape"] == "true"
    assert data["adverse_tail_exceeds_body"] == "true"
    assert data["quality"] == "MIXED_CONTEXTUAL_QUALITY"


def test_doji_like_balance_and_overlap_are_caution_not_a_range_id():
    prior = candle(0, 105, 95, high=110, low=90)
    bar = candle(1, 99, 99, high=106, low=94)
    data = diagnostic((prior, bar), "LONG")
    assert data["doji_like_balance"] == "true"
    assert data["inside_prior_range"] == "true"
    assert data["two_sided_action"] == "false"
    assert data["overlap_context"] == "REVERSAL_APPEARANCE_RANGE_CAUTION"
    assert data["range_identity_created"] == "false"
    assert "range_id" not in data


def test_two_sided_overlap_and_midpoint_caution_do_not_select_direction():
    prior = candle(0, 105, 95, high=110, low=90)
    bar = candle(1, 99, 101, high=106, low=94)
    bull = diagnostic((prior, bar), "LONG")
    bear = diagnostic((prior, bar), "SHORT")
    assert bull["two_sided_action"] == "true"
    assert bull["midpoint_overlap_caution"] == "true"
    assert bull["overlap_context"] == "REVERSAL_APPEARANCE_RANGE_CAUTION"
    assert bear["overlap_context"] == "REVERSAL_APPEARANCE_RANGE_CAUTION"
    assert bull["trade_eligible"] == bear["trade_eligible"] == "false"


def test_first_bar_has_no_invented_prior_context():
    bar = candle(0, 100, 102, high=103, low=99)
    data = diagnostic((bar,), "LONG")
    assert data["previous_close_relation"] == "NO_PRIOR_BAR"
    assert data["overlap_context"] == "NO_PRIOR_CONTEXT"


def test_reversal_diagnostic_is_prefix_causal():
    prior = candle(0, 104, 100, high=105, low=99)
    current = candle(1, 100, 103, high=104, low=97)
    future = candle(2, 110, 91, high=112, low=90)
    prefix = (prior, current)
    assert diagnostic(prefix, "LONG") == diagnostic((prior, current, future)[:2], "LONG")


def test_context_diagnostic_cannot_create_candidate_or_established_range():
    from app.modules.brooks_core.books_full_engine import BrooksTrilogyFullCoreEngine
    src = inspect.getsource(BrooksTrilogyFullCoreEngine._context_evidence)
    assert "chapter5_reversal_diagnostic" in src
    assert "BrooksPatternCandidate(" not in src
    assert "RangeIdentityEvidence(" not in src
    assert "chapter4_one_bar_trade_eligible" in src


def test_prefill_or_terminal_state_never_has_entry_quality():
    item = lifecycle()
    assert item.chapter5_entry_bar is None
    assert service()._observe_chapter5_entry_bar(item, strong_bar(5, "LONG")) == item
    terminal = service()._terminate_chapter4_unfilled(item, "CANCELLED")
    assert terminal.chapter5_entry_bar is None
    assert terminal.confirmed_signal_bar_identity_id is None


@pytest.mark.parametrize("direction", ["LONG", "SHORT"])
def test_entry_quality_finalizes_only_after_full_actual_interval(direction):
    helper = service()
    original = lifecycle(direction)
    item = helper._promote_chapter4_entry(original, strong_bar(5, direction))
    assert item.chapter5_entry_bar is not None
    assert item.chapter5_entry_bar.final_quality is None
    assert item.entry_bar_identity_id == item.chapter5_entry_bar.bar_identity_id
    for minute in (6, 7, 8):
        item = helper._observe_chapter5_entry_bar(item, strong_bar(minute, direction))
        assert item.chapter5_entry_bar.final_quality is None
    item = helper._observe_chapter5_entry_bar(item, strong_bar(9, direction))
    assert item.chapter5_entry_bar.final_quality == "STRONG_DIRECTIONAL"
    assert item.chapter5_entry_bar.count == 5
    assert item.chapter5_entry_bar.last_1m_close_time == (
        START + timedelta(minutes=10)
    ).isoformat()
    assert item.potential_signal_bar_index == original.potential_signal_bar_index
    assert item.economic_opportunity_id == original.economic_opportunity_id
    assert item.post_entry_lifecycle.completed_bars == ()
    assert Chapter4SignalEntryLifecycle.from_metadata(item.to_metadata()) == item


def test_completed_entry_doji_is_weak_without_trade_effect():
    helper = service()
    def flat(minute: int) -> Candle:
        return candle(minute, 100, 100, high=101, low=99)
    item = helper._promote_chapter4_entry(lifecycle(), flat(5))
    for minute in range(6, 10):
        item = helper._observe_chapter5_entry_bar(item, flat(minute))
    assert item.chapter5_entry_bar.final_quality == "WEAK_DOJI_OR_INSIDE"
    assert item.chapter5_entry_bar.trade_eligible is False
    assert item.post_entry_lifecycle.completed_bars == ()

def test_inside_bar_weakness_requires_real_previous_range():
    result = service()._chapter5_entry_quality(
        direction="LONG",
        open_price=D(100), high_price=D(105), low_price=D(99),
        close_price=D(104), prior_high=D(106), prior_low=D(98),
    )
    assert result[0] == "WEAK_DOJI_OR_INSIDE"
    assert result[2] is True
    missing = service()._chapter5_entry_quality(
        direction="LONG",
        open_price=D(100), high_price=D(105), low_price=D(99),
        close_price=D(104),
    )
    assert missing[2] is None
    assert "PRIOR_RANGE_UNAVAILABLE" in missing[1]


def test_delayed_fill_uses_only_closed_prior_one_minute_candles():
    helper = service()
    item = helper._promote_chapter4_entry(
        lifecycle(), strong_bar(7, "LONG"),
        prior_closed_1m=(strong_bar(5, "LONG"), strong_bar(6, "LONG")),
    )
    assert item.chapter5_entry_bar.count == 3
    assert item.chapter5_entry_bar.final_quality is None
    item = helper._observe_chapter5_entry_bar(item, strong_bar(8, "LONG"))
    assert item.chapter5_entry_bar.final_quality is None
    item = helper._observe_chapter5_entry_bar(item, strong_bar(9, "LONG"))
    assert item.chapter5_entry_bar.final_quality == "STRONG_DIRECTIONAL"
    assert item.entry_bar_open_time == (START + timedelta(minutes=5)).isoformat()
    assert item.entry_bar_index == 11


def test_missing_one_minute_or_late_activation_fails_closed():
    helper = service()
    item = helper._promote_chapter4_entry(
        lifecycle(), strong_bar(7, "LONG"),
        prior_closed_1m=(strong_bar(5, "LONG"),),
    )
    for minute in (8, 9):
        item = helper._observe_chapter5_entry_bar(item, strong_bar(minute, "LONG"))
    assert item.chapter5_entry_bar.final_quality is None
    assert item.chapter5_entry_bar.count == 1


def test_lifecycle_observation_is_idempotent():
    helper = service()
    item = helper._promote_chapter4_entry(lifecycle(), strong_bar(5, "LONG"))
    observed = helper._observe_chapter5_entry_bar(item, strong_bar(6, "LONG"))
    assert helper._observe_chapter5_entry_bar(observed, strong_bar(6, "LONG")) == observed
    for minute in (7, 8, 9):
        observed = helper._observe_chapter5_entry_bar(
            observed, strong_bar(minute, "LONG")
        )
    assert observed.chapter5_entry_bar.final_quality == "STRONG_DIRECTIONAL"
    assert helper._observe_chapter5_entry_bar(
        observed, strong_bar(9, "LONG")
    ) == observed


def test_later_followthrough_cannot_backdate_entry_quality():
    helper = service()
    item = helper._promote_chapter4_entry(lifecycle(), strong_bar(5, "LONG"))
    for minute in range(6, 10):
        item = helper._observe_chapter5_entry_bar(item, strong_bar(minute, "LONG"))
    entry_evidence = item.chapter5_entry_bar
    for minute in range(10, 15):
        bar = strong_bar(minute, "LONG")
        item = helper._observe_chapter5_entry_bar(item, bar)
        item = helper._advance_chapter4_post_entry(item, bar)
    assert item.chapter5_entry_bar == entry_evidence
    assert len(item.post_entry_lifecycle.completed_bars) == 1
    assert item.post_entry_lifecycle.completed_bars[0].open_time == (
        START + timedelta(minutes=10)
    ).isoformat()


def test_runtime_wiring_and_no_market_fetch_in_diagnostic_helper():
    process = inspect.getsource(LiveSignalLifecycleService._process_item)
    helper = inspect.getsource(LiveSignalLifecycleService._observe_chapter5_entry_bar)
    assert "_promote_chapter4_entry" in process
    assert "_observe_chapter5_entry_bar" in process
    assert "prior_closed_1m=" in process
    assert "TIMEFRAME_SECONDS" in helper
    assert "fetch" not in helper
    assert "append_event" not in helper
    assert "update_stop_loss" not in helper


def test_metadata_backward_compatibility_without_chapter5_field():
    initial = lifecycle()
    stored = initial.to_metadata()
    del stored["chapter5_entry_bar"]
    restored = Chapter4SignalEntryLifecycle.from_metadata(stored)
    assert restored == initial
    assert dataclasses.replace(initial, chapter5_entry_bar=None) == initial
