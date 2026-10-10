"""Iran-resident futures eligibility must fail closed on unknown policy.

The internal twenty-venue research archive is NOT the operator choices.
The latter requires verified affirmative futures-eligibility evidence.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from naseri_markets.iran_futures_eligibility import (
    RESEARCH_DATE, RANKING_METRIC, RESTRICTED_SOURCES, REVIEW_SOURCES,
    VERIFIED_IRAN_FUTURES_VENUES, available_futures_venues,
    iran_futures_approved, ranked_iran_futures_venues, review_status,
)
from naseri_markets.engine_control_store import BROOKS_ENGINE_ID, EngineControlStore
from naseri_markets.futures_venues import FUTURES_VENUES


def test_all_previous_venues_excluded_without_positive_official_evidence():
    assert RESEARCH_DATE == "2026-10-11"
    assert RANKING_METRIC == "reported_24h_derivatives_volume_usd"
    assert len(FUTURES_VENUES) == 20  # audit archive, not selectable
    assert set(RESTRICTED_SOURCES) | set(REVIEW_SOURCES) == {
        v.key for v in FUTURES_VENUES}
    assert set(RESTRICTED_SOURCES).isdisjoint(REVIEW_SOURCES)
    assert not VERIFIED_IRAN_FUTURES_VENUES
    assert not available_futures_venues()
    assert not ranked_iran_futures_venues()
    assert all(not iran_futures_approved(v.key) for v in FUTURES_VENUES)
    assert not iran_futures_approved("fake")
    assert review_status("toobit") == "RESTRICTED_OR_POLICY_BLOCKED"
    assert review_status("kucoin") == "ELIGIBILITY_UNVERIFIED"


def test_reference_sort_is_descending_comparable_futures_volume(monkeypatch):
    import naseri_markets.iran_futures_eligibility as eligibility
    venue = eligibility.ApprovedVenue
    sample = (
        venue("xt", "XT.COM", "https://example.org/eligibility", "https://example.org/api",
              100, "2026-10-11"),
        venue("kucoin", "KuCoin", "https://example.org/eligibility", "https://example.org/api",
              200, "2026-10-11"),
    )
    # Test only a pure ranking rule; NOT approval of these actual exchanges.
    monkeypatch.setattr(eligibility, "VERIFIED_IRAN_FUTURES_VENUES", sample)
    assert [x.key for x in eligibility.ranked_iran_futures_venues()] == [
        "kucoin", "xt"]


@pytest.mark.asyncio
async def test_blocked_exchanges_cannot_be_selected_via_private_panel(tmp_path):
    pytest.importorskip("telegram")
    from naseri_markets.custom_admin_panel import _token
    from naseri_markets.integrated_engine_panel import IntegratedEnginePanel

    folder = tmp_path / "operator-private"
    panel = IntegratedEnginePanel(state_dir=folder, admin_ids={123})
    token = _token(BROOKS_ENGINE_ID)
    with EngineControlStore(folder) as host:
        for page in range(4):
            markup = panel.exchange_keyboard(host, BROOKS_ENGINE_ID, page)
            buttons = [b.callback_data for row in markup.inline_keyboard for b in row]
            assert not any(x.startswith("ex:set:") for x in buttons)
        pair_menu = panel.pair_keyboard(host, BROOKS_ENGINE_ID)
        assert not any(
            b.callback_data.startswith("ep:set:")
            for row in pair_menu.inline_keyboard for b in row)
        assert "غیرمجاز برای انتخاب" in panel.settings_text(host, BROOKS_ENGINE_ID)

    message = SimpleNamespace(reply_text=AsyncMock())
    cb = SimpleNamespace(
        data=f"ex:set:{token}:0:1", answer=AsyncMock(), message=message)
    update = SimpleNamespace(
        callback_query=cb, effective_user=SimpleNamespace(id=123),
        effective_chat=SimpleNamespace(type="private", id=123))
    await panel.callback(update, SimpleNamespace())
    with EngineControlStore(folder) as host:
        assert host.preferences(BROOKS_ENGINE_ID)["futures_exchange"] == "kraken"
        assert host.preferences(BROOKS_ENGINE_ID)["revision"] == 1
    assert "نامعتبر" in message.reply_text.await_args.args[0]
