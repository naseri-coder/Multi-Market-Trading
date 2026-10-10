"""Integrated new product Telegram UI: real Custom, Brooks, owner-only controls."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("telegram")
from telegram.ext import CommandHandler

from naseri_markets.bot_admin_app import (
    build_admin_application, main,
)
from naseri_markets.custom_admin_panel import _token
from naseri_markets.custom_cli import _export_demo
from naseri_markets.engine_control_store import (
    BROOKS_ENGINE_ID, OWNER_CORE_ID, EngineControlStore,
)
from naseri_markets.integrated_engine_panel import IntegratedEnginePanel
from naseri_markets.trusted_custom import LocalCustomRefused, TRUST_ACK


@pytest.fixture
def setup(tmp_path):
    sample = _export_demo(tmp_path / "public_demo")
    state_dir = tmp_path / "private-state"
    with EngineControlStore(state_dir, owner_visible=True) as store:
        assert store.get(BROOKS_ENGINE_ID).engine_kind == "BUILTIN_BROOKS"
        assert not store.get(BROOKS_ENGINE_ID).enabled
        store.register_owner_reference(engine_id=OWNER_CORE_ID, actor_id=123)
        store.host.register(
            tmp_path / "public_demo" / "descriptor.json",
            tmp_path / "public_demo" / "public_toy_demo.py",
            descriptor_sha256=sample["descriptor_sha256"],
            code_sha256=sample["code_sha256"], trust_ack=TRUST_ACK)
    return state_dir, sample, tmp_path / "public_demo/quote.json"


def fake(*, user=123, chat=123, chat_type="private", data=None, value=None):
    message = SimpleNamespace(reply_text=AsyncMock(), text=value)
    query = SimpleNamespace(data=data, answer=AsyncMock(), message=message)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=user),
        effective_chat=SimpleNamespace(id=chat, type=chat_type),
        effective_message=message, callback_query=query if data is not None else None)
    bot = SimpleNamespace(get_chat=AsyncMock(), get_chat_member=AsyncMock(),
                          get_me=AsyncMock(), send_message=AsyncMock())
    context = SimpleNamespace(user_data={}, bot=bot)
    return update, context, message, query


def test_brooks_visible_actual_legacy_unmounted_and_owner_private_absent(setup):
    state, sample, quote = setup
    with EngineControlStore(state, owner_visible=False) as public:
        ids = {x.engine_id for x in public.list()}
        assert BROOKS_ENGINE_ID in ids and "public_toy_demo" in ids
        assert OWNER_CORE_ID not in ids
        assert public.get(OWNER_CORE_ID) is None
        with pytest.raises(LocalCustomRefused, match="UNKNOWN_OR_PRIVATE"):
            public.preferences(OWNER_CORE_ID)
        with pytest.raises(LocalCustomRefused, match="OWNER_ONLY"):
            public.register_owner_reference(engine_id=OWNER_CORE_ID, actor_id=234)
        brooks = public.get(BROOKS_ENGINE_ID)
        assert not brooks.enabled
        assert brooks.engine_kind == "BUILTIN_BROOKS"
        assert brooks.runtime_status == "RUNTIME_NOT_MOUNTED"
        assert public.route(BROOKS_ENGINE_ID)["delivery_mode"] == "DISABLED"
    with EngineControlStore(state, owner_visible=True) as private:
        nyfr = private.get(OWNER_CORE_ID)
        assert nyfr.engine_kind == "OWNER_CUSTOM"
        assert nyfr.runtime_status == "RUNTIME_NOT_MOUNTED"
        assert not nyfr.enabled


def test_per_engine_prefs_persist_and_legacy_brooks_is_never_executed(setup):
    state, sample, quote = setup
    with EngineControlStore(state, owner_visible=True) as store:
        before = store.preferences(BROOKS_ENGINE_ID)
        assert before["signal_environment"] == "OFF"
        changed = store.change_preference(
            BROOKS_ENGINE_ID, field="timeframe", value="1h",
            expected_revision=before["revision"], actor_id=123)
        assert changed["timeframe"] == "1h"
        assert changed["timeframe_runtime_applied"] is False
        requested = store.toggle_as_admin(
            BROOKS_ENGINE_ID, enabled=True, expected_revision=1, actor_id=123)
        assert requested.requested_enabled
        assert not requested.enabled
        assert requested.runtime_status == "RUNTIME_NOT_MOUNTED"
        with pytest.raises(LocalCustomRefused, match="STALE"):
            store.toggle_as_admin(
                BROOKS_ENGINE_ID, enabled=True, expected_revision=1, actor_id=123)
        nyfr = store.toggle_as_admin(
            OWNER_CORE_ID, enabled=True, expected_revision=1, actor_id=123)
        assert nyfr.requested_enabled
        assert not nyfr.enabled
        assert nyfr.engine_kind == "OWNER_CUSTOM"
        assert store.signals(OWNER_CORE_ID) == []
        assert store.signals(BROOKS_ENGINE_ID) == []
    with EngineControlStore(state, owner_visible=False) as nonowner:
        assert nonowner.get(OWNER_CORE_ID) is None
        assert nonowner.get(BROOKS_ENGINE_ID).requested_enabled
        assert nonowner.preferences(BROOKS_ENGINE_ID)["timeframe"] == "1h"


def test_public_custom_settings_off_and_market_gated_at_real_paper_execution(setup):
    state, sample, quote = setup
    with EngineControlStore(state, owner_visible=False) as store:
        store.toggle_as_admin(
            "public_toy_demo", enabled=True, expected_revision=1,
            descriptor_sha256=sample["descriptor_sha256"], actor_id=234)
        prefs = store.preferences("public_toy_demo")
        assert prefs["signal_environment"] == "PAPER"
        store.change_preference(
            "public_toy_demo", field="signal_environment", value="OFF",
            expected_revision=prefs["revision"], actor_id=234)
        with pytest.raises(LocalCustomRefused, match="PAPER_ENVIRONMENT_DISABLED"):
            store.host.paper("public_toy_demo", quote.read_bytes())
        assert store.host.signals() == []
        prefs = store.preferences("public_toy_demo")
        store.change_preference(
            "public_toy_demo", field="signal_environment", value="PAPER",
            expected_revision=prefs["revision"], actor_id=234)
        prefs = store.preferences("public_toy_demo")
        store.change_preference(
            "public_toy_demo", field="market_scope", value="forex",
            expected_revision=prefs["revision"], actor_id=234)
        with pytest.raises(LocalCustomRefused, match="MARKET_SCOPE_BLOCKED"):
            store.host.paper("public_toy_demo", quote.read_bytes())
        assert store.host.signals() == []
        prefs = store.preferences("public_toy_demo")
        store.change_preference(
            "public_toy_demo", field="market_scope", value="index",
            expected_revision=prefs["revision"], actor_id=234)
        assert store.host.paper("public_toy_demo", quote.read_bytes())["stored"] == 1
        assert len(store.host.signals()) == 1


def test_owner_only_preference_cannot_be_changed_from_nonowner_store(setup):
    state, _, _ = setup
    with EngineControlStore(state, owner_visible=False) as store:
        with pytest.raises(LocalCustomRefused, match="UNKNOWN_OR_PRIVATE"):
            store.change_preference(
                OWNER_CORE_ID, field="timeframe", value="5m",
                expected_revision=1, actor_id=234)
        with pytest.raises(LocalCustomRefused, match="UNKNOWN_OR_PRIVATE"):
            store.toggle_as_admin(
                OWNER_CORE_ID, enabled=True, expected_revision=1, actor_id=234)
        with pytest.raises(LocalCustomRefused, match="UNKNOWN_OR_PRIVATE"):
            store.set_route(
                OWNER_CORE_ID, channel_id=-1001234567890, channel_title="owner",
                actor_id=234, verified_private_channel=True)


@pytest.mark.parametrize("field,value", [
    ("signal_environment", "LIVE"),
    ("signal_environment", "FORWARD"),
    ("market_scope", "broker"),
    ("timeframe", "10s"),
    ("stop_loss", "-1"),
])
def test_settings_fail_closed_no_live_trading_or_threshold_mutation(setup, field, value):
    state, _, _ = setup
    with EngineControlStore(state, owner_visible=True) as store:
        with pytest.raises(LocalCustomRefused, match="SETTING_ALLOWLIST"):
            store.change_preference(
                BROOKS_ENGINE_ID, field=field, value=value,
                expected_revision=1, actor_id=123)
        assert store.preferences(BROOKS_ENGINE_ID)["revision"] == 1
        assert store.admin_history(BROOKS_ENGINE_ID) == []


@pytest.mark.asyncio
async def test_private_telegram_manager_list_nonowner_no_nyfr_owner_visible(setup):
    state, _, _ = setup
    panel = IntegratedEnginePanel(
        state_dir=state, admin_ids={123, 234}, owner_ids={123})
    admin, context, message, _ = fake(user=234, chat=234)
    await panel.panel(admin, context)
    assert message.reply_text.await_count == 1
    markup = message.reply_text.await_args.kwargs["reply_markup"]
    callbacks = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert f"cm:open:{_token(BROOKS_ENGINE_ID)}" in callbacks
    assert f"cm:open:{_token(OWNER_CORE_ID)}" not in callbacks
    owner, context2, message2, _ = fake()
    await panel.panel(owner, context2)
    owner_markup = message2.reply_text.await_args.kwargs["reply_markup"]
    owner_buttons = [b.callback_data for row in owner_markup.inline_keyboard for b in row]
    assert f"cm:open:{_token(OWNER_CORE_ID)}" in owner_buttons


@pytest.mark.asyncio
async def test_private_owner_callback_leak_attempt_denied(setup):
    state, _, _ = setup
    panel = IntegratedEnginePanel(
        state_dir=state, admin_ids={123, 234}, owner_ids={123})
    nonowner, context, message, query = fake(
        user=234, chat=234, data=f"cm:open:{_token(OWNER_CORE_ID)}")
    await panel.callback(nonowner, context)
    assert message.reply_text.await_count == 1
    assert "NY First-Reversal" not in message.reply_text.await_args.args[0]
    with EngineControlStore(state, owner_visible=False) as store:
        assert store.get(OWNER_CORE_ID) is None


@pytest.mark.asyncio
async def test_brooks_toggles_and_per_engine_settings_in_telegram(setup):
    state, _, _ = setup
    panel = IntegratedEnginePanel(state_dir=state, admin_ids={123}, owner_ids={123})
    token = _token(BROOKS_ENGINE_ID)
    update, context, msg, query = fake(data=f"cm:enable:{token}:1")
    await panel.callback(update, context)
    with EngineControlStore(state, owner_visible=True) as store:
        s = store.get(BROOKS_ENGINE_ID)
        assert s.requested_enabled and not s.enabled
        assert s.revision == 2
    update, context, msg, query = fake(data=f"em:settings:{token}")
    await panel.callback(update, context)
    assert "تایم‌فریم" in msg.reply_text.await_args.args[0]
    update, context, msg, query = fake(data=f"em:tf:{token}:1")
    await panel.callback(update, context)
    with EngineControlStore(state, owner_visible=True) as store:
        assert store.preferences(BROOKS_ENGINE_ID)["timeframe"] == "1h"
        assert store.preferences(BROOKS_ENGINE_ID)["revision"] == 2
    await panel.callback(update, context)  # replay stale callback
    with EngineControlStore(state, owner_visible=True) as store:
        assert store.preferences(BROOKS_ENGINE_ID)["revision"] == 2
    update, context, _, _ = fake(data=f"cm:disable:{token}:2")
    await panel.callback(update, context)
    with EngineControlStore(state, owner_visible=True) as store:
        assert not store.get(BROOKS_ENGINE_ID).requested_enabled
        assert not store.get(BROOKS_ENGINE_ID).enabled
        assert store.admin_history(BROOKS_ENGINE_ID)[0]["action"] == (
            "REQUEST_DISABLE_NOT_CONNECTED")


@pytest.mark.asyncio
async def test_owner_custom_disable_and_settings_never_execute_private_code(setup):
    state, _, _ = setup
    panel = IntegratedEnginePanel(state_dir=state, admin_ids={123}, owner_ids={123})
    token = _token(OWNER_CORE_ID)
    up, ctx, msg, q = fake(data=f"cm:enable:{token}:1")
    await panel.callback(up, ctx)
    with EngineControlStore(state, owner_visible=True) as store:
        s = store.get(OWNER_CORE_ID)
        assert s.requested_enabled and not s.enabled
        assert "RUNTIME_NOT_MOUNTED" == s.runtime_status
        assert store.host.get(OWNER_CORE_ID) is None
    up, ctx, msg, q = fake(data=f"em:env:{token}:1")
    await panel.callback(up, ctx)
    with EngineControlStore(state, owner_visible=True) as store:
        assert store.preferences(OWNER_CORE_ID)["signal_environment"] == "PAPER"
        assert store.host.get(OWNER_CORE_ID) is None


@pytest.mark.asyncio
async def test_unauthorized_group_or_unlisted_cannot_access_engine_settings(setup):
    state, _, _ = setup
    panel = IntegratedEnginePanel(state_dir=state, admin_ids={123}, owner_ids={123})
    token = _token(BROOKS_ENGINE_ID)
    for user, chat, kind in [(234, 234, "private"), (123, -1001234567890, "group")]:
        up, ctx, msg, query = fake(
            user=user, chat=chat, chat_type=kind, data=f"em:tf:{token}:1")
        await panel.callback(up, ctx)
        assert msg.reply_text.await_count == 0
        assert query.answer.await_count == 1
    with EngineControlStore(state, owner_visible=True) as store:
        assert store.preferences(BROOKS_ENGINE_ID)["revision"] == 1


@pytest.mark.asyncio
async def test_per_engine_private_destination_and_zero_channel_send(setup):
    state, _, _ = setup
    panel = IntegratedEnginePanel(state_dir=state, admin_ids={123}, owner_ids={123})
    token = _token(BROOKS_ENGINE_ID)
    up, ctx, msg, q = fake(data=f"cm:route:{token}")
    await panel.callback(up, ctx)
    assert "mmt_custom_admin_pending" in ctx.user_data
    ctx.bot.get_chat.return_value = SimpleNamespace(
        type="channel", title="Private Brooks Channel", username=None)
    ctx.bot.get_me.return_value = SimpleNamespace(id=9000)
    ctx.bot.get_chat_member.return_value = SimpleNamespace(
        status="administrator", can_post_messages=True)
    up2, _, msg2, _ = fake(value="-1001234567890")
    await panel.route_input(up2, ctx)
    with EngineControlStore(state, owner_visible=True) as store:
        assert store.route(BROOKS_ENGINE_ID)["channel_id"] == -1001234567890
        assert store.route(BROOKS_ENGINE_ID)["delivery_mode"] == "DISABLED"
        assert store.route(OWNER_CORE_ID)["channel_id"] is None
        assert store.route("public_toy_demo")["channel_id"] is None
    ctx.bot.send_message.assert_not_awaited()


def test_bot_application_integration_mounts_same_telegram_application(setup):
    state, _, _ = setup
    app = build_admin_application(
        token="123456:VALID_TEST_ONLY_NOT_A_REAL_TOKEN",
        state_dir=state, admin_ids={123, 234}, owner_ids={123},
        owner_reference=True)
    handlers = [h for group in app.handlers.values() for h in group]
    commands = set().union(*(h.commands for h in handlers
                             if isinstance(h, CommandHandler)))
    assert {"custom", "engines"}.issubset(commands)
    assert app.updater is not None
    with EngineControlStore(state, owner_visible=False) as public:
        assert public.get(OWNER_CORE_ID) is None


def test_nonproduction_launcher_offline_check_no_bot_token_or_network(setup, capsys, monkeypatch):
    state, _, _ = setup
    monkeypatch.delenv("MMT_DEV_BOT_TOKEN", raising=False)
    assert main(["--check", "--state-dir", str(state),
                 "--admin-ids", "123", "--owner-ids", "123"]) == 0
    answer = json.loads(capsys.readouterr().out)
    assert answer["brooks_reference_listed"]
    assert not answer["telegram_connected"]
    assert not answer["live_signals_enabled"]
    assert not answer["custom_private_code_loaded"]
    assert main(["--nonproduction-poll", "--state-dir", str(state),
                 "--admin-ids", "123", "--owner-ids", "123"]) == 2


def test_no_private_nyfr_source_or_distribution_bundle_imported():
    import ast
    import inspect
    import naseri_markets.engine_control_store as store
    import naseri_markets.integrated_engine_panel as panel
    import naseri_markets.bot_admin_app as application
    for module in (store, panel, application):
        code = inspect.getsource(module)
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert (node.module or "").split(".")[0] not in (
                    "production_source", "brooks_core")
        assert "Ed25519PrivateKey" not in code
        assert "private_nyfr_core" not in code
        assert "subprocess.run" not in code
