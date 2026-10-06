"""Read-only public Binance USD-M Futures data helpers for MARC research."""

from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx

from app.modules.market_data.entities import Candle, validate_candle_sequence

_BINANCE_FUTURES_BASE_URL = "https://fapi.binance.com"
_BINANCE_VISION_BASE_URL = "https://data.binance.vision"
_INTERVAL_MS = {
    "15m": 15 * 60 * 1000,
    "30m": 30 * 60 * 1000,
}


@dataclass(frozen=True, slots=True)
class BinanceVisionSeries:
    candles: tuple[Candle, ...]
    verified_archives: int
    archive_manifest_sha256: str
    gap_count: int
    segment_count: int


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
    now: datetime | None = None,
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

    closed_cutoff = min(end, _aware_utc(now or datetime.now(UTC)))
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
                if (
                    candle.open_time >= start
                    and candle.open_time < end
                    and candle.close_time <= closed_cutoff
                ):
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


def split_contiguous_candles(
    candles: tuple[Candle, ...],
    *,
    timeframe: str,
) -> tuple[tuple[Candle, ...], ...]:
    """Split ordered unique candles at every missing/misaligned interval."""
    if not candles:
        return ()
    expected = timedelta(milliseconds=_INTERVAL_MS[timeframe])
    segments: list[list[Candle]] = [[candles[0]]]
    for candle in candles[1:]:
        previous = segments[-1][-1]
        if candle.open_time - previous.open_time == expected:
            segments[-1].append(candle)
        else:
            segments.append([candle])
    return tuple(tuple(segment) for segment in segments)


def resample_15m_to_30m(candles: tuple[Candle, ...]) -> tuple[Candle, ...]:
    """Aggregate only complete UTC-aligned adjacent 15m pairs into 30m candles."""
    source = tuple(candles)
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
    return tuple(out)


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


def _epoch_ms(value: str | int) -> int:
    raw = int(value)
    if raw > 100_000_000_000_000:
        return raw // 1000
    return raw


def _archive_row_to_candle(row: list[str]) -> Candle:
    if len(row) < 7:
        raise ValueError("malformed Binance Vision kline row")
    return Candle(
        open_time=_from_ms(_epoch_ms(row[0])),
        close_time=_from_ms(_epoch_ms(row[6])),
        open=Decimal(row[1]),
        high=Decimal(row[2]),
        low=Decimal(row[3]),
        close=Decimal(row[4]),
        volume=Decimal(row[5]),
    )


def _month_starts(start: datetime, end: datetime) -> tuple[datetime, ...]:
    month = datetime(start.year, start.month, 1, tzinfo=UTC)
    values = []
    while month < end:
        values.append(month)
        if month.month == 12:
            month = datetime(month.year + 1, 1, 1, tzinfo=UTC)
        else:
            month = datetime(month.year, month.month + 1, 1, tzinfo=UTC)
    return tuple(values)


async def _download_bytes(
    client: httpx.AsyncClient,
    url: str,
) -> bytes:
    for attempt in range(6):
        response = await client.get(url)
        if response.status_code in {418, 429} or response.status_code >= 500:
            if attempt == 5:
                response.raise_for_status()
            retry_after = float(response.headers.get("Retry-After", "1"))
            await asyncio.sleep(max(1.0, retry_after) * (attempt + 1))
            continue
        response.raise_for_status()
        return response.content
    raise RuntimeError("unreachable Binance Vision retry state")


async def fetch_binance_vision_monthly_klines(
    *,
    symbol: str,
    start: datetime,
    end: datetime,
    timeframe: str = "15m",
    request_delay_seconds: float = 0.10,
    base_url: str = _BINANCE_VISION_BASE_URL,
    now: datetime | None = None,
) -> BinanceVisionSeries:
    """Fetch and checksum-verify official monthly USD-M Futures kline archives."""
    if timeframe != "15m":
        raise ValueError("MARC archive source currently supports 15m source data only")
    start = _aware_utc(start)
    end = _aware_utc(end)
    if end <= start:
        raise ValueError("end must be after start")
    current = _aware_utc(now or datetime.now(UTC))
    current_month = datetime(current.year, current.month, 1, tzinfo=UTC)
    if end > current_month:
        raise ValueError(
            "Binance Vision monthly source requires end at or before current UTC month"
        )

    symbol = symbol.upper()
    by_open: dict[datetime, Candle] = {}
    verified: list[tuple[str, str]] = []
    timeout = httpx.Timeout(60.0)

    async with httpx.AsyncClient(
        timeout=timeout,
        headers={"User-Agent": "crypto-price-action-marc-backtest/0.1"},
        follow_redirects=True,
    ) as client:
        for month in _month_starts(start, end):
            stamp = month.strftime("%Y-%m")
            filename = f"{symbol}-{timeframe}-{stamp}.zip"
            prefix = (
                f"{base_url.rstrip('/')}/data/futures/um/monthly/klines/"
                f"{symbol}/{timeframe}/{filename}"
            )
            checksum_bytes = await _download_bytes(client, prefix + ".CHECKSUM")
            expected = checksum_bytes.decode("utf-8").strip().split()[0].lower()
            if len(expected) != 64 or any(ch not in "0123456789abcdef" for ch in expected):
                raise RuntimeError(f"invalid Binance Vision checksum for {filename}")

            archive = await _download_bytes(client, prefix)
            actual = hashlib.sha256(archive).hexdigest()
            if actual != expected:
                raise RuntimeError(f"Binance Vision checksum mismatch for {filename}")
            verified.append((filename, actual))

            with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
                members = [
                    name for name in zipped.namelist()
                    if not name.endswith("/") and name.lower().endswith(".csv")
                ]
                if len(members) != 1:
                    raise RuntimeError(f"unexpected Binance Vision archive layout: {filename}")
                with zipped.open(members[0]) as raw:
                    text = io.TextIOWrapper(raw, encoding="utf-8", newline="")
                    for row in csv.reader(text):
                        if not row:
                            continue
                        try:
                            int(row[0])
                        except ValueError:
                            continue
                        candle = _archive_row_to_candle(row)
                        if start <= candle.open_time < end:
                            by_open[candle.open_time] = candle

            if request_delay_seconds:
                await asyncio.sleep(request_delay_seconds)

    candles = tuple(by_open[key] for key in sorted(by_open))
    segments = split_contiguous_candles(candles, timeframe=timeframe)
    manifest = hashlib.sha256()
    for filename, digest in verified:
        manifest.update(f"{digest}  {filename}\n".encode())
    return BinanceVisionSeries(
        candles=candles,
        verified_archives=len(verified),
        archive_manifest_sha256=manifest.hexdigest(),
        gap_count=max(0, len(segments) - 1),
        segment_count=len(segments),
    )
