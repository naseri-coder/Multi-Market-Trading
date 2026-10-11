"""Stage 8: independent DEMO requery, position lineage, read-only custody."""
from __future__ import annotations

import argparse
import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from types import SimpleNamespace as NS

import pytest

from naseri_markets.mt5_demo_evidence_custody_v1 import (
    DemoHistoryEvidenceCustodyV1,
    EvidenceCustodyRefused,
)
from naseri_markets.mt5_demo_independent_reverify_v1 import (
    MT5DemoIndependentReverifierV1,
    MT5ReverificationRefused,
)
from naseri_markets.mt5_demo_readonly_adapter_v1 import DemoAccountExpectation
from naseri_markets.mt5_demo_reverify_probe import run_once

START = datetime(2026, 10, 1, tzinfo=UTC)
END = START + timedelta(days=1)
T1 = int((START + timedelta(hours=4)).timestamp() * 1000)
T2 = int((START + timedelta(hours=7)).timestamp() * 1000)


def order(ticket=101, at=T1, *, pid=501, symbol="EURUSD"):
    return NS(
        ticket=ticket, position_id=pid, symbol=symbol, type=0, state=4,
        time_setup_msc=at-100, time_done_msc=at,
        volume_initial=1.0, volume_current=0.0, price_open=100.0,
    )


def deal(ticket=201, at=T1, *, oid=101, pid=501, symbol="EURUSD",
         side=0, entry=0, volume=1.0, price=100.0):
    return NS(
        ticket=ticket, order=oid, position_id=pid, symbol=symbol,
        type=side, entry=entry, time_msc=at, volume=volume,
        price=price, profit=0.0, commission=-0.1, swap=0.0, fee=-0.01,
    )


def active(ticket=901, identifier=501, *, symbol="EURUSD", side=0, volume=0.6):
    return NS(
        ticket=ticket, identifier=identifier, symbol=symbol,
        type=side, volume=volume,
    )


class MockMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_MARGIN_MODE_RETAIL_NETTING = 0
    ACCOUNT_MARGIN_MODE_RETAIL_HEDGING = 2

    def __init__(self, *, netting=False):
        self.account = NS(
            trade_mode=0, margin_mode=0 if netting else 2,
            login=1234567, server="Fixture-Demo",
        )
        self.terminal = NS(connected=True)
        self.orders = [order(), order(102, T2)]
        self.deals = [
            deal(), deal(202, T2, oid=102, side=1,
                         entry=1, volume=0.4, price=110.0),
        ]
        self.active = [active()]
        self.calls: list[str] = []
        self._reads = 0
        self.change_login_at: int | None = None
        self.change_mode_at: int | None = None
        self.missing_position_history = False
        self.target_extra = False
        self.target_error = False

    def initialize(self):
        self.calls.append("initialize")
        return True

    def shutdown(self):
        self.calls.append("shutdown")

    def terminal_info(self):
        self.calls.append("terminal_info")
        return self.terminal

    def account_info(self):
        self.calls.append("account_info")
        self._reads += 1
        values = vars(self.account).copy()
        if self.change_login_at and self._reads >= self.change_login_at:
            values["login"] = 7654321
        if self.change_mode_at and self._reads >= self.change_mode_at:
            values["margin_mode"] = 0 if values["margin_mode"] == 2 else 2
        return NS(**values)

    def _range(self, values, start, end, key):
        first, last = int(start.timestamp()*1000), int(end.timestamp()*1000)
        return tuple(item for item in values if first <= getattr(item, key) <= last)

    def history_orders_get(self, *args, **kwargs):
        self.calls.append("history_orders_get")
        if "position" in kwargs:
            if self.target_error:
                raise RuntimeError("broken target")
            if self.missing_position_history:
                return ()
            return tuple(item for item in self.orders
                         if item.position_id == kwargs["position"])
        return self._range(self.orders, args[0], args[1], "time_done_msc")

    def history_deals_get(self, *args, **kwargs):
        self.calls.append("history_deals_get")
        if "position" in kwargs:
            if self.target_error:
                raise RuntimeError("broken target")
            matched = tuple(item for item in self.deals
                            if item.position_id == kwargs["position"])
            if self.target_extra:
                return matched + (deal(
                    299, T2+100, oid=102, side=1, entry=1,
                    volume=0.1, price=110,
                ),)
            return matched
        return self._range(self.deals, args[0], args[1], "time_msc")

    def history_orders_total(self, start, end):
        return len(self._range(self.orders, start, end, "time_done_msc"))

    def history_deals_total(self, start, end):
        return len(self._range(self.deals, start, end, "time_msc"))

    def positions_get(self):
        self.calls.append("positions_get")
        return self.active


def expected():
    return DemoAccountExpectation(
        account_id="demo-a", login=1234567, server="Fixture-Demo",
    )


@pytest.fixture
def prepared(tmp_path):
    db = tmp_path / "custody.sqlite"
    provider = MockMT5()
    with DemoHistoryEvidenceCustodyV1(db) as custody:
        token = custody.open_read_session(provider, expected())
        receipt = custody.capture_and_append(
            provider, expected(), START, END,
            session=token, action_id="capture-1", captured_at=END,
        )
        original_head = custody.verify("demo-a")["head"]
    yield db, provider, receipt, original_head


def verify(db, provider, **kwargs):
    return MT5DemoIndependentReverifierV1(
        provider, expected(), custody_path=db, **kwargs,
    ).verify(START, END, observed_at=END)


def test_independent_window_and_position_lineage_matching(prepared):
    db, provider, receipt, head = prepared
    report = verify(db, provider)
    assert report["content_matches_stored_window"]
    assert report["receipt_digest"] == receipt["content_digest"]
    assert report["custody_head"] == head
    assert report["targeted_positions_checked"] == 1
    lineage = report["position_checks"][0]
    assert lineage["position_id"] == 501
    assert lineage["targeted_deals"] == 2
    assert lineage["targeted_orders"] == 2
    assert lineage["issues"] == []
    assert lineage["active_identifier_confirmed"]
    assert lineage["active_ticket"] == 901
    assert lineage["accounting"]["positions"][0]["signed_lots_window_only"] == "0.6"
    assert not report["needs_review"]
    assert not report["broker_cryptographically_authenticated"]
    assert not report["all_position_lifespans_proven"]
    assert not report["may_execute_order"]
    assert not report["may_unlock_stage4"]
    assert not report["may_release_paper_risk"]


def test_verification_does_not_modify_custody_or_counters(prepared):
    db, provider, _, _ = prepared
    before = db.stat().st_mtime_ns
    result = verify(db, provider)
    after = db.stat().st_mtime_ns
    with DemoHistoryEvidenceCustodyV1(db, read_only=True) as custody:
        assert custody.verify("demo-a")["windows"] == 1
        with pytest.raises(EvidenceCustodyRefused, match="READONLY_CUSTODY_CANNOT_MUTATE"):
            custody.open_read_session(provider, expected())
    assert result["content_matches_stored_window"]
    assert before == after


def test_requery_refuses_when_broker_deal_price_changes(prepared):
    db, provider, _, _ = prepared
    provider.deals[1].price = 123.45
    with pytest.raises(MT5ReverificationRefused, match="INDEPENDENT_HISTORY_CONTENT_MISMATCH"):
        verify(db, provider)


def test_requery_refuses_broker_missing_historical_deal(prepared):
    db, provider, _, _ = prepared
    provider.deals.pop()
    with pytest.raises(MT5ReverificationRefused, match="INDEPENDENT_HISTORY_CONTENT_MISMATCH"):
        verify(db, provider)


def test_requery_refuses_broker_order_revision(prepared):
    db, provider, _, _ = prepared
    provider.orders[1].volume_initial = 1.9
    with pytest.raises(MT5ReverificationRefused, match="INDEPENDENT_HISTORY_CONTENT_MISMATCH"):
        verify(db, provider)


def test_targeted_query_returns_missing_orders_no_false_proof(prepared):
    db, provider, _, _ = prepared
    provider.missing_position_history = True
    with pytest.raises(MT5ReverificationRefused, match="TARGETED_VS_WINDOW_HISTORY_CONFLICT"):
        verify(db, provider)


def test_targeted_query_has_unexpected_deal_in_window_fails(prepared):
    db, provider, _, _ = prepared
    provider.target_extra = True
    with pytest.raises(MT5ReverificationRefused, match="TARGETED_VS_WINDOW_HISTORY_CONFLICT"):
        verify(db, provider)


def test_provider_targeted_query_exception_fails_closed(prepared):
    db, provider, _, _ = prepared
    provider.target_error = True
    with pytest.raises(MT5ReverificationRefused, match="TARGETED_POSITION_QUERY_FAILED"):
        verify(db, provider)


def test_broker_reported_new_active_volume_difference_flagged(prepared):
    db, provider, _, _ = prepared
    provider.active[0].volume = 0.7
    report = verify(db, provider)
    assert report["needs_review"]
    assert "ACTIVE_POSITION_MISMATCH" in report["position_checks"][0]["issues"]
    assert not report["may_unlock_stage4"]


def test_missing_active_position_when_history_open_flags(prepared):
    db, provider, _, _ = prepared
    provider.active = []
    report = verify(db, provider)
    assert report["needs_review"]
    assert "RECORDED_POSITION_NOT_CURRENTLY_ACTIVE" in report["position_checks"][0]["issues"]


def test_unknown_open_position_not_attributed_to_history(prepared):
    db, provider, _, _ = prepared
    provider.active.append(active(903, 900, volume=1.2))
    report = verify(db, provider)
    assert report["unmatched_open_position_identifiers"] == [900]
    assert report["needs_review"]


def test_netting_multiple_simultaneous_positions_same_symbol_rejected(tmp_path):
    db = tmp_path / "custody.sqlite"
    provider = MockMT5(netting=True)
    with DemoHistoryEvidenceCustodyV1(db) as custody:
        session = custody.open_read_session(provider, expected())
        custody.capture_and_append(
            provider, expected(), START, END, session=session,
            action_id="n-1", captured_at=END,
        )
    provider.active.append(active(902, 502))
    with pytest.raises(MT5ReverificationRefused, match="NETTING_MULTIPLE_OPEN_POSITIONS"):
        verify(db, provider)


def test_hedging_two_opposite_positions_same_symbol_independent(tmp_path):
    db = tmp_path / "custody.sqlite"
    provider = MockMT5()
    provider.orders.append(order(103, T2, pid=502))
    provider.deals.append(deal(
        203, T2, oid=103, pid=502, side=1, entry=0, volume=0.4,
    ))
    provider.active.append(active(904, 502, side=1, volume=0.4))
    with DemoHistoryEvidenceCustodyV1(db) as custody:
        session = custody.open_read_session(provider, expected())
        custody.capture_and_append(
            provider, expected(), START, END, session=session,
            action_id="h-1", captured_at=END,
        )
    report = verify(db, provider)
    assert report["account_mode"] == "HEDGING"
    assert report["targeted_positions_checked"] == 2
    assert {x["position_id"] for x in report["position_checks"]} == {501, 502}
    assert not report["needs_review"]


def test_active_identifier_differs_from_mutable_position_ticket(prepared):
    db, provider, _, _ = prepared
    provider.active[0].ticket = 998811
    report = verify(db, provider)
    assert report["position_checks"][0]["active_ticket"] == 998811
    assert not report["needs_review"]


def test_margin_mode_drift_fails(prepared):
    db, provider, _, _ = prepared
    provider.account.margin_mode = 0
    with pytest.raises(MT5ReverificationRefused, match="CUSTODY_DEMO_ACCOUNT_MODE_DRIFT"):
        verify(db, provider)


def test_real_account_refused_before_history_requests(prepared):
    db, provider, _, _ = prepared
    provider.calls.clear()
    provider.account.trade_mode = 2
    with pytest.raises(ValueError, match="REAL_OR_UNKNOWN_ACCOUNT_FORBIDDEN"):
        verify(db, provider)
    assert "history_deals_get" not in provider.calls


def test_demo_account_switch_on_requery_fails(prepared):
    db, provider, _, _ = prepared
    provider.change_login_at = provider._reads + 3
    with pytest.raises(ValueError, match="LOGIN_MISMATCH"):
        verify(db, provider)


def test_stale_or_wrong_demo_custody_path_refused(prepared, tmp_path):
    _, provider, _, _ = prepared
    with pytest.raises(EvidenceCustodyRefused, match="READ_ONLY_SOURCE_MISSING"):
        verify(tmp_path / "not-present.sqlite", provider)


def test_corrupted_chain_prevents_read_only_verification(prepared):
    db, provider, _, _ = prepared
    with sqlite3.connect(db) as raw:
        raw.execute("UPDATE mt5_demo_receipts SET digest=?", ("f"*64,))
    with pytest.raises(EvidenceCustodyRefused, match="CONTENT_CORRUPTED"):
        verify(db, provider)


def test_other_date_window_is_not_implicitly_proven(prepared):
    db, provider, _, _ = prepared
    validator = MT5DemoIndependentReverifierV1(
        provider, expected(), custody_path=db,
    )
    with pytest.raises(EvidenceCustodyRefused, match="EXACT_WINDOW_NOT_FOUND"):
        validator.verify(START + timedelta(hours=1), END)


def test_more_positions_than_allowed_fails_without_partial_report(tmp_path):
    db = tmp_path / "custody.sqlite"
    provider = MockMT5()
    provider.orders.append(order(103, T2, pid=502))
    provider.deals.append(deal(203, T2, oid=103, pid=502, side=0, entry=0))
    provider.active.append(active(904, 502, side=0, volume=1.0))
    with DemoHistoryEvidenceCustodyV1(db) as custody:
        session = custody.open_read_session(provider, expected())
        custody.capture_and_append(
            provider, expected(), START, END, session=session,
            action_id="twopos", captured_at=END,
        )
    with pytest.raises(MT5ReverificationRefused, match="TARGETED_POSITION_LIMIT_EXCEEDED"):
        verify(db, provider, max_positions=1)


def test_duplicate_active_identifier_refused(prepared):
    db, provider, _, _ = prepared
    provider.active.append(active(999, 501))
    with pytest.raises(MT5ReverificationRefused, match="DUPLICATE_ACTIVE_POSITION_ID"):
        verify(db, provider)


def test_active_positions_incomplete_is_failure(prepared):
    db, provider, _, _ = prepared
    provider.active = None
    with pytest.raises(MT5ReverificationRefused, match="MT5_ACTIVE_POSITIONS_INCOMPLETE"):
        verify(db, provider)


def test_outside_window_prior_trade_never_proves_entire_lifespan(prepared):
    db, provider, _, _ = prepared
    before = T1 - 86400000
    provider.orders.append(order(109, before))
    provider.deals.append(deal(209, before, oid=109, volume=0.3))
    report = verify(db, provider)
    lineage = report["position_checks"][0]
    assert lineage["earlier_history_observed"]
    assert not lineage["entire_position_lifespan_proven"]


def test_unverified_unlinked_order_in_position_history_is_reported(prepared):
    db, provider, _, _ = prepared
    before = T1 - 86400000
    provider.deals.append(deal(209, before, oid=108, volume=0.2))
    report = verify(db, provider)
    assert "POSITION_DEAL_ORDER_NOT_IN_TARGETED_HISTORY" in (
        report["position_checks"][0]["issues"]
    )
    assert report["needs_review"]


def test_no_trades_in_window_but_active_exposure_is_not_clear(tmp_path):
    db = tmp_path / "custody.sqlite"
    provider = MockMT5()
    provider.orders = []
    provider.deals = []
    with DemoHistoryEvidenceCustodyV1(db) as custody:
        session = custody.open_read_session(provider, expected())
        custody.capture_and_append(
            provider, expected(), START, END, session=session,
            action_id="empty", captured_at=END,
        )
    report = verify(db, provider)
    assert report["targeted_positions_checked"] == 0
    assert report["unmatched_open_position_identifiers"] == [501]
    assert report["needs_review"]


def test_probe_success_clears_no_gate_and_closes_sdk(prepared):
    db, provider, _, _ = prepared
    args = argparse.Namespace(
        connect_existing_demo_terminal=True, account_id="demo-a",
        expected_login=1234567, expected_server="Fixture-Demo",
        custody_db=str(db), start_utc=START.isoformat(),
        end_utc=END.isoformat(),
    )
    report = run_once(args, provider)
    assert report["content_matches_stored_window"]
    assert not report["may_unlock_stage4"]
    assert provider.calls[-1] == "shutdown"
    assert "order_send" not in provider.calls


def test_probe_no_explicit_optin_does_not_initialize(prepared):
    db, provider, _, _ = prepared
    provider.calls.clear()
    args = argparse.Namespace(
        connect_existing_demo_terminal=False, account_id="demo-a",
        expected_login=1234567, expected_server="Fixture-Demo",
        custody_db=str(db), start_utc=START.isoformat(),
        end_utc=END.isoformat(),
    )
    with pytest.raises(MT5ReverificationRefused, match="OPT_IN_REQUIRED"):
        run_once(args, provider)
    assert provider.calls == []


def test_probe_real_account_refused_and_sdk_shutdown(prepared):
    db, provider, _, _ = prepared
    provider.account.trade_mode = 2
    args = argparse.Namespace(
        connect_existing_demo_terminal=True, account_id="demo-a",
        expected_login=1234567, expected_server="Fixture-Demo",
        custody_db=str(db), start_utc=START.isoformat(),
        end_utc=END.isoformat(),
    )
    with pytest.raises(ValueError, match="REAL_OR_UNKNOWN_ACCOUNT_FORBIDDEN"):
        run_once(args, provider)
    assert provider.calls[-1] == "shutdown"
