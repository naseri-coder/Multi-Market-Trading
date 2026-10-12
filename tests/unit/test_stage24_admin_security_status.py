"""Stage24 admin read-only evidence display: NO security/trading side effects."""
from __future__ import annotations

import pytest

pytest.importorskip("telegram")
from telegram.ext import CommandHandler

from naseri_markets.integrated_engine_panel import IntegratedEnginePanel
from naseri_markets.bot_admin_app import build_admin_application
from test_integrated_engine_panel import fake, setup  # noqa: F401


@pytest.mark.asyncio
async def test_private_admin_can_only_view_blocked_stage24_status(setup):  # noqa: F811
    state, _, _ = setup
    panel = IntegratedEnginePanel(state_dir=state, admin_ids={123},
                                  owner_ids={123})
    user, context, message, _ = fake(user=123, chat=123)
    await panel.coresecurity(user, context)
    assert message.reply_text.await_count == 1
    text = message.reply_text.await_args.args[0]
    assert "Stage24" in text
    assert "🔒" in text
    assert "انجام نشده" in text
    assert "NY First-Reversal" not in text
    assert context.bot.send_message.await_count == 0
    assert not (state / "stage24_host_observation.sqlite").exists()


@pytest.mark.asyncio
async def test_group_and_stranger_cannot_discover_stage24(setup):  # noqa: F811
    state, _, _ = setup
    panel = IntegratedEnginePanel(state_dir=state, admin_ids={123},
                                  owner_ids={123})
    for uid, cid, kind in [(999, 999, "private"),
                            (123, -10012345, "group")]:
        user, context, message, _ = fake(user=uid, chat=cid, chat_type=kind)
        await panel.coresecurity(user, context)
        message.reply_text.assert_not_awaited()
        context.bot.send_message.assert_not_awaited()


def test_coresecurity_command_in_same_offline_admin_application(setup):  # noqa: F811
    state, _, _ = setup
    app = build_admin_application(
        token="123456:LOCAL_ONLY_FAKE_TEST", state_dir=state,
        admin_ids={123}, owner_ids={123})
    commands = {value for group in app.handlers.values()
                for handler in group if isinstance(handler, CommandHandler)
                for value in handler.commands}
    assert {"engines", "coresecurity"}.issubset(commands)
    assert not (state / "stage24_host_observation.sqlite").exists()
