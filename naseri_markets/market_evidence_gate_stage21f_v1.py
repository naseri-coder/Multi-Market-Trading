"""Stage 21F: fail-closed, independent-*code* review of captured public data.

A separately operator-invoked same-provider replay can test reproducibility,
NOT independent-provider authenticity, funding completeness, historical Mark
coverage, live liquidation safety or profitability. Never touches trading
state, accounts, Telegram, or existing Stage21C/D/E capture files.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable

from .kucoin_futures_replay_stage21_v1 import VenueReplayRefused, _public_get
from .public_forward_capture_stage21c_v1 import (
    _gate, _json, _read_private, _sha, _utc, _write_new,
    verify_capture_bundle,
)
from .public_funding_mark_stage21e_v1 import (
    MAX_PUBLIC_BYTES, FundingRequest, _read_annex,
    parse_funding_history, analyze_funding_and_mark,
)

MAX_MANIFEST_BYTES = 8192


class EvidenceGateRefused(ValueError):
    """Malformed evidence is not a clean, justified BLOCKED outcome."""


@dataclass(frozen=True, slots=True)
class CorroboratedFunding:
    symbol: str
    recapture_sha256: str
    settled_events: int
    exact_event_match: bool
    verification: str = "SAME_PROVIDER_SECOND_OBSERVATION_ONLY"


def _same(a: tuple, b: tuple) -> bool:
    return tuple((row.symbol, row.settled_at, row.rate) for row in a) == tuple(
        (row.symbol, row.settled_at, row.rate) for row in b)


def _read_recheck(folder: Path, *, required: bool) -> tuple[CorroboratedFunding, ...] | None:
    marker = folder / "stage21f_recheck.json"
    names = (folder / "stage21f_funding_0.json",
             folder / "stage21f_funding_1.json")
    if not marker.exists() and not any(p.exists() for p in names):
        if required:
            raise EvidenceGateRefused("EXPLICIT_FUNDING_RECHECK_REQUIRED")
        return None
    if not marker.is_file() or any(not path.is_file() for path in names):
        raise EvidenceGateRefused("PARTIAL_CORROBORATION_UNATTESTED")
    record, datasets, _metadata = verify_capture_bundle(folder)
    annex = json.loads(_read_private(folder / "stage21e.json", MAX_MANIFEST_BYTES))
    body = json.loads(_read_private(marker, MAX_MANIFEST_BYTES))
    if (type(body) is not dict or body.get("version") != 1
            or body.get("source") != "KUCOIN_SAME_PROVIDER_RECAPTURE"
            or body.get("stage21e_sha256") != _sha(
                _read_private(folder / "stage21e.json", MAX_MANIFEST_BYTES))
            or body.get("stage21c_sha256") != _sha(
                _read_private(folder / "sealed.json", MAX_MANIFEST_BYTES))
            or body.get("capture_mode") != record["capture_mode"]
            or type(body.get("items")) is not list or len(body["items"]) != 2):
        raise EvidenceGateRefused("CORROBORATION_MANIFEST_DRIFT")
    verified = []
    for i, (query, _raw) in enumerate(datasets):
        item = body["items"][i]
        raw = _read_private(names[i], MAX_PUBLIC_BYTES)
        initial_raw = _read_private(
            folder / f"stage21e_funding_{i}.json", MAX_PUBLIC_BYTES)
        if (item.get("symbol") != query.symbol
                or item.get("window_start") != query.start.isoformat()
                or item.get("window_end") != query.end.isoformat()
                or item.get("raw_sha256") != _sha(raw)
                or item.get("first_sha256") != _sha(initial_raw)):
            raise EvidenceGateRefused("FUNDING_RECHECK_SOURCE_OR_DIGEST_DRIFT")
        try:
            first = parse_funding_history(
                initial_raw, FundingRequest(query.symbol, query.start, query.end))
            other = parse_funding_history(
                raw, FundingRequest(query.symbol, query.start, query.end))
            instant = datetime.fromisoformat(item["observed_at"])
            original = datetime.fromisoformat(annex["sources"][i]["mark_received_at"])
        except (TypeError, ValueError, KeyError) as exc:
            raise EvidenceGateRefused("INVALID_RECHECK_TIME_OR_PAYLOAD") from exc
        if (_utc(instant) < _utc(original)
                or _utc(instant) > _utc(original) + timedelta(hours=24)):
            raise EvidenceGateRefused("RECHECK_TIME_NOT_DISTINCT_AND_BOUNDED")
        match = _same(first, other)
        if match is not True or item.get("matches_first") is not True:
            raise EvidenceGateRefused("RECHECK_FUNDING_CONTENT_CONFLICT")
        verified.append(CorroboratedFunding(
            query.symbol, _sha(raw), len(other), True))
    return tuple(verified)


def recapture_funding_for_comparison(
    folder: Path, *, operator_ack: bool = False,
    transport: Callable[[str], bytes] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> dict:
    """ONE explicitly approved second fetch per contract. No loop or retries.

    Repeated retrieval of one provider is only a consistency check. If it
    differs, refuse without overwriting the previously captured history.
    """
    _gate(operator_ack)
    record, annex, first_rows, _marks, _metadata = _read_annex(folder)
    if any((folder / filename).exists() for filename in (
            "stage21f_recheck.json", "stage21f_funding_0.json",
            "stage21f_funding_1.json")):
        raise EvidenceGateRefused("RECHECK_EXISTS_OR_PARTIAL")
    if transport is not None and not callable(transport):
        raise EvidenceGateRefused("INVALID_RECHECK_TRANSPORT")
    if (record["capture_mode"] == "INJECTED_TEST_TRANSPORT") != (
            transport is not None):
        raise EvidenceGateRefused("MIXED_RECHECK_PROVENANCE_FORBIDDEN")
    if clock is None:
        clock = lambda: datetime.now(UTC)
    when = _utc(clock())
    originals = tuple(datetime.fromisoformat(item["mark_received_at"])
                      for item in annex["sources"])
    if any(when < _utc(instant) or when > _utc(instant) + timedelta(hours=24)
           for instant in originals):
        raise EvidenceGateRefused("SECOND_OBSERVATION_WITHIN_24H_REQUIRED")
    _record, datasets, _snap = verify_capture_bundle(folder)
    responses = []
    for i, (query, _raw) in enumerate(datasets):
        request = FundingRequest(query.symbol, query.start, query.end)
        try:
            fresh = (_public_get(request.url) if transport is None
                     else transport(request.url))
        except (OSError, ValueError, VenueReplayRefused) as exc:
            raise EvidenceGateRefused("PUBLIC_FUNDING_RECHECK_UNAVAILABLE") from exc
        received = _utc(clock())
        if not timedelta(0) <= received - when <= timedelta(minutes=2):
            raise EvidenceGateRefused("RECHECK_CLOCK_ROLLBACK_OR_DELAY")
        second = parse_funding_history(fresh, request)
        if not _same(first_rows[i], second):
            raise EvidenceGateRefused("RECHECK_FUNDING_CONTENT_CONFLICT")
        responses.append((query, fresh, received, len(second), annex["sources"][i]))
    # Commit only two consistent, validated captures. If the disk write
    # fails, a partial bundle is never silently retried or represented as PASS.
    for i, (_q, raw, _observed, _count, _item) in enumerate(responses):
        _write_new(folder / f"stage21f_funding_{i}.json", raw)
    manifest = {
        "version": 1, "source": "KUCOIN_SAME_PROVIDER_RECAPTURE",
        "capture_mode": record["capture_mode"],
        "stage21e_sha256": _sha(
            _read_private(folder / "stage21e.json", MAX_MANIFEST_BYTES)),
        "stage21c_sha256": _sha(
            _read_private(folder / "sealed.json", MAX_MANIFEST_BYTES)),
        "items": [
            {"symbol": q.symbol, "window_start": q.start.isoformat(),
             "window_end": q.end.isoformat(), "raw_sha256": _sha(raw),
             "first_sha256": source["funding_sha256"],
             "observed_at": observed.isoformat(),
             "matches_first": True, "settlements": count}
            for q, raw, observed, count, source in responses
        ],
        "funding_complete": False,
        "historic_mark_prices_available": False,
        "independent_provider_verification": False,
        "live_trading_authorized": False,
    }
    _write_new(folder / "stage21f_recheck.json", _json(manifest))
    return {
        "state": "SAME_PROVIDER_RECAPTURE_MATCHED_NOT_INDEPENDENT_SOURCE",
        "symbols": [r[0].symbol for r in responses],
        "events": [r[3] for r in responses],
        "funding_complete": False,
        "independent_provider_verified": False,
        "broker_order_sent": False,
        "telegram_sent": False,
    }


def evaluate_market_evidence_gate(
    folder: Path, *, operator_ack: bool = False,
    paper_path: Path | None = None,
    require_recheck: bool = True,
) -> dict:
    """Read-only fail-closed publication gate; never overwrites PAPER.

    PASS_LOCAL_INTEGRITY is a *file-level* verdict. Even exact repetition of a
    funding response does not certify expected funding intervals or source
    independence. No accessible historical mark data from this API.
    """
    _gate(operator_ack)
    record, annex, settlements, marks, _metadata = _read_annex(folder)
    repeated = _read_recheck(folder, required=require_recheck)
    baseline = analyze_funding_and_mark(
        folder, operator_ack=True, paper_path=paper_path)
    if (baseline["stage"] != "21E"
            or baseline["current_snapshot_is_historical_price"] is not False
            or baseline["funding_history_complete"] is not False
            or baseline["liquidation_price_verified"] is not False
            or baseline["profitability_proven"] is not False):
        raise EvidenceGateRefused("PREVIOUS_STAGE_ATTESTATION_DRIFT")
    _record, datasets, _meta = verify_capture_bundle(folder)
    items = []
    for i, (query, _data) in enumerate(datasets):
        funding = settlements[i]
        mark = marks[i]
        snapshot = datetime.fromisoformat(annex["sources"][i]["mark_received_at"])
        if (mark.symbol != query.symbol or mark.observed_for > _utc(snapshot)
                or mark.observed_for < query.end):
            raise EvidenceGateRefused("CURRENT_MARK_TIMELINE_DRIFT")
        items.append({
            "symbol": query.symbol,
            "candle_count": query.expected_bars,
            "funding_events_observed": len(funding),
            "funding_events_reproducible_same_source": repeated is not None,
            "funding_recheck_sha256": (repeated[i].recapture_sha256
                                      if repeated else None),
            "funding_interval_schedule_verified": False,
            "funding_event_completeness": "UNKNOWN_NOT_ZERO",
            "historical_mark_samples_inside_window": 0,
            "historical_mark_price_coverage": "MISSING_CURRENT_ONLY",
            "current_mark_observed_at": mark.observed_for.isoformat(),
            "settlement_time_mark_attested": False,
            "exchange_source_independently_authenticated": False,
        })
    audit = baseline.get("paper_funding_scenario")
    return {
        "schema_version": 1,
        "stage": "21F",
        "mode": "READONLY_CROSS_EVIDENCE_REVIEW",
        "symbols": items,
        "source_mode": record["capture_mode"],
        "local_hash_and_schema_consistency": "PASS_LOCAL_ONLY",
        "funding_repeatability": ("MATCHED_SAME_PROVIDER_NOT_SOURCE_INDEPENDENT"
                                  if repeated else "NOT_TESTED"),
        "independent_feed_verification": "ABSENT",
        "funding_completeness": "UNVERIFIABLE_FROM_PUBLIC_RESPONSE_ALONE",
        "historical_mark_coverage": "ABSENT_CURRENT_MARK_ONLY",
        "maintenance_margin_tiers_attested": False,
        "historical_liquidation_risk_verified": False,
        "paper_journal_checked": audit is not None,
        "paper_journal_local_integrity": (audit.get("audit_state") if audit
                                          else "NOT_SUPPLIED"),
        "closed_order_scenarios": (len(audit["orders"]) if audit else None),
        "performance_evidence_gate": "BLOCKED_MISSING_MARK_FUNDING_EXECUTION_PROOF",
        "strategy_profitability_verified": False,
        "publication_authorized": False,
        "live_trading_authorized": False,
        "funding_applied_to_paper_pnl": False,
        "broker_order_sent": False,
        "telegram_sent": False,
    }


__all__ = [
    "EvidenceGateRefused", "CorroboratedFunding",
    "recapture_funding_for_comparison", "evaluate_market_evidence_gate",
]
