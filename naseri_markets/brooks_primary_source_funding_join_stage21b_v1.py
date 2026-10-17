"""Stage21B: genuine BTCUSDT trade/funding/mark source -> V5 modeled ONE trade.

One fixed historical *retrospective* study only. It neither opens a
prospective holdout nor authorizes a connected PAPER daemon or real fills.
Venue archive HTTPS/checksum != independently signed publisher provenance.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .binance_public_funding_mark_stage18_v1 import (
    reconcile_stage18_primary_public_sources,
)
from .binance_vision_archive_stage16_v1 import (
    select_reviewed_brooks_window,
)
from .brooks_causal_lifecycle_stage21_preflight_v1 import (
    run_stage21_brooks_lifecycle_preflight,
)
from .futures_economic_scenario_stage16_v1 import FundingMarkScenario
from .futures_economics_evidence_stage18_v1 import _reconcile_capture
from .stage17_official_archive_capture_v1 import Stage17Capture

_SHA = re.compile(r"[a-f0-9]{64}\Z")
_FIELDS = ("open_at", "close_at", "open", "high", "low", "close", "volume")
_ORIGIN = datetime(2024, 1, 1, tzinfo=UTC)
_END = datetime(2024, 2, 1, tzinfo=UTC)
_FUNDING = timedelta(hours=8)


class Stage21SourceRefused(ValueError):
    """Stable refusal identifiers: never return untrusted file content."""


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _approved(raw: bytes, pin: str) -> None:
    if (type(raw) is not bytes or type(pin) is not str
            or not _SHA.fullmatch(pin) or _hash(raw) != pin):
        raise Stage21SourceRefused("ST21B_INDEPENDENT_OPERATOR_PIN_MISMATCH")


def _bars_exact(source: bytes, expected: int) -> tuple[dict, ...]:
    if type(source) is not bytes or not 1 <= len(source) <= 65536:
        raise Stage21SourceRefused("ST21B_EXACT_WINDOW_BOUNDS")
    try:
        rows = list(csv.reader(io.StringIO(source.decode("ascii"), newline=""), strict=True))
    except (csv.Error, UnicodeError, ValueError) as exc:
        raise Stage21SourceRefused("ST21B_INVALID_CANONICAL_SOURCE_CSV") from exc
    if (len(rows) != expected + 1 or tuple(rows[0]) != _FIELDS
            or any(len(r) != len(_FIELDS) for r in rows[1:])):
        raise Stage21SourceRefused("ST21B_CANONICAL_COLUMN_OR_WINDOW_DRIFT")
    keys = ("open_time", "close_time", "open", "high", "low", "close", "volume")
    return tuple(dict(zip(keys, row, strict=True)) for row in rows[1:])


def _source_funding(
    schedule_bytes: bytes, event_bytes: bytes, *,
    start: datetime, end: datetime,
) -> tuple[tuple[datetime, ...], tuple[FundingMarkScenario, ...]]:
    """Demand every scheduled 8h settlement in the reviewed future horizon."""
    try:
        schedule = list(csv.DictReader(io.StringIO(schedule_bytes.decode("ascii"))))
        records = list(csv.DictReader(io.StringIO(event_bytes.decode("ascii"))))
    except (UnicodeError, ValueError, csv.Error) as exc:
        raise Stage21SourceRefused("ST21B_INVALID_SOURCE_DERIVED_EVENTS") from exc
    if len(schedule) != len(records) or len(schedule) != 92:
        raise Stage21SourceRefused("ST21B_COMPLETE_SOURCE_EVENT_INVENTORY_REQUIRED")
    indices = []
    rates = []
    for schedule_row, observed in zip(schedule, records, strict=True):
        if (set(schedule_row) != {"funding_time_utc"}
                or set(observed) != {"funding_time_utc", "funding_rate", "mark_price"}
                or schedule_row["funding_time_utc"] != observed["funding_time_utc"]):
            raise Stage21SourceRefused("ST21B_FUNDING_MARK_JOIN_DRIFT")
        when = datetime.fromisoformat(
            schedule_row["funding_time_utc"].replace("Z", "+00:00")
        )
        indices.append(when)
        rates.append(FundingMarkScenario(
            at=when, funding_rate=observed["funding_rate"],
            referenced_mark_price=observed["mark_price"],
        ))
    if (tuple(sorted(set(indices))) != tuple(indices)
            or indices[0] != _ORIGIN + _FUNDING
            or indices[-1] != _END - _FUNDING):
        raise Stage21SourceRefused("ST21B_EIGHT_HOUR_EVIDENCE_COVERAGE_DRIFT")
    if (start < _ORIGIN or end > _END or not start < end
            or start.utcoffset() != timedelta(0) or end.utcoffset() != timedelta(0)):
        raise Stage21SourceRefused("ST21B_REVIEWED_MONTH_ONLY")
    expected = []
    instant = _ORIGIN
    while instant <= end:
        if start < instant <= end:
            expected.append(instant)
        instant += _FUNDING
    wanted = tuple(expected)
    selected = tuple(event for event in rates if start < event.at <= end)
    if tuple(e.at for e in selected) != wanted:
        raise Stage21SourceRefused("ST21B_FUNDING_BOUNDARY_OR_MISSING_SETTLEMENT")
    return wanted, selected


def run_stage21b_source_joined_brooks_research(
    *, capture: Stage17Capture,
    stage17_quality_report_bytes: bytes,
    expected_trade_zip_sha256: str,
    funding_zip: bytes, funding_checksum: bytes,
    expected_funding_zip_sha256: str,
    mark_zip: bytes, mark_checksum: bytes,
    expected_mark_zip_sha256: str,
    legacy_source: Path,
    contract_assumptions_bytes: bytes,
    contract_assumptions_sha256: str,
    quantity_contracts: str,
    window_start_bar_index: int = 0,
    decision_closed_bars: int = 60,
    next_closed_bars: int = 32,
    operator_ack: bool = False,
) -> dict:
    """Produce a source-pinned, *hypothetical* first V5 trade with funding.

    The market, all later candles and public archives are already historical.
    The engine worker sees only the first <=224 closed bars; after that,
    future candles are added solely to a conservative execution model.
    """
    if (operator_ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or "MMT_PRODUCTION" in os.environ):
        raise Stage21SourceRefused("ST21B_NONPRODUCTION_ACK_REQUIRED")
    if (type(capture) is not Stage17Capture
            or type(window_start_bar_index) is not int
            or type(decision_closed_bars) is not int
            or type(next_closed_bars) is not int
            or not 0 <= window_start_bar_index < 2900
            or not 60 <= decision_closed_bars <= 224
            or not 1 <= next_closed_bars <= 32):
        raise Stage21SourceRefused("ST21B_EXPLICIT_BOUNDED_PLAN_REQUIRED")
    _approved(capture.original_zip, expected_trade_zip_sha256)
    if capture.archive.zip_sha256 != expected_trade_zip_sha256:
        raise Stage21SourceRefused("ST21B_STAGE17_ARCHIVE_PIN_DRIFT")
    _approved(funding_zip, expected_funding_zip_sha256)
    _approved(mark_zip, expected_mark_zip_sha256)
    _approved(contract_assumptions_bytes, contract_assumptions_sha256)
    try:
        _reconcile_capture(capture, stage17_quality_report_bytes)
        funding_receipt, schedule, rate_mark = reconcile_stage18_primary_public_sources(
            funding_zip=funding_zip, funding_checksum=funding_checksum,
            mark_zip=mark_zip, mark_checksum=mark_checksum,
            operator_ack=True,
        )
        window = select_reviewed_brooks_window(
            capture.archive, start_bar_index=window_start_bar_index,
            count=decision_closed_bars + next_closed_bars, operator_ack=True,
        )
    except ValueError as exc:
        raise Stage21SourceRefused("ST21B_REVIEWED_SOURCE_VALIDATION_REFUSED") from exc
    joined_bars = _bars_exact(window.canonical_csv_bytes, window.count)
    prefix = joined_bars[:decision_closed_bars]
    future = joined_bars[decision_closed_bars:]
    if len(prefix) != decision_closed_bars or len(future) != next_closed_bars:
        raise Stage21SourceRefused("ST21B_CLOSED_BAR_SPLIT_MISMATCH")
    if (prefix[-1]["close_time"] != future[0]["open_time"]
            or future[-1]["close_time"] != window.last_close_utc):
        raise Stage21SourceRefused("ST21B_NONCONTIGUOUS_CLOSED_SPLIT")
    begin = datetime.fromisoformat(future[0]["open_time"].replace("Z", "+00:00"))
    finish = datetime.fromisoformat(future[-1]["close_time"].replace("Z", "+00:00"))
    times, events = _source_funding(schedule, rate_mark, start=begin, end=finish)
    replay = {
        "schema_version": 1, "origin": "replay", "market": "crypto",
        "provider": "binance_replay", "exchange": "binance",
        "market_type": "futures", "symbol": "BTCUSDT",
        "quote_currency": "USDT", "timezone": "UTC",
        "timeframe": "15m", "candles": list(prefix),
    }
    try:
        model = run_stage21_brooks_lifecycle_preflight(
            original_replay_bytes=_canonical(replay),
            legacy_source=legacy_source,
            post_signal_closed_candles=future,
            metadata_bytes=contract_assumptions_bytes,
            metadata_sha256=contract_assumptions_sha256,
            quantity_contracts=quantity_contracts,
            expected_funding_instants=times,
            funding_mark_events=events,
            operator_ack=True,
        )
    except ValueError as exc:
        raise Stage21SourceRefused("ST21B_FROZEN_BROOKS_OR_CASHFLOW_REFUSED") from exc
    if (model.get("actual_frozen_brooks_decision") not in
            ("NO_SIGNAL", "LONG", "SHORT")
            or model.get("actual_realized_pnl") is not False
            or model.get("live_trading_authorized") is not False
            or model.get("paper_trading_enabled") is not False
            or model.get("production_modified") is not False):
        raise Stage21SourceRefused("ST21B_UNSUPPORTED_ENGINE_CLAIM")
    result = {
        "stage": "STAGE21B_REAL_PRIMARY_SOURCE_BROOKS_RESEARCH_V1",
        "verdict": "GENUINE_RETROSPECTIVE_SOURCE_MODELED_NO_EXECUTED_PNL",
        "monthly_trade_source_zip_sha256": capture.archive.zip_sha256,
        "monthly_trade_source_canonical_sha256": capture.archive.csv_sha256,
        "real_funding_zip_sha256": funding_receipt["funding_zip_sha256"],
        "real_mark_zip_sha256": funding_receipt["mark_zip_sha256"],
        "funding_mark_source_receipt_sha256": funding_receipt["receipt_sha256"],
        "funding_schedule_sha256": _hash(schedule),
        "source_derived_funding_and_mark_proxy_sha256": _hash(rate_mark),
        "original_brooks_research_evidence_sha256": model["report_sha256"],
        "frozen_decision_cutoff_utc": model["decision_cutoff_utc"],
        "predecision_observed_bars": decision_closed_bars,
        "postdecision_modeled_bars": next_closed_bars,
        "evidence_closed_bar_window_sha256": window.csv_sha256,
        "funding_events_in_future_horizon": len(times),
        "actual_frozen_brooks_decision": model["actual_frozen_brooks_decision"],
        "model_trade_state": model["hypothetical_trade"]["state"],
        "hypothetical_trade_receipt": model["hypothetical_trade"],
        "backtest_policy_refitted": False,
        "provider_origin_signatures_authenticated": False,
        "funding_mark_exact_settlement_authenticated": False,
        "historical_account_fee_tier_verified": False,
        "historical_depth_orderbook_verified": False,
        "trade_fill_evidence_verified": False,
        "statistically_valid_prospective_oos_proven": False,
        "historical_archive_already_known_before_study": True,
        "paper_or_live_market_connections_enabled": False,
        "live_trading_authorized": False,
        "production_modified": False,
    }
    result["report_sha256"] = _hash(_canonical(result))
    return result


__all__ = ["Stage21SourceRefused", "run_stage21b_source_joined_brooks_research"]
