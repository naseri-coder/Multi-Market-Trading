from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RiskAssessment:
    risk_score: float
    approved: bool
    reasons: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)
