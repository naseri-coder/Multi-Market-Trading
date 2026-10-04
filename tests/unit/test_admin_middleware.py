"""Security tests for administrator authorization middleware."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.bot.application import build_application
from app.bot.middlewares.admin import admin_required
from app.core.config import Settings


def fake_update(user_id: int | None) -> SimpleNamespace:
    user = SimpleNamespace(id=user_id) if user_id is not None else None
    return SimpleNamespace(
        effective_user=user,
        effective_message=SimpleNamespace(reply_text=AsyncMock()),
        update_id=77,
    )


async def test_configured_admin_reaches_protected_handler() -> None:
    handler = AsyncMock()
    protected = admin_required({123456789})(handler)
    update = fake_update(123456789)
    context = SimpleNamespace()

    await protected(update, context)

    handler.assert_awaited_once_with(update, context)
    update.effective_message.reply_text.assert_not_awaited()


async def test_normal_user_cannot_reach_protected_handler() -> None:
    handler = AsyncMock()
    protected = admin_required({123456789})(handler)
    update = fake_update(987654321)

    await protected(update, SimpleNamespace())

    handler.assert_not_awaited()
    update.effective_message.reply_text.assert_awaited_once()
    assert "اجازه دسترسی" in update.effective_message.reply_text.await_args.args[0]


async def test_missing_telegram_identity_fails_closed() -> None:
    handler = AsyncMock()
    protected = admin_required({123456789})(handler)
    update = fake_update(None)

    await protected(update, SimpleNamespace())

    handler.assert_not_awaited()
    update.effective_message.reply_text.assert_awaited_once()


async def test_empty_admin_allowlist_denies_everyone() -> None:
    handler = AsyncMock()
    protected = admin_required(set())(handler)
    update = fake_update(123456789)

    await protected(update, SimpleNamespace())

    handler.assert_not_awaited()
    update.effective_message.reply_text.assert_awaited_once()


async def test_every_registered_admin_route_denies_a_normal_user(
    valid_token: str,
    valid_database_url: str,
) -> None:
    settings = Settings(
        telegram_bot_token=valid_token,
        database_url=valid_database_url,
        admin_ids={123456789},
        _env_file=None,
    )
    application = build_application(settings)
    admin_handlers = [
        handler
        for handler in application.handlers[0]
        if hasattr(handler.callback, "__wrapped__")
    ]

    assert len(admin_handlers) == 46
    for handler in admin_handlers:
        update = fake_update(987654321)
        await handler.callback(update, SimpleNamespace())
        update.effective_message.reply_text.assert_awaited_once()
        assert "اجازه دسترسی" in update.effective_message.reply_text.await_args.args[0]
