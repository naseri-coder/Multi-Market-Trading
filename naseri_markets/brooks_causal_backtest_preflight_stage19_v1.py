"""Stage19: actual frozen Brooks V5 *decision* preflight, not a trading backtest.

This is the safe bridge across Stage17 archive provenance, Stage18 asserted
futures economics and Stage15 genuine Brooks subprocess. There is no order
simulation, PnL booking, fitting, signal send, or inferred trade fill.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .binance_vision_archive_stage16_v1 import (
    VisionBrooksWindow, select_reviewed_brooks_window,
)
from .real_brooks_historical_stage15_v1 import review_real_brooks_history
from .stage17_official_archive_capture_v1 import (
    Stage17Capture, _make_stage12_spec,
)

_SHA = re.compile(r"[a-f0-9]{64}\Z")
_STAGE18 = "STAGE18_USDM_ECONOMICS_RECONCILIATION_V1"


class Stage19Refused(ValueError):
    """Stable public failure codes only; no user or exchange data in errors."""


def _canonical(obj: object) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _validate_stage18(raw: bytes, capture: Stage17Capture) -> str:
    if type(raw) is not bytes or not 1 <= len(raw) <= 262144:
        raise Stage19Refused("ST19_PINNED_STAGE18_REPORT_REQUIRED")
    try:
        report = json.loads(raw)
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise Stage19Refused("ST19_BAD_STAGE18_REPORT") from exc
    if type(report) is not dict:
        raise Stage19Refused("ST19_BAD_STAGE18_REPORT")
    declared = report.get("report_sha256")
    unsigned = dict(report)
    unsigned.pop("report_sha256", None)
    if (type(declared) is not str or not _SHA.fullmatch(declared)
            or hashlib.sha256(_canonical(unsigned)).hexdigest() != declared
            or report.get("stage") != _STAGE18
            or report.get("status") != "RESEARCH_ONLY_ASSERTED_EVIDENCE_ECONOMICS_INCOMPLETE"
            or report.get("original_market_zip_sha256") != capture.archive.zip_sha256
            or report.get("canonical_month_csv_sha256") != capture.archive.csv_sha256
            or report.get("scenario_count") != len(report.get("scenarios", []))
            or not 1 <= report["scenario_count"] <= 16):
        raise Stage19Refused("ST19_STAGE18_ECONOMIC_LINEAGE_DRIFT")
    expected_false = (
        "source_independently_authenticated",
        "actual_historical_funding_schedule_verified",
        "historical_mark_prices_authenticated",
        "effective_account_fee_tier_verified",
        "orderbook_liquidity_and_slippage_verified",
        "complete_margin_liquidation_model_verified",
        "connected_to_real_brooks_trades",
        "real_historical_futures_backtest_run",
        "out_of_sample_edge_established",
        "live_trading_authorized",
    )
    if any(report.get(name) is not False for name in expected_false):
        raise Stage19Refused("ST19_STAGE18_UNSUPPORTED_VERIFIED_CLAIM")
    for name in (
        "stage17_quality_report_sha256", "contract_metadata_sha256",
        "declared_funding_schedule_sha256", "funding_and_mark_rows_sha256",
    ):
        if type(report.get(name)) is not str or not _SHA.fullmatch(report[name]):
            raise Stage19Refused("ST19_INCOMPLETE_STAGE18_EVIDENCE_INVENTORY")
    if type(report.get("declared_funding_events")) is not int or report["declared_funding_events"] < 1:
        raise Stage19Refused("ST19_MISSING_FUNDING_EVIDENCE")
    # An unsigned report whose author controls its hashes cannot establish
    # independent exchange custody, regardless of successful local matching.
    return declared


def review_stage19_brooks_causal_preflight(
    capture: Stage17Capture, *,
    window: VisionBrooksWindow,
    window_csv_path: Path,
    stage18_report_bytes: bytes,
    legacy_source: Path,
    evaluation_cutoffs_utc: tuple[datetime, ...],
    archive_as_of_utc: datetime,
    operator_ack: bool = False,
) -> dict:
    """Run genuine Brooks on approved closed-bar cuts, without trade accounting.

    Stage18 has *only* operator-asserted economics; Stage19 deliberately cannot
    promote its hypothetical scenario PnL into actual Brooks trade PnL.
    """
    if (operator_ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        raise Stage19Refused("ST19_EXPLICIT_NONPRODUCTION_ACK_REQUIRED")
    if (type(capture) is not Stage17Capture
            or type(window) is not VisionBrooksWindow
            or not isinstance(window_csv_path, Path)
            or not window_csv_path.is_absolute() or window_csv_path.is_symlink()
            or not isinstance(legacy_source, Path) or not legacy_source.is_absolute()
            or legacy_source.is_symlink()):
        raise Stage19Refused("ST19_PINNED_LOCAL_RESEARCH_INPUTS_REQUIRED")
    if (type(archive_as_of_utc) is not datetime or archive_as_of_utc.tzinfo is None
            or archive_as_of_utc.utcoffset() != timedelta(0)):
        raise Stage19Refused("ST19_UTC_AS_OF_REQUIRED")
    # Stage15 refuses cutoffs that are not on a closed bar or lack 60-bar warmup.
    if (type(evaluation_cutoffs_utc) is not tuple
            or not 1 <= len(evaluation_cutoffs_utc) <= 3
            or any(type(v) is not datetime or v.tzinfo is None
                   or v.utcoffset() != timedelta(0) for v in evaluation_cutoffs_utc)
            or tuple(sorted(set(evaluation_cutoffs_utc))) != evaluation_cutoffs_utc):
        raise Stage19Refused("ST19_PREDECLARED_CAUSAL_CUTS_REQUIRED")
    stage18_hash = _validate_stage18(stage18_report_bytes, capture)
    if (window.parent_official_zip_sha256 != capture.archive.zip_sha256
            or window.parent_monthly_csv_sha256 != capture.archive.csv_sha256
            or window.count < 60 or window.count > 512):
        raise Stage19Refused("ST19_WINDOW_OR_PARENT_SHA_MISMATCH")
    try:
        regenerated = select_reviewed_brooks_window(
            capture.archive, start_bar_index=window.start_bar_index,
            count=window.count, operator_ack=True,
        )
    except ValueError as exc:
        raise Stage19Refused("ST19_WINDOW_REGENERATION_REFUSED") from exc
    if regenerated != window:
        raise Stage19Refused("ST19_WINDOW_REGENERATION_DRIFT")
    if (hashlib.sha256(window.canonical_csv_bytes).hexdigest() != window.csv_sha256
            or hashlib.sha256(window.stage12_receipt_bytes).hexdigest() != window.receipt_sha256):
        raise Stage19Refused("ST19_WINDOW_SHA_MISMATCH")
    try:
        if window_csv_path.read_bytes() != window.canonical_csv_bytes:
            raise Stage19Refused("ST19_WINDOW_DISK_DATA_CHANGED")
    except OSError as exc:
        raise Stage19Refused("ST19_WINDOW_LOCAL_FILE_UNAVAILABLE") from exc

    genuine = review_real_brooks_history(
        window_csv_path, _make_stage12_spec(window.csv_sha256),
        receipt_bytes=window.stage12_receipt_bytes,
        trusted_receipt_sha256=window.receipt_sha256,
        archive_as_of_utc=archive_as_of_utc,
        legacy_source=legacy_source,
        evaluation_cutoffs_utc=evaluation_cutoffs_utc,
        operator_ack=True,
    )
    if (genuine.get("mode") != "STAGE15_REAL_PINNED_BROOKS_V5_OFFLINE_TRACE_ONLY"
            or genuine.get("dataset_sha256") != window.csv_sha256
            or genuine.get("evaluation_count") != len(evaluation_cutoffs_utc)
            or genuine.get("actual_brooks_engine_evaluated") is not True
            or genuine.get("economic_pnl_calculated") is not False
            or genuine.get("trading_edge_proven") is not False
            or genuine.get("broker_orders_authorized") is not False
            or genuine.get("telegram_sent") is not False):
        raise Stage19Refused("ST19_GENUINE_BROOKS_TRACE_INCONSISTENT")
    rows = window.canonical_csv_bytes.decode("ascii").splitlines()
    if len(rows) != window.count + 1:
        raise Stage19Refused("ST19_WINDOW_BAR_INVENTORY_DRIFT")
    end = datetime.fromisoformat(window.last_close_utc.replace("Z", "+00:00"))
    decisions = []
    for cutoff, item in zip(evaluation_cutoffs_utc, genuine["evaluations"], strict=True):
        if (item.get("closed_bar_cutoff_utc") != cutoff.isoformat()
                or item.get("decision") not in ("NO_SIGNAL", "LONG", "SHORT")
                or item.get("market_order_sent") is not False
                or item.get("telegram_sent") is not False):
            raise Stage19Refused("ST19_NONCAUSAL_OR_INCONSISTENT_DECISION")
        # The *existence* of the next bar can be checked retrospectively;
        # no next-open price, future volume or fill is exposed to the model.
        decisions.append({
            "cutoff_utc": cutoff.isoformat(),
            "actual_brooks_decision": item["decision"],
            "frozen_engine_source_sha256": item["source_manifest_sha256"],
            "decision_evidence_sha256": item["decision_evidence_sha256"],
            "visible_bar_count": item["visible_history_bar_count"],
            "has_subsequent_candle": cutoff < end,
            "future_candle_price_exposed_to_engine": False,
            "actual_strategy_entry_fill_verified": False,
            "realized_trade_pnl_calculated": False,
        })
    result = {
        "stage": "STAGE19_BROOKS_V5_CAUSAL_BACKTEST_PREFLIGHT_V1",
        "status": "REAL_FROZEN_BROOKS_DECISION_TRACE_RESEARCH_ONLY_NO_VALIDATED_BACKTEST",
        "parent_monthly_zip_sha256": capture.archive.zip_sha256,
        "parent_monthly_csv_sha256": capture.archive.csv_sha256,
        "reviewed_window_csv_sha256": window.csv_sha256,
        "stage15_report_sha256": genuine["report_sha256"],
        "stage18_report_sha256": stage18_hash,
        "actual_frozen_brooks_v5_executed": True,
        "reviewed_cuts": len(decisions),
        "decisions": decisions,
        "independent_market_data_custody_verified": False,
        "historic_funding_and_mark_verified": False,
        "contract_fee_and_margin_economics_verified": False,
        "actual_brooks_trades_filled": False,
        "economic_backtest_executed": False,
        "walk_forward_oos_executed": False,
        "profitability_proven": False,
        "telegram_sent": False,
        "broker_order_sent": False,
        "production_authorized": False,
        "next_stage_authorized": False,
        "blockers": [
            "STAGE17_REAL_SOURCE_AND_CLOCK_AUTHENTICATION_REQUIRED",
            "STAGE18_HISTORICAL_FUNDING_MARK_FEE_MARGIN_EVIDENCE_REQUIRED",
            "BROOKS_ENTRY_STOP_TARGET_EXECUTION_ATTRIBUTION_REQUIRED",
            "TRADE_LIFECYCLE_AND_CONSERVATIVE_FILL_MODEL_REQUIRED",
            "PRISTINE_OOS_NOT_TESTED",
        ],
    }
    result["report_sha256"] = hashlib.sha256(_canonical(result)).hexdigest()
    return result


__all__ = ["Stage19Refused", "review_stage19_brooks_causal_preflight"]
