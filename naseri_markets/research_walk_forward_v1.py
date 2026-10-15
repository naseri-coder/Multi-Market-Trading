"""Time-purged, explicitly scoped walk-forward AUDIT for offline PAPER outcomes.

This never trains, tunes, selects a strategy, reads data, executes a core,
books a trade, certifies edge, accesses a provider or changes a ledger.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

MAX_RECORDS = 10000
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z", re.ASCII)
_OUTCOMES = frozenset({"CLOSED_PAPER", "INCOMPLETE", "UNFILLED"})


class WalkForwardRefused(ValueError):
    """Reject invalid research inputs without echoing private evidence."""


@dataclass(frozen=True, slots=True)
class WalkForwardSettings:
    validation_folds: int
    embargo_seconds: int

    def __post_init__(self) -> None:
        if type(self.validation_folds) is not int or not 2 <= self.validation_folds <= 12:
            raise WalkForwardRefused("INVALID_WF_FOLD_COUNT")
        if type(self.embargo_seconds) is not int or not 0 <= self.embargo_seconds <= 604800:
            raise WalkForwardRefused("INVALID_WF_EMBARGO")


@dataclass(frozen=True, slots=True)
class _Record:
    order_id: str
    entry: datetime
    exit: datetime | None
    net_r: Decimal | None
    outcome: str


def _utc(value: datetime) -> datetime:
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise WalkForwardRefused("WF_UTC_TIMESTAMP_REQUIRED")
    if value.utcoffset() != timedelta(0):
        raise WalkForwardRefused("WF_UTC_TIMESTAMP_REQUIRED")
    return value.astimezone(UTC)


def _time(value: object) -> datetime:
    if type(value) is not str or not 15 <= len(value) <= 48:
        raise WalkForwardRefused("WF_UTC_TIMESTAMP_REQUIRED")
    try:
        return _utc(datetime.fromisoformat(value))
    except (TypeError, ValueError, OverflowError) as exc:
        raise WalkForwardRefused("WF_UTC_TIMESTAMP_REQUIRED") from exc


def _duration_us(value: timedelta) -> int:
    return ((value.days * 86400 + value.seconds) * 1000000 + value.microseconds)


def _records(rows: list[dict], *, start: datetime, end: datetime) -> list[_Record]:
    if type(rows) is not list or len(rows) > MAX_RECORDS:
        raise WalkForwardRefused("INVALID_WF_POPULATION")
    result: list[_Record] = []
    seen: set[str] = set()
    for row in rows:
        if type(row) is not dict:
            raise WalkForwardRefused("INVALID_WF_RECORD")
        key = row.get("order_id")
        outcome = row.get("outcome")
        if (type(key) is not str or not _ID.fullmatch(key)
                or key in seen or type(outcome) is not str or outcome not in _OUTCOMES):
            raise WalkForwardRefused("INVALID_OR_DUPLICATE_WF_RECORD")
        seen.add(key)
        entry = _time(row.get("entry_at"))
        if not start <= entry < end:
            raise WalkForwardRefused("WF_RECORD_OUTSIDE_PROTOCOL_WINDOW")
        exit_at = _time(row["exit_at"]) if row.get("exit_at") is not None else None
        if exit_at is not None and exit_at <= entry:
            raise WalkForwardRefused("NONCAUSAL_WF_OUTCOME")
        value = row.get("net_r")
        if outcome == "CLOSED_PAPER":
            if exit_at is None or type(value) is not Decimal or not value.is_finite():
                raise WalkForwardRefused("INCOMPLETE_WF_REALIZED_OUTCOME")
        elif value is not None:
            raise WalkForwardRefused("NONCLOSED_WF_HAS_REALIZED_RETURN")
        result.append(_Record(key, entry, exit_at, value, outcome))
    return result


def _summary(rows: list[_Record], *, cut: datetime) -> dict:
    # Population is never shortened; excluded records are accounted for.
    eligible = [r for r in rows if r.outcome == "CLOSED_PAPER"
                and r.exit is not None and r.exit < cut]
    crosses = sum(r.exit is not None and r.exit >= cut for r in rows)
    unresolved = sum(r.outcome == "INCOMPLETE" for r in rows)
    unfilled = sum(r.outcome == "UNFILLED" for r in rows)
    total = len(eligible)
    returns = [r.net_r for r in eligible]
    return {
        "population": len(rows),
        "eligible_closed": total,
        "cross_cutoff_exit": crosses,
        "incomplete": unresolved,
        "unfilled": unfilled,
        "win_rate_closed": str(
            Decimal(sum(r > 0 for r in returns)) / total
        ) if total else None,
        "mean_net_r_closed": str(
            sum(returns, Decimal("0")) / total
        ) if total else None,
        "excluded_from_closed_metrics": len(rows) - total,
    }


def evaluate_walk_forward(
    records: list[dict], *,
    window_start: datetime,
    training_end: datetime,
    validation_end: datetime,
    window_end: datetime,
    settings: WalkForwardSettings,
    min_closed_per_segment: int,
) -> dict:
    """Return evidence-scoped diagnostics; fail closed on invalid protocol.

    Each test fold uses only previous entries whose labels fully closed
    before the embargo-adjusted training cutoff. The reserved final holdout
    is never available to any training or validation fold.
    """
    if type(settings) is not WalkForwardSettings:
        raise WalkForwardRefused("WF_SETTINGS_REQUIRED")
    if (type(min_closed_per_segment) is not int
            or not 1 <= min_closed_per_segment <= MAX_RECORDS):
        raise WalkForwardRefused("INVALID_WF_SAMPLE_MINIMUM")
    start, train_end, valid_end, end = (
        _utc(value) for value in (window_start, training_end, validation_end, window_end)
    )
    if not start < train_end < valid_end < end or end - start > timedelta(days=400):
        raise WalkForwardRefused("INVALID_WF_STUDY_WINDOW")
    total_us = _duration_us(valid_end - train_end)
    if total_us < settings.validation_folds:
        raise WalkForwardRefused("WF_VALIDATION_WINDOW_TOO_SHORT")
    embargo = timedelta(seconds=settings.embargo_seconds)
    if train_end - embargo <= start:
        raise WalkForwardRefused("WF_TRAINING_WINDOW_TOO_SHORT")
    full = _records(records, start=start, end=end)
    folds: list[dict] = []
    global_blockers: set[str] = set()
    all_test_ids: set[str] = set()
    for i in range(settings.validation_folds):
        left = train_end + timedelta(microseconds=i * total_us // settings.validation_folds)
        right = train_end + timedelta(
            microseconds=(i + 1) * total_us // settings.validation_folds
        )
        cutoff = left - embargo
        if cutoff <= start or right <= left:
            raise WalkForwardRefused("WF_TRAINING_WINDOW_TOO_SHORT")
        prior = [r for r in full if start <= r.entry < cutoff]
        gap = [r for r in full if cutoff <= r.entry < left]
        test = [r for r in full if left <= r.entry < right]
        test_ids = {r.order_id for r in test}
        if all_test_ids.intersection(test_ids):
            raise WalkForwardRefused("WF_OVERLAPPING_VALIDATION_FOLDS")
        all_test_ids.update(test_ids)
        train_stats = _summary(prior, cut=cutoff)
        test_stats = _summary(test, cut=right)
        fold_blockers: list[str] = []
        if train_stats["eligible_closed"] < min_closed_per_segment:
            fold_blockers.append("INSUFFICIENT_FOLD_TRAINING_SAMPLE")
        if test_stats["eligible_closed"] < min_closed_per_segment:
            fold_blockers.append("INSUFFICIENT_FOLD_VALIDATION_SAMPLE")
        if train_stats["cross_cutoff_exit"]:
            fold_blockers.append("TRAIN_LABEL_CROSSES_CUTOFF")
        if test_stats["cross_cutoff_exit"]:
            fold_blockers.append("VALIDATION_LABEL_CROSSES_CUTOFF")
        if train_stats["incomplete"] or test_stats["incomplete"]:
            fold_blockers.append("INCOMPLETE_FOLD_OUTCOMES")
        global_blockers.update(fold_blockers)
        folds.append({
            "fold": i + 1,
            "train_start": start.isoformat(),
            "train_label_cutoff_exclusive": cutoff.isoformat(),
            "test_start": left.isoformat(),
            "test_end_exclusive": right.isoformat(),
            "embargo_entry_count": len(gap),
            "training": train_stats,
            "validation": test_stats,
            "blockers": fold_blockers,
        })
    validation_records = [r for r in full if train_end <= r.entry < valid_end]
    if {r.order_id for r in validation_records} != all_test_ids:
        raise WalkForwardRefused("WF_INCOMPLETE_VALIDATION_COVERAGE")
    holdout = [r for r in full if valid_end <= r.entry < end]
    holdout_stats = _summary(holdout, cut=end)
    if holdout_stats["eligible_closed"] < min_closed_per_segment:
        global_blockers.add("INSUFFICIENT_FINAL_HOLDOUT_SAMPLE")
    if holdout_stats["cross_cutoff_exit"]:
        global_blockers.add("FINAL_HOLDOUT_LABEL_EXCEEDS_WINDOW")
    if holdout_stats["incomplete"]:
        global_blockers.add("INCOMPLETE_FINAL_HOLDOUT")
    spill = sum(r.entry < valid_end and r.exit is not None
                and r.exit >= valid_end for r in full)
    if spill:
        global_blockers.add("PRE_HOLDOUT_LABEL_CROSSES_BOUNDARY")
    report = {
        "mode": "OFFLINE_PAPER_OUTCOME_FOLD_AUDIT_ONLY",
        "validation_folds": settings.validation_folds,
        "embargo_seconds": settings.embargo_seconds,
        "min_closed_per_segment": min_closed_per_segment,
        "full_study_population": len(full),
        "initial_training_population": sum(start <= r.entry < train_end for r in full),
        "validation_population": len(validation_records),
        "holdout_population": len(holdout),
        "pre_holdout_spill_count": spill,
        "folds": folds,
        "final_holdout": holdout_stats,
        "blockers": sorted(global_blockers),
        "readiness": "DESCRIPTIVE_ONLY_NOT_PROFITABILITY_PROOF",
        "independent_provider_data_verified": False,
        "prospective_holdout_verified": False,
        "strategy_retraining_performed": False,
        "parameter_selection_performed": False,
        "real_orders_sent": False,
    }
    raw = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False)
    report["audit_sha256"] = hashlib.sha256(raw.encode("ascii")).hexdigest()
    return report


__all__ = [
    "WalkForwardRefused", "WalkForwardSettings", "evaluate_walk_forward",
]
