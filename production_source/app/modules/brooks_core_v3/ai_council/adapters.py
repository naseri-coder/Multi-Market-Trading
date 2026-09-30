"""Safe council-opinion adapters from prior Brooks Core v3 stages."""

from __future__ import annotations

from app.modules.brooks_core_v3.traders_equation import (
    TraderEquationAssessment,
    TraderEquationStatus,
)

from .entities import CouncilOpinion, CouncilStance


def trader_equation_opinion(
    assessment: TraderEquationAssessment,
) -> CouncilOpinion:
    if assessment.status is TraderEquationStatus.FAVORABLE:
        stance = CouncilStance.SUPPORT
    elif assessment.status is TraderEquationStatus.UNFAVORABLE:
        stance = CouncilStance.OPPOSE
    else:
        stance = CouncilStance.ABSTAIN

    return CouncilOpinion(
        reviewer_id="traders_equation",
        stance=stance,
        basis="brooks_traders_equation",
        reasons=(
            f"equation_status={assessment.status.value}",
            "No probability was inferred by the AI Council.",
        ),
        evidence_refs=(assessment.source_evidence.rule_id,),
    )
