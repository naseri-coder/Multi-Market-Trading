"""Stage20: actual Brooks train/validation decisions, HELDOUT NEVER RUN.

All Stage17 archive, Stage18 funding/mark and economic inputs are SYNTHETIC.
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
from naseri_markets import brooks_walk_forward_preholdout_stage20_v1 as stage20
from naseri_markets.binance_vision_archive_stage16_v1 import (
    select_reviewed_brooks_window,
)
from naseri_markets.brooks_replay import LEGACY_MANIFEST_SHA256
from naseri_markets.futures_economics_evidence_stage18_v1 import (
    Stage18ScenarioTrade, audit_futures_economic_evidence,
)

_BEGIN = datetime(2024, 1, 1, tzinfo=UTC)
_BAR = timedelta(minutes=15)
_SOURCE = Path(stage20.__file__).resolve().parents[1] / "production_source"


@pytest.fixture(autouse=True)
def nonproduction(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def _archive():
    name = "BTCUSDT-15m-2024-01.zip"
    candle_rows = []
    for i in range(31 * 24 * 4):
        ms = int(_BEGIN.timestamp()) * 1000 + i * 900000
        candle_rows.append(
            f"{ms},100,101,99,100,10,{ms+899999},1000,10,4,400,0"
        )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as member:
        member.writestr(name[:-4] + ".csv", ("\n".join(candle_rows) + "\n").encode())
    blob = buffer.getvalue()
    checksum = (hashlib.sha256(blob).hexdigest() + "  " + name + "\n").encode()
    return blob, checksum


def _stage18_metadata():
    return json.dumps({
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
    }, sort_keys=True, separators=(",", ":")).encode()


def _prepare(tmp_path, monkeypatch):
    zipped, checksum = _archive()
    monkeypatch.setattr(
        stage17, "_get_exact",
        lambda url, _cap: checksum if url.endswith(".CHECKSUM") else zipped,
    )
    capture = stage17.capture_stage17_vision_month(
        year=2024, month=1, operator_ack=True,
    )
    local = tmp_path / "stage17-original-evidence"
    stage17.persist_research_capture(capture, destination=local)
    stage17_quality = (local / "quality-report.json").read_bytes()
    meta = _stage18_metadata()
    schedule = b"funding_time_utc\n2024-01-01T08:00:00Z\n"
    marks = (b"funding_time_utc,funding_rate,mark_price\n"
             b"2024-01-01T08:00:00Z,0.0001,100\n")
    economics = audit_futures_economic_evidence(
        capture, stage17_quality_report_bytes=stage17_quality,
        contract_metadata_bytes=meta,
        contract_metadata_sha256=hashlib.sha256(meta).hexdigest(),
        scheduled_funding_csv_bytes=schedule,
        scheduled_funding_sha256=hashlib.sha256(schedule).hexdigest(),
        funding_mark_csv_bytes=marks,
        funding_mark_sha256=hashlib.sha256(marks).hexdigest(),
        scenarios=(
            Stage18ScenarioTrade(
                "frozen_hypothetical", "long", "0.01", "100", "101",
                _BEGIN + timedelta(hours=4), _BEGIN + timedelta(hours=12),
                "1", 5,
            ),
        ),
        operator_ack=True,
    )
    economic_bytes = json.dumps(economics, sort_keys=True).encode()
    full = select_reviewed_brooks_window(
        capture.archive, start_bar_index=0, count=100, operator_ack=True,
    )
    prefix = select_reviewed_brooks_window(
        capture.archive, start_bar_index=0, count=72, operator_ack=True,
    )
    path = tmp_path / "preholdout-prefix-only.csv"
    path.write_bytes(prefix.canonical_csv_bytes)
    plan = stage20.Stage20FrozenPlan(
        protocol="BROOKS_STAGE20_PREHOLDOUT_DECISION_PROTOCOL_V1",
        original_month_zip_sha256=capture.archive.zip_sha256,
        complete_month_csv_sha256=capture.archive.csv_sha256,
        economics_report_bytes_sha256=hashlib.sha256(economic_bytes).hexdigest(),
        brooks_source_manifest_sha256=LEGACY_MANIFEST_SHA256,
        window_start_bar_index=0, complete_research_window_bars=100,
        training_end_bar=60, validation_end_bar=72,
        holdout_end_bar=100, embargo_bars=2,
    )
    plan_bytes, pin = stage20.freeze_stage20_plan(plan)
    assert hashlib.sha256(plan_bytes).hexdigest() == pin
    return {
        "capture": capture, "full_window": full, "frozen_plan": plan,
        "independently_approved_plan_sha256": pin,
        "economics_report_bytes": economic_bytes,
        "preholdout_csv_path": path,
        "original_brooks_source": _SOURCE,
        "archive_as_of_utc": datetime.now(UTC),
        "operator_ack": True,
    }


def test_real_frozen_brooks_train_validation_only_no_holdout(tmp_path, monkeypatch):
    assert _SOURCE.is_dir()
    args = _prepare(tmp_path, monkeypatch)
    before = args["preholdout_csv_path"].read_bytes()
    result = stage20.run_stage20_preholdout(**args)
    assert result["actual_frozen_brooks_v5_executed"] is True
    assert result["training_last_closed_bar"] == 60
    assert result["validation_last_closed_bar"] == 72
    assert result["holdout_first_reserved_bar"] == 75
    assert result["holdout_last_reserved_bar"] == 100
    assert result["train_decision"] in ("NO_SIGNAL", "LONG", "SHORT")
    assert result["validation_decision"] in ("NO_SIGNAL", "LONG", "SHORT")
    assert result["strategy_refit_or_selection_performed"] is False
    assert result["holdout_engine_evaluation_performed"] is False
    assert result["holdout_outcome_used_for_model_selection"] is False
    assert result["independent_plan_precommitment_attested"] is False
    assert result["pristine_prospective_oos_verified"] is False
    assert result["economic_trade_pnl_calculated"] is False
    assert result["live_authorized"] is False
    assert result["blockers"]
    assert args["preholdout_csv_path"].read_bytes() == before
    assert not list(tmp_path.rglob("*.sqlite"))
    assert stage20.run_stage20_preholdout(**args) == result


@pytest.mark.parametrize("changes", [
    {"training_end_bar": 59},
    {"validation_end_bar": 62},
    {"holdout_end_bar": 101},
    {"embargo_bars": 0},
    {"window_start_bar_index": -1},
    {"brooks_source_manifest_sha256": "f" * 64},
])
def test_invalid_or_unfrozen_plan_is_refused(changes):
    plan = stage20.Stage20FrozenPlan(
        protocol="BROOKS_STAGE20_PREHOLDOUT_DECISION_PROTOCOL_V1",
        original_month_zip_sha256="1"*64,
        complete_month_csv_sha256="2"*64,
        economics_report_bytes_sha256="3"*64,
        brooks_source_manifest_sha256=LEGACY_MANIFEST_SHA256,
        window_start_bar_index=0, complete_research_window_bars=100,
        training_end_bar=60, validation_end_bar=72,
        holdout_end_bar=100, embargo_bars=2,
    )
    with pytest.raises(stage20.Stage20Refused):
        stage20.freeze_stage20_plan(replace(plan, **changes))


def test_changed_plan_or_stage18_report_refused_before_brooks(tmp_path, monkeypatch):
    args = _prepare(tmp_path, monkeypatch)
    monkeypatch.setattr(
        stage20, "review_stage19_brooks_causal_preflight",
        lambda *_a, **_k: pytest.fail("Brooks worker must not run"),
    )
    args["frozen_plan"] = replace(args["frozen_plan"], validation_end_bar=73)
    with pytest.raises(stage20.Stage20Refused, match="PLAN_PIN"):
        stage20.run_stage20_preholdout(**args)
    args["frozen_plan"] = replace(args["frozen_plan"], validation_end_bar=72)
    args["economics_report_bytes"] += b" "
    with pytest.raises(stage20.Stage20Refused, match="CAPTURE_ECONOMICS"):
        stage20.run_stage20_preholdout(**args)


def test_post_validation_price_bytes_are_not_in_prefix(tmp_path, monkeypatch):
    args = _prepare(tmp_path, monkeypatch)
    assert args["full_window"].count == 100
    assert len(args["preholdout_csv_path"].read_bytes().splitlines()) == 73
    from naseri_markets import brooks_walk_forward_preholdout_stage20_v1 as mod
    original = mod.review_stage19_brooks_causal_preflight
    observed = []
    def capture_prefix(*a, **k):
        observed.append(k["window"].count)
        assert k["window_csv_path"].read_bytes().splitlines()[-1].startswith(
            b"2024-01-01T17:45:00Z,"
        )
        assert k["evaluation_cutoffs_utc"][-1] == _BEGIN + _BAR*72
        return original(*a, **k)
    monkeypatch.setattr(mod, "review_stage19_brooks_causal_preflight", capture_prefix)
    stage20.run_stage20_preholdout(**args)
    assert observed == [72]


def test_tampered_prefix_or_complete_window_refused_before_worker(tmp_path, monkeypatch):
    args = _prepare(tmp_path, monkeypatch)
    monkeypatch.setattr(
        stage20, "review_stage19_brooks_causal_preflight",
        lambda *_a, **_k: pytest.fail("worker reached on corrupted data"),
    )
    file = args["preholdout_csv_path"]
    file.write_bytes(file.read_bytes().replace(
        b",100,101,99,100,10", b",100,102,99,100,10", 1,
    ))
    with pytest.raises(stage20.Stage20Refused, match="PREFIX_BYTES"):
        stage20.run_stage20_preholdout(**args)
    prefix = select_reviewed_brooks_window(
        args["capture"].archive, start_bar_index=0, count=72, operator_ack=True,
    )
    file.write_bytes(prefix.canonical_csv_bytes)
    args["full_window"] = replace(args["full_window"], count=99)
    with pytest.raises(stage20.Stage20Refused, match="CAPTURE_ECONOMICS"):
        stage20.run_stage20_preholdout(**args)


def test_production_or_missing_ack_refused_before_execution(tmp_path, monkeypatch):
    args = _prepare(tmp_path, monkeypatch)
    monkeypatch.setattr(
        stage20, "review_stage19_brooks_causal_preflight",
        lambda *_a, **_k: pytest.fail("worker must be offline"),
    )
    args["operator_ack"] = False
    with pytest.raises(stage20.Stage20Refused, match="NONPRODUCTION"):
        stage20.run_stage20_preholdout(**args)
    args["operator_ack"] = True
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(stage20.Stage20Refused, match="NONPRODUCTION"):
        stage20.run_stage20_preholdout(**args)
