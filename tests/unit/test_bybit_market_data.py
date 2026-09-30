from datetime import UTC, datetime, timedelta
import httpx
import pytest
from app.modules.market_data.bybit import BybitMarketDataProvider

@pytest.mark.asyncio
async def test_bybit_reverses_newest_first_and_filters_open_candle():
    start = datetime(2026, 9, 2, 8, 0, tzinfo=UTC)
    now = start + timedelta(minutes=45, seconds=1)
    def ms(dt):
        return int(dt.timestamp() * 1000)
    rows = []
    for i in range(4):
        ot = start + timedelta(minutes=15*i)
        rows.append([str(ms(ot)), "100", "110", "90", "105", "10", "0"])
    rows = list(reversed(rows))
    payload = {"retCode": 0, "result": {"list": rows}}

    async def handler(request):
        assert request.url.path == "/v5/market/kline"
        return httpx.Response(200, json=payload)

    p = BybitMarketDataProvider(
        transport=httpx.MockTransport(handler),
        clock=lambda: now,
    )
    try:
        s = await p.get_snapshot(
            symbol="BTCUSDT", timeframe="15m", limit=2, market_type="spot"
        )
    finally:
        await p.aclose()

    assert len(s.candles) == 2
    assert s.candles[0].open_time < s.candles[1].open_time
    assert s.candles[-1].close_time <= now
