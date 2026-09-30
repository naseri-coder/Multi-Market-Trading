from datetime import UTC, datetime, timedelta
from decimal import Decimal
import pytest
from app.modules.market_data.entities import Candle, MarketSnapshot, validate_candle_sequence

def make_candle(start):
    return Candle(
        open_time=start,
        close_time=start + timedelta(minutes=15),
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal("105"),
        volume=Decimal("1"),
    )

def test_snapshot_hash_is_deterministic():
    start = datetime(2026, 9, 2, 8, tzinfo=UTC)
    snap = MarketSnapshot(
        exchange="binance",
        market_type="spot",
        symbol="BTCUSDT",
        timeframe="15m",
        candles=(make_candle(start), make_candle(start + timedelta(minutes=15))),
        captured_at=start + timedelta(minutes=31),
    )
    assert len(snap.snapshot_hash) == 64
    assert snap.snapshot_hash == snap.snapshot_hash

def test_missing_candle_is_rejected():
    start = datetime(2026, 9, 2, 8, tzinfo=UTC)
    with pytest.raises(ValueError, match="missing or misaligned"):
        validate_candle_sequence(
            (make_candle(start), make_candle(start + timedelta(minutes=30))),
            timeframe="15m",
        )

def test_future_candle_is_rejected():
    start = datetime(2026, 9, 2, 8, tzinfo=UTC)
    with pytest.raises(ValueError, match="future/unclosed"):
        MarketSnapshot(
            exchange="binance",
            market_type="spot",
            symbol="BTCUSDT",
            timeframe="15m",
            candles=(make_candle(start),),
            captured_at=start + timedelta(minutes=10),
        )
