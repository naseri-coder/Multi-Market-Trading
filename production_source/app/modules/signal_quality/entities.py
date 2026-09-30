from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class SignalQualityRecord:
    signal_id: int
    ai_score: Decimal
    risk_score: Decimal
    final_score: Decimal
    confidence: Decimal
    quality_grade: str
    market_regime: str | None
    gate_approved: bool
    gate_reason: str | None
    metadata: dict[str, Any] = field(
        default_factory=dict
    )
    created_at: datetime | None = None
