from __future__ import annotations

from typing import Any

from app.modules.brooks_core.candidate_scoring import score_candidate
from app.modules.brooks_core.market_context import build_market_context
from app.modules.signal_automation.entities import (
    BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1,
)
from app.modules.signal_intelligence.entities import SignalQualityAssessment
from app.modules.signal_intelligence.probability import ProbabilityAssessment
from app.modules.signal_intelligence.scoring import SignalScoringEngine


class SignalIntelligenceService:
    """Compose Brooks quality dimensions without inventing probability."""

    def __init__(self) -> None:
        self.scoring = SignalScoringEngine()

    def evaluate(
        self,
        candidate: Any,
        ai_score: float,
        risk_score: float,
        council_confidence: float = 0.0,
        probability: ProbabilityAssessment | None = None,
    ) -> SignalQualityAssessment:
        snapshot = getattr(candidate, "snapshot", None)
        market_context = build_market_context(snapshot) if snapshot is not None else None
        quality = score_candidate(
            candidate,
            risk_score=risk_score,
            market_context=market_context,
        )
        score = quality.final_score
        grade = self.scoring.grade(score)
        calibrated = probability is not None and probability.calibrated
        outcome_policy_id = probability.outcome_policy_id if probability is not None else None
        realized_r_policy = (
            outcome_policy_id == BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1
        )
        legacy_policy = outcome_policy_id == "LEGACY_LATEST_TERMINAL_EVENT_V1"
        unknown_policy = probability is not None and not (realized_r_policy or legacy_policy)
        confidence = (
            float(probability.probability)
            if calibrated and probability is not None and probability.probability is not None
            else 0.0
        )
        major_conflicts = tuple(item for item in quality.conflicts if item.severity == "MAJOR")

        legacy_probability_available = bool(
            probability is not None
            and probability.probability is not None
            and probability.break_even_probability is not None
        )
        if legacy_policy:
            probability_calibrated_metadata: bool | None = calibrated
            minimum_probability_met: bool | None = bool(
                calibrated
                and legacy_probability_available
                and probability is not None
                and probability.probability >= probability.break_even_probability
            )
        elif realized_r_policy:
            probability_calibrated_metadata = True if probability.probability is not None else None
            minimum_probability_met = (
                bool(probability.probability >= probability.break_even_probability)
                if legacy_probability_available
                else None
            )
        else:
            probability_calibrated_metadata = None
            minimum_probability_met = None

        if realized_r_policy:
            hp_economic_condition = probability.readiness_state == "CALIBRATED_FAVORABLE"
        elif legacy_policy:
            hp_economic_condition = bool(
                minimum_probability_met and probability.trader_equation_favorable
            )
        else:
            hp_economic_condition = False

        approved = bool(
            hp_economic_condition
            and not unknown_policy
            and not major_conflicts
            and quality.structure_quality > 0
            and quality.context_quality > 0
            and quality.risk_quality > 0
        )

        context_metadata: dict[str, object] = {}
        if market_context is not None:
            context_metadata = {
                "market_regime": market_context.regime,
                "always_in": market_context.always_in,
                "trend_strength": str(market_context.trend_strength),
                "trading_range_probability": str(market_context.trading_range_probability),
                "volatility_ratio": str(market_context.volatility_ratio),
                "volatility_state": market_context.volatility_state,
                "compression_expansion_ratio": str(market_context.compression_expansion_ratio),
                "channel_quality": market_context.channel_quality,
                "channel_direction": market_context.channel_direction,
                "swing_quality": str(market_context.swing_quality),
                "location": market_context.location,
                "support": str(market_context.support)
                if market_context.support is not None
                else None,
                "resistance": str(market_context.resistance)
                if market_context.resistance is not None
                else None,
                "measured_move_probability": str(market_context.measured_move_probability),
                "measured_move_failure": market_context.measured_move_failure,
                "higher_timeframe": market_context.higher_timeframe,
                "higher_timeframe_regime": market_context.higher_timeframe_regime,
                "timeframe_alignment": market_context.timeframe_alignment,
                "higher_timeframe_agreement": str(market_context.higher_timeframe_agreement),
                "context_probability_semantics": market_context.probability_semantics,
            }

        probability_metadata: dict[str, object] = {
            "probability_calibrated": probability_calibrated_metadata,
            "probability": probability.probability if probability is not None else None,
            "minimum_probability_met": minimum_probability_met,
            "hp_policy_routing_status": (
                "REALIZED_R_POLICY"
                if realized_r_policy
                else "LEGACY_POLICY"
                if legacy_policy
                else "UNKNOWN_POLICY_FAIL_CLOSED"
                if unknown_policy
                else "NO_PROBABILITY_ASSESSMENT"
            ),
            "hp_policy_rejection_reason": (
                "UNKNOWN_HP_OUTCOME_POLICY" if unknown_policy else None
            ),
        }
        if probability is not None:
            probability_metadata.update(
                {
                    "empirical_win_rate": probability.empirical_win_rate,
                    "probability_lower_bound": probability.lower_bound,
                    "probability_upper_bound": probability.upper_bound,
                    "historical_reliability": probability.historical_reliability,
                    "historical_sample_size": probability.sample_size,
                    "historical_wins": probability.wins,
                    "historical_losses": probability.losses,
                    "probability_scope": probability.scope,
                    "break_even_probability": probability.break_even_probability,
                    "expected_value_r": probability.expected_value_r,
                    "trader_equation_favorable": probability.trader_equation_favorable,
                    "hp_outcome_policy_id": probability.outcome_policy_id,
                    "hp_statistics_contract_id": probability.statistics_contract_id,
                    "hp_readiness_state": probability.readiness_state,
                    "hp_structural_scope": probability.structural_scope,
                    "hp_economic_scope": probability.economic_scope,
                    "hp_structural_required_n": probability.structural_required_n,
                    "hp_economic_required_n": probability.economic_required_n,
                    "hp_valid_realized_r_count": probability.valid_realized_r_count,
                    "hp_unknown_case_count": probability.unknown_case_count,
                    "hp_mean_realized_r": probability.mean_realized_r,
                    "hp_median_realized_r": probability.median_realized_r,
                    "hp_ci95_lower_r": probability.ci95_lower_r,
                    "hp_ci95_upper_r": probability.ci95_upper_r,
                    "hp_bootstrap_valid_fraction": probability.bootstrap_valid_fraction,
                    "hp_history_case_set_hash": probability.history_case_set_hash,
                    "hp_positive_fraction": probability.positive_fraction,
                    "hp_positive_fraction_wilson_lower": probability.positive_fraction_wilson_lower,
                    "hp_realized_r_statistical_confidence": (
                        probability.realized_r_statistical_confidence
                    ),
                    "hp_event_metrics_role": (
                        "DIAGNOSTIC_ONLY"
                        if realized_r_policy
                        else "LEGACY_GATE"
                        if legacy_policy
                        else "UNKNOWN_POLICY_FAIL_CLOSED"
                    ),
                }
            )

        return SignalQualityAssessment(
            final_score=score,
            confidence=round(confidence, 4),
            quality_grade=grade,
            approved=approved,
            metadata={
                **context_metadata,
                **probability_metadata,
                "ai_score": ai_score,
                "risk_score": risk_score,
                "council_confidence": round(min(max(float(council_confidence), 0.0), 1.0), 4),
                "brooks_certainty": quality.brooks_certainty,
                "structure_quality": quality.structure_quality,
                "context_quality": quality.context_quality,
                "entry_quality": quality.entry_quality,
                "risk_quality": quality.risk_quality,
                "quality_model": "BROOKS_CONTEXT_EVIDENCE_HISTORICAL_PROBABILITY_V2",
                "unclassified_rule_ids": list(quality.unclassified_rule_ids),
                "evidence_conflicts": [
                    f"{item.severity}:{item.rule_id}:{item.reason}" for item in quality.conflicts
                ],
            },
        )
