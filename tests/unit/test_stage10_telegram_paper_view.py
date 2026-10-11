"""Stage 10 private Telegram bridge-view callback: inspection never creates orders."""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("telegram")

from naseri_markets.custom_admin_panel import _token
from naseri_markets.engine_control_store import BROOKS_ENGINE_ID, EngineControlStore
from naseri_markets.integrated_engine_panel import IntegratedEnginePanel


def request(*, user=123, data=""):
    msg = SimpleNamespace(reply_text=AsyncMock())
    query = SimpleNamespace(data=data, answer=AsyncMock(), message=msg)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=user),
        effective_chat=SimpleNamespace(id=user, type="private"),
        callback_query=query,
    )
    return update, msg, query


@pytest.fixture
def panel(tmp_path):
    state = tmp_path / "private-state"
    with EngineControlStore(state):
        pass
    return IntegratedEnginePanel(state_dir=state, admin_ids={123}, owner_ids=())


def test_brooks_detail_shows_separate_order_state_without_creating_ledger(panel):
    with panel._open(123) as host:
        text = panel.detail(host, BROOKS_ENGINE_ID)
        labels = [
            b.callback_data for row in panel.keyboard(host, BROOKS_ENGINE_ID).inline_keyboard
            for b in row
        ]
    assert "NOT_CONFIGURED" in text
    assert any(item.startswith("s10:view:") for item in labels)
    assert not (panel.state_dir / "brooks_stage10_paper.sqlite").exists()


@pytest.mark.asyncio
async def test_admin_only_brooks_read_only_callback(panel):
    update, msg, query = request(
        user=123, data=f"s10:view:{_token(BROOKS_ENGINE_ID)}",
    )
    await panel.callback(update, SimpleNamespace())
    query.answer.assert_awaited()
    msg.reply_text.assert_awaited_once()
    result = msg.reply_text.await_args.args[0]
    assert "NOT_CONFIGURED" in result
    assert "🔒" in result
    assert not (panel.state_dir / "brooks_stage10_paper.sqlite").exists()


@pytest.mark.asyncio
async def test_forged_nonadmin_private_view_denied_without_db_touch(panel):
    update, msg, query = request(
        user=666, data=f"s10:view:{_token(BROOKS_ENGINE_ID)}",
    )
    await panel.callback(update, SimpleNamespace())
    query.answer.assert_awaited_once()
    assert query.answer.await_args.kwargs.get("show_alert") is True
    msg.reply_text.assert_not_awaited()
    assert not (panel.state_dir / "brooks_stage10_paper.sqlite").exists()


@pytest.mark.asyncio
async def test_unknown_private_callback_token_does_not_leak_owner_ids(panel):
    update, msg, query = request(
        user=123, data="s10:view:000000000000",
    )
    await panel.callback(update, SimpleNamespace())
    query.answer.assert_awaited()
    msg.reply_text.assert_awaited()
    assert not (panel.state_dir / "brooks_stage10_paper.sqlite").exists()
