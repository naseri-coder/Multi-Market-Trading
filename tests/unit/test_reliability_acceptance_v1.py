"""Stage13 read-only robustness and restart acceptance; synthetic evidence only."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from naseri_markets.reliability_acceptance_v1 import (
    AcceptanceRefused, LedgerPaths, evaluate_offline_reliability,
)


def wire(v):
    return json.dumps(v, sort_keys=True, separators=(",", ":"))


def seed(tmp_path, *, paper=True, signal=True):
    paths = LedgerPaths(tmp_path / "control.sqlite", tmp_path / "paper.sqlite",
                        tmp_path / "signal.sqlite")
    with sqlite3.connect(paths.control) as c:
        c.executescript("""
            CREATE TABLE t12_instances(instance_id TEXT,core_id TEXT,created_by INTEGER,revision INTEGER,max_reserved TEXT,max_notional TEXT,max_order TEXT,max_orders INTEGER);
            CREATE TABLE t12_bindings(binding_id TEXT,instance_id TEXT,market TEXT,provider TEXT,symbol TEXT);
            CREATE TABLE t12_audit(seq INTEGER,instance_id TEXT,actor_id INTEGER,revision INTEGER,action TEXT,payload_hash TEXT,prev_hash TEXT,entry_hash TEXT);
        """)
        c.execute("INSERT INTO t12_instances VALUES (?,?,?,?,?,?,?,?)", ("inst_a","fixture.contract.check",101,2,"0.10","0.50","0.05",10))
        c.execute("INSERT INTO t12_bindings VALUES (?,?,?,?,?)",("bind_a","inst_a","crypto","fixture_venue","ABCUSD"))
        prev = "0" * 64
        for rev,action in ((1,"CREATE"),(2,"ADD_BINDING")):
            payload = "a" * 64
            raw=wire([prev,"inst_a",101,rev,action,payload])
            digest=hashlib.sha256(raw.encode()).hexdigest()
            c.execute("INSERT INTO t12_audit VALUES (?,?,?,?,?,?,?,?)",
                      (rev,"inst_a",101,rev,action,payload,prev,digest))
            prev=digest
    with sqlite3.connect(paths.paper) as c:
        c.executescript("""
            CREATE TABLE paper_core_orders(order_id TEXT,instance_id TEXT,binding_id TEXT,account_id TEXT);
            CREATE TABLE paper_core_allocations(instance_id TEXT,policy_json TEXT);
            CREATE TABLE paper_core_bindings(binding_id TEXT,instance_id TEXT);
            CREATE TABLE paper_core_decisions(order_id TEXT,binding_id TEXT);
            CREATE TABLE paper_risk_reservations(order_id TEXT,status TEXT);
            CREATE TABLE paper_orders(order_id TEXT,snapshot TEXT);
            CREATE TABLE paper_stage9_plans(order_id TEXT);
            CREATE TABLE paper_stage9_exits(order_id TEXT);
            CREATE TABLE paper_stage9_bars(order_id TEXT);
        """)
        if paper:
            c.execute("INSERT INTO paper_core_allocations VALUES (?,?)",("inst_a",wire(dict(account_id="account_a",instance_id="inst_a",core_id="fixture.contract.check",max_reserved_risk_fraction="0.10",max_notional_fraction="0.50",max_order_risk_fraction="0.05",max_active_orders=10))))
            c.execute("INSERT INTO paper_core_bindings VALUES (?,?)",("bind_a","inst_a"))
            c.execute("INSERT INTO paper_core_orders VALUES (?,?,?,?)",("order_a","inst_a","bind_a","account_a"))
            c.execute("INSERT INTO paper_core_decisions VALUES (?,?)",("order_a","bind_a"))
            c.execute("INSERT INTO paper_risk_reservations VALUES (?,?)",("order_a","RELEASED"))
            c.execute("INSERT INTO paper_orders VALUES (?,?)",("order_a",wire(dict(status="CLOSED",filled_quantity="1",closed_quantity="1",spec=dict(account_id="account_a",engine_id="fixture.contract.check",instrument=dict(market="crypto",provider="fixture_venue",symbol="ABCUSD"))))))
            c.execute("INSERT INTO paper_stage9_plans VALUES (?)",("order_a",))
            c.execute("INSERT INTO paper_stage9_exits VALUES (?)",("order_a",))
            c.execute("INSERT INTO paper_stage9_bars VALUES (?)",("order_a",))
    with sqlite3.connect(paths.signal) as c:
        c.executescript("""
          CREATE TABLE offline_signal_states(signal_key TEXT,instance_id TEXT,binding_id TEXT,core_id TEXT,market TEXT,provider TEXT,symbol TEXT,status TEXT,channel_id INTEGER);
          CREATE TABLE offline_signal_events(signal_key TEXT,payload_json TEXT,payload_sha256 TEXT);
          CREATE TABLE offline_signal_commands(signal_key TEXT,channel_id INTEGER,state TEXT,message_id INTEGER);
        """)
        if signal:
            c.execute("INSERT INTO offline_signal_states VALUES (?,?,?,?,?,?,?,?,?)",("sign_a","inst_a","bind_a","fixture.contract.check","crypto","fixture_venue","ABCUSD","TARGETS_COMPLETE",-10012))
            body=wire({"event":"ENTRY"})
            c.execute("INSERT INTO offline_signal_events VALUES (?,?,?)",("sign_a",body,hashlib.sha256(body.encode()).hexdigest()))
            c.execute("INSERT INTO offline_signal_commands VALUES (?,?,?,?)",("sign_a",-10012,"PENDING",None))
    return paths


def sql(path, statement, params=()):
    with sqlite3.connect(path) as c:
        c.execute(statement, params)


def test_three_role_integrity_and_determinism(tmp_path):
    paths=seed(tmp_path)
    before={p:p.read_bytes() for p in (paths.control,paths.paper,paths.signal)}
    a=evaluate_offline_reliability(paths)
    b=evaluate_offline_reliability(paths)
    assert a == b
    assert a.integrity_verdict == "PASS"
    assert a.release_verdict == "BLOCKED_NONPRODUCTION_UNATTESTED"
    assert a.counts["paper_orders"] == a.counts["signal_states"] == 1
    assert not a.telegram_sent and not a.broker_order_sent and not a.production_authorized
    assert all(path.read_bytes() == data for path,data in before.items())


def test_signal_only_and_paper_only_keep_independent_permissions(tmp_path):
    for name,options in (("signal",dict(paper=False)),("paper",dict(signal=False))):
        location=tmp_path/name;location.mkdir()
        result=evaluate_offline_reliability(seed(location,**options))
        assert result.integrity_verdict == "PASS"
        assert result.release_verdict.startswith("BLOCKED")


@pytest.mark.parametrize("target,stmt,reason",[
  ("paper","UPDATE paper_risk_reservations SET status='ACTIVE'","TERMINAL_ORDER_RISK_STILL_RESERVED"),
  ("paper","UPDATE paper_risk_reservations SET status='RELEASED'",None),
  ("paper","DELETE FROM paper_orders","ORPHAN_PAPER_ORDER"),
  ("paper","DELETE FROM paper_stage9_plans",None),
  ("control","UPDATE t12_bindings SET provider='wrong'","PAPER_INSTRUMENT_IDENTITY_MISMATCH"),
  ("control","UPDATE t12_audit SET entry_hash='deadbeef' WHERE revision=1","CONTROL_AUDIT_HASH_CHAIN_TAMPERED"),
  ("paper","UPDATE paper_core_allocations SET policy_json='{}'","INVALID_PAPER_ALLOCATION_POLICY"),
  ("control","UPDATE t12_instances SET max_order='0.03'","PANEL_TO_PAPER_RISK_BUDGET_DRIFT"),
  ("signal","UPDATE offline_signal_commands SET state='UNKNOWN'","DELIVERY_AMBIGUOUS"),
  ("signal","UPDATE offline_signal_commands SET channel_id=-10099","CROSS_CHANNEL"),
  ("signal","UPDATE offline_signal_events SET payload_json='{}'","SIGNAL_EVENT_CONTENT_TAMPERED"),
])
def test_fault_injection(tmp_path,target,stmt,reason):
    paths=seed(tmp_path)
    sql(getattr(paths,target),stmt)
    report=evaluate_offline_reliability(paths)
    if reason:
        assert any(reason in issue for issue in report.blockers)
        assert report.integrity_verdict == "BLOCKED"
    else:
        assert report.release_verdict.startswith("BLOCKED")


def test_released_while_open_rejected(tmp_path):
    paths=seed(tmp_path)
    row=dict(status="FILLED",filled_quantity="1",closed_quantity="0",spec=dict(account_id="account_a",engine_id="fixture.contract.check",instrument=dict(market="crypto",provider="fixture_venue",symbol="ABCUSD")))
    sql(paths.paper,"UPDATE paper_orders SET snapshot=?",(wire(row),))
    report=evaluate_offline_reliability(paths)
    assert "RISK_RELEASED_ON_OPEN_POSITION" in report.blockers


def test_missing_and_symlink_files_refused_without_creation(tmp_path):
    paths=seed(tmp_path)
    missing=tmp_path/"no.sqlite"
    with pytest.raises(AcceptanceRefused,match="EXISTING_REGULAR"):
        evaluate_offline_reliability(replace(paths,signal=missing))
    assert not missing.exists()
    link=tmp_path/"link.sqlite";link.symlink_to(paths.signal)
    with pytest.raises(AcceptanceRefused,match="EXISTING_REGULAR"):
        evaluate_offline_reliability(replace(paths,signal=link))
    with pytest.raises(AcceptanceRefused,match="SHARED_DATABASE"):
        evaluate_offline_reliability(replace(paths,signal=paths.paper))


def test_missing_schema_fails_closed(tmp_path):
    paths=seed(tmp_path)
    with sqlite3.connect(paths.signal) as c:
        c.execute("DROP TABLE offline_signal_commands")
    with pytest.raises(AcceptanceRefused,match="STAGE_SCHEMA_MISSING"):
        evaluate_offline_reliability(paths)


def test_empty_never_claims_ready(tmp_path):
    result=evaluate_offline_reliability(seed(tmp_path,paper=False,signal=False))
    assert result.integrity_verdict == "BLOCKED"
    assert "NO_EVALUATED_OUTPUT_EVIDENCE" in result.blockers


def test_clashing_origin_not_executed(tmp_path):
    paths=seed(tmp_path)
    sql(paths.signal,"UPDATE offline_signal_states SET binding_id='impostor'")
    assert "ORPHAN_OR_MISMATCHED_SIGNAL_BINDING" in evaluate_offline_reliability(paths).blockers


def test_unknown_signal_ack_rejected(tmp_path):
    paths=seed(tmp_path)
    sql(paths.signal,"UPDATE offline_signal_commands SET state='SIMULATED_ACK'")
    assert "ACK_WITHOUT_SIMULATED_MESSAGE_ID" in evaluate_offline_reliability(paths).blockers
