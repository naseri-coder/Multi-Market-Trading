"""Stage 12 read-only research audit on actual Stage10/11 offline fixtures."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from decimal import Decimal

import pytest

from naseri_markets.brooks_stage12_cli import run_once
from naseri_markets.brooks_stage12_research_audit import (
    Stage12ResearchRefused, evaluate_brooks_stage12,
)
from test_brooks_stage10_paper_bridge import (
    ACCOUNT, SIGNAL, configure_simulator, create_source, linker,
)
from test_brooks_stage11_candle_replay import bar, payload
from naseri_markets.brooks_stage11_candle_replay import BrooksStage11CandleReplay


def manifest(*, signals=None, symbol="PF_XBTUSD",
             training="2026-09-15T00:00:00+00:00",
             validation="2026-09-30T00:00:00+00:00",
             end="2026-10-10T00:00:00+00:00", origin="synthetic_fixture"):
    return {
        "schema_version": 1,
        "purpose": "offline_paper_cohort_diagnostic",
        "study_id": "brooks-stage12-offline-fixture",
        "account_id": ACCOUNT,
        "provider": "kraken_futures_trade_public",
        "symbol": symbol,
        "timeframe": "15m",
        "quote_currency": "USD",
        "window_start_utc": "2026-09-01T00:00:00+00:00",
        "training_end_utc": training,
        "validation_end_utc": validation,
        "window_end_utc": end,
        "expected_signal_ids": [SIGNAL] if signals is None else signals,
        "dataset_origin": origin,
        "dataset_sha256": "0" * 64,
        "protocol_frozen_before_outcomes": True,
    }


def encoded(**changes):
    study = manifest()
    study.update(changes)
    return json.dumps(study, sort_keys=True).encode()


@pytest.fixture
def local(tmp_path):
    root = tmp_path/"private"
    create_source(root)
    configure_simulator(root)
    order = linker(root)
    return root, order["order_id"]


def finish(root, bars=None):
    if bars is None:
        bars = [bar(0), bar(1, o="110", h="125", l="101", c="122")]
    return BrooksStage11CandleReplay(root).replay(
        account_id=ACCOUNT, signal_id=SIGNAL,
        candles_json=payload(bars), ack_offline_only=True,
    )


def evaluate(root, **changed):
    return evaluate_brooks_stage12(root, encoded(**changed))


def test_one_closed_sample_remains_insufficient_and_is_never_authority(local):
    root, _ = local
    finish(root)
    result = evaluate(root)
    assert result["status"] == "INSUFFICIENT_CLOSED_PAPER_SAMPLES"
    assert result["overall"]["linked_signals"] == 1
    assert result["overall"]["closed_paper_trades"] == 1
    assert result["overall"]["not_closed_or_not_replayed"] == 0
    assert result["partitions"]["training"]["closed_paper_trades"] == 0
    assert result["partitions"]["validation"]["closed_paper_trades"] == 0
    assert result["partitions"]["holdout"]["closed_paper_trades"] == 1
    assert Decimal(result["overall"]["mean_net_realized_r"]) == Decimal("1.94")
    assert Decimal(result["overall"]["median_net_realized_r"]) == Decimal("1.94")
    assert Decimal(result["overall"]["sum_net_pnl"]) == Decimal("19.4")
    assert Decimal(result["overall"]["sum_modeled_costs"]) == Decimal("0.60")
    assert Decimal(result["overall"]["stress_2x_cost_mean_r"]) == Decimal("1.88")
    assert result["overall"]["win_rate"] == "1"
    assert result["actual_provider_dataset_verified"] is False
    assert result["pre_registration_independently_verified"] is False
    assert result["observed_full_signal_universe"] is False
    assert result["account_link_universe_complete"] is True
    assert result["profitability_or_live_edge_proven"] is False
    assert result["may_execute_broker_order"] is False
    assert result["may_publish_signal"] is False
    assert result["may_activate_core"] is False
    assert result["manifest_sha256"] == hashlib.sha256(encoded()).hexdigest()


def test_no_replay_is_incomplete_not_automatically_classed_as_loss(local):
    root, _ = local
    result = evaluate(root)
    assert result["status"] == "INCOMPLETE_PAPER_OUTCOMES"
    assert result["overall"]["closed_paper_trades"] == 0
    assert result["overall"]["not_closed_or_not_replayed"] == 1
    assert result["overall"]["mean_net_realized_r"] is None
    assert result["overall"]["profit_factor"] is None


def test_open_paper_position_remains_in_denominator(local):
    root, _ = local
    finish(root, [bar(0)])
    result = evaluate(root)
    assert result["status"] == "INCOMPLETE_PAPER_OUTCOMES"
    assert result["overall"]["linked_signals"] == 1
    assert result["overall"]["not_closed_or_not_replayed"] == 1
    assert result["overall"]["sum_net_pnl"] == "0"


def test_stop_loss_stress_does_not_turn_negative_to_positive(local):
    root, _ = local
    finish(root, [bar(0, o="105", h="125", l="89", c="110")])
    result = evaluate(root)
    assert Decimal(result["overall"]["mean_net_realized_r"]) < 0
    assert Decimal(result["overall"]["stress_2x_cost_mean_r"]) < Decimal(
        result["overall"]["mean_net_realized_r"]
    )
    assert result["overall"]["winners"] == 0


@pytest.mark.parametrize("changes,reason", [
    ({"expected_signal_ids": ["unrelated"]}, "INCOMPLETE_ACCOUNT_SIGNAL_UNIVERSE"),
    ({"expected_signal_ids": []}, "SIGNAL_LIST_INVALID"),
    ({"expected_signal_ids": [SIGNAL, SIGNAL]}, "SIGNAL_LIST_INVALID"),
    ({"symbol": "PF_ETHUSD"}, "HETEROGENEOUS_ACCOUNT_INSTRUMENT"),
    ({"timeframe": "1h"}, "SOURCE_RECEIPT_CONFLICT"),
    ({"training_end_utc": "2026-10-05T00:00:00+00:00"}, "OVERLAPPING_OR_REVERSED"),
    ({"protocol_frozen_before_outcomes": False}, "PRE_REGISTRATION"),
    ({"dataset_origin": "verified_real_market"}, "UNVERIFIED_DATASET"),
    ({"window_end_utc": "2026-10-01T01:00:00+00:00"}, "SIGNAL_OUTSIDE"),
])
def test_rejects_cherry_picking_and_inconsistent_research_scope(local, changes, reason):
    root, _ = local
    finish(root)
    with pytest.raises(Stage12ResearchRefused, match=reason):
        evaluate_brooks_stage12(root, encoded(**changes))


def test_corrupt_stage11_hash_refuses_whole_study(local):
    root, oid = local
    finish(root)
    with sqlite3.connect(root/"brooks_stage10_paper.sqlite") as conn:
        conn.execute(
            "UPDATE brooks_stage11_positions SET state_sha256=? WHERE order_id=?",
            ("0"*64, oid),
        )
    with pytest.raises(Stage12ResearchRefused, match="ORDER_DIGEST_MISMATCH"):
        evaluate(root)


def test_corrupt_cost_accounting_cannot_improve_study(local):
    root, oid = local
    finish(root)
    with sqlite3.connect(root/"brooks_stage10_paper.sqlite") as conn:
        raw = conn.execute(
            "SELECT metadata_json FROM brooks_stage11_positions WHERE order_id=?",
            (oid,),
        ).fetchone()[0]
        data = json.loads(raw)
        data["net_realized_pnl"] = "999999999"
        conn.execute(
            "UPDATE brooks_stage11_positions SET metadata_json=? WHERE order_id=?",
            (json.dumps(data), oid),
        )
    with pytest.raises(Stage12ResearchRefused, match="NET_ACCOUNTING_CONFLICT"):
        evaluate(root)


def test_corrupt_brooks_receipt_refuses_scope(local):
    root, _ = local
    with sqlite3.connect(root/"custom_paper.db") as conn:
        conn.execute("UPDATE brooks_paper_receipts SET receipt_sha256=?", ("0"*64,))
    with pytest.raises(Stage12ResearchRefused, match="RECEIPT_HASH_FAILURE"):
        evaluate(root)


def test_post_close_open_risk_not_counted_as_realized_profit(local):
    root, oid = local
    finish(root)
    with sqlite3.connect(root/"brooks_stage10_paper.sqlite") as conn:
        conn.execute(
            "UPDATE paper_risk_reservations SET status='ACTIVE' WHERE order_id=?",
            (oid,),
        )
    with pytest.raises(Stage12ResearchRefused, match="RISK_NOT_RELEASED"):
        evaluate(root)


def test_missing_candle_journal_refuses_report(local):
    root, oid = local
    finish(root)
    with sqlite3.connect(root/"brooks_stage10_paper.sqlite") as conn:
        conn.execute(
            "DELETE FROM brooks_stage11_bars WHERE order_id=? AND seq=1",
            (oid,),
        )
    with pytest.raises(Stage12ResearchRefused, match="BAR_JOURNAL_INCOMPLETE"):
        evaluate(root)


def test_readonly_does_not_create_files_or_advance_lifecycle(local):
    root, oid = local
    before = set(p.name for p in root.iterdir())
    with sqlite3.connect(root/"brooks_stage10_paper.sqlite") as conn:
        initial = conn.execute(
            "SELECT COUNT(*) FROM paper_order_events WHERE order_id=?", (oid,),
        ).fetchone()[0]
    first = evaluate(root)
    second = evaluate(root)
    assert first == second
    extra = {p.name for p in root.iterdir()} - before
    # Opening an existing SQLite WAL database in mode=ro can create WAL-index
    # and shared-memory sidecars; these are not transactional row writes.
    assert extra <= {
        "custom_paper.db-wal", "custom_paper.db-shm",
        "brooks_stage10_paper.sqlite-wal", "brooks_stage10_paper.sqlite-shm",
    }
    with sqlite3.connect(root/"brooks_stage10_paper.sqlite") as conn:
        after = conn.execute(
            "SELECT COUNT(*) FROM paper_order_events WHERE order_id=?", (oid,),
        ).fetchone()[0]
    assert initial == after == 1


def test_never_creates_missing_account_database(tmp_path):
    root = tmp_path/"no-db"
    with pytest.raises(Stage12ResearchRefused, match="DATABASE_MISSING"):
        evaluate(root)
    assert not root.exists()


def test_cli_explicit_research_gates_and_safe_report(local, tmp_path):
    root, _ = local
    report_path = tmp_path/"study.json"
    report_path.write_bytes(encoded())
    args = argparse.Namespace(
        state_dir=root, manifest=report_path,
        ack_offline_research_only=True,
    )
    for env in ({}, {"MMT_NONPRODUCTION":"0"},
                {"MMT_NONPRODUCTION":"1", "MMT_PRODUCTION":"1"}):
        with pytest.raises(Stage12ResearchRefused, match="NONPRODUCTION_OPTIN"):
            run_once(args, environment=env)
    args.ack_offline_research_only = False
    with pytest.raises(Stage12ResearchRefused, match="NONPRODUCTION_OPTIN"):
        run_once(args, environment={"MMT_NONPRODUCTION":"1"})
    args.ack_offline_research_only = True
    result = run_once(args, environment={"MMT_NONPRODUCTION":"1"})
    assert result["status"] == "INCOMPLETE_PAPER_OUTCOMES"


def test_cli_rejects_symlink_manifest(local, tmp_path):
    root, _ = local
    original = tmp_path/"real.json"
    original.write_bytes(encoded())
    symlink = tmp_path/"alias.json"
    symlink.symlink_to(original)
    args = argparse.Namespace(
        state_dir=root, manifest=symlink, ack_offline_research_only=True,
    )
    with pytest.raises(Stage12ResearchRefused, match="MANIFEST_FILE_UNSAFE"):
        run_once(args, environment={"MMT_NONPRODUCTION":"1"})


@pytest.mark.parametrize("bytestring", [
    b"{}", b"null", b"\x00", b"", b"\xff",
    b'{"schema_version":1,"schema_version":1}',
])
def test_noncanonical_or_missing_study_manifest_fails_closed(local, bytestring):
    root, _ = local
    with pytest.raises(Stage12ResearchRefused):
        evaluate_brooks_stage12(root, bytestring)
