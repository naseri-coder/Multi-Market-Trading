"""Stage 10: evidence-to-Stage3 PAPER order/risk bridge, tests run offline only."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal as D

import pytest

from naseri_markets.brooks_paper_receipts import make_receipt, record_receipt
from naseri_markets.brooks_stage10_cli import run_once
from naseri_markets.brooks_stage10_paper_bridge import (
    BrooksStage10PaperBridge,
    BrooksStage10Refused,
    panel_stage10_overview,
)
from naseri_markets.contracts import (
    Direction, EvidenceMode, Instrument, Market, SignalIntent,
)
from naseri_markets.delivery_ledger import _wire_intent
from naseri_markets.engine_control_store import BROOKS_ENGINE_ID, EngineControlStore
from naseri_markets.execution_position_core_v1 import PaperExecutionOrchestratorV1
from naseri_markets.risk_portfolio_contract_v1 import AccountRiskPolicy, PortfolioRiskPolicy
from naseri_markets.risk_portfolio_manager_v1 import RiskRefused

SIGNAL = "brooks-stage10-fixture"
VERSION = "brooks-trilogy-full-core-v5-context-structural"
ACCOUNT = "paper-account-1"
PORTFOLIO = "paper-portfolio-1"
SCAN = "f" * 64
SNAPSHOT = "a" * 64
SOURCE = "b" * 64
WHEN = datetime(2026, 10, 1, 1, 30, tzinfo=UTC)


def instrument() -> Instrument:
    return Instrument(
        Market.CRYPTO, "kraken_futures_trade_public", "PF_XBTUSD", "UTC", "USD"
    )


def signal() -> SignalIntent:
    return SignalIntent(
        signal_id=SIGNAL, engine_id=BROOKS_ENGINE_ID,
        engine_version=VERSION, instrument=instrument(),
        direction=Direction.LONG, observed_at=WHEN,
        entry=D("100"), stop=D("90"), targets=(D("120"), D("130")),
        evidence_mode=EvidenceMode.PAPER,
    )


def portfolio() -> PortfolioRiskPolicy:
    return PortfolioRiskPolicy(
        portfolio_id=PORTFOLIO, currency="USD",
        max_reserved_risk=D("150"), max_notional=D("20000"),
        max_daily_loss=D("100"), max_group_risk=D("150"),
        max_engine_risk=D("150"), max_active_orders=5,
    )


def account(*, cleared=True) -> AccountRiskPolicy:
    return AccountRiskPolicy(
        account_id=ACCOUNT, portfolio_id=PORTFOLIO, currency="USD",
        equity=D("1000"), max_order_risk_fraction=D("0.05"),
        max_total_risk_fraction=D("0.2"), max_daily_loss_fraction=D("0.1"),
        max_notional_fraction=D("2"), max_margin_fraction=D("0.9"),
        max_leverage=D("3"), contract_multiplier=D("1"),
        quantity_step=D("0.01"), roundtrip_fee_fraction=D("0.002"),
        worst_slippage_fraction=D("0.003"), max_active_orders=5,
        external_exposure_cleared=cleared,
    )


def create_source(state_dir):
    with EngineControlStore(state_dir) as store:
        existing = store.get(BROOKS_ENGINE_ID)
        store.toggle_as_admin(
            BROOKS_ENGINE_ID, enabled=True, actor_id=123,
            expected_revision=existing.revision,
        )
        prefs = store.preferences(BROOKS_ENGINE_ID)
        store.change_preference(
            BROOKS_ENGINE_ID, field="signal_environment",
            value="PAPER", expected_revision=prefs["revision"], actor_id=123,
        )
        paper_signal = signal()
        raw = _wire_intent(paper_signal)
        digest = hashlib.sha256(raw.encode()).hexdigest()
        store._db.execute(
            "INSERT INTO a7_paper_intents VALUES (?,?,?,?)",
            (BROOKS_ENGINE_ID, SIGNAL, digest, raw),
        )
        store._db.execute(
            "INSERT INTO brooks_replay_scans VALUES (?,?,?,?,?,?)",
            (SCAN, SNAPSHOT, "LONG", "TEST_ONLY", SIGNAL, SOURCE),
        )
        receipt = make_receipt(
            scan_id=SCAN, raw={
                "exchange": "kraken_futures",
                "provider": "kraken_futures_trade_public",
                "symbol": "PF_XBTUSD", "quote_currency": "USD",
                "timeframe": "15m", "market_type": "futures",
                "candles": [{"close_time": WHEN.isoformat()}],
            },
            snapshot_hash=SNAPSHOT, source_digest=SOURCE,
            decision="LONG", signal=paper_signal, outcome="RECORDED",
        )
        record_receipt(store._db, receipt)


def configure_simulator(state_dir, *, cleared=True):
    path = state_dir / "brooks_stage10_paper.sqlite"
    with PaperExecutionOrchestratorV1(
        path, clock=lambda: date(2026, 10, 11),
    ) as core:
        core.configure_portfolio(portfolio())
        core.configure_account(account(cleared=cleared))
        core.register_instrument(
            portfolio_id=PORTFOLIO, instrument=instrument(),
            group_id="CRYPTO_PAPER",
        )


@pytest.fixture
def env(tmp_path):
    state = tmp_path / "private-state"
    create_source(state)
    configure_simulator(state)
    return state


def linker(state, **overrides):
    args = {
        "signal_id": SIGNAL, "account_id": ACCOUNT,
        "quantity": "1.00", "ack_paper_risk": True,
    }
    args.update(overrides)
    return BrooksStage10PaperBridge(state).link(**args)


def test_creates_only_simulated_order_and_atomic_risk_reservation(env):
    out = linker(env)
    assert out["status"] == "PAPER_ORDER_CREATED"
    assert out["mode"] == "OFFLINE_BROOKS_PAPER_RISK_LINK_ONLY"
    assert out["order_status"] == "CREATED"
    assert out["risk_reservation_created"]
    assert not out["paper_fill_confirmed"]
    assert not out["broker_fill_confirmed"]
    assert not out["live_orders_authorized"]
    assert not out["telegram_publication_authorized"]
    assert not out["automated_execution"]
    status = panel_stage10_overview(env)
    assert status == {
        "status": "OFFLINE_PAPER_ONLY", "linked_orders": 1,
        "active_paper_reservations": 1, "broker_execution": False,
    }
    with PaperExecutionOrchestratorV1(env / "brooks_stage10_paper.sqlite") as core:
        assert core.order_state(out["order_id"])["status"] == "CREATED"
        assert D(core.risk_snapshot(PORTFOLIO)["reserved_risk"]) > 0


def test_retried_link_is_idempotent_across_restart(env):
    first = linker(env)
    other_instance = linker(env)
    assert first["order_id"] == other_instance["order_id"]
    assert other_instance["status"] == "EXISTING_PAPER_ORDER"
    assert not other_instance["risk_reservation_created"]
    assert panel_stage10_overview(env)["linked_orders"] == 1
    with PaperExecutionOrchestratorV1(env / "brooks_stage10_paper.sqlite") as core:
        assert len(core.order_events(first["order_id"])) == 1


def test_link_rejects_changed_quantity_for_same_signal(env):
    linker(env)
    with pytest.raises(BrooksStage10Refused, match="IDENTITY_CONFLICT"):
        linker(env, quantity="2.00")
    assert panel_stage10_overview(env)["linked_orders"] == 1


def test_optin_is_required_even_when_account_and_engine_are_ready(env):
    with pytest.raises(BrooksStage10Refused, match="OPTIN_REQUIRED"):
        linker(env, ack_paper_risk=False)
    assert panel_stage10_overview(env)["linked_orders"] == 0


@pytest.mark.parametrize("qty", ["0", "-1", "NaN", "Infinity", "1e1000", "abc", ""])
def test_invalid_quantity_is_fail_closed(env, qty):
    with pytest.raises(BrooksStage10Refused):
        linker(env, quantity=qty)
    assert panel_stage10_overview(env)["linked_orders"] == 0


def test_quantity_step_mismatch_rolls_back_local_bridge_and_order(env):
    with pytest.raises(RiskRefused, match="QUANTITY_STEP_VIOLATION"):
        linker(env, quantity="0.001")
    assert panel_stage10_overview(env)["linked_orders"] == 0


def test_excessive_quantity_is_risk_refused_not_sized_optimistically(env):
    with pytest.raises(RiskRefused):
        linker(env, quantity="100000.00")
    assert panel_stage10_overview(env)["active_paper_reservations"] == 0


def test_unverified_external_exposure_fails_closed(tmp_path):
    state = tmp_path / "private-state"
    create_source(state)
    configure_simulator(state, cleared=False)
    with pytest.raises(RiskRefused, match="EXTERNAL_EXPOSURE_UNVERIFIED"):
        linker(state)
    assert panel_stage10_overview(state)["linked_orders"] == 0


def test_corrupted_a7_intent_content_or_digest_is_rejected(env):
    with EngineControlStore(env) as store:
        store._db.execute(
            "UPDATE a7_paper_intents SET digest=? WHERE signal_id=?",
            ("0" * 64, SIGNAL),
        )
    with pytest.raises(BrooksStage10Refused, match="A7_DIGEST_MISMATCH"):
        linker(env)


def test_conflicting_untrusted_receipt_rejected_before_risk(env):
    with EngineControlStore(env) as store:
        row = store._db.execute(
            "SELECT receipt_json FROM brooks_paper_receipts WHERE scan_id=?",
            (SCAN,),
        ).fetchone()
        data = json.loads(row["receipt_json"])
        data["broker_order_authorized"] = True
        raw = json.dumps(data, sort_keys=True, separators=(",", ":"))
        store._db.execute(
            "UPDATE brooks_paper_receipts SET receipt_json=?,receipt_sha256=? "
            "WHERE scan_id=?", (raw, hashlib.sha256(raw.encode()).hexdigest(), SCAN),
        )
    with pytest.raises(BrooksStage10Refused, match="EVIDENCE_CONFLICT"):
        linker(env)
    assert panel_stage10_overview(env)["linked_orders"] == 0


def test_missing_scan_receipt_fails_closed(env):
    with EngineControlStore(env) as store:
        store._db.execute("DELETE FROM brooks_paper_receipts WHERE scan_id=?", (SCAN,))
    with pytest.raises(BrooksStage10Refused, match="SIGNED_LOCAL_RECEIPT_REQUIRED"):
        linker(env)


def test_stale_timeframe_setting_refuses_signal(env):
    with EngineControlStore(env) as store:
        old = store.preferences(BROOKS_ENGINE_ID)
        store.change_preference(
            BROOKS_ENGINE_ID, field="timeframe", value="1h",
            expected_revision=old["revision"], actor_id=123,
        )
    with pytest.raises(BrooksStage10Refused, match="EVIDENCE_CONFLICT"):
        linker(env)


def test_operator_disabled_brooks_blocks_link(env):
    with EngineControlStore(env) as store:
        current = store.get(BROOKS_ENGINE_ID)
        store.toggle_as_admin(
            BROOKS_ENGINE_ID, enabled=False,
            expected_revision=current.revision, actor_id=123,
        )
    with pytest.raises(BrooksStage10Refused, match="NOT_ARMED"):
        linker(env)


def test_wrong_engine_signal_and_missing_id_rejected(env):
    with pytest.raises(BrooksStage10Refused, match="NO_PERSISTED_BROOKS_SIGNAL"):
        linker(env, signal_id="unknown-signal")


def test_wrong_venue_pair_selected_rejected(env):
    with EngineControlStore(env) as store:
        # A manually modified preferences value is an untrusted / conflicting
        # admin state; never use it to authorize a historical Kraken receipt.
        store._db.execute(
            "UPDATE managed_engine_preferences SET futures_symbol=? "
            "WHERE engine_id=?", ("PF_ETHUSD", BROOKS_ENGINE_ID),
        )
    with pytest.raises(BrooksStage10Refused, match="SELECTED_FUTURES_IDENTITY_DRIFT"):
        linker(env)


def test_old_created_order_never_auto_filled_or_telegram_published(env):
    out = linker(env)
    with EngineControlStore(env) as store:
        assert store.publication(BROOKS_ENGINE_ID)["effective_publication"] is False
        assert store.route(BROOKS_ENGINE_ID)["delivery_mode"] == "DISABLED"
    with PaperExecutionOrchestratorV1(env / "brooks_stage10_paper.sqlite") as core:
        assert core.order_state(out["order_id"])["filled_quantity"] == "0"


def test_subsequent_offline_fixture_events_remain_explicit_and_durable(env):
    out = linker(env)
    oid = out["order_id"]
    with PaperExecutionOrchestratorV1(env / "brooks_stage10_paper.sqlite") as core:
        core.apply(oid, action_id="fixture-submit", event="SUBMIT")
        core.apply(
            oid, action_id="fixture-ack", event="ACK",
            remote_order_id="offline-fixture-ack",
        )
        core.apply(
            oid, action_id="fixture-fill", event="FILL",
            quantity="1.00", price="100",
        )
        core.apply(
            oid, action_id="fixture-close", event="CLOSE_FILL",
            quantity="1.00", price="121",
        )
        assert core.order_state(oid)["status"] == "CLOSED"
        assert core.risk_snapshot(PORTFOLIO)["reserved_risk"] == "0"
    assert panel_stage10_overview(env)["active_paper_reservations"] == 0
    assert linker(env)["status"] == "EXISTING_PAPER_ORDER"


def test_status_panel_never_creates_broker_or_risk_db(tmp_path):
    state = tmp_path / "no-paper-db"
    state.mkdir(mode=0o700)
    assert panel_stage10_overview(state)["status"] == "NOT_CONFIGURED"
    assert list(state.iterdir()) == []


def test_untrusted_nonregular_destination_is_refused(env, tmp_path):
    with pytest.raises(BrooksStage10Refused, match="DEDICATED_PAPER_DATABASE_REQUIRED"):
        BrooksStage10PaperBridge(env, paper_db=tmp_path / "other.sqlite")


def test_cli_requires_explicit_nonproduction_flags_and_mode(env):
    args = type("Args", (), {})()
    args.status = False
    args.ack_nonproduction_stage10_paper = True
    args.state_dir = env
    args.signal_id = SIGNAL
    args.account_id = ACCOUNT
    args.quantity = "1.00"
    for flags in (
        {}, {"MMT_NONPRODUCTION": "0"},
        {"MMT_NONPRODUCTION": "1", "MMT_PRODUCTION": "1"},
    ):
        with pytest.raises(BrooksStage10Refused, match="NONPRODUCTION_OPTIN_REQUIRED"):
            run_once(args, environment=flags)
    result = run_once(args, environment={"MMT_NONPRODUCTION": "1"})
    assert result["order_status"] == "CREATED"
    args.status = True
    assert run_once(args, environment={})["linked_orders"] == 1
