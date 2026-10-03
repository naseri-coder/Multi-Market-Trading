import asyncio
import dataclasses
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest
from app.modules.ai_council.agents import RiskAgent, _verified_v5_execution_geometry
from app.modules.ai_council.service import AICouncilService
from app.modules.brooks_core.books_full_engine import BrooksTrilogyFullCoreEngine
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.market_data.entities import Candle, MarketSnapshot
from app.modules.paper_runtime.entities import PaperSignalCandidate
from app.modules.risk_engine.service import RiskEngineService
from app.modules.signal_automation.entities import (
    BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1,
    FINAL_BROOKS_HP_SEMANTIC_COHORT_ID,
)
from app.modules.signal_gate.service import SignalGateService
from app.modules.signal_intelligence.probability import HistoricalCase, HistoricalProbabilityEngine
from app.modules.signal_intelligence.service import SignalIntelligenceService


def candidate_from_fixture(*, mirror=False):
    raw = json.loads((Path(__file__).parent / "fixtures/v5_council_geometry.json").read_text())
    bars = []
    for row in raw:
        values = {k: Decimal(row[k]) for k in ("open", "high", "low", "close", "volume")}
        # Deterministic synthetic price transformation, independent of market history.
        if mirror:
            values.update(
                open=Decimal("2000") - values["open"],
                high=Decimal("2000") - values["low"],
                low=Decimal("2000") - values["high"],
                close=Decimal("2000") - values["close"],
            )
        bars.append(
            Candle(
                open_time=datetime.fromisoformat(row["open_time"]),
                close_time=datetime.fromisoformat(row["close_time"]),
                **values,
            )
        )
    snapshot = MarketSnapshot(
        "binance", "futures", "BNBUSDT", "15m", tuple(bars), bars[-1].close_time
    )
    result = asyncio.run(
        BrooksTrilogyFullCoreEngine(
            policy=BrooksFullCorePolicy(enable_trade_decisions=True)
        ).evaluate(snapshot)
    )
    assert result.decision in {"LONG", "SHORT"}
    fields = {
        f.name: getattr(result, f.name)
        for f in dataclasses.fields(PaperSignalCandidate)
        if hasattr(result, f.name)
    }
    fields.update(
        source_signal_id="TEST_ONLY",
        symbol=snapshot.symbol,
        timeframe=snapshot.timeframe,
        direction=result.decision,
        exchange=snapshot.exchange,
        market_type=snapshot.market_type,
        market_snapshot_id=snapshot.snapshot_id,
        market_snapshot_hash=snapshot.snapshot_hash,
        chart_path="TEST_NO_PUBLICATION",
        snapshot=snapshot,
    )
    return PaperSignalCandidate(**fields)


@pytest.mark.parametrize("mirror", [False, True])
def test_exact_v5_single_target_and_capped_stop_pass_council(mirror):
    candidate = candidate_from_fixture(mirror=mirror)
    assert len(candidate.targets) == 1
    bar = candidate.snapshot.candles[-1]
    assert bar.low < candidate.stop_loss < bar.high
    assessment = RiskAgent().evaluate(candidate)
    assert assessment.approved
    assert assessment.metadata["v5_geometry_verified"]
    assert AICouncilService().evaluate(candidate).approved


@pytest.mark.parametrize(
    "field", ["entry_price", "stop_loss", "targets", "configuration_version", "engine_version"]
)
def test_modified_or_unproven_geometry_is_rejected(field):
    candidate = candidate_from_fixture()
    values = {
        "entry_price": candidate.entry_price + Decimal("0.001"),
        "stop_loss": candidate.stop_loss + Decimal("0.001"),
        "targets": (candidate.targets[0] + Decimal("0.001"),),
        "configuration_version": "unverified",
        "engine_version": "legacy",
    }
    changed = dataclasses.replace(candidate, **{field: values[field]})
    assert not _verified_v5_execution_geometry(changed)
    assert not RiskAgent().evaluate(changed).approved


@pytest.mark.parametrize("mirror", [False, True])
def test_synthetic_favorable_history_reaches_final_gate_without_bypass(mirror):
    candidate = dataclasses.replace(
        candidate_from_fixture(mirror=mirror), semantic_cohort_id=FINAL_BROOKS_HP_SEMANTIC_COHORT_ID
    )
    council = AICouncilService().evaluate(candidate)
    risk = RiskEngineService().evaluate(candidate)
    # Explicit synthetic all-win history: tests wiring, not actual profitability.
    cases = tuple(
        HistoricalCase(
            signal_id=i,
            setup_type=candidate.setup_type,
            timeframe=candidate.timeframe,
            direction=candidate.direction,
            structure_quality=100,
            context_quality=100,
            entry_quality=100,
            risk_feature=100,
            outcome=1,
            rule_ids=(),
            semantic_cohort_id=FINAL_BROOKS_HP_SEMANTIC_COHORT_ID,
            generation_mode="LIVE",
            symbol=candidate.symbol,
            economic_opportunity_id=f"synthetic-{i}",
            realized_r=0.2 + (i % 5) / 100,
            payoff_input_fingerprint=f"synthetic-positive-{i}",
            outcome_policy_id=BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1,
        )
        for i in range(1, 41)
    )
    probability = HistoricalProbabilityEngine(cases).assess(candidate)
    quality = SignalIntelligenceService().evaluate(
        candidate,
        ai_score=council.final_score,
        risk_score=risk.risk_score,
        council_confidence=council.confidence,
        probability=probability,
    )
    assert council.approved and risk.approved
    assert probability.readiness_state == "CALIBRATED_FAVORABLE"
    assert quality.approved
    assert SignalGateService().evaluate(quality).approved
    negative = HistoricalProbabilityEngine(
        tuple(
            dataclasses.replace(
                c,
                outcome=0,
                realized_r=-0.2,
                payoff_input_fingerprint=f"synthetic-negative-{c.signal_id}",
            )
            for c in cases
        )
    ).assess(candidate)
    rejected = SignalIntelligenceService().evaluate(
        candidate,
        ai_score=council.final_score,
        risk_score=risk.risk_score,
        council_confidence=council.confidence,
        probability=negative,
    )
    assert not rejected.approved
    assert not SignalGateService().evaluate(rejected).approved
