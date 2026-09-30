from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.modules.brooks_core.second_entry_v2 import detect_book_second_entry
from app.modules.market_data.entities import Candle


BASE = datetime(2026, 1, 1, tzinfo=UTC)


def candle(i, o, h, l, c):
    return Candle(
        open_time=BASE + timedelta(minutes=15 * i),
        close_time=BASE + timedelta(minutes=15 * (i + 1)),
        open=Decimal(str(o)),
        high=Decimal(str(h)),
        low=Decimal(str(l)),
        close=Decimal(str(c)),
        volume=Decimal("1"),
    )


def test_h2_requires_distinct_later_second_excursion():
    candles = (
        candle(0, 10.0, 10.4, 9.8, 10.2),  # pullback origin high
        candle(1, 10.1, 10.2, 9.5, 9.7),   # down progress
        candle(2, 9.7, 10.3, 9.6, 10.0),   # H1
        candle(3, 10.0, 10.1, 9.2, 9.4),   # distinct second excursion
        candle(4, 9.4, 10.2, 9.3, 10.0),   # H2 on final bar
    )
    result = detect_book_second_entry(candles, trend_direction="BULL_TREND", start_index=0)
    assert result.setup is not None
    assert result.setup.setup_type == "H2_CONFIRMED"
    assert result.setup.direction == "LONG"
    assert [event.label for event in result.events] == ["H1", "H2"]


def test_equal_high_and_inside_bar_are_neutral_not_global_blockers():
    candles = (
        candle(0, 10.0, 10.5, 9.8, 10.2),
        candle(1, 10.1, 10.2, 9.4, 9.6),
        candle(2, 9.6, 10.3, 9.5, 10.0),   # H1
        candle(3, 10.0, 10.3, 9.6, 9.8),  # equal high -> no event
        candle(4, 9.8, 10.1, 9.7, 9.9),   # inside -> neutral
        candle(5, 9.9, 10.0, 9.2, 9.4),   # second excursion
        candle(6, 9.4, 10.2, 9.3, 10.0),   # H2
    )
    result = detect_book_second_entry(candles, trend_direction="BULL_TREND", start_index=0)
    assert result.setup is not None
    assert result.setup.setup_type == "H2_CONFIRMED"
    assert [event.label for event in result.events] == ["H1", "H2"]


def test_l2_is_mirror_of_h2():
    candles = (
        candle(0, 10.0, 10.2, 9.5, 9.8),
        candle(1, 9.8, 10.6, 9.7, 10.4),   # up progress
        candle(2, 10.4, 10.5, 9.6, 9.9),  # L1
        candle(3, 9.9, 10.9, 9.8, 10.7),  # distinct second excursion up
        candle(4, 10.7, 10.8, 9.7, 10.0), # L2 final
    )
    result = detect_book_second_entry(candles, trend_direction="BEAR_TREND", start_index=0)
    assert result.setup is not None
    assert result.setup.setup_type == "L2_CONFIRMED"
    assert result.setup.direction == "SHORT"
    assert [event.label for event in result.events] == ["L1", "L2"]


def test_h2_that_happened_before_final_bar_is_not_relabelled():
    candles = (
        candle(0, 10.0, 10.4, 9.8, 10.2),
        candle(1, 10.1, 10.2, 9.5, 9.7),
        candle(2, 9.7, 10.3, 9.6, 10.0),   # H1
        candle(3, 10.0, 10.1, 9.2, 9.4),  # second excursion
        candle(4, 9.4, 10.2, 9.3, 10.0),  # H2, but not final
        candle(5, 10.0, 10.1, 9.8, 9.9),
    )
    result = detect_book_second_entry(candles, trend_direction="BULL_TREND", start_index=0)
    assert result.setup is None
    assert result.highest_entry_number == 2
    assert "occurred before final" in result.reason
