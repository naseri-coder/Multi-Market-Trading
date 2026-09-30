from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AgentDecision:
    agent_name: str
    score: float
    confidence: float
    approved: bool
    reasoning: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CouncilDecision:
    final_score: float
    approved: bool
    summary: str
    decisions: list[AgentDecision]
    confidence: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)
