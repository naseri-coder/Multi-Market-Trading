"""Unit tests for channel management and multi-channel membership rules."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.channels.entities import (
    ChannelRecord,
    CreateChannel,
    ResolvedTelegramChannel,
    UpdateChannel,
)
from app.modules.channels.errors import (
    ChannelConfigurationError,
    ChannelMembershipCheckError,
    InvalidChannelError,
    TelegramChannelGatewayError,
)
from app.modules.channels.service import ChannelService


def channel_record(
    channel_id: int,
    *,
    username: str | None = "channelname",
    invite_link: str | None = None,
    is_active: bool = True,
    sort_order: int = 0,
) -> ChannelRecord:
    timestamp = datetime(2026, 9, 1, tzinfo=UTC)
    return ChannelRecord(
        id=channel_id,
        telegram_chat_id=-1_000_000_000_000 - channel_id,
        username=username,
        title=f"Channel {channel_id}",
        invite_link=invite_link,
        is_active=is_active,
        sort_order=sort_order,
        created_at=timestamp,
        updated_at=timestamp,
    )


def fake_repository(
    *,
    active: tuple[ChannelRecord, ...] = (),
) -> SimpleNamespace:
    return SimpleNamespace(
        create=AsyncMock(),
        update=AsyncMock(),
        delete=AsyncMock(),
        toggle=AsyncMock(),
        get_by_id=AsyncMock(),
        get_by_telegram_chat_id=AsyncMock(),
        list_all=AsyncMock(return_value=()),
        list_active=AsyncMock(return_value=active),
    )


async def test_create_normalizes_public_channel_before_persistence() -> None:
    repository = fake_repository()
    repository.create.return_value = channel_record(1)
    service = ChannelService(repository)

    result = await service.create_channel(
        CreateChannel(
            telegram_chat_id=-1_001_234_567_890,
            username="  @channelname  ",
            title="  Public Channel  ",
            invite_link=None,
            sort_order=3,
        )
    )

    submitted = repository.create.await_args.args[0]
    assert result.id == 1
    assert submitted.username == "channelname"
    assert submitted.title == "Public Channel"
    assert submitted.sort_order == 3


async def test_update_accepts_private_channel_with_telegram_invite_link() -> None:
    repository = fake_repository()
    repository.update.return_value = channel_record(
        4,
        username=None,
        invite_link="https://t.me/+private-token",
    )
    service = ChannelService(repository)

    await service.update_channel(
        4,
        UpdateChannel(
            title=" Private ",
            username=None,
            invite_link=" https://t.me/+private-token ",
            sort_order=0,
        ),
    )

    channel_id, submitted = repository.update.await_args.args
    assert channel_id == 4
    assert submitted.title == "Private"
    assert submitted.invite_link == "https://t.me/+private-token"


async def test_refresh_updates_telegram_metadata_and_preserves_sort_order() -> None:
    existing = channel_record(4, sort_order=9)
    refreshed = channel_record(4, username="newchannel", sort_order=9)
    repository = fake_repository()
    repository.get_by_telegram_chat_id.return_value = existing
    repository.update.return_value = refreshed
    service = ChannelService(repository)

    result = await service.refresh_channel(
        ResolvedTelegramChannel(
            telegram_chat_id=existing.telegram_chat_id,
            username="@newchannel",
            title=" Updated title ",
            invite_link=None,
        )
    )

    repository.get_by_telegram_chat_id.assert_awaited_once_with(existing.telegram_chat_id)
    channel_id, submitted = repository.update.await_args.args
    assert channel_id == existing.id
    assert submitted.title == "Updated title"
    assert submitted.username == "newchannel"
    assert submitted.sort_order == 9
    assert result == refreshed


@pytest.mark.parametrize(
    ("channel", "message"),
    [
        (
            CreateChannel(100, "channelname", "Title", None, 0),
            "must be negative",
        ),
        (
            CreateChannel(-1001, None, "Title", None, 0),
            "username or private invite",
        ),
        (
            CreateChannel(-1001, "bad-name", "Title", None, 0),
            "username format",
        ),
        (
            CreateChannel(-1001, None, "Title", "http://t.me/+token", 0),
            "HTTPS URL",
        ),
        (
            CreateChannel(-1001, "channelname", "Title", None, -1),
            "non-negative integer",
        ),
        (
            CreateChannel(-1001, "channelname", "Title", None, True),
            "non-negative integer",
        ),
    ],
)
async def test_create_rejects_invalid_channel_metadata(
    channel: CreateChannel,
    message: str,
) -> None:
    repository = fake_repository()

    with pytest.raises(InvalidChannelError, match=message):
        await ChannelService(repository).create_channel(channel)

    repository.create.assert_not_awaited()


async def test_no_active_channels_allows_user_without_gateway_calls() -> None:
    repository = fake_repository(active=())
    gateway = SimpleNamespace(is_member=AsyncMock())

    result = await ChannelService(repository).check_membership(123456789, gateway)

    assert result.allowed is True
    assert result.checked_channels == 0
    assert result.missing_channels == ()
    gateway.is_member.assert_not_awaited()


async def test_single_active_channel_allows_member() -> None:
    repository = fake_repository(active=(channel_record(1),))
    gateway = SimpleNamespace(is_member=AsyncMock(return_value=True))

    result = await ChannelService(repository).check_membership(123456789, gateway)

    assert result.allowed is True
    assert result.checked_channels == 1
    assert result.missing_channels == ()


async def test_single_active_channel_reports_non_member() -> None:
    channel = channel_record(1)
    repository = fake_repository(active=(channel,))
    gateway = SimpleNamespace(is_member=AsyncMock(return_value=False))

    result = await ChannelService(repository).check_membership(123456789, gateway)

    assert result.allowed is False
    assert result.checked_channels == 1
    assert result.missing_channels == (channel,)


async def test_multiple_active_channels_are_all_checked() -> None:
    channels = (channel_record(1), channel_record(2), channel_record(3))
    repository = fake_repository(active=channels)

    async def membership(chat_id: int, user_id: int) -> bool:
        assert user_id == 123456789
        return chat_id != channels[1].telegram_chat_id

    gateway = SimpleNamespace(is_member=AsyncMock(side_effect=membership))

    result = await ChannelService(repository).check_membership(123456789, gateway)

    assert result.allowed is False
    assert result.checked_channels == 3
    assert result.missing_channels == (channels[1],)
    assert gateway.is_member.await_count == 3
    assert {call.args[0] for call in gateway.is_member.await_args_list} == {
        channel.telegram_chat_id for channel in channels
    }


async def test_inactive_channels_are_not_returned_or_checked() -> None:
    active = channel_record(1)
    inactive = channel_record(2, is_active=False)
    repository = fake_repository(active=(active,))
    repository.list_all.return_value = (active, inactive)
    gateway = SimpleNamespace(is_member=AsyncMock(return_value=True))

    result = await ChannelService(repository).check_membership(123456789, gateway)

    assert result.checked_channels == 1
    gateway.is_member.assert_awaited_once_with(active.telegram_chat_id, 123456789)


async def test_one_gateway_failure_fails_closed_after_all_checks() -> None:
    channels = (channel_record(1), channel_record(2))
    repository = fake_repository(active=channels)

    async def membership(chat_id: int, user_id: int) -> bool:
        if chat_id == channels[0].telegram_chat_id:
            raise TelegramChannelGatewayError("Telegram unavailable")
        return True

    gateway = SimpleNamespace(is_member=AsyncMock(side_effect=membership))

    with pytest.raises(ChannelMembershipCheckError):
        await ChannelService(repository).check_membership(123456789, gateway)

    assert gateway.is_member.await_count == 2


async def test_missing_channel_without_join_url_fails_closed() -> None:
    channel = channel_record(1, username=None, invite_link=None)
    repository = fake_repository(active=(channel,))
    gateway = SimpleNamespace(is_member=AsyncMock(return_value=False))

    with pytest.raises(ChannelConfigurationError):
        await ChannelService(repository).check_membership(123456789, gateway)


async def test_membership_check_preserves_task_cancellation() -> None:
    repository = fake_repository(active=(channel_record(1),))
    gateway = SimpleNamespace(is_member=AsyncMock(side_effect=asyncio.CancelledError()))

    with pytest.raises(asyncio.CancelledError):
        await ChannelService(repository).check_membership(123456789, gateway)
