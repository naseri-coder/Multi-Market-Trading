"""PAPER-08: manual, read-only cross-journal reconciliation and fail-closed restart."""
from __future__ import annotations

import sqlite3

import pytest

from test_brooks_paper07_real_replay_link import invoke, fake_positive_transport

from naseri_markets import brooks_stage10_cli
from naseri_markets.brooks_stage10_recovery_v1 import reconcile_stage10_paper
from naseri_markets.brooks_stage10_paper_bridge import (
    BrooksStage10Refused,
    panel_stage10_overview,
)


pytest_plugins = ["test_brooks_paper07_real_replay_link"]

def test_readonly_not_configured_creates_nothing(tmp_path):
    state = tmp_path / "empty"
    state.mkdir(mode=0o700)
    result = reconcile_stage10_paper(state)
    assert result["status"] == "NOT_CONFIGURED"
    assert not result["can_automatically_resume"]
    assert list(state.iterdir()) == []


def test_crash_between_scan_and_paper_fails_closed_on_retry(ready, monkeypatch):
    fake_positive_transport(monkeypatch, ready[1])
    original = brooks_stage10_cli.BrooksStage10PaperBridge.link

    def simulated_crash(*_a, **_kw):
        raise BrooksStage10Refused("INJECTED_POST_SCAN_PRE_LINK_CRASH")

    monkeypatch.setattr(
        brooks_stage10_cli.BrooksStage10PaperBridge, "link", simulated_crash,
    )
    with pytest.raises(BrooksStage10Refused, match="INJECTED"):
        invoke(ready)
    orphan = reconcile_stage10_paper(ready[0])
    assert orphan["status"] == "MANUAL_RECONCILIATION_REQUIRED"
    assert orphan["unlinked_signals"] == 1
    assert orphan["linked_orders"] == 0
    assert not orphan["can_automatically_resume"]
    monkeypatch.setattr(brooks_stage10_cli.BrooksStage10PaperBridge, "link", original)
    with pytest.raises(BrooksStage10Refused, match="RECONCILIATION_REQUIRED"):
        invoke(ready)
    assert panel_stage10_overview(ready[0])["linked_orders"] == 0


def test_verified_duplicate_after_restart_is_readonly_and_safe(ready, monkeypatch):
    fake_positive_transport(monkeypatch, ready[1])
    first = invoke(ready)
    before = (ready[0] / "brooks_stage10_paper.sqlite").stat().st_size
    result = reconcile_stage10_paper(ready[0], signal_id=first["signal_id"])
    assert result["status"] == "MATCHED_PAPER_ORDER"
    assert result["linked_orders"] == 1
    assert result["active_paper_reservations"] == 1
    assert result["unlinked_signals"] == 0
    assert not result["can_automatically_resume"]  # diagnostic only
    assert (ready[0] / "brooks_stage10_paper.sqlite").stat().st_size == before
    second = invoke(ready)
    assert second["paper"]["status"] == "EXISTING_PAPER_ORDER"
    assert second["paper"]["order_id"] == first["paper"]["order_id"]
    assert not second["paper"]["risk_reservation_created"]


@pytest.mark.parametrize("corrupt", ["lost_order", "lost_risk", "changed_link"])
def test_tampered_cross_database_rows_quarantined(ready, monkeypatch, corrupt):
    fake_positive_transport(monkeypatch, ready[1])
    first = invoke(ready)
    path = ready[0] / "brooks_stage10_paper.sqlite"
    with sqlite3.connect(path) as db:
        if corrupt == "lost_order":
            db.execute("DELETE FROM paper_orders WHERE order_id=?", (
                first["paper"]["order_id"],))
        elif corrupt == "lost_risk":
            db.execute("DELETE FROM paper_risk_reservations WHERE order_id=?", (
                first["paper"]["order_id"],))
        else:
            db.execute("UPDATE brooks_stage10_links SET request_digest=?",
                       ("0" * 64,))
    report = reconcile_stage10_paper(ready[0])
    assert report["status"] == "MANUAL_RECONCILIATION_REQUIRED"
    assert report["inconsistent_links"] >= 1
    assert not report["can_automatically_resume"]
    with pytest.raises(BrooksStage10Refused, match="RECONCILIATION_REQUIRED"):
        invoke(ready)


def test_operator_revoke_retains_historical_snapshot(ready, monkeypatch):
    from naseri_markets.engine_control_store import BROOKS_ENGINE_ID, EngineControlStore
    fake_positive_transport(monkeypatch, ready[1])
    invoke(ready)
    with EngineControlStore(ready[0]) as store:
        state = store.get(BROOKS_ENGINE_ID)
        store.toggle_as_admin(
            BROOKS_ENGINE_ID, enabled=False, actor_id=123,
            expected_revision=state.revision,
        )
    report = reconcile_stage10_paper(ready[0])
    assert report["status"] == "MATCHED_PAPER_ORDER"
    assert report["linked_orders"] == 1
    with pytest.raises(ValueError):
        invoke(ready)


def test_missing_destination_after_signal_does_not_create_new_db(ready, monkeypatch):
    fake_positive_transport(monkeypatch, ready[1])
    first = invoke(ready)
    # Simulator existing paths cannot be regenerated merely by a status query.
    path = ready[0] / "brooks_stage10_paper.sqlite"
    path.rename(ready[0] / "temporarily-held.sqlite")
    report = reconcile_stage10_paper(ready[0])
    assert report["status"] == "MANUAL_RECONCILIATION_REQUIRED"
    assert not path.exists()
    assert not report["can_automatically_resume"]
    with pytest.raises(BrooksStage10Refused, match="RECONCILIATION_REQUIRED"):
        invoke(ready)
    assert not path.exists()
    assert first["paper"]["order_status"] == "CREATED"
