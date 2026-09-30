"""Signal persistence port and async PostgreSQL implementation."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Protocol

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as _models  # noqa: F401
from app.modules.signals.entities import (
    SignalEventRecord,
    SignalListMode,
    SignalRecord,
    SignalTargetRecord,
)
from app.modules.signals.errors import (
    SignalNotFoundError,
    SignalRepositoryError,
    SignalStateError,
    SignalTargetNotFoundError,
)
from app.modules.signals.models import (
    Signal,
    SignalEvent,
    SignalPublicationScope,
    SignalStatus,
    SignalTarget,
    SignalTargetStatus,
)


class SignalRepository(Protocol):
    """Persistence operations consumed by SignalService."""

    async def create_signal(
        self,
        *,
        values: dict[str, object],
        created_at: datetime,
    ) -> SignalRecord: ...

    async def get_signal(self, signal_id: int, *, for_update: bool = False) -> SignalRecord: ...

    async def update_signal(
        self,
        signal_id: int,
        *,
        values: dict[str, object],
        updated_at: datetime,
    ) -> SignalRecord: ...

    async def list_targets(self, signal_id: int) -> tuple[SignalTargetRecord, ...]: ...

    async def get_target(
        self,
        signal_id: int,
        target_id: int,
        *,
        for_update: bool = False,
    ) -> SignalTargetRecord: ...

    async def create_target(
        self,
        *,
        signal_id: int,
        target_number: int,
        target_price: Decimal,
        created_at: datetime,
    ) -> SignalTargetRecord: ...

    async def mark_target_hit(
        self,
        signal_id: int,
        target_id: int,
        *,
        hit_at: datetime,
        profit_loss: Decimal,
    ) -> SignalTargetRecord: ...

    async def cancel_pending_targets(self, signal_id: int, *, changed_at: datetime) -> int: ...

    async def append_event(
        self,
        *,
        signal_id: int,
        event_type: str,
        metadata: dict[str, object],
        created_at: datetime,
    ) -> SignalEventRecord: ...

    async def list_events(
        self,
        signal_id: int,
        *,
        limit: int,
        offset: int,
    ) -> tuple[SignalEventRecord, ...]: ...

    async def count_public_signals(
        self,
        *,
        mode: str,
        live_since: datetime | None,
    ) -> int: ...

    async def list_public_signals(
        self,
        *,
        mode: str,
        live_since: datetime | None,
        limit: int,
        offset: int,
    ) -> tuple[SignalRecord, ...]: ...

    async def get_public_signal(self, signal_id: int) -> SignalRecord: ...

    async def count_targets(self, signal_id: int) -> int: ...

    async def list_targets_page(
        self,
        signal_id: int,
        *,
        limit: int,
        offset: int,
    ) -> tuple[SignalTargetRecord, ...]: ...

    async def count_admin_signals(
        self,
        *,
        statuses: tuple[str, ...],
    ) -> int: ...

    async def list_admin_signals(
        self,
        *,
        statuses: tuple[str, ...],
        limit: int,
        offset: int,
    ) -> tuple[SignalRecord, ...]: ...


def _to_signal(model: Signal) -> SignalRecord:
    return SignalRecord(
        id=model.id,
        symbol=model.symbol,
        direction=model.direction,
        entry_price=model.entry_price,
        stop_loss=model.stop_loss,
        leverage=model.leverage,
        status=model.status,
        description=model.description,
        profit_loss=model.profit_loss,
        created_at=model.created_at,
        updated_at=model.updated_at,
        closed_at=model.closed_at,
    )


def _to_target(model: SignalTarget) -> SignalTargetRecord:
    return SignalTargetRecord(
        id=model.id,
        signal_id=model.signal_id,
        target_number=model.target_number,
        target_price=model.target_price,
        status=model.status,
        hit_at=model.hit_at,
        profit_loss=model.profit_loss,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _to_event(model: SignalEvent) -> SignalEventRecord:
    return SignalEventRecord(
        id=model.id,
        signal_id=model.signal_id,
        event_type=model.event_type,
        metadata=dict(model.event_metadata),
        created_at=model.created_at,
    )


class SQLAlchemySignalRepository:
    """Async repository bound to a caller-owned transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_signal(
        self,
        *,
        values: dict[str, object],
        created_at: datetime,
    ) -> SignalRecord:
        statement = (
            insert(Signal)
            .values(**values, created_at=created_at, updated_at=created_at)
            .returning(Signal)
        )
        try:
            model = (await self.session.execute(statement)).scalar_one()
        except SQLAlchemyError as exc:
            raise SignalRepositoryError("Unable to create signal") from exc
        return _to_signal(model)

    async def get_signal(self, signal_id: int, *, for_update: bool = False) -> SignalRecord:
        statement = select(Signal).where(Signal.id == signal_id)
        if for_update:
            statement = statement.with_for_update()
        try:
            model = await self.session.scalar(statement)
        except SQLAlchemyError as exc:
            raise SignalRepositoryError("Unable to load signal") from exc
        if model is None:
            raise SignalNotFoundError("Signal does not exist")
        return _to_signal(model)

    async def update_signal(
        self,
        signal_id: int,
        *,
        values: dict[str, object],
        updated_at: datetime,
    ) -> SignalRecord:
        statement = (
            update(Signal)
            .where(Signal.id == signal_id)
            .values(**values, updated_at=updated_at)
            .returning(Signal)
        )
        try:
            model = (await self.session.execute(statement)).scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise SignalRepositoryError("Unable to update signal") from exc
        if model is None:
            raise SignalNotFoundError("Signal does not exist")
        return _to_signal(model)

    async def list_targets(self, signal_id: int) -> tuple[SignalTargetRecord, ...]:
        statement = (
            select(SignalTarget)
            .where(SignalTarget.signal_id == signal_id)
            .order_by(SignalTarget.target_number, SignalTarget.id)
        )
        try:
            models = (await self.session.scalars(statement)).all()
        except SQLAlchemyError as exc:
            raise SignalRepositoryError("Unable to list signal targets") from exc
        return tuple(_to_target(model) for model in models)

    async def get_target(
        self,
        signal_id: int,
        target_id: int,
        *,
        for_update: bool = False,
    ) -> SignalTargetRecord:
        statement = select(SignalTarget).where(
            SignalTarget.id == target_id,
            SignalTarget.signal_id == signal_id,
        )
        if for_update:
            statement = statement.with_for_update()
        try:
            model = await self.session.scalar(statement)
        except SQLAlchemyError as exc:
            raise SignalRepositoryError("Unable to load signal target") from exc
        if model is None:
            raise SignalTargetNotFoundError("Signal target does not exist")
        return _to_target(model)

    async def create_target(
        self,
        *,
        signal_id: int,
        target_number: int,
        target_price: Decimal,
        created_at: datetime,
    ) -> SignalTargetRecord:
        statement = (
            insert(SignalTarget)
            .values(
                signal_id=signal_id,
                target_number=target_number,
                target_price=target_price,
                status=SignalTargetStatus.PENDING.value,
                created_at=created_at,
                updated_at=created_at,
            )
            .returning(SignalTarget)
        )
        try:
            model = (await self.session.execute(statement)).scalar_one()
        except SQLAlchemyError as exc:
            raise SignalRepositoryError("Unable to add signal target") from exc
        return _to_target(model)

    async def mark_target_hit(
        self,
        signal_id: int,
        target_id: int,
        *,
        hit_at: datetime,
        profit_loss: Decimal,
    ) -> SignalTargetRecord:
        statement = (
            update(SignalTarget)
            .where(
                SignalTarget.id == target_id,
                SignalTarget.signal_id == signal_id,
                SignalTarget.status == SignalTargetStatus.PENDING.value,
            )
            .values(
                status=SignalTargetStatus.HIT.value,
                hit_at=hit_at,
                profit_loss=profit_loss,
                updated_at=hit_at,
            )
            .returning(SignalTarget)
        )
        try:
            model = (await self.session.execute(statement)).scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise SignalRepositoryError("Unable to mark signal target as hit") from exc
        if model is None:
            await self.get_target(signal_id, target_id)
            raise SignalStateError("Signal target is not pending")
        return _to_target(model)

    async def cancel_pending_targets(self, signal_id: int, *, changed_at: datetime) -> int:
        statement = (
            update(SignalTarget)
            .where(
                SignalTarget.signal_id == signal_id,
                SignalTarget.status == SignalTargetStatus.PENDING.value,
            )
            .values(
                status=SignalTargetStatus.CANCELLED.value,
                updated_at=changed_at,
            )
        )
        try:
            result = await self.session.execute(statement)
        except SQLAlchemyError as exc:
            raise SignalRepositoryError("Unable to cancel pending signal targets") from exc
        return int(result.rowcount or 0)

    async def append_event(
        self,
        *,
        signal_id: int,
        event_type: str,
        metadata: dict[str, object],
        created_at: datetime,
    ) -> SignalEventRecord:
        statement = (
            insert(SignalEvent)
            .values(
                signal_id=signal_id,
                event_type=event_type,
                event_metadata=metadata,
                created_at=created_at,
            )
            .returning(SignalEvent)
        )
        try:
            model = (await self.session.execute(statement)).scalar_one()
        except SQLAlchemyError as exc:
            raise SignalRepositoryError("Unable to append signal event") from exc
        return _to_event(model)

    async def list_events(
        self,
        signal_id: int,
        *,
        limit: int,
        offset: int,
    ) -> tuple[SignalEventRecord, ...]:
        statement = (
            select(SignalEvent)
            .where(SignalEvent.signal_id == signal_id)
            .order_by(SignalEvent.created_at.desc(), SignalEvent.id.desc())
            .limit(limit)
            .offset(offset)
        )
        try:
            models = (await self.session.scalars(statement)).all()
        except SQLAlchemyError as exc:
            raise SignalRepositoryError("Unable to load signal history") from exc
        return tuple(_to_event(model) for model in models)

    async def count_public_signals(
        self,
        *,
        mode: str,
        live_since: datetime | None,
    ) -> int:
        statement = select(func.count(Signal.id)).where(
            *self._public_signal_filters(mode, live_since)
        )
        try:
            return int((await self.session.scalar(statement)) or 0)
        except SQLAlchemyError as exc:
            raise SignalRepositoryError("Unable to count public signals") from exc

    async def list_public_signals(
        self,
        *,
        mode: str,
        live_since: datetime | None,
        limit: int,
        offset: int,
    ) -> tuple[SignalRecord, ...]:
        statement = (
            select(Signal)
            .where(*self._public_signal_filters(mode, live_since))
            .order_by(Signal.created_at.desc(), Signal.id.desc())
            .limit(limit)
            .offset(offset)
        )
        try:
            models = (await self.session.scalars(statement)).all()
        except SQLAlchemyError as exc:
            raise SignalRepositoryError("Unable to list public signals") from exc
        return tuple(_to_signal(model) for model in models)

    async def get_public_signal(self, signal_id: int) -> SignalRecord:
        statement = select(Signal).where(
            Signal.id == signal_id,
            Signal.status != SignalStatus.DRAFT.value,
            Signal.publication_scope.in_(
                (
                    SignalPublicationScope.PUBLIC.value,
                    SignalPublicationScope.PUBLIC_VIP.value,
                )
            ),
        )
        try:
            model = await self.session.scalar(statement)
        except SQLAlchemyError as exc:
            raise SignalRepositoryError("Unable to load public signal") from exc
        if model is None:
            raise SignalNotFoundError("Public signal does not exist")
        return _to_signal(model)

    async def count_targets(self, signal_id: int) -> int:
        statement = select(func.count(SignalTarget.id)).where(
            SignalTarget.signal_id == signal_id
        )
        try:
            return int((await self.session.scalar(statement)) or 0)
        except SQLAlchemyError as exc:
            raise SignalRepositoryError("Unable to count signal targets") from exc

    async def list_targets_page(
        self,
        signal_id: int,
        *,
        limit: int,
        offset: int,
    ) -> tuple[SignalTargetRecord, ...]:
        statement = (
            select(SignalTarget)
            .where(SignalTarget.signal_id == signal_id)
            .order_by(SignalTarget.target_number, SignalTarget.id)
            .limit(limit)
            .offset(offset)
        )
        try:
            models = (await self.session.scalars(statement)).all()
        except SQLAlchemyError as exc:
            raise SignalRepositoryError("Unable to load signal target page") from exc
        return tuple(_to_target(model) for model in models)

    async def count_admin_signals(
        self,
        *,
        statuses: tuple[str, ...],
    ) -> int:
        statement = select(func.count(Signal.id)).where(
            Signal.status.in_(statuses)
        )
        try:
            return int((await self.session.scalar(statement)) or 0)
        except SQLAlchemyError as exc:
            raise SignalRepositoryError(
                "Unable to count administrator signals"
            ) from exc

    async def list_admin_signals(
        self,
        *,
        statuses: tuple[str, ...],
        limit: int,
        offset: int,
    ) -> tuple[SignalRecord, ...]:
        statement = (
            select(Signal)
            .where(Signal.status.in_(statuses))
            .order_by(Signal.created_at.desc(), Signal.id.desc())
            .limit(limit)
            .offset(offset)
        )
        try:
            models = (await self.session.scalars(statement)).all()
        except SQLAlchemyError as exc:
            raise SignalRepositoryError(
                "Unable to list administrator signals"
            ) from exc
        return tuple(_to_signal(model) for model in models)

    @staticmethod
    def _public_signal_filters(
        mode: str,
        live_since: datetime | None,
    ) -> tuple[object, ...]:
        public_scope_filter = Signal.publication_scope.in_(
            (
                SignalPublicationScope.PUBLIC.value,
                SignalPublicationScope.PUBLIC_VIP.value,
            )
        )
        if mode == SignalListMode.LIVE.value and live_since is not None:
            return (
                public_scope_filter,
                Signal.status != SignalStatus.DRAFT.value,
                Signal.created_at >= live_since,
            )
        if mode == SignalListMode.OPEN.value:
            return (
                public_scope_filter,
                Signal.status == SignalStatus.OPEN.value,
            )
        if mode == SignalListMode.HISTORY.value:
            return (
                public_scope_filter,
                Signal.status.in_(
                    (SignalStatus.CLOSED.value, SignalStatus.CANCELLED.value)
                ),
            )
        raise SignalRepositoryError("Unsupported public signal collection")
