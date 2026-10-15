"""Executable Stage-13 fixture walk-forward, not retrospective PAPER outcome slicing."""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from naseri_markets.contracts import Instrument, Market
from naseri_markets.core_api_v1 import CoreEventType, DataOrigin
from naseri_markets.executable_walk_forward_stage13_v1 import (
    ExecutableWalkForwardRefused, FrozenExecutionPlan, execute_frozen_walk_forward,
)
from naseri_markets.historical_data_loader_a1 import (
    HistoricalDataRefused, HistoricalFileSpec,
)
from naseri_markets.market_data_engine_v1 import (
    FeedDefinition, PriceBasis, VolumeSemantics,
)

D = Decimal
START = datetime(2026, 10, 13, tzinfo=UTC)
CYCLE = (
    ("100", "101", "99", "100"),
    ("100", "104", "100", "103"),
    ("103", "107", "101", "102"),
    ("102", "103", "99", "101"),
)
HEADER = b"open_at,close_at,open,high,low,close,volume\n"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def fixture(tmp_path: Path, *, fee="2", slip="3", no_signal=False, bar_count=24):
    path = tmp_path / "stage13_data.csv"
    raw = [HEADER]
    for i in range(bar_count):
        candle = CYCLE[i % len(CYCLE)] if not no_signal else (
            "100", "101", "99", "100",
        )
        opened = START + timedelta(minutes=15*i)
        closed = opened + timedelta(minutes=15)
        raw.append((
            f"{opened.isoformat()},{closed.isoformat()},"
            f"{','.join(candle)},10\n"
        ).encode())
    payload = b"".join(raw)
    path.write_bytes(payload)
    sha = hashlib.sha256(payload).hexdigest()
    feed = FeedDefinition(
        "stage13_feed", Instrument(
            Market.CRYPTO, "fixture_venue", "ABCUSDT", "UTC", "USDT",
        ),
        "15m", CoreEventType.CLOSED_CANDLE, DataOrigin.REPLAY,
        "hist_" + sha[:40], PriceBasis.TRADE, VolumeSemantics.TRADED,
        max_latency_seconds=120,
    )
    spec = HistoricalFileSpec(feed, sha, 5)
    end = START + timedelta(minutes=15*bar_count)
    receipt = {
        "schema_version": 1,
        "dataset_sha256": sha, "feed_id": feed.feed_id, "market": "crypto",
        "provider_claim": "fixture_venue", "symbol": "ABCUSDT",
        "timezone": "UTC", "quote_currency": "USDT",
        "timeframe": "15m", "event": "closed_candle",
        "price_basis": "trade", "volume_semantics": "traded",
        "contract_kind": "spot",
        "session_policy": "continuous_utc_operator_assertion",
        "capture_method": "operator_supplied_archive",
        "availability_lag_seconds": 5,
        "expected_rows": bar_count,
        "window_start_utc": START.isoformat(),
        "window_end_utc": end.isoformat(),
        "retrieved_at_utc": (end + timedelta(seconds=30)).isoformat(),
    }
    received = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
    digest = hashlib.sha256(received).hexdigest()
    plan = FrozenExecutionPlan(
        START + timedelta(minutes=15*8),
        START + timedelta(minutes=15*16),
        end, end + timedelta(minutes=1),
        2, 1, D(fee), D(slip), D("1000"), D("0.1"), 1,
    )
    return path, spec, received, digest, plan


def run(all_parts, **kwargs):
    path, spec, receipt, digest, plan = all_parts
    return execute_frozen_walk_forward(
        path, spec, receipt_bytes=receipt, trusted_receipt_sha256=digest,
        plan=kwargs.get("plan", plan), operator_ack=kwargs.get("ack", True),
    )


def test_real_evaluation_runs_on_expanding_training_validation_and_holdout(tmp_path):
    all_parts = fixture(tmp_path)
    before = all_parts[0].read_bytes()
    a = run(all_parts)
    b = run(all_parts)
    assert a == b
    assert a["verdict"] == "EXECUTED_SYNTHETIC_CORE_DESCRIPTIVE_ONLY"
    assert a["blockers"] == []
    assert len(a["folds"]) == 2
    assert [f["test"]["closed"] for f in a["folds"]] == [1, 1]
    assert [f["train"]["closed"] for f in a["folds"]] == [2, 3]
    assert a["reserved_final_holdout"]["closed"] == 2
    assert all(f["test"]["core_evaluations"] == 4 for f in a["folds"])
    assert all(f["test"]["filled"] == 1 for f in a["folds"])
    assert a["reserved_final_holdout"]["core_evaluations"] == 8
    assert [f["test"]["pending_unfilled_at_end"] for f in a["folds"]] == [0, 0]
    assert all(f["train"]["core_evaluations"] > 2 for f in a["folds"])
    assert len(a["evidence_sha256"]) == 64
    assert a["core_id"] == "fixture.contract.check"
    assert all(a[k] is False for k in (
        "strategy_parameters_fitted", "historical_archival_provider_verified",
        "independent_pit_custody_verified",
        "protocol_independently_frozen_before_results",
        "walk_forward_strategy_refit_per_fold",
        "sample_significance_established", "profitability_proven",
        "broker_order_sent", "telegram_sent", "live_authorized",
    ))
    assert all_parts[0].read_bytes() == before


def test_cost_and_execution_slippage_reduce_modeled_outcomes(tmp_path):
    no_cost = fixture(tmp_path, fee="0", slip="0")
    cheap = run(no_cost)
    costly = run(fixture(tmp_path, fee="5", slip="10"))
    for fold_no in range(2):
        c = cheap["folds"][fold_no]["test"]
        d = costly["folds"][fold_no]["test"]
        assert c["closed"] == d["closed"] == 1
        assert D(c["net_pnl"]) > D(d["net_pnl"])
        assert D(c["mean_net_r"]) > D(d["mean_net_r"])
        assert D(d["stress_2x_fees_net_pnl"]) < D(d["net_pnl"])
        assert D(c["modeled_fees"]) == 0
        assert D(d["modeled_fees"]) > 0
    assert cheap["evidence_sha256"] != costly["evidence_sha256"]


def test_insufficient_eligible_trades_block_instead_of_claiming_edge(tmp_path):
    all_parts = fixture(tmp_path, no_signal=True)
    result = run(all_parts)
    assert "INSUFFICIENT_CLOSED_TRADES" in " ".join(result["blockers"])
    assert result["verdict"] == "EXECUTED_WITH_UNRESOLVED_EVIDENCE_BLOCKERS"
    assert result["reserved_final_holdout"]["closed"] == 0
    assert result["reserved_final_holdout"]["mean_net_r"] is None


def test_short_segments_purge_and_missing_fold_boundary_fail_closed(tmp_path):
    all_parts = fixture(tmp_path)
    plan = all_parts[-1]
    with pytest.raises(ExecutableWalkForwardRefused, match="EMBARGO_OR_FOLD"):
        run(all_parts, plan=replace(plan, embargo_bars=8))
    with pytest.raises(ExecutableWalkForwardRefused, match="FOLD_BOUNDARY"):
        run(all_parts, plan=replace(
            plan, training_end=plan.training_end + timedelta(seconds=1),
        ))
    with pytest.raises(ExecutableWalkForwardRefused, match="FOLDS_REQUIRE_WHOLE"):
        run(all_parts, plan=replace(
            plan, validation_end=plan.validation_end - timedelta(minutes=15),
        ))


def test_past_fold_cannot_receive_future_data_and_bad_archival_time_refused(tmp_path):
    parts = fixture(tmp_path)
    path, spec, receipt, _digest, plan = parts
    wrong = json.loads(receipt)
    wrong["retrieved_at_utc"] = (
        plan.archive_as_of_utc + timedelta(seconds=10)
    ).isoformat()
    payload = json.dumps(wrong, sort_keys=True, separators=(",", ":")).encode()
    with pytest.raises(HistoricalDataRefused, match="WINDOW_OR_ACQUISITION"):
        execute_frozen_walk_forward(
            path, spec, receipt_bytes=payload,
            trusted_receipt_sha256=hashlib.sha256(payload).hexdigest(),
            plan=plan, operator_ack=True,
        )
    # Mutating a future bar changes the full-file pinned digest and refuses;
    # the temporal evaluator cannot rewrite, unpin or retroactively fit.
    path.write_bytes(path.read_bytes().replace(b"102,103,99,101", b"102,103,99,100"))
    with pytest.raises(HistoricalDataRefused, match="SOURCE_HASH_MISMATCH"):
        run(parts)


def test_real_archive_can_only_be_available_after_its_final_bar(tmp_path):
    parts = fixture(tmp_path)
    plan = parts[-1]
    with pytest.raises(ExecutableWalkForwardRefused, match="INVALID_FROZEN_FOLDS"):
        run(parts, plan=replace(plan, archive_as_of_utc=plan.study_end))
    assert run(parts)["historical_archival_provider_verified"] is False


@pytest.mark.parametrize("fee,slip,frac", [
    ("NaN", "1", "0.1"), ("1", "-1", "0.1"),
    ("1000", "0", "0.1"), ("1", "1", "1.1"), ("1", "1", "0"),
])
def test_invalid_economic_parameters_fail_before_execution(tmp_path, fee, slip, frac):
    parts = fixture(tmp_path)
    with pytest.raises(ExecutableWalkForwardRefused):
        replace(parts[-1], fee_bps_per_side=D(fee),
                slippage_bps_per_side=D(slip), notional_fraction=D(frac))


def test_nonproduction_and_explicit_ack_required(tmp_path, monkeypatch):
    parts = fixture(tmp_path)
    with pytest.raises(ExecutableWalkForwardRefused, match="NONPRODUCTION"):
        run(parts, ack=False)
    monkeypatch.delenv("MMT_NONPRODUCTION")
    with pytest.raises(ExecutableWalkForwardRefused, match="NONPRODUCTION"):
        run(parts)
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(ExecutableWalkForwardRefused, match="NONPRODUCTION"):
        run(parts)


def test_no_authenticated_core_or_hidden_signals_are_inferred(tmp_path):
    parts = fixture(tmp_path)
    result = run(parts)
    assert result["strategy_parameters_fitted"] is False
    assert result["funding_mark_contract_economics_verified"] is False
    assert result["profitability_proven"] is False
    assert result["core_version"] == "1.0.0"
    for fold in result["folds"]:
        assert fold["train_cutoff_utc"] < fold["test_start_utc"]
