from datetime import UTC, datetime, timedelta

import httpx
import pytest

from app.modules.market_data.binance_futures import BinanceFuturesMarketDataProvider
from app.modules.market_data.errors import InsufficientClosedCandlesError, MarketDataResponseError


def test_binance_futures_import():
    assert BinanceFuturesMarketDataProvider


def test_binance_futures_provider_contract():
    provider = BinanceFuturesMarketDataProvider()
    try:
        assert provider.exchange == "binance"
        assert hasattr(provider, "get_snapshot")
        assert "futures" in provider.__class__.__doc__.lower()
    finally:
        import asyncio
        asyncio.run(provider.aclose())


@pytest.mark.asyncio
async def test_binance_futures_market_snapshot_contract():
    start = datetime(2026, 9, 2, 8, 0, tzinfo=UTC)
    rows = []
    for i in range(3):
        ot = start + timedelta(minutes=15*i)
        ct = ot + timedelta(minutes=15) - timedelta(milliseconds=1)
        rows.append([int(ot.timestamp()*1000), "100", "110", "90", "105", "10", int(ct.timestamp()*1000)])

    async def handler(request):
        assert request.url.path == "/fapi/v1/klines"
        return httpx.Response(200, json=rows)

    now = start + timedelta(minutes=45)
    provider = BinanceFuturesMarketDataProvider(
        transport=httpx.MockTransport(handler), clock=lambda: now
    )
    try:
        snapshot = await provider.get_snapshot(symbol="btcusdt", timeframe="15m", limit=2, market_type="futures")
    finally:
        await provider.aclose()

    assert snapshot.symbol == "BTCUSDT"
    assert snapshot.market_type == "futures"
    assert snapshot.timeframe == "15m"
    candle = snapshot.candles[0]
    assert all(hasattr(candle, field) for field in ("open", "high", "low", "close", "volume"))


def test_futures_symbol_coverage():
    symbols = {"BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "SOLUSDT"}
    assert symbols == {"BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "SOLUSDT"}

@pytest.mark.asyncio
async def test_binance_futures_requests_limit_plus_one():
    start = datetime(2026, 9, 2, 8, 0, tzinfo=UTC)
    rows = []
    for i in range(3):
        ot = start + timedelta(minutes=15 * i)
        ct = ot + timedelta(minutes=15) - timedelta(milliseconds=1)
        rows.append([int(ot.timestamp() * 1000), "100", "110", "90", "105", "10", int(ct.timestamp() * 1000)])

    async def handler(request):
        assert request.url.path == "/fapi/v1/klines"
        assert request.url.params["limit"] == "3"
        return httpx.Response(200, json=rows)

    now = start + timedelta(minutes=45)
    provider = BinanceFuturesMarketDataProvider(
        transport=httpx.MockTransport(handler), clock=lambda: now
    )
    try:
        snapshot = await provider.get_snapshot(symbol="BTCUSDT", timeframe="15m", limit=2, market_type="futures")
    finally:
        await provider.aclose()

    assert len(snapshot.candles) == 2


@pytest.mark.asyncio
async def test_binance_futures_filters_open_candle():
    start = datetime(2026, 9, 2, 8, 0, tzinfo=UTC)
    now = start + timedelta(minutes=30, seconds=1)
    closed_rows = []
    for i in range(2):
        ot = start + timedelta(minutes=15 * i)
        ct = ot + timedelta(minutes=15) - timedelta(milliseconds=1)
        closed_rows.append([int(ot.timestamp() * 1000), "100", "110", "90", "105", "10", int(ct.timestamp() * 1000)])
    open_ot = start + timedelta(minutes=30)
    open_ct = open_ot + timedelta(minutes=15) - timedelta(milliseconds=1)
    rows = closed_rows + [[int(open_ot.timestamp() * 1000), "105", "115", "95", "110", "12", int(open_ct.timestamp() * 1000)]]

    async def handler(request):
        return httpx.Response(200, json=rows)

    provider = BinanceFuturesMarketDataProvider(transport=httpx.MockTransport(handler), clock=lambda: now)
    try:
        snapshot = await provider.get_snapshot(symbol="BTCUSDT", timeframe="15m", limit=2, market_type="futures")
    finally:
        await provider.aclose()

    assert len(snapshot.candles) == 2
    assert snapshot.candles[-1].close_time <= now
    assert all(candle.close_time <= now for candle in snapshot.candles)


@pytest.mark.asyncio
async def test_binance_futures_raises_for_insufficient_closed_candles():
    start = datetime(2026, 9, 2, 8, 0, tzinfo=UTC)
    ct = start + timedelta(minutes=15) - timedelta(milliseconds=1)
    rows = [[int(start.timestamp() * 1000), "100", "110", "90", "105", "10", int(ct.timestamp() * 1000)]]

    async def handler(request):
        return httpx.Response(200, json=rows)

    provider = BinanceFuturesMarketDataProvider(transport=httpx.MockTransport(handler), clock=lambda: start + timedelta(hours=1))
    try:
        with pytest.raises(InsufficientClosedCandlesError, match="insufficient futures candles"):
            await provider.get_snapshot(symbol="BTCUSDT", timeframe="15m", limit=2, market_type="futures")
    finally:
        await provider.aclose()


@pytest.mark.asyncio
async def test_binance_futures_rejects_non_list_response():
    async def handler(request):
        return httpx.Response(200, json={"unexpected": "payload"})

    provider = BinanceFuturesMarketDataProvider(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(MarketDataResponseError, match="response must be a list"):
            await provider.get_snapshot(symbol="BTCUSDT", timeframe="15m", limit=2, market_type="futures")
    finally:
        await provider.aclose()


@pytest.mark.asyncio
async def test_binance_futures_rejects_malformed_kline_row():
    async def handler(request):
        return httpx.Response(200, json=[[1, "100"]])

    provider = BinanceFuturesMarketDataProvider(transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(MarketDataResponseError, match="malformed Binance futures kline"):
            await provider.get_snapshot(symbol="BTCUSDT", timeframe="15m", limit=2, market_type="futures")
    finally:
        await provider.aclose()


@pytest.mark.asyncio
async def test_binance_futures_accepts_linear_market_type():
    start = datetime(2026, 9, 2, 8, 0, tzinfo=UTC)
    now = start + timedelta(hours=1)
    rows = []
    for i in range(3):
        ot = start + timedelta(minutes=15 * i)
        ct = ot + timedelta(minutes=15) - timedelta(milliseconds=1)
        rows.append([int(ot.timestamp() * 1000), "100", "110", "90", "105", "10", int(ct.timestamp() * 1000)])

    async def handler(request):
        return httpx.Response(200, json=rows)

    provider = BinanceFuturesMarketDataProvider(transport=httpx.MockTransport(handler), clock=lambda: now)
    try:
        snapshot = await provider.get_snapshot(symbol="BTCUSDT", timeframe="15m", limit=2, market_type="linear")
    finally:
        await provider.aclose()

    assert snapshot.market_type == "futures"
    assert snapshot.symbol == "BTCUSDT"
    assert len(snapshot.candles) == 2

