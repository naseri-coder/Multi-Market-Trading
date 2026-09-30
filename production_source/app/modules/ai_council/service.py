from __future__ import annotations

from typing import Any

from app.modules.ai_council.agents import (
    MarketAgent,
    PriceActionAgent,
    RiskAgent,
)
from app.modules.ai_council.consensus import CouncilConsensus
from app.modules.ai_council.entities import CouncilDecision


class AICouncilService:
    def __init__(self) -> None:
        self.agents = [
            MarketAgent(),
            PriceActionAgent(),
            RiskAgent(),
        ]
        self.consensus = CouncilConsensus()

    def evaluate(
        self,
        candidate: Any,
    ) -> CouncilDecision:
        decisions = [
            agent.evaluate(candidate)
            for agent in self.agents
        ]

        return self.consensus.evaluate(decisions)
