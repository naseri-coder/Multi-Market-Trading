"""Stage18: conservative, operator-pinned futures cashflow RECONCILIATION.

Inputs remain operator-asserted; the stage never certifies exchange-authenticated
funding, mark, fees, liquidity, liquidation or completed actual Brooks fills.
No network, orders, operational writes, strategy evaluation or Telegram.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

from .binance_vision_archive_stage16_v1 import prepare_vision_monthly_um_15m
from .futures_economic_scenario_stage16_v1 import (
    FundingMarkScenario,
    model_linear_usdm_research_scenario,
)
from .stage17_official_archive_capture_v1 import Stage17Capture

_HEX = re.compile(r"[a-f0-9]{64}\Z")
_DEC = re.compile(r"(?:0|[1-9][0-9]{0,14})(?:\.[0-9]{1,12})?\Z")
_RATE = re.compile(r"-?(?:0|[1-9][0-9]{0,2})(?:\.[0-9]{1,12})?\Z")
_ISO = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\Z")
_BASIS = timedelta(minutes=15)
_SCHEDULE_HEADER = ["funding_time_utc"]
_EVENTS_HEADER = ["funding_time_utc", "funding_rate", "mark_price"]


class Stage18Refused(ValueError):
    """Fixed, non-sensitive error identifiers for every fail-closed input."""


@dataclass(frozen=True, slots=True)
class Stage18ScenarioTrade:
    """One *hypothetical* trade; never an actual execution or Brooks output."""

    scenario_id: str
    side: str
    contracts: str
    entry_price: str
    exit_price: str
    entry_at_utc: datetime
    exit_at_utc: datetime
    isolated_collateral_usdt: str
    leverage: int


def _sha(data: bytes, digest: str, *, maximum: int) -> None:
    if (type(data) is not bytes or not 1 <= len(data) <= maximum
            or type(digest) is not str or not _HEX.fullmatch(digest)
            or hashlib.sha256(data).hexdigest() != digest):
        raise Stage18Refused("ST18_EXACT_PINNED_ARTIFACT_REQUIRED")


def _time(value: object) -> datetime:
    if (type(value) is not str or not _ISO.fullmatch(value)):
        raise Stage18Refused("ST18_CANONICAL_UTC_TIMESTAMP_REQUIRED")
    try:
        actual = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Stage18Refused("ST18_INVALID_EVENT_TIME") from exc
    if actual.utcoffset() != timedelta(0) or actual.second != 0:
        raise Stage18Refused("ST18_ALIGNED_EVENT_TIME_REQUIRED")
    return actual.astimezone(UTC)


def _scenario_time(value: object) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise Stage18Refused("ST18_EXPLICIT_UTC_SCENARIO_TIME_REQUIRED")
    if (value.second or value.microsecond
            or (value.minute % 15) or value.hour not in range(24)):
        raise Stage18Refused("ST18_FIFTEEN_MINUTE_SCENARIO_GRID_REQUIRED")
    return value.astimezone(UTC)


def _amount(value: object, *, rate: bool = False) -> Decimal:
    pattern = _RATE if rate else _DEC
    if type(value) is not str or not pattern.fullmatch(value):
        raise Stage18Refused("ST18_CANONICAL_DECIMAL_REQUIRED")
    try:
        d = Decimal(value)
    except InvalidOperation as exc:
        raise Stage18Refused("ST18_INVALID_DECIMAL") from exc
    if not d.is_finite() or (d <= 0 if not rate else abs(d) > Decimal("0.01")):
        raise Stage18Refused("ST18_OUT_OF_BOUNDS_AMOUNT_OR_RATE")
    return d


def _csv(raw: bytes, *, header: list[str], sha256: str, max_rows: int) -> list[dict[str, str]]:
    _sha(raw, sha256, maximum=128 * 1024)
    try:
        content = raw.decode("ascii")
        stream = csv.DictReader(io.StringIO(content, newline=""), strict=True)
        if stream.fieldnames != header:
            raise Stage18Refused("ST18_EXACT_CSV_SCHEMA_REQUIRED")
        rows = list(stream)
        if not 1 <= len(rows) <= max_rows or any(
            set(row) != set(header) or any(type(v) is not str or not v for v in row.values())
            for row in rows
        ):
            raise Stage18Refused("ST18_INCOMPLETE_OR_MALFORMED_EVIDENCE_ROWS")
        return rows
    except Stage18Refused:
        raise
    except (UnicodeError, csv.Error, ValueError) as exc:
        raise Stage18Refused("ST18_INVALID_EVIDENCE_CSV") from exc


def _json_report(raw: bytes) -> dict:
    if type(raw) is not bytes or not 1 <= len(raw) <= 8192:
        raise Stage18Refused("ST18_STAGE17_REPORT_REQUIRED")
    try:
        report = json.loads(raw)
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise Stage18Refused("ST18_INVALID_STAGE17_REPORT") from exc
    if type(report) is not dict:
        raise Stage18Refused("ST18_INVALID_STAGE17_REPORT")
    return report


def _reconcile_capture(capture: Stage17Capture, report_bytes: bytes) -> tuple[datetime, datetime, str]:
    if type(capture) is not Stage17Capture:
        raise Stage18Refused("ST18_EXACT_STAGE17_CAPTURE_REQUIRED")
    report = _json_report(report_bytes)
    archive = capture.archive
    if (report.get("status") != "CAPTURED_AND_LOCALLY_VALIDATED_SOURCE_UNATTESTED"
            or report.get("stage") != "STAGE17_OFFICIAL_HTTPS_CAPTURE_AND_LOCAL_QUALITY_V1"
            or report.get("original_zip_sha256") != archive.zip_sha256
            or report.get("original_checksum_sha256") != archive.checksum_sha256
            or report.get("canonical_csv_sha256") != archive.csv_sha256
            or report.get("stage12_receipt_sha256") != archive.receipt_sha256
            or report.get("rows") != archive.count
            or type(report.get("stage12_evidence_sha256")) is not str
            or not _HEX.fullmatch(report["stage12_evidence_sha256"])
            or report.get("source_independently_authenticated") is not False
            or report.get("production_authorized") is not False
            or report.get("preapproved_hashes_matched") is not capture.operator_hashes_preapproved):
        raise Stage18Refused("ST18_STAGE17_ACCEPTANCE_LINEAGE_MISMATCH")
    if any((
        hashlib.sha256(capture.original_zip).hexdigest() != archive.zip_sha256,
        hashlib.sha256(capture.original_checksum).hexdigest() != archive.checksum_sha256,
        hashlib.sha256(archive.canonical_csv_bytes).hexdigest() != archive.csv_sha256,
        hashlib.sha256(archive.stage12_receipt_bytes).hexdigest() != archive.receipt_sha256,
    )):
        raise Stage18Refused("ST18_CAPTURE_BYTES_CHANGED")
    receipt = json.loads(archive.stage12_receipt_bytes)
    claimed = datetime.fromisoformat(receipt["retrieved_at_utc"].replace("Z", "+00:00"))
    try:
        # Re-run the already reviewed Stage16 full-month validator over *original* raw bytes.
        original = prepare_vision_monthly_um_15m(
            capture.original_zip, capture.original_checksum,
            expected_zip_sha256=archive.zip_sha256,
            expected_checksum_sha256=archive.checksum_sha256,
            year=int(archive.first_open_utc[:4]), month=int(archive.first_open_utc[5:7]),
            retrieved_at_utc=claimed, operator_ack=True,
        )
    except (ValueError, TypeError, KeyError) as exc:
        raise Stage18Refused("ST18_STAGE17_REVALIDATION_FAILED") from exc
    if (original.csv_sha256 != archive.csv_sha256
            or original.receipt_sha256 != archive.receipt_sha256
            or original.count != archive.count
            or original.canonical_csv_bytes != archive.canonical_csv_bytes):
        raise Stage18Refused("ST18_STAGE17_REVALIDATION_DRIFT")
    first = datetime.fromisoformat(archive.first_open_utc.replace("Z", "+00:00"))
    last = datetime.fromisoformat(archive.last_close_utc.replace("Z", "+00:00"))
    return first, last, hashlib.sha256(report_bytes).hexdigest()


def audit_futures_economic_evidence(
    capture: Stage17Capture, *,
    stage17_quality_report_bytes: bytes,
    contract_metadata_bytes: bytes,
    contract_metadata_sha256: str,
    scheduled_funding_csv_bytes: bytes,
    scheduled_funding_sha256: str,
    funding_mark_csv_bytes: bytes,
    funding_mark_sha256: str,
    scenarios: tuple[Stage18ScenarioTrade, ...],
    operator_ack: bool = False,
) -> dict:
    """Reconcile explicit raw event inventory; model fixed costs without execution claims.

    Schedule must be separately declared and SHA-pinned *before* inspection of
    hypothetical trade results. Matching operator-declared schedule/events
    does not authenticate venue funding history or funding completeness.
    """
    if (operator_ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or "MMT_PRODUCTION" in os.environ):
        raise Stage18Refused("ST18_NONPRODUCTION_ACK_REQUIRED")
    start, end, stage17_sha = _reconcile_capture(capture, stage17_quality_report_bytes)
    _sha(contract_metadata_bytes, contract_metadata_sha256, maximum=4096)
    try:
        metadata = json.loads(contract_metadata_bytes)
    except (ValueError, UnicodeError, TypeError, RecursionError) as exc:
        raise Stage18Refused("ST18_BAD_CONTRACT_METADATA") from exc
    if type(metadata) is not dict:
        raise Stage18Refused("ST18_BAD_CONTRACT_METADATA")
    maint = _amount(metadata.get("maintenance_margin_fraction"))
    fee = _amount(metadata.get("taker_fee_fraction"), rate=True)
    slip = _amount(metadata.get("worst_slippage_fraction"), rate=True)
    if maint >= 1 or fee > Decimal("0.005") or slip > Decimal("0.005"):
        raise Stage18Refused("ST18_STRESS_COST_HEADROOM_REQUIRED")

    schedule = _csv(scheduled_funding_csv_bytes, header=_SCHEDULE_HEADER,
                    sha256=scheduled_funding_sha256, max_rows=200)
    records = _csv(funding_mark_csv_bytes, header=_EVENTS_HEADER,
                   sha256=funding_mark_sha256, max_rows=200)
    if len(schedule) != len(records):
        raise Stage18Refused("ST18_FUNDING_EVENT_INVENTORY_INCOMPLETE")
    events = []
    previous = start
    for expected, actual in zip(schedule, records, strict=True):
        instant = _time(expected["funding_time_utc"])
        if actual["funding_time_utc"] != expected["funding_time_utc"] or not previous < instant < end:
            raise Stage18Refused("ST18_UNORDERED_OR_MISSING_FUNDING_EVENT")
        rate = _amount(actual["funding_rate"], rate=True)
        mark = _amount(actual["mark_price"])
        events.append(FundingMarkScenario(instant, str(rate), str(mark)))
        previous = instant

    if type(scenarios) is not tuple or not 1 <= len(scenarios) <= 16:
        raise Stage18Refused("ST18_BOUNDED_SCENARIO_LEDGER_REQUIRED")
    result_rows = []
    seen_ids = set()
    prev_exit = start
    for trade in scenarios:
        if type(trade) is not Stage18ScenarioTrade:
            raise Stage18Refused("ST18_EXACT_HYPOTHETICAL_TRADE_REQUIRED")
        if (type(trade.scenario_id) is not str or not re.fullmatch(r"[a-z][a-z0-9_]{2,39}", trade.scenario_id)
                or trade.scenario_id in seen_ids):
            raise Stage18Refused("ST18_DUPLICATE_OR_INVALID_SCENARIO_ID")
        seen_ids.add(trade.scenario_id)
        entry = _scenario_time(trade.entry_at_utc)
        exit_at = _scenario_time(trade.exit_at_utc)
        if not (start <= prev_exit <= entry < exit_at <= end):
            raise Stage18Refused("ST18_OVERLAPPED_OR_OUT_OF_MONTH_SCENARIO")
        prev_exit = exit_at
        collateral = _amount(trade.isolated_collateral_usdt)
        qty = _amount(trade.contracts)
        entry_price = _amount(trade.entry_price)
        if type(trade.leverage) is not int or not 1 <= trade.leverage <= 20:
            raise Stage18Refused("ST18_UNREVIEWED_LEVERAGE")
        mult = _amount(metadata.get("base_units_per_contract"))
        notional = qty * mult * entry_price
        initial_margin_proxy = notional / Decimal(trade.leverage)
        maintenance_proxy = notional * maint
        if collateral <= initial_margin_proxy + maintenance_proxy:
            raise Stage18Refused("ST18_INSUFFICIENT_CONSERVATIVE_COLLATERAL")
        selected = tuple(event for event in events if entry < event.at <= exit_at)
        fixed_cases = (("baseline", 1, 1), ("fee_double", 2, 1),
                       ("slippage_double", 1, 2), ("combined_double", 2, 2))
        cases = []
        for case_id, fee_multiplier, slip_multiplier in fixed_cases:
            variant = dict(metadata)
            variant["taker_fee_fraction"] = str(fee * fee_multiplier)
            variant["worst_slippage_fraction"] = str(slip * slip_multiplier)
            raw_variant = json.dumps(variant, sort_keys=True, separators=(",", ":")).encode()
            try:
                cashflow = model_linear_usdm_research_scenario(
                    raw_variant,
                    expected_metadata_sha256=hashlib.sha256(raw_variant).hexdigest(),
                    side=trade.side,
                    quantity_contracts=trade.contracts,
                    entry_price=trade.entry_price,
                    exit_price=trade.exit_price,
                    entry_at=entry,
                    exit_at=exit_at,
                    funding_mark_events=selected,
                    operator_ack=True,
                )
            except ValueError as exc:
                raise Stage18Refused("ST18_STAGE16_SCENARIO_REFUSED") from exc
            cases.append({
                "id": case_id,
                "net_quote": cashflow["net_scenario_quote"],
                "gross_quote": cashflow["gross_quote"],
                "funding_quote": cashflow["funding_cashflow_quote"],
                "fee_quote": cashflow["taker_fees_quote"],
                "adverse_slippage_quote": cashflow["adverse_slippage_quote"],
                "model_evidence_sha256": cashflow["evidence_sha256"],
            })
        if any(Decimal(case["net_quote"]) > Decimal(cases[0]["net_quote"]) for case in cases[1:]):
            raise Stage18Refused("ST18_STRESS_CASE_MONOTONICITY_VIOLATION")
        result_rows.append({
            "scenario_id": trade.scenario_id,
            "reference_notional_quote": str(notional),
            "initial_margin_proxy_quote": str(initial_margin_proxy),
            "maintenance_margin_proxy_quote": str(maintenance_proxy),
            "declared_collateral_quote": str(collateral),
            "funding_events_in_window": len(selected),
            "cashflow_cases": cases,
            "actual_margin_tier_attested": False,
            "real_liquidation_threshold_verified": False,
            "executed_fill_prices_verified": False,
        })
    report = {
        "stage": "STAGE18_USDM_ECONOMICS_RECONCILIATION_V1",
        "status": "RESEARCH_ONLY_ASSERTED_EVIDENCE_ECONOMICS_INCOMPLETE",
        "stage17_quality_report_sha256": stage17_sha,
        "original_market_zip_sha256": capture.archive.zip_sha256,
        "canonical_month_csv_sha256": capture.archive.csv_sha256,
        "contract_metadata_sha256": contract_metadata_sha256,
        "declared_funding_schedule_sha256": scheduled_funding_sha256,
        "funding_and_mark_rows_sha256": funding_mark_sha256,
        "declared_funding_events": len(events),
        "scenario_count": len(result_rows),
        "scenarios": result_rows,
        "source_independently_authenticated": False,
        "actual_historical_funding_schedule_verified": False,
        "historical_mark_prices_authenticated": False,
        "effective_account_fee_tier_verified": False,
        "orderbook_liquidity_and_slippage_verified": False,
        "complete_margin_liquidation_model_verified": False,
        "connected_to_real_brooks_trades": False,
        "real_historical_futures_backtest_run": False,
        "out_of_sample_edge_established": False,
        "live_trading_authorized": False,
    }
    report["report_sha256"] = hashlib.sha256(json.dumps(
        report, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()).hexdigest()
    return report


__all__ = ["Stage18Refused", "Stage18ScenarioTrade", "audit_futures_economic_evidence"]
