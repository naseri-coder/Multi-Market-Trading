"""Stage 11 full-population, read-only, fail-closed research acceptance."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, UTC
from decimal import Decimal as D

import pytest

from naseri_markets.strategy_research_lab_v1 import (
    ResearchLabRefused, evaluate_stage9_research, parse_protocol,
)

DAYS = ("2026-01-02", "2026-01-12", "2026-01-22")


def dump(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def protocol(ids=None, **kw):
    p = dict(schema_version=1, study_id="research_v1", core_id="examplecore",
             instance_id="instance_a", account_id="account_a",
             window_start_utc="2026-01-01T00:00:00+00:00",
             training_end_utc="2026-01-10T00:00:00+00:00",
             validation_end_utc="2026-01-20T00:00:00+00:00",
             window_end_utc="2026-02-01T00:00:00+00:00",
             expected_order_ids=ids if ids is not None else ["order_1","order_2","order_3"],
             dataset_origin="synthetic_fixture", declared_dataset_sha256="a"*64,
             initial_equity="1000", min_closed_per_segment=1,
             claimed_protocol_frozen_before_outcomes=True)
    p.update(kw)
    return dump(p).encode()


def seed(tmp_path, *, pnl=("10", "-10", "15")):
    path = tmp_path / "paper.sqlite"
    conn = sqlite3.connect(path)
    conn.executescript("""
    CREATE TABLE paper_stage9_plans (order_id TEXT, input_close TEXT, entry_bar_close TEXT, last_bar_close TEXT, plan_json TEXT, setup_id TEXT, manifest_digest TEXT, binding_digest TEXT);
    CREATE TABLE paper_stage9_exits (order_id TEXT, action_id TEXT, reason TEXT, quantity TEXT, price TEXT, gross TEXT, modeled_cost TEXT, net TEXT, evidence_digest TEXT);
    CREATE TABLE paper_stage9_bars (order_id TEXT, bar_close TEXT, bar_digest TEXT, receipt_json TEXT);
    CREATE TABLE paper_core_orders (order_id TEXT, account_id TEXT, instance_id TEXT, binding_id TEXT);
    CREATE TABLE paper_orders (order_id TEXT, snapshot TEXT);
    CREATE TABLE risk_accounts (account_id TEXT, policy TEXT);
    CREATE TABLE paper_core_allocations (instance_id TEXT, policy_json TEXT);
    CREATE TABLE paper_core_bindings (binding_id TEXT, manifest_digest TEXT, binding_digest TEXT);
    CREATE TABLE paper_core_decisions (order_id TEXT, binding_id TEXT, decision_id TEXT);
    """)
    policy=dict(contract_multiplier="1",roundtrip_fee_fraction="0.005",
                worst_slippage_fraction="0.005")
    conn.execute("INSERT INTO risk_accounts VALUES (?,?)", ("account_a",dump(policy)))
    conn.execute("INSERT INTO paper_core_allocations VALUES (?,?)", (
        "instance_a",dump(dict(account_id="account_a",core_id="examplecore",core_version="1",instance_id="instance_a"))))
    for i, (day, net) in enumerate(zip(DAYS,pnl),1):
        order = f"order_{i}"
        entry_at=f"{day}T00:00:00+00:00"
        close_at=f"{day}T00:15:00+00:00"
        digest = hashlib.sha256(order.encode()).hexdigest()
        binding = f"binding_{i}"
        plan = dict(core_id="examplecore",core_version="1",instance_id="instance_a",
                    binding_id=binding,decision_id=f"decision_{i}",source_ref="fixture",
                    timeframe="15m",market="crypto",targets=[{"price":"120","fraction":"1"}])
        conn.execute("INSERT INTO paper_core_orders VALUES (?,?,?,?)",(order,"account_a","instance_a",binding))
        conn.execute("INSERT INTO paper_core_bindings VALUES (?,?,?)",(binding,"b"*64,"c"*64))
        conn.execute("INSERT INTO paper_core_decisions VALUES (?,?,?)",(order,binding,f"decision_{i}"))
        conn.execute("INSERT INTO paper_stage9_plans VALUES (?,?,?,?,?,?,?,?)",(
            order,entry_at,entry_at,close_at,dump(plan),"setup_a","b"*64,"c"*64))
        # Modeled cost = max(100,exit)*1*0.01
        target_net=D(net)
        price = D(100) + (target_net+D(1)) / D("0.99") if target_net >= 0 else (D(100)+target_net+D(1))
        cost = max(D(100),price)*D("0.01")
        gross=price-D(100)
        net_value=gross-cost
        spec=dict(account_id="account_a",engine_id="examplecore",
                  instrument=dict(market="crypto",provider="fixture",symbol=f"PAIR_{i}"),
                  direction="long",reference_entry="100",stop="90",quantity="1")
        snap=dict(status="CLOSED",filled_quantity="1",closed_quantity="1",
                  average_fill_price="100",spec=spec)
        conn.execute("INSERT INTO paper_orders VALUES (?,?)",(order,dump(snap)))
        exitrow=(order,f"action_{i}","TARGET_1","1",str(price),str(gross),str(cost),str(net_value),digest)
        conn.execute("INSERT INTO paper_stage9_exits VALUES (?,?,?,?,?,?,?,?,?)",exitrow)
        receipt=dict(order_id=order,closed_bar=close_at,exits=[dict(
            reason="TARGET_1",quantity="1",price=str(price),gross=str(gross),
            modeled_cost=str(cost),net=str(net_value),risk_released=True)])
        conn.execute("INSERT INTO paper_stage9_bars VALUES (?,?,?,?)",(order,close_at,digest,dump(receipt)))
    conn.commit(); conn.close()
    return path


def test_reproducible_three_segments_and_no_live_claim(tmp_path):
    db=seed(tmp_path)
    before=db.read_bytes()
    raw=protocol()
    result=evaluate_stage9_research(db,raw)
    assert result == evaluate_stage9_research(db,raw)
    assert db.read_bytes()==before
    assert result["expected_order_count"]==3
    assert result["metrics"]["by_setup"]["setup_a"]["closed"]==3
    assert all(result["metrics"][s]["closed"]==1 for s in ("training","validation","holdout"))
    assert result["metrics"]["overall"]["population"]==3
    assert result["metrics"]["overall"]["winners"]==2
    assert result["metrics"]["overall"]["losers"]==1
    assert result["readiness"] == "DESCRIPTIVE_ONLY_NOT_PROFITABILITY_PROOF"
    assert not result["broker_order_sent"] and not result["telegram_sent"]
    assert result["metrics"]["overall"]["stress_2x_cost_net_pnl"] != result["metrics"]["overall"]["net_pnl"]


def test_minimum_samples_are_not_silently_relaxed(tmp_path):
    db=seed(tmp_path)
    r=evaluate_stage9_research(db,protocol(min_closed_per_segment=20))
    assert "INSUFFICIENT_SEGMENT_SAMPLE" in r["blockers"]


def test_nonexhaustive_selection_refused(tmp_path):
    db=seed(tmp_path)
    with pytest.raises(ResearchLabRefused,match="NONEXHAUSTIVE"):
        evaluate_stage9_research(db,protocol(["order_1", "order_2"]))


def test_fake_extra_order_id_refused(tmp_path):
    db=seed(tmp_path)
    with pytest.raises(ResearchLabRefused,match="NONEXHAUSTIVE"):
        evaluate_stage9_research(db,protocol(["order_1","order_2","order_3","fake"] ))


def test_missing_table_refused(tmp_path):
    p=tmp_path/'empty.sqlite'; sqlite3.connect(p).close()
    with pytest.raises(ResearchLabRefused,match="MISSING_STAGE"):
        evaluate_stage9_research(p,protocol())


@pytest.mark.parametrize("mutation,reason",[
    ("UPDATE paper_stage9_exits SET net='999' WHERE order_id='order_1'","UNVERIFIED_EXIT"),
    ("UPDATE paper_stage9_exits SET modeled_cost='0' WHERE order_id='order_1'","UNVERIFIED_EXIT"),
    ("UPDATE paper_stage9_exits SET gross='100' WHERE order_id='order_1'","UNVERIFIED_EXIT"),
    ("UPDATE paper_stage9_exits SET evidence_digest='deadbeef' WHERE order_id='order_1'","UNVERIFIED_EXIT"),
    ("UPDATE paper_stage9_exits SET quantity='2' WHERE order_id='order_1'","MODELED_COST_POLICY"),
    ("DELETE FROM paper_stage9_exits WHERE order_id='order_1'","CLOSED_QUANTITY"),
    ("UPDATE paper_core_orders SET account_id='account_b' WHERE order_id='order_1'","NONEXHAUSTIVE"),
    ("UPDATE paper_stage9_plans SET manifest_digest='a' WHERE order_id='order_1'","CROSS_CORE"),
    ("UPDATE paper_orders SET snapshot='{}' WHERE order_id='order_1'","CROSS_CORE"),
])
def test_tampered_evidence_refused(tmp_path,mutation,reason):
    db=seed(tmp_path)
    conn=sqlite3.connect(db);conn.execute(mutation);conn.commit();conn.close()
    with pytest.raises(ResearchLabRefused,match=reason):
        evaluate_stage9_research(db,protocol())


def test_cross_partition_closure_reported(tmp_path):
    db=seed(tmp_path)
    conn=sqlite3.connect(db)
    moved="2026-01-11T00:15:00+00:00"
    conn.execute("UPDATE paper_stage9_bars SET bar_close=? WHERE order_id='order_1'",(moved,))
    raw=conn.execute("SELECT receipt_json FROM paper_stage9_bars WHERE order_id='order_1'").fetchone()[0]
    d=json.loads(raw);d["closed_bar"]=moved
    conn.execute("UPDATE paper_stage9_bars SET receipt_json=? WHERE order_id='order_1'",(dump(d),))
    conn.commit();conn.close()
    report=evaluate_stage9_research(db,protocol())
    assert "CROSS_PARTITION_EXIT_LEAKAGE" in report["blockers"]


def test_unfilled_and_incomplete_are_in_denominator(tmp_path):
    db=seed(tmp_path)
    con=sqlite3.connect(db)
    order="order_3"
    snap=json.loads(con.execute("SELECT snapshot FROM paper_orders WHERE order_id=?",(order,)).fetchone()[0])
    snap.update(status="CANCELED",filled_quantity="0",closed_quantity="0",average_fill_price=None)
    con.execute("UPDATE paper_orders SET snapshot=? WHERE order_id=?",(dump(snap),order))
    con.execute("DELETE FROM paper_stage9_exits WHERE order_id=?",(order,))
    con.execute("UPDATE paper_stage9_bars SET receipt_json=? WHERE order_id=?",(dump(dict(order_id=order,closed_bar="2026-01-22T00:15:00+00:00",exits=[])),order))
    con.commit();con.close()
    result=evaluate_stage9_research(db,protocol())
    assert result["metrics"]["overall"]["population"]==3
    assert result["metrics"]["overall"]["closed"]==2
    assert result["metrics"]["holdout"]["unfilled"]==1


def test_read_only_missing_file_does_not_create(tmp_path):
    path=tmp_path/'never.sqlite'
    with pytest.raises(ResearchLabRefused,match='EXISTING_REGULAR'):
        evaluate_stage9_research(path,protocol())
    assert not path.exists()


def test_symlink_file_refused(tmp_path):
    db=seed(tmp_path); link=tmp_path/'link.sqlite';link.symlink_to(db)
    with pytest.raises(ResearchLabRefused,match='EXISTING_REGULAR'):
        evaluate_stage9_research(link,protocol())


@pytest.mark.parametrize('change,needle',[
    ({'claimed_protocol_frozen_before_outcomes':False},'FREEZE_CLAIM'),
    ({'dataset_origin':'authenticated_live'},'DATASET_PROVENANCE'),
    ({'initial_equity':'NaN'},'INVALID_DECIMAL'),
    ({'initial_equity':'-1'},'INVALID_DECIMAL'),
    ({'min_closed_per_segment':True},'MINIMUM_SAMPLE'),
    ({'expected_order_ids':['order_1','order_1']},'EXPECTED_ORDER'),
    ({'window_start_utc':'2026-01-10T00:00:00+00:00'},'BOUNDARIES'),
    ({'declared_dataset_sha256':'z'*64},'DATASET_PROVENANCE'),
])
def test_protocol_refusal(change,needle):
    with pytest.raises(ResearchLabRefused,match=needle):
        parse_protocol(protocol(**change))


def test_duplicate_json_protocol_fields_refused():
    raw=protocol().decode().replace('"schema_version":1', '"schema_version":1,"schema_version":1')
    with pytest.raises(ResearchLabRefused,match='DUPLICATE'):
        parse_protocol(raw.encode())


def test_empty_study_requires_no_observed_orders(tmp_path):
    db=seed(tmp_path)
    con=sqlite3.connect(db)
    con.execute('DELETE FROM paper_stage9_exits');con.execute('DELETE FROM paper_stage9_bars');con.execute('DELETE FROM paper_stage9_plans')
    con.commit();con.close()
    r=evaluate_stage9_research(db,protocol(ids=[]))
    assert 'NO_OBSERVED_ORDERS' in r['blockers']
    assert r['metrics']['overall']['win_rate'] is None
    assert r['metrics']['overall']['profit_factor'] is None


def test_stable_report_digest_binds_the_evidence(tmp_path):
    db=seed(tmp_path)
    first=evaluate_stage9_research(db,protocol())
    con=sqlite3.connect(db);con.execute("UPDATE paper_stage9_bars SET bar_digest='f'||substr(bar_digest,2) WHERE order_id='order_2'")
    con.commit();con.close()
    with pytest.raises(ResearchLabRefused,match='UNVERIFIED_EXIT'):
        evaluate_stage9_research(db,protocol())
    assert first['report_sha256']!='0'*64


def test_unplanned_stage8_order_is_reported_not_ignored(tmp_path):
    db=seed(tmp_path)
    con=sqlite3.connect(db)
    con.execute("INSERT INTO paper_core_orders VALUES (?,?,?,?)",
                ("stage8_no_plan","account_a","instance_a","binding_1"))
    con.commit();con.close()
    result=evaluate_stage9_research(db,protocol())
    assert "UNLINKED_STAGE8_ORDERS_WINDOW_UNKNOWN" in result["blockers"]
    assert result["unlinked_stage8_order_count"] == 1


def test_missing_join_evidence_cannot_reduce_the_cohort(tmp_path):
    db=seed(tmp_path)
    con=sqlite3.connect(db)
    con.execute("DELETE FROM paper_core_bindings WHERE binding_id='binding_1'")
    con.commit();con.close()
    with pytest.raises(ResearchLabRefused,match="NONEXHAUSTIVE"):
        evaluate_stage9_research(db,protocol())


def test_cli_is_opt_in_stdout_only_and_declines_missing_db(tmp_path,capsys):
    from scripts.mmt_research_lab_v1 import main
    db=seed(tmp_path)
    study=tmp_path/"research.json";study.write_bytes(protocol())
    assert main(["--db",str(db),"--protocol",str(study)])==2
    assert 'EXPLICIT_OFFLINE_ACK' in capsys.readouterr().err
    assert main(["--db",str(db),"--protocol",str(study),"--ack-offline-research"])==0
    result=json.loads(capsys.readouterr().out)
    assert result["expected_order_count"]==3
    assert main(["--db",str(tmp_path/'missing'),"--protocol",str(study),"--ack-offline-research"])==2


def test_walk_forward_opt_in_is_reproducible_and_does_not_change_legacy_report(tmp_path):
    db = seed(tmp_path)
    original = evaluate_stage9_research(db, protocol())
    augmented = evaluate_stage9_research(
        db, protocol(), walk_forward_folds=2, embargo_seconds=3600,
    )
    assert "walk_forward" not in original
    assert original == evaluate_stage9_research(db, protocol())
    assert augmented == evaluate_stage9_research(
        db, protocol(), walk_forward_folds=2, embargo_seconds=3600,
    )
    assert {k: v for k, v in augmented.items() if k not in (
        "walk_forward", "report_sha256"
    )} == {k: v for k, v in original.items() if k != "report_sha256"}
    assert augmented["walk_forward"]["validation_population"] == 1
    assert augmented["walk_forward"]["holdout_population"] == 1
    assert augmented["walk_forward"]["folds"][1]["validation"]["population"] == 0
    assert "INSUFFICIENT_FOLD_VALIDATION_SAMPLE" in augmented["walk_forward"]["blockers"]
    assert augmented["readiness"] == "DESCRIPTIVE_ONLY_NOT_PROFITABILITY_PROOF"
    assert db.is_file()


@pytest.mark.parametrize("folds,embargo", [
    (1, 0), (13, 0), (2, -1), (2, 604801),
    (2, True), (None, 1),
])
def test_invalid_optional_walk_forward_settings_refuse_entire_audit(
    tmp_path, folds, embargo,
):
    db = seed(tmp_path)
    with pytest.raises(ResearchLabRefused):
        evaluate_stage9_research(
            db, protocol(), walk_forward_folds=folds, embargo_seconds=embargo,
        )


def test_offline_cli_exposes_only_explicit_opt_in_walk_forward(tmp_path, capsys):
    from scripts.mmt_research_lab_v1 import main

    db = seed(tmp_path)
    study = tmp_path / "wf-study.json"
    study.write_bytes(protocol())
    args = [
        "--db", str(db), "--protocol", str(study), "--ack-offline-research",
    ]
    assert main(args + ["--wf-folds", "2", "--wf-embargo-seconds", "3600"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["walk_forward"]["validation_folds"] == 2
    assert output["walk_forward"]["embargo_seconds"] == 3600
    assert not output["walk_forward"]["strategy_retraining_performed"]
    assert main(args + ["--wf-embargo-seconds", "3600"]) == 2
    assert "RESEARCH_REFUSED" in capsys.readouterr().err
