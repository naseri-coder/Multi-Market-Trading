"""Transactional Phase 7 channel tests against real PostgreSQL."""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update

from app.core.config import Settings
from app.db.session import DatabaseManager
from app.modules.channels.entities import (
    CreateChannel,
    ResolvedTelegramChannel,
    UpdateChannel,
)
from app.modules.channels.errors import ChannelNotFoundError, DuplicateChannelError
from app.modules.channels.models import Channel
from app.modules.channels.repository import SQLAlchemyChannelRepository
from app.modules.channels.service import ChannelService

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="TEST_DATABASE_URL is required for the real channel integration test",
)


async def test_real_channel_crud_and_multi_channel_membership(valid_token: str) -> None:
    settings = Settings(
        telegram_bot_token=valid_token,
        database_url=TEST_DATABASE_URL,
        db_pool_size=2,
        db_max_overflow=0,
        _env_file=None,
    )
    database = DatabaseManager.from_settings(settings)
    suffix = uuid4().hex[:8]
    base_chat_id = -1_000_000_000_000_000 - uuid4().int % 100_000_000_000

    try:
        async with database.session() as session:
            transaction = await session.begin()
            try:
                await session.execute(update(Channel).values(is_active=False))
                repository = SQLAlchemyChannelRepository(session)
                service = ChannelService(repository)
                public = await service.create_channel(
                    CreateChannel(
                        telegram_chat_id=base_chat_id,
                        username=f"public_{suffix}",
                        title="Public Test Channel",
                        invite_link=None,
                        sort_order=2,
                    )
                )
                private = await service.create_channel(
                    CreateChannel(
                        telegram_chat_id=base_chat_id - 1,
                        username=None,
                        title="Private Test Channel",
                        invite_link="https://t.me/+private-test-token",
                        sort_order=1,
                    )
                )

                listed = await service.list_channels()
                test_ids_in_order = [
                    channel.id for channel in listed if channel.id in {public.id, private.id}
                ]
                assert test_ids_in_order == [private.id, public.id]

                gateway = SimpleNamespace(
                    is_member=AsyncMock(
                        side_effect=lambda chat_id, user_id: chat_id == public.telegram_chat_id
                    )
                )
                membership = await service.check_membership(123456789, gateway)
                assert membership.allowed is False
                assert membership.checked_channels == 2
                assert membership.missing_channels == (private,)
                assert gateway.is_member.await_count == 2

                edited = await service.update_channel(
                    public.id,
                    UpdateChannel(
                        title="Updated Public Channel",
                        username=f"public_{suffix}",
                        invite_link=None,
                        sort_order=0,
                    ),
                )
                assert edited.title == "Updated Public Channel"

                refreshed = await service.refresh_channel(
                    ResolvedTelegramChannel(
                        telegram_chat_id=public.telegram_chat_id,
                        username=f"public_{suffix}",
                        title="Refreshed Public Channel",
                        invite_link=None,
                    )
                )
                assert refreshed.title == "Refreshed Public Channel"
                assert refreshed.sort_order == 0

                disabled = await service.toggle_channel(private.id)
                assert disabled.is_active is False
                active = await repository.list_active()
                assert [channel.id for channel in active] == [public.id]

                gateway.is_member.reset_mock()
                gateway.is_member.return_value = True
                gateway.is_member.side_effect = None
                membership = await service.check_membership(123456789, gateway)
                assert membership.allowed is True
                assert membership.checked_channels == 1
                gateway.is_member.assert_awaited_once_with(
                    public.telegram_chat_id,
                    123456789,
                )

                await service.delete_channel(public.id)
                with pytest.raises(ChannelNotFoundError):
                    await service.get_channel(public.id)

                savepoint = await session.begin_nested()
                try:
                    with pytest.raises(DuplicateChannelError):
                        await service.create_channel(
                            CreateChannel(
                                telegram_chat_id=private.telegram_chat_id,
                                username=f"duplicate_{suffix}",
                                title="Duplicate",
                                invite_link=None,
                                sort_order=0,
                            )
                        )
                finally:
                    await savepoint.rollback()

                count = await session.scalar(
                    select(func.count(Channel.id)).where(
                        Channel.telegram_chat_id == private.telegram_chat_id
                    )
                )
                assert count == 1
            finally:
                await transaction.rollback()
    finally:
        await database.dispose()
