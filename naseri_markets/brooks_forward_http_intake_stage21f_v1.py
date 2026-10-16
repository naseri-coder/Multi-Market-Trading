"""Stage21F: offline, source-byte-preserving BTCUSDT prospective intake.

Requires EXACT externally timestamped Stage21E plan/token and pinned TSA
certificates, then normalizes operator-supplied Binance USD-M REST klines.
NEVER fetches market data or creates a network client, strategy task,
PAPER worker, broker order or operational journal.

HTTP Date and HTTPS URL are operator-asserted metadata, not trusted proofs
of provider identity or an independently witnessed capture timestamp.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from datetime import timedelta
from email.utils import parsedate_to_datetime

from .brooks_prospective_forward_custody_stage21c_v1 import (
    _gate,
    _hash,
    _load_plan,
    _utc,
    review_brooks_forward_candle_receipt,
)
from .brooks_rfc3161_precommitment_stage21d_v1 import (
    verify_brooks_rfc3161_precommitment,
)

_PLAN_SHA = "c557e8792ff7f097ee483903e2e6702c622a20f3975af898ee9aca7e257ad94d"
_STAMP_SHA = "2e36862213d0f32cffadf161b3edae2610b03eef32f49e3b368253b49f83cf75"
_CA_SHA = "2151b61137ffa86bf664691ba67e7da0b19f98c758e3d228d5d8ebf27e044438"
_SIGNER_SHA = "8bfb0305bb64e2571ca507552ef3245cb1c2fee8728e0ff8689225081ea13467"
_HEADER = "open_at,close_at,open,high,low,close,volume\n"
_NUMBER = re.compile(r"(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,12})?\Z")
_INT = re.compile(r"(?:0|[1-9][0-9]{0,17})\Z")
_STEP_MS = 900000


class Stage21IntakeRefused(ValueError):
    """Constant refusal codes; never echo original untrusted venue bytes."""


def _decimal(raw: object, *, positive: bool) -> None:
    if type(raw) is not str or not _NUMBER.fullmatch(raw):
        raise Stage21IntakeRefused("ST21F_NONCANONICAL_VENUE_NUMBER")
    if positive and not any(c in "123456789" for c in raw):
        raise Stage21IntakeRefused("ST21F_POSITIVE_PRICE_REQUIRED")


def _integer(value: object) -> int:
    if type(value) is not int or not 0 <= value <= 9999999999999:
        raise Stage21IntakeRefused("ST21F_EXACT_VENUE_INTEGER_REQUIRED")
    return value


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _reject_constant(_value: str):
    raise Stage21IntakeRefused("ST21F_NONFINITE_JSON_REFUSED")


def _reject_duplicate_keys(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise Stage21IntakeRefused("ST21F_DUPLICATE_JSON_KEYS")
        out[key] = value
    return out


def _original_data_to_canonical(raw: bytes) -> tuple[bytes, int, int]:
    if type(raw) is not bytes or not 10 <= len(raw) <= 160000:
        raise Stage21IntakeRefused("ST21F_BOUNDED_ORIGINAL_HTTP_BODY_REQUIRED")
    try:
        observed = json.loads(
            raw.decode("ascii"), parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except Stage21IntakeRefused:
        raise
    except (ValueError, UnicodeError, TypeError) as exc:
        raise Stage21IntakeRefused("ST21F_INVALID_ORIGINAL_KLINE_JSON") from exc
    if (type(observed) is not list or not 1 <= len(observed) <= 96
            or any(type(item) is not list or len(item) != 12 for item in observed)):
        raise Stage21IntakeRefused("ST21F_EXACT_12_COLUMN_KLINES_REQUIRED")
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(("open_at", "close_at", "open", "high", "low", "close", "volume"))
    first_ms = None
    last_exclusive_ms = None
    for row in observed:
        start = _integer(row[0])
        close_inclusive = _integer(row[6])
        if (close_inclusive != start + _STEP_MS - 1
                or start % _STEP_MS or (last_exclusive_ms is not None
                                       and start != last_exclusive_ms)):
            raise Stage21IntakeRefused("ST21F_15M_GRID_GAP_REVISION_OR_CLOSE_DRIFT")
        for idx in (1, 2, 3, 4):
            _decimal(row[idx], positive=True)
        for idx in (5, 7, 9, 10):
            _decimal(row[idx], positive=False)
        _integer(row[8])
        if type(row[11]) is not str or row[11] != "0":
            raise Stage21IntakeRefused("ST21F_RESERVED_EXCHANGE_COLUMN_DRIFT")
        opening, high, low, closing = (row[i] for i in (1, 2, 3, 4))
        from decimal import Decimal
        a, b, c, d = (Decimal(n) for n in (opening, high, low, closing))
        if not c <= min(a, d) <= max(a, d) <= b:
            raise Stage21IntakeRefused("ST21F_CANDLE_OHLC_INCONSISTENT")
        from datetime import UTC, datetime
        begin = datetime.fromtimestamp(start / 1000, tz=UTC)
        end = datetime.fromtimestamp((start + _STEP_MS) / 1000, tz=UTC)
        writer.writerow((
            begin.strftime("%Y-%m-%dT%H:%M:%SZ"),
            end.strftime("%Y-%m-%dT%H:%M:%SZ"),
            opening, high, low, closing, row[5],
        ))
        if first_ms is None:
            first_ms = start
        last_exclusive_ms = start + _STEP_MS
    data = output.getvalue().encode("ascii")
    if not data.startswith(_HEADER.encode()):
        raise Stage21IntakeRefused("ST21F_CANONICAL_CSV_HEADER_REFUSED")
    return data, first_ms, last_exclusive_ms


def _verified_external_plan(
    *, plan_bytes: bytes, plan_sha256: str,
    timestamp_response_der: bytes, timestamp_response_sha256: str,
    trusted_ca_pem: bytes, trusted_ca_sha256: str,
    tsa_signer_certificate_pem: bytes, tsa_signer_certificate_sha256: str,
) -> dict:
    """Cryptographically verify the exact *first* Stage21E notarized plan."""
    for supplied, required in (
        (plan_sha256, _PLAN_SHA),
        (timestamp_response_sha256, _STAMP_SHA),
        (trusted_ca_sha256, _CA_SHA),
        (tsa_signer_certificate_sha256, _SIGNER_SHA),
    ):
        if supplied != required:
            raise Stage21IntakeRefused("ST21F_ONLY_ORIGINAL_NOTARIZED_PLAN_ALLOWED")
    if type(plan_bytes) is not bytes or _hash(plan_bytes) != _PLAN_SHA:
        raise Stage21IntakeRefused("ST21F_ORIGINAL_FROZEN_PLAN_BYTES_MISMATCH")
    try:
        evidence = verify_brooks_rfc3161_precommitment(
            plan_bytes=plan_bytes, plan_sha256=plan_sha256,
            timestamp_response_der=timestamp_response_der,
            timestamp_response_sha256=timestamp_response_sha256,
            trusted_ca_pem=trusted_ca_pem,
            trusted_ca_sha256=trusted_ca_sha256,
            tsa_signer_certificate_pem=tsa_signer_certificate_pem,
            tsa_signer_certificate_sha256=tsa_signer_certificate_sha256,
            operator_ack=True,
        )
    except ValueError as exc:
        raise Stage21IntakeRefused("ST21F_EXTERNAL_SIGNATURE_REFUSED") from exc
    if (evidence.get("cryptographic_tsa_signature_and_imprint_valid") is not True
            or evidence.get("signer_chain_matched_operator_pinned_ca") is not True
            or evidence.get("plan_sha256") != _PLAN_SHA
            or evidence.get("signed_timestamp_utc") != "2026-10-16T01:36:00+00:00"
            or evidence.get("paper_mode_authorized") is not False):
        raise Stage21IntakeRefused("ST21F_EXACT_TIMESTAMP_EVIDENCE_MISMATCH")
    return evidence


def stage21f_admit_offline_binance_response(
    *, plan_bytes: bytes, plan_sha256: str,
    timestamp_response_der: bytes, timestamp_response_sha256: str,
    trusted_ca_pem: bytes, trusted_ca_sha256: str,
    tsa_signer_certificate_pem: bytes, tsa_signer_certificate_sha256: str,
    original_http_response_body: bytes,
    original_http_response_sha256: str,
    request_url: str, http_response_status: int, http_content_type: str,
    untrusted_http_date: str,
    operator_observed_at_utc,
    previous_stage21c_receipt_bytes: bytes | None = None,
    capture_claim: str = "OPERATOR_SUPPLIED_PUBLIC_SOURCE_UNVERIFIED",
    operator_ack: bool = False,
) -> tuple[dict, bytes, bytes]:
    """No I/O: original HTTP bytes -> 15m Stage21C receipt with scoped claims.

    This handles a *submitted* file, not the actual venue connection.
    A plain HTTP Date header, URL and claimed local observed time are
    alterable; the authentic TSA stamp only commits the plan, not price data.
    """
    _gate(operator_ack)
    proof = _verified_external_plan(
        plan_bytes=plan_bytes, plan_sha256=plan_sha256,
        timestamp_response_der=timestamp_response_der,
        timestamp_response_sha256=timestamp_response_sha256,
        trusted_ca_pem=trusted_ca_pem, trusted_ca_sha256=trusted_ca_sha256,
        tsa_signer_certificate_pem=tsa_signer_certificate_pem,
        tsa_signer_certificate_sha256=tsa_signer_certificate_sha256,
    )
    plan, start, end = _load_plan(plan_bytes, plan_sha256)
    if (capture_claim not in (
        "OPERATOR_SUPPLIED_PUBLIC_SOURCE_UNVERIFIED",
        "SYNTHETIC_OFFLINE_TEST_ONLY",
    ) or type(http_response_status) is not int or http_response_status != 200
            or http_content_type not in ("application/json", "application/json;charset=UTF-8")):
        raise Stage21IntakeRefused("ST21F_EXPLICIT_UNVERIFIED_PUBLIC_JSON_REQUIRED")
    now = _utc(operator_observed_at_utc)
    try:
        date = parsedate_to_datetime(untrusted_http_date)
    except (TypeError, ValueError, OverflowError) as exc:
        raise Stage21IntakeRefused("ST21F_INVALID_UNTRUSTED_HTTP_DATE") from exc
    if (date.tzinfo is None or not timedelta(0) <= now - date <= timedelta(minutes=5)):
        raise Stage21IntakeRefused("ST21F_HTTP_DATE_OPERATOR_TIME_DRIFT")
    if (type(original_http_response_sha256) is not str
            or _hash(original_http_response_body) != original_http_response_sha256):
        raise Stage21IntakeRefused("ST21F_EXACT_RESPONSE_BYTES_DIGEST_MISMATCH")
    csv_bytes, first_ms, last_ms = _original_data_to_canonical(original_http_response_body)
    expected_url = (
        "https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT"
        f"&interval=15m&startTime={first_ms}&limit={csv_bytes.count(bytes([10])) - 1}"
    )
    if type(request_url) is not str or request_url != expected_url:
        raise Stage21IntakeRefused("ST21F_EXACT_READONLY_REQUEST_URL_REQUIRED")
    from datetime import UTC, datetime
    beginning = datetime.fromtimestamp(first_ms / 1000, tz=UTC)
    last_end = datetime.fromtimestamp(last_ms / 1000, tz=UTC)
    if (beginning < start or last_end > end
            or not timedelta(seconds=5) <= now - last_end <= timedelta(minutes=10)):
        raise Stage21IntakeRefused("ST21F_NOT_FRESH_CLOSED_FUTURE_CANDLES")
    try:
        stage21c, receipt_sha = review_brooks_forward_candle_receipt(
            plan_bytes=plan_bytes, plan_sha256=plan_sha256,
            original_capture_csv_bytes=csv_bytes,
            operator_recorded_at_utc=now,
            capture_origin=capture_claim,
            previous_receipt_bytes=previous_stage21c_receipt_bytes,
            operator_ack=True,
        )
    except ValueError as exc:
        raise Stage21IntakeRefused("ST21F_STAGE21C_CHAIN_OR_REPLAY_REFUSED") from exc
    chain = json.loads(stage21c)
    result = {
        "protocol": "STAGE21F_FROZEN_PUBLIC_RESPONSE_INTAKE_V1",
        "status": "UNVERIFIED_OFFLINE_SOURCE_ENVELOPE_ONLY",
        "externally_timestamped_plan_sha256": _PLAN_SHA,
        "notarized_plan_signed_timestamp_utc": proof["signed_timestamp_utc"],
        "original_tsa_response_sha256": _STAMP_SHA,
        "operator_claimed_readonly_request_url": request_url,
        "operator_claimed_http_date": untrusted_http_date,
        "operator_observed_at_utc": now.isoformat(),
        "original_http_response_sha256": original_http_response_sha256,
        "canonical_15m_csv_sha256": _hash(csv_bytes),
        "stage21c_receipt_sha256": receipt_sha,
        "stage21c_sequence": chain["sequence"],
        "previous_stage21c_receipt_sha256": chain["previous_receipt_sha256"],
        "number_of_closed_bars": chain["row_count"],
        "first_open_utc": chain["first_open_utc"],
        "last_close_utc": chain["last_close_utc"],
        "actual_issuer_signed_price_message_verified": False,
        "independent_capture_clock_verified": False,
        "https_tls_session_evidence_verified": False,
        "independent_tsa_provider_assessed": False,
        "historical_account_fees_verified": False,
        "future_market_data_prospectively_verified": False,
        "actual_forward_brooks_engine_evaluated": False,
        "verified_out_of_sample_profitability": False,
        "connected_paper_authorized": False,
        "live_trading_authorized": False,
        "production_modified": False,
    }
    result["report_sha256"] = _hash(_canonical(result))
    return result, csv_bytes, stage21c


__all__ = ["Stage21IntakeRefused", "stage21f_admit_offline_binance_response"]
