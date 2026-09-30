"""Favorites Telegram rendering, callback, and registration tests."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from telegram.error import BadRequest
from telegram.ext import CallbackQueryHandler

from app.bot.handlers import favorites_user
from app.bot.keyboards.favorites import (
    FAVORITES_CALLBACK_PATTERN,
    build_favorite_detail_actions,
    build_favorite_toggle_button,
    build_favorites_list,
)
from app.modules.favorites.entities import FavoriteMutation, FavoritePage
from app.modules.signals.entities import SignalDetail, SignalRecord

NOW = datetime(2026, 9, 1, 20, tzinfo=UTC)


def signal(signal_id: int = 7) -> SignalRecord:
    return SignalRecord(
        id=signal_id,
        symbol="BTC/USDT",
        direction="LONG",
        entry_price=Decimal("100.000000000000000000"),
        stop_loss=Decimal("90"),
        leverage=Decimal("5"),
        status="OPEN",
        description=None,
        profit_loss=None,
        created_at=NOW,
        updated_at=NOW,
        closed_at=None,
    )


def page(*signals: SignalRecord, current: int = 1, total_pages: int = 1) -> FavoritePage:
    return FavoritePage(
        signals=signals,
        page=current,
        page_size=10,
        total_items=len(signals),
        total_pages=total_pages,
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
                "report_timezone": "Asia/Tehran",
            }
        ),
    )


def test_favorite_callbacks_are_exact_bounded_and_tamper_resistant() -> None:
    valid = (
        "v1:favorites:user:menu",
        "v1:favorites:user:list:2",
        "v1:favorites:user:view:2:7:1",
        "v1:favorites:user:toggle:add:open:2:7:1",
        "v1:favorites:user:toggle:remove:favorites:2:7:1",
    )
    assert all(re.fullmatch(FAVORITES_CALLBACK_PATTERN, item) for item in valid)
    assert re.fullmatch(FAVORITES_CALLBACK_PATTERN, f"{valid[-1]}:tampered") is None
    assert re.fullmatch(FAVORITES_CALLBACK_PATTERN, "v1:favorites:user:list:0") is None
    assert all(len(item.encode()) <= 64 for item in valid)


def test_favorite_keyboards_expose_toggle_pagination_and_back_actions() -> None:
    add = build_favorite_toggle_button(
        7,
        is_favorite=False,
        source="open",
        list_page=2,
        target_page=1,
    )
    remove = build_favorite_toggle_button(
        7,
        is_favorite=True,
        source="favorites",
        list_page=2,
        target_page=1,
    )
    listing = build_favorites_list([(7, "BTC")], page=2, total_pages=3)
    detail = build_favorite_detail_actions(
        7,
        list_page=2,
        target_page=2,
        total_target_pages=3,
        is_favorite=True,
    )

    assert add.callback_data == "v1:favorites:user:toggle:add:open:2:7:1"
    assert remove.callback_data == "v1:favorites:user:toggle:remove:favorites:2:7:1"
    assert "افزودن" in add.text
    assert "حذف" in remove.text
    list_callbacks = [button.callback_data for row in listing.inline_keyboard for button in row]
    detail_callbacks = [button.callback_data for row in detail.inline_keyboard for button in row]
    assert "v1:favorites:user:list:1" in list_callbacks
    assert "v1:favorites:user:list:3" in list_callbacks
    assert detail_callbacks[-1] == "v1:favorites:user:list:2"


def test_favorite_page_renderer_handles_empty_and_formats_decimal() -> None:
    empty_text, _ = favorites_user.render_favorite_page(page())
    text, _ = favorites_user.render_favorite_page(page(signal()))

    assert "هنوز سیگنالی" in empty_text
    assert "🎯 ورود: 100" in text
    assert "100.000000000000000000" not in text


async def test_menu_checks_access_and_loads_first_page(monkeypatch) -> None:
    current_update = update()
    current_context = context()
    database = object()
    loader = AsyncMock(return_value=page(signal()))
    monkeypatch.setattr(
        favorites_user,
        "_prepare_favorite_access",
        AsyncMock(return_value=42),
    )
    monkeypatch.setattr(favorites_user, "get_database_manager", lambda value: database)
    monkeypatch.setattr(favorites_user, "load_favorite_page", loader)

    await favorites_user.favorites_menu_handler(current_update, current_context)

    loader.assert_awaited_once_with(database, 42, page=1)
    current_update.effective_message.reply_text.assert_awaited_once()


async def test_missing_access_stops_before_favorite_query(monkeypatch) -> None:
    current_update = update()
    loader = AsyncMock()
    monkeypatch.setattr(
        favorites_user,
        "_prepare_favorite_access",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(favorites_user, "load_favorite_page", loader)

    await favorites_user.favorites_menu_handler(current_update, context())

    loader.assert_not_awaited()
    current_update.effective_message.reply_text.assert_not_awaited()


async def test_list_callback_answers_and_edits_same_message(monkeypatch) -> None:
    current_update = update("v1:favorites:user:list:2")
    database = object()
    loader = AsyncMock(return_value=page(signal(), current=2, total_pages=2))
    monkeypatch.setattr(
        favorites_user,
        "_prepare_favorite_access",
        AsyncMock(return_value=42),
    )
    monkeypatch.setattr(favorites_user, "get_database_manager", lambda value: database)
    monkeypatch.setattr(favorites_user, "load_favorite_page", loader)

    await favorites_user.favorites_callback_handler(current_update, context())

    current_update.callback_query.answer.assert_awaited_once()
    loader.assert_awaited_once_with(database, 42, page=2)
    current_update.callback_query.edit_message_text.assert_awaited_once()


async def test_toggle_from_signal_detail_updates_star_state(monkeypatch) -> None:
    current_update = update("v1:favorites:user:toggle:add:open:2:7:1")
    database = object()
    detail = SignalDetail(
        signal=signal(),
        targets=(),
        target_page=1,
        target_page_size=5,
        total_targets=0,
        total_target_pages=1,
    )
    mutation = AsyncMock(
        return_value=FavoriteMutation(signal_id=7, is_favorite=True, changed=True)
    )
    monkeypatch.setattr(
        favorites_user,
        "_prepare_favorite_access",
        AsyncMock(return_value=42),
    )
    monkeypatch.setattr(favorites_user, "get_database_manager", lambda value: database)
    monkeypatch.setattr(favorites_user, "mutate_favorite", mutation)
    monkeypatch.setattr(
        favorites_user,
        "load_signal_detail",
        AsyncMock(return_value=detail),
    )
    monkeypatch.setattr(
        favorites_user,
        "load_favorite_status",
        AsyncMock(return_value=True),
    )

    await favorites_user.favorites_callback_handler(current_update, context())

    mutation.assert_awaited_once_with(database, 42, 7, action="add")
    keyboard = current_update.callback_query.edit_message_text.await_args.kwargs[
        "reply_markup"
    ]
    assert "حذف از علاقه‌مندی‌ها" in keyboard.inline_keyboard[0][0].text


async def test_duplicate_callback_edit_is_harmless() -> None:
    query = SimpleNamespace(
        edit_message_text=AsyncMock(
            side_effect=BadRequest("Message is not modified")
        )
    )

    await favorites_user._safe_edit_favorite_message(query, "same")

    query.edit_message_text.assert_awaited_once()


def test_registration_uses_one_anchored_favorite_callback_handler() -> None:
    application = SimpleNamespace(add_handler=Mock())

    favorites_user.register_favorites_user_handlers(application)

    handlers = [call.args[0] for call in application.add_handler.call_args_list]
    assert len(handlers) == 3
    callback = handlers[-1]
    assert isinstance(callback, CallbackQueryHandler)
    assert callback.pattern.fullmatch("v1:favorites:user:list:open:1") is None
    assert callback.pattern.fullmatch("v1:favorites:user:list:1")
