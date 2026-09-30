from datetime import UTC, datetime, timedelta
import httpx
import pytest
from app.modules.market_data.binance_futures import BinanceFuturesMarketDataProvider

@pytest.mark.asyncio
async def test_binance_normalizes_closed_candles():
    start = datetime(2026, 9, 2, 8, 0, tzinfo=UTC)
    now = start + timedelta(minutes=45, seconds=1)
    def ms(dt):
        return int(dt.timestamp() * 1000)
    rows = []
    for i in range(3):
        ot = start + timedelta(minutes=15*i)
        ct = ot + timedelta(minutes=15) - timedelta(milliseconds=1)
        rows.append([ms(ot), "100", "110", "90", "105", "10", ms(ct)])

    async def handler(request):
        assert request.url.path == "/fapi/v1/klines"
        return httpx.Response(200, json=rows)

    p = BinanceFuturesMarketDataProvider(transport=httpx.MockTransport(handler), clock=lambda: now)
    try:
        s = await p.get_snapshot(symbol="btcusdt", timeframe="15m", limit=2, market_type="futures")
    finally:
        await p.aclose()

    assert s.symbol == "BTCUSDT"
    assert len(s.candles) == 2
    assert s.candles[-1].close_time <= now
