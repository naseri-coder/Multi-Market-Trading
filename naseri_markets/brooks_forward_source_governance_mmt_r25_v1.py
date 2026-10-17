"""MMT-R25: OFFLINE venue-source policy, correction journal and forward schedule.

This is an adverse-evidence review, NOT authentication of Binance history.
FreeTSA signs the experimental PLAN; it does not sign market responses, an
Android receive clock, or account fills. All source-governance outcomes
remain blocked for independently proven venue provenance and economic OOS.
No HTTP client, broker, signals, trading, cron or background worker exists here.
"""
from __future__ import annotations

import hashlib
import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .brooks_forward_source_custody_stage21g_v1 import (
    _canon,
    _read_original_evidence,
    _write_exclusive,
)
from .brooks_future_kline_admission_stage21f_v1 import (
    _CANONICAL_PLAN_SHA,
    Stage21AdmissionRefused,
    _rows,
)
from .brooks_prospective_forward_custody_stage21c_v1 import (
    _gate,
    _load_plan,
    _timestamp,
)
from .brooks_sequential_forward_custody_mmt_r24_v1 import (
    _strict_json,
    _strict_read,
    stage24_replay_all_previous_batches,
)
from .brooks_termux_readiness_mmt_r23_v1 import stage23_offline_witness_preflight

_BAR = timedelta(minutes=15)
_CAPTURE_LAG = timedelta(seconds=5)
_MAX_RESPONSE_LAG = timedelta(hours=1)
_MAX_CANDLES = 96
_MAX_SOURCE_BYTES = 131072
_POLICY_KIND = "MMT_R25_FROZEN_BROOKS_FORWARD_PROVENANCE_POLICY_V1"
_REVISION_KIND = "MMT_R25_UNTRUSTED_LATER_SOURCE_OBSERVATION_V1"
_GOVERNANCE_FLAGS = {
    "original_rfc3161_plan_authenticated_under_pinned_root": True,
    "original_market_response_venue_signed": False,
    "independent_receive_clock_attested": False,
    "independent_market_custodian_receipt_verified": False,
    "exchange_revisions_and_outages_independently_reconciled": False,
    "account_specific_fee_and_fill_evidence_confirmed": False,
    "true_prospective_oos_edge_demonstrated": False,
    "paper_mode_authorized": False,
    "live_orders_authorized": False,
    "production_modified": False,
}


class Stage25PolicyRefused(ValueError):
    """Static refusal codes only, never untrusted venue data in messages."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _utc_clock(value: datetime) -> datetime:
    if (type(value) is not datetime or value.tzinfo is None
            or value.utcoffset() != timedelta(0)):
        raise Stage25PolicyRefused("R25_EXPLICIT_UTC_AWARE_CLOCK_REQUIRED")
    return value.astimezone(UTC)


def _witness_and_study(folder: Path, recorded_at: datetime):
    # Actually re-run original pinned RFC3161 OpenSSL verification, not merely
    # trust that a prior report claimed a genuine timestamp.
    first = stage23_offline_witness_preflight(
        evidence_directory=folder,
        at_utc=recorded_at,
        operator_ack=True,
    )
    if (first.get("actual_external_rfc3161_signature_verified") is not True
            or first.get("canonical_frozen_plan_sha256") != _CANONICAL_PLAN_SHA
            or first.get("future_market_candles_received") is not False
            or first.get("paper_mode_active") is not False):
        raise Stage25PolicyRefused("R25_EXTERNAL_SIGNED_STUDY_WITNESS_REFUSED")
    pinned = _read_original_evidence(folder)
    plan, start, end = _load_plan(pinned["exact-frozen-brooks-plan.json"],
                                  _CANONICAL_PLAN_SHA)
    if (plan.symbol != "BTCUSDT" or plan.timeframe != "15m"
            or plan.market != "binance_usdm" or plan.paper_market_access is not False
            or start >= end or (end-start).total_seconds() % 900 != 0):
        raise Stage25PolicyRefused("R25_SIGNED_STUDY_MARKET_OR_RANGE_DRIFT")
    return pinned, plan, start, end


def r25_fixed_manual_96bar_schedule(
    *, witness_directory: Path, as_of_utc: datetime, operator_ack: bool = False,
) -> dict:
    """14 windows, exactly 96 closed candles each; NEVER a job scheduler."""
    _gate(operator_ack)
    now = _utc_clock(as_of_utc)
    _, plan, start, end = _witness_and_study(witness_directory, now)
    total = int((end - start) / _BAR)
    if total != 1344:
        raise Stage25PolicyRefused("R25_UNEXPECTED_FROZEN_STUDY_BAR_COUNT")
    sessions = []
    for index in range(14):
        opening = start + index * _MAX_CANDLES * _BAR
        closed_at = opening + _MAX_CANDLES * _BAR
        if closed_at > end:
            raise Stage25PolicyRefused("R25_96_BAR_SCHEDULE_EXCEEDS_SIGNED_END")
        if now < closed_at + _CAPTURE_LAG:
            status = "AWAITING_LAST_CLOSED_CANDLE"
        elif now <= closed_at + _MAX_RESPONSE_LAG:
            status = "MANUAL_ONE_SHOT_WINDOW_ELIGIBLE_NOT_AUTHORIZED"
        else:
            status = "OPERATOR_CAPTURE_WINDOW_EXPIRED_NOT_BACKFILLABLE"
        sessions.append({
            "session": index + 1,
            "first_open_utc": opening.isoformat(),
            "last_close_utc": closed_at.isoformat(),
            "exact_bars": _MAX_CANDLES,
            "earliest_start_utc": (closed_at + _CAPTURE_LAG).isoformat(),
            "latest_completed_response_utc": (
                closed_at + _MAX_RESPONSE_LAG
            ).isoformat(),
            "clock_derived_window_status": status,
            "automatically_scheduled": False,
            "market_request_made": False,
        })
    if sessions[-1]["last_close_utc"] != end.isoformat():
        raise Stage25PolicyRefused("R25_SCHEDULE_FAILED_TO_COVER_EXACT_STUDY")
    data = {
        "protocol": _POLICY_KIND,
        "canonical_signed_plan_sha256": _CANONICAL_PLAN_SHA,
        "study_start_utc": start.isoformat(),
        "study_end_utc": end.isoformat(),
        "recorded_operator_clock_utc_unattested": now.isoformat(),
        "symbol": plan.symbol,
        "market": plan.market,
        "timeframe": plan.timeframe,
        "closed_bar_count": total,
        "operator_manual_sessions": len(sessions),
        "schedule_is_recommendation_not_signed_experiment_change": True,
        "no_cron_no_background_job": True,
        "no_network_requests": True,
        "trusted_market_source_status": "NOT_INDEPENDENTLY_ATTESTED",
        "receive_clock_trust_status": "OPERATOR_CLOCK_CLAIM_ONLY",
        "independent_provider_provenance_required_before_confirmatory_oos": True,
        "disposition": "RESEARCH_PROTOCOL_REVIEW_REQUIRED",
        "review_required_for_post_timestamp_data_policy": True,
        "assurance_flags": dict(_GOVERNANCE_FLAGS),
        "sessions": sessions,
    }
    data["local_document_sha256"] = _sha(_canon(data))
    return data


def r25_offline_chain_governance(
    *, witness_directory: Path, previous_directories: tuple[Path, ...],
    as_of_utc: datetime, operator_ack: bool = False,
) -> dict:
    """Recheck every original first, report gaps; never elevate source trust."""
    _gate(operator_ack)
    now = _utc_clock(as_of_utc)
    policy = r25_fixed_manual_96bar_schedule(
        witness_directory=witness_directory, as_of_utc=now, operator_ack=True,
    )
    pinned = _read_original_evidence(witness_directory)
    if type(previous_directories) is not tuple:
        raise Stage25PolicyRefused("R25_PRIOR_BATCH_LIST_MUST_BE_TUPLE")
    if previous_directories:
        state = stage24_replay_all_previous_batches(
            previous_directories=previous_directories,
            witness=pinned, operator_ack=True,
        )
        next_open = state.next_open_utc
        verified = state.accepted_batches
        last_digest = state.previous_batch_digest
    else:
        next_open = datetime.fromisoformat(policy["study_start_utc"])
        verified = 0
        last_digest = _CANONICAL_PLAN_SHA
    signed_end = datetime.fromisoformat(policy["study_end_utc"])
    if not next_open <= signed_end:
        raise Stage25PolicyRefused("R25_ACCEPTED_CHAIN_EXCEEDS_SIGNED_END")
    missing_before_now = (
        next_open < signed_end and now > next_open + _BAR + _MAX_RESPONSE_LAG
    )
    return {
        "protocol": "MMT_R25_OFFLINE_PRIOR_SOURCE_POLICY_REVIEW_V1",
        "canonical_signed_plan_sha256": _CANONICAL_PLAN_SHA,
        "operator_clock_unattested_utc": now.isoformat(),
        "replayed_and_checked_previous_batches": verified,
        "prior_local_complete_source_chain_sha256": last_digest,
        "next_unaccepted_first_open_utc": next_open.isoformat(),
        "local_clock_indicates_possible_capture_lateness": missing_before_now,
        "do_not_infer_exchange_outage_from_missing_capture": True,
        "independent_source_provenance": "UNVERIFIED",
        "receiver_timestamp_external_witness": "UNVERIFIED",
        "data_revisions_completely_excluded": False,
        "authorize_continued_prospective_qualification": False,
        "historical_backfill_qualifies_as_forward": False,
        "connected_paper_enabled": False,
        "live_order_authorized": False,
        "original_source_check_status": (
            "SIGNED_PLAN_AND_ALL_PRIOR_LOCAL_BATCHES_REPLAYED"
            if verified else "SIGNED_PLAN_ONLY_NO_PRIOR_SOURCE_EVIDENCE"
        ),
    }


def _read_bounded_candidate(path: Path) -> bytes:
    if (not isinstance(path, Path) or not path.is_absolute()
            or path.is_symlink() or not path.is_file()):
        raise Stage25PolicyRefused("R25_ABSOLUTE_ORIGINAL_CANDIDATE_REQUIRED")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        status = os.fstat(fd)
        if (not stat.S_ISREG(status.st_mode) or status.st_size < 2
                or status.st_size > _MAX_SOURCE_BYTES):
            raise Stage25PolicyRefused("R25_NEW_SOURCE_BYTES_OUTSIDE_LIMIT")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(_MAX_SOURCE_BYTES+1)
        if len(data) != status.st_size:
            raise Stage25PolicyRefused("R25_LATER_SOURCE_CHANGED_DURING_READ")
        return data
    finally:
        os.close(fd)


def r25_record_untrusted_revision_observation(
    *, witness_directory: Path, previous_directories: tuple[Path, ...],
    target_batch_index: int, later_original_body_path: Path,
    destination: Path, operator_observed_at_utc: datetime,
    operator_ack: bool = False,
) -> dict:
    """Append-only local comparison, never replace or certify a market batch.

    The candidate is OPERATOR-SUPPLIED bytes, not a signed Binance response.
    Even a legitimate changed source does NOT authorize automatic backfill,
    continuation, revised Brooks entry/exit, or confirmed prospective OOS.
    """
    _gate(operator_ack)
    now = _utc_clock(operator_observed_at_utc)
    if (type(previous_directories) is not tuple or not previous_directories
            or type(target_batch_index) is not int
            or not 0 <= target_batch_index < len(previous_directories)):
        raise Stage25PolicyRefused("R25_EXISTING_ORIGINAL_TARGET_BATCH_REQUIRED")
    if (not isinstance(destination, Path) or not destination.is_absolute()
            or destination.is_symlink() or destination.exists()
            or not destination.parent.is_dir()
            or destination.parent.is_symlink()):
        raise Stage25PolicyRefused("R25_FRESH_PRIVATE_REVISION_FOLDER_REQUIRED")
    raw_later = _read_bounded_candidate(later_original_body_path)
    witnesses, _, _, _ = _witness_and_study(witness_directory, now)
    state = stage24_replay_all_previous_batches(
        previous_directories=previous_directories,
        witness=witnesses, operator_ack=True,
    )
    target = previous_directories[target_batch_index]
    receipt = _strict_json(_strict_read(target, "stage21f-quarantine-receipt.json"))
    trace = _strict_json(_strict_read(target, "source-tls-http-observation.json"))
    raw_original = _strict_read(target, "original-venue-response.json")
    try:
        first_open = _timestamp(receipt["stage21c_receipt"]["first_open_utc"])
        count = receipt["candle_count"]
    except (KeyError, TypeError, ValueError) as exc:
        raise Stage25PolicyRefused("R25_PREVIOUS_BATCH_SCHEMA_REFUSED") from exc
    if type(count) is not int or not 1 <= count <= _MAX_CANDLES:
        raise Stage25PolicyRefused("R25_INVALID_ORIGINAL_BATCH_SIZE")
    if now < _timestamp(receipt["stage21c_receipt"]["last_close_utc"]):
        raise Stage25PolicyRefused("R25_LATER_OBSERVATION_CLAIM_BEFORE_BAR_CLOSE")
    normalized_prior = _rows(raw_original, start=first_open, expected=count)
    try:
        normalized_later = _rows(raw_later, start=first_open, expected=count)
        parse_status = "STRICT_12_FIELD_SAME_WINDOW_SCHEMA_PASS"
    except Stage21AdmissionRefused:
        normalized_later = None
        parse_status = "SOURCE_CANDIDATE_SCHEMA_REJECTED"
    if raw_original == raw_later:
        comparison = "EXACT_RAW_BYTES_UNCHANGED"
    elif normalized_later is None:
        comparison = "UNREADABLE_OR_WRONG_WINDOW_NOT_A_VALID_SOURCE_REVISION"
    elif normalized_prior == normalized_later:
        comparison = "ORIGINAL_BYTES_CHANGED_CANONICAL_CANDLES_UNCHANGED"
    else:
        comparison = "CANONICAL_SOURCE_CANDLES_CHANGED_REVIEW_REQUIRED"
    # Mark every changed-byte candidate, including semantically unchanged data,
    # for explicit methodological review. Never assert publisher correction.
    needs_review = comparison != "EXACT_RAW_BYTES_UNCHANGED"
    report = {
        "protocol": _REVISION_KIND,
        "canonical_signed_plan_sha256": _CANONICAL_PLAN_SHA,
        "original_complete_local_source_chain_sha256": state.previous_batch_digest,
        "batch_sequence": target_batch_index + 1,
        "prior_original_source_url_operator_claim": trace["exact_request_url"],
        "target_candle_first_open_utc": first_open.isoformat(),
        "target_candle_count": count,
        "recorded_later_observation_clock_utc_unattested": now.isoformat(),
        "preserved_original_source_sha256": _sha(raw_original),
        "later_observed_candidate_sha256": _sha(raw_later),
        "original_canonical_csv_sha256": _sha(normalized_prior),
        "later_canonical_csv_sha256": (
            _sha(normalized_later) if normalized_later is not None else None
        ),
        "later_source_shape_status": parse_status,
        "difference_classification": comparison,
        "requires_human_source_and_methodology_review": needs_review,
        "later_candidate_independently_from_binance_authenticated": False,
        "provider_declared_correction_independently_verified": False,
        "independent_receive_time_verified": False,
        "accepted_original_batch_was_replaced": False,
        "automatic_correction_application": False,
        "automatic_backfill_or_retry_performed": False,
        "forward_oos_qualification_granted": False,
        "paper_mode_authorized": False,
        "live_order_authorized": False,
        "disposition": "REVIEW_ONLY_ORIGINAL_CHAIN_IMMUTABLE",
    }
    report["report_sha256"] = _sha(_canon(report))
    # Only after the entire prior chain is cryptographically re-evaluated,
    # write a new exclusive research folder. The original batches are NEVER
    # rewritten, and invalid candidates are retained, clearly labeled.
    destination.mkdir(mode=0o700)
    _write_exclusive(destination, "later-operator-supplied-source.json", raw_later)
    _write_exclusive(destination, "R25-untrusted-revision-review.json", _canon(report))
    return report


__all__ = [
    "Stage25PolicyRefused",
    "r25_fixed_manual_96bar_schedule",
    "r25_offline_chain_governance",
    "r25_record_untrusted_revision_observation",
]
