"""R22 offline lineage and fail-closed Binance schema regression tests."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from naseri_markets.brooks_future_kline_admission_stage21f_v1 import (
    Stage21AdmissionRefused,
    _rows,
)

ROOT=Path(__file__).resolve().parents[2]
START=datetime(2026,10,20,tzinfo=UTC)
IMMUTABLE={
    "docs/STAGE17_NETWORK_INDEPENDENT_SOURCE_INTAKE_V1.md":
        "b89c6cc327eefe0e6a4abf1c3c1e0220d3f6cb90",
    "docs/STAGE17_REAL_BTCUSDT_2024_01_EVIDENCE.md":
        "bda5869c4b1ff1e0afbb19a358a37bf82fa5a2df",
    "docs/STAGE18_REAL_BINANCE_FUNDING_MARK_2024_01_EVIDENCE.md":
        "1699a26e63096ef85d3d72ad0a0da2d61fe74f12",
    "naseri_markets/binance_public_funding_mark_stage18_v1.py":
        "320286e540db84b4197d1e16b308ec5567b01b6f",
    "tests/unit/test_stage18_primary_public_funding_mark_v1.py":
        "7bcd0e7337cddd3ba0cfa9dd7cb63c61c9c792e7",
}
DOWNLOAD_WORKFLOWS=(
    ".github/workflows/stage17-official-archive-acquisition.yml",
    ".github/workflows/stage18-public-funding-mark-evidence.yml",
)

def _blob(data):
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()

@pytest.mark.parametrize("path,sha",tuple(IMMUTABLE.items()))
def test_identical_reviewed_original_git_blobs(path,sha):
    assert _blob((ROOT/path).read_bytes()) == sha

@pytest.mark.parametrize("path",DOWNLOAD_WORKFLOWS)
def test_restored_downloaders_are_explicitly_manual_only(path):
    source=(ROOT/path).read_text()
    triggers=source.split("permissions:",1)[0]
    assert "workflow_dispatch:" in triggers
    assert all(t not in triggers for t in ("pull_request:","push:","schedule:"))
    assert "I_APPROVE_ONE_READONLY_HISTORICAL_DOWNLOAD" in source
    assert "if: "+chr(36)+"{{ inputs.explicit_historical_source_research_approval ==" in source
    assert "permissions:\n  contents: read" in source

def test_original_external_timestamped_study_and_bridge_source_not_modified():
    raw=(ROOT/"docs/evidence/"
         "STAGE21E_BROOKS_ORIGINAL_EXTERNALLY_TIMESTAMPED_PLAN_20261016.json").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == (
        "c557e8792ff7f097ee483903e2e6702c622a20f3975af898ee9aca7e257ad94d"
    )
    plan=json.loads(raw)
    assert plan["study_start_utc"]=="2026-10-20T00:00:00Z"
    assert plan["study_end_utc"]=="2026-11-03T00:00:00Z"
    assert plan["paper_market_access"] is False
    bridge=(ROOT/"naseri_markets/"
            "brooks_primary_source_funding_join_stage21b_v1.py").read_bytes()
    assert hashlib.sha256(bridge).hexdigest() == plan["bridge_source_sha256"]

def test_one_canonical_stage21f_module_in_stage21g_pipeline():
    assert not (ROOT/"naseri_markets/brooks_forward_http_intake_stage21f_v1.py").exists()
    assert (ROOT/"naseri_markets/brooks_future_kline_admission_stage21f_v1.py").is_file()
    source=(ROOT/"naseri_markets/brooks_forward_source_custody_stage21g_v1.py").read_text()
    assert "brooks_future_kline_admission_stage21f_v1" in source
    assert "brooks_forward_http_intake_stage21f_v1" not in source

def bar():
    ts=int(START.timestamp()*1000)
    return [ts,"100.0","104.0","99.0","102.0","10",ts+899999,"1000",12,"4","400","0"]

def packet(*bars):
    return json.dumps(list(bars),separators=(",",":")).encode("ascii")

def test_canonical_twelve_column_parser_accepts_correct_original_data():
    result=_rows(packet(bar()),start=START,expected=1)
    assert result.startswith(b"open_at,close_at,open,high,low,close,volume\n")
    assert result.endswith(b"100.0,104.0,99.0,102.0,10\n")

@pytest.mark.parametrize("idx,bad",[
    (1,"0"),(2,"90"),(3,"105"),(4,"-1"),
    (5,"NaN"),(5,"-1"),(7,"garbage"),(7,1000),
    (8,True),(8,-1),(9,"-1"),(10,"NaN"),
    (10,400),(11,"1"),(11,0),
])
def test_bad_original_twelve_column_source_never_enters_pipeline(idx,bad):
    fields=bar()
    fields[idx]=bad
    with pytest.raises(Stage21AdmissionRefused):
        _rows(packet(fields),start=START,expected=1)

def test_nan_constant_duplicate_and_missing_candle_rejected():
    source=packet(bar())
    with pytest.raises(Stage21AdmissionRefused):
        _rows(source.replace(b'"1000"',b'NaN'),start=START,expected=1)
    second=bar()
    second[0]+=900000
    second[6]+=900000
    assert _rows(packet(bar(),second),start=START,expected=2).count(b"\n")==3
    second[0]+=900000
    with pytest.raises(Stage21AdmissionRefused,match="GRID"):
        _rows(packet(bar(),second),start=START,expected=2)
