"""Notification settings Telegram adapter and callback tests."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from telegram.error import BadRequest
from telegram.ext import CallbackQueryHandler

from app.bot.handlers import notification_settings_user
from app.bot.keyboards.notifications import (
    NOTIFICATION_SETTINGS_CALLBACK_PATTERN,
    build_notification_settings_keyboard,
)
from app.modules.notifications.entities import NotificationPreference
from app.modules.notifications.models import NotificationType
from app.modules.notifications.service import SUPPORTED_NOTIFICATION_TYPES

NOW = datetime(2026, 9, 2, 1, tzinfo=UTC)


def preferences(
    *,
    disabled: frozenset[str] = frozenset(),
) -> tuple[NotificationPreference, ...]:
    return tuple(
        NotificationPreference(
            notification_type=notification_type,
            is_enabled=notification_type not in disabled,
            created_at=NOW,
            updated_at=NOW,
        )
        for notification_type in SUPPORTED_NOTIFICATION_TYPES
    )


def update(callback_data: str | None = None) -> SimpleNamespace:
    message = SimpleNamespace(reply_text=AsyncMock())
    query = None
    if callback_data is not None:
        query = SimpleNamespace(
            data=callback_data,
            answer=AsyncMock(),
            edit_message_text=AsyncMock(),
            message=message,
        )
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=123456789),
        effective_message=message,
        callback_query=query,
    )


def context() -> SimpleNamespace:
    return SimpleNamespace(
        user_data={},
        application=SimpleNamespace(
            bot_data={
                "database": object(),
                "admin_ids": frozenset(),
            }
        ),
    )


def test_callbacks_are_exact_versioned_and_bounded() -> None:
    valid = [
        "v1:notifications:user:menu",
        *(
            f"v1:notifications:user:set:disable:{notification_type}"
            for notification_type in SUPPORTED_NOTIFICATION_TYPES
        ),
        *(
            f"v1:notifications:user:set:enable:{notification_type}"
            for notification_type in SUPPORTED_NOTIFICATION_TYPES
        ),
    ]

    assert all(
        re.fullmatch(NOTIFICATION_SETTINGS_CALLBACK_PATTERN, item)
        for item in valid
    )
    assert all(len(item.encode()) <= 64 for item in valid)
    assert (
        re.fullmatch(
            NOTIFICATION_SETTINGS_CALLBACK_PATTERN,
            f"{valid[-1]}:tampered",
        )
        is None
    )
    assert (
        re.fullmatch(
            NOTIFICATION_SETTINGS_CALLBACK_PATTERN,
            "v1:notifications:user:set:disable:EMAIL",
        )
        is None
    )


def test_renderer_and_keyboard_show_all_six_states_and_back_action() -> None:
    current = preferences(disabled=frozenset({NotificationType.STOP_HIT.value}))

    text, keyboard = (
        notification_settings_user.render_notification_preferences(current)
    )
    callbacks = [
        button.callback_data
        for row in keyboard.inline_keyboard
        for button in row
    ]

    assert "📡 سیگنال جدید: ✅ فعال" in text
    assert "🛑 برخورد به حد ضرر: ⛔ غیرفعال" in text
    assert len(keyboard.inline_keyboard) == 7
    assert callbacks[0] == "v1:notifications:user:set:disable:NEW_SIGNAL"
    assert callbacks[2] == "v1:notifications:user:set:enable:STOP_HIT"
    assert callbacks[-1] == "v1:notifications:user:menu"


def test_keyboard_rejects_unknown_preference_type() -> None:
    unknown = (
        NotificationPreference(
            notification_type="EMAIL",
            is_enabled=True,
            created_at=NOW,
            updated_at=NOW,
        ),
    )

    with pytest.raises(KeyError):
        build_notification_settings_keyboard(unknown)


async def test_menu_checks_access_and_loads_preferences(monkeypatch) -> None:
    current_update = update()
    database = object()
    loader = AsyncMock(return_value=preferences())
    monkeypatch.setattr(
        notification_settings_user,
        "_prepare_notification_settings_access",
        AsyncMock(return_value=42),
    )
    monkeypatch.setattr(
        notification_settings_user,
        "get_database_manager",
        lambda value: database,
    )
    monkeypatch.setattr(
        notification_settings_user,
        "load_notification_preferences",
        loader,
    )

    await notification_settings_user.notification_settings_menu_handler(
        current_update,
        context(),
    )

    loader.assert_awaited_once_with(database, 42)
    current_update.effective_message.reply_text.assert_awaited_once()


async def test_missing_access_stops_before_query(monkeypatch) -> None:
    current_update = update()
    loader = AsyncMock()
    monkeypatch.setattr(
        notification_settings_user,
        "_prepare_notification_settings_access",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        notification_settings_user,
        "load_notification_preferences",
        loader,
    )

    await notification_settings_user.notification_settings_menu_handler(
        current_update,
        context(),
    )

    loader.assert_not_awaited()
    current_update.effective_message.reply_text.assert_not_awaited()


async def test_disable_callback_persists_explicit_state_and_redraws(
    monkeypatch,
) -> None:
    current_update = update(
        "v1:notifications:user:set:disable:NEW_SIGNAL"
    )
    database = object()
    updated = preferences(
        disabled=frozenset({NotificationType.NEW_SIGNAL.value})
    )
    setter = AsyncMock(return_value=updated)
    monkeypatch.setattr(
        notification_settings_user,
        "_prepare_notification_settings_access",
        AsyncMock(return_value=42),
    )
    monkeypatch.setattr(
        notification_settings_user,
        "get_database_manager",
        lambda value: database,
    )
    monkeypatch.setattr(
        notification_settings_user,
        "set_notification_preference",
        setter,
    )

    await notification_settings_user.notification_settings_callback_handler(
        current_update,
        context(),
    )

    current_update.callback_query.answer.assert_awaited_once_with(
        "در حال ذخیره..."
    )
    setter.assert_awaited_once_with(
        database,
        42,
        NotificationType.NEW_SIGNAL.value,
        is_enabled=False,
    )
    edit = current_update.callback_query.edit_message_text
    edit.assert_awaited_once()
    assert "📡 سیگنال جدید: ⛔ غیرفعال" in edit.await_args.args[0]


async def test_duplicate_callback_edit_is_harmless() -> None:
    query = SimpleNamespace(
        edit_message_text=AsyncMock(
            side_effect=BadRequest("Message is not modified")
        )
    )

    await notification_settings_user._safe_edit_notification_message(
        query,
        "same",
    )

    query.edit_message_text.assert_awaited_once()


def test_registration_has_one_anchored_callback_handler() -> None:
    application = SimpleNamespace(add_handler=Mock())

    notification_settings_user.register_notification_settings_user_handlers(
        application
    )

    handlers = [call.args[0] for call in application.add_handler.call_args_list]
    assert len(handlers) == 3
    callback = handlers[-1]
    assert isinstance(callback, CallbackQueryHandler)
    assert callback.pattern.fullmatch(
        "v1:notifications:user:set:disable:NEW_SIGNAL"
    )
    assert callback.pattern.fullmatch(
        "v1:notifications:user:set:disable:NEW_SIGNAL:tampered"
    ) is None
