"""Empirical Brooks outcome probability from real terminal signal history.

No rule-count confidence or invented setup probability is used. The conservative
probability is the Wilson lower bound of similar historical terminal outcomes.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from math import sqrt
from threading import Lock
from types import SimpleNamespace
from typing import Literal

import numpy as np
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.brooks_core.evidence_weighting import (
    RuleHistoricalReliability,
    summarize_candidate_evidence,
)
from app.modules.signal_automation.entities import (
    BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1,
    BROOKS_HP_STATISTICS_CONTRACT_ID,
    FINAL_BROOKS_HP_SEMANTIC_COHORT_ID,
    HP_COLD_START_BOOTSTRAP_POLICY_ID,
)
from app.modules.signal_automation.models import SignalAutomationMetadata, SignalRuleEvidence
from app.modules.signal_quality.models import (
    SignalQualityAssessment as SignalQualityAssessmentModel,
)
from app.modules.signals.models import Signal, SignalEvent, SignalTarget

_MIN_EXACT = 8
_MIN_FAMILY = 12
_MIN_BROAD = 20
_MAX_NEIGHBORS = 20
_Z95 = 1.959963984540054
_ECONOMIC_MINIMUM = 20
_BOOTSTRAP_RESAMPLES = 100_000
_BOOTSTRAP_VALID_MINIMUM = 0.95
_BOOTSTRAP_EPSILON = 1e-15
_BOOTSTRAP_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hp-realized-r")
_BOOTSTRAP_CACHE: OrderedDict[str, tuple[dict[str, float] | None, dict[str, object]]] = (
    OrderedDict()
)
_BOOTSTRAP_CACHE_LOCK = Lock()
_BOOTSTRAP_CACHE_MAXSIZE = 512
HistoricalProbabilityDataDomain = Literal["LEGACY_MIXED", "FUTURES_ONLY"]


@dataclass(frozen=True, slots=True)
class HistoricalCase:
    signal_id: int
    setup_type: str
    timeframe: str
    direction: str
    structure_quality: float
    context_quality: float
    entry_quality: float
    risk_feature: float
    outcome: int
    rule_ids: tuple[str, ...]
    semantic_cohort_id: str | None = None
    generation_mode: str | None = None
    bootstrap_policy_id: str | None = None
    economic_opportunity_id: str | None = None
    symbol: str | None = None
    realized_r: float | None = None
    payoff_input_fingerprint: str | None = None
    outcome_policy_id: str = "LEGACY_LATEST_TERMINAL_EVENT_V1"


@dataclass(frozen=True, slots=True)
class ProbabilityAssessment:
    calibrated: bool
    probability: float | None
    empirical_win_rate: float | None
    lower_bound: float | None
    upper_bound: float | None
    historical_reliability: float
    sample_size: int
    wins: int
    losses: int
    scope: str
    break_even_probability: float | None
    expected_value_r: float | None
    trader_equation_favorable: bool
    neighbor_signal_ids: tuple[int, ...] = ()
    semantic_cohort_id: str | None = None
    cohort_isolation_applied: bool = False
    compatible_case_count: int = 0
    required_sample_size: int = 0
    outcome_policy_id: str = "LEGACY_LATEST_TERMINAL_EVENT_V1"
    statistics_contract_id: str | None = None
    readiness_state: str = "UNBOOTSTRAPPED"
    structural_scope: str | None = None
    economic_scope: str | None = None
    structural_required_n: int = 0
    economic_required_n: int = _ECONOMIC_MINIMUM
    valid_realized_r_count: int = 0
    unknown_case_count: int = 0
    mean_realized_r: float | None = None
    median_realized_r: float | None = None
    ci95_lower_r: float | None = None
    ci95_upper_r: float | None = None
    bootstrap_valid_fraction: float | None = None
    history_case_set_hash: str | None = None
    positive_fraction: float | None = None
    positive_fraction_wilson_lower: float | None = None
    realized_r_statistical_confidence: float | None = None


def _stored_semantic_cohort_id(metadata: object) -> str | None:
    analysis = dict(getattr(metadata, "analysis_metadata", None) or {})
    value = analysis.get("hp_semantic_cohort_id")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _stored_bootstrap_policy_id(metadata: object) -> str | None:
    analysis = dict(getattr(metadata, "analysis_metadata", None) or {})
    raw = analysis.get("hp_cold_start_bootstrap")
    if not isinstance(raw, dict) or raw.get("bootstrap") is not True:
        return None
    value = raw.get("policy_id")
    return str(value).strip() if value is not None else None


def _stored_bootstrap_economic_opportunity_id(metadata: object) -> str | None:
    analysis = dict(getattr(metadata, "analysis_metadata", None) or {})
    raw = analysis.get("hp_cold_start_bootstrap")
    if not isinstance(raw, dict) or raw.get("bootstrap") is not True:
        return None
    value = raw.get("economic_opportunity_id")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _stored_live_economic_opportunity_id(quality_metadata: object) -> str | None:
    if not isinstance(quality_metadata, dict):
        return None
    breakdown = quality_metadata.get("risk_semantic_breakdown")
    if not isinstance(breakdown, dict):
        return None
    structural = breakdown.get("structural_validation")
    if not isinstance(structural, dict):
        return None
    value = structural.get("economic_opportunity_id")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _is_authorized_bootstrap_shadow(case: HistoricalCase) -> bool:
    return (
        case.generation_mode == "SHADOW"
        and case.semantic_cohort_id == FINAL_BROOKS_HP_SEMANTIC_COHORT_ID
        and case.bootstrap_policy_id == HP_COLD_START_BOOTSTRAP_POLICY_ID
        and bool(case.economic_opportunity_id)
    )


def _deduplicate_hp_economic_opportunities(
    cases: tuple[HistoricalCase, ...],
) -> tuple[HistoricalCase, ...]:
    """Count at most one final-cohort sample per economic opportunity.

    Selection is deterministic and outcome-neutral. A real LIVE observation
    precedes an authorized bootstrap SHADOW observation for the same opportunity.
    """
    passthrough: list[HistoricalCase] = []
    grouped: dict[tuple[str, str, str, str], list[HistoricalCase]] = {}
    for case in cases:
        if (
            case.semantic_cohort_id == FINAL_BROOKS_HP_SEMANTIC_COHORT_ID
            and case.economic_opportunity_id
            and (case.generation_mode == "LIVE" or _is_authorized_bootstrap_shadow(case))
        ):
            grouped.setdefault(
                (
                    case.semantic_cohort_id,
                    str(case.symbol or "").strip().upper(),
                    str(case.timeframe or "").strip(),
                    case.economic_opportunity_id,
                ),
                [],
            ).append(case)
        else:
            passthrough.append(case)

    selected = [
        min(
            group,
            key=lambda item: (
                0 if item.generation_mode == "LIVE" else 1,
                item.signal_id,
            ),
        )
        for group in grouped.values()
    ]
    return tuple(sorted((*passthrough, *selected), key=lambda item: item.signal_id))


def _candidate_semantic_cohort_id(candidate: object | None) -> str | None:
    if candidate is None:
        return None
    value = getattr(candidate, "semantic_cohort_id", None)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _candidate_symbol(candidate: object | None) -> str | None:
    if candidate is None:
        return None
    value = getattr(candidate, "symbol", None)
    if value is None:
        return None
    text = str(value).strip().upper()
    return text or None


def _setup_family(setup_type: str | None) -> str:
    value = str(setup_type or "UNKNOWN").upper()
    for suffix in ("_LONG", "_SHORT"):
        if value.endswith(suffix):
            value = value[: -len(suffix)]
    for prefix in (
        "BREAKOUT_PULLBACK",
        "FAILED_BREAKOUT",
        "FAILED_FAILURE",
        "BREAKOUT",
        "PARABOLIC_WEDGE",
        "MICRO_WEDGE",
        "WEDGE",
        "DOUBLE_TOP",
        "DOUBLE_BOTTOM",
        "MAJOR_TREND_REVERSAL",
        "FINAL_FLAG",
        "CLIMACTIC_REVERSAL",
        "TRADING_RANGE_FADE",
        "H1",
        "H2",
        "H3",
        "H4",
        "L1",
        "L2",
        "L3",
        "L4",
    ):
        if value.startswith(prefix):
            return prefix
    return value


def historical_probability_sample_accounting(
    cases: tuple[HistoricalCase, ...],
    candidate: object,
) -> dict[str, int]:
    """Inspect same-cohort eligible sample counts without changing HP selection."""
    cohort = _candidate_semantic_cohort_id(candidate)
    symbol = _candidate_symbol(candidate)
    deduplicated = _deduplicate_hp_economic_opportunities(cases)
    compatible = tuple(
        case
        for case in deduplicated
        if (cohort is None or case.semantic_cohort_id == cohort)
        and (symbol is None or str(case.symbol or "").strip().upper() == symbol)
    )
    setup = str(getattr(candidate, "setup_type", "") or "UNKNOWN")
    timeframe = str(getattr(candidate, "timeframe", "") or "")
    direction = str(getattr(candidate, "direction", "") or "").upper()
    family = _setup_family(setup)
    return {
        "live_terminal": sum(case.generation_mode == "LIVE" for case in compatible),
        "bootstrap_shadow_terminal": sum(
            case.generation_mode == "SHADOW"
            and case.bootstrap_policy_id == HP_COLD_START_BOOTSTRAP_POLICY_ID
            for case in compatible
        ),
        "total_eligible_same_cohort": len(compatible),
        "setup_timeframe": sum(
            case.setup_type == setup and case.timeframe == timeframe for case in compatible
        ),
        "setup_all_timeframes": sum(case.setup_type == setup for case in compatible),
        "family_timeframe": sum(
            _setup_family(case.setup_type) == family and case.timeframe == timeframe
            for case in compatible
        ),
        "family_all_timeframes": sum(
            _setup_family(case.setup_type) == family for case in compatible
        ),
        "direction_timeframe": sum(
            case.direction == direction and case.timeframe == timeframe for case in compatible
        ),
        "direction_all_timeframes": sum(case.direction == direction for case in compatible),
    }


def _realized_r(signal: object, metadata: object) -> tuple[float | None, str | None]:
    analysis = dict(getattr(metadata, "analysis_metadata", None) or {})
    plan = analysis.get("trade_management_v6")
    if not isinstance(plan, dict):
        return None, None
    initial_stop = plan.get("initial_stop_loss")
    profit_loss = getattr(signal, "profit_loss", None)
    entry = getattr(signal, "entry_price", None)
    leverage = getattr(signal, "leverage", None)
    try:
        entry_d = Decimal(str(entry))
        stop_d = Decimal(str(initial_stop))
        pnl_d = Decimal(str(profit_loss))
        leverage_d = Decimal(str(leverage))
        risk_pct = abs(entry_d - stop_d) / entry_d * Decimal("100") * leverage_d
        if risk_pct <= 0:
            return None, None
        realized = pnl_d / risk_pct
    except (InvalidOperation, TypeError, ValueError, ZeroDivisionError):
        return None, None
    if not math.isfinite(float(realized)):
        return None, None
    payload = {
        "economic_opportunity_id": (_stored_bootstrap_economic_opportunity_id(metadata) or ""),
        "signal_id": int(signal.id),
        "profit_loss": str(profit_loss),
        "entry_price": str(entry),
        "initial_stop_loss": str(initial_stop),
        "leverage": str(leverage),
        "tm_policy_version": str(plan.get("policy_version") or ""),
    }
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return float(realized), fingerprint


def _bootstrap_seed_material(
    *,
    semantic_cohort_id: str | None,
    symbol: str | None,
    scope: str,
    scope_key: str,
    case_fingerprints: tuple[str, ...],
) -> str:
    return "|".join(
        (
            BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1,
            BROOKS_HP_STATISTICS_CONTRACT_ID,
            str(semantic_cohort_id or ""),
            str(symbol or "").upper(),
            scope,
            scope_key,
            *case_fingerprints,
        )
    )


def _finite_sample_one_sided_bootstrap_support(
    t_observed: float,
    t_star: np.ndarray,
) -> tuple[float, float, int, int]:
    """Return finite-sample corrected support for mean(realized_r) > 0R.

    The frozen convention counts ties in the empirical upper tail:
    k = count(t_star >= t_observed), p = (k + 1) / (B_valid + 1),
    and statistical confidence = 1 - p.  The +1 correction prevents
    reporting a zero Monte-Carlo p-value from a finite resample set.
    """
    if not math.isfinite(t_observed):
        raise ValueError("t_observed must be finite")
    values = np.asarray(t_star, dtype=np.float64)
    if values.ndim != 1 or values.size == 0 or not np.isfinite(values).all():
        raise ValueError("t_star must be a non-empty finite vector")
    valid = int(values.size)
    upper_tail_count = int(np.count_nonzero(values >= t_observed))
    p_one_sided = (upper_tail_count + 1) / (valid + 1)
    confidence = 1.0 - p_one_sided
    return confidence, p_one_sided, upper_tail_count, valid


def _bootstrap_t(
    values: tuple[float, ...],
    cache_key: str,
) -> tuple[dict[str, float] | None, dict[str, object]]:
    with _BOOTSTRAP_CACHE_LOCK:
        cached = _BOOTSTRAP_CACHE.get(cache_key)
        if cached is not None:
            _BOOTSTRAP_CACHE.move_to_end(cache_key)
            return cached
    x = np.asarray(values, dtype=np.float64)
    n = len(x)
    mean = float(x.mean())
    sample_se = float(x.std(ddof=1) / math.sqrt(n))
    if not math.isfinite(sample_se) or sample_se <= _BOOTSTRAP_EPSILON:
        result = (None, {"invalid_reason": "ZERO_OR_INVALID_SE", "valid_fraction": 0.0})
    else:
        seed = int.from_bytes(hashlib.sha256(cache_key.encode()).digest()[:8], "big")
        rng = np.random.default_rng(seed)
        chunks: list[np.ndarray] = []
        valid = 0
        for start in range(0, _BOOTSTRAP_RESAMPLES, 2_000):
            count = min(2_000, _BOOTSTRAP_RESAMPLES - start)
            samples = x[rng.integers(0, n, size=(count, n))]
            means = samples.mean(axis=1)
            standard_errors = samples.std(axis=1, ddof=1) / math.sqrt(n)
            mask = np.isfinite(standard_errors) & (standard_errors > _BOOTSTRAP_EPSILON)
            valid += int(mask.sum())
            if mask.any():
                chunks.append((means[mask] - mean) / standard_errors[mask])
        valid_fraction = valid / _BOOTSTRAP_RESAMPLES
        if valid_fraction < _BOOTSTRAP_VALID_MINIMUM:
            result = (
                None,
                {
                    "invalid_reason": "TOO_MANY_DEGENERATE_RESAMPLES",
                    "valid_fraction": valid_fraction,
                },
            )
        else:
            statistics = np.concatenate(chunks)
            q025, q975 = np.quantile(statistics, (0.025, 0.975))
            t_observed = mean / sample_se
            (
                statistical_confidence,
                p_one_sided,
                upper_tail_count,
                valid_bootstrap_count,
            ) = _finite_sample_one_sided_bootstrap_support(t_observed, statistics)
            result = (
                {
                    "mean": mean,
                    "median": float(np.median(x)),
                    "lower": mean - float(q975) * sample_se,
                    "upper": mean - float(q025) * sample_se,
                    "statistical_confidence": statistical_confidence,
                },
                {
                    "valid_fraction": valid_fraction,
                    "seed": seed,
                    "t_observed": t_observed,
                    "p_one_sided": p_one_sided,
                    "upper_tail_count": upper_tail_count,
                    "valid_bootstrap_count": valid_bootstrap_count,
                },
            )
    with _BOOTSTRAP_CACHE_LOCK:
        _BOOTSTRAP_CACHE[cache_key] = result
        _BOOTSTRAP_CACHE.move_to_end(cache_key)
        while len(_BOOTSTRAP_CACHE) > _BOOTSTRAP_CACHE_MAXSIZE:
            _BOOTSTRAP_CACHE.popitem(last=False)
    return result


def _risk_feature(entry, stop, target) -> float:
    risk = abs(float(entry) - float(stop))
    reward = abs(float(target) - float(entry))
    if risk <= 0 or reward <= 0:
        return 0.0
    rr = reward / risk
    return round(100.0 * rr / (1.0 + rr), 4)


def _current_trade_math(candidate: object) -> tuple[float | None, float | None]:
    entry = getattr(candidate, "entry_price", None)
    stop = getattr(candidate, "stop_loss", None)
    targets = tuple(getattr(candidate, "targets", ()) or ())
    if entry is None or stop is None or not targets:
        return None, None
    risk = abs(float(entry) - float(stop))
    reward = abs(float(targets[0]) - float(entry))
    if risk <= 0 or reward <= 0:
        return None, None
    return risk, reward


def _wilson(wins: int, total: int) -> tuple[float, float, float]:
    if total <= 0:
        return 0.0, 0.0, 1.0
    p = wins / total
    z2 = _Z95 * _Z95
    denominator = 1.0 + z2 / total
    center = (p + z2 / (2.0 * total)) / denominator
    margin = _Z95 * sqrt((p * (1.0 - p) / total) + z2 / (4.0 * total * total)) / denominator
    return p, max(0.0, center - margin), min(1.0, center + margin)


def _distance(case: HistoricalCase, features: tuple[float, float, float, float]) -> float:
    historical = (
        case.structure_quality,
        case.context_quality,
        case.entry_quality,
        case.risk_feature,
    )
    return sum(abs(a - b) / 100.0 for a, b in zip(historical, features, strict=True)) / 4.0


class HistoricalProbabilityRepository:
    def __init__(
        self,
        session: AsyncSession,
        *,
        data_domain: HistoricalProbabilityDataDomain = "LEGACY_MIXED",
        semantic_cohort_id: str | None = None,
        symbol: str | None = None,
    ) -> None:
        if data_domain not in {"LEGACY_MIXED", "FUTURES_ONLY"}:
            raise ValueError("unsupported Historical Probability data domain")
        self.session = session
        self.data_domain = data_domain
        self.semantic_cohort_id = semantic_cohort_id
        self.symbol = str(symbol).strip().upper() if symbol is not None else None

    async def load_cases(self) -> tuple[HistoricalCase, ...]:
        ranked = (
            select(
                SignalEvent.signal_id.label("signal_id"),
                SignalEvent.event_type.label("event_type"),
                func.row_number()
                .over(
                    partition_by=SignalEvent.signal_id,
                    order_by=(SignalEvent.created_at.desc(), SignalEvent.id.desc()),
                )
                .label("outcome_rank"),
            )
            .where(SignalEvent.event_type.in_(("TARGET_HIT", "STOP_HIT")))
            .subquery()
        )
        bootstrap = SignalAutomationMetadata.analysis_metadata["hp_cold_start_bootstrap"]
        performance_eligible = or_(
            SignalAutomationMetadata.counts_toward_performance.is_(True),
            and_(
                SignalAutomationMetadata.counts_toward_performance.is_(False),
                SignalAutomationMetadata.generation_mode == "SHADOW",
                bootstrap["bootstrap"].astext == "true",
                bootstrap["policy_id"].astext == HP_COLD_START_BOOTSTRAP_POLICY_ID,
                bootstrap["state"].astext == "BOOTSTRAP_TERMINAL_ELIGIBLE",
                bootstrap["hp_eligible"].astext == "true",
                bootstrap["economic_opportunity_id"].astext.is_not(None),
                bootstrap["economic_opportunity_id"].astext != "",
            ),
        )
        eligibility = [
            ranked.c.outcome_rank == 1,
            SignalAutomationMetadata.producer == "BROOKS",
            performance_eligible,
        ]
        if self.semantic_cohort_id is not None:
            eligibility.append(
                SignalAutomationMetadata.analysis_metadata["hp_semantic_cohort_id"].astext
                == self.semantic_cohort_id
            )
        if self.symbol is not None:
            eligibility.append(Signal.symbol == self.symbol)
        if self.data_domain == "FUTURES_ONLY":
            eligibility.extend(
                (
                    SignalAutomationMetadata.exchange == "binance",
                    SignalAutomationMetadata.market_type == "futures",
                )
            )
        statement = (
            select(
                Signal,
                SignalAutomationMetadata,
                ranked.c.event_type,
                SignalQualityAssessmentModel.extra_metadata.label("quality_metadata"),
            )
            .join(SignalAutomationMetadata, SignalAutomationMetadata.signal_id == Signal.id)
            .join(ranked, ranked.c.signal_id == Signal.id)
            .outerjoin(
                SignalQualityAssessmentModel,
                SignalQualityAssessmentModel.signal_id == Signal.id,
            )
            .where(*eligibility)
        )
        rows = tuple((await self.session.execute(statement)).all())
        if not rows:
            return ()
        signal_ids = tuple(row[0].id for row in rows)
        evidence_rows = tuple(
            (
                await self.session.scalars(
                    select(SignalRuleEvidence)
                    .where(SignalRuleEvidence.signal_id.in_(signal_ids))
                    .order_by(SignalRuleEvidence.signal_id, SignalRuleEvidence.ordinal)
                )
            ).all()
        )
        target_rows = tuple(
            (
                await self.session.scalars(
                    select(SignalTarget).where(
                        SignalTarget.signal_id.in_(signal_ids),
                        SignalTarget.target_number == 1,
                    )
                )
            ).all()
        )
        evidence_by_signal: dict[int, list[SignalRuleEvidence]] = {}
        for item in evidence_rows:
            evidence_by_signal.setdefault(item.signal_id, []).append(item)
        target_by_signal = {item.signal_id: item for item in target_rows}

        cases: list[HistoricalCase] = []
        for signal, metadata, event_type, quality_metadata in rows:
            target = target_by_signal.get(signal.id)
            if target is None:
                continue
            realized_r, payoff_fingerprint = _realized_r(signal, metadata)
            candidate = SimpleNamespace(
                setup_type=metadata.setup_type,
                direction=signal.direction,
                rule_evidence=tuple(evidence_by_signal.get(signal.id, ())),
            )
            summary = summarize_candidate_evidence(candidate)
            cases.append(
                HistoricalCase(
                    signal_id=signal.id,
                    setup_type=metadata.setup_type or "UNKNOWN",
                    timeframe=metadata.timeframe,
                    direction=signal.direction,
                    structure_quality=summary.structure_quality,
                    context_quality=summary.context_quality,
                    entry_quality=summary.entry_quality,
                    risk_feature=_risk_feature(
                        signal.entry_price, signal.stop_loss, target.target_price
                    ),
                    outcome=1 if event_type == "TARGET_HIT" else 0,
                    rule_ids=summary.selected_rule_ids,
                    semantic_cohort_id=_stored_semantic_cohort_id(metadata),
                    generation_mode=metadata.generation_mode,
                    bootstrap_policy_id=_stored_bootstrap_policy_id(metadata),
                    economic_opportunity_id=(
                        _stored_bootstrap_economic_opportunity_id(metadata)
                        if metadata.generation_mode == "SHADOW"
                        else _stored_live_economic_opportunity_id(quality_metadata)
                        if metadata.generation_mode == "LIVE"
                        else None
                    ),
                    symbol=signal.symbol,
                    realized_r=realized_r,
                    payoff_input_fingerprint=payoff_fingerprint,
                    outcome_policy_id=BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1,
                )
            )
        return _deduplicate_hp_economic_opportunities(tuple(cases))


class HistoricalProbabilityEngine:
    def __init__(self, cases: tuple[HistoricalCase, ...]) -> None:
        self.cases = _deduplicate_hp_economic_opportunities(cases)

    def _assess_legacy(self, candidate: object) -> ProbabilityAssessment:
        summary = summarize_candidate_evidence(candidate)
        targets = tuple(getattr(candidate, "targets", ()) or ())
        risk_feature = (
            _risk_feature(candidate.entry_price, candidate.stop_loss, targets[0])
            if targets
            else 0.0
        )
        features = (
            summary.structure_quality,
            summary.context_quality,
            summary.entry_quality,
            risk_feature,
        )
        setup = str(getattr(candidate, "setup_type", "") or "UNKNOWN")
        timeframe = str(getattr(candidate, "timeframe", "") or "")
        direction = str(getattr(candidate, "direction", "") or "").upper()
        family = _setup_family(setup)
        cohort = _candidate_semantic_cohort_id(candidate)
        symbol = _candidate_symbol(candidate)
        cases = tuple(
            x
            for x in self.cases
            if (cohort is None or x.semantic_cohort_id == cohort)
            and (symbol is None or str(x.symbol or "").strip().upper() == symbol)
        )
        levels = (
            (
                "SETUP_TIMEFRAME",
                _MIN_EXACT,
                tuple(x for x in cases if x.setup_type == setup and x.timeframe == timeframe),
            ),
            ("SETUP_ALL_TIMEFRAMES", _MIN_EXACT, tuple(x for x in cases if x.setup_type == setup)),
            (
                "FAMILY_TIMEFRAME",
                _MIN_FAMILY,
                tuple(
                    x
                    for x in cases
                    if _setup_family(x.setup_type) == family and x.timeframe == timeframe
                ),
            ),
            (
                "FAMILY_ALL_TIMEFRAMES",
                _MIN_FAMILY,
                tuple(x for x in cases if _setup_family(x.setup_type) == family),
            ),
            (
                "DIRECTION_TIMEFRAME",
                _MIN_BROAD,
                tuple(x for x in cases if x.direction == direction and x.timeframe == timeframe),
            ),
            (
                "DIRECTION_ALL_TIMEFRAMES",
                _MIN_BROAD,
                tuple(x for x in cases if x.direction == direction),
            ),
        )
        selected = next((x for x in levels if len(x[2]) >= x[1]), levels[-1])
        scope, minimum, pool = selected
        if len(pool) < minimum:
            return self._uncalibrated(
                candidate,
                scope=f"{scope}:INSUFFICIENT_HISTORY",
                semantic_cohort_id=cohort,
                cohort_isolation_applied=cohort is not None,
                compatible_case_count=len(pool),
                required_sample_size=minimum,
            )
        neighbors = tuple(
            sorted(pool, key=lambda x: (_distance(x, features), x.signal_id))[:_MAX_NEIGHBORS]
        )
        wins = sum(x.outcome for x in neighbors)
        empirical, lower, upper = _wilson(wins, len(neighbors))
        risk, reward = _current_trade_math(candidate)
        break_even = risk / (risk + reward) if risk and reward else None
        expected = lower * reward - (1.0 - lower) * risk if risk and reward else None
        return ProbabilityAssessment(
            calibrated=True,
            probability=round(lower, 6),
            empirical_win_rate=round(empirical, 6),
            lower_bound=round(lower, 6),
            upper_bound=round(upper, 6),
            historical_reliability=round(max(0.0, 1.0 - (upper - lower)), 6),
            sample_size=len(neighbors),
            wins=wins,
            losses=len(neighbors) - wins,
            scope=scope,
            break_even_probability=round(break_even, 6) if break_even is not None else None,
            expected_value_r=round(expected / risk, 6) if expected is not None and risk else None,
            trader_equation_favorable=bool(expected is not None and expected > 0),
            neighbor_signal_ids=tuple(x.signal_id for x in neighbors),
            semantic_cohort_id=cohort,
            cohort_isolation_applied=cohort is not None,
            compatible_case_count=len(pool),
            required_sample_size=minimum,
        )

    async def assess_async(self, candidate: object) -> ProbabilityAssessment:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_BOOTSTRAP_EXECUTOR, self.assess, candidate)

    def assess(self, candidate: object) -> ProbabilityAssessment:
        if self.cases and all(
            case.outcome_policy_id == "LEGACY_LATEST_TERMINAL_EVENT_V1" for case in self.cases
        ):
            return self._assess_legacy(candidate)
        setup = str(getattr(candidate, "setup_type", "") or "UNKNOWN")
        timeframe = str(getattr(candidate, "timeframe", "") or "")
        direction = str(getattr(candidate, "direction", "") or "").upper()
        family = _setup_family(setup)
        semantic_cohort_id = _candidate_semantic_cohort_id(candidate)
        symbol = _candidate_symbol(candidate)
        isolated = semantic_cohort_id is not None
        compatible = tuple(
            case
            for case in self.cases
            if (not isolated or case.semantic_cohort_id == semantic_cohort_id)
            and (symbol is None or str(case.symbol or "").strip().upper() == symbol)
        )
        levels = (
            (
                "SETUP_TIMEFRAME",
                _MIN_EXACT,
                f"{setup}|{timeframe}",
                tuple(x for x in compatible if x.setup_type == setup and x.timeframe == timeframe),
            ),
            (
                "SETUP_ALL_TIMEFRAMES",
                _MIN_EXACT,
                setup,
                tuple(x for x in compatible if x.setup_type == setup),
            ),
            (
                "FAMILY_TIMEFRAME",
                _MIN_FAMILY,
                f"{family}|{timeframe}",
                tuple(
                    x
                    for x in compatible
                    if _setup_family(x.setup_type) == family and x.timeframe == timeframe
                ),
            ),
            (
                "FAMILY_ALL_TIMEFRAMES",
                _MIN_FAMILY,
                family,
                tuple(x for x in compatible if _setup_family(x.setup_type) == family),
            ),
            (
                "DIRECTION_TIMEFRAME",
                _MIN_BROAD,
                f"{direction}|{timeframe}",
                tuple(
                    x for x in compatible if x.direction == direction and x.timeframe == timeframe
                ),
            ),
            (
                "DIRECTION_ALL_TIMEFRAMES",
                _MIN_BROAD,
                direction,
                tuple(x for x in compatible if x.direction == direction),
            ),
        )
        structural_scope = levels[-1][0]
        structural_required = levels[-1][1]
        last_valid = 0
        last_unknown = 0
        controlling = None
        structural_found = False
        for scope, structural_minimum, scope_key, pool in levels:
            if len(pool) < structural_minimum:
                continue
            if not structural_found:
                structural_scope = scope
                structural_required = structural_minimum
                structural_found = True
            valid = tuple(
                x for x in pool if x.realized_r is not None and x.payoff_input_fingerprint
            )
            last_valid = len(valid)
            last_unknown = len(pool) - len(valid)
            if len(valid) >= _ECONOMIC_MINIMUM:
                controlling = (scope, scope_key, pool, valid)
                break
        if controlling is None:
            broad = levels[-1][3]
            valid = tuple(x for x in broad if x.realized_r is not None)
            state = "UNBOOTSTRAPPED" if not valid else "MATURING"
            return self._uncalibrated(
                candidate,
                scope=f"{structural_scope}:STATISTICALLY_UNREADY",
                semantic_cohort_id=semantic_cohort_id,
                cohort_isolation_applied=isolated,
                compatible_case_count=len(broad),
                required_sample_size=_ECONOMIC_MINIMUM,
                readiness_state=state,
                structural_scope=structural_scope,
                structural_required_n=structural_required,
                valid_realized_r_count=max(last_valid, len(valid)),
                unknown_case_count=max(last_unknown, len(broad) - len(valid)),
                outcome_policy_id=BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1,
                statistics_contract_id=BROOKS_HP_STATISTICS_CONTRACT_ID,
            )
        scope, scope_key, pool, valid = controlling
        ordered = tuple(
            sorted(valid, key=lambda x: (str(x.economic_opportunity_id or ""), x.signal_id))
        )
        fingerprints = tuple(str(x.payoff_input_fingerprint) for x in ordered)
        material = _bootstrap_seed_material(
            semantic_cohort_id=semantic_cohort_id,
            symbol=symbol,
            scope=scope,
            scope_key=scope_key,
            case_fingerprints=fingerprints,
        )
        case_hash = hashlib.sha256("|".join(fingerprints).encode()).hexdigest()
        stats, diagnostics = _bootstrap_t(
            tuple(float(x.realized_r) for x in ordered if x.realized_r is not None),
            material,
        )
        wins = sum(x.outcome for x in pool)
        empirical, lower, upper = _wilson(wins, len(pool))
        positive = sum(float(x.realized_r) > 0 for x in ordered)
        _, positive_lower, _ = _wilson(positive, len(ordered))
        risk, reward = _current_trade_math(candidate)
        break_even = risk / (risk + reward) if risk and reward else None
        legacy_expected = lower * reward - (1.0 - lower) * risk if risk and reward else None
        legacy_favorable = bool(legacy_expected is not None and legacy_expected > 0.0)
        if stats is None:
            state = "STATISTICAL_ASSESSMENT_INVALID"
        else:
            state = (
                "CALIBRATED_FAVORABLE"
                if stats["lower"] > 0.0
                else "CALIBRATED_UNFAVORABLE"
            )
        return ProbabilityAssessment(
            calibrated=True,
            probability=round(lower, 6),
            empirical_win_rate=round(empirical, 6),
            lower_bound=round(lower, 6),
            upper_bound=round(upper, 6),
            historical_reliability=round(max(0.0, 1.0 - (upper - lower)), 6),
            sample_size=len(pool),
            wins=wins,
            losses=len(pool) - wins,
            scope=scope,
            break_even_probability=round(break_even, 6) if break_even is not None else None,
            expected_value_r=(
                round(legacy_expected / risk, 6)
                if legacy_expected is not None and risk
                else None
            ),
            trader_equation_favorable=legacy_favorable,
            neighbor_signal_ids=tuple(x.signal_id for x in ordered),
            semantic_cohort_id=semantic_cohort_id,
            cohort_isolation_applied=isolated,
            compatible_case_count=len(pool),
            required_sample_size=_ECONOMIC_MINIMUM,
            outcome_policy_id=BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1,
            statistics_contract_id=BROOKS_HP_STATISTICS_CONTRACT_ID,
            readiness_state=state,
            structural_scope=scope,
            economic_scope=scope,
            structural_required_n=next(x[1] for x in levels if x[0] == scope),
            valid_realized_r_count=len(ordered),
            unknown_case_count=len(pool) - len(ordered),
            mean_realized_r=(stats["mean"] if stats else None),
            median_realized_r=(stats["median"] if stats else None),
            ci95_lower_r=(stats["lower"] if stats else None),
            ci95_upper_r=(stats["upper"] if stats else None),
            bootstrap_valid_fraction=float(diagnostics.get("valid_fraction", 0.0)),
            history_case_set_hash=case_hash,
            positive_fraction=positive / len(ordered),
            positive_fraction_wilson_lower=positive_lower,
            realized_r_statistical_confidence=(
                stats["statistical_confidence"] if stats else None
            ),
        )

    @staticmethod
    def _uncalibrated(
        candidate: object,
        *,
        scope: str,
        semantic_cohort_id: str | None = None,
        cohort_isolation_applied: bool = False,
        compatible_case_count: int = 0,
        required_sample_size: int = 0,
        readiness_state: str = "UNBOOTSTRAPPED",
        structural_scope: str | None = None,
        structural_required_n: int = 0,
        valid_realized_r_count: int = 0,
        unknown_case_count: int = 0,
        outcome_policy_id: str = "LEGACY_LATEST_TERMINAL_EVENT_V1",
        statistics_contract_id: str | None = None,
    ) -> ProbabilityAssessment:
        return ProbabilityAssessment(
            calibrated=False,
            probability=None,
            empirical_win_rate=None,
            lower_bound=None,
            upper_bound=None,
            historical_reliability=0.0,
            sample_size=0,
            wins=0,
            losses=0,
            scope=scope,
            break_even_probability=None,
            expected_value_r=None,
            trader_equation_favorable=False,
            semantic_cohort_id=semantic_cohort_id,
            cohort_isolation_applied=cohort_isolation_applied,
            compatible_case_count=compatible_case_count,
            required_sample_size=required_sample_size,
            outcome_policy_id=outcome_policy_id,
            statistics_contract_id=statistics_contract_id,
            readiness_state=readiness_state,
            structural_scope=structural_scope,
            structural_required_n=structural_required_n,
            valid_realized_r_count=valid_realized_r_count,
            unknown_case_count=unknown_case_count,
        )

    def rule_reliability(self) -> tuple[RuleHistoricalReliability, ...]:
        by_rule: dict[str, list[int]] = {}
        for case in self.cases:
            for rule_id in case.rule_ids:
                by_rule.setdefault(rule_id, []).append(case.outcome)
        result: list[RuleHistoricalReliability] = []
        for rule_id, outcomes in sorted(by_rule.items()):
            wins = sum(outcomes)
            sample = len(outcomes)
            losses = sample - wins
            reliability = wins / sample if sample >= _MIN_EXACT else None
            result.append(
                RuleHistoricalReliability(
                    rule_id=rule_id,
                    sample_size=sample,
                    wins=wins,
                    losses=losses,
                    reliability=(round(reliability, 6) if reliability is not None else None),
                    failure_probability=(
                        round(1.0 - reliability, 6) if reliability is not None else None
                    ),
                    historical_importance=sample,
                )
            )
        return tuple(result)


async def load_probability_engine(
    session: AsyncSession,
    *,
    data_domain: HistoricalProbabilityDataDomain = "LEGACY_MIXED",
    candidate: object | None = None,
) -> HistoricalProbabilityEngine:
    semantic_cohort_id = _candidate_semantic_cohort_id(candidate)
    symbol = _candidate_symbol(candidate)
    cases = await HistoricalProbabilityRepository(
        session,
        data_domain=data_domain,
        semantic_cohort_id=semantic_cohort_id,
        symbol=symbol,
    ).load_cases()
    return HistoricalProbabilityEngine(cases)
