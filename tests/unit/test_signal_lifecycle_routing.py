"""Regression tests for market-aware LIVE signal lifecycle routing."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.modules.market_data.binance import BinanceSpotMarketDataProvider
from app.modules.market_data.binance_futures import BinanceFuturesMarketDataProvider
from app.modules.operations.lifecycle import LifecycleItem, LiveSignalLifecycleService


def _service(provider):
    return LiveSignalLifecycleService(
        database=object(),
        provider=provider,
        bot=object(),
        vip_channel_id=1,
        cutover_at=datetime(2026, 9, 2, tzinfo=UTC),
        candle_limit=20,
    )


def _item(signal_id: int, symbol: str, market_type: str) -> LifecycleItem:
    return LifecycleItem(
        signal=SimpleNamespace(id=signal_id, symbol=symbol),
        metadata=SimpleNamespace(exchange="binance", market_type=market_type),
        delivery=SimpleNamespace(),
        targets=(),
    )

@pytest.mark.asyncio
async def test_historical_spot_metadata_routes_to_spot_provider():
    current = BinanceFuturesMarketDataProvider()
    service = _service(current)
    routed, owned = service._provider_for_market(exchange="binance", market_type="spot")
    try:
        assert type(routed) is BinanceSpotMarketDataProvider
        assert owned is True
    finally:
        await routed.aclose()
        await current.aclose()


@pytest.mark.asyncio
async def test_historical_futures_metadata_routes_to_futures_provider():
    current = BinanceFuturesMarketDataProvider()
    service = _service(current)
    routed, owned = service._provider_for_market(exchange="binance", market_type="futures")
    try:
        assert routed is current
        assert owned is False
    finally:
        await current.aclose()


@pytest.mark.asyncio
async def test_historical_linear_metadata_routes_to_futures_provider():
    current = BinanceFuturesMarketDataProvider()
    service = _service(current)
    routed, owned = service._provider_for_market(exchange="binance", market_type="linear")
    try:
        assert routed is current
        assert isinstance(routed, BinanceFuturesMarketDataProvider)
        assert owned is False
    finally:
        await current.aclose()


class RecordingProvider:
    exchange = "binance"

    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[dict[str, object]] = []

    async def get_snapshot(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(candles=("closed-candle",))


async def _prepare_service(service, items, providers, processed):
    async def retry_pending():
        return 0

    async def load_items():
        return tuple(items)

    async def process_item(item, candles):
        assert candles == ("closed-candle",)
        processed.append(item.signal.id)
        return {"changed": False, "ambiguous": False}

    service._retry_pending_message_updates = retry_pending
    service._load_items = load_items
    service._process_item = process_item
    service._provider_for_market = (
        lambda *, exchange, market_type: (providers[market_type], False)
    )


@pytest.mark.asyncio
async def test_lifecycle_selects_provider_per_metadata():
    providers = {
        "spot": RecordingProvider("spot"),
        "futures": RecordingProvider("futures"),
        "linear": RecordingProvider("linear"),
    }
    items = [
        _item(1, "BTCUSDT", "spot"),
        _item(2, "ETHUSDT", "futures"),
        _item(3, "SOLUSDT", "linear"),
    ]
    processed: list[int] = []
    service = _service(SimpleNamespace(exchange="unused"))
    await _prepare_service(service, items, providers, processed)
    result = await service.run_once()

    assert result["tracked"] == 3
    assert processed == [1, 2, 3]
    assert providers["spot"].calls[0]["market_type"] == "spot"
    assert providers["futures"].calls[0]["market_type"] == "futures"
    assert providers["linear"].calls[0]["market_type"] == "linear"


@pytest.mark.asyncio
async def test_lifecycle_processes_mixed_market_queue():
    spot = RecordingProvider("spot")
    futures = RecordingProvider("futures")
    providers = {"spot": spot, "futures": futures, "linear": futures}
    items = [
        _item(10, "BTCUSDT", "spot"),
        _item(11, "BTCUSDT", "spot"),
        _item(12, "BTCUSDT", "futures"),
        _item(13, "BTCUSDT", "linear"),
    ]
    processed: list[int] = []
    service = _service(SimpleNamespace(exchange="unused"))
    await _prepare_service(service, items, providers, processed)

    result = await service.run_once()

    assert result["tracked"] == 4
    assert processed == [10, 11, 12, 13]
    assert [call["market_type"] for call in spot.calls] == ["spot"]
    assert [call["market_type"] for call in futures.calls] == ["futures", "linear"]
