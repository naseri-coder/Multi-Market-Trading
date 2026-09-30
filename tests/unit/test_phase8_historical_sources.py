from datetime import UTC, datetime, timedelta
import json

import httpx
import pytest

from app.modules.shadow_replay.historical import (
    BinanceHistoricalCandleSource,
    BybitHistoricalCandleSource,
)


def ms(dt):
    return int(dt.timestamp() * 1000)


@pytest.mark.asyncio
async def test_binance_historical_source_returns_only_closed_ordered_candles():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows = []
    for i in range(3):
        open_time = start + timedelta(minutes=15 * i)
        close_time = open_time + timedelta(minutes=15) - timedelta(milliseconds=1)
        rows.append([
            ms(open_time), "100", "102", "99", "101", "5", ms(close_time)
        ])

    async def handler(request):
        return httpx.Response(200, json=rows)

    source = BinanceHistoricalCandleSource(
        transport=httpx.MockTransport(handler)
    )
    try:
        candles = await source.get_closed_candles(
            symbol="btcusdt",
            timeframe="15m",
            limit=3,
            market_type="spot",
            end_at=start + timedelta(minutes=46),
        )
    finally:
        await source.aclose()

    assert len(candles) == 3
    assert candles[0].open_time < candles[-1].open_time
    assert all(c.close_time <= start + timedelta(minutes=46) for c in candles)


@pytest.mark.asyncio
async def test_bybit_historical_source_normalizes_reverse_api_order():
    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows = []
    for i in range(3):
        open_time = start + timedelta(minutes=15 * i)
        rows.append([
            str(ms(open_time)), "100", "102", "99", "101", "5"
        ])
    rows.reverse()

    async def handler(request):
        return httpx.Response(
            200,
            json={"retCode": 0, "result": {"list": rows}},
        )

    source = BybitHistoricalCandleSource(
        transport=httpx.MockTransport(handler)
    )
    try:
        candles = await source.get_closed_candles(
            symbol="btcusdt",
            timeframe="15m",
            limit=3,
            market_type="spot",
            end_at=start + timedelta(minutes=46),
        )
    finally:
        await source.aclose()

    assert len(candles) == 3
    assert candles[0].open_time < candles[-1].open_time
    assert candles[-1].close_time == start + timedelta(minutes=45)
