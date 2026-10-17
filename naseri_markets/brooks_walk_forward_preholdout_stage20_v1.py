"""Stage20: strictly predeclared walk-forward *decision* protocol, PRE-HOLDOUT ONLY.

Executes actual Stage15/19 frozen Brooks V5 at one train-close and one
validation-close cut. The held-out interval is NEVER evaluated here.
This is retrospective research on operator-asserted data, not blind OOS,
fitted walk-forward, a futures trade backtest, or evidence of profitability.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .binance_vision_archive_stage16_v1 import (
    VisionBrooksWindow, select_reviewed_brooks_window,
)
from .brooks_causal_backtest_preflight_stage19_v1 import (
    review_stage19_brooks_causal_preflight,
)
from .brooks_replay import LEGACY_MANIFEST_SHA256
from .stage17_official_archive_capture_v1 import Stage17Capture

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_PROTOCOL = "BROOKS_STAGE20_PREHOLDOUT_DECISION_PROTOCOL_V1"
_BAR = timedelta(minutes=15)


class Stage20Refused(ValueError):
    """Stable, content-free research refusal identifiers."""


@dataclass(frozen=True, slots=True)
class Stage20FrozenPlan:
    """SHA-frozen geometry for one prospective split; no policy refitting."""

    protocol: str
    original_month_zip_sha256: str
    complete_month_csv_sha256: str
    economics_report_bytes_sha256: str
    brooks_source_manifest_sha256: str
    window_start_bar_index: int
    complete_research_window_bars: int
    training_end_bar: int
    validation_end_bar: int
    holdout_end_bar: int
    embargo_bars: int


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=True).encode("ascii")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def freeze_stage20_plan(plan: Stage20FrozenPlan) -> tuple[bytes, str]:
    """Create a reproducible plan receipt. This is NOT an external timestamp."""
    if type(plan) is not Stage20FrozenPlan or plan.protocol != _PROTOCOL:
        raise Stage20Refused("ST20_EXACT_FROZEN_PROTOCOL_REQUIRED")
    for sha in (
        plan.original_month_zip_sha256,
        plan.complete_month_csv_sha256,
        plan.economics_report_bytes_sha256,
        plan.brooks_source_manifest_sha256,
    ):
        if type(sha) is not str or not _SHA.fullmatch(sha):
            raise Stage20Refused("ST20_EXACT_SHA256_PROVENANCE_REQUIRED")
    if plan.brooks_source_manifest_sha256 != LEGACY_MANIFEST_SHA256:
        raise Stage20Refused("ST20_BROOKS_FROZEN_SOURCE_MISMATCH")
    values = (
        plan.window_start_bar_index,
        plan.complete_research_window_bars,
        plan.training_end_bar,
        plan.validation_end_bar,
        plan.holdout_end_bar,
        plan.embargo_bars,
    )
    if any(type(v) is not int for v in values):
        raise Stage20Refused("ST20_INTEGER_SPLIT_REQUIRED")
    start, length, train, valid, holdout, embargo = values
    if (not 0 <= start <= 3000 or not 60 <= length <= 512
            or not 1 <= embargo <= 48
            or not 60 <= train
            or not train + embargo + 1 <= valid
            or not valid + embargo + 1 <= holdout
            or holdout != length):
        raise Stage20Refused("ST20_CAUSAL_TRAIN_VALIDATION_HOLDOUT_SPLIT_REQUIRED")
    raw = _canonical(asdict(plan))
    return raw, _digest(raw)


def run_stage20_preholdout(
    capture: Stage17Capture, *,
    full_window: VisionBrooksWindow,
    frozen_plan: Stage20FrozenPlan,
    independently_approved_plan_sha256: str,
    economics_report_bytes: bytes,
    preholdout_csv_path: Path,
    original_brooks_source: Path,
    archive_as_of_utc: datetime,
    operator_ack: bool = False,
) -> dict:
    """Evaluate train/validation decisions, NEVER run the reserved holdout.

    A user-provided digest does not prove a prior time-stamped precommitment.
    Even when the data and code pass local integrity checks, there is no blind
    prospective OOS or historically witnessed genuine market truth.
    """
    if (operator_ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or "MMT_PRODUCTION" in os.environ):
        raise Stage20Refused("ST20_NONPRODUCTION_EXPLICIT_APPROVAL_REQUIRED")
    plan_bytes, plan_sha = freeze_stage20_plan(frozen_plan)
    if (type(independently_approved_plan_sha256) is not str
            or not _SHA.fullmatch(independently_approved_plan_sha256)
            or plan_sha != independently_approved_plan_sha256):
        raise Stage20Refused("ST20_PREDECLARED_PLAN_PIN_MISMATCH")
    if (type(capture) is not Stage17Capture
            or type(full_window) is not VisionBrooksWindow):
        raise Stage20Refused("ST20_STAGE17_AND_STAGE16_CAPTURE_REQUIRED")
    if (capture.archive.zip_sha256 != frozen_plan.original_month_zip_sha256
            or capture.archive.csv_sha256 != frozen_plan.complete_month_csv_sha256
            or type(economics_report_bytes) is not bytes
            or not 1 <= len(economics_report_bytes) <= 262144
            or _digest(economics_report_bytes) != frozen_plan.economics_report_bytes_sha256
            or full_window.parent_official_zip_sha256 != capture.archive.zip_sha256
            or full_window.parent_monthly_csv_sha256 != capture.archive.csv_sha256
            or full_window.start_bar_index != frozen_plan.window_start_bar_index
            or full_window.count != frozen_plan.complete_research_window_bars):
        raise Stage20Refused("ST20_EXACT_CAPTURE_ECONOMICS_OR_WINDOW_PIN_MISMATCH")
    if (not isinstance(preholdout_csv_path, Path)
            or not preholdout_csv_path.is_absolute()
            or preholdout_csv_path.is_symlink()
            or not isinstance(original_brooks_source, Path)
            or not original_brooks_source.is_absolute()
            or original_brooks_source.is_symlink()
            or type(archive_as_of_utc) is not datetime
            or archive_as_of_utc.tzinfo is None
            or archive_as_of_utc.utcoffset() != timedelta(0)):
        raise Stage20Refused("ST20_REVIEWED_ABSOLUTE_SOURCE_AND_UTC_REQUIRED")
    try:
        parent = select_reviewed_brooks_window(
            capture.archive,
            start_bar_index=frozen_plan.window_start_bar_index,
            count=frozen_plan.complete_research_window_bars,
            operator_ack=True,
        )
        # INTENTIONAL: cut the study at validation end. Neither the genuine
        # worker nor Stage19 is handed the post-validation embargo/holdout.
        prefix = select_reviewed_brooks_window(
            capture.archive,
            start_bar_index=frozen_plan.window_start_bar_index,
            count=frozen_plan.validation_end_bar,
            operator_ack=True,
        )
    except ValueError as exc:
        raise Stage20Refused("ST20_BOUNDED_WINDOW_REDERIVATION_REFUSED") from exc
    if full_window != parent:
        raise Stage20Refused("ST20_FULL_WINDOW_REDERIVATION_DRIFT")
    if (not preholdout_csv_path.is_file()
            or preholdout_csv_path.stat().st_size != len(prefix.canonical_csv_bytes)):
        raise Stage20Refused("ST20_EXACT_PREFIX_FILE_REQUIRED")
    if preholdout_csv_path.read_bytes() != prefix.canonical_csv_bytes:
        raise Stage20Refused("ST20_PREFIX_BYTES_MISMATCH")
    origin = datetime.fromisoformat(prefix.first_open_utc.replace("Z", "+00:00"))
    train_cut = origin + _BAR * frozen_plan.training_end_bar
    valid_cut = origin + _BAR * frozen_plan.validation_end_bar
    # Only two cuts, no test/holdout outcome is queried.
    receipt = review_stage19_brooks_causal_preflight(
        capture,
        window=prefix,
        window_csv_path=preholdout_csv_path,
        stage18_report_bytes=economics_report_bytes,
        legacy_source=original_brooks_source,
        evaluation_cutoffs_utc=(train_cut, valid_cut),
        archive_as_of_utc=archive_as_of_utc,
        operator_ack=True,
    )
    evaluations = receipt.get("decisions")
    if (receipt.get("actual_frozen_brooks_v5_executed") is not True
            or receipt.get("reviewed_cuts") != 2
            or receipt.get("reviewed_window_csv_sha256") != prefix.csv_sha256
            or type(evaluations) is not list or len(evaluations) != 2
            or any(d.get("actual_brooks_decision") not in ("LONG", "SHORT", "NO_SIGNAL")
                   for d in evaluations)
            or [d.get("cutoff_utc") for d in evaluations] != [
                train_cut.isoformat(), valid_cut.isoformat(),
            ]
            or receipt.get("economic_backtest_executed") is not False
            or receipt.get("broker_order_sent") is not False
            or receipt.get("telegram_sent") is not False):
        raise Stage20Refused("ST20_STAGE19_PREHOLDOUT_TRACE_INCONSISTENT")
    findings = {
        "stage": "STAGE20_BROOKS_WALK_FORWARD_PREHOLDOUT_PROTOCOL_V1",
        "verdict": "CAUSAL_DECISION_REPLAY_ONLY_HOLDOUT_UNOPENED",
        "frozen_plan_bytes_sha256": plan_sha,
        "frozen_plan_bytes_length": len(plan_bytes),
        "source_month_zip_sha256": capture.archive.zip_sha256,
        "source_month_csv_sha256": capture.archive.csv_sha256,
        "study_window_csv_sha256": full_window.csv_sha256,
        "preholdout_prefix_csv_sha256": prefix.csv_sha256,
        "economics_report_bytes_sha256": frozen_plan.economics_report_bytes_sha256,
        "actual_frozen_brooks_v5_executed": True,
        "brooks_preholdout_stage19_receipt_sha256": receipt["report_sha256"],
        "training_last_closed_bar": frozen_plan.training_end_bar,
        "validation_last_closed_bar": frozen_plan.validation_end_bar,
        "holdout_first_reserved_bar": frozen_plan.validation_end_bar + frozen_plan.embargo_bars + 1,
        "holdout_last_reserved_bar": frozen_plan.holdout_end_bar,
        "train_decision": evaluations[0]["actual_brooks_decision"],
        "validation_decision": evaluations[1]["actual_brooks_decision"],
        "train_snapshot_sha256": evaluations[0]["decision_evidence_sha256"],
        "validation_snapshot_sha256": evaluations[1]["decision_evidence_sha256"],
        "strategy_refit_or_selection_performed": False,
        "holdout_engine_evaluation_performed": False,
        "holdout_outcome_used_for_model_selection": False,
        "independent_plan_precommitment_attested": False,
        "retrospective_archive_contains_future_holdout_bytes": True,
        "pristine_prospective_oos_verified": False,
        "walk_forward_profitability_backtest_performed": False,
        "independent_exchange_price_provenance_verified": False,
        "funding_mark_margin_execution_verified": False,
        "economic_trade_pnl_calculated": False,
        "trading_edge_demonstrated": False,
        "paper_mode_authorized": False,
        "live_authorized": False,
        "blockers": [
            "REAL_EXCHANGE_MONTHLY_ARCHIVE_AND_TRUSTED_ASOF_MISSING",
            "FUNDING_MARK_FEE_AND_LIQUIDATION_TRUTH_MISSING",
            "BROOKS_GEOMETRY_TO_FILL_LIFECYCLE_MISSING",
            "INDEPENDENTLY_TIMESTAMPED_PRECOMMITMENT_MISSING",
            "FRESH_PROSPECTIVE_HOLDOUT_NOT_YET_OBSERVED",
            "ONLY_ONE_TRAIN_AND_ONE_VALIDATION_DECISION_NO_STATISTICAL_EDGE",
        ],
    }
    findings["evidence_sha256"] = _digest(_canonical(findings))
    return findings


__all__ = [
    "Stage20Refused", "Stage20FrozenPlan", "freeze_stage20_plan",
    "run_stage20_preholdout",
]
