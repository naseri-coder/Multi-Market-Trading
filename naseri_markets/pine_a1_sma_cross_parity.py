"""PINE-A1: a tiny *declarative* Pine SMA-cross subset and inert trace comparator.

NO Pine interpreter, TradingView connectivity, strategy execution or Worker.
Any syntax outside the exact closed-bar indicator template is rejected.
Offline parity against caller-provided CSV is NOT independent TV attestation.
"""
from __future__ import annotations

import csv
import hashlib
import io
import os
import re
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from .core_api_v1 import CoreEventType, DataOrigin
from .historical_data_loader_a1 import (
    HistoricalDataRefused,
    HistoricalFileSpec,
    validate_historical_file,
)
from .market_data_engine_v1 import PriceBasis

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_VERSION = re.compile(r"//@version=(5|6)\Z")
_TITLE = re.compile(r'indicator\("([A-Za-z][A-Za-z0-9 _.-]{0,47})", overlay=true\)\Z')
_FAST = re.compile(r"fast = ta\.sma\(close, ([1-9][0-9]{0,2})\)\Z")
_SLOW = re.compile(r"slow = ta\.sma\(close, ([1-9][0-9]{0,2})\)\Z")
_LONG = "longSignal = barstate.isconfirmed and ta.crossover(fast, slow)"
_SHORT = "shortSignal = barstate.isconfirmed and ta.crossunder(fast, slow)"
_GENESIS = b"\x00" * 32
_DOMAIN = b"MMT-PINE-A1-TRACE-REVIEW-V1\x00"
_MAX_SOURCE = 16 * 1024
_MAX_REFERENCE = 1024 * 1024
_MAX_BARS = 10_000
_SIGNALS = frozenset({"NONE", "LONG", "SHORT"})


class PineA1Refused(ValueError):
    """Fail closed without emitting strategy or market content."""


@dataclass(frozen=True, slots=True)
class PineSmaCrossRule:
    """Portable non-executable closed-bar rule IR, not general Pine support."""

    source_sha256: str
    pine_version: int
    indicator_title: str
    fast_length: int
    slow_length: int
    input_price: str = "close"
    on_bar: str = "barstate.isconfirmed"
    cross_up: str = "ta.crossover(fast,slow)"
    cross_down: str = "ta.crossunder(fast,slow)"
    portable_rule: str = "PINE_A1_CONFIRMED_CLOSED_BAR_SMA_CROSS_V1"
    executable: bool = False
    compiled: bool = False
    tradingview_equivalence_proven: bool = False
    worker_execution_authorized: bool = False


@dataclass(frozen=True, slots=True)
class PineTraceReview:
    source_sha256: str
    historical_sha256: str
    oracle_sha256: str
    symbol: str
    timeframe: str
    price_basis: str
    bars_compared: int
    warmup_bars: int
    long_signals: int
    short_signals: int
    mismatch_bars: int
    first_mismatch_at: datetime | None
    trace_sha256: str
    status: str
    offline_fixture_trace_matched: bool
    actual_tradingview_source_authenticated: bool = False
    actual_tradingview_trace_authenticated: bool = False
    true_pine_runtime_equivalence_proven: bool = False
    market_source_authenticated: bool = False
    point_in_time_proven: bool = False
    paper_strategy_executed: bool = False
    paper_order_sent: bool = False
    broker_order_sent: bool = False
    telegram_sent: bool = False
    worker_execution_authorized: bool = False
    quarantine_release_authorized: bool = False


def parse_pine_sma_cross(
    source: bytes, *, expected_sha256: str,
) -> PineSmaCrossRule:
    """Recognize ONLY six exact Pine v5/v6 indicator statements.

    Any strategy(), request.security, alert, orders, unconfirmed bar or
    unsupported Pine functionality fails by exact syntax rejection.
    """
    if (type(source) is not bytes or not 0 < len(source) <= _MAX_SOURCE
            or type(expected_sha256) is not str
            or _SHA.fullmatch(expected_sha256) is None):
        raise PineA1Refused("PINE_A1_BOUNDED_PINNED_SOURCE_REQUIRED")
    if hashlib.sha256(source).hexdigest() != expected_sha256:
        raise PineA1Refused("PINE_A1_SOURCE_SHA_MISMATCH")
    try:
        text = source.decode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise PineA1Refused("PINE_A1_UTF8_SOURCE_REQUIRED") from exc
    if "\x00" in text or "\ufeff" in text:
        raise PineA1Refused("PINE_A1_UNSAFE_SOURCE_ENCODING")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) != 6:
        raise PineA1Refused("PINE_A1_UNSUPPORTED_OR_AMBIGUOUS_SYNTAX")
    version = _VERSION.fullmatch(lines[0])
    title = _TITLE.fullmatch(lines[1])
    fast = _FAST.fullmatch(lines[2])
    slow = _SLOW.fullmatch(lines[3])
    if (version is None or title is None or fast is None or slow is None
            or lines[4] != _LONG or lines[5] != _SHORT):
        raise PineA1Refused("PINE_A1_UNSUPPORTED_OR_AMBIGUOUS_SYNTAX")
    f, s = int(fast.group(1)), int(slow.group(1))
    if not 2 <= f < s <= 200:
        raise PineA1Refused("PINE_A1_INVALID_SMA_WINDOW")
    return PineSmaCrossRule(
        source_sha256=expected_sha256, pine_version=int(version.group(1)),
        indicator_title=title.group(1), fast_length=f, slow_length=s,
    )


def _timestamp(raw: str) -> datetime:
    if type(raw) is not str or not 1 <= len(raw) <= 64:
        raise PineA1Refused("PINE_A1_ORACLE_TIME_INVALID")
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PineA1Refused("PINE_A1_ORACLE_TIME_INVALID") from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise PineA1Refused("PINE_A1_ORACLE_TIMEZONE_REQUIRED")
    return dt.astimezone(UTC)


def _oracle(raw: bytes, sha: str) -> tuple[tuple[datetime, str], ...]:
    if (type(raw) is not bytes or not 0 < len(raw) <= _MAX_REFERENCE
            or type(sha) is not str or _SHA.fullmatch(sha) is None):
        raise PineA1Refused("PINE_A1_PINNED_ORACLE_REQUIRED")
    if hashlib.sha256(raw).hexdigest() != sha:
        raise PineA1Refused("PINE_A1_ORACLE_SHA_MISMATCH")
    try:
        source = io.StringIO(raw.decode("utf-8", errors="strict"), newline="")
        reader = csv.DictReader(source, restkey="__extra__", restval=None)
        if reader.fieldnames != ["close_at", "signal"]:
            raise PineA1Refused("PINE_A1_EXACT_ORACLE_SCHEMA_REQUIRED")
        rows: list[tuple[datetime, str]] = []
        prior: datetime | None = None
        for record in reader:
            if (len(rows) >= _MAX_BARS or set(record) != {"close_at", "signal"}
                    or any(type(v) is not str for v in record.values())
                    or record["signal"] not in _SIGNALS):
                raise PineA1Refused("PINE_A1_ORACLE_ROW_INVALID")
            ts = _timestamp(record["close_at"])
            if prior is not None and ts <= prior:
                raise PineA1Refused("PINE_A1_ORACLE_OUT_OF_ORDER")
            rows.append((ts, record["signal"]))
            prior = ts
    except PineA1Refused:
        raise
    except (csv.Error, UnicodeError, ValueError) as exc:
        raise PineA1Refused("PINE_A1_ORACLE_ENCODING_OR_CSV_INVALID") from exc
    if not rows:
        raise PineA1Refused("PINE_A1_EMPTY_ORACLE")
    return tuple(rows)


def _cross_signal(
    closes: deque[Decimal], fast_length: int, slow_length: int,
) -> str:
    """Compare SMA *sums* without Decimal division/rounding artifacts.

    Equality on prior bar counts as crossover precondition; equality on
    current bar is never a crossover. Only confirmed closed candles are read.
    """
    if len(closes) <= slow_length:
        return "NONE"
    numbers = tuple(closes)
    fast_now = sum(numbers[-fast_length:])
    slow_now = sum(numbers[-slow_length:])
    fast_before = sum(numbers[-fast_length - 1:-1])
    slow_before = sum(numbers[-slow_length - 1:-1])
    a = fast_now * slow_length - slow_now * fast_length
    b = fast_before * slow_length - slow_before * fast_length
    if a > 0 and b <= 0:
        return "LONG"
    if a < 0 and b >= 0:
        return "SHORT"
    return "NONE"


def compare_pine_trace(
    path: Path, *, spec: HistoricalFileSpec, rule: PineSmaCrossRule,
    oracle_bytes: bytes, expected_oracle_sha256: str,
    operator_ack: bool = False,
) -> PineTraceReview:
    """Review typed DATA-A1 candles vs caller-supplied full-bar trace.

    Comparison alone never proves oracle was exported from TradingView.
    No trading/core evaluation is performed and no orders are emitted.
    """
    if (os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"
            or operator_ack is not True):
        raise PineA1Refused("PINE_A1_NONPRODUCTION_OPERATOR_ACK_REQUIRED")
    if (not isinstance(path, Path) or not path.is_absolute()
            or type(spec) is not HistoricalFileSpec
            or type(rule) is not PineSmaCrossRule
            or type(spec.max_rows) is not int
            or spec.max_rows > _MAX_BARS
            or spec.feed.event is not CoreEventType.CLOSED_CANDLE
            or spec.feed.origin is not DataOrigin.REPLAY
            or spec.feed.price_basis is PriceBasis.BID_ASK):
        raise PineA1Refused("PINE_A1_EXACT_CLOSED_BAR_FEED_REQUIRED")
    expected = _oracle(oracle_bytes, expected_oracle_sha256)
    try:
        approval = validate_historical_file(path, spec)
        if approval.report.rows_validated != len(expected):
            raise PineA1Refused("PINE_A1_SOURCE_ORACLE_LENGTH_MISMATCH")
        closes: deque[Decimal] = deque(maxlen=rule.slow_length + 1)
        n = long_count = short_count = mismatches = 0
        first_mismatch: datetime | None = None
        chain = _GENESIS
        for packet in approval.packets():
            candle = packet.candle
            if (candle is None or candle.close_at != packet.observed_at
                    or packet.observed_at > packet.received_at):
                raise PineA1Refused("PINE_A1_CAUSAL_CLOSED_BAR_REQUIRED")
            closes.append(candle.close)
            generated = _cross_signal(closes, rule.fast_length, rule.slow_length)
            oracle_time, oracle_signal = expected[n]
            if oracle_time != packet.observed_at:
                raise PineA1Refused("PINE_A1_SOURCE_ORACLE_TIMESTAMP_MISMATCH")
            long_count += int(generated == "LONG")
            short_count += int(generated == "SHORT")
            if generated != oracle_signal:
                mismatches += 1
                if first_mismatch is None:
                    first_mismatch = packet.observed_at
            chain = hashlib.sha256(
                _DOMAIN + chain + (n + 1).to_bytes(8, "big")
                + packet.observed_at.isoformat().encode("ascii") + b"\x00"
                + generated.encode("ascii") + b"\x00"
                + oracle_signal.encode("ascii"),
            ).digest()
            n += 1
        if n != len(expected):
            raise PineA1Refused("PINE_A1_SOURCE_ORACLE_LENGTH_MISMATCH")
    except HistoricalDataRefused as exc:
        raise PineA1Refused("PINE_A1_MARKET_DATA_PREVALIDATION_REFUSED") from exc
    return PineTraceReview(
        source_sha256=rule.source_sha256,
        historical_sha256=approval.report.sha256,
        oracle_sha256=expected_oracle_sha256,
        symbol=spec.feed.instrument.symbol, timeframe=spec.feed.timeframe,
        price_basis=spec.feed.price_basis.value,
        bars_compared=n, warmup_bars=min(n, rule.slow_length),
        long_signals=long_count, short_signals=short_count,
        mismatch_bars=mismatches, first_mismatch_at=first_mismatch,
        trace_sha256=chain.hex(),
        status=("PINE_A1_OFFLINE_TRACE_MATCH_NOT_TV_ATTESTED" if not mismatches
                else "PINE_A1_OFFLINE_TRACE_MISMATCH_NO_DEPLOY"),
        offline_fixture_trace_matched=mismatches == 0,
    )


__all__ = [
    "PineA1Refused", "PineSmaCrossRule", "PineTraceReview",
    "parse_pine_sma_cross", "compare_pine_trace",
]
