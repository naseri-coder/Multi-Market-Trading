"""Stage 5: DEMO-only MT5 read adapter and diagnostic-only PAPER comparison."""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from naseri_markets.contracts import Direction, Instrument, Market
from naseri_markets.execution_contract_v1 import OrderKind, OrderSpec
from naseri_markets.execution_position_core_v1 import PaperExecutionOrchestratorV1
from naseri_markets.mt5_demo_exposure_audit_v1 import (
    DemoTicketBinding,
    MT5ComparisonRefused,
    compare_demo_to_paper,
)
from naseri_markets.mt5_demo_readonly_adapter_v1 import (
    DemoAccountExpectation,
    MT5DemoReadOnlyAdapterV1,
    MT5ReadRefused,
)
from naseri_markets.mt5_demo_readonly_probe import run_once
from naseri_markets.risk_portfolio_contract_v1 import AccountRiskPolicy, PortfolioRiskPolicy


NOW = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0

    def __init__(self):
        self.account = NS(
            trade_mode=0, login=1234567, server="Example-Demo",
            equity=1000.5, balance=1100.0, margin_free=900.0, currency="USD",
        )
        self.terminal = NS(connected=True)
        self.positions = ()
        self.orders = ()
        self.calls = []
        self.initialized = False
        self.account_reads = 0
        self.swap_after = None

    def initialize(self):
        self.calls.append("initialize")
        self.initialized = True
        return True

    def shutdown(self):
        self.calls.append("shutdown")
        self.initialized = False

    def terminal_info(self):
        self.calls.append("terminal_info")
        return self.terminal

    def account_info(self):
        self.calls.append("account_info")
        self.account_reads += 1
        if self.swap_after and self.account_reads >= self.swap_after:
            return NS(**(vars(self.account) | {"login": 7654321}))
        return self.account

    def positions_get(self):
        self.calls.append("positions_get")
        return self.positions

    def orders_get(self):
        self.calls.append("orders_get")
        return self.orders


@pytest.fixture
def fake():
    return FakeMT5()


def expectation():
    return DemoAccountExpectation(
        account_id="demo-a", login=1234567, server="Example-Demo"
    )


def pos(ticket=567, *, symbol="EURUSD", volume=0.10, type_code=0):
    return NS(ticket=ticket, symbol=symbol, type=type_code, volume=volume,
              price_open=1.125, sl=1.11, tp=1.145)


def pending(ticket=568, *, symbol="EURUSD", type_code=2, volume=0.10):
    return NS(ticket=ticket, symbol=symbol, type=type_code,
              volume_initial=volume, volume_current=volume,
              price_open=1.125, sl=1.11, tp=1.145)


def capture(fake):
    return MT5DemoReadOnlyAdapterV1(fake, expectation()).capture(observed_at=NOW)


def instrument():
    return Instrument(market=Market.FOREX, provider="MT5-DEMO",
                      symbol="EURUSD", timezone="UTC", quote_currency="USD")


def spec():
    return OrderSpec(
        order_id="paper-1", signal_id="s1", account_id="demo-a",
        engine_id="brooks", instrument=instrument(),
        direction=Direction.LONG, kind=OrderKind.LIMIT,
        quantity=D("1"), reference_entry=D("1.125"),
        stop=D("1.11"), target=D("1.145"),
    )


def paper_core(path):
    core = PaperExecutionOrchestratorV1(path)
    core.configure_portfolio(PortfolioRiskPolicy(
        portfolio_id="demo-portfolio", currency="USD",
        max_reserved_risk=D("100"), max_notional=D("5000"),
        max_daily_loss=D("200"), max_group_risk=D("100"),
        max_engine_risk=D("100"), max_active_orders=20,
    ))
    core.configure_account(AccountRiskPolicy(
        account_id="demo-a", portfolio_id="demo-portfolio", currency="USD",
        equity=D("1000"), max_order_risk_fraction=D("0.02"),
        max_total_risk_fraction=D("0.1"),
        max_daily_loss_fraction=D("0.2"),
        max_notional_fraction=D("2"), max_margin_fraction=D("0.5"),
        max_leverage=D("3"), contract_multiplier=D("1"),
        quantity_step=D("0.01"), roundtrip_fee_fraction=D("0.001"),
        worst_slippage_fraction=D("0.001"), max_active_orders=20,
        external_exposure_cleared=True,
    ))
    core.register_instrument(
        portfolio_id="demo-portfolio", instrument=instrument(), group_id="FX"
    )
    return core


def test_happy_demo_empty_snapshot_no_mutation(fake):
    report = capture(fake)
    assert report.account_id == "demo-a"
    assert report.login == 1234567
    assert report.positions == ()
    assert report.pending_orders == ()
    assert report.wire()["history_complete"] is False
    assert report.wire()["risk_authority"] is False
    assert report.wire()["broker_execution_authority"] is False
    assert fake.calls == [
        "terminal_info", "account_info", "positions_get", "orders_get",
        "terminal_info", "account_info",
    ]


def test_demo_active_exposure_is_sorted_and_decimal(fake):
    fake.positions = (pos(600), pos(100, volume=0.02, type_code=1))
    fake.orders = (pending(900),)
    snap = capture(fake)
    assert [x.ticket for x in snap.positions] == [100, 600]
    assert snap.positions[0].volume == D("0.02")
    assert snap.pending_orders[0].kind == "PENDING_ORDER"
    assert snap.equity == D("1000.5")
    assert snap.free_margin == D("900.0")


@pytest.mark.parametrize("mode", [1, 2, -1])
def test_real_or_unknown_account_trade_mode_denied(fake, mode):
    fake.account.trade_mode = mode
    with pytest.raises(MT5ReadRefused, match="REAL_OR_UNKNOWN_ACCOUNT_FORBIDDEN"):
        capture(fake)
    assert "positions_get" not in fake.calls


def test_lookalike_demo_server_name_cannot_replace_trade_mode(fake):
    fake.account.trade_mode = 2
    fake.account.server = "Very-Legitimate-Demo"
    with pytest.raises(MT5ReadRefused):
        capture(fake)


def test_expected_login_and_server_exact_match(fake):
    fake.account.login = 222222
    with pytest.raises(MT5ReadRefused, match="LOGIN_MISMATCH"):
        capture(fake)
    fake.account.login = 1234567
    fake.account.server = "Other-Demo"
    with pytest.raises(MT5ReadRefused, match="SERVER_MISMATCH"):
        capture(fake)


def test_account_switch_during_read_is_detected(fake):
    fake.swap_after = 2
    with pytest.raises(MT5ReadRefused, match="LOGIN_MISMATCH"):
        capture(fake)
    assert fake.calls.count("positions_get") == 1


def test_terminal_disconnected_before_any_exposure_query(fake):
    fake.terminal.connected = False
    with pytest.raises(MT5ReadRefused, match="TERMINAL_DISCONNECTED"):
        capture(fake)
    assert "positions_get" not in fake.calls


@pytest.mark.parametrize("attribute", ["positions", "orders"])
def test_none_or_incomplete_query_fails_closed(fake, attribute):
    setattr(fake, attribute, None)
    with pytest.raises(MT5ReadRefused, match="ACTIVE_QUERY_INCOMPLETE"):
        capture(fake)


def test_query_exception_fails_closed(fake):
    fake.positions_get = lambda: (_ for _ in ()).throw(OSError("terminal gone"))
    with pytest.raises(MT5ReadRefused, match="ACTIVE_QUERY_EXCEPTION"):
        capture(fake)


@pytest.mark.parametrize("volume", [0, -1, float("nan"), float("inf")])
def test_invalid_active_volume_fails_closed(fake, volume):
    fake.positions = (pos(volume=volume),)
    with pytest.raises(MT5ReadRefused, match="MT5_INVALID_VOLUME"):
        capture(fake)


def test_duplicate_provider_ticket_is_refused(fake):
    fake.positions = (pos(), pos())
    with pytest.raises(MT5ReadRefused, match="DUPLICATE_ACTIVE_TICKET"):
        capture(fake)


def test_impossible_pending_volume_contradiction(fake):
    row = pending()
    row.volume_current = 2.0
    fake.orders = (row,)
    with pytest.raises(MT5ReadRefused, match="ORDER_VOLUME_INCREASE_CONTRADICTION"):
        capture(fake)


@pytest.mark.parametrize("account", [
    {"login": 0}, {"login": True}, {"server": ""}, {"trade_mode": "0"},
])
def test_incomplete_account_identity_never_authorized(fake, account):
    for key, value in account.items():
        setattr(fake.account, key, value)
    with pytest.raises(MT5ReadRefused):
        capture(fake)


def test_timestamp_must_have_timezone(fake):
    with pytest.raises(MT5ReadRefused, match="OBSERVATION_TIMESTAMP_REQUIRED"):
        MT5DemoReadOnlyAdapterV1(fake, expectation()).capture(
            observed_at=datetime(2026, 10, 11, 12, 0)
        )


def test_invalid_account_expectation_fails_without_provider_read(fake):
    with pytest.raises(ValueError, match="EXPECTED_DEMO_LOGIN_REQUIRED"):
        DemoAccountExpectation("demo-a", 0, "Example-Demo")
    assert fake.calls == []


def test_cli_opt_in_and_shutdown_on_success(fake):
    args = argparse.Namespace(
        connect_existing_demo_terminal=True, account_id="demo-a",
        expected_login=1234567, expected_server="Example-Demo", paper_ledger=None,
    )
    result = run_once(args, fake)
    assert result["snapshot"]["mode"] == "DEMO_READ_ONLY"
    assert result["reconciliation_authority"] is False
    assert fake.calls[0] == "initialize"
    assert fake.calls[-1] == "shutdown"
    assert fake.initialized is False
    assert "order_send" not in fake.calls


def test_cli_refuses_non_demo_but_shuts_down(fake):
    fake.account.trade_mode = 2
    args = argparse.Namespace(
        connect_existing_demo_terminal=True, account_id="demo-a",
        expected_login=1234567, expected_server="Example-Demo", paper_ledger=None,
    )
    with pytest.raises(MT5ReadRefused):
        run_once(args, fake)
    assert fake.calls[-1] == "shutdown"


def test_cli_explicit_opt_in_required_before_initialize(fake):
    args = argparse.Namespace(
        connect_existing_demo_terminal=False, account_id="demo-a",
        expected_login=1234567, expected_server="Example-Demo", paper_ledger=None,
    )
    with pytest.raises(MT5ReadRefused, match="EXPLICIT_DEMO_TERMINAL_OPT_IN_REQUIRED"):
        run_once(args, fake)
    assert fake.calls == []


def test_comparison_reads_real_stage3_paper_ledger_without_writing(fake, tmp_path):
    db = tmp_path / "stage3.sqlite"
    with paper_core(db) as core:
        core.create(spec(), action_id="create")
        core.apply("paper-1", action_id="sent", event="SUBMIT")
        core.apply("paper-1", action_id="ack", event="ACK",
                   remote_order_id="paper-remote")
        core.apply("paper-1", action_id="fill", event="FILL",
                   quantity="1", price="1.125")
        before_events = len(core.order_events("paper-1"))
        budget = core.risk_snapshot("demo-portfolio")
        fake.positions = (pos(),)
        snapshot = capture(fake)
        result = compare_demo_to_paper(snapshot, ledger=db, account_id="demo-a")
        codes = [x["code"] for x in result["discrepancies"]]
        assert "UNASSOCIATED_DEMO_OPEN_POSITION" in codes
        assert "LOCAL_POSITION_REQUIRES_MANUAL_TICKET_BINDING" in codes
        assert result["may_release_paper_risk"] is False
        assert result["may_unlock_paper_recovery"] is False
        assert result["may_execute_trades"] is False
        assert core.risk_snapshot("demo-portfolio") == budget
        assert len(core.order_events("paper-1")) == before_events


def test_operator_ticket_binding_and_explicit_lot_conversion_are_diagnostic(fake, tmp_path):
    db = tmp_path / "stage3.sqlite"
    with paper_core(db) as core:
        core.create(spec(), action_id="create")
        core.apply("paper-1", action_id="sent", event="SUBMIT")
        core.apply("paper-1", action_id="ack", event="ACK",
                   remote_order_id="paper-remote")
        core.apply("paper-1", action_id="fill", event="FILL",
                   quantity="1", price="1.125")
        fake.positions = (pos(volume=0.10),)
        snapshot = capture(fake)
        bound = compare_demo_to_paper(
            snapshot, ledger=db, account_id="demo-a",
            bindings=(DemoTicketBinding("paper-1", position_ticket=567),),
        )
        assert "VOLUME_UNIT_CONVERSION_UNVERIFIED" in {
            x["code"] for x in bound["discrepancies"]
        }
        verified = compare_demo_to_paper(
            snapshot, ledger=db, account_id="demo-a",
            bindings=(DemoTicketBinding(
                "paper-1", position_ticket=567,
                mt5_lots_per_paper_unit=D("0.10"),
            ),),
        )
        assert verified["discrepancies"] == []
        assert verified["history_complete"] is False
        assert verified["may_unlock_paper_recovery"] is False


def test_mismatched_mt5_lots_never_auto_cleans_risk(fake, tmp_path):
    db = tmp_path / "stage3.sqlite"
    with paper_core(db) as core:
        core.create(spec(), action_id="create")
        core.apply("paper-1", action_id="sent", event="SUBMIT")
        core.apply("paper-1", action_id="ack", event="ACK",
                   remote_order_id="paper-remote")
        core.apply("paper-1", action_id="fill", event="FILL",
                   quantity="1", price="1.125")
        fake.positions = (pos(volume=0.50),)
        before = core.risk_snapshot("demo-portfolio")
        report = compare_demo_to_paper(
            capture(fake), ledger=db, account_id="demo-a",
            bindings=(DemoTicketBinding(
                "paper-1", position_ticket=567, mt5_lots_per_paper_unit=D("0.10")
            ),),
        )
        assert "BOUND_POSITION_LOT_VOLUME_MISMATCH" in {
            x["code"] for x in report["discrepancies"]
        }
        assert core.risk_snapshot("demo-portfolio") == before


def test_empty_demo_positions_are_not_evidence_that_submitted_order_rejected(
    fake, tmp_path,
):
    db = tmp_path / "stage3.sqlite"
    with paper_core(db) as core:
        core.create(spec(), action_id="create")
        core.apply("paper-1", action_id="send", event="SUBMIT")
        core.apply("paper-1", action_id="unknown", event="MARK_UNKNOWN")
        result = compare_demo_to_paper(capture(fake), ledger=db, account_id="demo-a")
        assert "HISTORICAL_ORDER_EVIDENCE_REQUIRED" in {
            x["code"] for x in result["discrepancies"]
        }
        assert core.order_state("paper-1")["status"] == "SUBMISSION_UNKNOWN"
        assert core.risk_snapshot("demo-portfolio")["active_orders"] == 1


def test_wrong_account_or_invalid_database_fails_closed(fake, tmp_path):
    with pytest.raises(MT5ComparisonRefused, match="LOCAL_ACCOUNT_IDENTITY_MISMATCH"):
        compare_demo_to_paper(capture(fake), ledger=tmp_path / "x", account_id="other")
    with pytest.raises(MT5ComparisonRefused, match="PAPER_LEDGER_NOT_REGULAR_FILE"):
        compare_demo_to_paper(capture(fake), ledger=tmp_path / "missing.sqlite",
                              account_id="demo-a")


def test_duplicate_manual_ticket_binding_rejected(fake, tmp_path):
    with pytest.raises(MT5ComparisonRefused, match="DUPLICATE_BINDING_TICKET"):
        compare_demo_to_paper(
            capture(fake), ledger=tmp_path / "missing",
            account_id="demo-a",
            bindings=(DemoTicketBinding("p1", position_ticket=123),
                      DemoTicketBinding("p2", position_ticket=123)),
        )


def test_manual_conversion_must_be_positive_decimal():
    with pytest.raises(ValueError):
        DemoTicketBinding("p1", position_ticket=567, mt5_lots_per_paper_unit=D("NaN"))
    with pytest.raises(ValueError, match="LOT_CONVERSION_REQUIRES_POSITION_TICKET"):
        DemoTicketBinding("p1", mt5_lots_per_paper_unit=D("0.1"))


def test_paper_readonly_audit_is_not_an_stage4_provider_receipt(fake):
    from naseri_markets.offline_broker_fixture_v1 import BrokerSnapshot

    snapshot = capture(fake)
    assert not isinstance(snapshot, BrokerSnapshot)
    assert "history_complete" in json.loads(json.dumps(snapshot.wire()))
