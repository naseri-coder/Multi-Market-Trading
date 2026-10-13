"""DATA-A1: bounded, read-only CSV/Parquet historical market-data decoder.

Produces Stage-5 typed MarketPacket samples; NEVER runs a strategy, sends a
Telegram message, places an order or claims authenticated exchange history.
An immutable, owner-approved byte digest is required before any parsing.
"""
from __future__ import annotations

import csv
import hashlib
import os
import re
import stat
from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .core_api_v1 import (
    _TIMEFRAME_MINUTES,
    BidAskTick,
    ClosedCandle,
    CoreEventType,
    DataOrigin,
    _utc,
)
from .market_data_engine_v1 import (
    FeedDefinition,
    MarketPacket,
    PriceBasis,
    VolumeSemantics,
)


class HistoricalDataRefused(ValueError):
    """Fail closed: do not deliver unsafe, ambiguous or incomplete history."""


_SHA = re.compile(r"[0-9a-f]{64}\Z")
_CSV_LIMIT = 512 * 1024 * 1024
_PARQUET_LIMIT = 1024 * 1024 * 1024
_MAX_ROWS = 5_000_000
_PARQUET_GROUP_LIMIT = 64 * 1024 * 1024
_BATCH_SIZE = 4096
_BAR = ("open_at", "close_at", "open", "high", "low", "close")
_TICK = ("occurred_at", "bid", "ask")


@dataclass(frozen=True, slots=True)
class HistoricalFileSpec:
    """Operator-bound identity and byte digest. Not a provider attestation."""

    feed: FeedDefinition
    expected_sha256: str
    availability_lag_seconds: int = 0
    max_rows: int = _MAX_ROWS

    def __post_init__(self) -> None:
        if type(self.feed) is not FeedDefinition or self.feed.origin is not DataOrigin.REPLAY:
            raise HistoricalDataRefused("REPLAY_FEED_ONLY")
        if type(self.expected_sha256) is not str or not _SHA.fullmatch(self.expected_sha256):
            raise HistoricalDataRefused("PINNED_FILE_DIGEST_REQUIRED")
        if self.feed.source_ref != ("hist_" + self.expected_sha256[:40]):
            raise HistoricalDataRefused("SOURCE_REF_MUST_MATCH_FILE_DIGEST")
        if (type(self.availability_lag_seconds) is not int
                or not 0 <= self.availability_lag_seconds <= self.feed.max_latency_seconds):
            raise HistoricalDataRefused("INVALID_REPLAY_AVAILABILITY_LAG")
        if type(self.max_rows) is not int or not 1 <= self.max_rows <= _MAX_ROWS:
            raise HistoricalDataRefused("INVALID_MAX_ROWS")
        if (self.feed.event is CoreEventType.CLOSED_CANDLE
                and self.feed.volume_semantics is VolumeSemantics.UNKNOWN):
            raise HistoricalDataRefused("VOLUME_SEMANTICS_MUST_BE_EXPLICIT")


@dataclass(frozen=True, slots=True)
class HistoricalFileReport:
    format: str
    feed_id: str
    instrument: object
    timeframe: str
    source_ref: str
    sha256: str
    rows_validated: int
    first_observed_at: datetime
    last_observed_at: datetime
    origin: DataOrigin = DataOrigin.REPLAY
    provider_authenticated: bool = False
    exchange_session_calendar_verified: bool = False
    forward_ready: bool = False
    strategy_executed: bool = False
    telegram_sent: bool = False
    broker_order_sent: bool = False


def _fieldnames(feed: FeedDefinition) -> tuple[str, ...]:
    if feed.event is CoreEventType.QUOTE_TICK:
        if feed.price_basis is not PriceBasis.BID_ASK:
            raise HistoricalDataRefused("TICK_REQUIRES_BID_ASK_BASIS")
        return _TICK
    if feed.event is CoreEventType.CLOSED_CANDLE:
        if feed.price_basis is PriceBasis.BID_ASK:
            raise HistoricalDataRefused("CANDLE_REQUIRES_ONE_PRICE_BASIS")
        volume = ("tick_volume" if feed.volume_semantics is VolumeSemantics.TICK_COUNT
                  else "volume")
        return (*_BAR, volume)
    raise HistoricalDataRefused("UNSUPPORTED_EVENT_TYPE")


def _utc_timestamp(value: object) -> datetime:
    if type(value) is str and 0 < len(value) <= 64:
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HistoricalDataRefused("BAD_ISO8601_TIMESTAMP") from exc
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise HistoricalDataRefused("EXPLICIT_TIMEZONE_REQUIRED")
    try:
        return _utc(value)
    except (ValueError, TypeError) as exc:
        raise HistoricalDataRefused("BAD_TIMESTAMP") from exc


def _number(value: object, *, zero_allowed: bool = False,
            tick_count: bool = False) -> Decimal:
    if tick_count:
        if type(value) is int:
            if value < 0:
                raise HistoricalDataRefused("INVALID_TICK_COUNT")
            return Decimal(value)
        if type(value) is str and len(value) <= 32 and re.fullmatch(r"0|[1-9][0-9]*", value):
            return Decimal(value)
        raise HistoricalDataRefused("INVALID_TICK_COUNT")
    if type(value) not in (str, Decimal):
        raise HistoricalDataRefused("STRING_OR_DECIMAL_PRICE_REQUIRED")
    if len(str(value)) > 64:
        raise HistoricalDataRefused("NUMBER_TOO_LONG")
    try:
        num = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise HistoricalDataRefused("INVALID_NUMERIC_VALUE") from exc
    if not num.is_finite() or (num < 0 if zero_allowed else num <= 0):
        raise HistoricalDataRefused("INVALID_NUMERIC_VALUE")
    return num


def _packet(spec: HistoricalFileSpec, row: dict[str, object], sequence: int) -> MarketPacket:
    feed = spec.feed
    try:
        if feed.event is CoreEventType.CLOSED_CANDLE:
            start, end = _utc_timestamp(row["open_at"]), _utc_timestamp(row["close_at"])
            volume_key = ("tick_volume" if feed.volume_semantics is VolumeSemantics.TICK_COUNT
                          else "volume")
            candle = ClosedCandle(
                start, end, *(_number(row[k]) for k in ("open", "high", "low", "close")),
                _number(row[volume_key], zero_allowed=True,
                        tick_count=volume_key == "tick_volume"),
            )
            expected = timedelta(minutes=_TIMEFRAME_MINUTES[feed.timeframe])
            duration = end - start
            if ((feed.timeframe != "1d" and duration != expected)
                    or (feed.timeframe == "1d"
                        and not timedelta(hours=23) <= duration <= timedelta(hours=25))):
                raise HistoricalDataRefused("BAR_TIMEFRAME_MISMATCH")
            observed = end
            return MarketPacket(feed.feed_id, sequence,
                                observed + timedelta(seconds=spec.availability_lag_seconds),
                                feed.source_ref, candle=candle)
        observed = _utc_timestamp(row["occurred_at"])
        tick = BidAskTick(observed, _number(row["bid"]), _number(row["ask"]))
        return MarketPacket(feed.feed_id, sequence,
                            observed + timedelta(seconds=spec.availability_lag_seconds),
                            feed.source_ref, tick=tick)
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, HistoricalDataRefused):
            raise
        raise HistoricalDataRefused("INVALID_MARKET_SAMPLE") from exc


def _stat_file(path: Path, max_bytes: int) -> os.stat_result:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise HistoricalDataRefused("FILE_NOT_ACCESSIBLE") from exc
    if (not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size <= 0 or metadata.st_size > max_bytes):
        raise HistoricalDataRefused("INVALID_FILE_TYPE_OR_SIZE")
    return metadata


def _digest(path: Path, max_bytes: int) -> tuple[str, os.stat_result]:
    original = _stat_file(path, max_bytes)
    checksum = hashlib.sha256()
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as data:
            opened = os.fstat(data.fileno())
            if (not stat.S_ISREG(opened.st_mode) or opened.st_ino != original.st_ino
                    or opened.st_dev != original.st_dev or opened.st_size != original.st_size):
                raise HistoricalDataRefused("FILE_CHANGED_BEFORE_VALIDATION")
            count = 0
            while block := data.read(1024 * 1024):
                count += len(block)
                if count > max_bytes:
                    raise HistoricalDataRefused("FILE_SIZE_LIMIT_EXCEEDED")
                checksum.update(block)
            after = os.fstat(data.fileno())
            if (after.st_size != opened.st_size or after.st_mtime_ns != opened.st_mtime_ns
                    or count != opened.st_size):
                raise HistoricalDataRefused("FILE_CHANGED_DURING_HASH")
    except OSError as exc:
        raise HistoricalDataRefused("FILE_READ_FAILED") from exc
    return checksum.hexdigest(), original


def _validate_same_file(path: Path, previous: os.stat_result) -> None:
    now = _stat_file(path, _PARQUET_LIMIT)
    if (now.st_dev, now.st_ino, now.st_size, now.st_mtime_ns) != (
            previous.st_dev, previous.st_ino, previous.st_size, previous.st_mtime_ns):
        raise HistoricalDataRefused("FILE_CHANGED_SINCE_PREFLIGHT")


def _csv_rows(path: Path, expected: tuple[str, ...]) -> Iterator[dict[str, object]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream, restkey="__extra__", restval=None)
            if reader.fieldnames is None or tuple(reader.fieldnames) != expected:
                raise HistoricalDataRefused("CSV_EXACT_COLUMN_ORDER_REQUIRED")
            for raw in reader:
                if set(raw) != set(expected) or any(v is None for v in raw.values()):
                    raise HistoricalDataRefused("CSV_ROW_SHAPE_MISMATCH")
                yield raw
    except (csv.Error, UnicodeError, OSError) as exc:
        raise HistoricalDataRefused("CSV_DECODING_FAILED") from exc


def _parquet_rows(path: Path, expected: tuple[str, ...]) -> Iterator[dict[str, object]]:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise HistoricalDataRefused("PYARROW_RESEARCH_DEPENDENCY_REQUIRED") from exc
    try:
        with closing(pq.ParquetFile(path, memory_map=False)) as reader:
            schema = reader.schema_arrow
            if (tuple(schema.names) != expected or reader.metadata is None
                    or reader.metadata.num_columns != len(expected)
                    or reader.metadata.num_row_groups > 10_000):
                raise HistoricalDataRefused("PARQUET_EXACT_SCHEMA_REQUIRED")
            for field in schema:
                is_time = field.name in ("open_at", "close_at", "occurred_at")
                numeric = field.name not in ("open_at", "close_at", "occurred_at")
                supported = (pa.types.is_string(field.type)
                             or (is_time and pa.types.is_timestamp(field.type)
                                 and field.type.tz is not None)
                             or (numeric and (pa.types.is_decimal(field.type)
                                              or (field.name == "tick_volume"
                                                  and pa.types.is_integer(field.type)))))
                if not supported:
                    raise HistoricalDataRefused("PARQUET_UNSAFE_COLUMN_TYPE")
            for i in range(reader.metadata.num_row_groups):
                group = reader.metadata.row_group(i)
                if group.total_byte_size > _PARQUET_GROUP_LIMIT:
                    raise HistoricalDataRefused("PARQUET_ROW_GROUP_TOO_LARGE")
            for batch in reader.iter_batches(batch_size=_BATCH_SIZE, use_threads=False):
                for row in batch.to_pylist():
                    if any(value is None for value in row.values()):
                        raise HistoricalDataRefused("PARQUET_NULL_VALUE")
                    yield row
    except HistoricalDataRefused:
        raise
    except (OSError, ValueError, TypeError, RuntimeError) as exc:
        raise HistoricalDataRefused("PARQUET_DECODING_FAILED") from exc


def _samples(path: Path, spec: HistoricalFileSpec) -> Iterator[MarketPacket]:
    suffix = path.suffix.lower()
    columns = _fieldnames(spec.feed)
    rows = _csv_rows(path, columns) if suffix == ".csv" else _parquet_rows(path, columns)
    previous: MarketPacket | None = None
    count = 0
    for row in rows:
        count += 1
        if count > spec.max_rows:
            raise HistoricalDataRefused("ROW_LIMIT_EXCEEDED")
        packet = _packet(spec, row, count)
        if previous:
            if packet.observed_at <= previous.observed_at:
                raise HistoricalDataRefused("OUT_OF_ORDER_OR_DUPLICATE_TIME")
            if packet.candle and previous.candle and (
                    packet.candle.open_at != previous.candle.close_at):
                raise HistoricalDataRefused("UNVERIFIED_BAR_GAP_OR_OVERLAP")
        previous = packet
        yield packet
    if count == 0:
        raise HistoricalDataRefused("EMPTY_DATASET")


@dataclass(frozen=True, slots=True)
class ApprovedHistoricalReplay:
    """Validated in full before returning. The file must remain immutable."""

    path: Path
    spec: HistoricalFileSpec
    report: HistoricalFileReport
    _source_stat: os.stat_result

    def packets(self) -> Iterator[MarketPacket]:
        """Bounded-memory replay; cannot grant a live/production execution path.

        Revalidates the pinned byte digest before yielding; caller MUST keep
        the approved source immutable. A mutable file can still change during
        iteration; replay is not an atomic filesystem snapshot.
        """
        _validate_same_file(self.path, self._source_stat)
        digest, _ = _digest(self.path, _PARQUET_LIMIT if self.path.suffix.lower()
                            == ".parquet" else _CSV_LIMIT)
        if digest != self.report.sha256:
            raise HistoricalDataRefused("REPLAY_FILE_DIGEST_DRIFT")
        count = 0
        for packet in _samples(self.path, self.spec):
            count += 1
            yield packet
        _validate_same_file(self.path, self._source_stat)
        if count != self.report.rows_validated:
            raise HistoricalDataRefused("REPLAY_ROW_COUNT_DRIFT")


def validate_historical_file(
    path: Path, spec: HistoricalFileSpec,
) -> ApprovedHistoricalReplay:
    """Two-pass, full file validation before any MarketPacket is exposed."""
    if not isinstance(path, Path) or not isinstance(spec, HistoricalFileSpec):
        raise HistoricalDataRefused("EXPLICIT_PATH_AND_SPEC_REQUIRED")
    suffix = path.suffix.lower()
    if suffix not in (".csv", ".parquet"):
        raise HistoricalDataRefused("CSV_OR_PARQUET_ONLY")
    max_bytes = _PARQUET_LIMIT if suffix == ".parquet" else _CSV_LIMIT
    digest, initial_stat = _digest(path, max_bytes)
    if digest != spec.expected_sha256:
        raise HistoricalDataRefused("SOURCE_HASH_MISMATCH")
    first = last = None
    count = 0
    for packet in _samples(path, spec):
        if first is None:
            first = packet.observed_at
        last = packet.observed_at
        count += 1
    _validate_same_file(path, initial_stat)
    # A second digest closes the simple mutation-between-read-pass hole.
    repeated, _ = _digest(path, max_bytes)
    if repeated != digest:
        raise HistoricalDataRefused("SOURCE_CHANGED_DURING_VALIDATION")
    assert first is not None and last is not None
    report = HistoricalFileReport(
        suffix.lstrip("."), spec.feed.feed_id, spec.feed.instrument,
        spec.feed.timeframe, spec.feed.source_ref, digest, count, first, last,
    )
    return ApprovedHistoricalReplay(path, spec, report, initial_stat)


__all__ = [
    "ApprovedHistoricalReplay", "HistoricalDataRefused", "HistoricalFileReport",
    "HistoricalFileSpec", "validate_historical_file",
]
