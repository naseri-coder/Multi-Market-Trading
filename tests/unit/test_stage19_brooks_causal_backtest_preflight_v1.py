"""Stage19 synthetic-data tests that actually execute frozen Brooks V5.

No real venue bytes, authenticated mark/funding or strategy PnL in test data.
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from naseri_markets import stage17_official_archive_capture_v1 as stage17
from naseri_markets.binance_vision_archive_stage16_v1 import select_reviewed_brooks_window
from naseri_markets.brooks_causal_backtest_preflight_stage19_v1 import (
    Stage19Refused, review_stage19_brooks_causal_preflight,
)
from naseri_markets.futures_economics_evidence_stage18_v1 import (
    Stage18ScenarioTrade, audit_futures_economic_evidence,
)

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "production_source"
BEGIN = datetime(2024, 1, 1, tzinfo=UTC)
INTERVAL = timedelta(minutes=15)


@pytest.fixture(autouse=True)
def safe(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def _fixture_zip():
    name = "BTCUSDT-15m-2024-01.zip"
    rows = []
    for index in range(31 * 24 * 4):
        ms = int(BEGIN.timestamp()) * 1000 + index * 900000
        rows.append(f"{ms},100,101,99,100,10,{ms+899999},1000,10,4,400,0")
    handle = io.BytesIO()
    with zipfile.ZipFile(handle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name[:-4]+".csv", ("\n".join(rows) + "\n").encode())
    blob = handle.getvalue()
    checksum = (hashlib.sha256(blob).hexdigest() + "  " + name + "\n").encode()
    return blob, checksum


def _metadata():
    metadata = {
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
    return json.dumps(metadata, sort_keys=True, separators=(",", ":")).encode()


def _make_args(tmp_path, monkeypatch):
    raw_zip, chk = _fixture_zip()
    monkeypatch.setattr(
        stage17, "_get_exact",
        lambda url, _size: chk if url.endswith(".CHECKSUM") else raw_zip,
    )
    captured = stage17.capture_stage17_vision_month(
        year=2024, month=1, operator_ack=True,
    )
    stage17_path = tmp_path / "stage17-research"
    stage17.persist_research_capture(captured, destination=stage17_path)
    stage17_receipt = (stage17_path / "quality-report.json").read_bytes()
    meta = _metadata()
    schedule = b"funding_time_utc\n2024-01-01T08:00:00Z\n"
    events = (b"funding_time_utc,funding_rate,mark_price\n"
              b"2024-01-01T08:00:00Z,0.0001,100\n")
    economic = audit_futures_economic_evidence(
        captured, stage17_quality_report_bytes=stage17_receipt,
        contract_metadata_bytes=meta,
        contract_metadata_sha256=hashlib.sha256(meta).hexdigest(),
        scheduled_funding_csv_bytes=schedule,
        scheduled_funding_sha256=hashlib.sha256(schedule).hexdigest(),
        funding_mark_csv_bytes=events,
        funding_mark_sha256=hashlib.sha256(events).hexdigest(),
        scenarios=(Stage18ScenarioTrade(
            "reviewed_hypothetical", "long", "0.01", "100", "101",
            BEGIN + timedelta(hours=4), BEGIN + timedelta(hours=12),
            "1", 5,
        ),),
        operator_ack=True,
    )
    window = select_reviewed_brooks_window(
        captured.archive, start_bar_index=0, count=72, operator_ack=True,
    )
    path = tmp_path / "stage19-exact-window.csv"
    path.write_bytes(window.canonical_csv_bytes)
    return dict(
        capture=captured, window=window, window_csv_path=path,
        stage18_report_bytes=json.dumps(economic, sort_keys=True).encode(),
        legacy_source=SOURCE,
        evaluation_cutoffs_utc=(BEGIN + INTERVAL*60, BEGIN + INTERVAL*72),
        archive_as_of_utc=datetime.now(UTC), operator_ack=True,
    )


def test_genuine_frozen_brooks_closes_only_and_never_sends_trades(tmp_path, monkeypatch):
    assert SOURCE.is_dir()
    args = _make_args(tmp_path, monkeypatch)
    before = args["window_csv_path"].read_bytes()
    report = review_stage19_brooks_causal_preflight(**args)
    assert report["actual_frozen_brooks_v5_executed"] is True
    assert report["reviewed_cuts"] == 2
    assert [d["visible_bar_count"] for d in report["decisions"]] == [60, 72]
    assert all(d["actual_brooks_decision"] in ("NO_SIGNAL", "LONG", "SHORT")
               for d in report["decisions"])
    assert [d["has_subsequent_candle"] for d in report["decisions"]] == [True, False]
    assert all(d["future_candle_price_exposed_to_engine"] is False for d in report["decisions"])
    assert report["economic_backtest_executed"] is False
    assert report["profitability_proven"] is False
    assert report["production_authorized"] is False
    assert report["next_stage_authorized"] is False
    assert report["blockers"]
    assert args["window_csv_path"].read_bytes() == before
    assert not list(tmp_path.rglob("*.sqlite"))
    repeated = review_stage19_brooks_causal_preflight(**args)
    assert report == repeated


def test_stage18_unverified_or_tampered_report_never_reaches_worker(tmp_path, monkeypatch):
    args = _make_args(tmp_path, monkeypatch)
    from naseri_markets import brooks_causal_backtest_preflight_stage19_v1 as mod
    monkeypatch.setattr(mod, "review_real_brooks_history",
                        lambda *_a, **_k: pytest.fail("unexpected Brooks subprocess"))
    doc = json.loads(args["stage18_report_bytes"])
    doc["canonical_month_csv_sha256"] = "b" * 64
    args["stage18_report_bytes"] = json.dumps(doc).encode()
    with pytest.raises(Stage19Refused, match="ECONOMIC_LINEAGE"):
        review_stage19_brooks_causal_preflight(**args)
    doc["canonical_month_csv_sha256"] = args["capture"].archive.csv_sha256
    doc["source_independently_authenticated"] = True
    unsigned = dict(doc)
    unsigned.pop("report_sha256")
    doc["report_sha256"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    args["stage18_report_bytes"] = json.dumps(doc).encode()
    with pytest.raises(Stage19Refused, match="UNSUPPORTED_VERIFIED_CLAIM"):
        review_stage19_brooks_causal_preflight(**args)


def test_parent_window_pins_and_disk_tamper_fail_closed(tmp_path, monkeypatch):
    args = _make_args(tmp_path, monkeypatch)
    from naseri_markets import brooks_causal_backtest_preflight_stage19_v1 as mod
    monkeypatch.setattr(mod, "review_real_brooks_history",
                        lambda *_a, **_k: pytest.fail("unexpected Brooks subprocess"))
    args["window"] = replace(args["window"], parent_official_zip_sha256="0"*64)
    with pytest.raises(Stage19Refused, match="PARENT_SHA"):
        review_stage19_brooks_causal_preflight(**args)
    args["window"] = select_reviewed_brooks_window(
        args["capture"].archive, start_bar_index=0, count=72, operator_ack=True,
    )
    args["window_csv_path"].write_bytes(args["window"].canonical_csv_bytes + b"forgery")
    with pytest.raises(Stage19Refused, match="DISK_DATA_CHANGED"):
        review_stage19_brooks_causal_preflight(**args)


def test_nonproduction_and_noncausal_cutoffs_blocked(tmp_path, monkeypatch):
    args = _make_args(tmp_path, monkeypatch)
    from naseri_markets import brooks_causal_backtest_preflight_stage19_v1 as mod
    monkeypatch.setattr(mod, "review_real_brooks_history",
                        lambda *_a, **_k: pytest.fail("unexpected Brooks subprocess"))
    args["operator_ack"] = False
    with pytest.raises(Stage19Refused, match="NONPRODUCTION"):
        review_stage19_brooks_causal_preflight(**args)
    args["operator_ack"] = True
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(Stage19Refused, match="NONPRODUCTION"):
        review_stage19_brooks_causal_preflight(**args)
    monkeypatch.delenv("MMT_PRODUCTION")
    args["evaluation_cutoffs_utc"] = (BEGIN + INTERVAL*72, BEGIN + INTERVAL*60)
    with pytest.raises(Stage19Refused, match="CAUSAL_CUTS"):
        review_stage19_brooks_causal_preflight(**args)
    args["evaluation_cutoffs_utc"] = (BEGIN + INTERVAL*60,)*2
    with pytest.raises(Stage19Refused, match="CAUSAL_CUTS"):
        review_stage19_brooks_causal_preflight(**args)
