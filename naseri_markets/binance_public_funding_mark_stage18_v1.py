"""Review a bounded official USD-M funding and mark-price archive pair.

The actual provider ZIP/CHECKSUM bytes are observed public transport data, not
an exchange digital signature or proof of what was published in 2024.
No trading, orderbook/fill simulation, paper activation or production.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import zipfile
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

_MONTH_START = datetime(2024, 1, 1, tzinfo=UTC)
_MONTH_END = datetime(2024, 2, 1, tzinfo=UTC)
_INTERVAL_MS = 900000
_DAY_MS = 86400000
_MONTH_START_MS = int(_MONTH_START.timestamp() * 1000)
_MARK_COUNT = 31 * 96
_FUNDING_COUNT = 31 * 3
_MAX_ZIP = 8 * 1024 * 1024
_MAX_CSV = 24 * 1024 * 1024
_ARCHIVE = {
    "funding": (
        "https://data.binance.vision/data/futures/um/monthly/fundingRate/BTCUSDT/"
        "BTCUSDT-fundingRate-2024-01.zip"
    ),
    "mark": (
        "https://data.binance.vision/data/futures/um/monthly/markPriceKlines/"
        "BTCUSDT/15m/BTCUSDT-15m-2024-01.zip"
    ),
}
_MARK_HEADER = (
    "open_time,open,high,low,close,volume,close_time,quote_volume,"
    "count,taker_buy_volume,taker_buy_quote_volume,ignore"
).split(",")
_FUND_HEADER = ["calc_time", "funding_interval_hours", "last_funding_rate"]


class Stage18MarketEvidenceRefused(ValueError):
    """Static refusal identifiers without reflecting untrusted CSV cells."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _decimal(raw: str, *, signed: bool = False) -> Decimal:
    if type(raw) is not str or not raw or len(raw) > 30 or "e" in raw.lower():
        raise Stage18MarketEvidenceRefused("ST18_UNSAFE_MARK_OR_FUNDING_DECIMAL")
    try:
        x = Decimal(raw)
    except InvalidOperation as exc:
        raise Stage18MarketEvidenceRefused("ST18_BAD_MARK_OR_FUNDING_NUMBER") from exc
    if not x.is_finite() or (abs(x) > Decimal("0.01") if signed else x <= 0):
        raise Stage18MarketEvidenceRefused("ST18_OUT_OF_BOUNDS_MARK_OR_FUNDING")
    return x


def _archive_csv(*, kind: str, zip_bytes: bytes, checksum_bytes: bytes) -> list[list[str]]:
    if type(kind) is not str or kind not in _ARCHIVE:
        raise Stage18MarketEvidenceRefused("ST18_UNKNOWN_SOURCE")
    if (type(zip_bytes) is not bytes or type(checksum_bytes) is not bytes
            or not 1 <= len(zip_bytes) <= _MAX_ZIP
            or not 1 <= len(checksum_bytes) <= 256):
        raise Stage18MarketEvidenceRefused("ST18_BOUNDED_BINARY_ARTIFACT_REQUIRED")
    filename = _ARCHIVE[kind].rsplit("/", 1)[-1]
    if checksum_bytes.strip(b"\r\n") != (_sha(zip_bytes) + "  " + filename).encode():
        raise Stage18MarketEvidenceRefused("ST18_SIBLING_CHECKSUM_REFUSED")
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as container:
            items = container.infolist()
            if (len(items) != 1 or items[0].filename != filename[:-4] + ".csv"
                    or not 1 <= items[0].file_size <= _MAX_CSV
                    or items[0].is_dir()):
                raise Stage18MarketEvidenceRefused("ST18_UNEXPECTED_ZIP_MEMBER")
            raw = container.read(items[0])
        if len(raw) > _MAX_CSV:
            raise Stage18MarketEvidenceRefused("ST18_UNCOMPRESSED_SIZE_LIMIT")
        rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"), newline=""), strict=True))
    except Stage18MarketEvidenceRefused:
        raise
    except (OSError, UnicodeError, csv.Error, zipfile.BadZipFile, ValueError) as exc:
        raise Stage18MarketEvidenceRefused("ST18_BAD_ORIGINAL_CSV_ARCHIVE") from exc
    expected_header = _MARK_HEADER if kind == "mark" else _FUND_HEADER
    if (not rows or rows[0] != expected_header
            or len(rows) != (1 + (_MARK_COUNT if kind == "mark" else _FUNDING_COUNT))
            or any(len(row) != len(expected_header) for row in rows)):
        raise Stage18MarketEvidenceRefused("ST18_MONTH_SCHEMA_OR_ROW_COUNT_DRIFT")
    return rows[1:]


def reconcile_stage18_primary_public_sources(
    *, funding_zip: bytes, funding_checksum: bytes,
    mark_zip: bytes, mark_checksum: bytes, operator_ack: bool = False,
) -> tuple[dict, bytes, bytes]:
    """Return source lineage plus Stage18's normalized event/schedule CSV pair.

    For the first funding at January 1 00:00, preceding mark-price candle
    lies in December and is NOT available. It is excluded and flagged.
    Each remaining mark is previous 15m candle close, only an approximation
    to the exact mark at funding settlement. Both normalized inventories
    share ONE provider source: no independent funding-time certification.
    """
    if (operator_ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        raise Stage18MarketEvidenceRefused("ST18_RESEARCH_ONLY_ACK_REQUIRED")
    funding_rows = _archive_csv(kind="funding", zip_bytes=funding_zip,
                                checksum_bytes=funding_checksum)
    mark_rows = _archive_csv(kind="mark", zip_bytes=mark_zip,
                             checksum_bytes=mark_checksum)
    closes = {}
    for i, row in enumerate(mark_rows):
        start_ms = _MONTH_START_MS + i * _INTERVAL_MS
        if (row[0] != str(start_ms)
                or row[6] != str(start_ms + _INTERVAL_MS - 1)):
            raise Stage18MarketEvidenceRefused("ST18_MARK_CANDLE_GRID_GAP")
        opening, high, low, close = (_decimal(row[j]) for j in (1, 2, 3, 4))
        if low > min(opening, close) or high < max(opening, close):
            raise Stage18MarketEvidenceRefused("ST18_MARK_PRICE_OHLC_INCONSISTENT")
        closes[start_ms + _INTERVAL_MS] = close
    schedule = ["funding_time_utc"]
    events = ["funding_time_utc,funding_rate,mark_price"]
    excluded = []
    for i, row in enumerate(funding_rows):
        at_ms = _MONTH_START_MS + i * 8 * 3600000
        if row[0] != str(at_ms) or row[1] != "8":
            raise Stage18MarketEvidenceRefused("ST18_FUNDING_INTERVAL_GAP_OR_POLICY_DRIFT")
        rate = _decimal(row[2], signed=True)
        if i == 0:
            excluded.append("2024-01-01T00:00:00Z:PRECEDING_MARK_CANDLE_NOT_IN_MONTH")
            continue
        mark = closes.get(at_ms)
        if mark is None:
            raise Stage18MarketEvidenceRefused("ST18_CANNOT_RECONCILE_MARK_TIME")
        stamp = datetime.fromtimestamp(at_ms / 1000, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        schedule.append(stamp)
        events.append(f"{stamp},{rate},{mark}")
    schedule_bytes = ("\n".join(schedule) + "\n").encode("ascii")
    event_bytes = ("\n".join(events) + "\n").encode("ascii")
    if len(schedule) != _FUNDING_COUNT or len(events) != _FUNDING_COUNT:
        raise Stage18MarketEvidenceRefused("ST18_INTERSECTION_COVERAGE_MISMATCH")
    report = {
        "stage": "STAGE18_PRIMARY_PUBLIC_FUNDING_MARK_RECONCILIATION_V1",
        "symbol": "BTCUSDT",
        "month": "2024-01",
        "market": "BINANCE_USDM",
        "funding_archive_url": _ARCHIVE["funding"],
        "funding_zip_sha256": _sha(funding_zip),
        "funding_checksum_sha256": _sha(funding_checksum),
        "mark_archive_url": _ARCHIVE["mark"],
        "mark_zip_sha256": _sha(mark_zip),
        "mark_checksum_sha256": _sha(mark_checksum),
        "observed_funding_events": _FUNDING_COUNT,
        "mark_candle_rows": _MARK_COUNT,
        "source_derived_reconciled_funding_events": _FUNDING_COUNT - 1,
        "excluded_boundary_funding_events": excluded,
        "normal_schedule_sha256": _sha(schedule_bytes),
        "normal_rate_mark_sha256": _sha(event_bytes),
        "historical_mark_at_exact_settlement_proven": False,
        "mark_price_is_prior_15m_candle_close_proxy": True,
        "independent_publisher_signature": False,
        "trusted_2024_pit_archive_revision_attested": False,
        "account_specific_fee_tier_verified": False,
        "historical_orderbook_and_slippage_verified": False,
        "full_tiered_liquidation_economics_verified": False,
        "genuine_brooks_filled_positions_booked": False,
        "oos_profitability_proven": False,
        "paper_trading_authorized": False,
        "live_trading_authorized": False,
    }
    report["receipt_sha256"] = _sha(json.dumps(
        report, sort_keys=True, separators=(",", ":")
    ).encode("ascii"))
    return report, schedule_bytes, event_bytes
