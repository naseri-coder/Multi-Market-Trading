from __future__ import annotations

from app.modules.risk_engine.entities import RiskAssessment


class RiskValidator:
    def validate(
        self,
        risk_score: float,
    ) -> RiskAssessment:

        approved = risk_score >= 75.0

        reasons = []

        if approved:
            reasons.append(
                "Risk score passed threshold."
            )
        else:
            reasons.append(
                "Risk score below threshold."
            )

        return RiskAssessment(
            risk_score=risk_score,
            approved=approved,
            reasons=reasons,
            metadata={
                "threshold": 75.0,
            },
        )
