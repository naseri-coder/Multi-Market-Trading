"""Channel repository port and SQLAlchemy implementation."""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as _models  # noqa: F401
from app.modules.channels.entities import ChannelRecord, CreateChannel, UpdateChannel
from app.modules.channels.errors import (
    ChannelNotFoundError,
    ChannelRepositoryError,
    DuplicateChannelError,
)
from app.modules.channels.models import Channel


class ChannelRepository(Protocol):
    """Persistence operations consumed by ChannelService."""

    async def create(self, channel: CreateChannel) -> ChannelRecord: ...

    async def update(self, channel_id: int, channel: UpdateChannel) -> ChannelRecord: ...

    async def delete(self, channel_id: int) -> None: ...

    async def toggle(self, channel_id: int) -> ChannelRecord: ...

    async def get_by_id(self, channel_id: int) -> ChannelRecord: ...

    async def get_by_telegram_chat_id(self, telegram_chat_id: int) -> ChannelRecord: ...

    async def list_all(self) -> tuple[ChannelRecord, ...]: ...

    async def list_active(self) -> tuple[ChannelRecord, ...]: ...


def _to_record(channel: Channel) -> ChannelRecord:
    return ChannelRecord(
        id=channel.id,
        telegram_chat_id=channel.telegram_chat_id,
        username=channel.username,
        title=channel.title,
        invite_link=channel.invite_link,
        is_active=channel.is_active,
        sort_order=channel.sort_order,
        created_at=channel.created_at,
        updated_at=channel.updated_at,
    )


class SQLAlchemyChannelRepository:
    """PostgreSQL channel repository bound to a caller-owned transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, channel: CreateChannel) -> ChannelRecord:
        statement = (
            insert(Channel)
            .values(
                telegram_chat_id=channel.telegram_chat_id,
                username=channel.username,
                title=channel.title,
                invite_link=channel.invite_link,
                sort_order=channel.sort_order,
            )
            .returning(Channel)
        )
        try:
            created = (await self.session.execute(statement)).scalar_one()
        except IntegrityError as exc:
            raise DuplicateChannelError("Telegram channel is already configured") from exc
        except SQLAlchemyError as exc:
            raise ChannelRepositoryError("Unable to create channel") from exc
        return _to_record(created)

    async def update(self, channel_id: int, channel: UpdateChannel) -> ChannelRecord:
        statement = (
            update(Channel)
            .where(Channel.id == channel_id)
            .values(
                title=channel.title,
                username=channel.username,
                invite_link=channel.invite_link,
                sort_order=channel.sort_order,
            )
            .returning(Channel)
        )
        try:
            updated = (await self.session.execute(statement)).scalar_one_or_none()
        except IntegrityError as exc:
            raise DuplicateChannelError("Telegram channel metadata conflicts") from exc
        except SQLAlchemyError as exc:
            raise ChannelRepositoryError("Unable to update channel") from exc
        if updated is None:
            raise ChannelNotFoundError("Channel does not exist")
        return _to_record(updated)

    async def delete(self, channel_id: int) -> None:
        statement = delete(Channel).where(Channel.id == channel_id).returning(Channel.id)
        try:
            deleted_id = (await self.session.execute(statement)).scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise ChannelRepositoryError("Unable to delete channel") from exc
        if deleted_id is None:
            raise ChannelNotFoundError("Channel does not exist")

    async def toggle(self, channel_id: int) -> ChannelRecord:
        statement = (
            update(Channel)
            .where(Channel.id == channel_id)
            .values(is_active=~Channel.is_active)
            .returning(Channel)
        )
        try:
            updated = (await self.session.execute(statement)).scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise ChannelRepositoryError("Unable to toggle channel") from exc
        if updated is None:
            raise ChannelNotFoundError("Channel does not exist")
        return _to_record(updated)

    async def get_by_id(self, channel_id: int) -> ChannelRecord:
        return await self._get(
            select(Channel).where(Channel.id == channel_id),
        )

    async def get_by_telegram_chat_id(self, telegram_chat_id: int) -> ChannelRecord:
        return await self._get(
            select(Channel).where(Channel.telegram_chat_id == telegram_chat_id),
        )

    async def _get(self, statement: object) -> ChannelRecord:
        try:
            channel = (await self.session.execute(statement)).scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise ChannelRepositoryError("Unable to load channel") from exc
        if channel is None:
            raise ChannelNotFoundError("Channel does not exist")
        return _to_record(channel)

    async def list_all(self) -> tuple[ChannelRecord, ...]:
        return await self._list(active_only=False)

    async def list_active(self) -> tuple[ChannelRecord, ...]:
        return await self._list(active_only=True)

    async def _list(self, *, active_only: bool) -> tuple[ChannelRecord, ...]:
        statement = select(Channel).order_by(Channel.sort_order, Channel.id)
        if active_only:
            statement = statement.where(Channel.is_active.is_(True))
        try:
            channels = (await self.session.execute(statement)).scalars().all()
        except SQLAlchemyError as exc:
            raise ChannelRepositoryError("Unable to list channels") from exc
        return tuple(_to_record(channel) for channel in channels)
