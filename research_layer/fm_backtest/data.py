"""Checksum-verified Binance USD-M Futures data loader for FM research."""

from __future__ import annotations

import csv
import hashlib
import io
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Candle:
    open_time_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


BASE_URL = "https://data.binance.vision/data/futures/um/monthly/klines"


def _months(start: datetime, end: datetime) -> tuple[str, ...]:
    cursor = datetime(start.year, start.month, 1, tzinfo=UTC)
    values: list[str] = []
    while cursor < end:
        values.append(f"{cursor.year:04d}-{cursor.month:02d}")
        if cursor.month == 12:
            cursor = datetime(cursor.year + 1, 1, 1, tzinfo=UTC)
        else:
            cursor = datetime(cursor.year, cursor.month + 1, 1, tzinfo=UTC)
    return tuple(values)


def _url(symbol: str, interval: str, month: str) -> str:
    name = f"{symbol}-{interval}-{month}.zip"
    return f"{BASE_URL}/{symbol}/{interval}/{name}"


def _fetch(url: str, *, timeout: int = 45) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "FM-research-backtest/0.1"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def _exists(url: str) -> bool:
    try:
        _fetch(url + ".CHECKSUM", timeout=20)
        return True
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return False


def full_coverage(
    *,
    symbol: str,
    start: datetime,
    end: datetime,
    interval: str = "15m",
) -> bool:
    return all(_exists(_url(symbol, interval, month)) for month in _months(start, end))


def select_full_coverage_symbols(
    *,
    ranked_candidates: tuple[str, ...],
    start: datetime,
    end: datetime,
    count: int = 10,
) -> tuple[str, ...]:
    selected: list[str] = []
    for symbol in ranked_candidates:
        ok = full_coverage(symbol=symbol, start=start, end=end)
        print(f"FM_COVERAGE symbol={symbol} full_year={str(ok).lower()}", flush=True)
        if ok:
            selected.append(symbol)
        if len(selected) == count:
            break
    if len(selected) != count:
        raise RuntimeError(
            f"only {len(selected)} full-coverage symbols found; required {count}"
        )
    return tuple(selected)


def _timestamp_ms(raw: str) -> int:
    value = int(raw)
    # Binance Vision newer archives may use microseconds.
    if value > 10**14:
        return value // 1000
    return value


def _parse_zip(payload: bytes, expected_name: str) -> tuple[Candle, ...]:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = archive.namelist()
        if len(names) != 1:
            raise RuntimeError(f"unexpected archive members for {expected_name}: {names}")
        raw = archive.read(names[0]).decode("utf-8")
    reader = csv.reader(io.StringIO(raw))
    candles: list[Candle] = []
    for row in reader:
        if not row:
            continue
        try:
            open_time = _timestamp_ms(row[0])
        except ValueError:
            continue
        candles.append(
            Candle(
                open_time_ms=open_time,
                open=Decimal(row[1]),
                high=Decimal(row[2]),
                low=Decimal(row[3]),
                close=Decimal(row[4]),
                volume=Decimal(row[5]),
            )
        )
    return tuple(candles)


def load_15m_year(
    *,
    symbol: str,
    start: datetime,
    end: datetime,
) -> tuple[Candle, ...]:
    output: list[Candle] = []
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    for month in _months(start, end):
        url = _url(symbol, "15m", month)
        checksum_text = _fetch(url + ".CHECKSUM").decode("utf-8").strip()
        expected_sha = checksum_text.split()[0].lower()
        payload = _fetch(url)
        actual_sha = hashlib.sha256(payload).hexdigest()
        if actual_sha != expected_sha:
            raise RuntimeError(
                f"checksum mismatch {symbol} {month}: {actual_sha} != {expected_sha}"
            )
        parsed = _parse_zip(payload, url.rsplit("/", 1)[-1])
        output.extend(
            candle
            for candle in parsed
            if start_ms <= candle.open_time_ms < end_ms
        )
        print(
            f"FM_ARCHIVE_PASS symbol={symbol} month={month} "
            f"rows={len(parsed)} sha256={actual_sha[:12]}",
            flush=True,
        )
    output.sort(key=lambda candle: candle.open_time_ms)
    deduped: list[Candle] = []
    last_time: int | None = None
    for candle in output:
        if candle.open_time_ms == last_time:
            continue
        deduped.append(candle)
        last_time = candle.open_time_ms
    return tuple(deduped)


def resample_30m(candles: tuple[Candle, ...]) -> tuple[Candle, ...]:
    by_time = {candle.open_time_ms: candle for candle in candles}
    output: list[Candle] = []
    step = 30 * 60 * 1000
    half = 15 * 60 * 1000
    for first in candles:
        if first.open_time_ms % step != 0:
            continue
        second = by_time.get(first.open_time_ms + half)
        if second is None:
            continue
        output.append(
            Candle(
                open_time_ms=first.open_time_ms,
                open=first.open,
                high=max(first.high, second.high),
                low=min(first.low, second.low),
                close=second.close,
                volume=first.volume + second.volume,
            )
        )
    return tuple(output)
