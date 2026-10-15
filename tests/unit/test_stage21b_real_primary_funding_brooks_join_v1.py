"""Synthetic Stage21B complete-month custody/funding to actual Brooks worker.

All figures are fixture prices. Native integration may later be exercised
with separately downloaded genuine provider originals on a disposable runner.
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from naseri_markets import stage17_official_archive_capture_v1 as stage17
from naseri_markets import brooks_primary_source_funding_join_stage21b_v1 as bridge
from naseri_markets.futures_economic_scenario_stage16_v1 import FundingMarkScenario

START = datetime(2024, 1, 1, tzinfo=UTC)
BASE_MS = int(START.timestamp() * 1000)


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def zipped(name, rows):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(name[:-4]+".csv", ("\n".join(rows)+"\n").encode())
    original = output.getvalue()
    checksum = (hashlib.sha256(original).hexdigest()+"  "+name+"\n").encode()
    return original, checksum


def fixture(tmp_path, monkeypatch):
    trade_rows = []
    mark_rows = ["open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore"]
    for n in range(2976):
        m = BASE_MS + 900000*n
        trade_rows.append(f"{m},100,102,98,100,10,{m+899999},1000,10,4,400,0")
        mark_rows.append(f"{m},100,101,99,100,0,{m+899999},0,900,0,0,0")
    trade, trade_chk = zipped("BTCUSDT-15m-2024-01.zip", trade_rows)
    mark, mark_chk = zipped("BTCUSDT-15m-2024-01.zip", mark_rows)
    rates = ["calc_time,funding_interval_hours,last_funding_rate"]
    for n in range(93):
        stamp = BASE_MS + n*8*3600000
        rates.append(f"{stamp},8,0.0001")
    funding, funding_chk = zipped("BTCUSDT-fundingRate-2024-01.zip", rates)
    monkeypatch.setattr(
        stage17, "_get_exact",
        lambda url, _limit: trade_chk if url.endswith(".CHECKSUM") else trade,
    )
    capture = stage17.capture_stage17_vision_month(year=2024, month=1, operator_ack=True)
    folder = tmp_path/"stage17-custody"
    stage17.persist_research_capture(capture, destination=folder)
    quality = (folder/"quality-report.json").read_bytes()
    metadata = json.dumps({
        "schema_version": 1, "provider_claim": "binance_usdm_operator_claim",
        "symbol": "BTCUSDT", "contract_kind": "linear_perpetual",
        "settle_currency": "USDT", "base_units_per_contract": "1",
        "price_tick": "0.1", "quantity_step": "0.001",
        "taker_fee_fraction": "0.0004",
        "worst_slippage_fraction": "0.0007",
        "maintenance_margin_fraction": "0.005",
        "source_metadata_sha256": "1"*64,
    }, sort_keys=True, separators=(",", ":")).encode()
    return dict(
        capture=capture, stage17_quality_report_bytes=quality,
        expected_trade_zip_sha256=hashlib.sha256(trade).hexdigest(),
        funding_zip=funding, funding_checksum=funding_chk,
        expected_funding_zip_sha256=hashlib.sha256(funding).hexdigest(),
        mark_zip=mark, mark_checksum=mark_chk,
        expected_mark_zip_sha256=hashlib.sha256(mark).hexdigest(),
        legacy_source=__import__("pathlib").Path(
            bridge.__file__).resolve().parents[1]/"production_source",
        contract_assumptions_bytes=metadata,
        contract_assumptions_sha256=hashlib.sha256(metadata).hexdigest(),
        quantity_contracts="0.01",
        operator_ack=True,
    )


def test_genuine_frozen_brooks_worker_on_verified_synthetic_three_source_month(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    outcome = bridge.run_stage21b_source_joined_brooks_research(**args)
    assert outcome["predecision_observed_bars"] == 60
    assert outcome["postdecision_modeled_bars"] == 32
    assert outcome["actual_frozen_brooks_decision"] in ("LONG","SHORT","NO_SIGNAL")
    assert outcome["funding_events_in_future_horizon"] == 1
    assert outcome["funding_schedule_sha256"]
    assert outcome["source_derived_funding_and_mark_proxy_sha256"]
    assert outcome["original_brooks_research_evidence_sha256"]
    assert outcome["paper_or_live_market_connections_enabled"] is False
    assert outcome["historical_account_fee_tier_verified"] is False
    assert outcome["statistically_valid_prospective_oos_proven"] is False
    assert outcome["trade_fill_evidence_verified"] is False
    assert outcome["production_modified"] is False
    assert bridge.run_stage21b_source_joined_brooks_research(**args) == outcome


def test_real_source_join_only_calls_worker_with_predecision_bars(tmp_path, monkeypatch):
    args = fixture(tmp_path, monkeypatch)
    observed = {}
    def pseudo_runner(**kw):
        original = json.loads(kw["original_replay_bytes"])
        observed["bars_seen"] = len(original["candles"])
        observed["times"] = kw["expected_funding_instants"]
        observed["events"] = kw["funding_mark_events"]
        observed["future"] = kw["post_signal_closed_candles"]
        return {
            "actual_frozen_brooks_decision": "NO_SIGNAL",
            "actual_realized_pnl": False, "live_trading_authorized": False,
            "paper_trading_enabled": False, "production_modified": False,
            "report_sha256": "2"*64,
            "decision_cutoff_utc": original["candles"][-1]["close_time"],
            "hypothetical_trade": {"state": "NO_SIGNAL"},
        }
    monkeypatch.setattr(bridge, "run_stage21_brooks_lifecycle_preflight", pseudo_runner)
    response = bridge.run_stage21b_source_joined_brooks_research(**args)
    assert observed["bars_seen"] == 60
    assert len(observed["future"]) == 32
    assert observed["times"] == (START+timedelta(hours=16),)
    assert len(observed["events"]) == 1
    assert observed["events"][0] == FundingMarkScenario(
        at=START+timedelta(hours=16),
        funding_rate="0.0001", referenced_mark_price="100",
    )
    assert response["model_trade_state"] == "NO_SIGNAL"


@pytest.mark.parametrize("pin", [
    "expected_trade_zip_sha256","expected_funding_zip_sha256",
    "expected_mark_zip_sha256","contract_assumptions_sha256",
])
def test_operator_sha_drift_refused_before_strategy(tmp_path,monkeypatch,pin):
    args = fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(bridge, "run_stage21_brooks_lifecycle_preflight",
                        lambda **_kw: pytest.fail("must not execute frozen engine"))
    args[pin] = "f"*64
    with pytest.raises(bridge.Stage21SourceRefused, match="PIN"):
        bridge.run_stage21b_source_joined_brooks_research(**args)


def test_missing_funding_event_from_source_is_not_zero_filled(tmp_path,monkeypatch):
    args = fixture(tmp_path,monkeypatch)
    with zipfile.ZipFile(io.BytesIO(args["funding_zip"])) as z:
        rows = z.read(z.namelist()[0]).decode().splitlines()
    rows.pop(4)
    raw, chk = zipped("BTCUSDT-fundingRate-2024-01.zip",rows)
    args["funding_zip"] = raw
    args["funding_checksum"] = chk
    args["expected_funding_zip_sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(bridge.Stage21SourceRefused, match="VALIDATION"):
        bridge.run_stage21b_source_joined_brooks_research(**args)


def test_february_boundary_missing_funding_is_explicit_refusal(tmp_path,monkeypatch):
    args = fixture(tmp_path,monkeypatch)
    args["window_start_bar_index"] = 2976-92
    with pytest.raises(bridge.Stage21SourceRefused, match="BOUNDARY_OR_MISSING"):
        bridge.run_stage21b_source_joined_brooks_research(**args)


def test_future_and_split_not_allowed_to_exceed_bounds(tmp_path,monkeypatch):
    args = fixture(tmp_path,monkeypatch)
    args["next_closed_bars"]=33
    with pytest.raises(bridge.Stage21SourceRefused,match="BOUNDED_PLAN"):
        bridge.run_stage21b_source_joined_brooks_research(**args)
    args["next_closed_bars"]=32
    args["window_start_bar_index"] = 2976-90
    with pytest.raises(bridge.Stage21SourceRefused,match="VALIDATION"):
        bridge.run_stage21b_source_joined_brooks_research(**args)


def test_tampered_stage17_quality_or_production_fence_refused(tmp_path,monkeypatch):
    args=fixture(tmp_path,monkeypatch)
    quality=json.loads(args["stage17_quality_report_bytes"])
    quality["original_zip_sha256"]="a"*64
    args["stage17_quality_report_bytes"]=json.dumps(quality).encode()
    with pytest.raises(bridge.Stage21SourceRefused,match="VALIDATION"):
        bridge.run_stage21b_source_joined_brooks_research(**args)
    monkeypatch.setenv("MMT_PRODUCTION","1")
    with pytest.raises(bridge.Stage21SourceRefused,match="NONPRODUCTION"):
        bridge.run_stage21b_source_joined_brooks_research(**args)


def test_post_exit_funding_must_exist_but_is_not_charged(tmp_path,monkeypatch):
    args=fixture(tmp_path,monkeypatch)
    from naseri_markets.brooks_causal_lifecycle_stage21_preflight_v1 import (
        FrozenGeometry, _model_next_open,
    )
    first=START+timedelta(hours=15)
    g=FrozenGeometry(
        decision="LONG", input_sha256="1"*64,
        source_manifest_sha256="2"*64,
        snapshot_sha256="3"*64, decision_evidence_sha256="4"*64,
        signal_close_at=first, entry="100",stop="95",targets=("105",),
    )
    future=[]
    for n in range(8):
        low="94" if n==0 else "99"
        future.append({
            "open_time":first+timedelta(minutes=15*n),
            "close_time":first+timedelta(minutes=15*(n+1)),
            "open":__import__("decimal").Decimal("100"),
            "high":__import__("decimal").Decimal("102"),
            "low":__import__("decimal").Decimal(low),
            "close":__import__("decimal").Decimal("100"),
            "volume":__import__("decimal").Decimal("10"),
        })
    at=START+timedelta(hours=16)
    e=FundingMarkScenario(at=at,funding_rate="0.0001",referenced_mark_price="100")
    report=_model_next_open(
        g,future=tuple(future),quantity="0.01",
        metadata=args["contract_assumptions_bytes"],
        metadata_sha256=args["contract_assumptions_sha256"],
        expected_funding_instants=(at,),funding_events=(e,),
    )
    assert report["state"]=="HYPOTHETICAL_CLOSED_POSITION"
    assert report["funding_event_count"]==0
    assert report["exit_reason"]=="STOP_TOUCHED"
    with pytest.raises(ValueError,match="FUNDING"):
        _model_next_open(
            g,future=tuple(future),quantity="0.01",
            metadata=args["contract_assumptions_bytes"],
            metadata_sha256=args["contract_assumptions_sha256"],
            expected_funding_instants=(at,),funding_events=(),
        )
