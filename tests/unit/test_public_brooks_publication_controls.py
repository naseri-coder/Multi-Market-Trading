"""Public Brooks panel publication intent remains distinct from actual delivery."""
import pytest

from naseri_markets.engine_control_store import (
    BROOKS_ENGINE_ID, OWNER_CORE_ID, EngineControlStore,
)
from naseri_markets.trusted_custom import LocalCustomRefused


def test_public_brooks_publication_request_is_persistent_but_never_sends(tmp_path):
    path = tmp_path / "private"
    with EngineControlStore(path) as store:
        before = store.publication(BROOKS_ENGINE_ID)
        assert before["revision"] == 0
        assert before["effective_publication"] is False
        changed = store.request_publication(
            BROOKS_ENGINE_ID, enabled=True,
            expected_revision=0, actor_id=123)
        assert changed["requested_publication"] is True
        assert changed["effective_publication"] is False
        assert changed["reason"] == "NO_AUTHENTICATED_FORWARD_PUBLISHER"
        with pytest.raises(LocalCustomRefused, match="STALE"):
            store.request_publication(
                BROOKS_ENGINE_ID, enabled=False,
                expected_revision=0, actor_id=123)
        assert store.route(BROOKS_ENGINE_ID)["delivery_mode"] == "DISABLED"
        assert store.signals(BROOKS_ENGINE_ID) == []
    with EngineControlStore(path) as store:
        assert store.publication(BROOKS_ENGINE_ID)["requested_publication"]
        assert not store.publication(BROOKS_ENGINE_ID)["effective_publication"]
        disabled = store.request_publication(
            BROOKS_ENGINE_ID, enabled=False,
            expected_revision=1, actor_id=123)
        assert not disabled["requested_publication"]


def test_owner_custom_and_untrusted_actor_cannot_activate_publication(tmp_path):
    with EngineControlStore(tmp_path / "private", owner_visible=True) as store:
        store.register_owner_reference(engine_id=OWNER_CORE_ID, actor_id=123)
        with pytest.raises(LocalCustomRefused, match="PERMISSION_DENIED"):
            store.request_publication(
                OWNER_CORE_ID, enabled=True,
                expected_revision=0, actor_id=123)
        with pytest.raises(LocalCustomRefused, match="PERMISSION_DENIED"):
            store.request_publication(
                BROOKS_ENGINE_ID, enabled=True,
                expected_revision=0, actor_id=0)


def test_publication_audit_uses_its_own_cas_revision(tmp_path):
    with EngineControlStore(tmp_path / "state") as store:
        store.request_publication(BROOKS_ENGINE_ID, enabled=True,
                                  expected_revision=0, actor_id=123)
        assert store.admin_history(BROOKS_ENGINE_ID)[0]["engine_revision"] == 1
        store.request_publication(BROOKS_ENGINE_ID, enabled=False,
                                  expected_revision=1, actor_id=123)
        assert store.admin_history(BROOKS_ENGINE_ID)[0]["engine_revision"] == 2


def test_real_telegram_application_registers_all_button_callbacks(tmp_path):
    pytest.importorskip("telegram")
    from telegram.ext import CallbackQueryHandler
    from naseri_markets.bot_admin_app import build_admin_application
    from naseri_markets.custom_admin_panel import _token

    app = build_admin_application(
        token="123456:NONPRODUCTION_TEST_TOKEN", state_dir=tmp_path / "state",
        admin_ids={123, 234}, owner_ids={123}, owner_reference=True)
    handlers = [
        h for group in app.handlers.values() for h in group
        if isinstance(h, CallbackQueryHandler)]
    token = _token(BROOKS_ENGINE_ID)
    def supported(payload):
        return any(h.pattern is not None and h.pattern.match(payload) for h in handlers)
    assert supported(f"cm:open:{token}")
    assert supported(f"em:settings:{token}")
    assert supported(f"em:env:{token}:1")
    assert supported(f"bp:on:{token}:0")
    assert supported(f"bp:off:{token}:1")
    assert not supported(f"unrelated:open:{token}")
    assert len([h for h in handlers if h.pattern.match(f"bp:on:{token}:0")]) == 1


@pytest.mark.asyncio
async def test_telegram_brooks_publication_buttons_end_to_end(tmp_path):
    pytest.importorskip("telegram")
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from naseri_markets.custom_admin_panel import _token
    from naseri_markets.integrated_engine_panel import IntegratedEnginePanel

    state_dir = tmp_path / "state"
    panel = IntegratedEnginePanel(state_dir=state_dir, admin_ids={123, 234},
                                  owner_ids={123})
    token = _token(BROOKS_ENGINE_ID)

    def update_for(data, *, admin=123, chat=None):
        message = SimpleNamespace(reply_text=AsyncMock())
        query = SimpleNamespace(data=data, message=message, answer=AsyncMock())
        return (SimpleNamespace(
            effective_user=SimpleNamespace(id=admin),
            effective_chat=SimpleNamespace(
                id=admin if chat is None else chat, type="private"),
            callback_query=query, effective_message=message),
            SimpleNamespace(user_data={}, bot=SimpleNamespace(
                send_message=AsyncMock())))

    with EngineControlStore(state_dir) as store:
        keyboard = panel.keyboard(store, BROOKS_ENGINE_ID)
        callbacks = [b.callback_data for row in keyboard.inline_keyboard for b in row]
        assert f"bp:on:{token}:0" in callbacks
        assert "درخواست انتشار سیگنال: ⏸ ثبت نشده" in panel.detail(
            store, BROOKS_ENGINE_ID)

    update, context = update_for(f"bp:on:{token}:0")
    await panel.callback(update, context)
    assert update.callback_query.answer.await_count == 1
    text = update.effective_message.reply_text.await_args.args[0]
    assert "درخواست انتشار سیگنال: ✅ ثبت شده" in text
    assert "انتشار مؤثر سیگنال: 🔒 غیرفعال" in text
    context.bot.send_message.assert_not_awaited()
    with EngineControlStore(state_dir) as store:
        assert store.publication(BROOKS_ENGINE_ID)["revision"] == 1
        assert store.publication(BROOKS_ENGINE_ID)["requested_publication"]
        assert not store.publication(BROOKS_ENGINE_ID)["effective_publication"]

    # Stale press must not increment revision or write a second audit.
    await panel.callback(update, context)
    with EngineControlStore(state_dir) as store:
        assert store.publication(BROOKS_ENGINE_ID)["revision"] == 1
        assert len(store.admin_history(BROOKS_ENGINE_ID)) == 1

    # The other explicit admin can disable publication without affecting
    # analysis requested state or the owner-only private reference.
    update2, ctx2 = update_for(f"bp:off:{token}:1", admin=234)
    await panel.callback(update2, ctx2)
    with EngineControlStore(state_dir) as store:
        assert not store.publication(BROOKS_ENGINE_ID)["requested_publication"]
        assert not store.publication(BROOKS_ENGINE_ID)["effective_publication"]
        assert store.publication(BROOKS_ENGINE_ID)["revision"] == 2
    ctx2.bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_telegram_publication_denies_nonadmin_and_different_private_chat(tmp_path):
    pytest.importorskip("telegram")
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from naseri_markets.custom_admin_panel import _token
    from naseri_markets.integrated_engine_panel import IntegratedEnginePanel
    panel = IntegratedEnginePanel(state_dir=tmp_path / "state",
                                  admin_ids={123}, owner_ids={123})
    token = _token(BROOKS_ENGINE_ID)
    for uid, cid in ((444, 444), (123, 444)):
        query = SimpleNamespace(
            data=f"bp:on:{token}:0", answer=AsyncMock(),
            message=SimpleNamespace(reply_text=AsyncMock()))
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=uid),
            effective_chat=SimpleNamespace(id=cid, type="private"),
            callback_query=query)
        await panel.callback(update, SimpleNamespace(user_data={}))
        query.answer.assert_awaited_once()
        query.message.reply_text.assert_not_awaited()
    with EngineControlStore(tmp_path / "state") as store:
        assert store.publication(BROOKS_ENGINE_ID)["revision"] == 0
        assert not store.publication(BROOKS_ENGINE_ID)["requested_publication"]
