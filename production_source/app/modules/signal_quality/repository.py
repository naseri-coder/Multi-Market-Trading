from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.signal_quality.entities import SignalQualityRecord
from app.modules.signal_quality.models import SignalQualityAssessment


class SignalQualityRepository(Protocol):
    async def create_assessment(
        self,
        *,
        signal_id: int,
        ai_score: Decimal,
        risk_score: Decimal,
        final_score: Decimal,
        confidence: Decimal,
        quality_grade: str,
        market_regime: str | None,
        gate_approved: bool,
        gate_reason: str | None,
        metadata: dict[str, object],
        created_at: datetime,
    ) -> SignalQualityRecord:
        ...


def _to_record(
    model: SignalQualityAssessment,
) -> SignalQualityRecord:
    return SignalQualityRecord(
        signal_id=model.signal_id,
        ai_score=model.ai_score,
        risk_score=model.risk_score,
        final_score=model.final_score,
        confidence=model.confidence,
        quality_grade=model.quality_grade,
        market_regime=model.market_regime,
        gate_approved=model.gate_approved,
        gate_reason=model.gate_reason,
        metadata=dict(model.extra_metadata or {}),
        created_at=model.created_at,
    )


class SQLAlchemySignalQualityRepository:

    def __init__(
        self,
        session: AsyncSession,
    ) -> None:
        self.session = session


    async def create_assessment(
        self,
        *,
        signal_id: int,
        ai_score: Decimal,
        risk_score: Decimal,
        final_score: Decimal,
        confidence: Decimal,
        quality_grade: str,
        market_regime: str | None,
        gate_approved: bool,
        gate_reason: str | None,
        metadata: dict[str, object],
        created_at: datetime,
    ) -> SignalQualityRecord:

        try:
            result = await self.session.execute(
                select(SignalQualityAssessment).where(
                    SignalQualityAssessment.signal_id == signal_id
                )
            )

            model = result.scalar_one_or_none()

            # Quality assessment is an immutable historical
            # snapshot of the signal at publication time.
            # Duplicate evaluations must not rewrite it.
            if model is not None:
                return _to_record(model)

            model = SignalQualityAssessment(
                signal_id=signal_id,
                ai_score=ai_score,
                risk_score=risk_score,
                final_score=final_score,
                confidence=confidence,
                quality_grade=quality_grade,
                market_regime=market_regime,
                gate_approved=gate_approved,
                gate_reason=gate_reason,
                extra_metadata=metadata,
                created_at=created_at,
            )

            self.session.add(model)

            await self.session.flush()

        except SQLAlchemyError as exc:
            raise RuntimeError(
                "Unable to create or update signal quality assessment"
            ) from exc


        await self.session.refresh(model)

        return _to_record(model)
