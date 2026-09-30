from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SignalQualityAssessment:
    final_score: float
    confidence: float
    quality_grade: str
    approved: bool
    metadata: dict[str, Any] = field(default_factory=dict)
