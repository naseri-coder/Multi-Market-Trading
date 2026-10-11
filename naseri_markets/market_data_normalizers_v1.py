"""Strict offline fixture mappers; NOT authenticated exchange/broker API clients.

Crypto volume is traded units; FX tick_volume is a tick count, never a
claim of exchange-traded base volume. Explicit provider identifiers are always
supplied by the host through FeedDefinition, never by strategy source.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Mapping

from .contracts import Market
from .core_api_v1 import BidAskTick, ClosedCandle, CoreEventType, _utc
from .market_data_engine_v1 import FeedDefinition, MarketDataRefused, PriceBasis, VolumeSemantics


def _decimal(value: object, *, nonnegative: bool = False) -> Decimal:
    if type(value) is not str or not 0 < len(value) <= 64:
        raise MarketDataRefused("DECIMAL_STRING_REQUIRED")
    try:
        n = Decimal(value)
    except InvalidOperation as exc:
        raise MarketDataRefused("INVALID_DECIMAL") from exc
    if not n.is_finite() or (n < 0 if nonnegative else n <= 0):
        raise MarketDataRefused("INVALID_DECIMAL")
    return n


def _datetime(value: object) -> datetime:
    if type(value) is not str or len(value) > 48:
        raise MarketDataRefused("ISO_DATETIME_REQUIRED")
    try:
        return _utc(datetime.fromisoformat(value))
    except (ValueError, TypeError) as exc:
        raise MarketDataRefused("INVALID_PROVIDER_TIMESTAMP") from exc


def _mapping(raw: Mapping[str, object], keys: frozenset[str]) -> None:
    if not isinstance(raw, Mapping) or set(raw) != keys:
        raise MarketDataRefused("EXACT_FIXTURE_SCHEMA_REQUIRED")


def normalize_crypto_bar(feed: FeedDefinition, raw: Mapping[str, object]) -> ClosedCandle:
    """Normalize a host-supplied crypto OHLCV fixture (NOT a network request)."""
    if (feed.instrument.market is not Market.CRYPTO or
            feed.event is not CoreEventType.CLOSED_CANDLE or
            feed.volume_semantics is not VolumeSemantics.TRADED or
            feed.price_basis is not PriceBasis.TRADE):
        raise MarketDataRefused("CRYPTO_FEED_CONTRACT_MISMATCH")
    _mapping(raw, frozenset({"open_at", "close_at", "open", "high", "low", "close", "volume"}))
    return ClosedCandle(_datetime(raw["open_at"]), _datetime(raw["close_at"]),
                        _decimal(raw["open"]), _decimal(raw["high"]),
                        _decimal(raw["low"]), _decimal(raw["close"]),
                        _decimal(raw["volume"], nonnegative=True))


def normalize_forex_bar(feed: FeedDefinition, raw: Mapping[str, object]) -> ClosedCandle:
    """Normalize broker bid OHLC bars; 'tick_volume' is NOT traded volume."""
    if (feed.instrument.market is not Market.FOREX or
            feed.event is not CoreEventType.CLOSED_CANDLE or
            feed.volume_semantics is not VolumeSemantics.TICK_COUNT or
            feed.price_basis is not PriceBasis.BID):
        raise MarketDataRefused("FOREX_FEED_CONTRACT_MISMATCH")
    _mapping(raw, frozenset({"open_at", "close_at", "open", "high", "low", "close", "tick_volume"}))
    count = raw["tick_volume"]
    if type(count) is not int or count < 0:
        raise MarketDataRefused("FOREX_TICK_COUNT_REQUIRED")
    return ClosedCandle(_datetime(raw["open_at"]), _datetime(raw["close_at"]),
                        _decimal(raw["open"]), _decimal(raw["high"]),
                        _decimal(raw["low"]), _decimal(raw["close"]), Decimal(count))


def normalize_bidask_tick(feed: FeedDefinition, raw: Mapping[str, object]) -> BidAskTick:
    """Normalize inert quote payload from an explicitly configured feed."""
    if feed.event is not CoreEventType.QUOTE_TICK:
        raise MarketDataRefused("TICK_FEED_CONTRACT_MISMATCH")
    _mapping(raw, frozenset({"occurred_at", "bid", "ask"}))
    return BidAskTick(_datetime(raw["occurred_at"]),
                      _decimal(raw["bid"]), _decimal(raw["ask"]))
