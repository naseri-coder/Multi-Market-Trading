"""Telegram broadcast adapter tests."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram.error import Forbidden, RetryAfter, TelegramError

from app.integrations.telegram.broadcasts import TelegramBroadcastGateway
from app.modules.broadcasts.entities import BroadcastRecord
from app.modules.broadcasts.errors import (
    BroadcastBlockedError,
    BroadcastDeliveryError,
    BroadcastRetryAfterError,
)
from app.modules.broadcasts.models import BroadcastContentType, BroadcastMediaType


def record(
    *,
    media_type: str | None = None,
    forward: bool = False,
) -> BroadcastRecord:
    timestamp = datetime(2026, 9, 1, tzinfo=UTC)
    is_media = media_type is not None
    return BroadcastRecord(
        id=1,
        created_by_telegram_user_id=2,
        content_type=(
            BroadcastContentType.FORWARD.value
            if forward
            else BroadcastContentType.MEDIA.value
            if is_media
            else BroadcastContentType.TEXT.value
        ),
        text=None if is_media or forward else "Announcement",
        media_type=media_type,
        media_file_id="telegram-file-id" if is_media else None,
        caption="Caption" if is_media else None,
        status="DRAFT",
        total_recipients=0,
        sent_count=0,
        failed_count=0,
        blocked_count=0,
        confirmed_at=None,
        completed_at=None,
        created_at=timestamp,
        updated_at=timestamp,
        source_chat_id=123456789 if forward else None,
        source_message_id=55 if forward else None,
    )


def bot() -> SimpleNamespace:
    return SimpleNamespace(
        send_message=AsyncMock(),
        send_photo=AsyncMock(),
        send_video=AsyncMock(),
        send_document=AsyncMock(),
        send_animation=AsyncMock(),
        send_audio=AsyncMock(),
        send_voice=AsyncMock(),
        forward_message=AsyncMock(),
    )


async def test_text_is_sent_as_a_new_message() -> None:
    telegram = bot()

    await TelegramBroadcastGateway(telegram).send(123, record())

    telegram.send_message.assert_awaited_once_with(chat_id=123, text="Announcement")


@pytest.mark.parametrize("media_type", [item.value for item in BroadcastMediaType])
async def test_each_media_type_uses_its_matching_bot_method(media_type: str) -> None:
    telegram = bot()

    await TelegramBroadcastGateway(telegram).send(123, record(media_type=media_type))

    sender = getattr(telegram, f"send_{media_type.lower()}")
    sender.assert_awaited_once()
    assert sender.await_args.kwargs[media_type.lower()] == "telegram-file-id"
    assert sender.await_args.kwargs["caption"] == "Caption"


async def test_forward_uses_original_source_reference() -> None:
    telegram = bot()

    await TelegramBroadcastGateway(telegram).send(987654321, record(forward=True))

    telegram.forward_message.assert_awaited_once_with(
        chat_id=987654321,
        from_chat_id=123456789,
        message_id=55,
    )


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (Forbidden("blocked"), BroadcastBlockedError),
        (RetryAfter(4), BroadcastRetryAfterError),
        (TelegramError("failed"), BroadcastDeliveryError),
    ],
)
async def test_telegram_errors_are_mapped_without_exposing_raw_details(
    error: TelegramError,
    expected: type[Exception],
) -> None:
    telegram = bot()
    telegram.send_message.side_effect = error

    with pytest.raises(expected):
        await TelegramBroadcastGateway(telegram).send(123, record())
