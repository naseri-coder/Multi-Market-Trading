from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.modules.brooks_core.second_entry import detect_second_entry
from app.modules.market_data.entities import Candle


def candle(i, high, low):
    start = datetime(2026, 9, 2, tzinfo=UTC) + timedelta(minutes=15 * i)
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


def test_bull_two_leg_pullback_detects_h2_on_final_bar():
    candles = (
        candle(0, 110, 100),
        candle(1, 109, 99),    # first down leg
        candle(2, 111, 100),   # H1 attempt
        candle(3, 110, 98),    # second down leg
        candle(4, 112, 99),    # H2 attempt
    )
    result = detect_second_entry(
        candles,
        trend_direction="BULL_TREND",
        start_index=0,
    )
    assert result.setup is not None
    assert result.setup.direction == "LONG"
    assert result.setup.setup_type == "H2_CONFIRMED"


def test_bear_two_leg_pullback_detects_l2_on_final_bar():
    candles = (
        candle(0, 100, 90),
        candle(1, 101, 91),    # first up leg
        candle(2, 100, 89),    # L1 attempt
        candle(3, 102, 90),    # second up leg
        candle(4, 101, 88),    # L2 attempt
    )
    result = detect_second_entry(
        candles,
        trend_direction="BEAR_TREND",
        start_index=0,
    )
    assert result.setup is not None
    assert result.setup.direction == "SHORT"
    assert result.setup.setup_type == "L2_CONFIRMED"


def test_inside_bar_edge_case_remains_fail_closed():
    candles = (
        candle(0, 110, 90),
        candle(1, 108, 92),
        candle(2, 111, 91),
        candle(3, 109, 93),
    )
    result = detect_second_entry(
        candles,
        trend_direction="BULL_TREND",
        start_index=0,
    )
    assert result.setup is None
    assert result.blocked_indices
