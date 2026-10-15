"""Offline PBO/DSR diagnostics for a COMPLETE, synchronized candidate return matrix.

No strategy fitting, execution, market APIs, data downloads, database access,
trade selection, trusted holdout access, or profitability certification.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import re
import statistics
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from statistics import NormalDist

_MAX_BYTES = 2_000_000
_MAX_ROWS = 960
_MAX_CANDIDATES = 16
_EULER_GAMMA = 0.5772156649015329
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z", re.ASCII)
_DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]{0,12})(?:\.[0-9]{1,12})?\Z", re.ASCII)
_KEYS = frozenset({
    "schema_version", "study_id", "candidate_ids", "selected_candidate_id",
    "declared_total_trials", "trial_inventory_complete", "cscv_blocks",
    "reserved_holdout_start_utc", "rows",
})
_ROW_KEYS = frozenset({"period_start_utc", "period_end_utc", "net_return_fraction"})


class OverfitEvidenceRefused(ValueError):
    """Never includes caller-provided values or payload fragments."""


def _unique(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, value in pairs:
        if key in result:
            raise OverfitEvidenceRefused("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _reject_constant(_value: str) -> object:
    raise OverfitEvidenceRefused("NONFINITE_JSON_CONSTANT")


def _utc(value: object) -> datetime:
    if type(value) is not str or not 20 <= len(value) <= 48:
        raise OverfitEvidenceRefused("INVALID_RESEARCH_TIMESTAMP")
    try:
        instant = datetime.fromisoformat(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise OverfitEvidenceRefused("INVALID_RESEARCH_TIMESTAMP") from exc
    if instant.tzinfo is None or instant.utcoffset() != timedelta(0):
        raise OverfitEvidenceRefused("UTC_TIMESTAMP_REQUIRED")
    instant = instant.astimezone(UTC)
    if not 2000 <= instant.year <= 2100:
        raise OverfitEvidenceRefused("RESEARCH_TIME_OUT_OF_BOUNDS")
    return instant


def _return(value: object) -> float:
    if type(value) is not str or not _DECIMAL.fullmatch(value):
        raise OverfitEvidenceRefused("DECIMAL_RETURN_STRING_REQUIRED")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise OverfitEvidenceRefused("INVALID_RETURN_DECIMAL") from exc
    if not number.is_finite() or abs(number) > 10:
        raise OverfitEvidenceRefused("INVALID_RETURN_DECIMAL")
    return float(number)


def _sharpe(values: list[float]) -> float:
    if len(values) < 12:
        raise OverfitEvidenceRefused("INSUFFICIENT_STATISTICAL_SAMPLE")
    deviation = statistics.stdev(values)
    if not math.isfinite(deviation) or deviation <= 1e-15:
        raise OverfitEvidenceRefused("ZERO_OR_INVALID_RETURN_VARIANCE")
    result = statistics.mean(values) / deviation
    if not math.isfinite(result):
        raise OverfitEvidenceRefused("NONFINITE_SHARPE")
    return result


def _moments(values: list[float]) -> tuple[float, float]:
    center = statistics.mean(values)
    centered = [v - center for v in values]
    second = math.fsum(x * x for x in centered) / len(values)
    if second <= 1e-30 or not math.isfinite(second):
        raise OverfitEvidenceRefused("ZERO_OR_INVALID_RETURN_VARIANCE")
    third = math.fsum(x ** 3 for x in centered) / len(values)
    fourth = math.fsum(x ** 4 for x in centered) / len(values)
    skew = third / second ** 1.5
    kurtosis = fourth / second ** 2
    if not (math.isfinite(skew) and math.isfinite(kurtosis)):
        raise OverfitEvidenceRefused("NONFINITE_SAMPLE_MOMENTS")
    return skew, kurtosis


def _cscv(series: list[list[float]], blocks: int) -> dict:
    """Exact symmetric CSCV, intentionally NOT causal walk-forward validation."""
    count = len(series[0])
    block_size = count // blocks
    candidate_count = len(series)
    logits: list[float] = []
    below_or_equal = 0
    rank_ties = 0
    for training_blocks in itertools.combinations(range(blocks), blocks // 2):
        chosen = set(training_blocks)
        train_indices = [
            k for block in training_blocks
            for k in range(block * block_size, (block + 1) * block_size)
        ]
        test_indices = [
            k for block in range(blocks) if block not in chosen
            for k in range(block * block_size, (block + 1) * block_size)
        ]
        insample = [
            _sharpe([values[k] for k in train_indices]) for values in series
        ]
        maximum = max(insample)
        contenders = [
            i for i, score in enumerate(insample)
            if math.isclose(score, maximum, rel_tol=1e-12, abs_tol=1e-12)
        ]
        # Picking one arbitrarily would make PBO dependent on candidate order.
        if len(contenders) != 1:
            raise OverfitEvidenceRefused("AMBIGUOUS_INSAMPLE_BEST_TRIAL")
        selected = contenders[0]
        outsample = [
            _sharpe([values[k] for k in test_indices]) for values in series
        ]
        target = outsample[selected]
        less = sum(score < target and not math.isclose(
            score, target, rel_tol=1e-12, abs_tol=1e-12
        ) for score in outsample)
        same = sum(math.isclose(
            score, target, rel_tol=1e-12, abs_tol=1e-12
        ) for score in outsample)
        if same > 1:
            rank_ties += 1
        # Midrank with denominator N+1: never log(0) or log(infinity).
        relative_rank = (less + (same + 1) / 2) / (candidate_count + 1)
        logit = math.log(relative_rank / (1 - relative_rank))
        logits.append(logit)
        if logit <= 0:
            below_or_equal += 1
    return {
        "method": "CSCV_SYMMETRIC_SHARPE_PER_PERIOD",
        "block_count": blocks,
        "block_size": block_size,
        "split_count": len(logits),
        "oos_rank_tie_split_count": rank_ties,
        "negative_or_zero_logit_count": below_or_equal,
        "pbo_fraction": below_or_equal / len(logits),
        "median_oos_rank_logit": statistics.median(logits),
        "note": "DIAGNOSTIC_CSCV_NOT_TEMPORAL_FORWARD_VALIDATION",
    }


def _dsr(series: list[list[float]], selected: int, trial_count: int) -> dict:
    sharpes = [_sharpe(values) for values in series]
    spread = statistics.stdev(sharpes)
    if not math.isfinite(spread) or spread <= 1e-15:
        raise OverfitEvidenceRefused("UNKNOWN_OR_ZERO_TRIAL_SHARPE_VARIANCE")
    inverse = NormalDist().inv_cdf
    # Per-period Sharpe throughout; deliberately not annualized.
    expected_max = spread * (
        (1 - _EULER_GAMMA) * inverse(1 - 1 / trial_count)
        + _EULER_GAMMA * inverse(1 - 1 / (trial_count * math.e))
    )
    observed = sharpes[selected]
    skew, kurtosis = _moments(series[selected])
    variance_factor = (
        1 - skew * observed + ((kurtosis - 1) / 4) * observed ** 2
    )
    if not math.isfinite(variance_factor) or variance_factor <= 1e-12:
        raise OverfitEvidenceRefused("INVALID_DSR_VARIANCE_FACTOR")
    z = (
        (observed - expected_max) * math.sqrt(len(series[selected]) - 1)
        / math.sqrt(variance_factor)
    )
    probability = NormalDist().cdf(z)
    if not math.isfinite(probability):
        raise OverfitEvidenceRefused("NONFINITE_DSR")
    return {
        "method": "BAILEY_LOPEZ_DE_PRADO_PER_PERIOD_DSR",
        "sample_count": len(series[selected]),
        "declared_complete_trial_count": trial_count,
        "observed_sharpe_per_period": observed,
        "cross_trial_sharpe_std": spread,
        "selected_skewness": skew,
        "selected_raw_kurtosis": kurtosis,
        "expected_maximum_null_sharpe": expected_max,
        "dsr_probability": probability,
        "note": "DIAGNOSTIC_ESTIMATE_NOT_A_PROBABILITY_OF_REAL_TRADING_PROFIT",
    }


def analyze_overfit_fixture(raw: bytes) -> dict:
    """Refuse incomplete/unbalanced, untrusted or holdout-crossing evidence."""
    if type(raw) is not bytes or not 1 <= len(raw) <= _MAX_BYTES:
        raise OverfitEvidenceRefused("RESEARCH_FILE_SIZE_BOUND")
    try:
        protocol = json.loads(
            raw, object_pairs_hook=_unique, parse_constant=_reject_constant
        )
    except OverfitEvidenceRefused:
        raise
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise OverfitEvidenceRefused("INVALID_RESEARCH_JSON") from exc
    if type(protocol) is not dict or set(protocol) != _KEYS:
        raise OverfitEvidenceRefused("RESEARCH_SCHEMA_MISMATCH")
    if type(protocol["schema_version"]) is not int or protocol["schema_version"] != 1:
        raise OverfitEvidenceRefused("RESEARCH_VERSION_MISMATCH")
    ident = protocol["study_id"]
    if type(ident) is not str or not _ID.fullmatch(ident):
        raise OverfitEvidenceRefused("INVALID_STUDY_ID")
    ids = protocol["candidate_ids"]
    if (type(ids) is not list or not 3 <= len(ids) <= _MAX_CANDIDATES
            or any(type(x) is not str or not _ID.fullmatch(x) for x in ids)
            or ids != sorted(set(ids))):
        raise OverfitEvidenceRefused("INVALID_OR_INCOMPLETE_CANDIDATE_INVENTORY")
    selected = protocol["selected_candidate_id"]
    if type(selected) is not str or selected not in ids:
        raise OverfitEvidenceRefused("SELECTED_CANDIDATE_NOT_IN_INVENTORY")
    n = protocol["declared_total_trials"]
    if (type(n) is not int or n != len(ids)
            or protocol["trial_inventory_complete"] is not True):
        raise OverfitEvidenceRefused("COMPLETE_EXPERIMENT_INVENTORY_REQUIRED")
    blocks = protocol["cscv_blocks"]
    if type(blocks) is not int or blocks not in (4, 6, 8, 10, 12):
        raise OverfitEvidenceRefused("INVALID_CSCV_BLOCK_COUNT")
    holdout_start = _utc(protocol["reserved_holdout_start_utc"])
    rows = protocol["rows"]
    if (type(rows) is not list or not blocks * 8 <= len(rows) <= _MAX_ROWS
            or len(rows) % blocks != 0):
        raise OverfitEvidenceRefused("INCOMPLETE_OR_UNBALANCED_CSCV_ROWS")
    series = [[] for _ in ids]
    prev_end = None
    width = None
    for row in rows:
        if type(row) is not dict or set(row) != _ROW_KEYS:
            raise OverfitEvidenceRefused("INVALID_RESEARCH_ROW")
        start = _utc(row["period_start_utc"])
        end = _utc(row["period_end_utc"])
        if end <= start or end > holdout_start:
            raise OverfitEvidenceRefused("HOLDOUT_OR_NONCAUSAL_TIME_BOUNDARY")
        if prev_end is not None and start != prev_end:
            raise OverfitEvidenceRefused("MISSING_OR_OVERLAPPING_TIME_BIN")
        duration = end - start
        if width is not None and duration != width:
            raise OverfitEvidenceRefused("UNEQUAL_RETURN_HORIZON")
        values = row["net_return_fraction"]
        if type(values) is not dict or set(values) != set(ids):
            raise OverfitEvidenceRefused("NONEXHAUSTIVE_TRIAL_RETURN_ROW")
        for i, key in enumerate(ids):
            series[i].append(_return(values[key]))
        prev_end, width = end, duration
    pbo = _cscv(series, blocks)
    dsr = _dsr(series, ids.index(selected), n)
    report = {
        "study_id": ident,
        "mode": "OFFLINE_FULL_MATRIX_OVERFIT_DIAGNOSTICS_ONLY",
        "matrix_sha256": hashlib.sha256(raw).hexdigest(),
        "selected_candidate_id": selected,
        "period_count": len(rows),
        "candidate_count": len(ids),
        "reserved_holdout_start_utc": holdout_start.isoformat(),
        "holdout_rows_loaded": 0,
        "trial_inventory_claim_not_independently_verified": True,
        "historical_source_authenticated": False,
        "selection_pre_registered_verified": False,
        "serial_correlation_adjusted": False,
        "strategy_retraining_performed": False,
        "trading_authorized": False,
        "readiness": "DESCRIPTIVE_ONLY_NOT_PROFITABILITY_PROOF",
        "pbo": pbo,
        "dsr": dsr,
    }
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False)
    report["report_sha256"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return report


__all__ = ["OverfitEvidenceRefused", "analyze_overfit_fixture"]
