"""Actual native Stage18 raw-archive parser on STRICTLY SYNTHETIC fixtures."""
from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from datetime import UTC, datetime

import pytest

from naseri_markets.binance_public_funding_mark_stage18_v1 import (
    Stage18MarketEvidenceRefused, reconcile_stage18_primary_public_sources,
)

_START_MS = int(datetime(2024, 1, 1, tzinfo=UTC).timestamp()) * 1000


@pytest.fixture(autouse=True)
def research(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def _zip(kind, rows):
    if kind == "funding":
        name = "BTCUSDT-fundingRate-2024-01.zip"
    else:
        name = "BTCUSDT-15m-2024-01.zip"
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(name.replace(".zip", ".csv"),
                   ("\n".join(",".join(row) for row in rows) + "\n").encode())
    original = out.getvalue()
    checksum = (hashlib.sha256(original).hexdigest() + "  " + name + "\n").encode()
    return original, checksum


def _fixture():
    marks = [[
        "open_time", "open", "high", "low", "close", "volume", "close_time",
        "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore",
    ]]
    for i in range(31 * 96):
        start = _START_MS + i * 900000
        marks.append([str(start), "100", "102", "99", "101", "0",
                      str(start + 899999), "0", "900", "0", "0", "0"])
    funding = [["calc_time", "funding_interval_hours", "last_funding_rate"]]
    for i in range(31 * 3):
        funding.append([str(_START_MS + i * 8 * 3600000), "8", "0.0001"])
    fz, fc = _zip("funding", funding)
    mz, mc = _zip("mark", marks)
    return dict(funding_zip=fz, funding_checksum=fc,
                mark_zip=mz, mark_checksum=mc, operator_ack=True), funding, marks


def test_complete_month_reconciles_92_nonboundary_source_events():
    args, _, _ = _fixture()
    report, schedule, rates = reconcile_stage18_primary_public_sources(**args)
    assert report["observed_funding_events"] == 93
    assert report["mark_candle_rows"] == 2976
    assert report["source_derived_reconciled_funding_events"] == 92
    assert report["excluded_boundary_funding_events"]
    a = list(csv.DictReader(io.StringIO(schedule.decode())))
    b = list(csv.DictReader(io.StringIO(rates.decode())))
    assert len(a) == len(b) == 92
    assert a[0]["funding_time_utc"] == "2024-01-01T08:00:00Z"
    assert b[0]["mark_price"] == "101"
    assert a[-1]["funding_time_utc"] == "2024-01-31T16:00:00Z"
    assert report["mark_price_is_prior_15m_candle_close_proxy"] is True
    assert not report["historical_mark_at_exact_settlement_proven"]
    assert not report["account_specific_fee_tier_verified"]
    assert not report["paper_trading_authorized"]
    assert report["normal_rate_mark_sha256"] == hashlib.sha256(rates).hexdigest()
    assert reconcile_stage18_primary_public_sources(**args)[0] == report


def test_funding_schedule_missing_event_refused():
    args, funding, _ = _fixture()
    funding.pop(4)
    args["funding_zip"], args["funding_checksum"] = _zip("funding", funding)
    with pytest.raises(Stage18MarketEvidenceRefused, match="ROW_COUNT"):
        reconcile_stage18_primary_public_sources(**args)


def test_shifted_funding_timestamp_or_change_in_interval_refused():
    args, funding, _ = _fixture()
    funding[4][0] = str(int(funding[4][0]) + 3600000)
    args["funding_zip"], args["funding_checksum"] = _zip("funding", funding)
    with pytest.raises(Stage18MarketEvidenceRefused, match="FUNDING_INTERVAL"):
        reconcile_stage18_primary_public_sources(**args)


def test_incorrect_mark_candle_grid_or_negative_ohlc_refused():
    args, funding, marks = _fixture()
    marks[2][0] = str(int(marks[2][0]) + 900000)
    args["mark_zip"], args["mark_checksum"] = _zip("mark", marks)
    with pytest.raises(Stage18MarketEvidenceRefused, match="MARK_CANDLE_GRID"):
        reconcile_stage18_primary_public_sources(**args)
    marks[2][0] = str(_START_MS + 900000)
    marks[2][1] = "-1"
    args["mark_zip"], args["mark_checksum"] = _zip("mark", marks)
    with pytest.raises(Stage18MarketEvidenceRefused, match="BOUNDS"):
        reconcile_stage18_primary_public_sources(**args)


def test_tampered_funding_checksum_refused():
    args, _, _ = _fixture()
    args["funding_checksum"] = b"0" * 64 + b"  BTCUSDT-fundingRate-2024-01.zip\n"
    with pytest.raises(Stage18MarketEvidenceRefused, match="CHECKSUM"):
        reconcile_stage18_primary_public_sources(**args)


def test_production_and_operator_ack_blocked(monkeypatch):
    args, _, _ = _fixture()
    args["operator_ack"] = False
    with pytest.raises(Stage18MarketEvidenceRefused, match="ACK"):
        reconcile_stage18_primary_public_sources(**args)
    args["operator_ack"] = True
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(Stage18MarketEvidenceRefused, match="ACK"):
        reconcile_stage18_primary_public_sources(**args)
