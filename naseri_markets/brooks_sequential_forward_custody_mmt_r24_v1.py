"""MMT-R24: manually continued Brooks future source custody; no background collector.

Replay original bytes and full previous local receipts BEFORE any new public
network request. SHA chaining is tamper-evident in a controlled local archive,
NOT an independently signed provider record or externally attested receive time.
No order, signal, strategy decision, broker, fee calculation, or PAPER system.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .brooks_forward_source_custody_stage21g_v1 import (
    Stage21GTransportObservation,
    _canon,
    _download_pinned_https,
    _now,
    _prepare_admission,
    _query,
    _read_original_evidence,
    _sha,
    _write_exclusive,
)
from .brooks_prospective_forward_custody_stage21c_v1 import (
    _gate,
    _load_plan,
    _no_duplicates,
)
from .brooks_future_kline_admission_stage21f_v1 import _CANONICAL_PLAN_SHA

_STUDY_BAR = timedelta(minutes=15)
_MAX_REPLAY_FOLDERS = 128
_MAX_WAIT_AFTER_CLOSE = timedelta(hours=1)
_COMPLETE_COMMON = frozenset({
    "attempt.json",
    "original-venue-response.json",
    "canonical-reviewed-closed-candles.csv",
    "stage21f-quarantine-receipt.json",
    "source-tls-http-observation.json",
})
_CONTINUATION_NAME = "stage24-previous-batch-link.json"
_SHA_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_MAX_STORED = {
    "attempt.json": 8192,
    "original-venue-response.json": 131072,
    "canonical-reviewed-closed-candles.csv": 160000,
    "stage21f-quarantine-receipt.json": 16000,
    "source-tls-http-observation.json": 8192,
    _CONTINUATION_NAME: 8192,
}


class Stage24CustodyRefused(ValueError):
    """Sanitized static refusal; no untrusted data in error messages."""


@dataclass(frozen=True, slots=True)
class Stage24ReplayState:
    next_open_utc: datetime
    previous_inner_receipt_bytes: bytes
    last_outer_receipt_sha256: str
    previous_batch_digest: str
    accepted_batches: int


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _strict_read(directory: Path, filename: str) -> bytes:
    candidate = directory / filename
    if candidate.is_symlink() or not candidate.is_file():
        raise Stage24CustodyRefused("R24_SOURCE_FILE_MISSING_OR_SYMLINK")
    fd = os.open(candidate, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        status = os.fstat(fd)
        if (not stat.S_ISREG(status.st_mode) or status.st_size < 1
                or status.st_size > _MAX_STORED[filename]):
            raise Stage24CustodyRefused("R24_SOURCE_FILE_SIZE_OR_TYPE_INVALID")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            raw = handle.read(_MAX_STORED[filename] + 1)
        if len(raw) != status.st_size:
            raise Stage24CustodyRefused("R24_SOURCE_SIZE_CHANGED_WHILE_READING")
        return raw
    finally:
        os.close(fd)


def _strict_json(raw: bytes) -> dict:
    if type(raw) is not bytes or not 2 <= len(raw) <= 16000:
        raise Stage24CustodyRefused("R24_CANONICAL_JSON_REQUIRED")
    try:
        record = json.loads(raw.decode("ascii"), object_pairs_hook=_no_duplicates)
        if type(record) is not dict or _canon(record) != raw:
            raise ValueError("not canonical")
    except (ValueError, UnicodeError, TypeError) as exc:
        raise Stage24CustodyRefused("R24_NONCANONICAL_OR_DUPLICATE_RECEIPT_REFUSED") from exc
    return record


def _utc_iso(text: object) -> datetime:
    if type(text) is not str or not text.endswith("+00:00") or len(text) > 50:
        raise Stage24CustodyRefused("R24_RECORDED_UTC_CLOCK_NOT_CANONICAL")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise Stage24CustodyRefused("R24_RECORDED_UTC_CLOCK_INVALID") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0) or parsed.isoformat() != text:
        raise Stage24CustodyRefused("R24_RECORDED_UTC_CLOCK_NOT_CANONICAL")
    return parsed.astimezone(UTC)


def _sha_string(value: object) -> bool:
    return type(value) is str and _SHA_PATTERN.fullmatch(value) is not None


def _fingerprint(files: dict[str, bytes]) -> str:
    """Link all preserved source, normalized and transport bytes, not just JSON receipts."""
    return _digest(_canon({
        "protocol": "R24_PRESERVED_BATCH_ALL_ORIGINAL_BYTES_V1",
        "file_sha256": {name: _digest(raw) for name, raw in sorted(files.items())},
    }))


def stage24_replay_all_previous_batches(
    *, previous_directories: tuple[Path, ...], witness: dict[str, bytes],
    operator_ack: bool = False,
) -> Stage24ReplayState:
    """Reject missing, reordered, rewritten, forged and noncontiguous local receipts.

    Call with EVERY accepted previous batch directory, oldest first.
    Cannot prove an operator did not rewrite *all* files: external source/clock
    independence must be assessed separately.
    """
    _gate(operator_ack)
    if (type(previous_directories) is not tuple
            or not 1 <= len(previous_directories) <= _MAX_REPLAY_FOLDERS):
        raise Stage24CustodyRefused("R24_COMPLETE_PRIOR_BATCH_LIST_REQUIRED")
    plan, start, end = _load_plan(
        witness["exact-frozen-brooks-plan.json"], _CANONICAL_PLAN_SHA,
    )
    if plan.symbol != "BTCUSDT" or plan.timeframe != "15m":
        raise Stage24CustodyRefused("R24_SIGNED_EXPERIMENT_SCOPE_MISMATCH")
    expected_open = start
    previous_inner: bytes | None = None
    last_outer_sha = _CANONICAL_PLAN_SHA
    previous_digest = _CANONICAL_PLAN_SHA
    visited: set[Path] = set()
    for index, folder in enumerate(previous_directories):
        if (not isinstance(folder, Path) or not folder.is_absolute()
                or folder.is_symlink() or not folder.is_dir()):
            raise Stage24CustodyRefused("R24_ABSOLUTE_PRIOR_BATCH_DIRECTORY_REQUIRED")
        actual = folder.resolve(strict=True)
        if actual in visited:
            raise Stage24CustodyRefused("R24_DUPLICATE_PRIOR_BATCH_DIRECTORY")
        visited.add(actual)
        names = frozenset(child.name for child in folder.iterdir())
        required = _COMPLETE_COMMON | (frozenset({_CONTINUATION_NAME}) if index else frozenset())
        if names != required:
            raise Stage24CustodyRefused("R24_PRIOR_BATCH_MISSING_UNEXPECTED_OR_FAILED")
        files = {name: _strict_read(folder, name) for name in sorted(required)}
        attempt = _strict_json(files["attempt.json"])
        recorded = _strict_json(files["stage21f-quarantine-receipt.json"])
        trace = _strict_json(files["source-tls-http-observation.json"])
        count = recorded.get("candle_count")
        if type(count) is not int or not 1 <= count <= 96:
            raise Stage24CustodyRefused("R24_PRIOR_SOURCE_CANDLE_COUNT_NOT_VALID")
        next_close = expected_open + count * _STUDY_BAR
        inner = recorded.get("stage21c_receipt")
        if (next_close > end or type(inner) is not dict
                or inner.get("sequence") != index + 1):
            raise Stage24CustodyRefused("R24_PRIOR_SOURCE_SEQUENCE_OR_WINDOW_DRIFT")
        if (attempt.get("requested_closed_bars") != count
                or attempt.get("canonical_plan_sha256") != _CANONICAL_PLAN_SHA
                or attempt.get("requested_url") != trace.get("exact_request_url")
                or attempt.get("protocol") not in (
                    ("STAGE21G_BROOKS_MANUAL_FIRST_SOURCE_CAPTURE_V1",)
                    if index == 0 else ("MMT_R24_MANUAL_NEXT_FORWARD_BATCH_V1",)
                )):
            raise Stage24CustodyRefused("R24_ATTEMPT_PARAMETERS_OR_PROTOCOL_DRIFT")
        common_attempt_keys = {
            "protocol", "canonical_plan_sha256", "requested_url",
            "requested_closed_bars", "claimed_attempt_started_utc",
        }
        first_attempt_fields = {
            "operator_ack", "no_live_or_connected_paper",
            "provider_outage_unproven", "outcome",
        }
        continued_attempt_fields = {
            "expected_first_open_utc", "expected_last_closed_utc",
            "previous_batch_digest", "previous_inner_receipt_sha256",
            "no_orders_no_connected_paper",
        }
        expected_attempt_keys = common_attempt_keys | (
            first_attempt_fields if index == 0 else continued_attempt_fields
        )
        if frozenset(attempt) != expected_attempt_keys:
            raise Stage24CustodyRefused("R24_ATTEMPT_EXACT_SCHEMA_REQUIRED")
        attempt_time = _utc_iso(attempt["claimed_attempt_started_utc"])
        if not next_close + timedelta(seconds=5) <= attempt_time <= (
            next_close + _MAX_WAIT_AFTER_CLOSE
        ):
            raise Stage24CustodyRefused("R24_ATTEMPT_DATE_OUTSIDE_CLOSED_WINDOW")
        if index == 0 and (
            attempt["operator_ack"] is not True
            or attempt["no_live_or_connected_paper"] is not True
            or attempt["provider_outage_unproven"] is not True
            or attempt["outcome"] != "CAPTURE_ATTEMPT_NOT_YET_RESOLVED"
        ):
            raise Stage24CustodyRefused("R24_INITIAL_SOURCE_ATTEMPT_FIELDS_DRIFT")
        if index and attempt["no_orders_no_connected_paper"] is not True:
            raise Stage24CustodyRefused("R24_RESUMED_SOURCE_ATTEMPT_SCOPE_DRIFT")
        if index:
            prior_link = _strict_json(files[_CONTINUATION_NAME])
            expected_link = _link(Stage24ReplayState(
                next_open_utc=expected_open,
                previous_inner_receipt_bytes=previous_inner,
                last_outer_receipt_sha256=last_outer_sha,
                previous_batch_digest=previous_digest,
                accepted_batches=index,
            ))
            if prior_link != expected_link:
                raise Stage24CustodyRefused("R24_LOCAL_SOURCE_PREVIOUS_LINK_MISMATCH")
            if (attempt.get("previous_batch_digest") != previous_digest
                    or attempt.get("previous_inner_receipt_sha256") != _digest(previous_inner)
                    or attempt.get("expected_first_open_utc") != expected_open.isoformat()
                    or attempt.get("expected_last_closed_utc") != next_close.isoformat()):
                raise Stage24CustodyRefused("R24_ATTEMPT_PREVIOUS_CHAIN_DIGEST_DRIFT")
        if (trace.get("original_body_sha256") != _digest(files["original-venue-response.json"])
                or trace.get("post_admission_receipt_sha256") != recorded.get("receipt_sha256")
                or not _sha_string(trace.get("client_observed_tls_peer_certificate_sha256"))):
            raise Stage24CustodyRefused("R24_PRIOR_RAW_BODY_TLS_OR_RECEIPT_DIGEST_DRIFT")
        if not _sha_string(recorded.get("receipt_sha256")):
            raise Stage24CustodyRefused("R24_PRIOR_OUTER_RECEIPT_SHA_REQUIRED")
        try:
            elapsed = trace["client_elapsed_seconds"]
            if type(elapsed) not in (float, int) or isinstance(elapsed, bool):
                raise ValueError("not a number")
            observation = Stage21GTransportObservation(
                request_url=trace["exact_request_url"],
                original_body=files["original-venue-response.json"],
                status=trace["http_status"],
                date_header=trace["http_date_header"],
                content_type=trace["http_content_type"],
                content_encoding=trace["http_content_encoding"],
                tls_peer_certificate_sha256=trace["client_observed_tls_peer_certificate_sha256"],
                tls_version=trace["client_observed_tls_version"],
                request_started_utc=_utc_iso(trace["client_request_started_utc"]),
                response_complete_utc=_utc_iso(trace["client_response_complete_utc"]),
                elapsed_seconds=elapsed,
            )
            expected_outer, expected_csv, expected_trace = _prepare_admission(
                observation,
                requested_url=trace["exact_request_url"],
                last_close=next_close,
                witness=witness,
                previous_stage21c_receipt_bytes=previous_inner,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise Stage24CustodyRefused("R24_PREVIOUS_BATCH_FAILED_STRICT_REPLAY") from exc
        if (_canon(expected_outer) != files["stage21f-quarantine-receipt.json"]
                or expected_csv != files["canonical-reviewed-closed-candles.csv"]
                or _canon(expected_trace) != files["source-tls-http-observation.json"]):
            raise Stage24CustodyRefused("R24_PREVIOUS_BATCH_RAW_CANONICAL_TRACE_MISMATCH")
        previous_inner = _canon(expected_outer["stage21c_receipt"])
        last_outer_sha = expected_outer["receipt_sha256"]
        previous_digest = _fingerprint(files)
        expected_open = next_close
    assert previous_inner is not None
    return Stage24ReplayState(
        next_open_utc=expected_open,
        previous_inner_receipt_bytes=previous_inner,
        last_outer_receipt_sha256=last_outer_sha,
        previous_batch_digest=previous_digest,
        accepted_batches=len(previous_directories),
    )


def _link(state: Stage24ReplayState) -> dict:
    return {
        "protocol": "MMT_R24_PREVIOUS_ACCEPTED_BATCH_LINK_V1",
        "previous_batch_digest": state.previous_batch_digest,
        "previous_outer_receipt_sha256": state.last_outer_receipt_sha256,
        "previous_inner_receipt_sha256": _digest(state.previous_inner_receipt_bytes),
        "previous_last_close_utc": state.next_open_utc.isoformat(),
        "previous_accepted_batch_count": state.accepted_batches,
        "independently_attested_external_market_time": False,
        "source_issuer_signed": False,
        "linked_trading_orders_or_paper": False,
    }


def run_stage24_manual_next_batch(
    *, witness_directory: Path, previous_directories: tuple[Path, ...],
    destination: Path, number_of_closed_bars: int, operator_ack: bool = False,
) -> dict:
    """At most ONE new public GET after complete offline replay of all prior batches.

    A missed window writes an explicit local GAP ledger, never fabricates bars
    or opens the network. An application failure writes an outage-UNKNOWN ledger.
    """
    _gate(operator_ack)
    if os.environ.get("MMT_R24_EXPLICIT_ONE_READONLY_GET") != "1":
        raise Stage24CustodyRefused("R24_EXPLICIT_ONE_READONLY_GET_APPROVAL_REQUIRED")
    if (type(number_of_closed_bars) is not int
            or not 1 <= number_of_closed_bars <= 96):
        raise Stage24CustodyRefused("R24_BOUNDED_1_TO_96_CLOSED_BARS_REQUIRED")
    if (not isinstance(destination, Path) or not destination.is_absolute()
            or destination.is_symlink() or destination.exists()
            or not destination.parent.is_dir()
            or destination.parent.is_symlink()):
        raise Stage24CustodyRefused("R24_NEW_PRIVATE_QUARANTINE_DIR_REQUIRED")
    witness = _read_original_evidence(witness_directory)
    state = stage24_replay_all_previous_batches(
        previous_directories=previous_directories, witness=witness,
        operator_ack=True,
    )
    plan, start, end = _load_plan(
        witness["exact-frozen-brooks-plan.json"], _CANONICAL_PLAN_SHA,
    )
    if state.next_open_utc <= start or state.next_open_utc >= end:
        raise Stage24CustodyRefused("R24_NEXT_BATCH_OUTSIDE_SIGNED_STUDY")
    next_close = state.next_open_utc + number_of_closed_bars * _STUDY_BAR
    if next_close > end:
        raise Stage24CustodyRefused("R24_REQUEST_EXTENDS_BEYOND_SIGNED_END")
    now = _now()
    earliest = next_close + timedelta(seconds=5)
    latest = next_close + _MAX_WAIT_AFTER_CLOSE
    if now < earliest:
        raise Stage24CustodyRefused("R24_NOT_YET_CLOSED_NO_NETWORK_OR_SOURCE_WRITE")
    destination.mkdir(mode=0o700)
    relative_query = _query(first_open=state.next_open_utc, bars=number_of_closed_bars)
    url = "https://fapi.binance.com" + relative_query
    attempt = {
        "protocol": "MMT_R24_MANUAL_NEXT_FORWARD_BATCH_V1",
        "canonical_plan_sha256": _CANONICAL_PLAN_SHA,
        "requested_url": url,
        "requested_closed_bars": number_of_closed_bars,
        "expected_first_open_utc": state.next_open_utc.isoformat(),
        "expected_last_closed_utc": next_close.isoformat(),
        "claimed_attempt_started_utc": now.isoformat(),
        "previous_batch_digest": state.previous_batch_digest,
        "previous_inner_receipt_sha256": _digest(state.previous_inner_receipt_bytes),
        "no_orders_no_connected_paper": True,
    }
    _write_exclusive(destination, "attempt.json", _canon(attempt))
    if now > latest:
        _write_exclusive(destination, "gap-ledger.json", _canon({
            "protocol": "MMT_R24_DECLARED_MISSED_FORWARD_WINDOW_V1",
            "attempt_sha256": _sha(_canon(attempt)),
            "first_missing_open_utc": state.next_open_utc.isoformat(),
            "last_requested_close_utc": next_close.isoformat(),
            "reason": "OPERATOR_RECEIVED_CLOCK_PAST_ONE_HOUR_EVIDENCE_WINDOW",
            "operator_clock_independently_attested": False,
            "binance_outage_proven": False,
            "source_bytes_invented_or_backfilled": False,
            "automatic_retry_performed": False,
            "permit_future_chain_to_skip_missing_bars": False,
            "paper_or_orders_enabled": False,
        }))
        raise Stage24CustodyRefused("R24_MISSED_PROSPECTIVE_EVIDENCE_WINDOW_NO_BACKFILL")
    _write_exclusive(destination, _CONTINUATION_NAME, _canon(_link(state)))
    try:
        observed = _download_pinned_https(relative_query)
        _write_exclusive(destination, "original-venue-response.json", observed.original_body)
        outer, normalized, trace = _prepare_admission(
            observed, requested_url=url, last_close=next_close,
            witness=witness,
            previous_stage21c_receipt_bytes=state.previous_inner_receipt_bytes,
        )
        _write_exclusive(destination, "canonical-reviewed-closed-candles.csv", normalized)
        _write_exclusive(destination, "stage21f-quarantine-receipt.json", _canon(outer))
        _write_exclusive(destination, "source-tls-http-observation.json", _canon(trace))
        return {
            "protocol": "MMT_R24_RESEARCH_ONLY_CONTINUED_CUSTODY_V1",
            "source_original_sha256": trace["original_body_sha256"],
            "local_transport_receipt_sha256": trace["receipt_sha256"],
            "local_canonical_stage21f_receipt_sha256": outer["receipt_sha256"],
            "local_stage21c_sequence": outer["stage21c_receipt"]["sequence"],
            "signed_plan_sha256": _CANONICAL_PLAN_SHA,
            "source_independently_signed": False,
            "receiver_clock_independently_attested": False,
            "corrections_inventory_complete": False,
            "real_trade_fills_verified": False,
            "oos_edge_demonstrated": False,
            "connected_paper_started": False,
            "live_orders_authorized": False,
        }
    except Exception as exc:
        code = (exc.args[0] if type(exc) is Stage24CustodyRefused and exc.args
                else "R24_CAPTURE_OR_VERIFY_FAILURE_SOURCE_OUTAGE_UNDETERMINED")
        _write_exclusive(destination, "failure-ledger.json", _canon({
            "protocol": "MMT_R24_UNRESOLVED_CAPTURE_FAILURE_V1",
            "attempt_sha256": _sha(_canon(attempt)),
            "static_reason": code,
            "exchange_outage_proven": False,
            "local_network_failure_possible": True,
            "data_backfilled_or_substituted": False,
            "automatic_retry_performed": False,
            "connected_paper_enabled": False,
            "production_modified": False,
        }))
        raise


__all__ = [
    "Stage24CustodyRefused",
    "Stage24ReplayState",
    "stage24_replay_all_previous_batches",
    "run_stage24_manual_next_batch",
]
