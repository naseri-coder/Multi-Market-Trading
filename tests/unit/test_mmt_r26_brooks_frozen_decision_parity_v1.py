"""R26: synthetic future what-if tests, real pinned Brooks worker once.

These are NOT actual historical PnL, live fills, exchange-signed source,
prospective OOS or connected PAPER tests. Full corpus still runs the pinned
source worker in an isolated subprocess for the real-worker smoke case.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from naseri_markets import brooks_frozen_decision_parity_mmt_r26_v1 as r26
from naseri_markets.futures_economic_scenario_stage16_v1 import FundingMarkScenario
from scripts import mmt_r26_offline_brooks_decision_cashflow_audit_v1 as cli

START = datetime(2024, 1, 1, tzinfo=UTC)
BAR = timedelta(minutes=15)
SOURCE = Path(r26.__file__).resolve().parents[1] / "production_source"


@pytest.fixture(autouse=True)
def research_only(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def _bar(i, *, opening="100", high="102", low="98", closing="100"):
    return {
        "open_time": (START + i*BAR).isoformat(),
        "close_time": (START + (i+1)*BAR).isoformat(),
        "open": opening, "high": high, "low": low,
        "close": closing, "volume": "10",
    }


def _replay():
    body = {
        "schema_version": 1, "origin": "replay", "market": "crypto",
        "provider": "binance_replay", "exchange": "binance",
        "market_type": "futures", "symbol": "BTCUSDT",
        "quote_currency": "USDT", "timezone": "UTC",
        "timeframe": "15m", "candles": [_bar(i) for i in range(60)],
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()


def _meta(*, fee="0.0004", slip="0.001"):
    raw=json.dumps({
        "schema_version":1,"provider_claim":"binance_usdm_operator_claim",
        "symbol":"BTCUSDT","contract_kind":"linear_perpetual",
        "settle_currency":"USDT","base_units_per_contract":"1",
        "price_tick":"1","quantity_step":"1",
        "taker_fee_fraction":fee,"worst_slippage_fraction":slip,
        "maintenance_margin_fraction":"0.005",
        "source_metadata_sha256":"a"*64,
    },sort_keys=True,separators=(",",":")).encode()
    return raw, hashlib.sha256(raw).hexdigest()


def _geometry(direction="LONG"):
    return r26.FrozenGeometry(
        decision=direction,input_sha256=hashlib.sha256(_replay()).hexdigest(),
        source_manifest_sha256="a"*64,snapshot_sha256="b"*64,
        decision_evidence_sha256="c"*64,signal_close_at=START+60*BAR,
        entry=None if direction == "NO_SIGNAL" else "100",
        stop=None if direction == "NO_SIGNAL" else (
            "95" if direction == "LONG" else "105"),
        targets=() if direction == "NO_SIGNAL" else (
            ("105",) if direction == "LONG" else ("95",)),
    )


def _paths(direction="LONG", *, funding=False):
    dates=(START+timedelta(hours=16),) if funding else ()
    events=(FundingMarkScenario(
        at=dates[0],funding_rate="0.001",referenced_mark_price="100",
    ),) if funding else ()
    flat=tuple(_bar(i) for i in range(60,64))
    if direction == "SHORT":
        adverse=(
            _bar(60,opening="100",high="107",low="93",closing="100"),
            *(_bar(i) for i in range(61,64)),
        )
    else:
        adverse=(
            _bar(60,opening="100",high="107",low="93",closing="100"),
            *(_bar(i) for i in range(61,64)),
        )
    return (
        r26.R26CounterfactualPath(
            label="unchanged_next_open",post_signal_closed_candles=flat,
            expected_funding_instants=dates,funding_mark_events=events,
        ),
        r26.R26CounterfactualPath(
            label="same_bar_stop_target",post_signal_closed_candles=adverse,
            expected_funding_instants=dates,funding_mark_events=events,
        ),
    )


def _execute(monkeypatch, direction="LONG", *, funding=False):
    calls=[]
    def pinned_worker(predecision, legacy_source):
        calls.append((predecision,legacy_source))
        return _geometry(direction)
    monkeypatch.setattr(r26,"_source",pinned_worker)
    raw,pin=_meta()
    report=r26.r26_audit_frozen_brooks_two_paths(
        original_replay_bytes=_replay(),legacy_source=SOURCE,
        counterfactuals=_paths(direction,funding=funding),
        economic_metadata_bytes=raw,economic_metadata_sha256=pin,
        quantity_contracts="1",operator_ack=True,
    )
    assert len(calls)==1
    assert calls[0] == (_replay(),SOURCE)
    assert report["actual_frozen_worker_invocations"] == 1
    assert report["network_used"] is False
    assert report["connected_paper_started"] is False
    assert report["live_order_authorized"] is False
    assert report["true_prospective_oos_performance_verified"] is False
    assert report["counterfactuals_real_market_observations"] is False
    return report


@pytest.mark.parametrize("direction",("LONG","SHORT"))
def test_same_worker_decision_two_future_paths_with_independent_fee_math(
    monkeypatch,direction,
):
    report=_execute(monkeypatch,direction)
    a,b=report["counterfactuals"]
    assert a["hypothetical_future_path_sha256"]!=b["hypothetical_future_path_sha256"]
    assert a["unchanged_original_frozen_decision_sha256"] == (
        b["unchanged_original_frozen_decision_sha256"]
    )
    assert a["counterfactual_hypothetical_order_model"]["exit_reason"] == (
        "MAX_HORIZON_UNOBSERVED_STOP_OR_TARGET"
    )
    assert b["counterfactual_hypothetical_order_model"]["exit_reason"] == (
        "STOP_PRIORITY_AMBIGUOUS_BAR"
    )
    assert b["counterfactual_hypothetical_order_model"]["intrabar_stop_target_ambiguity"]
    for item in (a,b):
        economics=item["independent_economic_accounting"]
        assert economics["independent_arithmetic_parity"] is True
        assert economics["gross_quote"] is not None
        assert economics["broker_fill_verified"] is False
        assert economics["reported_modeled_net_quote"] == (
            economics["independent_net_quote"]
        )
        assert item["actual_broker_fill_reconciled"] is False
    assert a["independent_economic_accounting"]["two_sided_taker_fee_quote"] == "0.0800"
    assert a["independent_economic_accounting"]["two_sided_adverse_slippage_proxy_quote"] == "0.200"
    assert b["independent_economic_accounting"]["charged_funding_instants"] == 0


def test_funding_charged_only_while_modeled_position_still_open(monkeypatch):
    report=_execute(monkeypatch,"LONG",funding=True)
    long_hold,early_stop=report["counterfactuals"]
    assert long_hold["independent_economic_accounting"]["charged_funding_instants"]==1
    assert long_hold["independent_economic_accounting"]["funding_quote"]=="-0.100"
    assert early_stop["independent_economic_accounting"]["charged_funding_instants"]==0
    assert early_stop["independent_economic_accounting"]["funding_quote"]=="0"


def test_short_positive_funding_is_received_by_model_not_actual_exchange(monkeypatch):
    report=_execute(monkeypatch,"SHORT",funding=True)
    hold=report["counterfactuals"][0]
    assert hold["independent_economic_accounting"]["funding_quote"]=="0.100"
    assert hold["counterfactual_hypothetical_order_model"]["broker_fill_verified"] is False


def test_no_signal_never_invents_an_order_or_profit(monkeypatch):
    report=_execute(monkeypatch,"NO_SIGNAL")
    for case in report["counterfactuals"]:
        rec=case["independent_economic_accounting"]
        assert rec["model_state"]=="NO_SIGNAL"
        assert rec["independent_arithmetic_parity"] is None
        assert rec["reported_modeled_net_quote"] is None
        assert rec["broker_fill_verified"] is False


def test_mutated_model_net_is_rejected_by_independent_decimal_reconciliation(monkeypatch):
    monkeypatch.setattr(r26,"_source",lambda *_:_geometry("LONG"))
    real=r26._model_next_open
    def fraudulent(*args,**kwargs):
        report=real(*args,**kwargs)
        report["net_scenario_quote"]="9999.00"
        return report
    monkeypatch.setattr(r26,"_model_next_open",fraudulent)
    raw,pin=_meta()
    with pytest.raises(r26.R26AttributionRefused,match="INDEPENDENT_DECIMAL"):
        r26.r26_audit_frozen_brooks_two_paths(
            original_replay_bytes=_replay(),legacy_source=SOURCE,
            counterfactuals=_paths(),economic_metadata_bytes=raw,
            economic_metadata_sha256=pin,quantity_contracts="1",operator_ack=True,
        )


def test_forged_original_stage16_receipt_hash_refused_even_if_net_is_correct(monkeypatch):
    monkeypatch.setattr(r26,"_source",lambda *_:_geometry("LONG"))
    real=r26._model_next_open
    def forged(*args,**kwargs):
        model=real(*args,**kwargs)
        assert model["state"]=="HYPOTHETICAL_CLOSED_POSITION"
        model["economic_receipt_sha256"]="f"*64
        return model
    monkeypatch.setattr(r26,"_model_next_open",forged)
    raw,pin=_meta()
    with pytest.raises(r26.R26AttributionRefused,match="ECONOMIC_RECEIPT_SHA"):
        r26.r26_audit_frozen_brooks_two_paths(
            original_replay_bytes=_replay(),legacy_source=SOURCE,
            counterfactuals=_paths(),economic_metadata_bytes=raw,
            economic_metadata_sha256=pin,quantity_contracts="1",operator_ack=True,
        )


def test_gapped_entry_is_reported_as_no_model_fill(monkeypatch):
    monkeypatch.setattr(r26,"_source",lambda *_:_geometry("LONG"))
    flat=list(_paths()[0].post_signal_closed_candles)
    gapped=replace(_paths()[0],label="gapped_entry",
                   post_signal_closed_candles=(
                       _bar(60,opening="110",high="112",low="109",closing="110"),
                       *flat[1:],
                   ))
    raw,pin=_meta()
    report=r26.r26_audit_frozen_brooks_two_paths(
        original_replay_bytes=_replay(),legacy_source=SOURCE,
        counterfactuals=(gapped,_paths()[1]),
        economic_metadata_bytes=raw,economic_metadata_sha256=pin,
        quantity_contracts="1",operator_ack=True,
    )
    first=report["counterfactuals"][0]
    assert first["independent_economic_accounting"]["model_state"] == (
        "MODEL_REFUSED_GAPPED_OR_DEVIATED_ENTRY"
    )
    assert first["independent_economic_accounting"]["independent_arithmetic_parity"] is None


def test_missing_funding_event_fails_closed_before_reporting_cashflow(monkeypatch):
    monkeypatch.setattr(r26,"_source",lambda *_:_geometry("LONG"))
    wrong=list(_paths(funding=True))
    wrong[0]=replace(wrong[0],funding_mark_events=())
    raw,pin=_meta()
    with pytest.raises(ValueError,match="FUNDING"):
        r26.r26_audit_frozen_brooks_two_paths(
            original_replay_bytes=_replay(),legacy_source=SOURCE,
            counterfactuals=tuple(wrong),
            economic_metadata_bytes=raw,economic_metadata_sha256=pin,
            quantity_contracts="1",operator_ack=True,
        )


def test_identical_futures_or_duplicate_labels_refuse_before_worker(monkeypatch):
    monkeypatch.setattr(r26,"_source",lambda *_:pytest.fail("worker must not run"))
    raw,pin=_meta()
    a,b=_paths()
    for cases,refusal in (
        ((a,replace(b,post_signal_closed_candles=a.post_signal_closed_candles)),
         "MUST_DIFFER"),
        ((a,replace(b,label=a.label)),"UNIQUE_BOUNDED"),
    ):
        with pytest.raises(r26.R26AttributionRefused,match=refusal):
            r26.r26_audit_frozen_brooks_two_paths(
                original_replay_bytes=_replay(),legacy_source=SOURCE,
                counterfactuals=cases,economic_metadata_bytes=raw,
                economic_metadata_sha256=pin,quantity_contracts="1",
                operator_ack=True,
            )


def test_bad_metadata_sha_and_no_ack_refuse_before_worker(monkeypatch):
    monkeypatch.setattr(r26,"_source",lambda *_:pytest.fail("worker must not run"))
    raw,pin=_meta()
    arguments=dict(original_replay_bytes=_replay(),legacy_source=SOURCE,
                   counterfactuals=_paths(),economic_metadata_bytes=raw,
                   economic_metadata_sha256=pin,quantity_contracts="1")
    with pytest.raises(r26.R26AttributionRefused,match="PINNED_ECONOMICS"):
        r26.r26_audit_frozen_brooks_two_paths(
            **{**arguments,"economic_metadata_sha256":"0"*64},
            operator_ack=True,
        )
    with pytest.raises(r26.R26AttributionRefused,match="NONPRODUCTION"):
        r26.r26_audit_frozen_brooks_two_paths(**arguments,operator_ack=False)


def test_production_fence_and_bogus_future_rejected(monkeypatch):
    raw,pin=_meta()
    arguments=dict(original_replay_bytes=_replay(),legacy_source=SOURCE,
                   counterfactuals=_paths(),economic_metadata_bytes=raw,
                   economic_metadata_sha256=pin,quantity_contracts="1")
    monkeypatch.setenv("MMT_PRODUCTION","1")
    monkeypatch.setattr(r26,"_source",lambda *_:pytest.fail("worker must not run"))
    with pytest.raises(r26.R26AttributionRefused,match="NONPRODUCTION"):
        r26.r26_audit_frozen_brooks_two_paths(**arguments,operator_ack=True)
    monkeypatch.delenv("MMT_PRODUCTION")
    monkeypatch.setattr(r26,"_source",lambda *_:_geometry("LONG"))
    a,b=_paths()
    skipped=replace(a,post_signal_closed_candles=(
        _bar(62),_bar(63),_bar(64),_bar(65),
    ))
    with pytest.raises(ValueError,match="CONTINUATION|NONCAUSAL"):
        r26.r26_audit_frozen_brooks_two_paths(
            **{**arguments,"counterfactuals":(skipped,b)},operator_ack=True,
        )


def test_one_real_frozen_brooks_v5_subprocess_called_before_counterfactuals(
    monkeypatch,
):
    """A REAL source-pinned worker evaluation, but fake future inputs only."""
    assert SOURCE.is_dir()
    real_worker=r26._source
    seen=[]
    def observed(*args):
        seen.append(args)
        return real_worker(*args)
    monkeypatch.setattr(r26,"_source",observed)
    raw,pin=_meta()
    report=r26.r26_audit_frozen_brooks_two_paths(
        original_replay_bytes=_replay(),legacy_source=SOURCE,
        counterfactuals=_paths(),economic_metadata_bytes=raw,
        economic_metadata_sha256=pin,quantity_contracts="1",operator_ack=True,
    )
    assert len(seen)==1
    assert seen[0] == (_replay(),SOURCE)
    assert report["frozen_original_decision"]["original_frozen_source_manifest_sha256"]
    assert report["frozen_original_decision"]["decision_evidence_sha256"]
    assert report["actual_frozen_worker_invocations"] == 1
    assert all(not p["actual_broker_fill_reconciled"] for p in report["counterfactuals"])
    assert report["backtest_trading_edge_demonstrated"] is False


def test_termux_cli_requires_explicit_research_ack(monkeypatch,tmp_path):
    monkeypatch.setenv("MMT_NONPRODUCTION","1")
    monkeypatch.setattr(
        cli, "r26_audit_frozen_brooks_two_paths",
        lambda **kw: pytest.fail("worker or model invoked without consent"),
    )
    with pytest.raises(SystemExit,match="NONPRODUCTION"):
        cli.main([
            "--original-predecision-replay",str(tmp_path/"missing.json"),
            "--two-futures-json",str(tmp_path/"missing-futures.json"),
            "--economic-metadata",str(tmp_path/"missing-meta.json"),
            "--economic-metadata-sha256","a"*64,
            "--quantity-contracts","1",
        ])


def test_manual_cli_loads_two_bounded_counterfactuals_without_network(
    monkeypatch,tmp_path,capsys,
):
    replay=tmp_path/"predecision.json"
    replay.write_bytes(_replay())
    meta=tmp_path/"contract.json"
    raw,pin=_meta()
    meta.write_bytes(raw)
    cases=_paths(funding=True)
    futures=tmp_path/"two-paths.json"
    futures.write_text(json.dumps({
        "protocol":"MMT_R26_TWO_OPERATOR_HYPOTHETICAL_PATHS_V1",
        "scenarios":[{
            "label":case.label,
            "future_candles":list(case.post_signal_closed_candles),
            "expected_funding_instants":[t.isoformat()
                                         for t in case.expected_funding_instants],
            "funding_events":[{
                "at":e.at.isoformat(),
                "funding_rate":e.funding_rate,
                "referenced_mark_price":e.referenced_mark_price,
            } for e in case.funding_mark_events],
        } for case in cases],
    },sort_keys=True).encode())
    called=[]
    def no_market_connection(**kw):
        called.append(kw)
        return {"network_used":False,"live_order_authorized":False}
    monkeypatch.setattr(cli,"r26_audit_frozen_brooks_two_paths",no_market_connection)
    cli.main([
        "--ack-research-only",
        "--original-predecision-replay",str(replay),
        "--two-futures-json",str(futures),
        "--economic-metadata",str(meta),
        "--economic-metadata-sha256",pin,
        "--quantity-contracts","1",
    ])
    assert len(called)==1
    assert called[0]["original_replay_bytes"]==_replay()
    assert called[0]["counterfactuals"]==cases
    assert called[0]["quantity_contracts"]=="1"
    assert called[0]["operator_ack"] is True
    assert '"network_used": false' in capsys.readouterr().out


def test_manual_cli_refuses_symlinked_counterfactuals_and_duplicate_json(
    monkeypatch,tmp_path,
):
    other=tmp_path/"other.json"
    other.write_bytes(b"{}")
    link=tmp_path/"linked.json"
    link.symlink_to(other)
    with pytest.raises(ValueError,match="BOUNDED_LOCAL_FILE"):
        cli._read_bounded_file(link)
    with pytest.raises(ValueError,match="SCENARIO_JSON_SCHEMA"):
        cli._paths(b'{"protocol":"x","protocol":"x","scenarios":[]}')
