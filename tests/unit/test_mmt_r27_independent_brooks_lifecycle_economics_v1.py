"""R27 shadow-verified Brooks decisions vs modeled stops, targets, ticks and costs.

These synthetic scenarios do NOT represent actual historical fills or OOS.
One dedicated smoke really invokes the original frozen V5 worker twice.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from naseri_markets import brooks_causal_lifecycle_stage21_preflight_v1 as stage21
from naseri_markets import brooks_independent_lifecycle_economics_mmt_r27_v1 as r27
from naseri_markets.brooks_replay import LEGACY_MANIFEST_SHA256
from naseri_markets.futures_economic_scenario_stage16_v1 import FundingMarkScenario

FIRST = datetime(2024, 1, 1, tzinfo=UTC)
STEP = timedelta(minutes=15)
FROZEN = Path(stage21.__file__).resolve().parents[1] / "production_source"


@pytest.fixture(autouse=True)
def research_only(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def _canon(v):
    return json.dumps(
        v, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _meta(*, taker="0.0004", slip="0.001", tick="1"):
    raw = _canon({
        "schema_version": 1, "provider_claim": "binance_usdm_operator_claim",
        "symbol": "BTCUSDT", "contract_kind": "linear_perpetual",
        "settle_currency": "USDT", "base_units_per_contract": "1",
        "price_tick": tick, "quantity_step": "1",
        "taker_fee_fraction": taker, "worst_slippage_fraction": slip,
        "maintenance_margin_fraction": "0.005",
        "source_metadata_sha256": "a"*64,
    })
    return raw, _sha(raw)


def _bar(index, prices=("100", "101", "99", "100")):
    opened = FIRST + index*STEP
    return {
        "open_time": opened.isoformat(),
        "close_time": (opened+STEP).isoformat(),
        "open": prices[0], "high": prices[1], "low": prices[2],
        "close": prices[3], "volume": "10",
    }


def _replay():
    return _canon({
        "schema_version": 1, "origin": "replay", "market": "crypto",
        "provider": "binance_replay", "exchange": "binance",
        "market_type": "futures", "symbol": "BTCUSDT",
        "quote_currency": "USDT", "timezone": "UTC",
        "timeframe": "15m", "candles": [_bar(i) for i in range(60)],
    })


def _geometry(side="LONG"):
    if side == "NO_SIGNAL":
        entry, stop, targets = None, None, ()
    elif side == "LONG":
        entry, stop, targets = "100", "95", ("105",)
    else:
        entry, stop, targets = "100", "105", ("95",)
    return stage21.FrozenGeometry(
        decision=side,
        input_sha256=_sha(_replay()),
        source_manifest_sha256=LEGACY_MANIFEST_SHA256,
        snapshot_sha256="b"*64,
        decision_evidence_sha256="c"*64,
        signal_close_at=FIRST + 60*STEP,
        entry=entry, stop=stop, targets=targets,
    )


def _evidence(
    monkeypatch, *, side="LONG", prices=(("100", "102", "98", "100"),),
    funding=(), metadata=None,
):
    replay = _replay()
    future = tuple(_bar(60+i, p) for i, p in enumerate(prices))
    geometry = _geometry(side)
    normalized = stage21._validated_continuation(
        replay, future, geometry.signal_close_at,
    )
    meta, pin = metadata or _meta()
    instants = tuple(event.at for event in funding)
    trade = stage21._model_next_open(
        geometry, future=normalized, quantity="1", metadata=meta,
        metadata_sha256=pin, expected_funding_instants=instants,
        funding_events=tuple(funding),
    )
    assert trade["broker_fill_verified"] is False
    report = {
        "stage": "STAGE21_BROOKS_CAUSAL_LIFECYCLE_PREPARATION_V1",
        "status": "ACTUAL_FROZEN_DECISION_HYPOTHETICAL_TRADE_MODEL_ONLY",
        "source_manifest_sha256": LEGACY_MANIFEST_SHA256,
        "historical_snapshot_sha256": geometry.snapshot_sha256,
        "decision_evidence_sha256": geometry.decision_evidence_sha256,
        "decision_input_sha256": _sha(replay),
        "future_input_sha256": _sha(_canon(future)),
        "decision_cutoff_utc": geometry.signal_close_at.isoformat(),
        "actual_frozen_brooks_decision": geometry.decision,
        "hypothetical_trade": trade,
        "independent_dataset_archive_authentication": False,
        "exact_contract_fee_and_mark_verified": False,
        "prospective_holdout_untouched_attested": False,
        "real_brooks_strategy_execution_parity": False,
        "actual_realized_pnl": False,
        "paper_trading_enabled": False,
        "live_trading_authorized": False,
        "network_or_telegram_used": False,
        "production_modified": False,
    }
    report["report_sha256"] = _sha(_canon(report))
    # This fake frozen worker belongs to SYNTHETIC tests only. A separate
    # real-worker E2E case below exercises the original code twice.
    monkeypatch.setattr(r27, "_source", lambda *_a, **_kw: geometry)
    return {
        "original_stage21a_report_bytes": _canon(report),
        "original_closed_bar_replay_bytes": replay,
        "frozen_source": FROZEN,
        "later_closed_candles": future,
        "contract_metadata_bytes": meta,
        "contract_metadata_sha256": pin,
        "quantity_contracts": "1",
        "expected_funding_instants": instants,
        "funding_mark_events": tuple(funding),
        "operator_ack": True,
    }


def _check(data):
    return r27.review_r27_independent_geometry_cost_parity(**data)


@pytest.mark.parametrize("side,prices,reason", [
    ("LONG", (("100", "106", "98", "101"),), "FIRST_TARGET_CAPPED"),
    ("SHORT", (("100", "102", "94", "96"),), "FIRST_TARGET_CAPPED"),
    ("LONG", (("100", "107", "93", "100"),), "STOP_PRIORITY_AMBIGUOUS_BAR"),
    ("SHORT", (("100", "107", "93", "100"),), "STOP_PRIORITY_AMBIGUOUS_BAR"),
    ("LONG", (("100", "102", "98", "100"),
              ("90", "92", "88", "89")), "ADVERSE_OPEN_GAP_TO_STOP"),
    ("SHORT", (("100", "102", "98", "100"),
               ("110", "112", "108", "111")), "ADVERSE_OPEN_GAP_TO_STOP"),
    ("LONG", (("100", "102", "98", "100"),
              ("100", "102", "98", "100")), "MAX_HORIZON_UNOBSERVED_STOP_OR_TARGET"),
])
def test_shadow_reproduces_stage21a_exit_priority_and_adverse_ticks(
    monkeypatch, side, prices, reason,
):
    data = _evidence(monkeypatch, side=side, prices=prices)
    result = _check(data)
    assert result["hypothetical_exit_reason"] == reason
    assert result["actual_frozen_worker_rerun_and_decision_hash_equal"] is True
    assert result["hypothetical_order_path_recomputed_separately"] is True
    assert result["independently_recalculated_modeled_cashflows"] is not None
    assert result["broker_actual_order_type_and_fill_verified"] is False
    assert result["original_brooks_real_exit_execution_parity_verified"] is False
    assert result["prospective_oos_edge_established"] is False


def test_funding_and_fee_accounting_independently_recomputed(monkeypatch):
    event = FundingMarkScenario(
        at=FIRST+62*STEP, funding_rate="0.0001",
        referenced_mark_price="100",
    )
    data = _evidence(
        monkeypatch,
        prices=tuple(("100", "102", "98", "100") for _ in range(4)),
        funding=(event,),
    )
    audit = _check(data)
    sums = audit["independently_recalculated_modeled_cashflows"]
    assert sums["gross_quote"] == "0"
    assert sums["funding_cashflow_quote"] == "-0.0100"
    assert sums["settled_funding_events"] == 1
    assert sums["taker_fees_quote"] == "0.0800"
    assert sums["adverse_slippage_quote"] == "0.200"
    assert sums["net_scenario_quote"] == "-0.2900"
    assert audit["actual_account_fee_tier_and_funding_settlement_verified"] is False


def test_no_signal_and_gap_refusal_never_certify_execution(monkeypatch):
    no_signal = _evidence(monkeypatch, side="NO_SIGNAL")
    assert _check(no_signal)["hypothetical_state"] == "NO_SIGNAL"
    gap = _evidence(
        monkeypatch, prices=(("110", "111", "109", "110"),),
    )
    assert _check(gap)["hypothetical_state"] == (
        "MODEL_REFUSED_GAPPED_OR_DEVIATED_ENTRY"
    )


@pytest.mark.parametrize("field,mutation", [
    ("entry_reference_price", "103"),
    ("exit_reference_price", "104"),
    ("quantity_contracts", "2"),
    ("exit_reason", "FIRST_TARGET_CAPPED"),
    ("net_scenario_quote", "999999.99"),
    ("funding_event_count", 2),
    ("economic_receipt_sha256", "f"*64),
    ("intrabar_stop_target_ambiguity", True),
    ("entry_time", "2024-01-02T00:00:00+00:00"),
])
def test_resigned_but_tampered_modeled_receipts_refused(
    monkeypatch, field, mutation,
):
    data = _evidence(
        monkeypatch, prices=(("100", "101", "99", "100"),),
    )
    original = json.loads(data["original_stage21a_report_bytes"])
    original["hypothetical_trade"][field] = mutation
    original.pop("report_sha256")
    original["report_sha256"] = _sha(_canon(original))
    data["original_stage21a_report_bytes"] = _canon(original)
    with pytest.raises(ValueError):
        _check(data)


def test_genuine_causal_input_binding_rejects_changed_future_bars(monkeypatch):
    data = _evidence(monkeypatch)
    data["later_closed_candles"] = (_bar(60, ("100","104","98","101")),)
    with pytest.raises(r27.R27IndependentParityRefused,
                       match="FROZEN_DECISION_DIFFERENCE"):
        _check(data)


def test_fee_tier_substitution_and_missing_funding_refused(monkeypatch):
    data = _evidence(monkeypatch)
    amended, amended_sha = _meta(taker="0.009")
    data["contract_metadata_bytes"] = amended
    data["contract_metadata_sha256"] = amended_sha
    with pytest.raises(r27.R27IndependentParityRefused,
                       match="CASHFLOW_MISMATCH|ECONOMIC_RECEIPT_MISMATCH"):
        _check(data)
    funding_event = FundingMarkScenario(
        at=FIRST + 62*STEP, funding_rate="0.0001",
        referenced_mark_price="100",
    )
    data = _evidence(
        monkeypatch,
        prices=tuple(("100","102","98","100") for _ in range(4)),
        funding=(funding_event,),
    )
    data["funding_mark_events"] = ()
    with pytest.raises(r27.R27IndependentParityRefused, match="FUNDING"):
        _check(data)


def test_nonproduction_fence_before_any_frozen_engine(monkeypatch):
    data = _evidence(monkeypatch)
    monkeypatch.setattr(
        r27, "_source", lambda *_a, **_kw: pytest.fail("unexpected worker"),
    )
    data["operator_ack"] = False
    with pytest.raises(r27.R27IndependentParityRefused, match="NONPRODUCTION"):
        _check(data)
    data["operator_ack"] = True
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(r27.R27IndependentParityRefused, match="NONPRODUCTION"):
        _check(data)


def test_actual_frozen_brooks_v5_worker_executed_twice_without_orders(
    monkeypatch,
):
    # This is a GENUINE frozen worker smoke on synthetic CLOSED candles;
    # it does not assert that any broker/exchange filled an order.
    monkeypatch.setattr(r27, "_source", stage21._source)
    meta, pin = _meta()
    result = r27.run_r27_brooks_two_pass_model_crosscheck(
        original_closed_bar_replay_bytes=_replay(),
        frozen_source=FROZEN,
        later_closed_candles=tuple(_bar(i) for i in range(60, 64)),
        contract_metadata_bytes=meta,
        contract_metadata_sha256=pin,
        quantity_contracts="1",
        expected_funding_instants=(),
        funding_mark_events=(),
        operator_ack=True,
    )
    audit = result["r27_independent_review"]
    assert audit["actual_frozen_worker_rerun_and_decision_hash_equal"] is True
    assert audit["broker_actual_order_type_and_fill_verified"] is False
    assert audit["paper_connected_or_live_enabled"] is False
    assert audit["realized_pnl_evidenced"] is False
    assert result["stage21a_original_report"]["actual_realized_pnl"] is False
