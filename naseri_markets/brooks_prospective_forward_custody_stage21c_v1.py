"""Stage21C/Brooks: frozen forward-plan and local, immutable-basis candle receipts.

Not a network client, clock authority, broker, actual PAPER pilot, blind OOS
certificate, or external witness. Local clock assertions and SHA256 hashes
cannot prove when the publisher originally created or served market data.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

from .brooks_replay import LEGACY_MANIFEST_SHA256

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_PLAN_KIND = "STAGE21C_BROOKS_PROSPECTIVE_PRECOMMIT_PROTOCOL_V1"
_CSV_FIELDS = ("open_at", "close_at", "open", "high", "low", "close", "volume")
_BAR = timedelta(minutes=15)
_MAX_READ = 160_000


class Stage21ForwardRefused(ValueError):
    """Content-independent refusal codes, never user-supplied data."""


def _gate(operator_ack: bool) -> None:
    if (operator_ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or "MMT_PRODUCTION" in os.environ):
        raise Stage21ForwardRefused("ST21C_RESEARCH_NONPRODUCTION_APPROVAL_REQUIRED")


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=True).encode("ascii")


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _timestamp(value: str) -> datetime:
    if (type(value) is not str or len(value) != 20
            or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00Z", value)):
        raise Stage21ForwardRefused("ST21C_CANONICAL_UTC_MINUTE_REQUIRED")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise Stage21ForwardRefused("ST21C_INVALID_UTC_DATE") from exc
    return parsed


def _utc(value: datetime) -> datetime:
    if (type(value) is not datetime or value.tzinfo is None
            or value.utcoffset() != timedelta(0)):
        raise Stage21ForwardRefused("ST21C_EXACT_AWARE_UTC_CLOCK_REQUIRED")
    return value.astimezone(UTC)


def _iso(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _decimal(value: str, *, price: bool) -> Decimal:
    if (type(value) is not str
            or not re.fullmatch(r"(?:0|[1-9]\d{0,17})(?:\.\d{1,12})?", value)):
        raise Stage21ForwardRefused("ST21C_CANONICAL_PRICE_REQUIRED")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise Stage21ForwardRefused("ST21C_BAD_PRICE") from exc
    if not result.is_finite() or result < 0 or (price and result == 0):
        raise Stage21ForwardRefused("ST21C_OUT_OF_BOUNDS_PRICE")
    return result


@dataclass(frozen=True, slots=True)
class BrooksProspectivePlan:
    """Exactly one BTCUSDT USDM 15m prospective data-capture protocol."""

    protocol: str
    strategy_manifest_sha256: str
    bridge_source_sha256: str
    economics_assumptions_sha256: str
    study_start_utc: str
    study_end_utc: str
    operator_created_utc: str
    symbol: str = "BTCUSDT"
    market: str = "binance_usdm"
    timeframe: str = "15m"
    warmup_closed_bars: int = 60
    max_forward_bars_per_receipt: int = 96
    funding_gap_policy: str = "REFUSE_MISSING_SCHEDULE"
    same_bar_stop_target_policy: str = "STOP_FIRST"
    paper_market_access: bool = False


def _validate_plan(plan: BrooksProspectivePlan) -> tuple[datetime, datetime, datetime]:
    if (type(plan) is not BrooksProspectivePlan or plan.protocol != _PLAN_KIND
            or plan.symbol != "BTCUSDT" or plan.market != "binance_usdm"
            or plan.timeframe != "15m"
            or type(plan.warmup_closed_bars) is not int
            or plan.warmup_closed_bars != 60
            or type(plan.max_forward_bars_per_receipt) is not int
            or plan.max_forward_bars_per_receipt != 96
            or plan.funding_gap_policy != "REFUSE_MISSING_SCHEDULE"
            or plan.same_bar_stop_target_policy != "STOP_FIRST"
            or plan.paper_market_access is not False):
        raise Stage21ForwardRefused("ST21C_FIXED_NO_LIVE_FORWARD_PROTOCOL_REQUIRED")
    for digest in (plan.strategy_manifest_sha256, plan.bridge_source_sha256,
                   plan.economics_assumptions_sha256):
        if type(digest) is not str or not _SHA.fullmatch(digest):
            raise Stage21ForwardRefused("ST21C_TRIPLE_PROVENANCE_SHA_REQUIRED")
    if plan.strategy_manifest_sha256 != LEGACY_MANIFEST_SHA256:
        raise Stage21ForwardRefused("ST21C_FROZEN_BROOKS_V5_SHA_REQUIRED")
    start, end, created = tuple(_timestamp(value) for value in (
        plan.study_start_utc, plan.study_end_utc, plan.operator_created_utc,
    ))
    if (start.minute % 15 or end.minute % 15
            or not timedelta(days=1) <= start - created
            or not timedelta(days=7) <= end - start <= timedelta(days=90)):
        raise Stage21ForwardRefused("ST21C_FUTURE_PRECOMMIT_WINDOW_NOT_VALID")
    return start, end, created


def freeze_brooks_prospective_plan(
    plan: BrooksProspectivePlan, *,
    operator_recorded_at_utc: datetime, operator_ack: bool = False,
) -> tuple[bytes, str]:
    """Make immutable-content plan; clock and precommitment are UNATTESTED."""
    _gate(operator_ack)
    _, _, created = _validate_plan(plan)
    now = _utc(operator_recorded_at_utc)
    if not timedelta(0) <= now - created <= timedelta(minutes=5):
        raise Stage21ForwardRefused("ST21C_OPERATOR_CLOCK_NOT_AT_REGISTRATION")
    raw = _canonical(asdict(plan))
    return raw, _hash(raw)


def _load_plan(
    plan_bytes: bytes, plan_sha256: str,
) -> tuple[BrooksProspectivePlan, datetime, datetime]:
    if (type(plan_bytes) is not bytes or not 1 <= len(plan_bytes) <= 4096
            or type(plan_sha256) is not str or not _SHA.fullmatch(plan_sha256)
            or _hash(plan_bytes) != plan_sha256):
        raise Stage21ForwardRefused("ST21C_FROZEN_PLAN_BYTES_OR_PIN_MISMATCH")
    try:
        obj = json.loads(plan_bytes, object_pairs_hook=_no_duplicates)
        plan = BrooksProspectivePlan(**obj)
    except Stage21ForwardRefused:
        raise
    except (TypeError, ValueError, UnicodeError, KeyError) as exc:
        raise Stage21ForwardRefused("ST21C_EXACT_FROZEN_PLAN_SCHEMA_REQUIRED") from exc
    if _canonical(asdict(plan)) != plan_bytes:
        raise Stage21ForwardRefused("ST21C_NONCANONICAL_FROZEN_PLAN_REFUSED")
    start, end, _ = _validate_plan(plan)
    return plan, start, end


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict:
    answer = {}
    for name, value in pairs:
        if name in answer:
            raise Stage21ForwardRefused("ST21C_DUPLICATE_JSON_FIELD")
        answer[name] = value
    return answer


def review_brooks_forward_candle_receipt(
    *, plan_bytes: bytes, plan_sha256: str,
    original_capture_csv_bytes: bytes, operator_recorded_at_utc: datetime,
    capture_origin: str, previous_receipt_bytes: bytes | None = None,
    operator_ack: bool = False,
) -> tuple[bytes, str]:
    """Offline chronological envelope. Does not run a strategy or make PnL.

    No trusted publisher clock, independent custody or server timestamp exists.
    Previous local receipt creates a tamper-evident HASH CHAIN, not a signature.
    """
    _gate(operator_ack)
    plan, start, end = _load_plan(plan_bytes, plan_sha256)
    if capture_origin not in (
        "OPERATOR_SUPPLIED_PUBLIC_SOURCE_UNVERIFIED",
        "SYNTHETIC_OFFLINE_TEST_ONLY",
    ):
        raise Stage21ForwardRefused("ST21C_EXPLICIT_UNVERIFIED_SOURCE_MODE_REQUIRED")
    now = _utc(operator_recorded_at_utc)
    if (type(original_capture_csv_bytes) is not bytes
            or not 1 <= len(original_capture_csv_bytes) <= _MAX_READ):
        raise Stage21ForwardRefused("ST21C_BOUNDED_CANDLE_EVIDENCE_REQUIRED")
    try:
        rows = list(csv.reader(
            io.StringIO(original_capture_csv_bytes.decode("ascii"), newline=""),
            strict=True,
        ))
    except (ValueError, csv.Error, UnicodeError) as exc:
        raise Stage21ForwardRefused("ST21C_INVALID_FORWARD_CSV") from exc
    if (not rows or tuple(rows[0]) != _CSV_FIELDS or
            not 1 <= len(rows) - 1 <= plan.max_forward_bars_per_receipt
            or any(len(row) != len(_CSV_FIELDS) for row in rows[1:])):
        raise Stage21ForwardRefused("ST21C_EXACT_CANDLE_SCHEMA_OR_ROWS_REQUIRED")
    previous_sha = plan_sha256
    expected_open = start
    seq = 1
    if previous_receipt_bytes is not None:
        if (type(previous_receipt_bytes) is not bytes
                or not 1 <= len(previous_receipt_bytes) <= 8192):
            raise Stage21ForwardRefused("ST21C_BOUNDED_PRIOR_RECEIPT_REQUIRED")
        try:
            prior = json.loads(previous_receipt_bytes, object_pairs_hook=_no_duplicates)
        except (ValueError, UnicodeError, TypeError) as exc:
            raise Stage21ForwardRefused("ST21C_INVALID_PRIOR_RECEIPT") from exc
        if (type(prior) is not dict or prior.get("protocol") != _PLAN_KIND
                or prior.get("plan_sha256") != plan_sha256
                or type(prior.get("sequence")) is not int
                or not 1 <= prior["sequence"] < 25000
                or prior.get("independent_timestamp_attested") is not False
                or prior.get("forward_paper_enabled") is not False
                or prior.get("receipt_sha256") != _hash(_canonical({
                    k: v for k, v in prior.items() if k != "receipt_sha256"
                }))):
            raise Stage21ForwardRefused("ST21C_PRIOR_CHAIN_OR_SCHEMA_REFUSED")
        expected_open = _timestamp(prior.get("last_close_utc"))
        if not start < expected_open < end:
            raise Stage21ForwardRefused("ST21C_PRIOR_RECEIPT_OUT_OF_PLAN")
        previous_sha = prior["receipt_sha256"]
        seq = prior["sequence"] + 1
    for row in rows[1:]:
        opened, closed = _timestamp(row[0]), _timestamp(row[1])
        if (opened != expected_open or closed - opened != _BAR
                or opened < start or closed > end):
            raise Stage21ForwardRefused("ST21C_FUTURE_SEQUENCE_GAP_OR_BOUNDS")
        opening, high, low, closing = tuple(
            _decimal(x, price=True) for x in row[2:6]
        )
        _decimal(row[6], price=False)
        if not low <= min(opening, closing) <= max(opening, closing) <= high:
            raise Stage21ForwardRefused("ST21C_OHLC_GEOMETRY_INVALID")
        expected_open = closed
    if now < expected_open + timedelta(seconds=5):
        raise Stage21ForwardRefused("ST21C_FUTURE_CANDLE_NOT_YET_CLOSED_AND_AVAILABLE")
    # Deliberately do NOT infer independent publisher custody from the times.
    receipt = {
        "protocol": _PLAN_KIND,
        "plan_sha256": plan_sha256,
        "sequence": seq,
        "previous_receipt_sha256": previous_sha,
        "source_claim": capture_origin,
        "original_capture_csv_sha256": _hash(original_capture_csv_bytes),
        "row_count": len(rows) - 1,
        "first_open_utc": rows[1][0],
        "last_close_utc": _iso(expected_open),
        "operator_observed_at_utc": now.isoformat(),
        "independent_timestamp_attested": False,
        "provider_signature_verified": False,
        "precommitment_witness_verified": False,
        "historical_data_revision_excluded": False,
        "strategy_worker_executed": False,
        "executed_trade_fills_verified": False,
        "walk_forward_profitability_backtest_performed": False,
        "verified_prospective_oos": False,
        "forward_paper_enabled": False,
        "live_trading_authorized": False,
        "production_modified": False,
        "status": "LOCAL_FORWARD_CANDLE_SEQUENCE_ONLY_EXTERNAL_WITNESS_MISSING",
    }
    receipt["receipt_sha256"] = _hash(_canonical(receipt))
    raw = _canonical(receipt)
    return raw, receipt["receipt_sha256"]


__all__ = [
    "Stage21ForwardRefused", "BrooksProspectivePlan",
    "freeze_brooks_prospective_plan", "review_brooks_forward_candle_receipt",
]
