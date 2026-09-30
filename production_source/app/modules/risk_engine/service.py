from __future__ import annotations

from typing import Any

from app.modules.risk_engine.calculator import RiskCalculator
from app.modules.risk_engine.validator import RiskValidator
from app.modules.risk_engine.entities import RiskAssessment


class RiskEngineService:
    def __init__(self) -> None:
        self.calculator = RiskCalculator()
        self.validator = RiskValidator()

    def evaluate(
        self,
        candidate: Any,
        *,
        confidence: float | None = None,
        quality_grade: str | None = None,
        market_regime: str | None = None,
    ) -> RiskAssessment:
        risk_score, semantic_breakdown = self.calculator.calculate_with_breakdown(candidate)

        assessment = self.validator.validate(risk_score)

        leverage = self.calculator.calculate_leverage(
            entry_price=candidate.entry_price,
            stop_loss=candidate.stop_loss,
            confidence=confidence,
            quality_grade=quality_grade,
            risk_score=risk_score,
            market_regime=market_regime,
        )

        metadata = dict(assessment.metadata)
        metadata.update(
            {
                "calculated_leverage": str(leverage),
                "risk_semantic_breakdown": semantic_breakdown,
            }
        )

        return RiskAssessment(
            risk_score=assessment.risk_score,
            approved=assessment.approved,
            reasons=assessment.reasons,
            metadata=metadata,
        )
