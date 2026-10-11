"""Stage-7 DEMO evidence custody, restart integrity and hedging/netting safety."""
from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from types import SimpleNamespace as NS

import pytest

from naseri_markets.mt5_demo_custody_probe import run_once
from naseri_markets.mt5_demo_evidence_custody_v1 import (
    DemoHistoryEvidenceCustodyV1,
    EvidenceCustodyRefused,
)
from naseri_markets.mt5_demo_history_readonly_v1 import (
    MT5DemoHistoryReaderV1,
    MT5HistoricalDeal,
)
from naseri_markets.mt5_demo_position_accounting_v1 import (
    AccountingRefused,
    diagnose_position_history,
)
from naseri_markets.mt5_demo_readonly_adapter_v1 import DemoAccountExpectation

START = datetime(2026, 10, 1, tzinfo=UTC)
MID = START + timedelta(days=1)
END = START + timedelta(days=2)
T1 = int((START + timedelta(hours=4)).timestamp() * 1000)
T2 = int((MID + timedelta(hours=4)).timestamp() * 1000)


def order(ticket: int, at: int, position: int = 501, symbol: str = "EURUSD") -> NS:
    return NS(
        ticket=ticket, position_id=position, symbol=symbol,
        type=0, state=4, time_setup_msc=at - 100,
        time_done_msc=at, volume_initial=1.0, volume_current=0.0,
        price_open=100.0,
    )


def deal(
    ticket: int, at: int, *, order_ticket: int = 101,
    position: int = 501, symbol: str = "EURUSD", kind: int = 0,
    entry: int = 0, qty: float = 1.0, price: float = 100.0,
) -> NS:
    return NS(
        ticket=ticket, order=order_ticket, position_id=position,
        symbol=symbol, type=kind, entry=entry, time_msc=at,
        volume=qty, price=price, profit=-1.0 if entry else 0.0,
        commission=-0.1, fee=-0.02, swap=0.0,
    )


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_MARGIN_MODE_RETAIL_NETTING = 0
    ACCOUNT_MARGIN_MODE_EXCHANGE = 1
    ACCOUNT_MARGIN_MODE_RETAIL_HEDGING = 2

    def __init__(self, margin_mode: int = 2):
        self.account = NS(
            trade_mode=0, margin_mode=margin_mode,
            login=1234567, server="Fixture-Demo",
        )
        self.terminal = NS(connected=True)
        self.orders = [order(101, T1), order(102, T2)]
        self.deals = [
            deal(201, T1),
            deal(202, T2, order_ticket=102, kind=1,
                 entry=1, qty=0.4, price=110),
        ]
        self.calls = []
        self.reads = 0
        self.switch_after = 0
        self.mode_switch_after = 0

    def account_info(self):
        self.calls.append("account_info")
        self.reads += 1
        data = vars(self.account).copy()
        if self.switch_after and self.reads >= self.switch_after:
            data["login"] = 7654321
        if self.mode_switch_after and self.reads >= self.mode_switch_after:
            data["margin_mode"] = 0 if data["margin_mode"] == 2 else 2
        return NS(**data)

    def terminal_info(self):
        self.calls.append("terminal_info")
        return self.terminal

    def _find(self, data, start, end, field):
        a = int(start.timestamp() * 1000)
        b = int(end.timestamp() * 1000)
        return tuple(x for x in data if a <= getattr(x, field) <= b)

    def history_orders_get(self, start, end):
        self.calls.append("history_orders_get")
        return self._find(self.orders, start, end, "time_done_msc")

    def history_deals_get(self, start, end):
        self.calls.append("history_deals_get")
        return self._find(self.deals, start, end, "time_msc")

    def history_orders_total(self, start, end):
        return len(self._find(self.orders, start, end, "time_done_msc"))

    def history_deals_total(self, start, end):
        return len(self._find(self.deals, start, end, "time_msc"))


def expected(account_id="demo-a", login=1234567, server="Fixture-Demo"):
    return DemoAccountExpectation(account_id=account_id, login=login, server=server)


def history(provider, start=START, end=MID):
    return MT5DemoHistoryReaderV1(provider, expected()).capture(
        start, end, captured_at=end,
    )


def parsed(raw: NS) -> MT5HistoricalDeal:
    return MT5HistoricalDeal.parse(raw)


@pytest.fixture
def env(tmp_path):
    with DemoHistoryEvidenceCustodyV1(tmp_path / "custody.sqlite") as custody:
        provider = FakeMT5()
        session = custody.open_read_session(provider, expected())
        yield custody, provider, session


def append(custody, provider, session, start=START, end=MID, action="ingest-a"):
    return custody.capture_and_append(
        provider, expected(), start, end, session=session, action_id=action,
        captured_at=end,
    )


def test_new_account_pinned_demo_hedging_and_empty_chain(env):
    custody, provider, session = env
    assert session and len(session) == 32
    report = custody.verify("demo-a")
    assert report["account_mode"] == "HEDGING"
    assert report["windows"] == 0
    assert report["ticket_count"] == 0
    assert report["locally_integrity_checked"]
    assert not report["broker_authenticated"]
    assert not report["may_unlock_recovery"]
    assert "order_send" not in provider.calls


def test_first_window_atomic_append_and_verified_ticket_index(env):
    custody, provider, session = env
    receipt = append(custody, provider, session)
    assert receipt["mode"] == "MT5_DEMO_HISTORY_EVIDENCE_ONLY"
    assert not receipt["replayed"]
    assert not receipt["may_send_order"]
    assert not receipt["may_release_risk"]
    report = custody.verify("demo-a")
    assert report["windows"] == 1
    assert report["ticket_count"] == 2
    assert report["last_end"] == MID.isoformat()


def test_contiguous_window_with_overlap_and_restart_replay(env, tmp_path):
    custody, provider, session = env
    append(custody, provider, session)
    next_receipt = append(
        custody, provider, session, START + timedelta(hours=3),
        END, action="ingest-b",
    )
    assert next_receipt["chain_hash"] != next_receipt["content_digest"]
    assert custody.verify("demo-a")["ticket_count"] == 4
    first = custody.accounting("demo-a")
    assert first["positions"][0]["signed_lots_window_only"] == "0.6"
    assert first["positions"][0]["entry_lots_window_only"] == "1.0"
    assert first["positions"][0]["exit_lots_window_only"] == "0.4"
    path = tmp_path / "custody.sqlite"
    # Independent reopened connection validates all persisted receipts.
    with DemoHistoryEvidenceCustodyV1(path) as reopened:
        assert reopened.verify("demo-a")["windows"] == 2
        assert reopened.accounting("demo-a")["positions"] == first["positions"]
        with pytest.raises(EvidenceCustodyRefused, match="FRESH_READ_SESSION_REQUIRED"):
            reopened.capture_and_append(
                provider, expected(), MID, END, session=session,
                action_id="stale-token",
            )
        fresh = reopened.open_read_session(provider, expected())
        assert fresh != session


def test_idempotent_same_key_and_content_does_not_create_new_receipt(env):
    custody, provider, session = env
    original = append(custody, provider, session)
    duplicate = append(custody, provider, session)
    assert duplicate["replayed"]
    assert duplicate["chain_hash"] == original["chain_hash"]
    assert custody.verify("demo-a")["windows"] == 1


def test_changed_action_payload_with_same_key_refused(env):
    custody, provider, session = env
    append(custody, provider, session)
    with pytest.raises(EvidenceCustodyRefused, match="ACTION_KEY_CONFLICT"):
        append(custody, provider, session, MID, END, action="ingest-a")
    assert custody.verify("demo-a")["windows"] == 1


def test_duplicate_window_new_id_is_fail_closed(env):
    custody, provider, session = env
    append(custody, provider, session)
    with pytest.raises(EvidenceCustodyRefused, match="WINDOW_ALREADY_RECORDED"):
        append(custody, provider, session, action="ingest-other")


@pytest.mark.parametrize("start,end", [
    (START, START + timedelta(hours=1)),
    (MID + timedelta(hours=1), END),
])
def test_older_or_gapped_window_fails_without_creating_receipt(env, start, end):
    custody, provider, session = env
    append(custody, provider, session)
    with pytest.raises(EvidenceCustodyRefused, match="GAP_OR_ROLLBACK"):
        append(custody, provider, session, start, end, action="roll-or-gap")
    assert custody.verify("demo-a")["windows"] == 1


def test_mutated_old_ticket_on_overlap_is_quarantined_by_refusal(env):
    custody, provider, session = env
    append(custody, provider, session)
    provider.deals[0].price = 999
    with pytest.raises(EvidenceCustodyRefused, match="TICKET_CONTENT_CONFLICT"):
        append(
            custody, provider, session, START + timedelta(hours=3),
            END, action="drift",
        )
    assert custody.verify("demo-a")["ticket_count"] == 2


def test_db_tampering_with_ticket_detected_by_full_verify(env, tmp_path):
    custody, provider, session = env
    append(custody, provider, session)
    with sqlite3.connect(tmp_path / "custody.sqlite") as db:
        db.execute(
            "UPDATE mt5_demo_tickets SET payload=? WHERE ticket=201",
            (json.dumps({"forged": True}),),
        )
    with pytest.raises(EvidenceCustodyRefused, match="TICKET_INDEX_CORRUPTED"):
        custody.verify("demo-a")
    with pytest.raises(EvidenceCustodyRefused, match="TICKET_INDEX_CORRUPTED"):
        custody.open_read_session(provider, expected())


def test_db_tampering_with_receipt_digest_detected(env, tmp_path):
    custody, provider, session = env
    append(custody, provider, session)
    with sqlite3.connect(tmp_path / "custody.sqlite") as db:
        db.execute("UPDATE mt5_demo_receipts SET digest=?", ("f" * 64,))
    with pytest.raises(EvidenceCustodyRefused, match="RECEIPT_CONTENT_CORRUPTED"):
        custody.verify("demo-a")


def test_db_rollback_head_tamper_detected(env, tmp_path):
    custody, provider, session = env
    append(custody, provider, session)
    with sqlite3.connect(tmp_path / "custody.sqlite") as db:
        db.execute("UPDATE mt5_demo_accounts SET receipt_count=0")
    with pytest.raises(EvidenceCustodyRefused, match="HEAD_OR_COUNT_CORRUPTED"):
        custody.verify("demo-a")


def test_mid_transaction_crash_rolls_back_all_tickets_and_receipt(env, monkeypatch):
    custody, provider, session = env

    def simulate_crash():
        raise RuntimeError("POWER_LOSS_AT_TICKET_STAGE")

    monkeypatch.setattr(custody, "_after_tickets_before_receipt", simulate_crash)
    with pytest.raises(RuntimeError, match="POWER_LOSS"):
        append(custody, provider, session)
    assert custody.verify("demo-a")["ticket_count"] == 0
    assert custody.verify("demo-a")["windows"] == 0
    monkeypatch.undo()
    assert append(custody, provider, session)["content_digest"]


def test_account_login_server_or_margin_mode_drift_refused(env):
    custody, provider, _session = env
    with pytest.raises(ValueError, match="LOGIN_MISMATCH"):
        custody.open_read_session(provider, expected(login=7654321))
    with pytest.raises(ValueError, match="SERVER_MISMATCH"):
        custody.open_read_session(provider, expected(server="Other-Demo"))
    provider.account.margin_mode = 0
    with pytest.raises(EvidenceCustodyRefused, match="IDENTITY_OR_MODE_DRIFT"):
        custody.open_read_session(provider, expected())


def test_real_account_and_unsupported_exchange_refused_before_history_capture(
    tmp_path,
):
    with DemoHistoryEvidenceCustodyV1(tmp_path / "custody.sqlite") as custody:
        provider = FakeMT5()
        provider.account.trade_mode = 2
        with pytest.raises(ValueError, match="REAL_OR_UNKNOWN_ACCOUNT_FORBIDDEN"):
            custody.open_read_session(provider, expected())
        assert "history_orders_get" not in provider.calls
        provider.account.trade_mode = 0
        provider.account.margin_mode = provider.ACCOUNT_MARGIN_MODE_EXCHANGE
        with pytest.raises(EvidenceCustodyRefused, match="UNSUPPORTED_ACCOUNT_MARGIN_MODE"):
            custody.open_read_session(provider, expected())


def test_account_switch_during_capture_refused_and_no_receipt(env):
    custody, provider, session = env
    provider.switch_after = provider.reads + 3
    with pytest.raises(ValueError, match="LOGIN_MISMATCH"):
        append(custody, provider, session)
    assert custody.verify("demo-a")["windows"] == 0


def test_account_margin_mode_switch_during_capture_refused_and_no_receipt(env):
    custody, provider, session = env
    provider.mode_switch_after = provider.reads + 3
    with pytest.raises(EvidenceCustodyRefused, match="ACCOUNT_MARGIN_MODE_SWITCHED"):
        append(custody, provider, session)
    assert custody.verify("demo-a")["windows"] == 0


def test_one_account_cannot_relabel_another_accounts_evidence(tmp_path):
    p = tmp_path / "custody.sqlite"
    with DemoHistoryEvidenceCustodyV1(p) as custody:
        provider = FakeMT5()
        session = custody.open_read_session(provider, expected())
        append(custody, provider, session)
        with pytest.raises(ValueError, match="LOGIN_MISMATCH"):
            custody.open_read_session(provider, expected("other-a", 222222))
        assert custody.verify("demo-a")["windows"] == 1


def test_account_session_is_not_execution_or_stage4_unlock(env):
    custody, provider, session = env
    receipt = append(custody, provider, session)
    summary = custody.accounting("demo-a")
    assert not receipt["may_send_order"]
    assert not summary["may_send_order"]
    assert not summary["may_mutate_paper_risk"]
    assert not summary["may_unlock_recovery"]


def test_hedging_multiple_opposite_positions_same_symbol_are_separate():
    deals = (
        parsed(deal(201, T1, position=501, kind=0, entry=0, qty=1)),
        parsed(deal(202, T2, position=502, kind=1, entry=0, qty=2)),
    )
    out = diagnose_position_history(deals, margin_mode="HEDGING")
    assert len(out["positions"]) == 2
    assert [p["signed_lots_window_only"] for p in out["positions"]] == ["1.0", "-2.0"]
    assert out["issues"] == []


def test_netting_same_symbol_combines_partial_close_and_reversal():
    deals = (
        parsed(deal(201, T1, position=501, kind=0, entry=0, qty=1)),
        parsed(deal(202, T2, position=501, kind=1, entry=2, qty=1.6)),
        parsed(deal(203, T2 + 20, position=501, kind=0, entry=1, qty=0.2)),
    )
    out = diagnose_position_history(deals, margin_mode="NETTING")
    p = out["positions"][0]
    assert p["signed_lots_window_only"] == "-0.4"
    assert D(p["entry_lots_window_only"]) == D("1.6")
    assert D(p["exit_lots_window_only"]) == D("1.2")
    assert p["reversal_count"] == 1
    assert out["issues"] == []
    assert not out["all_time_position_reconstruction_proven"]


def test_hedging_out_by_is_not_assumed_closed():
    deals = (
        parsed(deal(201, T1, kind=0, entry=0)),
        parsed(deal(202, T2, kind=1, entry=3)),
    )
    out = diagnose_position_history(deals, margin_mode="HEDGING")
    assert out["positions"][0]["signed_lots_window_only"] == "1.0"
    assert out["issues"][0]["code"] == "CLOSE_BY_COUNTERPART_EVIDENCE_REQUIRED"


def test_hedging_inout_is_unsupported():
    deals = (
        parsed(deal(201, T1, kind=0, entry=0)),
        parsed(deal(202, T2, kind=1, entry=2, qty=2)),
    )
    out = diagnose_position_history(deals, margin_mode="HEDGING")
    assert out["issues"][0]["code"] == "HEDGING_INOUT_UNSUPPORTED"


def test_netting_detects_missing_prior_entry():
    out = diagnose_position_history(
        (parsed(deal(203, T2, kind=1, entry=1, qty=0.4)),),
        margin_mode="NETTING",
    )
    assert out["issues"][0]["code"] == "OUT_WITHOUT_PRIOR_IN_WINDOW_ENTRY"
    assert out["positions"][0]["signed_lots_window_only"] == "0"


def test_netting_detects_position_identity_drift_with_active_exposure():
    deals = (
        parsed(deal(201, T1, kind=0, entry=0, position=501)),
        parsed(deal(202, T2, kind=1, entry=1, position=502, qty=0.5)),
    )
    out = diagnose_position_history(deals, margin_mode="NETTING")
    assert "NETTING_POSITION_ID_CHANGED_WITH_OPEN_EXPOSURE" in {
        item["code"] for item in out["issues"]
    }


def test_nontrade_balance_deals_do_not_create_positions():
    record = parsed(deal(
        303, T1, order_ticket=0, position=0, symbol="",
        kind=2, entry=0, qty=0, price=0,
    ))
    out = diagnose_position_history((record,), margin_mode="NETTING")
    assert out["positions"] == []
    assert out["nontrade_cash_window_only"] == "-0.12"


def test_reject_unsupported_margin_mode_and_duplicate_deal_identity():
    row = parsed(deal(201, T1))
    with pytest.raises(AccountingRefused, match="MODE_NOT_SUPPORTED"):
        diagnose_position_history((row,), margin_mode="EXCHANGE")
    with pytest.raises(AccountingRefused, match="DUPLICATE_TRADE_DEAL_TICKET"):
        diagnose_position_history((row, row), margin_mode="HEDGING")


def test_new_instance_recovers_netting_mode_and_accounting(tmp_path):
    path = tmp_path / "custody.sqlite"
    with DemoHistoryEvidenceCustodyV1(path) as custody:
        broker = FakeMT5(margin_mode=0)
        token = custody.open_read_session(broker, expected())
        append(custody, broker, token)
        first = custody.accounting("demo-a")
        assert first["margin_mode"] == "NETTING"
    with DemoHistoryEvidenceCustodyV1(path) as resumed:
        assert resumed.accounting("demo-a")["positions"] == first["positions"]
        new_broker = FakeMT5(margin_mode=0)
        new_token = resumed.open_read_session(new_broker, expected())
        assert new_token != token
        assert resumed.verify("demo-a")["windows"] == 1


def test_reject_nonregular_custody_file(tmp_path):
    folder = tmp_path / "folder"
    folder.mkdir()
    with pytest.raises(EvidenceCustodyRefused, match="NONREGULAR_CUSTODY_PATH"):
        DemoHistoryEvidenceCustodyV1(folder)
    link = tmp_path / "link"
    link.symlink_to(folder)
    with pytest.raises(EvidenceCustodyRefused, match="NONREGULAR_CUSTODY_PATH"):
        DemoHistoryEvidenceCustodyV1(link)


def test_one_shot_operator_cli_captures_then_shuts_sdk(tmp_path):
    from argparse import Namespace

    class InitializedFake(FakeMT5):
        def initialize(self):
            self.calls.append("initialize")
            return True

        def shutdown(self):
            self.calls.append("shutdown")

    provider = InitializedFake()
    args = Namespace(
        connect_existing_demo_terminal=True,
        account_id="demo-a", expected_login=1234567,
        expected_server="Fixture-Demo",
        start_utc=START.isoformat(), end_utc=MID.isoformat(),
        custody_db=str(tmp_path / "cli-custody.sqlite"),
        action_id="capture-cli-1",
    )
    report = run_once(args, provider)
    assert report["receipt"]["content_digest"]
    assert report["local_integrity"]["windows"] == 1
    assert not report["may_send_order"]
    assert not report["may_unlock_stage4"]
    assert provider.calls[0] == "initialize"
    assert provider.calls[-1] == "shutdown"
    assert "order_send" not in provider.calls


def test_one_shot_cli_denies_non_demo_and_still_shutdown(tmp_path):
    from argparse import Namespace

    class InitializedFake(FakeMT5):
        def initialize(self):
            self.calls.append("initialize")
            return True

        def shutdown(self):
            self.calls.append("shutdown")

    provider = InitializedFake()
    provider.account.trade_mode = 2
    args = Namespace(
        connect_existing_demo_terminal=True,
        account_id="demo-a", expected_login=1234567,
        expected_server="Fixture-Demo", start_utc=START.isoformat(),
        end_utc=MID.isoformat(),
        custody_db=str(tmp_path / "custody.sqlite"),
        action_id="capture-cli-real",
    )
    with pytest.raises(ValueError, match="REAL_OR_UNKNOWN_ACCOUNT_FORBIDDEN"):
        run_once(args, provider)
    assert provider.calls[-1] == "shutdown"
    with DemoHistoryEvidenceCustodyV1(tmp_path / "custody.sqlite") as store:
        with pytest.raises(EvidenceCustodyRefused, match="NOT_ENROLLED"):
            store.verify("demo-a")


def test_cli_requires_opt_in_before_initializer(tmp_path):
    from argparse import Namespace

    provider = FakeMT5()
    args = Namespace(
        connect_existing_demo_terminal=False,
        account_id="demo-a", expected_login=1234567,
        expected_server="Fixture-Demo", start_utc=START.isoformat(),
        end_utc=MID.isoformat(), custody_db=str(tmp_path / "custody.sqlite"),
        action_id="reject",
    )
    with pytest.raises(EvidenceCustodyRefused, match="OPT_IN_REQUIRED"):
        run_once(args, provider)
    assert provider.calls == []
