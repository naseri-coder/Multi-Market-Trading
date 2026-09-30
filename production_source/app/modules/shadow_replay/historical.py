"""Read-only public REST historical candle sources.

These adapters intentionally do not call MarketSnapshot.assert_fresh(): historical
data is expected to be stale. They only return fully closed, ordered candles.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx

from app.modules.market_data.binance import BINANCE_TIMEFRAMES
from app.modules.market_data.bybit import BYBIT_MARKET_TYPES, BYBIT_TIMEFRAMES
from app.modules.market_data.entities import (
    Candle,
    TIMEFRAME_SECONDS,
    validate_candle_sequence,
)
from app.modules.market_data.errors import (
    InsufficientClosedCandlesError,
    MarketDataResponseError,
    UnsupportedTimeframeError,
)
from app.modules.market_data.http import AsyncJsonHttpClient

_MAX_BATCH = 999


def _require_aware_end(end_at: datetime) -> datetime:
    if end_at.tzinfo is None:
        raise ValueError("end_at must be timezone-aware")
    return end_at.astimezone(UTC)


def _dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


class BinanceHistoricalCandleSource:
    exchange = "binance"

    def __init__(
        self,
        *,
        base_url: str = "https://api.binance.com",
        timeout_seconds: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.http = AsyncJsonHttpClient(
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            transport=transport,
        )

    async def get_closed_candles(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int,
        market_type: str,
        end_at: datetime,
    ) -> tuple[Candle, ...]:
        if market_type != "spot":
            raise ValueError("BinanceHistoricalCandleSource supports spot only")
        interval = BINANCE_TIMEFRAMES.get(timeframe)
        if interval is None:
            raise UnsupportedTimeframeError(timeframe)
        if limit < 2:
            raise ValueError("limit must be at least 2")

        end_at = _require_aware_end(end_at)
        cursor = end_at
        by_open: dict[datetime, Candle] = {}

        while len(by_open) < limit:
            request_limit = min(_MAX_BATCH, limit - len(by_open))
            try:
                payload = await self.http.get_json(
                    "/api/v3/klines",
                    params={
                        "symbol": symbol.upper(),
                        "interval": interval,
                        "limit": request_limit,
                        "endTime": int(cursor.timestamp() * 1000) - 1,
                    },
                )
            except (httpx.HTTPError, ValueError) as exc:
                raise MarketDataResponseError(
                    "Binance historical kline request failed"
                ) from exc

            if not isinstance(payload, list):
                raise MarketDataResponseError(
                    "Binance historical response must be a list"
                )
            if not payload:
                break

            batch: list[Candle] = []
            try:
                for row in payload:
                    if not isinstance(row, list) or len(row) < 7:
                        raise MarketDataResponseError(
                            "malformed Binance historical kline"
                        )
                    candle = Candle(
                        open_time=_dt(int(row[0])),
                        close_time=_dt(int(row[6])),
                        open=Decimal(str(row[1])),
                        high=Decimal(str(row[2])),
                        low=Decimal(str(row[3])),
                        close=Decimal(str(row[4])),
                        volume=Decimal(str(row[5])),
                    )
                    if candle.close_time <= end_at and candle.close_time <= cursor:
                        batch.append(candle)
                        by_open[candle.open_time] = candle
            except (ValueError, TypeError, ArithmeticError) as exc:
                raise MarketDataResponseError(
                    "unable to normalize Binance historical klines"
                ) from exc

            if not batch:
                break
            earliest = min(item.open_time for item in batch)
            if earliest >= cursor:
                raise MarketDataResponseError(
                    "Binance historical pagination did not move backward"
                )
            cursor = earliest

        if len(by_open) < limit:
            raise InsufficientClosedCandlesError(
                f"requested {limit}, received {len(by_open)} closed historical candles"
            )

        selected = tuple(sorted(by_open.values(), key=lambda c: c.open_time)[-limit:])
        return validate_candle_sequence(selected, timeframe=timeframe)

    async def aclose(self) -> None:
        await self.http.aclose()


class BybitHistoricalCandleSource:
    exchange = "bybit"

    def __init__(
        self,
        *,
        base_url: str = "https://api.bybit.com",
        timeout_seconds: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.http = AsyncJsonHttpClient(
            base_url=base_url,
            timeout_seconds=timeout_seconds,
            transport=transport,
        )

    async def get_closed_candles(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int,
        market_type: str,
        end_at: datetime,
    ) -> tuple[Candle, ...]:
        interval = BYBIT_TIMEFRAMES.get(timeframe)
        if interval is None:
            raise UnsupportedTimeframeError(timeframe)
        if market_type not in BYBIT_MARKET_TYPES:
            raise ValueError("market_type must be spot, linear, or inverse")
        if limit < 2:
            raise ValueError("limit must be at least 2")

        end_at = _require_aware_end(end_at)
        delta = timedelta(seconds=TIMEFRAME_SECONDS[timeframe])
        cursor = end_at
        by_open: dict[datetime, Candle] = {}

        while len(by_open) < limit:
            request_limit = min(_MAX_BATCH, limit - len(by_open))
            try:
                payload = await self.http.get_json(
                    "/v5/market/kline",
                    params={
                        "category": market_type,
                        "symbol": symbol.upper(),
                        "interval": interval,
                        "limit": request_limit,
                        "end": int(cursor.timestamp() * 1000) - 1,
                    },
                )
            except (httpx.HTTPError, ValueError) as exc:
                raise MarketDataResponseError(
                    "Bybit historical kline request failed"
                ) from exc

            if not isinstance(payload, dict) or payload.get("retCode") != 0:
                raise MarketDataResponseError(
                    "Bybit returned unsuccessful historical response"
                )
            result = payload.get("result")
            if not isinstance(result, dict) or not isinstance(result.get("list"), list):
                raise MarketDataResponseError(
                    "malformed Bybit historical kline result"
                )
            rows = result["list"]
            if not rows:
                break

            batch: list[Candle] = []
            try:
                for row in reversed(rows):
                    if not isinstance(row, list) or len(row) < 6:
                        raise MarketDataResponseError(
                            "malformed Bybit historical kline"
                        )
                    open_time = _dt(int(row[0]))
                    candle = Candle(
                        open_time=open_time,
                        close_time=open_time + delta,
                        open=Decimal(str(row[1])),
                        high=Decimal(str(row[2])),
                        low=Decimal(str(row[3])),
                        close=Decimal(str(row[4])),
                        volume=Decimal(str(row[5])),
                    )
                    if candle.close_time <= end_at and candle.close_time <= cursor:
                        batch.append(candle)
                        by_open[candle.open_time] = candle
            except (ValueError, TypeError, ArithmeticError) as exc:
                raise MarketDataResponseError(
                    "unable to normalize Bybit historical klines"
                ) from exc

            if not batch:
                break
            earliest = min(item.open_time for item in batch)
            if earliest >= cursor:
                raise MarketDataResponseError(
                    "Bybit historical pagination did not move backward"
                )
            cursor = earliest

        if len(by_open) < limit:
            raise InsufficientClosedCandlesError(
                f"requested {limit}, received {len(by_open)} closed historical candles"
            )

        selected = tuple(sorted(by_open.values(), key=lambda c: c.open_time)[-limit:])
        return validate_candle_sequence(selected, timeframe=timeframe)

    async def aclose(self) -> None:
        await self.http.aclose()
