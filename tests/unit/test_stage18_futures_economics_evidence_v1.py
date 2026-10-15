"""Stage18 fully offline evidence reconciliation over STUBBED Stage17 acquisition.

Every candle, contract parameter, event and trade in these tests is synthetic.
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from naseri_markets import stage17_official_archive_capture_v1 as stage17
from naseri_markets.futures_economics_evidence_stage18_v1 import (
    Stage18Refused, Stage18ScenarioTrade, audit_futures_economic_evidence,
)


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def raw_month():
    first = datetime(2024, 1, 1, tzinfo=UTC)
    name = "BTCUSDT-15m-2024-01.zip"
    candles = []
    for n in range(31 * 24 * 4):
        timestamp = int(first.timestamp()) * 1000 + n * 900000
        candles.append(f"{timestamp},100,102,98,100,10,{timestamp+899999},1000,10,4,400,0")
    source = ("\n".join(candles) + "\n").encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name[:-4] + ".csv", source)
    raw_zip = buffer.getvalue()
    checksum = (hashlib.sha256(raw_zip).hexdigest() + "  " + name + "\n").encode()
    return raw_zip, checksum


def fixture_capture(monkeypatch, tmp_path):
    raw_zip, checksum = raw_month()
    def get_exact(url, limit):
        return checksum if url.endswith(".CHECKSUM") else raw_zip
    monkeypatch.setattr(stage17, "_get_exact", get_exact)
    capture = stage17.capture_stage17_vision_month(year=2024, month=1, operator_ack=True)
    report = stage17.persist_research_capture(capture, destination=tmp_path / "stage17-receipt")
    assert report["rows"] == 2976
    data = (tmp_path / "stage17-receipt" / "quality-report.json").read_bytes()
    return capture, data


def metadata():
    body = {
        "schema_version": 1,
        "provider_claim": "binance_usdm_operator_claim",
        "symbol": "BTCUSDT",
        "contract_kind": "linear_perpetual",
        "settle_currency": "USDT",
        "base_units_per_contract": "1",
        "price_tick": "0.1",
        "quantity_step": "0.001",
        "taker_fee_fraction": "0.0004",
        "worst_slippage_fraction": "0.0007",
        "maintenance_margin_fraction": "0.005",
        "source_metadata_sha256": "1" * 64,
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()


def funding():
    schedule = ("funding_time_utc\n"
                "2024-01-01T08:00:00Z\n"
                "2024-01-01T16:00:00Z\n"
                "2024-01-02T00:00:00Z\n").encode()
    events = ("funding_time_utc,funding_rate,mark_price\n"
              "2024-01-01T08:00:00Z,0.0001,100\n"
              "2024-01-01T16:00:00Z,-0.0002,101\n"
              "2024-01-02T00:00:00Z,0.0003,100\n").encode()
    return schedule, events


def trade_set():
    dt = lambda day, hour: datetime(2024, 1, day, hour, tzinfo=UTC)
    return (
        Stage18ScenarioTrade(
            "scenario_long", "long", "0.01", "100", "101",
            dt(1, 4), dt(1, 12), "1", 5,
        ),
        Stage18ScenarioTrade(
            "scenario_short", "short", "0.01", "101", "99",
            dt(1, 12), dt(1, 20), "1", 5,
        ),
    )


def inputs(monkeypatch, tmp_path):
    capture, stage17_report = fixture_capture(monkeypatch, tmp_path)
    meta = metadata()
    schedule, records = funding()
    return {
        "capture": capture,
        "stage17_quality_report_bytes": stage17_report,
        "contract_metadata_bytes": meta,
        "contract_metadata_sha256": hashlib.sha256(meta).hexdigest(),
        "scheduled_funding_csv_bytes": schedule,
        "scheduled_funding_sha256": hashlib.sha256(schedule).hexdigest(),
        "funding_mark_csv_bytes": records,
        "funding_mark_sha256": hashlib.sha256(records).hexdigest(),
        "scenarios": trade_set(),
        "operator_ack": True,
    }


def test_actual_stage17_stage12_revalidation_and_stage16_decimal_economics(monkeypatch, tmp_path):
    args = inputs(monkeypatch, tmp_path)
    result = audit_futures_economic_evidence(**args)
    assert result["declared_funding_events"] == 3
    assert result["scenario_count"] == 2
    assert result["original_market_zip_sha256"] == args["capture"].archive.zip_sha256
    assert result["stage17_quality_report_sha256"]
    assert result["report_sha256"]
    long, short = result["scenarios"]
    assert long["funding_events_in_window"] == 1
    assert short["funding_events_in_window"] == 1
    assert long["cashflow_cases"][0]["funding_quote"] == "-0.00010000"
    assert short["cashflow_cases"][0]["funding_quote"] == "-0.00020200"
    assert float(long["cashflow_cases"][3]["net_quote"]) < float(long["cashflow_cases"][0]["net_quote"])
    assert not result["source_independently_authenticated"]
    assert not result["actual_historical_funding_schedule_verified"]
    assert not result["historical_mark_prices_authenticated"]
    assert not result["effective_account_fee_tier_verified"]
    assert not result["orderbook_liquidity_and_slippage_verified"]
    assert not result["complete_margin_liquidation_model_verified"]
    assert not result["connected_to_real_brooks_trades"]
    assert not result["real_historical_futures_backtest_run"]
    assert not result["live_trading_authorized"]
    repeat = audit_futures_economic_evidence(**args)
    assert repeat["report_sha256"] == result["report_sha256"]


@pytest.mark.parametrize("field,new", [
    ("scheduled_funding_sha256", "0" * 64),
    ("funding_mark_sha256", "f" * 64),
    ("contract_metadata_sha256", "a" * 64),
])
def test_pinned_files_are_immutable(monkeypatch, tmp_path, field, new):
    args = inputs(monkeypatch, tmp_path)
    args[field] = new
    with pytest.raises(Stage18Refused, match="PINNED"):
        audit_futures_economic_evidence(**args)


def test_missing_funding_schedule_event_refuses_instead_of_zero_fill(monkeypatch, tmp_path):
    args = inputs(monkeypatch, tmp_path)
    broken = args["funding_mark_csv_bytes"].replace(
        b"2024-01-01T16:00:00Z,-0.0002,101\n", b"",
    )
    args.update(funding_mark_csv_bytes=broken,
                funding_mark_sha256=hashlib.sha256(broken).hexdigest())
    with pytest.raises(Stage18Refused, match="INCOMPLETE"):
        audit_futures_economic_evidence(**args)


def test_hostile_duplicate_unordered_or_unexpected_schedule_refused(monkeypatch, tmp_path):
    args = inputs(monkeypatch, tmp_path)
    corrupted = args["scheduled_funding_csv_bytes"].replace(
        b"2024-01-01T16:00:00Z", b"2024-01-01T08:00:00Z",
    )
    args.update(scheduled_funding_csv_bytes=corrupted,
                scheduled_funding_sha256=hashlib.sha256(corrupted).hexdigest())
    with pytest.raises(Stage18Refused, match="UNORDERED"):
        audit_futures_economic_evidence(**args)


def test_nonproduction_and_ack_rejections_precede_all_validation(monkeypatch, tmp_path):
    args = inputs(monkeypatch, tmp_path)
    args["operator_ack"] = False
    with pytest.raises(Stage18Refused, match="NONPRODUCTION"):
        audit_futures_economic_evidence(**args)
    args["operator_ack"] = True
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(Stage18Refused, match="NONPRODUCTION"):
        audit_futures_economic_evidence(**args)


def test_stale_stage17_receipt_or_archive_tampering_refused(monkeypatch, tmp_path):
    args = inputs(monkeypatch, tmp_path)
    payload = json.loads(args["stage17_quality_report_bytes"])
    payload["original_zip_sha256"] = "b" * 64
    args["stage17_quality_report_bytes"] = json.dumps(payload).encode()
    with pytest.raises(Stage18Refused, match="LINEAGE"):
        audit_futures_economic_evidence(**args)


def test_low_collateral_and_overleveraged_scenarios_blocked(monkeypatch, tmp_path):
    args = inputs(monkeypatch, tmp_path)
    scenario = args["scenarios"][0]
    args["scenarios"] = (replace(scenario, isolated_collateral_usdt="0.01"),)
    with pytest.raises(Stage18Refused, match="COLLATERAL"):
        audit_futures_economic_evidence(**args)
    args["scenarios"] = (replace(scenario, leverage=50),)
    with pytest.raises(Stage18Refused, match="LEVERAGE"):
        audit_futures_economic_evidence(**args)


def test_overlap_and_duplicate_scenario_ids_refused(monkeypatch, tmp_path):
    args = inputs(monkeypatch, tmp_path)
    first, second = args["scenarios"]
    args["scenarios"] = (first, replace(second, entry_at_utc=first.entry_at_utc))
    with pytest.raises(Stage18Refused, match="OVERLAPPED"):
        audit_futures_economic_evidence(**args)
    args["scenarios"] = (first, replace(second, scenario_id=first.scenario_id))
    with pytest.raises(Stage18Refused, match="SCENARIO_ID"):
        audit_futures_economic_evidence(**args)


def test_forbidden_fee_stress_headroom(monkeypatch, tmp_path):
    args = inputs(monkeypatch, tmp_path)
    doc = json.loads(args["contract_metadata_bytes"])
    doc["taker_fee_fraction"] = "0.009"
    raw = json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()
    args.update(contract_metadata_bytes=raw,
                contract_metadata_sha256=hashlib.sha256(raw).hexdigest())
    with pytest.raises(Stage18Refused, match="STRESS_COST"):
        audit_futures_economic_evidence(**args)


def test_malformed_funding_values_and_csv_columns(monkeypatch, tmp_path):
    args = inputs(monkeypatch, tmp_path)
    wrong = args["funding_mark_csv_bytes"].replace(
        b"0.0001,100", b"0.9000,100",
    )
    args.update(funding_mark_csv_bytes=wrong,
                funding_mark_sha256=hashlib.sha256(wrong).hexdigest())
    with pytest.raises(Stage18Refused, match="BOUNDS"):
        audit_futures_economic_evidence(**args)
    wrong = b"funding_time_utc,fee\n2024-01-01T08:00:00Z,0.0001\n"
    args.update(funding_mark_csv_bytes=wrong,
                funding_mark_sha256=hashlib.sha256(wrong).hexdigest())
    with pytest.raises(Stage18Refused, match="SCHEMA"):
        audit_futures_economic_evidence(**args)
