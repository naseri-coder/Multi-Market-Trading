"""Stage-11 causal offline candle replay, lifecycle, restart and safety tests."""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import timedelta
from decimal import Decimal as D

import pytest

from naseri_markets.brooks_stage11_candle_replay import (
    BrooksStage11CandleReplay,
    BrooksStage11Refused,
    stage11_panel_summary,
)
from naseri_markets.brooks_stage11_cli import run_once
from naseri_markets.execution_position_core_v1 import PaperExecutionOrchestratorV1
from test_brooks_stage10_paper_bridge import (
    ACCOUNT, SIGNAL, WHEN, configure_simulator, create_source, linker,
)

STEP = timedelta(minutes=15)


def bar(i, *, o="105", h="110", l="99", c="104", v="5"):
    start = WHEN + i*STEP
    return {
        "open_time": start.isoformat(),
        "close_time": (start + STEP).isoformat(),
        "open": o, "high": h, "low": l, "close": c, "volume": v,
    }


def payload(bars, *, symbol="PF_XBTUSD", provider="kraken_futures_trade_public",
            timeframe="15m"):
    return json.dumps({
        "schema_version": 1, "origin": "offline_paper_replay",
        "market": "crypto", "provider": provider, "symbol": symbol,
        "quote_currency": "USD", "exchange": "kraken_futures",
        "market_type": "futures", "timezone": "UTC", "timeframe": timeframe,
        "candles": bars,
    }, sort_keys=True).encode()


@pytest.fixture
def prepared(tmp_path):
    root = tmp_path / "state"
    create_source(root)
    configure_simulator(root)
    output = linker(root)
    assert output["order_status"] == "CREATED"
    return root, output["order_id"]


def run(root, bars, **opts):
    return BrooksStage11CandleReplay(root).replay(
        account_id=opts.pop("account_id", ACCOUNT),
        signal_id=opts.pop("signal_id", SIGNAL),
        candles_json=opts.pop("raw", payload(bars)),
        ack_offline_only=opts.pop("consent", True),
    )


def order(root, oid):
    with PaperExecutionOrchestratorV1(root / "brooks_stage10_paper.sqlite") as core:
        return core.order_state(oid), core.order_events(oid), core.risk_snapshot("paper-portfolio-1")


def test_target_after_entry_reports_net_pnl_realized_r_and_releases_risk(prepared):
    root, oid = prepared
    result = run(root, [bar(0), bar(1, o="110", h="125", l="101", c="122")])
    assert result["status"] == "CLOSED"
    assert result["exit_reason"] == "TARGET"
    assert result["entry_price"] == "100"
    assert result["exit_price"] == "120"
    assert D(result["gross_pnl"]) == D("20")
    assert D(result["estimated_fees"]) == D("0.24")
    assert D(result["estimated_slippage"]) == D("0.36")
    assert D(result["net_realized_pnl"]) == D("19.40")
    assert D(result["realized_r"]) == D("1.94")
    assert result["paper_risk_released"]
    assert result["all_execution_is_synthetic"]
    assert not result["broker_orders_authorized"]
    assert not result["telegram_signal_delivery_authorized"]
    assert not result["live_pnl_proven"]
    snapshot, events, risk = order(root, oid)
    assert snapshot["status"] == "CLOSED"
    assert [x["event"] for x in events] == [
        "CREATE", "SUBMIT", "ACK", "FILL", "CLOSE_FILL",
    ]
    assert D(risk["reserved_risk"]) == 0
    assert stage11_panel_summary(root)["closed_paper_trades"] == 1


def test_simultaneous_stop_and_target_same_bar_assumes_stop(prepared):
    root, _ = prepared
    report = run(root, [bar(0, o="105", h="125", l="89", c="110")])
    assert report["exit_reason"] == "ENTRY_AND_STOP_SAME_BAR"
    assert report["exit_price"] == "90"
    assert D(report["net_realized_pnl"]) == D("-10.5")
    assert D(report["realized_r"]) == D("-1.05")


def test_stop_and_target_same_later_bar_assumes_stop(prepared):
    root, _ = prepared
    report = run(root, [bar(0), bar(1, o="103", h="124", l="88", c="100")])
    assert report["exit_reason"] == "STOP_WORST_CASE"
    assert report["exit_price"] == "90"
    assert D(report["net_realized_pnl"]) < 0


def test_adverse_stop_open_gap_prices_at_worse_open(prepared):
    root, _ = prepared
    report = run(root, [bar(0), bar(1, o="85", h="98", l="80", c="89")])
    assert report["exit_reason"] == "STOP"
    assert report["exit_price"] == "85"
    assert D(report["net_realized_pnl"]) < -10


def test_favorable_target_gap_does_not_claim_better_than_limit(prepared):
    root, _ = prepared
    report = run(root, [bar(0), bar(1, o="127", h="130", l="122", c="125")])
    assert report["exit_reason"] == "TARGET"
    assert report["exit_price"] == "120"


def test_entry_bar_target_not_credited_without_next_closed_bar(prepared):
    root, oid = prepared
    report = run(root, [bar(0, o="105", h="125", l="99", c="121")])
    assert report["status"] == "FILLED"
    assert report["exit_reason"] is None
    assert report["net_realized_pnl"] == "0"
    assert report["realized_r"] is None
    assert not report["paper_risk_released"]
    _, events, risk = order(root, oid)
    assert [e["event"] for e in events] == ["CREATE", "SUBMIT", "ACK", "FILL"]
    assert D(risk["reserved_risk"]) > 0


def test_waiting_entry_does_not_invent_fills_or_costs(prepared):
    root, oid = prepared
    report = run(root, [bar(0, o="110", h="115", l="105", c="108")])
    assert report["status"] == "CREATED"
    assert report["entry_time_utc"] is None
    assert report["realized_r"] is None
    snapshot, events, risk = order(root, oid)
    assert len(events) == 1
    assert D(risk["reserved_risk"]) > 0
    assert snapshot["filled_quantity"] == "0"


def test_restart_appends_one_bar_and_identical_rerun_is_idempotent(prepared):
    root, oid = prepared
    first = run(root, [bar(0)])
    assert first["bars_committed"] == 1
    second = run(root, [bar(0), bar(1, o="110", h="125", l="101", c="122")])
    assert second["status"] == "CLOSED"
    assert second["bars_committed"] == 2
    third = run(root, [bar(0), bar(1, o="110", h="125", l="101", c="122")])
    assert third == second
    _, events, _ = order(root, oid)
    assert len(events) == 5


def test_previous_bar_price_mutation_refused_atomically(prepared):
    root, oid = prepared
    run(root, [bar(0)])
    with pytest.raises(BrooksStage11Refused, match="PREVIOUS_BAR_MUTATED"):
        run(root, [bar(0, c="103")])
    state, events, _ = order(root, oid)
    assert state["status"] == "FILLED"
    assert len(events) == 4


def test_history_rollback_refused(prepared):
    root, oid = prepared
    run(root, [bar(0), bar(1, o="103", h="110", l="101", c="108")])
    with pytest.raises(BrooksStage11Refused, match="HISTORY_ROLLBACK"):
        run(root, [bar(0)])
    assert order(root, oid)[0]["status"] == "FILLED"


def test_after_closed_trade_new_bars_refused_instead_of_reopened(prepared):
    root, oid = prepared
    run(root, [bar(0), bar(1, o="110", h="125", l="101", c="122")])
    with pytest.raises(BrooksStage11Refused, match="TERMINAL_FROZEN"):
        run(root, [
            bar(0), bar(1, o="110", h="125", l="101", c="122"),
            bar(2, o="120", h="128", l="118", c="122"),
        ])
    assert order(root, oid)[0]["status"] == "CLOSED"


def test_crash_on_close_rolls_back_all_stage3_actions_and_stage11_bars(
    prepared, monkeypatch,
):
    root, oid = prepared
    real = PaperExecutionOrchestratorV1.apply
    def broken(self, order_id, *, event, **kw):
        if event == "CLOSE_FILL":
            raise RuntimeError("SIMULATED_POWER_LOSS")
        return real(self, order_id, event=event, **kw)
    monkeypatch.setattr(PaperExecutionOrchestratorV1, "apply", broken)
    with pytest.raises(RuntimeError, match="SIMULATED_POWER_LOSS"):
        run(root, [bar(0, h="125", l="89")])
    state, events, risk = order(root, oid)
    assert state["status"] == "CREATED"
    assert len(events) == 1
    assert D(risk["reserved_risk"]) > 0
    with sqlite3.connect(root / "brooks_stage10_paper.sqlite") as con:
        rows = con.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type='table' AND name='brooks_stage11_positions'"
        ).fetchone()[0]
        assert rows == 0
    monkeypatch.undo()
    assert run(root, [bar(0, h="125", l="89")])["status"] == "CLOSED"


def test_entry_open_gap_below_stop_rejected_without_any_risk_release(prepared):
    root, oid = prepared
    with pytest.raises(BrooksStage11Refused, match="ENTRY_OPEN_GAP_BEYOND_STOP"):
        run(root, [bar(0, o="80", h="105", l="77", c="90")])
    assert order(root, oid)[0]["status"] == "CREATED"


@pytest.mark.parametrize("bad", [
    [bar(0), bar(1, o="110", h="111", l="109", c="108")],
    [bar(0, h="100", l="101")],
    [bar(0, v="-1")],
    [bar(0, c="NaN")],
    [bar(0, o="105", h="110", l="99", c="105", v="Infinity")],
    [bar(1)],
    [dict(bar(0), close_time="2026-10-01T02:00:00+00:00")],
])
def test_invalid_or_noncausal_candle_refused(prepared, bad):
    root, oid = prepared
    with pytest.raises(BrooksStage11Refused):
        run(root, bad)
    assert order(root, oid)[0]["status"] == "CREATED"


@pytest.mark.parametrize("kwargs", [
    {"symbol":"PF_ETHUSD"}, {"provider":"injected"},
    {"timeframe":"1h"},
])
def test_wrong_market_pair_provider_or_timeframe_refused(prepared, kwargs):
    root, oid = prepared
    with pytest.raises(BrooksStage11Refused, match="INSTRUMENT_TIMEFRAME_DRIFT"):
        run(root, [], raw=payload([bar(0)], **kwargs))
    assert order(root, oid)[0]["status"] == "CREATED"


def test_without_operator_consent_or_link_never_executes(prepared):
    root, oid = prepared
    with pytest.raises(BrooksStage11Refused, match="OPTIN_REQUIRED"):
        run(root, [bar(0)], consent=False)
    with pytest.raises(BrooksStage11Refused, match="STAGE10_VERIFIED_LINK_REQUIRED"):
        run(root, [bar(0)], account_id="unknown")
    assert order(root, oid)[0]["status"] == "CREATED"


def test_no_broker_action_or_stage10_link_does_not_create_schema(tmp_path):
    root = tmp_path / "absent"
    assert stage11_panel_summary(root)["status"] == "NOT_CONFIGURED"
    assert not root.exists()
    with pytest.raises(BrooksStage11Refused, match="LEDGER_NOT_CONFIGURED"):
        run(root, [bar(0)])


def test_outside_stage11_event_mutation_detected(prepared):
    root, oid = prepared
    run(root, [bar(0)])
    with PaperExecutionOrchestratorV1(root / "brooks_stage10_paper.sqlite") as core:
        core.apply(oid, action_id="other-stop", event="AMEND_STOP", stop="95")
    with pytest.raises(BrooksStage11Refused, match="ORDER_STATE_DRIFT"):
        run(root, [bar(0), bar(1, o="104", h="125", l="97", c="120")])


def test_stage11_panel_summary_keeps_open_and_closed_separate(prepared):
    root, oid = prepared
    assert stage11_panel_summary(root)["status"] == "NOT_CONFIGURED"
    run(root, [bar(0)])
    mid = stage11_panel_summary(root)
    assert mid["replayed_orders"] == 1
    assert mid["closed_paper_trades"] == 0
    assert D(mid["aggregate_net_pnl"]) == 0
    run(root, [bar(0), bar(1, o="103", h="125", l="101", c="120")])
    final = stage11_panel_summary(root)
    assert final["closed_paper_trades"] == 1
    assert D(final["aggregate_net_pnl"]) > 0


def test_no_untrusted_external_file_without_two_operator_gates(prepared, tmp_path):
    root, _ = prepared
    fixture = tmp_path / "offline.json"
    fixture.write_bytes(payload([bar(0)]))
    args = argparse.Namespace(
        status=False, ack_offline_paper_only=True, state_dir=root,
        account_id=ACCOUNT, signal_id=SIGNAL, candles_file=fixture,
    )
    with pytest.raises(BrooksStage11Refused, match="EXPLICIT_NONPRODUCTION"):
        run_once(args, environment={})
    with pytest.raises(BrooksStage11Refused, match="EXPLICIT_NONPRODUCTION"):
        run_once(args, environment={"MMT_NONPRODUCTION":"1","MMT_PRODUCTION":"1"})
    args.ack_offline_paper_only = False
    with pytest.raises(BrooksStage11Refused, match="EXPLICIT_NONPRODUCTION"):
        run_once(args, environment={"MMT_NONPRODUCTION":"1"})
    args.ack_offline_paper_only = True
    assert run_once(args, environment={"MMT_NONPRODUCTION":"1"})["bars_committed"] == 1
    args.status = True
    assert run_once(args, environment={})["replayed_orders"] == 1


def test_file_symlink_denied(prepared, tmp_path):
    root, _ = prepared
    f = tmp_path / "candle.json"
    f.write_bytes(payload([bar(0)]))
    alias = tmp_path / "alias.json"
    alias.symlink_to(f)
    args = argparse.Namespace(
        status=False, ack_offline_paper_only=True, state_dir=root,
        account_id=ACCOUNT, signal_id=SIGNAL, candles_file=alias,
    )
    with pytest.raises(BrooksStage11Refused, match="FILE_INVALID"):
        run_once(args, environment={"MMT_NONPRODUCTION":"1"})


def test_short_entry_and_target_use_inverse_stop_geometry(tmp_path):
    """Short setup must not accidentally apply long OHLC hit semantics."""
    import hashlib
    from naseri_markets.contracts import Direction, EvidenceMode, SignalIntent
    from naseri_markets.brooks_paper_receipts import make_receipt
    from naseri_markets.delivery_ledger import _wire_intent
    from naseri_markets.engine_control_store import BROOKS_ENGINE_ID, EngineControlStore
    from test_brooks_stage10_paper_bridge import (
        SCAN, SNAPSHOT, SOURCE, VERSION, instrument,
    )

    root = tmp_path / "short-dev"
    create_source(root)
    short = SignalIntent(
        signal_id=SIGNAL, engine_id=BROOKS_ENGINE_ID,
        engine_version=VERSION, instrument=instrument(),
        direction=Direction.SHORT, observed_at=WHEN,
        entry=D("100"), stop=D("110"),
        targets=(D("80"), D("70")), evidence_mode=EvidenceMode.PAPER,
    )
    canonical = _wire_intent(short)
    receipt = make_receipt(
        scan_id=SCAN, raw={
            "exchange": "kraken_futures", "provider": "kraken_futures_trade_public",
            "symbol": "PF_XBTUSD", "quote_currency": "USD", "timeframe": "15m",
            "market_type": "futures",
            "candles": [{"close_time": WHEN.isoformat()}],
        },
        snapshot_hash=SNAPSHOT, source_digest=SOURCE,
        decision="SHORT", signal=short, outcome="RECORDED",
    )
    receipt_wire = json.dumps(receipt, sort_keys=True, separators=(",", ":"))
    with EngineControlStore(root) as store:
        store._db.execute(
            "UPDATE a7_paper_intents SET payload=?,digest=? "
            "WHERE signal_id=?", (
                canonical, hashlib.sha256(canonical.encode()).hexdigest(), SIGNAL,
            ),
        )
        store._db.execute(
            "UPDATE brooks_replay_scans SET decision='SHORT' WHERE scan_id=?",
            (SCAN,),
        )
        store._db.execute(
            "UPDATE brooks_paper_receipts "
            "SET receipt_json=?,receipt_sha256=? WHERE scan_id=?", (
                receipt_wire, hashlib.sha256(receipt_wire.encode()).hexdigest(), SCAN,
            ),
        )
    configure_simulator(root)
    assert linker(root)["order_status"] == "CREATED"
    result = run(root, [
        bar(0, o="95", h="101", l="90", c="97"),
        bar(1, o="90", h="95", l="75", c="82"),
    ])
    assert result["status"] == "CLOSED"
    assert result["exit_reason"] == "TARGET"
    assert D(result["gross_pnl"]) == D("20")
    assert D(result["net_realized_pnl"]) == D("19.5")
    assert D(result["realized_r"]) == D("1.95")
    assert stage11_panel_summary(root)["net_pnl_by_currency"] == {"USD":"19.500"}


def test_panel_never_sums_unrelated_currencies(prepared):
    root, oid = prepared
    run(root, [bar(0), bar(1, o="110", h="125", l="101", c="122")])
    with sqlite3.connect(root / "brooks_stage10_paper.sqlite") as db:
        db.execute(
            "INSERT INTO brooks_stage11_positions "
            "(order_id,metadata_json,state_sha256) VALUES (?,?,?)",
            ("fixture-eur-separate", json.dumps({
                "quote_currency": "EUR", "net_realized_pnl": "7",
                "risk_released": True,
            }), "0" * 64),
        )
    summary = stage11_panel_summary(root)
    assert summary["closed_paper_trades"] == 2
    assert summary["aggregate_net_pnl"] == "MULTI_CURRENCY_NOT_ADDITIVE"
    assert D(summary["net_pnl_by_currency"]["USD"]) == D("19.4")
    assert D(summary["net_pnl_by_currency"]["EUR"]) == D("7")
