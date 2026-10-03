"""Public internet smoke tests for Binance Futures/Bybit market data."""

import os
import pytest

from app.modules.market_data.binance_futures import BinanceFuturesMarketDataProvider
from app.modules.market_data.bybit import BybitMarketDataProvider

pytestmark = pytest.mark.skipif(os.getenv("RUN_PUBLIC_MARKET_DATA_SMOKE") != "1", reason="explicit public market-data smoke opt-in required")

@pytest.mark.asyncio
async def test_binance_public_closed_candles():
    p = BinanceFuturesMarketDataProvider()
    try:
        s = await p.get_snapshot(symbol="BTCUSDT", timeframe="15m", limit=20, market_type="futures")
    finally:
        await p.aclose()
    assert len(s.candles) == 20
    assert s.snapshot_hash

@pytest.mark.asyncio
async def test_bybit_public_closed_candles():
    p = BybitMarketDataProvider()
    try:
        s = await p.get_snapshot(symbol="BTCUSDT", timeframe="15m", limit=20, market_type="spot")
    finally:
        await p.aclose()
    assert len(s.candles) == 20
    assert s.snapshot_hash
