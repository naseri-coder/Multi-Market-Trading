from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.modules.signal_quality.entities import (
    SignalQualityRecord,
)
from app.modules.signal_quality.repository import (
    SignalQualityRepository,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


class SignalQualityService:
    """
    Stores final signal intelligence and gate decisions.
    """

    def __init__(
        self,
        repository: SignalQualityRepository,
    ) -> None:
        self.repository = repository

    async def save_quality_assessment(
        self,
        *,
        signal_id: int,
        ai_score: float,
        risk_score: float,
        final_score: float,
        confidence: float,
        quality_grade: str,
        market_regime: str | None,
        gate_approved: bool,
        gate_reason: str | None,
        metadata: dict[str, object],
    ) -> SignalQualityRecord:

        return await self.repository.create_assessment(
            signal_id=signal_id,
            ai_score=Decimal(str(ai_score)),
            risk_score=Decimal(str(risk_score)),
            final_score=Decimal(str(final_score)),
            confidence=Decimal(str(confidence)),
            quality_grade=quality_grade,
            market_regime=market_regime,
            gate_approved=gate_approved,
            gate_reason=gate_reason,
            metadata=metadata,
            created_at=utc_now(),
        )
