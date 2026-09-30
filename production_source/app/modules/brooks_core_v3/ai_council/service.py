"""Threshold-free deliberation service for Brooks Core v3."""

from __future__ import annotations

from .entities import (
    CouncilDeliberation,
    CouncilOpinion,
    CouncilResolution,
    CouncilStance,
)


class BrooksCoreV3AICouncil:
    def deliberate(
        self,
        *,
        market_snapshot_id: str,
        setup_candidate_id: str,
        opinions: tuple[CouncilOpinion, ...],
    ) -> CouncilDeliberation:
        reviewer_ids = [item.reviewer_id for item in opinions]
        if len(reviewer_ids) != len(set(reviewer_ids)):
            raise ValueError("council reviewer ids must be unique")

        support = sum(item.stance is CouncilStance.SUPPORT for item in opinions)
        oppose = sum(item.stance is CouncilStance.OPPOSE for item in opinions)
        abstain = sum(item.stance is CouncilStance.ABSTAIN for item in opinions)

        resolution = self._resolution(
            opinion_count=len(opinions),
            support=support,
            oppose=oppose,
            abstain=abstain,
        )
        blockers = (
            "ai_council_v3_no_numeric_scoring",
            "ai_council_v3_no_approval_decision",
            "ai_council_v3_no_runtime_publication",
        )
        if resolution is not CouncilResolution.UNANIMOUS_SUPPORT:
            blockers = (*blockers, "ai_council_v3_not_unanimous_support")

        return CouncilDeliberation(
            market_snapshot_id=market_snapshot_id,
            setup_candidate_id=setup_candidate_id,
            opinions=opinions,
            resolution=resolution,
            support_count=support,
            oppose_count=oppose,
            abstain_count=abstain,
            blockers=blockers,
        )

    @staticmethod
    def _resolution(
        *,
        opinion_count: int,
        support: int,
        oppose: int,
        abstain: int,
    ) -> CouncilResolution:
        if opinion_count == 0:
            return CouncilResolution.UNRESOLVED
        if support and oppose:
            return CouncilResolution.SPLIT
        if abstain:
            return CouncilResolution.UNRESOLVED
        if support == opinion_count:
            return CouncilResolution.UNANIMOUS_SUPPORT
        if oppose == opinion_count:
            return CouncilResolution.UNANIMOUS_OPPOSITION
        return CouncilResolution.UNRESOLVED
