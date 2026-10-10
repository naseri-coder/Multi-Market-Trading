"""Private Telegram engine selectors: safe paging, explicit CAS and no leaks."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("telegram")
from telegram.ext import CallbackQueryHandler

from naseri_markets.bot_admin_app import build_admin_application
from naseri_markets.custom_admin_panel import _token
from naseri_markets.engine_control_store import BROOKS_ENGINE_ID, EngineControlStore
from naseri_markets.integrated_engine_panel import IntegratedEnginePanel


def update(data, *, user=123, chat=123):
    msg = SimpleNamespace(reply_text=AsyncMock())
    callback = SimpleNamespace(data=data, message=msg, answer=AsyncMock())
    obj = SimpleNamespace(
        callback_query=callback, effective_user=SimpleNamespace(id=user),
        effective_chat=SimpleNamespace(type="private", id=chat))
    return obj, msg


def test_exchanges_are_all_reachable_by_four_pages_and_revision_bounded(tmp_path):
    panel = IntegratedEnginePanel(
        state_dir=tmp_path / "state", admin_ids={123}, owner_ids={123})
    token = _token(BROOKS_ENGINE_ID)
    with EngineControlStore(tmp_path / "state") as host:
        exchange_options = []
        for page in range(4):
            markup = panel.exchange_keyboard(host, BROOKS_ENGINE_ID, page)
            callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
            exchange_options.extend(x for x in callbacks if x.startswith("ex:set:"))
            assert all(len(x) <= 64 for x in callbacks)
        assert len(exchange_options) == len(set(exchange_options)) == 20
        assert exchange_options[0] == f"ex:set:{token}:0:1"
        assert exchange_options[-1] == f"ex:set:{token}:19:1"
        tf = panel.timeframe_keyboard(host, BROOKS_ENGINE_ID)
        choices = [b.callback_data for row in tf.inline_keyboard for b in row
                   if b.callback_data.startswith("et:set:")]
        assert len(set(choices)) == 8
        settings = panel.settings_keyboard(host, BROOKS_ENGINE_ID)
        actions = [b.callback_data for row in settings.inline_keyboard for b in row]
        assert f"ex:list:{token}:0" in actions
        assert f"et:list:{token}" in actions


def test_private_real_application_mounts_new_buttons(tmp_path):
    app = build_admin_application(
        token="123456:NONPRODUCTION_TEST_TOKEN",
        state_dir=tmp_path / "state", admin_ids={123}, owner_ids={123})
    handlers = [
        h for group in app.handlers.values() for h in group
        if isinstance(h, CallbackQueryHandler)]
    assert any(h.pattern.match("ex:list:123456abcdef:0") for h in handlers)
    assert any(h.pattern.match("et:list:123456abcdef") for h in handlers)


@pytest.mark.asyncio
async def test_admin_exchange_then_timeframe_persist_cas_no_telegram_send(tmp_path):
    path = tmp_path / "state"
    panel = IntegratedEnginePanel(state_dir=path, admin_ids={123}, owner_ids={123})
    token = _token(BROOKS_ENGINE_ID)
    forbidden, msg = update(f"ex:set:{token}:11:1", user=999, chat=999)
    await panel.callback(forbidden, SimpleNamespace())
    msg.reply_text.assert_not_awaited()
    with EngineControlStore(path) as host:
        assert host.preferences(BROOKS_ENGINE_ID)["futures_exchange"] == "kraken"

    click, msg = update(f"ex:set:{token}:11:1")
    await panel.callback(click, SimpleNamespace())
    assert "LBank" in msg.reply_text.await_args.args[0]
    with EngineControlStore(path) as host:
        assert host.preferences(BROOKS_ENGINE_ID)["futures_exchange"] == "lbank"
        assert host.preferences(BROOKS_ENGINE_ID)["revision"] == 2
    await panel.callback(click, SimpleNamespace())
    with EngineControlStore(path) as host:
        assert host.preferences(BROOKS_ENGINE_ID)["revision"] == 2

    click, msg = update(f"et:set:{token}:6:2")
    await panel.callback(click, SimpleNamespace())
    assert "12h" in msg.reply_text.await_args.args[0]
    with EngineControlStore(path) as host:
        assert host.preferences(BROOKS_ENGINE_ID)["timeframe"] == "12h"
        assert host.preferences(BROOKS_ENGINE_ID)["revision"] == 3
        assert host.route(BROOKS_ENGINE_ID)["delivery_mode"] == "DISABLED"
        assert host.publication(BROOKS_ENGINE_ID)["effective_publication"] is False

    click, msg = update(f"ex:set:{token}:30:3")
    await panel.callback(click, SimpleNamespace())
    assert "نامعتبر" in msg.reply_text.await_args.args[0]
    with EngineControlStore(path) as host:
        assert host.preferences(BROOKS_ENGINE_ID)["revision"] == 3
