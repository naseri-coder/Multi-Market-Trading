"""Stage-12 bounded Point-in-Time archive evidence for offline research.

Reuses DATA-A1 historical CSV/Parquet validation; cannot authenticate a venue
or retroactively prove what a provider had published at an earlier time.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .contracts import Market
from .core_api_v1 import CoreEventType, DataOrigin, _TIMEFRAME_MINUTES
from .historical_data_loader_a1 import (
    HistoricalDataRefused,
    HistoricalFileSpec,
    validate_historical_file,
)
from .market_data_engine_v1 import PriceBasis, VolumeSemantics

_RECEIPT_BYTES_MAX = 8192
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{1,79}\Z")
_UTC = re.compile(
    r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|\+00:00)\Z"
)
_RECEIPT_KEYS = frozenset({
    "schema_version", "dataset_sha256", "feed_id", "market",
    "provider_claim", "symbol", "timezone", "quote_currency",
    "timeframe", "event", "price_basis", "volume_semantics",
    "contract_kind", "session_policy", "capture_method",
    "availability_lag_seconds", "expected_rows",
    "window_start_utc", "window_end_utc", "retrieved_at_utc",
})


class HistoricalPitRefused(HistoricalDataRefused):
    """No untrusted input, raw data or archive path in the refusal code."""


def _duplicate_keys(items: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in items:
        if key in result:
            raise HistoricalPitRefused("PIT_DUPLICATE_RECEIPT_KEY")
        result[key] = value
    return result


def _nonfinite(_literal: str) -> None:
    raise HistoricalPitRefused("PIT_NONFINITE_RECEIPT_VALUE")


def _reject_float(_literal: str) -> None:
    raise HistoricalPitRefused("PIT_FLOAT_RECEIPT_VALUE")


def _parse_receipt(raw: bytes, trusted_digest: str) -> dict:
    if (type(trusted_digest) is not str or not _SHA.fullmatch(trusted_digest)
            or type(raw) is not bytes or not 1 <= len(raw) <= _RECEIPT_BYTES_MAX):
        raise HistoricalPitRefused("PIT_BOUND_RECEIPT_AND_PIN_REQUIRED")
    if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), trusted_digest):
        raise HistoricalPitRefused("PIT_RECEIPT_PIN_MISMATCH")
    try:
        obj = json.loads(
            raw, object_pairs_hook=_duplicate_keys,
            parse_constant=_nonfinite, parse_float=_reject_float,
        )
    except HistoricalPitRefused:
        raise
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise HistoricalPitRefused("PIT_INVALID_RECEIPT") from exc
    if (type(obj) is not dict or set(obj) != _RECEIPT_KEYS
            or type(obj["schema_version"]) is not int
            or obj["schema_version"] != 1):
        raise HistoricalPitRefused("PIT_EXACT_RECEIPT_SCHEMA_REQUIRED")
    return obj


def _stamp(value: object) -> datetime:
    if type(value) is not str or not _UTC.fullmatch(value):
        raise HistoricalPitRefused("PIT_CANONICAL_UTC_TIME_REQUIRED")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.utcoffset() != timedelta(0):
            raise ValueError
        return stamp.astimezone(UTC)
    except (ValueError, OverflowError) as exc:
        raise HistoricalPitRefused("PIT_CANONICAL_UTC_TIME_REQUIRED") from exc


def _asof(value: object) -> datetime:
    if (not isinstance(value, datetime) or value.tzinfo is None
            or value.utcoffset() != timedelta(0)):
        raise HistoricalPitRefused("PIT_EXPLICIT_UTC_ASOF_REQUIRED")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class HistoricalPitReport:
    """Locally consistent as-of selection, never independently attested truth."""

    dataset_sha256: str
    receipt_sha256: str
    evidence_sha256: str
    provider_claim: str
    symbol: str
    contract_kind_claim: str
    timeframe: str
    first_open_at: str
    last_close_at: str
    as_of_utc: str
    self_reported_retrieved_at_utc: str
    rows_validated: int
    zero_volume_rows: int
    duration_minutes: int
    max_claimed_availability_lag_seconds: int
    result: str = "OFFLINE_PIT_LOCAL_CAUSALITY_PASS_SOURCE_UNATTESTED"
    provider_authenticated: bool = False
    acquisition_clock_independently_attested: bool = False
    exchange_calendar_independently_verified: bool = False
    contract_economics_verified: bool = False
    historical_revisions_excluded: bool = False
    point_in_time_market_truth_certified: bool = False
    strategy_executed: bool = False
    backtest_run: bool = False
    profit_edge_proven: bool = False
    broker_orders_authorized: bool = False
    live_trading_authorized: bool = False
    telegram_sent: bool = False


def inspect_historical_pit_archive(
    path: Path,
    spec: HistoricalFileSpec,
    *,
    receipt_bytes: bytes,
    trusted_receipt_sha256: str,
    as_of_utc: datetime,
    operator_ack: bool = False,
) -> HistoricalPitReport:
    """Full-file archive gate; no file edits, strategy invocations or replay output.

    A caller-supplied receipt SHA256 is NOT an independent witness signature.
    For this initial contract, only contiguous UTC crypto trade-price candles
    are supported. Funding, MARK, bid/ask, contract sizing and FOREX sessions
    remain separately blocked until verified evidence is available.
    """
    if (operator_ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        raise HistoricalPitRefused("PIT_EXPLICIT_NONPRODUCTION_ACK_REQUIRED")
    if not isinstance(path, Path) or not path.is_absolute() or path.is_symlink():
        raise HistoricalPitRefused("PIT_ABSOLUTE_NON_SYMLINK_FILE_REQUIRED")
    if type(spec) is not HistoricalFileSpec:
        raise HistoricalPitRefused("PIT_EXISTING_DATA_A1_SPEC_REQUIRED")
    feed = spec.feed
    if (feed.instrument.market is not Market.CRYPTO
            or feed.event is not CoreEventType.CLOSED_CANDLE
            or feed.origin is not DataOrigin.REPLAY
            or feed.price_basis is not PriceBasis.TRADE
            or feed.volume_semantics is not VolumeSemantics.TRADED
            or feed.instrument.timezone != "UTC"
            or feed.timeframe not in _TIMEFRAME_MINUTES):
        raise HistoricalPitRefused("PIT_CONTIGUOUS_CRYPTO_TRADE_CANDLES_ONLY")
    asof = _asof(as_of_utc)
    receipt = _parse_receipt(receipt_bytes, trusted_receipt_sha256)
    identity = feed.instrument
    expected = {
        "dataset_sha256": spec.expected_sha256,
        "feed_id": feed.feed_id,
        "market": identity.market.value,
        "provider_claim": identity.provider,
        "symbol": identity.symbol,
        "timezone": identity.timezone,
        "quote_currency": identity.quote_currency,
        "timeframe": feed.timeframe,
        "event": feed.event.value,
        "price_basis": feed.price_basis.value,
        "volume_semantics": feed.volume_semantics.value,
        "availability_lag_seconds": spec.availability_lag_seconds,
    }
    for key, value in expected.items():
        if type(receipt[key]) is not type(value) or receipt[key] != value:
            raise HistoricalPitRefused("PIT_FILE_FEED_RECEIPT_IDENTITY_MISMATCH")
    for key in ("feed_id", "provider_claim", "symbol", "quote_currency"):
        if type(receipt[key]) is not str or not _ID.fullmatch(receipt[key]):
            raise HistoricalPitRefused("PIT_RECEIPT_IDENTITY_INVALID")
    if (receipt["session_policy"] != "continuous_utc_operator_assertion"
            or receipt["capture_method"] != "operator_supplied_archive"
            or type(receipt["contract_kind"]) is not str
            or receipt["contract_kind"] not in ("spot", "linear_perpetual")
            or type(receipt["expected_rows"]) is not int
            or not 2 <= receipt["expected_rows"] <= min(spec.max_rows, 100_000)):
        raise HistoricalPitRefused("PIT_UNVERIFIED_POLICY_OR_ROW_COUNT")
    window_start = _stamp(receipt["window_start_utc"])
    window_end = _stamp(receipt["window_end_utc"])
    retrieved_at = _stamp(receipt["retrieved_at_utc"])
    duration = timedelta(minutes=_TIMEFRAME_MINUTES[feed.timeframe])
    if (window_end <= window_start
            or (window_end - window_start) != receipt["expected_rows"] * duration
            or retrieved_at < window_end + timedelta(seconds=spec.availability_lag_seconds)
            or retrieved_at > asof
            or window_end > asof):
        raise HistoricalPitRefused("PIT_WINDOW_OR_ACQUISITION_CUTOFF_REFUSED")
    if (int(window_start.timestamp()) % int(duration.total_seconds()) != 0
            or int(window_end.timestamp()) % int(duration.total_seconds()) != 0):
        raise HistoricalPitRefused("PIT_UNALIGNED_CANDLE_WINDOW")

    approved = validate_historical_file(path, spec)
    if approved.report.rows_validated != receipt["expected_rows"]:
        raise HistoricalPitRefused("PIT_EXPECTED_SAMPLE_COUNT_MISMATCH")
    first_open = last_close = None
    zero_volume = count = 0
    for packet in approved.packets():
        if packet.candle is None:
            raise HistoricalPitRefused("PIT_CANDLE_REQUIRED")
        candle = packet.candle
        if first_open is None:
            first_open = candle.open_at
        last_close = candle.close_at
        if (packet.received_at > retrieved_at or packet.received_at > asof
                or candle.close_at > packet.received_at):
            raise HistoricalPitRefused("PIT_LOOKAHEAD_OR_UNAVAILABLE_CANDLE")
        if int(candle.open_at.timestamp()) % int(duration.total_seconds()) != 0:
            raise HistoricalPitRefused("PIT_UNALIGNED_CANDLE")
        zero_volume += int(candle.volume == 0)
        count += 1
    if (first_open != window_start or last_close != window_end
            or count != receipt["expected_rows"]):
        raise HistoricalPitRefused("PIT_WINDOW_DATASET_MISMATCH")
    source = hashlib.sha256(receipt_bytes).hexdigest()
    proof = {
        "stage": "STAGE12_LOCAL_PIT_QUALITY_V1",
        "receipt_sha256": source,
        "dataset_sha256": approved.report.sha256,
        "as_of_utc": asof.isoformat(),
        "first_open": first_open.isoformat(),
        "last_close": last_close.isoformat(),
        "rows": count, "zero_volume": zero_volume,
        "self_reported_retrieved_at": retrieved_at.isoformat(),
        "availability_lag_seconds": spec.availability_lag_seconds,
    }
    evidence_sha = hashlib.sha256(json.dumps(
        proof, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()
    return HistoricalPitReport(
        approved.report.sha256, source, evidence_sha, identity.provider,
        identity.symbol, receipt["contract_kind"], feed.timeframe,
        first_open.isoformat(), last_close.isoformat(), asof.isoformat(),
        retrieved_at.isoformat(), count, zero_volume,
        int((last_close - first_open).total_seconds() // 60),
        spec.availability_lag_seconds,
    )


__all__ = ["HistoricalPitRefused", "HistoricalPitReport", "inspect_historical_pit_archive"]
