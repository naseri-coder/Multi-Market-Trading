"""Tests for Telegram channel resolution and membership status mapping."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram import Chat, ChatMember
from telegram.error import TelegramError

from app.integrations.telegram.channels import TelegramChannelGateway, parse_chat_reference
from app.modules.channels.errors import TelegramChannelGatewayError


def fake_bot(
    *,
    chat: SimpleNamespace | None = None,
    member: SimpleNamespace | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=999,
        get_chat=AsyncMock(
            return_value=chat
            or SimpleNamespace(
                id=-1_001_234_567_890,
                type=Chat.CHANNEL,
                username="publicchannel",
                title="Public Channel",
                invite_link=None,
            )
        ),
        get_chat_member=AsyncMock(
            return_value=member or SimpleNamespace(status=ChatMember.ADMINISTRATOR)
        ),
        create_chat_invite_link=AsyncMock(
            return_value=SimpleNamespace(invite_link="https://t.me/+generated-private-link")
        ),
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("-1001234567890", -1_001_234_567_890),
        ("publicchannel", "@publicchannel"),
        ("@publicchannel", "@publicchannel"),
    ],
)
def test_parse_chat_reference_normalizes_supported_values(
    value: str,
    expected: int | str,
) -> None:
    assert parse_chat_reference(value) == expected


@pytest.mark.parametrize("value", ["", "   ", "123456"])
def test_parse_chat_reference_rejects_missing_or_positive_id(value: str) -> None:
    with pytest.raises(TelegramChannelGatewayError):
        parse_chat_reference(value)


async def test_resolve_public_channel_requires_and_confirms_bot_admin() -> None:
    bot = fake_bot()

    result = await TelegramChannelGateway(bot).resolve_channel("publicchannel")

    assert result.telegram_chat_id == -1_001_234_567_890
    assert result.username == "publicchannel"
    assert result.title == "Public Channel"
    bot.get_chat.assert_awaited_once_with("@publicchannel")
    bot.get_chat_member.assert_awaited_once_with(-1_001_234_567_890, 999)


async def test_resolve_private_channel_preserves_supplied_invite_link() -> None:
    chat = SimpleNamespace(
        id=-1_009_876_543_210,
        type=Chat.SUPERGROUP,
        username=None,
        title="Private Group",
        invite_link=None,
    )
    bot = fake_bot(chat=chat)

    result = await TelegramChannelGateway(bot).resolve_channel(
        "-1009876543210",
        supplied_invite_link="https://t.me/+private-token",
    )

    assert result.username is None
    assert result.invite_link == "https://t.me/+private-token"
    bot.create_chat_invite_link.assert_not_awaited()


async def test_resolve_private_channel_generates_missing_invite_link() -> None:
    chat = SimpleNamespace(
        id=-1_009_876_543_210,
        type=Chat.CHANNEL,
        username=None,
        title="Private Channel",
        invite_link=None,
    )
    bot = fake_bot(chat=chat)

    result = await TelegramChannelGateway(bot).resolve_channel("-1009876543210")

    assert result.invite_link == "https://t.me/+generated-private-link"
    bot.create_chat_invite_link.assert_awaited_once_with(
        -1_009_876_543_210,
        name="Crypto Signal Bot",
    )


async def test_resolve_rejects_unsupported_chat_type() -> None:
    bot = fake_bot(
        chat=SimpleNamespace(
            id=-50,
            type=Chat.GROUP,
            username=None,
            title="Legacy group",
            invite_link=None,
        )
    )

    with pytest.raises(TelegramChannelGatewayError, match="channels and supergroups"):
        await TelegramChannelGateway(bot).resolve_channel("-50")

    bot.get_chat_member.assert_not_awaited()


async def test_resolve_rejects_channel_when_bot_is_not_admin() -> None:
    bot = fake_bot(member=SimpleNamespace(status=ChatMember.MEMBER))

    with pytest.raises(TelegramChannelGatewayError, match="must be an administrator"):
        await TelegramChannelGateway(bot).resolve_channel("publicchannel")


async def test_resolve_maps_telegram_api_error() -> None:
    bot = fake_bot()
    bot.get_chat.side_effect = TelegramError("network failure")

    with pytest.raises(TelegramChannelGatewayError) as exc_info:
        await TelegramChannelGateway(bot).resolve_channel("publicchannel")

    assert isinstance(exc_info.value.__cause__, TelegramError)


@pytest.mark.parametrize(
    ("status", "is_member", "expected"),
    [
        (ChatMember.OWNER, None, True),
        (ChatMember.ADMINISTRATOR, None, True),
        (ChatMember.MEMBER, None, True),
        (ChatMember.RESTRICTED, True, True),
        (ChatMember.RESTRICTED, False, False),
        (ChatMember.LEFT, None, False),
        (ChatMember.BANNED, None, False),
    ],
)
async def test_membership_status_mapping(
    status: str,
    is_member: bool | None,
    expected: bool,
) -> None:
    member = SimpleNamespace(status=status)
    if is_member is not None:
        member.is_member = is_member
    bot = fake_bot(member=member)

    result = await TelegramChannelGateway(bot).is_member(-1001, 123456789)

    assert result is expected
    bot.get_chat_member.assert_awaited_once_with(-1001, 123456789)


async def test_membership_maps_telegram_api_error() -> None:
    bot = fake_bot()
    bot.get_chat_member.side_effect = TelegramError("forbidden")

    with pytest.raises(TelegramChannelGatewayError):
        await TelegramChannelGateway(bot).is_member(-1001, 123456789)
