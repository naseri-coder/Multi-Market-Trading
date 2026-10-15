"""Stage16: strict offline Binance Vision USD-M ZIP/CHECKSUM -> DATA-A1 inputs.

Zero network access, file writes, trading activity, strategy execution or
provider-authenticity attestation. Inputs are separately operator supplied.
"""
from __future__ import annotations

import calendar
import csv
import hashlib
import io
import re
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

_MAX_ZIP = 8 * 1024 * 1024
_MAX_UNCOMPRESSED = 24 * 1024 * 1024
_MAX_ROWS = 3_000
_BARS_PER_HOUR = 4
_BAR_MS = 900_000
_CHECKSUM = re.compile(rb"([0-9a-f]{64})  ([A-Za-z0-9._-]+\.zip)\n?\Z")
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_DEC = re.compile(r"(?:0|[1-9][0-9]{0,18})(?:\.[0-9]{1,18})?\Z")
_INT = re.compile(r"(?:0|[1-9][0-9]{0,18})\Z")
_HEADER = ("open_at", "close_at", "open", "high", "low", "close", "volume")


class VisionArchiveRefused(ValueError):
    """Only fixed error identifiers; never expose archive contents or paths."""


def _utc(value: datetime) -> datetime:
    if (type(value) is not datetime or value.tzinfo is None
            or value.utcoffset() != timedelta(0)):
        raise VisionArchiveRefused("ST16_EXPLICIT_UTC_CAPTURE_CLOCK_REQUIRED")
    return value.astimezone(UTC)


def _amount(raw: str, *, positive: bool = False) -> Decimal:
    if type(raw) is not str or not _DEC.fullmatch(raw):
        raise VisionArchiveRefused("ST16_NONCANONICAL_EXCHANGE_DECIMAL")
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise VisionArchiveRefused("ST16_INVALID_EXCHANGE_DECIMAL") from exc
    if not value.is_finite() or (value <= 0 if positive else value < 0):
        raise VisionArchiveRefused("ST16_INVALID_EXCHANGE_DECIMAL")
    return value


def _integer(raw: str) -> int:
    if type(raw) is not str or not _INT.fullmatch(raw):
        raise VisionArchiveRefused("ST16_INVALID_EXCHANGE_INTEGER")
    return int(raw)


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class VisionPreparedArchive:
    """Local conversion evidence; not independently authenticated provenance."""

    canonical_csv_bytes: bytes
    stage12_receipt_bytes: bytes
    zip_sha256: str
    checksum_sha256: str
    csv_sha256: str
    receipt_sha256: str
    count: int
    first_open_utc: str
    last_close_utc: str
    official_url_claim: str
    report_sha256: str
    independent_source_authenticated: bool = False
    exchange_archive_revision_excluded: bool = False
    independent_retrieval_clock_attested: bool = False
    market_contract_metadata_verified: bool = False
    historic_mark_and_funding_verified: bool = False
    economic_backtest_run: bool = False
    real_brooks_strategy_executed: bool = False
    trading_authorized: bool = False
    telegram_sent: bool = False
    status: str = "OFFLINE_VENUE_FORMAT_AND_SELF_CHECKSUM_PASS_UNATTESTED"


def prepare_vision_monthly_um_15m(
    zip_bytes: bytes, checksum_bytes: bytes, *,
    expected_zip_sha256: str,
    expected_checksum_sha256: str,
    year: int, month: int, retrieved_at_utc: datetime,
    operator_ack: bool = False,
) -> VisionPreparedArchive:
    """Validate complete UTC monthly BTCUSDT 15m *claimed* Binance Vision file.

    The CHECKSUM is downloaded/supplied separately but is NOT a signature.
    Caller must keep original source bytes and independently approve hashes.
    Nothing is downloaded, persisted or returned as live-ready market data.
    """
    import os

    if (operator_ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        raise VisionArchiveRefused("ST16_EXPLICIT_NONPRODUCTION_ACK_REQUIRED")
    if (type(year) is not int or not 2020 <= year <= 2030
            or type(month) is not int or not 1 <= month <= 12):
        raise VisionArchiveRefused("ST16_BOUNDED_MONTH_REQUIRED")
    stamp = _utc(retrieved_at_utc)
    month_start = datetime(year, month, 1, tzinfo=UTC)
    month_end = (datetime(year + 1, 1, 1, tzinfo=UTC) if month == 12
                 else datetime(year, month + 1, 1, tzinfo=UTC))
    if stamp <= month_end:
        raise VisionArchiveRefused("ST16_MONTH_NOT_CLOSED_AT_RECEIPT")
    if (type(zip_bytes) is not bytes or not 1 <= len(zip_bytes) <= _MAX_ZIP
            or type(checksum_bytes) is not bytes
            or not 1 <= len(checksum_bytes) <= 256):
        raise VisionArchiveRefused("ST16_BOUNDED_INPUT_BYTES_REQUIRED")
    for sha in (expected_zip_sha256, expected_checksum_sha256):
        if type(sha) is not str or not _SHA256.fullmatch(sha):
            raise VisionArchiveRefused("ST16_TWO_TRUSTED_SHA_PINS_REQUIRED")
    zip_sha = hashlib.sha256(zip_bytes).hexdigest()
    checksum_sha = hashlib.sha256(checksum_bytes).hexdigest()
    if zip_sha != expected_zip_sha256 or checksum_sha != expected_checksum_sha256:
        raise VisionArchiveRefused("ST16_ARCHIVE_OR_CHECKSUM_PIN_MISMATCH")
    archive_name = f"BTCUSDT-15m-{year:04d}-{month:02d}.zip"
    csv_name = archive_name[:-4] + ".csv"
    parsed = _CHECKSUM.fullmatch(checksum_bytes)
    if (parsed is None or parsed.group(2) != archive_name.encode("ascii")
            or parsed.group(1).decode("ascii") != zip_sha):
        raise VisionArchiveRefused("ST16_OFFICIAL_NAMED_CHECKSUM_MISMATCH")
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
            entries = archive.infolist()
            if len(entries) != 1:
                raise VisionArchiveRefused("ST16_EXACT_ONE_ARCHIVE_MEMBER_REQUIRED")
            entry = entries[0]
            if (entry.filename != csv_name or entry.is_dir()
                    or entry.flag_bits & 1 or entry.flag_bits & 8
                    or entry.compress_type not in (zipfile.ZIP_DEFLATED,
                                                    zipfile.ZIP_STORED)
                    or (entry.external_attr >> 16) & 0o170000 == 0o120000
                    or not 100 <= entry.file_size <= _MAX_UNCOMPRESSED
                    or entry.file_size > max(len(zip_bytes), 1) * 100):
                raise VisionArchiveRefused("ST16_UNSAFE_ARCHIVE_MEMBER")
            # Prevent repeated decompression and zip bombs before parsing.
            with archive.open(entry) as handle:
                raw = handle.read(_MAX_UNCOMPRESSED + 1)
            if len(raw) != entry.file_size:
                raise VisionArchiveRefused("ST16_ARCHIVE_DECOMPRESSION_SIZE_MISMATCH")
    except VisionArchiveRefused:
        raise
    except (zipfile.BadZipFile, RuntimeError, EOFError, OSError, ValueError,
            NotImplementedError, OverflowError) as exc:
        raise VisionArchiveRefused("ST16_ARCHIVE_CORRUPT_OR_UNSUPPORTED") from exc
    try:
        rows = list(csv.reader(io.StringIO(raw.decode("utf-8"), newline="")))
    except (UnicodeError, csv.Error, ValueError) as exc:
        raise VisionArchiveRefused("ST16_INVALID_ARCHIVE_CSV") from exc
    expected_count = calendar.monthrange(year, month)[1] * 24 * _BARS_PER_HOUR
    if (len(rows) not in (expected_count, expected_count + 1)
            or len(rows) > _MAX_ROWS + 1):
        raise VisionArchiveRefused("ST16_INCOMPLETE_MONTH_OR_EXTRA_ROWS")
    if len(rows) == expected_count + 1:
        # Some official futures bundles contain a standard 12-column header.
        if (len(rows[0]) != 12 or rows[0][0].strip().lower()
                not in ("open time", "open_time", "opentime")):
            raise VisionArchiveRefused("ST16_UNKNOWN_ARCHIVE_HEADER")
        rows = rows[1:]
    expected_open_ms = int(month_start.timestamp()) * 1000
    canonical = [",".join(_HEADER)]
    for row in rows:
        if len(row) != 12:
            raise VisionArchiveRefused("ST16_EXACT_12_KLINE_COLUMNS_REQUIRED")
        opened = _integer(row[0])
        closed = _integer(row[6])
        if (opened != expected_open_ms or opened % _BAR_MS
                or closed != opened + _BAR_MS - 1):
            raise VisionArchiveRefused("ST16_KLINE_GRID_OR_CLOSE_MS_MISMATCH")
        op, high, low, close = (_amount(x, positive=True) for x in row[1:5])
        volume = _amount(row[5])
        quote_volume = _amount(row[7])
        trades = _integer(row[8])
        buy_base = _amount(row[9])
        buy_quote = _amount(row[10])
        _amount(row[11])
        if (low > high or not low <= op <= high or not low <= close <= high
                or buy_base > volume or buy_quote > quote_volume
                or (volume == 0 and trades != 0)):
            raise VisionArchiveRefused("ST16_KLINE_ECONOMIC_OR_OHLC_INCONSISTENCY")
        opened_at = datetime.fromtimestamp(opened / 1000, tz=UTC)
        canonical.append(",".join((
            _iso(opened_at), _iso(opened_at + timedelta(minutes=15)),
            row[1], row[2], row[3], row[4], row[5],
        )))
        expected_open_ms += _BAR_MS
    if expected_open_ms != int(month_end.timestamp()) * 1000:
        raise VisionArchiveRefused("ST16_MONTH_TERMINATION_MISMATCH")
    content = ("\n".join(canonical) + "\n").encode("ascii")
    csv_sha = hashlib.sha256(content).hexdigest()
    receipt = {
        "schema_version": 1,
        "dataset_sha256": csv_sha,
        "feed_id": "stage16_binance_vision_um_btcusdt",
        "market": "crypto",
        "provider_claim": "binance_replay",
        "symbol": "BTCUSDT",
        "timezone": "UTC",
        "quote_currency": "USDT",
        "timeframe": "15m",
        "event": "closed_candle",
        "price_basis": "trade",
        "volume_semantics": "traded",
        "contract_kind": "linear_perpetual",
        "session_policy": "continuous_utc_operator_assertion",
        "capture_method": "operator_supplied_archive",
        "availability_lag_seconds": 5,
        "expected_rows": len(rows),
        "window_start_utc": _iso(month_start),
        "window_end_utc": _iso(month_end),
        "retrieved_at_utc": _iso(stamp),
    }
    receipt_bytes = json.dumps(receipt, separators=(",", ":"),
                               sort_keys=True).encode("ascii")
    receipt_sha = hashlib.sha256(receipt_bytes).hexdigest()
    source_url = (
        "https://data.binance.vision/data/futures/um/monthly/"
        f"klines/BTCUSDT/15m/{archive_name}"
    )
    evidence = {
        "source_url_claim": source_url, "zip_sha256": zip_sha,
        "checksum_sha256": checksum_sha, "canonical_csv_sha256": csv_sha,
        "receipt_sha256": receipt_sha, "count": len(rows),
        "operator_claimed_retrieval_time": _iso(stamp),
    }
    report_sha = hashlib.sha256(json.dumps(evidence, sort_keys=True,
                                           separators=(",", ":")).encode()).hexdigest()
    return VisionPreparedArchive(
        content, receipt_bytes, zip_sha, checksum_sha, csv_sha, receipt_sha,
        len(rows), _iso(month_start), _iso(month_end), source_url, report_sha,
    )


__all__ = ["VisionArchiveRefused", "VisionPreparedArchive",
           "prepare_vision_monthly_um_15m"]
