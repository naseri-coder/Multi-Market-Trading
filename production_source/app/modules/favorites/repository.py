"""Favorites repository port and async PostgreSQL implementation."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as _models  # noqa: F401
from app.modules.favorites.errors import FavoriteRepositoryError
from app.modules.favorites.models import UserFavorite
from app.modules.signals.entities import SignalRecord
from app.modules.signals.models import Signal, SignalStatus


class FavoriteRepository(Protocol):
    """Persistence contract consumed by FavoriteService."""

    async def public_signal_exists(self, signal_id: int) -> bool: ...

    async def add(
        self,
        *,
        user_id: int,
        signal_id: int,
        created_at: datetime,
    ) -> bool: ...

    async def remove(self, *, user_id: int, signal_id: int) -> bool: ...

    async def is_favorite(self, *, user_id: int, signal_id: int) -> bool: ...

    async def count_for_user(self, user_id: int) -> int: ...

    async def list_for_user(
        self,
        user_id: int,
        *,
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


class SQLAlchemyFavoriteRepository:
    """PostgreSQL repository bound to a caller-owned transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def public_signal_exists(self, signal_id: int) -> bool:
        statement = select(Signal.id).where(
            Signal.id == signal_id,
            Signal.status != SignalStatus.DRAFT.value,
        )
        try:
            return await self.session.scalar(statement) is not None
        except SQLAlchemyError as exc:
            raise FavoriteRepositoryError(
                "Unable to validate favorite signal"
            ) from exc

    async def add(
        self,
        *,
        user_id: int,
        signal_id: int,
        created_at: datetime,
    ) -> bool:
        statement = (
            insert(UserFavorite)
            .values(
                user_id=user_id,
                signal_id=signal_id,
                created_at=created_at,
            )
            .on_conflict_do_nothing(
                constraint="uq_user_favorites_user_signal"
            )
            .returning(UserFavorite.id)
        )
        try:
            result = await self.session.execute(statement)
            created_id = result.scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise FavoriteRepositoryError("Unable to add favorite") from exc
        return created_id is not None

    async def remove(self, *, user_id: int, signal_id: int) -> bool:
        statement = delete(UserFavorite).where(
            UserFavorite.user_id == user_id,
            UserFavorite.signal_id == signal_id,
        )
        try:
            result = await self.session.execute(statement)
        except SQLAlchemyError as exc:
            raise FavoriteRepositoryError("Unable to remove favorite") from exc
        return bool(result.rowcount)

    async def is_favorite(self, *, user_id: int, signal_id: int) -> bool:
        statement = select(UserFavorite.id).where(
            UserFavorite.user_id == user_id,
            UserFavorite.signal_id == signal_id,
        )
        try:
            return await self.session.scalar(statement) is not None
        except SQLAlchemyError as exc:
            raise FavoriteRepositoryError("Unable to load favorite state") from exc

    async def count_for_user(self, user_id: int) -> int:
        statement = (
            select(func.count(UserFavorite.id))
            .join(Signal, Signal.id == UserFavorite.signal_id)
            .where(
                UserFavorite.user_id == user_id,
                Signal.status != SignalStatus.DRAFT.value,
            )
        )
        try:
            return int((await self.session.scalar(statement)) or 0)
        except SQLAlchemyError as exc:
            raise FavoriteRepositoryError("Unable to count favorites") from exc

    async def list_for_user(
        self,
        user_id: int,
        *,
        limit: int,
        offset: int,
    ) -> tuple[SignalRecord, ...]:
        statement = (
            select(Signal)
            .join(UserFavorite, UserFavorite.signal_id == Signal.id)
            .where(
                UserFavorite.user_id == user_id,
                Signal.status != SignalStatus.DRAFT.value,
            )
            .order_by(UserFavorite.created_at.desc(), UserFavorite.id.desc())
            .limit(limit)
            .offset(offset)
        )
        try:
            models = (await self.session.scalars(statement)).all()
        except SQLAlchemyError as exc:
            raise FavoriteRepositoryError("Unable to list favorites") from exc
        return tuple(_to_signal(model) for model in models)
