from __future__ import annotations

from app.modules.ai_council.entities import (
    AgentDecision,
    CouncilDecision,
)


class CouncilConsensus:
    def evaluate(
        self,
        decisions: list[AgentDecision],
    ) -> CouncilDecision:

        if not decisions:
            return CouncilDecision(
                final_score=0.0,
                approved=False,
                summary="No agent decisions available.",
                decisions=[],
            )

        final_score = sum(
            decision.score for decision in decisions
        ) / len(decisions)

        approved = all(
            decision.approved for decision in decisions
        )

        mean_confidence = (
            sum(
                min(
                    max(
                        float(decision.confidence),
                        0.0,
                    ),
                    1.0,
                )
                for decision in decisions
            )
            / len(decisions)
        )

        scores = [
            float(decision.score)
            for decision in decisions
        ]

        score_spread = (
            max(scores) - min(scores)
        )

        score_agreement = min(
            max(
                1.0 - (score_spread / 100.0),
                0.0,
            ),
            1.0,
        )

        approval_agreement = (
            sum(
                1
                for decision in decisions
                if decision.approved
            )
            / len(decisions)
        )

        council_confidence = (
            (mean_confidence * 0.50)
            + (score_agreement * 0.25)
            + (approval_agreement * 0.25)
        )

        council_confidence = round(
            min(
                max(
                    council_confidence,
                    0.0,
                ),
                1.0,
            ),
            4,
        )

        summary = (
            "AI Council approved candidate."
            if approved
            else "AI Council rejected candidate."
        )

        return CouncilDecision(
            final_score=round(final_score, 2),
            approved=approved,
            summary=summary,
            decisions=decisions,
            confidence=council_confidence,
            metadata={
                "mean_agent_confidence": round(
                    mean_confidence,
                    4,
                ),
                "score_agreement": round(
                    score_agreement,
                    4,
                ),
                "approval_agreement": round(
                    approval_agreement,
                    4,
                ),
            },
        )
