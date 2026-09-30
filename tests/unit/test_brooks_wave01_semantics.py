from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.modules.brooks_core.books_entities import BrooksContextAssessment, ContextMetrics
from app.modules.brooks_core.books_full_engine import BrooksTrilogyFullCoreEngine
from app.modules.brooks_core.books_full_entities import BrooksPatternCandidate
from app.modules.brooks_core.books_full_patterns import (
    _bear_reversal as full_bear_reversal,
    _bull_reversal as full_bull_reversal,
    detect_breakout_family,
)
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.brooks_core.context_classifier import (
    is_bear_reversal_bar_minimum,
    is_bull_reversal_bar_minimum,
    is_strong_bull_bar,
)
from app.modules.brooks_core.pattern_expansion import (
    _bear_reversal as expanded_bear_reversal,
    _bull_reversal as expanded_bull_reversal,
    detect_reversal_bar_failure,
    scan_generic_breakout_attempt_observations,
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


def snapshot(candles: list[Candle]) -> MarketSnapshot:
    items = tuple(candles)
    return MarketSnapshot(
        exchange="binance", market_type="spot", symbol="BTCUSDT", timeframe="15m",
        candles=items, captured_at=items[-1].close_time, source="WAVE01_TEST",
    )


def simple_context(regime: str = "AMBIGUOUS", always_in: str = "UNRESOLVED"):
    return SimpleNamespace(
        regime=regime,
        structure_direction=regime if regime in {"BULL_TREND", "BEAR_TREND"} else "AMBIGUOUS",
        always_in=always_in,
        breakout_direction="UNRESOLVED",
        breakout_streak=0,
        metrics=SimpleNamespace(bar_overlap_rate=Decimal("0.2")),
    )


def full_context(*, breakout_direction: str, breakout_streak: int) -> BrooksContextAssessment:
    return BrooksContextAssessment(
        regime="AMBIGUOUS", always_in="UNRESOLVED", reason="wave01",
        structure_direction="AMBIGUOUS", breakout_direction=breakout_direction,
        breakout_streak=breakout_streak,
        metrics=ContextMetrics(
            directional_bar_fraction=Decimal("0.5"), body_overlap_rate=Decimal("0.2"),
            bar_overlap_rate=Decimal("0.2"), adjusted_displacement=Decimal("0.4"),
            close_path_efficiency=Decimal("0.5"), ema_side_fraction=Decimal("0.5"),
            strong_bull_bar_count=1, strong_bear_bar_count=1, tight_range_like=False,
        ),
    )


def breakout_candidate(direction: str, *reasons: str) -> BrooksPatternCandidate:
    return BrooksPatternCandidate(
        direction=direction, setup_type=f"BREAKOUT_{direction}", family="BREAKOUT",
        signal_index=9, reasons=tuple(reasons),
        source_rule_ids=("BB-RNG-02-BREAKOUT-FOLLOWTHROUGH",),
        taxonomy="SOURCE_INTERPRETATION", priority=20,
        context_required="BREAKOUT_OR_TREND",
    )


def swing(kind: str, index: int):
    return SimpleNamespace(kind=kind, candle_index=index)


def scan_with(*items):
    return SimpleNamespace(swings=tuple(items))


@pytest.mark.parametrize(
    "candle,bull,bear",
    [
        (bar(0, "99", "110", "90", "100"), True, False),   # bull body only; midpoint exactly
        (bar(1, "104", "110", "90", "104"), True, False),  # midpoint-only bull; doji
        (bar(2, "101", "110", "90", "100"), False, True),  # bear body only; midpoint exactly
        (bar(3, "96", "110", "90", "96"), False, True),    # midpoint-only bear; doji
        (bar(4, "100", "110", "90", "100"), False, False),
    ],
)
def test_wave01_targeted_reversal_minimum_or_semantics(candle, bull, bear):
    assert is_bull_reversal_bar_minimum(candle) is bull
    assert is_bear_reversal_bar_minimum(candle) is bear
    assert full_bull_reversal(candle) is bull
    assert expanded_bull_reversal(candle) is bull
    assert full_bear_reversal(candle) is bear
    assert expanded_bear_reversal(candle) is bear


def test_wave01_targeted_reversal_identity_is_not_strength_or_trade_eligibility():
    weak = bar(0, "99", "110", "90", "100")
    policy = BrooksFullCorePolicy()
    assert is_bull_reversal_bar_minimum(weak)
    assert not is_strong_bull_bar(weak, policy.context)


def test_wave01_targeted_midpoint_only_reversal_propagates_to_authorized_consumer():
    prior = bar(0, "96", "110", "90", "96")  # doji below midpoint => midpoint-only bear minimum
    final = bar(1, "96", "111", "95", "110")
    found = detect_reversal_bar_failure(
        snapshot([prior, final]), simple_context("BULL_TREND", "LONG"), BrooksFullCorePolicy()
    )
    assert [item.setup_type for item in found] == ["BEAR_REVERSAL_BAR_FAILURE_LONG"]


def _base_breakout_candles(final: Candle) -> list[Candle]:
    return [
        bar(0, "100", "102", "98", "101"),
        bar(1, "101", "103", "99", "102"),
        bar(2, "102", "105", "100", "103"),
        bar(3, "103", "104", "101", "102"),
        bar(4, "102", "104", "100", "103"),
        bar(5, "103", "104", "101", "102"),
        final,
    ]


def test_wave01_targeted_wick_extension_is_attempt_not_trade_candidate():
    candles = _base_breakout_candles(bar(6, "103", "106", "102", "104"))
    with patch(
        "app.modules.brooks_core.pattern_expansion.confirm_swings_causally",
        return_value=scan_with(swing("HIGH", 2)),
    ):
        obs = scan_generic_breakout_attempt_observations(
            snapshot(candles), simple_context(), BrooksFullCorePolicy()
        )
    attempt = next(item for item in obs if item.pattern_id == "BREAKOUT_ATTEMPT_LONG")
    assert attempt.role == "BREAKOUT_ATTEMPT"
    assert dict(attempt.metadata)["closed_beyond"] == "false"

    with patch(
        "app.modules.brooks_core.books_full_patterns._latest_swing_before",
        side_effect=lambda *a, **kw: swing("HIGH", 2) if kw["kind"] == "HIGH" else None,
    ):
        candidates = detect_breakout_family(snapshot(candles), simple_context(), BrooksFullCorePolicy())
    assert not any(item.family == "BREAKOUT" for item in candidates)


def test_wave01_targeted_short_wick_extension_is_attempt():
    candles = _base_breakout_candles(bar(6, "102", "103", "99", "101"))
    candles[2] = bar(2, "102", "105", "100", "103")
    with patch(
        "app.modules.brooks_core.pattern_expansion.confirm_swings_causally",
        return_value=scan_with(swing("LOW", 2)),
    ):
        obs = scan_generic_breakout_attempt_observations(
            snapshot(candles), simple_context(), BrooksFullCorePolicy()
        )
    attempt = next(item for item in obs if item.pattern_id == "BREAKOUT_ATTEMPT_SHORT")
    assert dict(attempt.metadata)["closed_beyond"] == "false"


def test_wave01_targeted_no_extension_has_no_attempt():
    candles = _base_breakout_candles(bar(6, "103", "104.5", "102", "104"))
    with patch(
        "app.modules.brooks_core.pattern_expansion.confirm_swings_causally",
        return_value=scan_with(swing("HIGH", 2)),
    ):
        obs = scan_generic_breakout_attempt_observations(
            snapshot(candles), simple_context(), BrooksFullCorePolicy()
        )
    assert not any(item.pattern_id == "BREAKOUT_ATTEMPT_LONG" for item in obs)


def test_wave01_targeted_one_decisive_breakout_bar_is_candidate():
    candles = _base_breakout_candles(bar(6, "103", "109", "102", "108.5"))
    with patch(
        "app.modules.brooks_core.books_full_patterns._latest_swing_before",
        side_effect=lambda *a, **kw: swing("HIGH", 2) if kw["kind"] == "HIGH" else None,
    ):
        found = detect_breakout_family(snapshot(candles), simple_context(), BrooksFullCorePolicy())
    item = next(x for x in found if x.setup_type == "BREAKOUT_LONG")
    assert "decisive_single_bar_breakout" in item.reasons
    assert "breakout_follow_through_confirmed" not in item.reasons
    assert dict(item.metadata)["follow_through"] == "false"


def test_wave01_targeted_two_strong_bars_preserve_follow_through_evidence():
    candles = _base_breakout_candles(bar(6, "106", "109", "105", "108.5"))
    candles[5] = bar(5, "102", "107", "101.5", "106.5")
    with patch(
        "app.modules.brooks_core.books_full_patterns._latest_swing_before",
        side_effect=lambda *a, **kw: swing("HIGH", 1) if kw["kind"] == "HIGH" else None,
    ):
        found = detect_breakout_family(snapshot(candles), simple_context(), BrooksFullCorePolicy())
    item = next(x for x in found if x.setup_type == "BREAKOUT_LONG")
    assert "strong_directional_breakout_bar" in item.reasons
    assert "breakout_follow_through_confirmed" in item.reasons
    assert "two_consecutive_strong_bars_beyond_breakout_level" in item.reasons
    assert dict(item.metadata)["follow_through"] == "true"


def test_wave01_targeted_context_gate_accepts_decisive_single_bar_not_attempt_only():
    engine = BrooksTrilogyFullCoreEngine()
    decisive = breakout_candidate(
        "LONG", "close_beyond_causal_swing_level", "strong_directional_breakout_bar",
        "decisive_single_bar_breakout",
    )
    status, _ = engine._context_contract_status(
        decisive, full_context(breakout_direction="LONG", breakout_streak=1)
    )
    assert status == "PASS"

    attempt_only = breakout_candidate(
        "LONG", "price_extension_beyond_causal_swing_level", "observation_only_not_confirmation"
    )
    status, reason = engine._context_contract_status(
        attempt_only, full_context(breakout_direction="LONG", breakout_streak=1)
    )
    assert status == "REJECT"
    assert reason == "breakout_context_not_confirmed"


def test_wave01_targeted_breakout_attempt_scans_only_history_before_current_bar():
    candles = _base_breakout_candles(bar(6, "103", "106", "102", "104"))
    seen_lengths: list[int] = []

    def fake_scan(items, **kwargs):
        seen_lengths.append(len(items))
        return scan_with(swing("HIGH", 2))

    with patch(
        "app.modules.brooks_core.pattern_expansion.confirm_swings_causally",
        side_effect=fake_scan,
    ):
        obs = scan_generic_breakout_attempt_observations(
            snapshot(candles), simple_context(), BrooksFullCorePolicy()
        )
    assert seen_lengths == [len(candles) - 1]
    assert any(item.pattern_id == "BREAKOUT_ATTEMPT_LONG" for item in obs)
    assert all(item.signal_index == len(candles) - 1 for item in obs)


def test_wave01_targeted_context_gate_preserves_two_bar_follow_through_as_stronger_evidence():
    engine = BrooksTrilogyFullCoreEngine()
    item = breakout_candidate(
        "LONG", "close_beyond_causal_swing_level", "strong_directional_breakout_bar",
        "two_consecutive_strong_bars_beyond_breakout_level", "breakout_follow_through_confirmed",
    )
    status, reason = engine._context_contract_status(
        item, full_context(breakout_direction="LONG", breakout_streak=2)
    )
    assert status == "PASS"
    assert reason == "breakout_context_confirmed"
