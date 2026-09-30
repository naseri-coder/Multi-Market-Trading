from __future__ import annotations

import json
import logging
from types import SimpleNamespace

from app.modules.brooks_runtime.coordinator import (
    _attach_risk_semantic_breakdown,
    _risk_semantic_breakdown,
    _risk_semantic_observability_payload,
)
from app.modules.risk_engine.entities import RiskAssessment
from app.modules.signal_intelligence.entities import SignalQualityAssessment


def _assessment() -> RiskAssessment:
    breakdown = {
        "risk_semantic_model": "PLAN_WEIGHTED_PRETRADE",
        "plan_reward": {
            "mode": "PLAN_WEIGHTED_PRETRADE",
            "initial_risk": "2",
            "target_plan_id": "plan-1",
            "target_plan_state": "PLANNED",
            "target_contributions": [
                {
                    "target_number": 1,
                    "target_price": "102",
                    "target_r": "1",
                    "allocation_fraction": "0.5",
                    "weighted_target_r": "0.5",
                }
            ],
            "runner_fraction": "0.5",
            "runner_objective": None,
            "runner_r": "0",
            "weighted_runner_r": "0",
            "plan_rr": "0.5",
            "runner_policy": "UNDEFINED_OBJECTIVE_ZERO_CONSERVATIVE",
        },
        "plan_rr": "0.5",
        "rr_points": "9",
        "geometry_points": "40",
        "structural_points": "15",
        "structural_validation": {
            "entry_method": "LIMIT_OR_MARKET_FADE",
            "validation_mode": "TYPED_ALTERNATIVE_EXECUTION_IDENTITY",
            "valid": True,
        },
        "total_risk_score": "64.00",
    }
    return RiskAssessment(
        risk_score=64.0, approved=False, reasons=["Risk score below threshold."],
        metadata={"threshold": 75.0, "risk_semantic_breakdown": breakdown},
    )


def _candidate() -> SimpleNamespace:
    return SimpleNamespace(
        market_snapshot_id="snap-1", economic_opportunity_id="opp-1",
        semantic_cohort_id="BROOKS_HP_SEMANTIC_COHORT_W01_W19_V1",
        symbol="BTCUSDT", timeframe="15m", setup_type="TRADING_RANGE_FADE_LONG",
        direction="LONG",
    )


def test_observability_payload_exposes_exact_bounded_risk_fields() -> None:
    assessment = _assessment()
    payload = _risk_semantic_observability_payload(_candidate(), assessment)
    assert payload == {
        "market_snapshot_id": "snap-1",
        "economic_opportunity_id": "opp-1",
        "semantic_cohort_id": "BROOKS_HP_SEMANTIC_COHORT_W01_W19_V1",
        "symbol": "BTCUSDT",
        "timeframe": "15m",
        "setup_type": "TRADING_RANGE_FADE_LONG",
        "direction": "LONG",
        "risk_score": 64.0,
        "approved": False,
        "reasons": ["Risk score below threshold."],
        "plan_rr": "0.5",
        "rr_points": "9",
        "entry_method": "LIMIT_OR_MARKET_FADE",
        "structural_validation_mode": "TYPED_ALTERNATIVE_EXECUTION_IDENTITY",
        "structural_points": "15",
        "runner_policy": "UNDEFINED_OBJECTIVE_ZERO_CONSERVATIVE",
        "weighted_runner_r": "0",
        "target_plan_state": "PLANNED",
    }
    assert "snapshot" not in payload
    assert "candles" not in payload
    json.dumps(payload, allow_nan=False)


def test_signal_quality_transport_preserves_exact_breakdown_and_existing_metadata() -> None:
    assessment = _assessment()
    quality = SignalQualityAssessment(
        final_score=80.0, confidence=0.0, quality_grade="B", approved=False,
        metadata={"existing": "preserved", "probability_calibrated": False},
    )
    original = _risk_semantic_breakdown(assessment)
    _attach_risk_semantic_breakdown(quality, assessment)
    assert quality.metadata["existing"] == "preserved"
    assert quality.metadata["probability_calibrated"] is False
    assert quality.metadata["risk_semantic_breakdown"] is original
    assert quality.metadata["risk_semantic_breakdown"] == original
    json.dumps(quality.metadata, allow_nan=False)


def test_legacy_quality_without_breakdown_remains_unchanged_and_no_fabrication() -> None:
    assessment = RiskAssessment(
        risk_score=82.0, approved=True, reasons=["Risk score passed threshold."], metadata={"threshold": 75.0}
    )
    quality = SignalQualityAssessment(
        final_score=82.0, confidence=0.5, quality_grade="B", approved=True, metadata={"legacy": True}
    )
    _attach_risk_semantic_breakdown(quality, assessment)
    assert quality.metadata == {"legacy": True}
    assert "risk_semantic_breakdown" not in quality.metadata
    assert _risk_semantic_observability_payload(_candidate(), assessment)["plan_rr"] is None


def test_transport_does_not_change_risk_decision_or_breakdown() -> None:
    assessment = _assessment()
    before = (assessment.risk_score, assessment.approved, list(assessment.reasons), json.dumps(assessment.metadata, sort_keys=True))
    quality = SignalQualityAssessment(
        final_score=80.0, confidence=0.0, quality_grade="B", approved=False, metadata={}
    )
    _ = _risk_semantic_observability_payload(_candidate(), assessment)
    _attach_risk_semantic_breakdown(quality, assessment)
    after = (assessment.risk_score, assessment.approved, list(assessment.reasons), json.dumps(assessment.metadata, sort_keys=True))
    assert after == before

def test_existing_runtime_log_event_uses_transport_payload(caplog) -> None:
    from app.modules.brooks_runtime import coordinator
    assessment = _assessment()
    payload = _risk_semantic_observability_payload(_candidate(), assessment)
    with caplog.at_level(logging.INFO, logger=coordinator.logger.name):
        coordinator.logger.info(
            "Risk Engine evaluated candidate",
            extra={"event": "risk_engine_candidate_evaluated", **payload},
        )
    record = caplog.records[-1]
    assert record.event == "risk_engine_candidate_evaluated"
    assert record.plan_rr == "0.5"
    assert record.rr_points == "9"
    assert record.entry_method == "LIMIT_OR_MARKET_FADE"
    assert record.structural_validation_mode == "TYPED_ALTERNATIVE_EXECUTION_IDENTITY"
    assert record.structural_points == "15"
    assert record.market_snapshot_id == "snap-1"

def test_signal_quality_jsonb_style_roundtrip_preserves_exact_breakdown() -> None:
    from datetime import UTC, datetime
    from decimal import Decimal

    from app.modules.signal_quality.models import SignalQualityAssessment as QualityModel
    from app.modules.signal_quality.repository import _to_record

    assessment = _assessment()
    quality = SignalQualityAssessment(
        final_score=80.0, confidence=0.0, quality_grade="B", approved=False,
        metadata={"existing": "preserved"},
    )
    _attach_risk_semantic_breakdown(quality, assessment)
    serialized = json.dumps(quality.metadata, allow_nan=False)
    reloaded = json.loads(serialized)
    model = QualityModel(
        signal_id=123,
        ai_score=Decimal("80"),
        risk_score=Decimal("64"),
        final_score=Decimal("80"),
        confidence=Decimal("0"),
        quality_grade="B",
        market_regime="TRADING_RANGE",
        gate_approved=False,
        gate_reason="test",
        extra_metadata=reloaded,
        created_at=datetime.now(UTC),
    )
    record = _to_record(model)
    assert record.metadata["existing"] == "preserved"
    assert record.metadata["risk_semantic_breakdown"] == _risk_semantic_breakdown(assessment)


def test_log_and_persisted_breakdown_fields_are_consistent() -> None:
    assessment = _assessment()
    quality = SignalQualityAssessment(
        final_score=80.0, confidence=0.0, quality_grade="B", approved=False, metadata={}
    )
    _attach_risk_semantic_breakdown(quality, assessment)
    payload = _risk_semantic_observability_payload(_candidate(), assessment)
    stored = quality.metadata["risk_semantic_breakdown"]
    structural = stored["structural_validation"]
    assert payload["plan_rr"] == stored["plan_rr"]
    assert payload["rr_points"] == stored["rr_points"]
    assert payload["entry_method"] == structural["entry_method"]
    assert payload["structural_validation_mode"] == structural["validation_mode"]
    assert payload["structural_points"] == stored["structural_points"]
