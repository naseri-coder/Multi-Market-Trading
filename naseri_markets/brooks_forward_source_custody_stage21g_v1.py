"""Stage21G: bounded, manual, nonproduction first-window Binance Futures HTTPS custody.

Does not place orders, connect PAPER, start a scheduler, supply a secret, or
claim independent exchange/timestamp attestation. A successful CA-verified TLS
channel is transport evidence, not an exchange-signed price feed. The HTTPS
Date header and runner clock are not independent clock attestations.
"""
from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import ssl
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

from .brooks_future_kline_admission_stage21f_v1 import (
    stage21f_admit_future_kline_batch_to_quarantine,
)
from .brooks_prospective_forward_custody_stage21c_v1 import _gate, _load_plan

_PLAN_SHA = "c557e8792ff7f097ee483903e2e6702c622a20f3975af898ee9aca7e257ad94d"
_SOURCE_HOST = "fapi.binance.com"
_EXPECTED_EVIDENCE = {
    "exact-frozen-brooks-plan.json": _PLAN_SHA,
    "original-external-timestamp-response.tsr":
        "2e36862213d0f32cffadf161b3edae2610b03eef32f49e3b368253b49f83cf75",
    "tsa-root-public.pem":
        "2151b61137ffa86bf664691ba67e7da0b19f98c758e3d228d5d8ebf27e044438",
    "tsa-signer-public.pem":
        "8bfb0305bb64e2571ca507552ef3245cb1c2fee8728e0ff8689225081ea13467",
}
_MAX_BODY = 131_072
_MAX_ARTIFACT_ITEM = 16_384
_FIRST_WINDOW_GRACE = timedelta(minutes=60)
_RECV_SKEW = timedelta(minutes=3)
_MAX_DURATION_SECONDS = 25


class Stage21GRefused(ValueError):
    """Static refusal codes; never print secrets or untrusted response bodies."""


@dataclass(frozen=True, slots=True)
class Stage21GTransportObservation:
    request_url: str
    original_body: bytes
    status: int
    date_header: str
    content_type: str
    content_encoding: str
    tls_peer_certificate_sha256: str
    tls_version: str
    request_started_utc: datetime
    response_complete_utc: datetime
    elapsed_seconds: float


def _now() -> datetime:
    return datetime.now(UTC)


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canon(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"),
        allow_nan=False, ensure_ascii=True,
    ).encode("ascii")


def _read_original_evidence(folder: Path) -> dict[str, bytes]:
    if (not isinstance(folder, Path) or not folder.is_absolute()
            or folder.is_symlink() or not folder.is_dir()):
        raise Stage21GRefused("ST21G_ABSOLUTE_UNLINKED_EVIDENCE_DIRECTORY_REQUIRED")
    result = {}
    for name, expected_sha in _EXPECTED_EVIDENCE.items():
        path = folder / name
        if path.is_symlink() or not path.is_file():
            raise Stage21GRefused("ST21G_ORIGINAL_EVIDENCE_MISSING_OR_LINKED")
        with path.open("rb") as handle:
            raw = handle.read(_MAX_ARTIFACT_ITEM + 1)
        if not 1 <= len(raw) <= _MAX_ARTIFACT_ITEM or _sha(raw) != expected_sha:
            raise Stage21GRefused("ST21G_ORIGINAL_WITNESS_ARTIFACT_PIN_DRIFT")
        result[name] = raw
    _load_plan(result["exact-frozen-brooks-plan.json"], _PLAN_SHA)
    return result


def _query(*, first_open: datetime, bars: int) -> str:
    return (
        "/fapi/v1/klines?interval=15m"
        f"&limit={bars}&startTime={int(first_open.timestamp() * 1000)}"
        "&symbol=BTCUSDT"
    )


def _download_pinned_https(path: str) -> Stage21GTransportObservation:
    """Exactly one direct CA-verified HTTPS GET; no redirect, retry or proxy."""
    if not path.startswith("/fapi/v1/klines?interval=15m&limit="):
        raise Stage21GRefused("ST21G_STRICT_PUBLIC_ENDPOINT_REQUIRED")
    context = ssl.create_default_context()
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    connection = http.client.HTTPSConnection(_SOURCE_HOST, timeout=15, context=context)
    started = _now()
    monotonic = time.monotonic()
    try:
        connection.connect()  # OS trust store; hostname-checked standard TLS.
        sock = connection.sock
        if sock is None:
            raise Stage21GRefused("ST21G_TLS_SOCKET_UNAVAILABLE")
        certificate = sock.getpeercert(binary_form=True)
        if not certificate or len(certificate) > 16384:
            raise Stage21GRefused("ST21G_NO_VALID_TLS_PEER_CERTIFICATE")
        peer_digest = _sha(certificate)
        tls_version = sock.version()
        if tls_version not in ("TLSv1.2", "TLSv1.3"):
            raise Stage21GRefused("ST21G_UNSAFE_TLS_VERSION")
        connection.request(
            "GET", path, headers={
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "User-Agent": "MMT-Brooks-Stage21G-ReadOnlyResearch/1",
                "Connection": "close",
            },
        )
        response = connection.getresponse()
        # Always cap even on error; an unexpected 302 is never followed.
        body = response.read(_MAX_BODY + 1)
        completed = _now()
        elapsed = time.monotonic() - monotonic
        if not 0 < len(body) <= _MAX_BODY or elapsed > _MAX_DURATION_SECONDS:
            raise Stage21GRefused("ST21G_OVERSIZED_OR_TIMED_OUT_RESPONSE")
        return Stage21GTransportObservation(
            request_url="https://" + _SOURCE_HOST + path,
            original_body=body,
            status=response.status,
            date_header=response.getheader("Date", ""),
            content_type=response.getheader("Content-Type", ""),
            content_encoding=response.getheader("Content-Encoding", "identity"),
            tls_peer_certificate_sha256=peer_digest,
            tls_version=tls_version,
            request_started_utc=started,
            response_complete_utc=completed,
            elapsed_seconds=elapsed,
        )
    except (OSError, ssl.SSLError, TimeoutError, http.client.HTTPException) as exc:
        raise Stage21GRefused("ST21G_NETWORK_OR_TLS_FAILURE_NOT_EXCHANGE_OUTAGE") from exc
    finally:
        connection.close()


def _date(text: str) -> datetime:
    if type(text) is not str or not 1 <= len(text) <= 96:
        raise Stage21GRefused("ST21G_ORIGINAL_HTTP_DATE_REQUIRED")
    try:
        value = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError) as exc:
        raise Stage21GRefused("ST21G_BAD_PROVIDER_DATE_HEADER") from exc
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise Stage21GRefused("ST21G_HTTP_DATE_NOT_UTC")
    return value.astimezone(UTC)


def _prepare_admission(
    observation: Stage21GTransportObservation, *,
    requested_url: str, last_close: datetime, witness: dict[str, bytes],
) -> tuple[dict, bytes, dict]:
    if (type(observation) is not Stage21GTransportObservation
            or observation.request_url != requested_url
            or type(observation.status) is not int or observation.status != 200
            or not observation.content_type.lower().startswith("application/json")
            or observation.content_encoding.lower() not in ("", "identity")
            or not re.fullmatch(
                r"[a-f0-9]{64}", observation.tls_peer_certificate_sha256,
            ) or observation.tls_version not in ("TLSv1.2", "TLSv1.3")
            or not 0 <= observation.elapsed_seconds <= _MAX_DURATION_SECONDS):
        raise Stage21GRefused("ST21G_DIRECT_TLS_HTTP_SOURCE_OBSERVATION_REFUSED")
    if (observation.request_started_utc.tzinfo is None
            or observation.response_complete_utc.tzinfo is None
            or observation.request_started_utc.utcoffset() != timedelta(0)
            or observation.response_complete_utc.utcoffset() != timedelta(0)
            or not observation.request_started_utc <= observation.response_complete_utc
            or not last_close + timedelta(seconds=5) <= observation.response_complete_utc
            <= last_close + _FIRST_WINDOW_GRACE):
        raise Stage21GRefused("ST21G_FIRST_WINDOW_TIMELINESS_NOT_DEMONSTRATED")
    reported = _date(observation.date_header)
    if abs(reported - observation.response_complete_utc) > _RECV_SKEW:
        raise Stage21GRefused("ST21G_PROVIDER_DATE_AND_RUNNER_CLOCK_DRIFT")
    report, canonical_csv = stage21f_admit_future_kline_batch_to_quarantine(
        exact_frozen_plan=witness["exact-frozen-brooks-plan.json"],
        original_tsr_der=witness["original-external-timestamp-response.tsr"],
        original_ca_pem=witness["tsa-root-public.pem"],
        original_tsa_signer_pem=witness["tsa-signer-public.pem"],
        original_provider_body_bytes=observation.original_body,
        declared_request_url=observation.request_url,
        declared_http_status=observation.status,
        declared_tls_verified=True,
        operator_received_at_utc=observation.response_complete_utc,
        previous_stage21c_receipt_bytes=None,
        operator_ack=True,
    )
    trace = {
        "method": "GET",
        "direct_https_hostname": _SOURCE_HOST,
        "exact_request_url": observation.request_url,
        "http_status": observation.status,
        "http_date_header": observation.date_header,
        "http_content_type": observation.content_type,
        "http_content_encoding": observation.content_encoding,
        "client_request_started_utc": observation.request_started_utc.isoformat(),
        "client_response_complete_utc": observation.response_complete_utc.isoformat(),
        "client_elapsed_seconds": round(observation.elapsed_seconds, 6),
        "client_observed_tls_version": observation.tls_version,
        "client_observed_tls_peer_certificate_sha256":
            observation.tls_peer_certificate_sha256,
        "original_body_sha256": _sha(observation.original_body),
        "post_admission_receipt_sha256": report["receipt_sha256"],
        "tls_ca_and_hostname_verified_by_client": True,
        "request_was_made_without_credentials_or_proxy": True,
        "provider_http_date_independently_authenticated": False,
        "client_clock_independently_attested": False,
        "source_venue_signature_verified": False,
        "provider_data_revision_absence_proven": False,
        "outage_is_attributable_to_provider": False,
        "actual_forward_brooks_decisions_executed": False,
        "forward_paper_enabled": False,
        "live_trading_authorized": False,
        "production_modified": False,
    }
    trace["receipt_sha256"] = _sha(_canon(trace))
    return report, canonical_csv, trace


def _write_exclusive(folder: Path, name: str, raw: bytes) -> None:
    destination = folder / name
    fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())


def run_stage21g_manual_first_window(
    *, witness_directory: Path, destination: Path,
    number_of_closed_bars: int, operator_ack: bool = False,
) -> dict:
    """First future batch ONLY. Explicit one-shot, not an unattended collector.

    Actual collection before Oct 20 2026 00:15:05Z is refused.
    Other batches require a new separately reviewed extension of the protocol.
    """
    _gate(operator_ack)
    if os.environ.get("ST21G_EXPLICIT_MANUAL_CAPTURE") != "1":
        raise Stage21GRefused("ST21G_EXPLICIT_MANUAL_CAPTURE_APPROVAL_REQUIRED")
    if type(number_of_closed_bars) is not int or not 1 <= number_of_closed_bars <= 96:
        raise Stage21GRefused("ST21G_FIRST_CAPTURE_1_TO_96_CLOSED_BARS_REQUIRED")
    if (not isinstance(destination, Path) or not destination.is_absolute()
            or destination.is_symlink() or destination.exists()):
        raise Stage21GRefused("ST21G_FRESH_ABSOLUTE_QUARANTINE_REQUIRED")
    witness = _read_original_evidence(witness_directory)
    plan, start, end = _load_plan(witness["exact-frozen-brooks-plan.json"], _PLAN_SHA)
    last_close = start + timedelta(minutes=15 * number_of_closed_bars)
    observed_now = _now()
    if (last_close > end or observed_now < last_close + timedelta(seconds=5)
            or observed_now > last_close + _FIRST_WINDOW_GRACE):
        raise Stage21GRefused("ST21G_NOT_YET_OPEN_OR_TOO_LATE_TO_CAPTURE_FIRST_WINDOW")
    request_path = _query(first_open=start, bars=number_of_closed_bars)
    requested_url = "https://" + _SOURCE_HOST + request_path
    destination.mkdir(mode=0o700, parents=False)
    attempt = {
        "protocol": "STAGE21G_BROOKS_MANUAL_FIRST_SOURCE_CAPTURE_V1",
        "requested_url": requested_url,
        "requested_closed_bars": number_of_closed_bars,
        "canonical_plan_sha256": _PLAN_SHA,
        "claimed_attempt_started_utc": observed_now.isoformat(),
        "operator_ack": True,
        "no_live_or_connected_paper": True,
        "provider_outage_unproven": True,
        "outcome": "CAPTURE_ATTEMPT_NOT_YET_RESOLVED",
    }
    _write_exclusive(destination, "attempt.json", _canon(attempt))
    try:
        observed = _download_pinned_https(request_path)
        _write_exclusive(destination, "original-venue-response.json", observed.original_body)
        report, normalized, trace = _prepare_admission(
            observed, requested_url=requested_url, last_close=last_close, witness=witness,
        )
        _write_exclusive(destination, "canonical-reviewed-closed-candles.csv", normalized)
        _write_exclusive(destination, "stage21f-quarantine-receipt.json", _canon(report))
        _write_exclusive(destination, "source-tls-http-observation.json", _canon(trace))
        return trace
    except Exception as exc:
        # A client failure is NOT proof of an exchange outage. No retry.
        code = exc.args[0] if (type(exc) is Stage21GRefused and exc.args) else (
            "ST21G_UNCLASSIFIED_RESEARCH_CAPTURE_FAILURE"
        )
        failure = {
            "protocol": "STAGE21G_CAPTURE_FAILURE_LEDGER_V1",
            "attempt_sha256": _sha(_canon(attempt)),
            "sanitized_refusal_code": code,
            "data_filled_or_backdated": False,
            "provider_outage_proven": False,
            "automatic_retry_performed": False,
            "paper_enabled": False,
            "production_modified": False,
        }
        _write_exclusive(destination, "failure-ledger.json", _canon(failure))
        raise


def compare_stage21g_same_window_source_bytes(
    *, old_original_response: bytes, newly_observed_response: bytes,
) -> dict:
    """Revision detection; never rewrite/upgrade the original response."""
    if (type(old_original_response) is not bytes
            or type(newly_observed_response) is not bytes
            or not 1 <= len(old_original_response) <= _MAX_BODY
            or not 1 <= len(newly_observed_response) <= _MAX_BODY):
        raise Stage21GRefused("ST21G_TWO_BOUNDED_ORIGINAL_SOURCE_BYTES_REQUIRED")
    first, second = _sha(old_original_response), _sha(newly_observed_response)
    result = {
        "protocol": "STAGE21G_SOURCE_REVISION_COMPARISON_ONLY_V1",
        "original_response_sha256": first,
        "later_observation_sha256": second,
        "raw_source_bytes_changed": first != second,
        "replace_original_source_permitted": False,
        "needs_manual_correction_investigation": first != second,
        "provider_revision_proven": False,
        "future_oos_evidence_automatically_accepted": False,
    }
    result["receipt_sha256"] = _sha(_canon(result))
    return result


__all__ = [
    "Stage21GRefused", "Stage21GTransportObservation",
    "run_stage21g_manual_first_window",
    "compare_stage21g_same_window_source_bytes",
]
