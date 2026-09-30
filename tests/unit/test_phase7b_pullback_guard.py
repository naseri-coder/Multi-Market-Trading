from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.modules.brooks_core.pullback_guard import assess_h1_h2_l1_l2_counting_window
from app.modules.market_data.entities import Candle


def candle(i, high, low):
    start = datetime(2026, 9, 2, tzinfo=UTC) + timedelta(minutes=15*i)
    high = Decimal(str(high))
    low = Decimal(str(low))
    mid = (high + low) / 2
    return Candle(
        open_time=start,
        close_time=start + timedelta(minutes=15),
        open=mid,
        high=high,
        low=low,
        close=mid,
        volume=Decimal("1"),
    )


def test_inside_bar_blocks_unresolved_h2_counting() -> None:
    candles = (
        candle(0, 110, 90),
        candle(1, 108, 92),
    )
    result = assess_h1_h2_l1_l2_counting_window(candles)
    assert result.allowed is False
    assert result.blocked_indices == (1,)


def test_simple_non_edge_window_is_only_eligible_not_counted() -> None:
    candles = (
        candle(0, 110, 90),
        candle(1, 111, 91),
        candle(2, 112, 92),
    )
    result = assess_h1_h2_l1_l2_counting_window(candles)
    assert result.allowed is True
    assert "does not itself define H1/H2/L1/L2" in result.reason
