"""Canonical immutable candle and snapshot contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import hashlib
import json
from typing import Iterable

from app.modules.market_data.errors import (
    InsufficientClosedCandlesError,
    MarketDataStaleError,
)

TIMEFRAME_SECONDS = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "12h": 43200,
    "1d": 86400,
    "1w": 604800,
}


@dataclass(frozen=True, slots=True)
class Candle:
    open_time: datetime
    close_time: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def __post_init__(self) -> None:
        if self.open_time.tzinfo is None or self.close_time.tzinfo is None:
            raise ValueError("candle timestamps must be timezone-aware")
        if self.close_time <= self.open_time:
            raise ValueError("close_time must be greater than open_time")
        if self.low > self.high:
            raise ValueError("low cannot exceed high")
        if not self.low <= self.open <= self.high:
            raise ValueError("open must be inside candle range")
        if not self.low <= self.close <= self.high:
            raise ValueError("close must be inside candle range")
        if self.volume < 0:
            raise ValueError("volume cannot be negative")


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    exchange: str
    market_type: str
    symbol: str
    timeframe: str
    candles: tuple[Candle, ...]
    captured_at: datetime
    source: str = "REST"

    def __post_init__(self) -> None:
        if self.timeframe not in TIMEFRAME_SECONDS:
            raise ValueError("unsupported canonical timeframe")
        if self.captured_at.tzinfo is None:
            raise ValueError("captured_at must be timezone-aware")
        if not self.candles:
            raise InsufficientClosedCandlesError("snapshot needs closed candles")
        previous = None
        for candle in self.candles:
            if candle.close_time > self.captured_at:
                raise ValueError("snapshot contains future/unclosed candle")
            if previous is not None and candle.open_time <= previous.open_time:
                raise ValueError("candles must be strictly ordered and unique")
            previous = candle

    @property
    def snapshot_id(self) -> str:
        last_close_ms = int(self.candles[-1].close_time.timestamp() * 1000)
        return (
            f"{self.exchange}:{self.market_type}:{self.symbol}:"
            f"{self.timeframe}:{last_close_ms}"
        )

    @property
    def snapshot_hash(self) -> str:
        payload = {
            "exchange": self.exchange,
            "market_type": self.market_type,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "captured_at": self.captured_at.astimezone(UTC).isoformat(),
            "candles": [
                {
                    "open_time": c.open_time.astimezone(UTC).isoformat(),
                    "close_time": c.close_time.astimezone(UTC).isoformat(),
                    "open": str(c.open),
                    "high": str(c.high),
                    "low": str(c.low),
                    "close": str(c.close),
                    "volume": str(c.volume),
                }
                for c in self.candles
            ],
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(raw).hexdigest()

    def assert_fresh(self, *, now: datetime, max_age_intervals: int = 2) -> None:
        interval = timedelta(seconds=TIMEFRAME_SECONDS[self.timeframe])
        if now - self.candles[-1].close_time > interval * max_age_intervals:
            raise MarketDataStaleError(
                f"{self.symbol} {self.timeframe} snapshot is stale"
            )


def validate_candle_sequence(
    candles: Iterable[Candle],
    *,
    timeframe: str,
) -> tuple[Candle, ...]:
    items = tuple(candles)
    if timeframe not in TIMEFRAME_SECONDS:
        raise ValueError("unsupported canonical timeframe")
    if not items:
        raise InsufficientClosedCandlesError("no closed candles")
    expected = TIMEFRAME_SECONDS[timeframe]
    previous = None
    for candle in items:
        if previous is not None:
            delta = int((candle.open_time - previous.open_time).total_seconds())
            if delta != expected:
                raise ValueError("missing or misaligned candle detected")
        previous = candle
    return items
