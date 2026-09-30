from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.modules.brooks_core.causal_structure import (
    confirm_swings_causally,
    evaluate_br031_structure,
)
from app.modules.market_data.entities import Candle


def make_candles(highs, lows):
    start = datetime(2026, 9, 2, tzinfo=UTC)
    out = []
    for i, (h, l) in enumerate(zip(highs, lows)):
        low = Decimal(str(l))
        high = Decimal(str(h))
        mid = (high + low) / 2
        out.append(
            Candle(
                open_time=start + timedelta(minutes=15*i),
                close_time=start + timedelta(minutes=15*(i+1)),
                open=mid,
                high=high,
                low=low,
                close=mid,
                volume=Decimal("1"),
            )
        )
    return tuple(out)


def test_confirmed_swing_is_not_visible_before_right_bars() -> None:
    candles = make_candles(
        [10, 11, 15, 12, 11],
        [5, 6, 7, 6, 5],
    )
    full = confirm_swings_causally(candles, left_bars=2, right_bars=2)
    assert any(s.kind == "HIGH" and s.candle_index == 2 and s.confirmed_at_index == 4 for s in full.swings)

    partial = confirm_swings_causally(candles[:4], left_bars=2, right_bars=2)
    assert not any(s.candle_index == 2 for s in partial.swings)


def test_equal_boundary_is_marked_ambiguous_not_strict_swing() -> None:
    candles = make_candles(
        [10, 12, 12, 11, 10],
        [5, 6, 7, 6, 5],
    )
    scan = confirm_swings_causally(candles, left_bars=1, right_bars=1)
    assert 1 in scan.ambiguous_indices or 2 in scan.ambiguous_indices


def test_br031_returns_ambiguous_when_not_enough_swings() -> None:
    candles = make_candles([10, 11, 12, 11, 10], [5, 6, 7, 6, 5])
    scan = confirm_swings_causally(candles, left_bars=2, right_bars=2)
    result = evaluate_br031_structure(scan)
    assert result.direction == "AMBIGUOUS"
