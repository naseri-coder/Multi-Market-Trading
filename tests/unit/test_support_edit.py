"""Telegram duplicate-edit handling for support callbacks."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram.error import BadRequest

from app.bot.handlers.support_edit import safely_edit_support_message


async def test_safe_support_edit_delegates_normal_edit() -> None:
    query = SimpleNamespace(edit_message_text=AsyncMock())

    await safely_edit_support_message(query, "Updated")

    query.edit_message_text.assert_awaited_once_with("Updated", reply_markup=None)


async def test_safe_support_edit_ignores_message_not_modified() -> None:
    query = SimpleNamespace(
        edit_message_text=AsyncMock(
            side_effect=BadRequest("Message is not modified: content is unchanged")
        )
    )

    await safely_edit_support_message(query, "Unchanged")


async def test_safe_support_edit_reraises_other_bad_requests() -> None:
    query = SimpleNamespace(
        edit_message_text=AsyncMock(side_effect=BadRequest("Message cannot be edited"))
    )

    with pytest.raises(BadRequest, match="cannot be edited"):
        await safely_edit_support_message(query, "Updated")
