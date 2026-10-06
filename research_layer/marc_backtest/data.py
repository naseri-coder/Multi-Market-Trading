"""Read-only public Binance USD-M Futures data helpers for MARC research."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx

from app.modules.market_data.entities import Candle, validate_candle_sequence

_BINANCE_FUTURES_BASE_URL = "https://fapi.binance.com"
_INTERVAL_MS = {"15m": 15 * 60 * 1000}


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _from_ms(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1000, tz=UTC)


def _row_to_candle(row: list[object]) -> Candle:
    if len(row) < 7:
        raise ValueError("malformed Binance kline row")
    return Candle(
        open_time=_from_ms(int(row[0])),
        close_time=_from_ms(int(row[6])),
        open=Decimal(str(row[1])),
        high=Decimal(str(row[2])),
        low=Decimal(str(row[3])),
        close=Decimal(str(row[4])),
        volume=Decimal(str(row[5])),
    )


async def fetch_binance_futures_klines(
    *,
    symbol: str,
    start: datetime,
    end: datetime,
    timeframe: str = "15m",
    request_delay_seconds: float = 0.25,
    base_url: str = _BINANCE_FUTURES_BASE_URL,
    transport: httpx.AsyncBaseTransport | None = None,
) -> tuple[Candle, ...]:
    """Fetch immutable closed klines using the public USD-M Futures REST API."""
    if timeframe not in _INTERVAL_MS:
        raise ValueError("MARC research downloader currently supports 15m source data only")
    start = _aware_utc(start)
    end = _aware_utc(end)
    if end <= start:
        raise ValueError("end must be after start")
    if request_delay_seconds < 0:
        raise ValueError("request delay cannot be negative")

    interval_ms = _INTERVAL_MS[timeframe]
    cursor = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    by_open: dict[datetime, Candle] = {}

    timeout = httpx.Timeout(30.0)
    headers = {"User-Agent": "crypto-price-action-marc-backtest/0.1"}
    async with httpx.AsyncClient(
        base_url=base_url,
        timeout=timeout,
        headers=headers,
        follow_redirects=True,
        transport=transport,
    ) as client:
        while cursor < end_ms:
            payload = None
            for attempt in range(6):
                response = await client.get(
                    "/fapi/v1/klines",
                    params={
                        "symbol": symbol.upper(),
                        "interval": timeframe,
                        "startTime": cursor,
                        "endTime": end_ms - 1,
                        "limit": 1000,
                    },
                )
                if response.status_code in {418, 429}:
                    retry_after = float(response.headers.get("Retry-After", "1"))
                    await asyncio.sleep(max(retry_after, 1.0) * (attempt + 1))
                    continue
                response.raise_for_status()
                payload = response.json()
                break
            if payload is None:
                raise RuntimeError("Binance rate limit retry budget exhausted")
            if not isinstance(payload, list):
                raise RuntimeError("Binance kline response must be a list")
            if not payload:
                break

            rows = [row for row in payload if isinstance(row, list)]
            if not rows:
                break
            for row in rows:
                candle = _row_to_candle(row)
                if candle.open_time >= start and candle.open_time < end:
                    by_open[candle.open_time] = candle

            next_cursor = int(rows[-1][0]) + interval_ms
            if next_cursor <= cursor:
                raise RuntimeError("Binance historical pagination did not advance")
            cursor = next_cursor
            if len(rows) < 1000:
                break
            if request_delay_seconds:
                await asyncio.sleep(request_delay_seconds)

    ordered = tuple(by_open[key] for key in sorted(by_open))
    return validate_candle_sequence(ordered, timeframe=timeframe)


def resample_15m_to_30m(candles: tuple[Candle, ...]) -> tuple[Candle, ...]:
    """Aggregate complete UTC-aligned pairs of 15m candles into 30m candles."""
    source = validate_candle_sequence(candles, timeframe="15m")
    out: list[Candle] = []
    index = 0
    while index + 1 < len(source):
        first = source[index]
        if first.open_time.minute % 30 != 0 or first.open_time.second != 0:
            index += 1
            continue
        second = source[index + 1]
        if second.open_time - first.open_time != timedelta(minutes=15):
            index += 1
            continue
        out.append(
            Candle(
                open_time=first.open_time,
                close_time=second.close_time,
                open=first.open,
                high=max(first.high, second.high),
                low=min(first.low, second.low),
                close=second.close,
                volume=first.volume + second.volume,
            )
        )
        index += 2
    return validate_candle_sequence(tuple(out), timeframe="30m")


def candle_series_sha256(candles: tuple[Candle, ...]) -> str:
    """Hash normalized OHLCV rows for reproducible dataset provenance."""
    digest = hashlib.sha256()
    for candle in candles:
        row = ",".join(
            (
                candle.open_time.astimezone(UTC).isoformat(),
                candle.close_time.astimezone(UTC).isoformat(),
                str(candle.open),
                str(candle.high),
                str(candle.low),
                str(candle.close),
                str(candle.volume),
            )
        )
        digest.update(row.encode())
        digest.update(b"\n")
    return digest.hexdigest()
