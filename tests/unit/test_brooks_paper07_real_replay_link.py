"""Stage07: actual pinned Brooks replay -> existing Stage10 risk PAPER link.

The LONG report is a mocked *transport contract*, never a simulated claim
that the authentic Brooks V5 engine generated a profitable setup.
"""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace

import pytest

from naseri_markets import brooks_replay
from naseri_markets.brooks_stage10_cli import run_once
from naseri_markets.brooks_stage10_paper_bridge import panel_stage10_overview
from naseri_markets.engine_control_store import BROOKS_ENGINE_ID, EngineControlStore
from naseri_markets.execution_position_core_v1 import PaperExecutionOrchestratorV1
from naseri_markets.contracts import Instrument, Market
from naseri_markets.risk_portfolio_contract_v1 import AccountRiskPolicy, PortfolioRiskPolicy

LEGACY = Path(__file__).resolve().parents[2] / "production_source"


def fixture_bars() -> bytes:
    origin = datetime(2026, 1, 1, tzinfo=UTC)
    bars = []
    for i in range(72):
        start = origin + timedelta(minutes=i * 15)
        bars.append({
            "open_time": start.isoformat(),
            "close_time": (start + timedelta(minutes=15)).isoformat(),
            "open": "100", "high": "101", "low": "99", "close": "100",
            "volume": "10",
        })
    return json.dumps({
        "schema_version": 1, "origin": "replay", "market": "crypto",
        "provider": "offline_paper_fixture", "symbol": "BTCUSDT",
        "timezone": "UTC", "quote_currency": "USDT",
        "exchange": "offline_fixture", "market_type": "futures",
        "timeframe": "15m", "candles": bars,
    }, sort_keys=True).encode()


@pytest.fixture
def ready(tmp_path: Path):
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    with EngineControlStore(state) as store:
        before = store.get(BROOKS_ENGINE_ID)
        store.toggle_as_admin(
            BROOKS_ENGINE_ID, enabled=True,
            expected_revision=before.revision, actor_id=123,
        )
        prefs = store.preferences(BROOKS_ENGINE_ID)
        store.change_preference(
            BROOKS_ENGINE_ID, field="signal_environment", value="PAPER",
            expected_revision=prefs["revision"], actor_id=123,
        )
    with PaperExecutionOrchestratorV1(state / "brooks_stage10_paper.sqlite") as core:
        core.configure_portfolio(PortfolioRiskPolicy(
            "p07-portfolio", "USDT", D(150), D(20000), D(100),
            D(150), D(150), 5,
        ))
        core.configure_account(AccountRiskPolicy(
            "p07-account", "p07-portfolio", "USDT", D(1000),
            D("0.05"), D("0.20"), D("0.10"), D(2),
            D("0.90"), D(3), D(1), D("0.01"),
            D("0.002"), D("0.003"), 5, True,
        ))
        core.register_instrument(
            portfolio_id="p07-portfolio",
            instrument=Instrument(
                Market.CRYPTO, "offline_paper_fixture", "BTCUSDT", "UTC", "USDT",
            ), group_id="CRYPTO_PAPER",
        )
    replay = tmp_path / "bars.json"
    replay.write_bytes(fixture_bars())
    return state, replay


def invoke(ready, **overrides):
    state, replay = ready
    defaults = dict(
        state_dir=state, status=False, link=False, replay_and_link=True,
        replay_file=replay, legacy_source=LEGACY,
        signal_id=None, account_id="p07-account", quantity="1.00",
        ack_nonproduction_stage10_paper=True, ack_real_brooks_offline=True,
    )
    defaults.update(overrides)
    return run_once(argparse.Namespace(**defaults), environment={
        "MMT_NONPRODUCTION": "1", "MMT_PRODUCTION": "0",
    })


def fake_positive_transport(monkeypatch, replay):
    """Strict mock of the worker process, not a synthetic Brooks engine result."""
    raw, _, bars = brooks_replay.parse_candle_replay(replay.read_bytes())
    snap_id, snap_hash = brooks_replay.canonical_snapshot_identity(raw, bars)
    mock = {
        "decision": "LONG", "entry": "101", "stop": "99",
        "targets": ["105"], "setup_type": "TEST_TRANSPORT_ONLY",
        "engine_version": "brooks-trilogy-full-core-v5-context-structural",
        "rule_set_version": "test-replay-contract",
        "configuration_version": "offline-fixture-only",
        "rule_ids": ["MOCK-DO-NOT-REPORT-AS-V5-SIGNAL"],
        "snapshot_id": snap_id, "snapshot_hash": snap_hash,
    }
    monkeypatch.setattr(
        brooks_replay.subprocess, "run",
        lambda *a, **k: SimpleNamespace(
            returncode=0, stdout=json.dumps(mock).encode(),
        ),
    )


def test_authentic_v5_closed_candle_replay_does_not_fabricate_paper_orders(ready):
    outcome = invoke(ready)
    assert outcome["mode"] == "PINNED_BROOKS_OFFLINE_TO_STAGE10_PAPER"
    assert outcome["engine_decision"] in ("NO_SIGNAL", "LONG", "SHORT")
    assert not outcome["broker_order_sent"]
    assert not outcome["telegram_sent"]
    with EngineControlStore(ready[0]) as store:
        assert store.brooks_replay_status()["scans"] == 1
    if outcome["engine_decision"] == "NO_SIGNAL":
        assert outcome["paper_order_created"] is False
        assert panel_stage10_overview(ready[0])["linked_orders"] == 0
    else:
        assert outcome["paper_order_created"] is True
        assert outcome["paper"]["order_status"] == "CREATED"


def test_mock_positive_contract_links_once_without_fill_and_restart_duplicate(
    ready, monkeypatch,
):
    fake_positive_transport(monkeypatch, ready[1])
    one = invoke(ready)
    assert one["engine_decision"] == "LONG"
    assert one["paper_order_created"]
    assert one["paper"]["status"] == "PAPER_ORDER_CREATED"
    assert one["paper"]["order_status"] == "CREATED"
    two = invoke(ready)
    assert two["paper"]["status"] == "EXISTING_PAPER_ORDER"
    assert not two["paper"]["risk_reservation_created"]
    assert one["paper"]["order_id"] == two["paper"]["order_id"]
    with PaperExecutionOrchestratorV1(
        ready[0] / "brooks_stage10_paper.sqlite",
    ) as core:
        row = core.order_state(one["paper"]["order_id"])
        assert row["status"] == "CREATED"
        assert row["filled_quantity"] == "0"
        assert len(core.order_events(one["paper"]["order_id"])) == 1
    assert panel_stage10_overview(ready[0])["linked_orders"] == 1


@pytest.mark.parametrize("bad", [
    {"ack_real_brooks_offline": False},
    {"ack_nonproduction_stage10_paper": False},
    {"legacy_source": Path("/no/such/frozen/source")},
])
def test_missing_operator_consent_or_source_refused_before_order(ready, bad):
    with pytest.raises(ValueError):
        invoke(ready, **bad)
    assert panel_stage10_overview(ready[0])["linked_orders"] == 0


def test_replay_filename_hardlink_denied_before_worker(ready, tmp_path):
    link = tmp_path / "second-link"
    import os
    os.link(ready[1], link)
    with pytest.raises(ValueError, match="REPLAY_FILE"):
        invoke(ready)
    assert panel_stage10_overview(ready[0])["linked_orders"] == 0


def test_wrong_selected_timeframe_fails_before_paper_risk(ready):
    with EngineControlStore(ready[0]) as store:
        preferences = store.preferences(BROOKS_ENGINE_ID)
        store.change_preference(
            BROOKS_ENGINE_ID, field="timeframe", value="1h",
            expected_revision=preferences["revision"], actor_id=123,
        )
    with pytest.raises(ValueError):
        invoke(ready)
    assert panel_stage10_overview(ready[0])["linked_orders"] == 0

def test_positive_transport_risk_rejection_keeps_no_order(
    ready, monkeypatch,
):
    from naseri_markets.risk_portfolio_manager_v1 import RiskRefused

    fake_positive_transport(monkeypatch, ready[1])
    with pytest.raises(RiskRefused):
        invoke(ready, quantity="100000.00")
    # The frozen replay scan/intent is committed in its existing journal,
    # but the Stage10 risk transaction must refuse an unsafe reservation.
    with EngineControlStore(ready[0]) as store:
        assert store.brooks_replay_status()["scans"] == 1
        assert store.brooks_replay_status()["paper_signals"] == 1
    assert panel_stage10_overview(ready[0])["linked_orders"] == 0
    assert panel_stage10_overview(ready[0])["active_paper_reservations"] == 0


def test_brooks_was_disabled_before_reading_worker(ready, monkeypatch):
    def should_not_run(*args, **kwargs):
        raise AssertionError("unexpected child interpreter")

    monkeypatch.setattr(brooks_replay.subprocess, "run", should_not_run)
    with EngineControlStore(ready[0]) as store:
        state = store.get(BROOKS_ENGINE_ID)
        store.toggle_as_admin(
            BROOKS_ENGINE_ID, enabled=False,
            expected_revision=state.revision, actor_id=123,
        )
    with pytest.raises(ValueError, match="NOT_ENABLED"):
        invoke(ready)
    assert panel_stage10_overview(ready[0])["linked_orders"] == 0


def test_replay_and_link_refuses_privileged_caller(ready, monkeypatch):
    from naseri_markets import brooks_stage10_cli

    monkeypatch.setattr(brooks_stage10_cli.os, "geteuid", lambda: 0)
    with pytest.raises(ValueError, match="UNPRIVILEGED"):
        invoke(ready)
    assert panel_stage10_overview(ready[0])["linked_orders"] == 0

def test_offline_brooks_extra_pins_historical_engine_dependency():
    import tomllib

    root = Path(__file__).resolve().parents[2]
    old = tomllib.loads((root / "pyproject.toml").read_text())
    new = tomllib.loads((root / "platform_release/pyproject.toml").read_text())
    assert new["project"]["dependencies"] == []
    assert sorted(new["project"]["optional-dependencies"]["brooks-offline"]) == sorted(
        old["project"]["dependencies"]
    )
    assert new["project"]["optional-dependencies"]["telegram-admin"] == [
        "python-telegram-bot==22.8"
    ]
