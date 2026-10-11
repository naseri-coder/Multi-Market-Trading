"""Stage 6: MT5 DEMO windowed order/deal history and diagnostic-only audit."""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from types import SimpleNamespace as NS

import pytest

from naseri_markets.contracts import Direction, Instrument, Market
from naseri_markets.execution_contract_v1 import OrderKind, OrderSpec
from naseri_markets.execution_position_core_v1 import PaperExecutionOrchestratorV1
from naseri_markets.mt5_demo_history_audit_v1 import (
    HistoricalTicketBinding,
    MT5HistoryAuditRefused,
    audit_demo_history,
)
from naseri_markets.mt5_demo_history_probe import run_once
from naseri_markets.mt5_demo_history_readonly_v1 import (
    MT5DemoHistoryReaderV1,
    MT5HistoryRefused,
)
from naseri_markets.mt5_demo_readonly_adapter_v1 import DemoAccountExpectation
from naseri_markets.risk_portfolio_contract_v1 import (
    AccountRiskPolicy,
    PortfolioRiskPolicy,
)

START = datetime(2026, 10, 1, tzinfo=UTC)
END = START + timedelta(days=2)
T1 = int((START + timedelta(hours=4)).timestamp() * 1000)
T2 = int((START + timedelta(days=1)).timestamp() * 1000)
T3 = int((START + timedelta(days=1, hours=4)).timestamp() * 1000)


def order_row(ticket=101, *, position=501, at=T1, volume=0.3, symbol="EURUSD"):
    return NS(
        ticket=ticket, position_id=position, symbol=symbol,
        type=0, state=4, time_setup_msc=at - 1000,
        time_done_msc=at, volume_initial=volume, volume_current=0.0,
        price_open=1.125,
    )


def deal_row(
    ticket=201, *, order=101, position=501, at=T1, volume=0.1,
    price=1.125, entry=0, type=0, symbol="EURUSD", profit=0.0,
):
    return NS(
        ticket=ticket, order=order, position_id=position,
        type=type, entry=entry, time_msc=at, volume=volume,
        price=price, profit=profit, commission=-0.1,
        swap=0.0, fee=-0.05, symbol=symbol,
    )


class FakeMT5History:
    ACCOUNT_TRADE_MODE_DEMO = 0

    def __init__(self):
        self.account = NS(
            trade_mode=0, login=98765, server="Broker-Demo",
        )
        self.terminal = NS(connected=True)
        self.orders = [order_row(), order_row(102, at=T3)]
        self.deals = [
            deal_row(), deal_row(202, at=T2, volume=0.2, price=1.15),
            deal_row(203, order=102, at=T3, entry=1,
                     type=1, volume=0.15, price=1.2, profit=22.0),
        ]
        self.calls: list[str] = []
        self.total_offset = 0
        self.disconnected_at = 0
        self.history_fail = False
        self.account_switch_at = 0
        self.account_reads = 0
        self.initialized = False

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
        self.account_reads += 1
        self.calls.append("account_info")
        if self.account_switch_at and self.account_reads >= self.account_switch_at:
            return NS(**(vars(self.account) | {"login": 999999}))
        return self.account

    def _window(self, entries, start, end, key):
        left = int(start.timestamp() * 1000)
        right = int(end.timestamp() * 1000)
        return tuple(row for row in entries if left <= getattr(row, key) <= right)

    def history_orders_get(self, start, end):
        self.calls.append("history_orders_get")
        if self.history_fail:
            return None
        return self._window(self.orders, start, end, "time_done_msc")

    def history_deals_get(self, start, end):
        self.calls.append("history_deals_get")
        return self._window(self.deals, start, end, "time_msc")

    def history_orders_total(self, start, end):
        self.calls.append("history_orders_total")
        return len(self._window(self.orders, start, end, "time_done_msc")) + self.total_offset

    def history_deals_total(self, start, end):
        self.calls.append("history_deals_total")
        return len(self._window(self.deals, start, end, "time_msc"))


@pytest.fixture
def provider():
    return FakeMT5History()


def expected():
    return DemoAccountExpectation(account_id="demo-a", login=98765, server="Broker-Demo")


def read(provider, *, start=START, end=END):
    return MT5DemoHistoryReaderV1(provider, expected()).capture(
        start, end, captured_at=END,
    )


def paper_spec():
    return OrderSpec(
        order_id="paper-1", signal_id="s1", account_id="demo-a",
        engine_id="brooks",
        instrument=Instrument(
            market=Market.FOREX, provider="MT5-DEMO",
            symbol="EURUSD", timezone="UTC", quote_currency="USD",
        ),
        direction=Direction.LONG, kind=OrderKind.LIMIT,
        quantity=D("1"), reference_entry=D("1.125"),
        stop=D("1.11"), target=D("1.15"),
    )


def paper_core(path):
    core = PaperExecutionOrchestratorV1(path)
    core.configure_portfolio(PortfolioRiskPolicy(
        portfolio_id="paper-folio", currency="USD", max_reserved_risk=D("100"),
        max_notional=D("5000"), max_daily_loss=D("200"), max_group_risk=D("100"),
        max_engine_risk=D("100"), max_active_orders=10,
    ))
    core.configure_account(AccountRiskPolicy(
        account_id="demo-a", portfolio_id="paper-folio", currency="USD",
        equity=D("1000"), max_order_risk_fraction=D("0.05"),
        max_total_risk_fraction=D("0.2"), max_daily_loss_fraction=D("0.2"),
        max_notional_fraction=D("2"), max_margin_fraction=D("0.9"),
        max_leverage=D("3"), contract_multiplier=D("1"),
        quantity_step=D("0.01"), roundtrip_fee_fraction=D("0.002"),
        worst_slippage_fraction=D("0.003"), max_active_orders=10,
        external_exposure_cleared=True,
    ))
    core.register_instrument(
        portfolio_id="paper-folio", instrument=paper_spec().instrument, group_id="FX"
    )
    return core


def fill_paper(core):
    core.create(paper_spec(), action_id="create")
    core.apply("paper-1", action_id="send", event="SUBMIT")
    core.apply("paper-1", action_id="ack", event="ACK",
               remote_order_id="paper-fixture-ack")
    core.apply("paper-1", action_id="filled", event="FILL",
               quantity="1", price="1.125")


def test_full_bounded_history_and_deal_linkage(provider):
    record = read(provider)
    assert len(record.orders) == 2
    assert len(record.deals) == 3
    assert record.slices == 2
    assert [d.order_ticket for d in record.deals] == [101, 101, 102]
    assert {d.position_id for d in record.deals} == {501}
    assert record.wire()["window_complete"] is True
    assert record.wire()["all_time_history_complete"] is False
    assert record.wire()["risk_authority"] is False
    assert "order_send" not in provider.calls
    assert provider.calls.count("history_deals_get") == 2


def test_entry_exit_vwap_and_net_accounting(provider):
    report = audit_demo_history(read(provider))
    position = report["position_summaries"][0]
    assert position["window_entry_lots"] == "0.3"
    assert position["window_exit_lots"] == "0.15"
    assert D(position["entry_vwap"]) == D("1.141666666666666666666666667")
    assert position["exit_vwap"] == "1.2"
    assert D(position["reported_net_cashflows"]) == D("21.55")
    assert report["may_execute_trades"] is False
    assert report["may_release_paper_risk"] is False


def test_boundary_overlap_deduplicated_by_order_and_deal_ticket(provider):
    duplicate = read(provider)
    assert len(duplicate.orders) == 2
    assert len(duplicate.deals) == 3
    assert duplicate.digest == read(provider).digest


def test_same_ticket_different_content_across_slices_fails(provider):
    class DriftingProvider(FakeMT5History):
        def history_deals_get(self, start, end):
            result = super().history_deals_get(start, end)
            if start > START:
                return tuple(
                    NS(**(vars(row) | {"price": 9.99}))
                    if row.ticket == 202 else row for row in result
                )
            return result
    with pytest.raises(MT5HistoryRefused, match="TICKET_REPLAY_CONFLICT"):
        read(DriftingProvider())


def test_account_real_before_first_history_read(provider):
    provider.account.trade_mode = 2
    with pytest.raises(ValueError, match="REAL_OR_UNKNOWN_ACCOUNT_FORBIDDEN"):
        read(provider)
    assert "history_orders_get" not in provider.calls


def test_account_switch_mid_query_fails_no_partial_snapshot(provider):
    provider.account_switch_at = 3
    with pytest.raises(ValueError, match="LOGIN_MISMATCH"):
        read(provider)


def test_disconnected_terminal_never_queries_history(provider):
    provider.terminal.connected = False
    with pytest.raises(ValueError, match="TERMINAL_DISCONNECTED"):
        read(provider)
    assert "history_orders_get" not in provider.calls


@pytest.mark.parametrize("bad_result", [True, False])
def test_none_history_or_negative_count_fails_closed(provider, bad_result):
    if bad_result:
        provider.history_fail = True
        expected_code = "MT5_HISTORY_INCOMPLETE_RESPONSE"
    else:
        provider.total_offset = -100
        expected_code = "MT5_HISTORY_TOTAL_MISMATCH"
    with pytest.raises(MT5HistoryRefused, match=expected_code):
        read(provider)


def test_nonmatching_totals_are_refused(provider):
    provider.total_offset = 1
    with pytest.raises(MT5HistoryRefused, match="MT5_HISTORY_TOTAL_MISMATCH"):
        read(provider)


@pytest.mark.parametrize("a,b", [
    (START, START),
    (END, START),
    (START.replace(tzinfo=None), END),
    (START, END.replace(tzinfo=None)),
    (START, START + timedelta(days=32)),
])
def test_invalid_time_scope_refused_before_provider_query(provider, a, b):
    with pytest.raises(MT5HistoryRefused):
        read(provider, start=a, end=b)
    assert "history_orders_get" not in provider.calls


def test_small_explicit_window_and_strict_row_limit(provider):
    with pytest.raises(MT5HistoryRefused, match="SLICE_TOO_LARGE"):
        MT5DemoHistoryReaderV1(provider, expected(), max_rows=1).capture(START, END)


@pytest.mark.parametrize("value", [float("nan"), -1.0, float("inf")])
def test_invalid_deal_volume_fails_closed(provider, value):
    provider.deals[0].volume = value
    with pytest.raises(ValueError, match="MT5_INVALID_VOLUME"):
        read(provider)


def test_nontrade_balance_deal_preserved_but_never_counted_as_fill(provider):
    balance = deal_row(
        ticket=555, order=0, position=0, at=T1,
        type=2, entry=0, volume=0, price=0, symbol="", profit=100,
    )
    provider.deals.append(balance)
    report = audit_demo_history(read(provider))
    assert report["deals"] == 4
    assert report["position_summaries"][0]["window_entry_lots"] == "0.3"


@pytest.mark.parametrize("bad_entry", [2, 3])
def test_reversal_or_close_by_is_not_automatically_replayed(provider, bad_entry):
    provider.deals[2].entry = bad_entry
    report = audit_demo_history(read(provider))
    codes = {item["code"] for item in report["issues"]}
    assert "REVERSAL_OR_CLOSE_BY_REQUIRES_INDEPENDENT_REVIEW" in codes


def test_trade_deal_missing_position_identity_fails(provider):
    provider.deals[0].position_id = 0
    with pytest.raises(MT5HistoryRefused, match="TRADE_DEAL_MISSING_ORDER_OR_POSITION"):
        read(provider)


def test_duplicate_row_ticket_with_different_payload_refused(provider):
    provider.deals.append(deal_row(ticket=201, price=9.99))
    with pytest.raises(MT5HistoryRefused, match="TICKET_REPLAY_CONFLICT"):
        read(provider)


def test_order_remaining_more_than_initial_refused(provider):
    provider.orders[0].volume_current = 0.5
    with pytest.raises(MT5HistoryRefused, match="REMAINING_EXCEEDS_INITIAL"):
        read(provider)


def test_empty_requested_window_is_not_all_time_exposure_proof(provider):
    provider.orders = []
    provider.deals = []
    snap = read(provider)
    assert snap.orders == () and snap.deals == ()
    report = audit_demo_history(snap)
    assert report["all_time_history_complete"] is False
    assert report["may_unlock_stage4_fence"] is False


def test_fee_commission_profit_nonfinite_refused(provider):
    provider.deals[0].commission = float("nan")
    with pytest.raises(MT5HistoryRefused, match="INVALID_COMMISSION"):
        read(provider)


def test_deal_order_absent_from_bounded_window_yields_diagnostic_not_invention(provider):
    provider.orders = [provider.orders[0]]
    report = audit_demo_history(read(provider))
    assert "DEAL_ORDER_OUTSIDE_CAPTURED_WINDOW" in {
        item["code"] for item in report["issues"]
    }


def test_paper_binding_reports_partial_close_discrepancy_without_mutations(
    provider, tmp_path,
):
    db = tmp_path / "paper.sqlite"
    with paper_core(db) as core:
        fill_paper(core)
        before = core.risk_snapshot("paper-folio")
        before_events = len(core.order_events("paper-1"))
        report = audit_demo_history(
            read(provider), paper_ledger=db, account_id="demo-a",
            bindings=(HistoricalTicketBinding("paper-1", 101, 501, D("0.3")),),
        )
        assert "BOUND_CUMULATIVE_EXIT_LOTS_MISMATCH" in {
            item["code"] for item in report["issues"]
        }
        assert core.risk_snapshot("paper-folio") == before
        assert len(core.order_events("paper-1")) == before_events
        assert report["may_unlock_stage4_fence"] is False


def test_consistent_mock_history_never_grants_risk_authority(provider, tmp_path):
    db = tmp_path / "paper.sqlite"
    with paper_core(db) as core:
        fill_paper(core)
        core.apply("paper-1", action_id="close", event="CLOSE_FILL",
                   quantity="0.5", price="1.2")
        report = audit_demo_history(
            read(provider), paper_ledger=db, account_id="demo-a",
            bindings=(HistoricalTicketBinding("paper-1", 101, 501, D("0.3")),),
        )
        assert report["issues"] == []
        assert report["may_release_paper_risk"] is False
        assert report["may_execute_trades"] is False
        assert core.order_state("paper-1")["open_position_quantity"] == "0.5"


def test_without_verified_manual_bindings_local_fills_stay_unattributed(
    provider, tmp_path,
):
    db = tmp_path / "paper.sqlite"
    with paper_core(db) as core:
        fill_paper(core)
        report = audit_demo_history(
            read(provider), paper_ledger=db, account_id="demo-a",
        )
        assert "PAPER_ORDER_REQUIRES_OPERATOR_HISTORY_BINDING" in {
            item["code"] for item in report["issues"]
        }


def test_duplicate_mapping_and_missing_ledger_denied(provider, tmp_path):
    binding = HistoricalTicketBinding("paper-1", 101, 501, D("0.3"))
    with pytest.raises(MT5HistoryAuditRefused, match="BINDINGS_REQUIRE_PAPER_LEDGER"):
        audit_demo_history(read(provider), bindings=(binding,))
    with pytest.raises(MT5HistoryAuditRefused, match="DUPLICATE_HISTORY_BINDING"):
        audit_demo_history(read(provider), bindings=(binding, binding),
                           paper_ledger=tmp_path / "does-not-exist", account_id="demo-a")


def test_wrong_paper_account_and_unreadable_db_denied(provider, tmp_path):
    with pytest.raises(MT5HistoryAuditRefused, match="PAPER_ACCOUNT_IDENTITY_MISMATCH"):
        audit_demo_history(
            read(provider), paper_ledger=tmp_path / "x", account_id="wrong-account",
        )
    with pytest.raises(MT5HistoryAuditRefused, match="PAPER_LEDGER_NOT_REGULAR_FILE"):
        audit_demo_history(
            read(provider), paper_ledger=tmp_path / "x", account_id="demo-a",
        )


def test_account_not_allowed_to_infer_unknown_order_is_rejected(
    provider, tmp_path,
):
    db = tmp_path / "paper.sqlite"
    with paper_core(db) as core:
        core.create(paper_spec(), action_id="create")
        core.apply("paper-1", action_id="send", event="SUBMIT")
        core.apply("paper-1", action_id="unknown", event="MARK_UNKNOWN")
        audit = audit_demo_history(
            read(provider), paper_ledger=db, account_id="demo-a",
        )
        assert audit["may_release_paper_risk"] is False
        assert core.order_state("paper-1")["status"] == "SUBMISSION_UNKNOWN"
        assert core.risk_snapshot("paper-folio")["active_orders"] == 1


def test_probe_cli_explicit_opt_in_and_sdk_shutdown(provider):
    args = argparse.Namespace(
        connect_existing_demo_terminal=True,
        account_id="demo-a", expected_login=98765, expected_server="Broker-Demo",
        start_utc=START.isoformat(), end_utc=END.isoformat(), paper_ledger=None,
    )
    report = run_once(args, provider)
    assert report["history"]["window_complete"]
    assert report["order_execution_authority"] is False
    assert provider.calls[0] == "initialize"
    assert provider.calls[-1] == "shutdown"
    assert "order_send" not in provider.calls
    assert not provider.initialized


def test_probe_shutdown_even_on_real_account(provider):
    provider.account.trade_mode = 2
    args = argparse.Namespace(
        connect_existing_demo_terminal=True, account_id="demo-a",
        expected_login=98765, expected_server="Broker-Demo",
        start_utc=START.isoformat(), end_utc=END.isoformat(), paper_ledger=None,
    )
    with pytest.raises(ValueError, match="REAL_OR_UNKNOWN_ACCOUNT_FORBIDDEN"):
        run_once(args, provider)
    assert provider.calls[-1] == "shutdown"


def test_no_optin_prevents_terminal_initialize(provider):
    args = argparse.Namespace(
        connect_existing_demo_terminal=False, account_id="demo-a",
        expected_login=98765, expected_server="Broker-Demo",
        start_utc=START.isoformat(), end_utc=END.isoformat(), paper_ledger=None,
    )
    with pytest.raises(MT5HistoryRefused, match="OPT_IN_REQUIRED"):
        run_once(args, provider)
    assert provider.calls == []


def test_identical_snapshot_wire_has_deterministic_content_digest(provider):
    first = read(provider)
    second = replace(first, captured_at=END + timedelta(hours=1))
    assert first.digest == second.digest
    assert json.loads(json.dumps(first.wire()))["all_time_history_complete"] is False
