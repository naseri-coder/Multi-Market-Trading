"""Async repository for PAPER delivery state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.paper_runtime.models import SignalDelivery


@dataclass(frozen=True, slots=True)
class DeliveryRecord:
    id: int
    signal_id: int
    channel_kind: str
    destination_id: str
    status: str
    attempt_count: int
    external_message_id: str | None


class DeliveryRepositoryError(Exception):
    pass


def _record(model: SignalDelivery) -> DeliveryRecord:
    return DeliveryRecord(
        id=model.id,
        signal_id=model.signal_id,
        channel_kind=model.channel_kind,
        destination_id=model.destination_id,
        status=model.status,
        attempt_count=model.attempt_count,
        external_message_id=model.external_message_id,
    )


class SQLAlchemySignalDeliveryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(
        self,
        *,
        signal_id: int,
        channel_kind: str,
        destination_id: str,
    ) -> DeliveryRecord | None:
        stmt = select(SignalDelivery).where(
            SignalDelivery.signal_id == signal_id,
            SignalDelivery.channel_kind == channel_kind,
            SignalDelivery.destination_id == destination_id,
        )
        try:
            model = await self.session.scalar(stmt)
        except SQLAlchemyError as exc:
            raise DeliveryRepositoryError("Unable to load delivery state") from exc
        return None if model is None else _record(model)

    async def create_pending(
        self,
        *,
        signal_id: int,
        channel_kind: str,
        destination_id: str,
        now: datetime,
    ) -> DeliveryRecord:
        stmt = (
            insert(SignalDelivery)
            .values(
                signal_id=signal_id,
                channel_kind=channel_kind,
                destination_id=destination_id,
                status="PENDING",
                attempt_count=0,
                created_at=now,
                updated_at=now,
            )
            .returning(SignalDelivery)
        )
        try:
            model = (await self.session.execute(stmt)).scalar_one()
        except IntegrityError as exc:
            raise DeliveryRepositoryError("Delivery reservation already exists") from exc
        except SQLAlchemyError as exc:
            raise DeliveryRepositoryError("Unable to create delivery reservation") from exc
        return _record(model)

    async def mark_sending(self, delivery_id: int, *, now: datetime) -> DeliveryRecord:
        stmt = (
            update(SignalDelivery)
            .where(
                SignalDelivery.id == delivery_id,
                SignalDelivery.status.in_(("PENDING", "FAILED")),
            )
            .values(
                status="SENDING",
                attempt_count=SignalDelivery.attempt_count + 1,
                last_error_code=None,
                updated_at=now,
            )
            .returning(SignalDelivery)
        )
        try:
            model = (await self.session.execute(stmt)).scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise DeliveryRepositoryError("Unable to reserve delivery attempt") from exc
        if model is None:
            raise DeliveryRepositoryError("Delivery is not retryable")
        return _record(model)

    async def mark_sent(
        self,
        delivery_id: int,
        *,
        message_id: str,
        now: datetime,
    ) -> DeliveryRecord:
        stmt = (
            update(SignalDelivery)
            .where(
                SignalDelivery.id == delivery_id,
                SignalDelivery.status == "SENDING",
            )
            .values(
                status="SENT",
                external_message_id=message_id,
                updated_at=now,
            )
            .returning(SignalDelivery)
        )
        try:
            model = (await self.session.execute(stmt)).scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise DeliveryRepositoryError("Unable to mark delivery sent") from exc
        if model is None:
            raise DeliveryRepositoryError("Delivery is not in SENDING state")
        return _record(model)

    async def mark_failed(
        self,
        delivery_id: int,
        *,
        error_code: str,
        now: datetime,
    ) -> DeliveryRecord:
        stmt = (
            update(SignalDelivery)
            .where(
                SignalDelivery.id == delivery_id,
                SignalDelivery.status == "SENDING",
            )
            .values(
                status="FAILED",
                last_error_code=error_code[:128],
                updated_at=now,
            )
            .returning(SignalDelivery)
        )
        try:
            model = (await self.session.execute(stmt)).scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise DeliveryRepositoryError("Unable to mark delivery failed") from exc
        if model is None:
            raise DeliveryRepositoryError("Delivery is not in SENDING state")
        return _record(model)

    async def mark_ambiguous(
        self,
        delivery_id: int,
        *,
        now: datetime,
    ) -> DeliveryRecord:
        stmt = (
            update(SignalDelivery)
            .where(
                SignalDelivery.id == delivery_id,
                SignalDelivery.status == "SENDING",
            )
            .values(status="AMBIGUOUS", updated_at=now)
            .returning(SignalDelivery)
        )
        try:
            model = (await self.session.execute(stmt)).scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise DeliveryRepositoryError("Unable to mark delivery ambiguous") from exc
        if model is None:
            raise DeliveryRepositoryError("Delivery is not in SENDING state")
        return _record(model)
