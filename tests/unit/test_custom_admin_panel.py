"""Custom Telegram admin panel: real local PAPER state and fake Bot API, no sends."""
from __future__ import annotations

import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("telegram")
from telegram.ext import Application, CallbackQueryHandler, CommandHandler

from naseri_markets.custom_admin_panel import (
    MENU_LABEL, AdminCustomPanelRefused, CustomAdminPanel, _token,
)
from naseri_markets.custom_cli import _export_demo
from naseri_markets.trusted_custom import (
    LocalCustomRefused, TRUST_ACK, TrustedLocalCustomHost,
)


@pytest.fixture
def panel(tmp_path):
    sample = _export_demo(tmp_path / "public-toy")
    state = tmp_path / "private"
    with TrustedLocalCustomHost(state) as h:
        h.register(
            tmp_path / "public-toy" / "descriptor.json",
            tmp_path / "public-toy" / "public_toy_demo.py",
            descriptor_sha256=sample["descriptor_sha256"],
            code_sha256=sample["code_sha256"], trust_ack=TRUST_ACK)
    return CustomAdminPanel(state_dir=state, admin_ids={123}), sample, state


def rig(*, user=123, chat=123, type="private", data=None, text=None):
    message = SimpleNamespace(reply_text=AsyncMock(), text=text)
    query = SimpleNamespace(data=data, answer=AsyncMock(), message=message)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=user),
        effective_chat=SimpleNamespace(id=chat, type=type),
        effective_message=message,
        callback_query=query if data is not None else None)
    bot = SimpleNamespace(get_chat=AsyncMock(), get_me=AsyncMock(),
                          get_chat_member=AsyncMock(), send_message=AsyncMock())
    context = SimpleNamespace(user_data={}, bot=bot)
    return update, context, message, query


def test_admin_menu_registration_reuses_existing_application_without_polling(panel):
    owner, sample, state = panel
    app = Application.builder().token("123456:TEST_TOKEN_NONPRODUCTION").build()
    owner.register(app)
    handlers = [h for group in app.handlers.values() for h in group]
    assert any(isinstance(h, CommandHandler) and "custom" in h.commands for h in handlers)
    assert any(isinstance(h, CallbackQueryHandler) for h in handlers)
    assert MENU_LABEL == "🎛 مدیریت هسته‌های Custom"
    with TrustedLocalCustomHost(state) as host:
        assert "public_toy_demo" in owner.summary(host)
        assert host.get("public_toy_demo").enabled is False
        assert not host.route("public_toy_demo")["live_publication_enabled"]


@pytest.mark.asyncio
async def test_admin_list_toggle_disable_audit_and_replay_reject(panel):
    owner, sample, path = panel
    update, context, message, query = rig()
    await owner.panel(update, context)
    assert message.reply_text.await_count == 1
    token = _token("public_toy_demo")
    update, context, message, query = rig(data=f"cm:enable:{token}:1")
    await owner.callback(update, context)
    assert query.answer.await_count == 1
    with TrustedLocalCustomHost(path) as host:
        assert host.get("public_toy_demo").enabled
        assert host.get("public_toy_demo").revision == 2
        assert host.admin_history("public_toy_demo")[0]["action"] == "ENABLE_PAPER"
    await owner.callback(update, context)
    with TrustedLocalCustomHost(path) as host:
        assert host.get("public_toy_demo").revision == 2
        assert host.admin_history("public_toy_demo")[0]["action"] == "ENABLE_PAPER"
    update, context, _, _ = rig(data=f"cm:disable:{token}:2")
    await owner.callback(update, context)
    with TrustedLocalCustomHost(path) as host:
        assert not host.get("public_toy_demo").enabled
        assert host.get("public_toy_demo").revision == 3
        assert host.admin_history("public_toy_demo")[0]["action"] == "DISABLE_PAPER"


@pytest.mark.asyncio
async def test_nonadmin_and_group_chat_never_change_data_or_show_details(panel):
    owner, _, path = panel
    for user, chat, type in [(99, 99, "private"), (123, -1001111111111, "supergroup"),
                             (123, 99, "private")]:
        update, context, message, query = rig(
            user=user, chat=chat, type=type,
            data=f"cm:enable:{_token('public_toy_demo')}:1")
        await owner.callback(update, context)
        assert message.reply_text.await_count == 0
        assert query.answer.await_count == 1
        await owner.panel(update, context)
        assert message.reply_text.await_count == 0
    with TrustedLocalCustomHost(path) as host:
        assert not host.get("public_toy_demo").enabled
        assert not host.admin_history("public_toy_demo")


@pytest.mark.asyncio
async def test_private_channel_route_verification_and_disabled_delivery(panel):
    owner, sample, path = panel
    token = _token("public_toy_demo")
    update, context, message, query = rig(data=f"cm:route:{token}")
    await owner.callback(update, context)
    assert "mmt_custom_admin_pending" in context.user_data
    context.bot.get_chat.return_value = SimpleNamespace(
        type="channel", username=None, title="Sample Private Channel")
    context.bot.get_me.return_value = SimpleNamespace(id=9898)
    context.bot.get_chat_member.return_value = SimpleNamespace(
        status="administrator", can_post_messages=True)
    update2, _, msg2, _ = rig(text="-1001234567890")
    # Telegram normally preserves context user_data for a chat/user pair.
    await owner.route_input(update2, context)
    assert msg2.reply_text.await_count == 1
    context.bot.send_message.assert_not_awaited()
    with TrustedLocalCustomHost(path) as host:
        route = host.route("public_toy_demo")
        assert route["channel_id"] == -1001234567890
        assert route["delivery_mode"] == "DISABLED"
        assert not route["live_publication_enabled"]
        assert host.admin_history("public_toy_demo")[0]["action"] == "SET_DISABLED_ROUTE"
    update3, context3, msg3, _ = rig(data=f"cm:clear:{token}")
    await owner.callback(update3, context3)
    with TrustedLocalCustomHost(path) as host:
        assert host.route("public_toy_demo")["channel_id"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_channel", [
    ("-1001234567890", "channel", "public_name", "administrator", True),
    ("-1001234567890", "supergroup", None, "administrator", True),
    ("-1001234567890", "channel", None, "member", False),
    ("-1001234567890", "channel", None, "administrator", False),
    ("@public", "channel", None, "creator", True),
    ("123456", "channel", None, "creator", True),
])
async def test_route_rejects_public_channel_wrong_type_no_bot_admin_and_username(
        panel, bad_channel):
    owner, _, path = panel
    raw, type, name, status, can_post = bad_channel
    update, context, _, _ = rig(data=f"cm:route:{_token('public_toy_demo')}")
    await owner.callback(update, context)
    context.bot.get_chat.return_value = SimpleNamespace(
        type=type, username=name, title="UNSAFE")
    context.bot.get_me.return_value = SimpleNamespace(id=9898)
    context.bot.get_chat_member.return_value = SimpleNamespace(
        status=status, can_post_messages=can_post)
    update2, _, msg2, _ = rig(text=raw)
    await owner.route_input(update2, context)
    with TrustedLocalCustomHost(path) as host:
        assert host.route("public_toy_demo")["channel_id"] is None
    assert msg2.reply_text.await_count == 1
    context.bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_pending_route_cas_stale_after_admin_toggle_denies_route(panel):
    owner, sample, path = panel
    update, context, _, _ = rig(data=f"cm:route:{_token('public_toy_demo')}")
    await owner.callback(update, context)
    with TrustedLocalCustomHost(path) as host:
        host.toggle_as_admin("public_toy_demo", enabled=True,
                             expected_revision=1, actor_id=123,
                             descriptor_sha256=sample["descriptor_sha256"])
    context.bot.get_chat.return_value = SimpleNamespace(
        type="channel", username=None, title="private")
    context.bot.get_me.return_value = SimpleNamespace(id=9898)
    context.bot.get_chat_member.return_value = SimpleNamespace(
        status="creator", can_post_messages=True)
    update2, _, msg2, _ = rig(text="-1001234567890")
    await owner.route_input(update2, context)
    with TrustedLocalCustomHost(path) as host:
        assert host.route("public_toy_demo")["channel_id"] is None
        assert host.get("public_toy_demo").enabled


@pytest.mark.asyncio
async def test_paper_preview_only_to_private_admin_never_to_channel(panel):
    owner, sample, path = panel
    with TrustedLocalCustomHost(path) as host:
        host.toggle_as_admin("public_toy_demo", enabled=True,
                             expected_revision=1, actor_id=123,
                             descriptor_sha256=sample["descriptor_sha256"])
        quote = (path.parent / "public-toy/quote.json").read_bytes()
        assert host.paper("public_toy_demo", quote)["stored"] == 1
        assert len(host.signals("public_toy_demo")) == 1
    update, context, message, _ = rig(data=f"cm:paper:{_token('public_toy_demo')}")
    await owner.callback(update, context)
    assert "toy-" in message.reply_text.await_args.args[0]
    context.bot.send_message.assert_not_awaited()


def test_route_store_requires_proof_and_admin_audit_is_atomic(panel):
    owner, sample, path = panel
    with TrustedLocalCustomHost(path) as host:
        with pytest.raises(LocalCustomRefused, match="PROOF_REQUIRED"):
            host.set_route("public_toy_demo", channel_id=-1001234567890,
                           channel_title="private", actor_id=123,
                           verified_private_channel=False)
        assert host.admin_history("public_toy_demo") == []
        with pytest.raises(LocalCustomRefused, match="STALE_REVISION"):
            host.toggle_as_admin("public_toy_demo", enabled=True,
                                 expected_revision=999, actor_id=123,
                                 descriptor_sha256=sample["descriptor_sha256"])
        assert host.admin_history("public_toy_demo") == []
        assert host.get("public_toy_demo").revision == 1


def test_panel_never_contains_nyfr_execution_or_network_sender():
    import ast
    import inspect
    import naseri_markets.custom_admin_panel as module
    tree = ast.parse(inspect.getsource(module))
    top_imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            top_imports.update(alias.name.split(".")[0] for alias in node.names)
    assert "urllib" not in top_imports
    assert "subprocess" not in top_imports
    assert "private_nyfr_core" not in inspect.getsource(module)
