"""Operator-chosen exchange research priorities are NEVER trade permissions."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from naseri_markets import futures_research_priority as catalog
from naseri_markets.dev_operator import main as dev_main
from naseri_markets.engine_control_store import BROOKS_ENGINE_ID, EngineControlStore
from naseri_markets.iran_futures_eligibility import available_futures_venues


EXPECTED = (
    "binance", "bybit", "mexc", "lbank", "xt", "toobit",
    "bitunix", "bigone", "kcex",
)


def test_exact_operator_priority_is_not_volume_or_iran_approval():
    rows = catalog.operator_futures_research()
    assert [x["exchange"] for x in rows] == list(EXPECTED)
    assert [x["priority"] for x in rows] == list(range(1, 10))
    assert catalog.RANKING_BASIS == "OPERATOR_PRIORITY_NOT_VERIFIED_VOLUME_RANK"
    assert all(x["operator_priority_not_volume_rank"] for x in rows)
    assert all(not x["iran_resident_futures_approved"] for x in rows)
    assert all(not x["paper_signal_authorized"] for x in rows)
    assert all(not x["live_order_authorized"] for x in rows)
    assert rows[7]["name"] == "BigONE"
    assert rows[7]["futures_api_evidence"] == "OFFICIAL_FUTURES_API_DOCUMENTED"
    assert rows[7]["iran_resident_eligibility"] == "UNVERIFIED"
    assert rows[8]["futures_api_evidence"] == (
        "FUTURES_MARKET_CONFIRMED_API_DOCUMENTATION_UNVERIFIED")
    assert available_futures_venues() == ()


def test_operator_offline_venues_cli_does_not_install_or_start(tmp_path, monkeypatch,
                                                              capsys):
    state = tmp_path / "state"
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    assert dev_main(["--state-dir", str(state), "init",
                     "--ack-nonproduction-init"]) == 0
    assert dev_main(["--state-dir", str(state), "venues"]) == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["mode"] == "OFFLINE_RESEARCH_ONLY"
    assert out["ranking_basis"] == catalog.RANKING_BASIS
    assert [x["exchange"] for x in out["venues"]] == list(EXPECTED)
    assert out["resident_futures_access_granted"] is False
    assert out["signal_delivery_enabled"] is False
    assert out["orders_enabled"] is False
    with EngineControlStore(state) as store:
        assert store.preferences(BROOKS_ENGINE_ID)["futures_exchange"] == "kraken"
        assert not store.publication(BROOKS_ENGINE_ID)["effective_publication"]
        assert store.brooks_replay_status()["scans"] == 0


@pytest.mark.asyncio
async def test_research_panel_exact_order_paging_read_only_admin_only(tmp_path):
    pytest.importorskip("telegram")
    from naseri_markets.custom_admin_panel import _token
    from naseri_markets.integrated_engine_panel import IntegratedEnginePanel
    token = _token(BROOKS_ENGINE_ID)
    private = tmp_path / "dev"
    panel = IntegratedEnginePanel(
        state_dir=private, admin_ids={123}, owner_ids={123})
    with EngineControlStore(private) as host:
        assert "vr:list:" + token + ":0" in [
            b.callback_data for row in panel.settings_keyboard(
                host, BROOKS_ENGINE_ID).inline_keyboard for b in row]
        a = panel.research_text(host, BROOKS_ENGINE_ID, 0)
        b = panel.research_text(host, BROOKS_ENGINE_ID, 1)
        assert a.index("1. Binance") < a.index("2. Bybit") < a.index(
            "3. MEXC") < a.index("4. LBank") < a.index("5. XT.COM")
        assert b.index("6. Toobit") < b.index("7. Bitunix") < b.index(
            "8. BigONE") < b.index("9. KCEX")
        assert "نه رتبه واقعی حجم معاملات" in a
        for page in (0, 1):
            keyboard = panel.research_keyboard(host, BROOKS_ENGINE_ID, page)
            callbacks = [bt.callback_data for r in keyboard.inline_keyboard for bt in r]
            assert all(not v.startswith(("ex:set:", "ep:set:", "cm:enable:"))
                       for v in callbacks)
            assert all(len(v) <= 64 for v in callbacks)
        with pytest.raises(Exception):
            panel.research_keyboard(host, BROOKS_ENGINE_ID, 2)

    def update(user):
        message = SimpleNamespace(reply_text=AsyncMock())
        query = SimpleNamespace(
            data=f"vr:list:{token}:1", message=message, answer=AsyncMock())
        req = SimpleNamespace(
            effective_user=SimpleNamespace(id=user),
            effective_chat=SimpleNamespace(type="private", id=user),
            callback_query=query)
        return req, message
    stranger, wrong_message = update(999)
    await panel.callback(stranger, SimpleNamespace())
    wrong_message.reply_text.assert_not_awaited()
    owner, own_message = update(123)
    await panel.callback(owner, SimpleNamespace())
    assert "8. BigONE" in own_message.reply_text.await_args.args[0]
    with EngineControlStore(private) as host:
        assert host.preferences(BROOKS_ENGINE_ID)["revision"] == 1
        assert host.preferences(BROOKS_ENGINE_ID)["futures_exchange"] == "kraken"
