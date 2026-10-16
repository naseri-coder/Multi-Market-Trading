"""R26 original Brooks receipt parity audit adversarial tests (synthetic only)."""
from __future__ import annotations

import copy
import hashlib
import json

import pytest

from naseri_markets import brooks_causal_execution_parity_audit_mmt_r26_v1 as r26
from naseri_markets.brooks_replay import LEGACY_MANIFEST_SHA256


def canon(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":"),allow_nan=False,ensure_ascii=True).encode("ascii")


def digest(obj):
    return hashlib.sha256(canon(obj)).hexdigest()


@pytest.fixture(autouse=True)
def research_only(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION","1")
    monkeypatch.delenv("MMT_PRODUCTION",raising=False)


def report(decision="LONG",state="HYPOTHETICAL_CLOSED_POSITION"):
    trade={
        "state":state,
        "hypothetical_order":state=="HYPOTHETICAL_CLOSED_POSITION",
        "broker_fill_verified":False,
        "net_scenario_quote":"-0.25" if state=="HYPOTHETICAL_CLOSED_POSITION" else None,
    }
    if state=="HYPOTHETICAL_CLOSED_POSITION":
        trade.update({
            "entry_model":"NEXT_CANDLE_OPEN_MARKET_ASSUMPTION",
            "exit_model":"NEAREST_TP_OR_STOP_FIRST_ADVERSE_GAP_PRIORITY",
            "actual_signal_execution_parity_verified":False,
            "account_fee_tier_verified":False,
            "settlement_mark_is_exact":False,
            "market_impact_verified":False,
            "funding_event_count":0,
            "entry_time":"2024-01-01T15:00:00+00:00",
            "exit_assumed_bar_close_time":"2024-01-01T15:15:00+00:00",
            "exit_reason":"STOP_TOUCHED",
            "economic_receipt_sha256":"a"*64,
            "entry_reference_price":"100",
            "exit_reference_price":"99",
            "quantity_contracts":"0.01",
        })
    d={
        "stage":"STAGE21_BROOKS_CAUSAL_LIFECYCLE_PREPARATION_V1",
        "status":"ACTUAL_FROZEN_DECISION_HYPOTHETICAL_TRADE_MODEL_ONLY",
        "source_manifest_sha256":LEGACY_MANIFEST_SHA256,
        "historical_snapshot_sha256":"b"*64,
        "decision_evidence_sha256":"c"*64,
        "decision_input_sha256":"d"*64,
        "future_input_sha256":"e"*64,
        "decision_cutoff_utc":"2024-01-01T15:00:00+00:00",
        "actual_frozen_brooks_decision":decision,
        "hypothetical_trade":trade,
        "independent_dataset_archive_authentication":False,
        "exact_contract_fee_and_mark_verified":False,
        "prospective_holdout_untouched_attested":False,
        "real_brooks_strategy_execution_parity":False,
        "actual_realized_pnl":False,
        "paper_trading_enabled":False,
        "live_trading_authorized":False,
        "network_or_telegram_used":False,
        "production_modified":False,
    }
    d["report_sha256"]=digest(d)
    return d


def seal(d):
    d=copy.deepcopy(d)
    d.pop("report_sha256",None)
    d["report_sha256"]=digest(d)
    return canon(d)


def audit(d):
    return r26.audit_original_stage21a_receipt(
        original_report_bytes=seal(d),operator_ack=True,
    )


@pytest.mark.parametrize("side",["LONG","SHORT"])
def test_genuine_receipt_shape_still_cannot_certify_broker_parity(side):
    r=audit(report(side))
    assert r["decision"]==side
    assert r["modeled_net_quote_reference_not_actual_pnl"]=="-0.25"
    assert r["strategy_order_type_equivalent_to_next_open_market_assumption"] is False
    assert r["historical_or_prospective_trade_profitability_established"] is False
    assert r["broker_fill_or_order_receipt_present"] is False
    assert r["connected_paper_mode_authorized"] is False
    assert r["live_order_authorized"] is False


def test_no_signal_never_becomes_trade():
    r=audit(report("NO_SIGNAL","NO_SIGNAL"))
    assert r["parity_disposition"]=="NO_SIGNAL_NO_ORDER"
    assert r["modeled_net_quote_reference_not_actual_pnl"] is None


def test_refused_gapped_entry_does_not_book_pnl():
    r=audit(report("LONG","MODEL_REFUSED_GAPPED_OR_DEVIATED_ENTRY"))
    assert r["parity_disposition"]=="HYPOTHETICAL_ENTRY_REFUSED"
    assert r["modeled_net_quote_reference_not_actual_pnl"] is None


@pytest.mark.parametrize("key,value",[
    ("real_brooks_strategy_execution_parity",True),
    ("actual_realized_pnl",True),
    ("paper_trading_enabled",True),
    ("live_trading_authorized",True),
    ("exact_contract_fee_and_mark_verified",True),
    ("source_manifest_sha256","f"*64),
    ("status","BROKER_EXECUTION_VERIFIED"),
])
def test_cannot_promote_any_stage21a_unsupported_claim(key,value):
    d=report()
    d[key]=value
    with pytest.raises(r26.R26ParityRefused):
        audit(d)


@pytest.mark.parametrize("key,value",[
    ("broker_fill_verified",True),
    ("actual_signal_execution_parity_verified",True),
    ("account_fee_tier_verified",True),
    ("settlement_mark_is_exact",True),
    ("market_impact_verified",True),
    ("entry_model","EXACT_BROKER_MARKET_FILL"),
    ("exit_model","UNOBSERVED_INTRABAR_PRIORITY"),
    ("quantity_contracts","0"),
    ("net_scenario_quote","NaN"),
    ("funding_event_count",17),
])
def test_cannot_upgrade_modeled_trade_to_verified(key,value):
    d=report()
    d["hypothetical_trade"][key]=value
    with pytest.raises(r26.R26ParityRefused):
        audit(d)


def test_tampered_hash_and_noncanonical_json_refused():
    original=report()
    raw=canon(original)
    with pytest.raises(r26.R26ParityRefused,match="SHA_MISMATCH"):
        r26.audit_original_stage21a_receipt(
            original_report_bytes=raw.replace(b'"LONG"',b'"SHORT"'),
            operator_ack=True,
        )
    with pytest.raises(r26.R26ParityRefused,match="SHA_MISMATCH"):
        r26.audit_original_stage21a_receipt(
            original_report_bytes=json.dumps(original,indent=2).encode(),
            operator_ack=True,
        )


def test_duplicate_json_and_nonfinite_json_refused():
    raw=canon(report())
    altered=raw.replace(b'"stage":',b'"stage":"fake","stage":')
    with pytest.raises(r26.R26ParityRefused,match="DUPLICATE"):
        r26.audit_original_stage21a_receipt(
            original_report_bytes=altered,operator_ack=True,
        )
    altered=raw.replace(b'"actual_realized_pnl":false',b'"actual_realized_pnl":NaN')
    with pytest.raises(r26.R26ParityRefused,match="NONFINITE"):
        r26.audit_original_stage21a_receipt(
            original_report_bytes=altered,operator_ack=True,
        )


def test_no_signal_with_scenario_pnl_rejected():
    d=report("NO_SIGNAL","NO_SIGNAL")
    d["hypothetical_trade"]["net_scenario_quote"]="1000000"
    with pytest.raises(r26.R26ParityRefused,match="NO_SIGNAL"):
        audit(d)


def test_original_receipt_missing_model_fields_refused():
    d=report()
    del d["hypothetical_trade"]["economic_receipt_sha256"]
    with pytest.raises(r26.R26ParityRefused,match="INCOMPLETE"):
        audit(d)


def test_refuses_production_and_missing_ack(monkeypatch):
    d=report()
    with pytest.raises(r26.R26ParityRefused,match="NONPRODUCTION"):
        r26.audit_original_stage21a_receipt(
            original_report_bytes=seal(d),operator_ack=False,
        )
    monkeypatch.setenv("MMT_PRODUCTION","1")
    with pytest.raises(r26.R26ParityRefused,match="NONPRODUCTION"):
        audit(d)


def test_original_stage21a_worker_called_before_parity_audit(monkeypatch):
    calls=[]
    monkeypatch.setattr(
        r26,"run_stage21_brooks_lifecycle_preflight",
        lambda **kwargs:(calls.append(("stage21a",kwargs)),report())[1],
    )
    result=r26.run_r26_genuine_brooks_model_and_audit(
        original_replay_bytes=b"synthetic",operator_ack=True,
    )
    assert calls[0][0]=="stage21a"
    assert calls[0][1]["operator_ack"] is True
    assert result["original_stage21a_report"]["actual_frozen_brooks_decision"]=="LONG"
    assert result["r26_execution_parity_audit"]["parity_disposition"]==(
        "MODELED_LIFECYCLE_ONLY_ACTUAL_ORDER_PARITY_UNVERIFIED"
    )
