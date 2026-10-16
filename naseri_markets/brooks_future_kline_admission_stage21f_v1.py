"""Stage21F: offline quarantine of original future Binance kline API response bytes.

This is a *gate*, not a collector, a broker, a verified price oracle, or a
forward PAPER runner. The RFC3161 proof authenticates the immutable plan only,
NOT the market response or operator-supplied reception time. Local integrity
cannot prove the HTTP endpoint, original TLS channel, or venue clock.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from datetime import timedelta
from decimal import Decimal

from .brooks_prospective_forward_custody_stage21c_v1 import (
    _gate,
    _iso,
    _load_plan,
    _timestamp,
    _utc,
    review_brooks_forward_candle_receipt,
)
from .brooks_rfc3161_precommitment_stage21d_v1 import (
    verify_brooks_rfc3161_precommitment,
)

_CANONICAL_PLAN_SHA = "c557e8792ff7f097ee483903e2e6702c622a20f3975af898ee9aca7e257ad94d"
_CANONICAL_TOKEN_SHA = "2e36862213d0f32cffadf161b3edae2610b03eef32f49e3b368253b49f83cf75"
_CANONICAL_CA_SHA = "2151b61137ffa86bf664691ba67e7da0b19f98c758e3d228d5d8ebf27e044438"
_CANONICAL_SIGNER_SHA = "8bfb0305bb64e2571ca507552ef3245cb1c2fee8728e0ff8689225081ea13467"
_API_ORIGIN = "https://fapi.binance.com"
_API_PATH = "/fapi/v1/klines"
_MAX_PAYLOAD = 131072
_VENUE_DECIMAL = re.compile(r"(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,12})?\Z")


class Stage21AdmissionRefused(ValueError):
    """Sanitized static refusal messages that never reveal untrusted values."""


def _hash(v: bytes) -> str:
    return hashlib.sha256(v).hexdigest()


def _canon(v: object) -> bytes:
    return json.dumps(
        v, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _strict_venue_decimal(value: object, *, positive: bool = False) -> Decimal:
    if type(value) is not str or not _VENUE_DECIMAL.fullmatch(value):
        raise Stage21AdmissionRefused("ST21F_NONCANONICAL_VENUE_NUMBER_REFUSED")
    parsed = Decimal(value)
    if positive and parsed <= 0:
        raise Stage21AdmissionRefused("ST21F_POSITIVE_VENUE_PRICE_REQUIRED")
    return parsed


def _strict_venue_integer(value: object) -> int:
    if type(value) is not int or not 0 <= value <= 9999999999999:
        raise Stage21AdmissionRefused("ST21F_INVALID_VENUE_INTEGER")
    return value


def _reject_nonfinite_constant(_value: str) -> None:
    raise Stage21AdmissionRefused("ST21F_NONFINITE_JSON_CONSTANT")


def _reject_duplicate_json_fields(fields: list[tuple[str, object]]) -> dict:
    output = {}
    for key, value in fields:
        if key in output:
            raise Stage21AdmissionRefused("ST21F_DUPLICATE_JSON_FIELDS")
        output[key] = value
    return output


def _rows(raw: bytes, *, start, expected: int) -> bytes:
    """Strict canonical Binance futures REST 12-column payload, no extra rows."""
    if type(raw) is not bytes or not 2 <= len(raw) <= _MAX_PAYLOAD:
        raise Stage21AdmissionRefused("ST21F_BOUNDED_ORIGINAL_PROVIDER_BYTES_REQUIRED")
    try:
        data = json.loads(
            raw.decode("ascii"), parse_constant=_reject_nonfinite_constant,
            object_pairs_hook=_reject_duplicate_json_fields,
        )
    except Stage21AdmissionRefused:
        raise
    except (ValueError, UnicodeError, TypeError) as exc:
        raise Stage21AdmissionRefused("ST21F_BAD_RAW_KLINE_JSON") from exc
    if (type(data) is not list or len(data) != expected
            or any(type(row) is not list or len(row) != 12 for row in data)):
        raise Stage21AdmissionRefused("ST21F_FIXED_TWELVE_COLUMN_KLINE_SHAPE")
    f = io.StringIO(newline="")
    csvwriter = csv.writer(f, lineterminator="\n")
    csvwriter.writerow(("open_at", "close_at", "open", "high", "low", "close", "volume"))
    for n, row in enumerate(data):
        open_ms = int((start + timedelta(minutes=15*n)).timestamp() * 1000)
        if (_strict_venue_integer(row[0]) != open_ms
                or _strict_venue_integer(row[6]) != open_ms + 900000 - 1):
            raise Stage21AdmissionRefused("ST21F_MISSING_DUPLICATED_OR_UNCLOSED_KLINE_GRID")
        opening, high, low, closing = (
            _strict_venue_decimal(row[j], positive=True) for j in (1, 2, 3, 4)
        )
        for j in (5, 7, 9, 10):
            _strict_venue_decimal(row[j])
        _strict_venue_integer(row[8])
        if row[11] != "0" or type(row[11]) is not str:
            raise Stage21AdmissionRefused("ST21F_RESERVED_VENUE_COLUMN_DRIFT")
        if not low <= min(opening, closing) <= max(opening, closing) <= high:
            raise Stage21AdmissionRefused("ST21F_INVALID_VENUE_OHLC_GEOMETRY")
        csvwriter.writerow((
            _iso(start + timedelta(minutes=15*n)),
            _iso(start + timedelta(minutes=15*(n+1))),
            row[1], row[2], row[3], row[4], row[5],
        ))
    return f.getvalue().encode("ascii")


def stage21f_admit_future_kline_batch_to_quarantine(
    *, exact_frozen_plan: bytes,
    original_tsr_der: bytes,
    original_ca_pem: bytes,
    original_tsa_signer_pem: bytes,
    original_provider_body_bytes: bytes,
    declared_request_url: str,
    declared_http_status: int,
    declared_tls_verified: bool,
    operator_received_at_utc,
    previous_stage21c_receipt_bytes: bytes | None = None,
    operator_ack: bool = False,
) -> tuple[dict, bytes]:
    """Actual signed precommitment + quarantined source snapshot.

    No source trust, no independent receiver clock, no exchange-filled
    positions, no trade PnL, no prospective OOS certification, no PAPER.
    """
    _gate(operator_ack)
    if type(exact_frozen_plan) is not bytes or _hash(exact_frozen_plan) != _CANONICAL_PLAN_SHA:
        raise Stage21AdmissionRefused("ST21F_ONLY_ORIGINAL_SIGNED_PLAN_ALLOWED")
    if (type(original_tsr_der) is not bytes or _hash(original_tsr_der) != _CANONICAL_TOKEN_SHA
            or type(original_ca_pem) is not bytes
            or _hash(original_ca_pem) != _CANONICAL_CA_SHA
            or type(original_tsa_signer_pem) is not bytes
            or _hash(original_tsa_signer_pem) != _CANONICAL_SIGNER_SHA):
        raise Stage21AdmissionRefused("ST21F_PINNED_EXTERNAL_WITNESS_BYTES_REQUIRED")
    if (type(declared_request_url) is not str
            or not declared_request_url.startswith(_API_ORIGIN + _API_PATH + "?")
            or type(declared_http_status) is not int or declared_http_status != 200
            or declared_tls_verified is not True):
        raise Stage21AdmissionRefused("ST21F_EXACT_CLAIMED_HTTPS_SOURCE_REQUIRED")
    plan, start, end = _load_plan(exact_frozen_plan, _CANONICAL_PLAN_SHA)
    received = _utc(operator_received_at_utc)
    if received < start + timedelta(minutes=15, seconds=5) or received > end + timedelta(days=2):
        raise Stage21AdmissionRefused("ST21F_CAPTURE_OUTSIDE_SIGNED_STUDY_WINDOW")
    if previous_stage21c_receipt_bytes is None:
        opened = start
    else:
        try:
            prev = json.loads(previous_stage21c_receipt_bytes)
            opened = _timestamp(prev["last_close_utc"])
        except (ValueError, KeyError, TypeError) as exc:
            raise Stage21AdmissionRefused("ST21F_INVALID_PRIOR_CUSTODY_RECEIPT") from exc
    if not start <= opened < end:
        raise Stage21AdmissionRefused("ST21F_CANDLE_START_OUTSIDE_SIGNED_WINDOW")
    try:
        parsed = json.loads(original_provider_body_bytes)
    except (ValueError, UnicodeError, TypeError) as exc:
        raise Stage21AdmissionRefused("ST21F_INVALID_PROVIDER_RESPONSE") from exc
    if type(parsed) is not list or not 1 <= len(parsed) <= 96:
        raise Stage21AdmissionRefused("ST21F_MAX_96_FULL_CLOSED_BARS_PER_CAPTURE")
    count = len(parsed)
    required_query = (
        f"{_API_ORIGIN}{_API_PATH}?interval=15m&limit={count}"
        f"&startTime={int(opened.timestamp()*1000)}&symbol=BTCUSDT"
    )
    if declared_request_url != required_query:
        raise Stage21AdmissionRefused("ST21F_SOURCE_URL_WINDOW_OR_QUERY_DRIFT")
    normalized = _rows(original_provider_body_bytes, start=opened, expected=count)
    try:
        witness = verify_brooks_rfc3161_precommitment(
            plan_bytes=exact_frozen_plan,
            plan_sha256=_CANONICAL_PLAN_SHA,
            timestamp_response_der=original_tsr_der,
            timestamp_response_sha256=_CANONICAL_TOKEN_SHA,
            trusted_ca_pem=original_ca_pem,
            trusted_ca_sha256=_CANONICAL_CA_SHA,
            tsa_signer_certificate_pem=original_tsa_signer_pem,
            tsa_signer_certificate_sha256=_CANONICAL_SIGNER_SHA,
            operator_ack=True,
        )
        chained, chain_sha = review_brooks_forward_candle_receipt(
            plan_bytes=exact_frozen_plan,
            plan_sha256=_CANONICAL_PLAN_SHA,
            original_capture_csv_bytes=normalized,
            operator_recorded_at_utc=received,
            capture_origin="OPERATOR_SUPPLIED_PUBLIC_SOURCE_UNVERIFIED",
            previous_receipt_bytes=previous_stage21c_receipt_bytes,
            operator_ack=True,
        )
    except ValueError as exc:
        raise Stage21AdmissionRefused("ST21F_SIGNED_PLAN_OR_CONTINUOUS_CUSTODY_REFUSED") from exc
    if (witness.get("cryptographic_tsa_signature_and_imprint_valid") is not True
            or witness.get("independent_tsa_provider_assessed") is not False
            or witness.get("paper_mode_authorized") is not False):
        raise Stage21AdmissionRefused("ST21F_TSA_RECEIPT_SCOPE_DRIFT")
    output = {
        "protocol": "STAGE21F_BROOKS_FUTURE_SOURCE_QUARANTINE_V1",
        "canonical_plan_sha256": _CANONICAL_PLAN_SHA,
        "original_external_tsa_response_sha256": _CANONICAL_TOKEN_SHA,
        "tsa_verified_signed_utc": witness["signed_timestamp_utc"],
        "declared_source_request_url": required_query,
        "declared_http_status": 200,
        "declared_https_verified_by_operator": True,
        "original_provider_response_bytes_sha256": _hash(original_provider_body_bytes),
        "normalized_closed_candle_csv_sha256": _hash(normalized),
        "source_origin_independently_attested": False,
        "network_transport_trace_independently_attested": False,
        "capture_time_independently_attested": False,
        "tsa_independence_policy_approved": False,
        "external_feed_signature_verified": False,
        "source_corrections_and_outage_inventory_complete": False,
        "stage21c_receipt_sha256": chain_sha,
        "stage21c_receipt": json.loads(chained),
        "candle_count": count,
        "market": plan.market, "symbol": plan.symbol,
        "signed_study_start_utc": plan.study_start_utc,
        "signed_study_end_utc": plan.study_end_utc,
        "actual_trades_filled": False,
        "oos_performance_verified": False,
        "connected_paper_enabled": False,
        "live_trading_authorized": False,
        "production_modified": False,
        "verdict": "LOCAL_QUARANTINE_ONLY_UNATTESTED_FUTURE_SOURCE",
    }
    output["receipt_sha256"] = _hash(_canon(output))
    return output, normalized


__all__ = ["Stage21AdmissionRefused", "stage21f_admit_future_kline_batch_to_quarantine"]
