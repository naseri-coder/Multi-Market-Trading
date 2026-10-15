"""Broker-free Stage21 hypothetical lifecycle tests, all using SYNTHETIC prices."""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from naseri_markets import brooks_causal_lifecycle_stage21_preflight_v1 as study
from naseri_markets.futures_economic_scenario_stage16_v1 import FundingMarkScenario

BEGIN = datetime(2024, 1, 1, tzinfo=UTC)
STEP = timedelta(minutes=15)
SOURCE = Path(study.__file__).resolve().parents[1] / "production_source"


@pytest.fixture(autouse=True)
def environment(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def metadata():
    raw = json.dumps({
        "schema_version": 1, "provider_claim": "binance_usdm_operator_claim",
        "symbol": "BTCUSDT", "contract_kind": "linear_perpetual",
        "settle_currency": "USDT", "base_units_per_contract": "1",
        "price_tick": "1", "quantity_step": "1",
        "taker_fee_fraction": "0.0004",
        "worst_slippage_fraction": "0.001",
        "maintenance_margin_fraction": "0.005",
        "source_metadata_sha256": "a"*64,
    }, sort_keys=True, separators=(",", ":")).encode()
    return raw, hashlib.sha256(raw).hexdigest()


def bar(i, *, opening="100", high="101", low="99", close="100"):
    return {
        "open_time": (BEGIN + STEP*i).isoformat(),
        "close_time": (BEGIN + STEP*(i+1)).isoformat(),
        "open": opening, "high": high, "low": low, "close": close,
        "volume": "10",
    }


def replay():
    bars = [bar(i) for i in range(60)]
    raw = {
        "schema_version": 1, "origin": "replay", "market": "crypto",
        "provider": "binance_replay", "exchange": "binance",
        "market_type": "futures", "symbol": "BTCUSDT",
        "quote_currency": "USDT", "timezone": "UTC",
        "timeframe": "15m", "candles": bars,
    }
    return json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()


def geometry(direction="LONG", entry="100", stop="95", target="105"):
    return study.FrozenGeometry(
        decision=direction, input_sha256="1"*64,
        source_manifest_sha256="2"*64, snapshot_sha256="3"*64,
        decision_evidence_sha256="4"*64,
        signal_close_at=BEGIN + 60*STEP,
        entry=entry, stop=stop, targets=(target,),
    )


def future(*values):
    output = []
    for i, item in enumerate(values):
        output.append({
            "open_time": BEGIN + (60+i)*STEP,
            "close_time": BEGIN + (61+i)*STEP,
            "open": study._decimal(item[0]), "high": study._decimal(item[1]),
            "low": study._decimal(item[2]), "close": study._decimal(item[3]),
            "volume": study._decimal("10"),
        })
    return tuple(output)


def simulate(g, bars, funding_times=(), events=()):
    meta, pin = metadata()
    return study._model_next_open(
        g, future=bars, quantity="1", metadata=meta, metadata_sha256=pin,
        expected_funding_instants=funding_times, funding_events=events,
    )


@pytest.mark.parametrize("direction,stop,target", [
    ("LONG", "95", "105"), ("SHORT", "105", "95"),
])
def test_worst_case_same_bar_stop_and_target_never_books_target(direction, stop, target):
    result = simulate(
        geometry(direction, stop=stop, target=target),
        future(("100", "107", "93", "100")),
    )
    assert result["state"] == "HYPOTHETICAL_CLOSED_POSITION"
    assert result["exit_reason"] == "STOP_PRIORITY_AMBIGUOUS_BAR"
    assert result["intrabar_stop_target_ambiguity"] is True
    assert result["exit_reference_price"] == stop
    assert float(result["net_scenario_quote"]) < 0
    assert result["broker_fill_verified"] is False
    assert result["actual_signal_execution_parity_verified"] is False


def test_adverse_open_gap_of_second_candle_exits_at_worse_gap_price():
    result = simulate(
        geometry(),
        future(("100", "102", "98", "100"), ("90", "92", "88", "89")),
    )
    assert result["exit_reason"] == "ADVERSE_OPEN_GAP_TO_STOP"
    assert result["exit_reference_price"] == "90"
    assert float(result["net_scenario_quote"]) < 0


def test_favourable_open_gap_never_awards_more_than_first_target():
    result = simulate(
        geometry(),
        future(("100", "102", "98", "100"), ("110", "112", "109", "111")),
    )
    assert result["exit_reason"] == "FIRST_TARGET_CAPPED"
    assert result["exit_reference_price"] == "105"


def test_signal_far_from_next_open_does_not_fill():
    outcome = simulate(geometry(), future(("110", "111", "109", "110")))
    assert outcome["state"] == "MODEL_REFUSED_GAPPED_OR_DEVIATED_ENTRY"
    assert outcome["net_scenario_quote"] is None


def test_stop_invalid_at_next_open_does_not_fill():
    outcome = simulate(geometry(), future(("94", "100", "92", "98")))
    assert outcome["state"] == "MODEL_REFUSED_GAPPED_OR_DEVIATED_ENTRY"


def test_known_funding_settlement_requires_matching_event():
    bars = future(
        ("100", "102", "98", "100"),
        ("100", "102", "98", "100"),
        ("100", "102", "98", "100"),
        ("100", "102", "98", "100"),
    )
    funding = (BEGIN + timedelta(hours=16),)
    with pytest.raises(study.Stage21StudyRefused, match="FUNDING"):
        simulate(geometry(), bars, funding_times=funding)
    event = FundingMarkScenario(
        at=funding[0], funding_rate="0.0001", referenced_mark_price="100",
    )
    modeled = simulate(geometry(), bars, funding_times=funding, events=(event,))
    assert modeled["funding_event_count"] == 1
    assert modeled["exit_reason"] == "MAX_HORIZON_UNOBSERVED_STOP_OR_TARGET"


def test_duplicate_future_bar_detected_and_bounded():
    raw = replay()
    identical = bar(60)
    with pytest.raises(study.Stage21StudyRefused, match="NONCAUSAL"):
        study._validated_continuation(
            raw, (identical, identical), BEGIN + 60*STEP
        )
    with pytest.raises(study.Stage21StudyRefused, match="BOUNDED"):
        study._validated_continuation(
            raw, tuple(bar(60+i) for i in range(33)), BEGIN + 60*STEP
        )


def test_no_signal_requires_absence_of_fabricated_targets():
    from dataclasses import replace
    normal = replace(geometry(), decision="NO_SIGNAL", entry=None,
                     stop=None, targets=())
    outcome = simulate(normal, future(("100", "101", "99", "100")))
    assert outcome["state"] == "NO_SIGNAL"
    assert outcome["hypothetical_order"] is False
    with pytest.raises(study.Stage21StudyRefused, match="GEOMETRY"):
        simulate(replace(normal, targets=("105",)),
                 future(("100", "101", "99", "100")))


def test_actual_frozen_worker_used_once_before_replay_future(monkeypatch):
    assert SOURCE.is_dir()
    observed = []
    original_worker = study._worker
    def checked_worker(root, input_data, timeout):
        observed.append(json.loads(input_data)["candles"][-1]["close_time"])
        assert len(json.loads(input_data)["candles"]) == 60
        return original_worker(root, input_data, timeout)
    monkeypatch.setattr(study, "_worker", checked_worker)
    meta, pin = metadata()
    result = study.run_stage21_brooks_lifecycle_preflight(
        original_replay_bytes=replay(), legacy_source=SOURCE,
        post_signal_closed_candles=tuple(bar(i) for i in range(60, 64)),
        metadata_bytes=meta, metadata_sha256=pin, quantity_contracts="1",
        expected_funding_instants=(), funding_mark_events=(),
        operator_ack=True,
    )
    assert len(observed) == 1
    assert result["actual_frozen_brooks_decision"] in ("NO_SIGNAL", "LONG", "SHORT")
    assert result["source_manifest_sha256"]
    assert result["decision_evidence_sha256"]
    assert result["hypothetical_trade"]["broker_fill_verified"] is False
    assert result["paper_trading_enabled"] is False
    assert result["live_trading_authorized"] is False
    assert result["actual_realized_pnl"] is False
    assert result["production_modified"] is False


def test_production_fence_before_any_worker(monkeypatch):
    monkeypatch.setattr(
        study, "_source", lambda *_a, **_k: pytest.fail("worker reached"),
    )
    meta, pin = metadata()
    kw = dict(original_replay_bytes=replay(), legacy_source=SOURCE,
              post_signal_closed_candles=(bar(60),),
              metadata_bytes=meta, metadata_sha256=pin,
              quantity_contracts="1", expected_funding_instants=(),
              funding_mark_events=(), operator_ack=False)
    with pytest.raises(study.Stage21StudyRefused, match="OFFLINE"):
        study.run_stage21_brooks_lifecycle_preflight(**kw)
    kw["operator_ack"] = True
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(study.Stage21StudyRefused, match="OFFLINE"):
        study.run_stage21_brooks_lifecycle_preflight(**kw)
