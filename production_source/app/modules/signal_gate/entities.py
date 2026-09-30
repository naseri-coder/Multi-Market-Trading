from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SignalGateDecision:
    approved: bool
    reason: str
    quality_grade: str
    confidence: float
    metadata: dict[str, Any] = field(
        default_factory=dict
    )
