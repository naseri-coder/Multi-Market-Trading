from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.modules.brooks_core.entities import BrooksCoreDecision
from app.modules.brooks_core.mapper import to_paper_candidate
from app.modules.live_vip_runtime.service import LiveVipRuntimeService
from app.modules.market_data.entities import Candle, MarketSnapshot
from app.modules.paper_runtime.service import PaperRuntimeService
from app.modules.risk_engine.service import RiskEngineService
from app.modules.signal_automation.entities import (
    BrooksSignalImport,
    FINAL_BROOKS_HP_SEMANTIC_COHORT_ID,
)
from app.modules.signal_automation.repository import _brooks_core_typed_metadata
from app.modules.signal_gate.service import SignalGateService
from app.modules.signal_intelligence.probability import (
    HistoricalCase,
    HistoricalProbabilityEngine,
    HistoricalProbabilityRepository,
    ProbabilityAssessment,
    _MAX_NEIGHBORS,
    _MIN_BROAD,
    _MIN_EXACT,
    _MIN_FAMILY,
    _stored_semantic_cohort_id,
)
from app.modules.signal_intelligence.service import SignalIntelligenceService


FINAL = FINAL_BROOKS_HP_SEMANTIC_COHORT_ID
OTHER = "BROOKS_HP_SEMANTIC_COHORT_OTHER_V1"


def hp_candidate(
    *,
    setup: str = "FAILED_BREAKOUT_LONG",
    timeframe: str = "15m",
    direction: str = "LONG",
    cohort: str | None = FINAL,
):
    return SimpleNamespace(
        setup_type=setup,
        timeframe=timeframe,
        direction=direction,
        entry_price=D("100"),
        stop_loss=D("99") if direction == "LONG" else D("101"),
        targets=(D("101"),) if direction == "LONG" else (D("99"),),
        rule_evidence=(),
        semantic_cohort_id=cohort,
        configuration_version="same-config-does-not-prove-semantic-compatibility",
        engine_version="engine",
        rule_set_version="rules",
    )


def case(
    signal_id: int,
    *,
    setup: str = "FAILED_BREAKOUT_LONG",
    timeframe: str = "15m",
    direction: str = "LONG",
    cohort: str | None = FINAL,
    outcome: int = 1,
    quality: float = 80.0,
):
    return HistoricalCase(
        signal_id=signal_id,
        setup_type=setup,
        timeframe=timeframe,
        direction=direction,
        structure_quality=quality,
        context_quality=quality,
        entry_quality=quality,
        risk_feature=50.0,
        outcome=outcome,
        rule_ids=(),
        semantic_cohort_id=cohort,
    )


def snap():
    start = datetime(2026, 9, 18, 12, tzinfo=UTC)
    candle = Candle(
        open_time=start,
        close_time=start + timedelta(minutes=15),
        open=D("100"),
        high=D("101"),
        low=D("99"),
        close=D("100.5"),
        volume=D("10"),
    )
    return MarketSnapshot(
        exchange="binance",
        market_type="futures",
        symbol="BTCUSDT",
        timeframe="15m",
        candles=(candle,),
        captured_at=candle.close_time,
    )


def core_decision(snapshot):
    return BrooksCoreDecision(
        decision="LONG",
        source_signal_id="hp-cohort-core-1",
        entry_price=D("101"),
        stop_loss=D("99"),
        targets=(D("103"),),
        setup_type="FAILED_BREAKOUT_LONG",
        reasoning=("cohort",),
        rule_ids=(),
        failed_rules=(),
        rule_evidence=(),
        engine_version="engine",
        rule_set_version="rules",
        configuration_version="config",
        market_snapshot_id=snapshot.snapshot_id,
        market_snapshot_hash=snapshot.snapshot_hash,
        chart_path="/tmp/hp.png",
    )


def import_command(*, cohort=FINAL):
    return BrooksSignalImport(
        source_signal_id="hp-import-1",
        symbol="BTCUSDT",
        direction="LONG",
        entry_price=D("100"),
        stop_loss=D("99"),
        targets=(D("101"),),
        leverage=D("1"),
        exchange="binance",
        market_type="futures",
        timeframe="15m",
        setup_type="FAILED_BREAKOUT_LONG",
        market_snapshot_id="snap",
        market_snapshot_hash="hash",
        engine_version="engine",
        rule_set_version="rules",
        configuration_version="config",
        reasoning=(),
        rule_ids=(),
        failed_rules=(),
        rule_evidence=(),
        generation_mode="LIVE",
        publication_scope="VIP",
        counts_toward_performance=True,
        semantic_cohort_id=cohort,
    )


class CaptureIntegration:
    def __init__(self):
        self.commands = []

    async def import_signal(self, command):
        self.commands.append(command)
        return SimpleNamespace(
            signal_id=1,
            created=False,
            disposition="BLOCKED_HP_COHORT_TEST",
        )


class EmptyResult:
    def all(self):
        return []


class RecordingSession:
    def __init__(self):
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return EmptyResult()


def test_final_cohort_id_is_stable_and_explicit():
    assert FINAL == "BROOKS_HP_SEMANTIC_COHORT_W01_W19_V1"


def test_mapper_attaches_final_semantic_cohort_before_hp_lookup():
    s = snap()
    candidate = to_paper_candidate(snapshot=s, decision=core_decision(s))
    assert candidate is not None
    assert candidate.semantic_cohort_id == FINAL


def test_persistence_payload_contains_semantic_cohort_even_without_typed_contracts():
    payload = _brooks_core_typed_metadata(import_command())
    assert payload["hp_semantic_cohort_id"] == FINAL


def test_legacy_import_without_cohort_remains_backward_compatible():
    command = import_command(cohort=None)
    assert command.semantic_cohort_id is None
    assert "hp_semantic_cohort_id" not in _brooks_core_typed_metadata(command)


def test_stored_cohort_loads_from_analysis_metadata():
    metadata = SimpleNamespace(analysis_metadata={"hp_semantic_cohort_id": FINAL})
    assert _stored_semantic_cohort_id(metadata) == FINAL


def test_legacy_row_missing_cohort_loads_as_unknown_not_final():
    metadata = SimpleNamespace(analysis_metadata={})
    assert _stored_semantic_cohort_id(metadata) is None


@pytest.mark.asyncio
async def test_repository_can_filter_final_cohort_at_sql_boundary():
    session = RecordingSession()
    cases = await HistoricalProbabilityRepository(
        session, semantic_cohort_id=FINAL
    ).load_cases()
    assert cases == ()
    sql = str(session.statement.compile(compile_kwargs={"literal_binds": True}))
    assert "analysis_metadata" in sql
    assert FINAL in sql


@pytest.mark.asyncio
async def test_futures_only_filter_is_preserved_with_cohort_filter():
    session = RecordingSession()
    await HistoricalProbabilityRepository(
        session,
        data_domain="FUTURES_ONLY",
        semantic_cohort_id=FINAL,
    ).load_cases()
    sql = str(session.statement.compile(compile_kwargs={"literal_binds": True}))
    assert "signal_automation_metadata.exchange = 'binance'" in sql
    assert "signal_automation_metadata.market_type = 'futures'" in sql
    assert FINAL in sql


def test_final_candidate_excludes_legacy_unknown_history():
    cases = tuple(case(i, cohort=None) for i in range(1, 30))
    result = HistoricalProbabilityEngine(cases).assess(hp_candidate())
    assert not result.calibrated
    assert result.cohort_isolation_applied


def test_final_candidate_excludes_different_semantic_cohort():
    cases = tuple(case(i, cohort=OTHER) for i in range(1, 30))
    result = HistoricalProbabilityEngine(cases).assess(hp_candidate())
    assert not result.calibrated


def test_exact_setup_timeframe_same_cohort_calibrates_at_eight():
    cases = tuple(case(i) for i in range(1, 9))
    result = HistoricalProbabilityEngine(cases).assess(hp_candidate())
    assert result.calibrated
    assert result.scope == "SETUP_TIMEFRAME"
    assert result.sample_size == 8


def test_exact_mixed_legacy_plus_two_final_does_not_calibrate():
    cases = tuple(case(i, cohort=None) for i in range(1, 25)) + tuple(
        case(i) for i in range(25, 27)
    )
    result = HistoricalProbabilityEngine(cases).assess(hp_candidate())
    assert not result.calibrated
    assert result.compatible_case_count == 2


def test_setup_all_timeframes_same_cohort_calibrates():
    cases = tuple(case(i, timeframe="5m") for i in range(1, 5)) + tuple(
        case(i, timeframe="1h") for i in range(5, 9)
    )
    result = HistoricalProbabilityEngine(cases).assess(hp_candidate())
    assert result.calibrated
    assert result.scope == "SETUP_ALL_TIMEFRAMES"


def test_family_timeframe_same_cohort_calibrates():
    cases = tuple(
        case(i, setup="FAILED_BREAKOUT_SHORT", direction="SHORT")
        for i in range(1, 13)
    )
    result = HistoricalProbabilityEngine(cases).assess(hp_candidate())
    assert result.calibrated
    assert result.scope == "FAMILY_TIMEFRAME"


def test_family_all_timeframes_same_cohort_calibrates():
    cases = tuple(
        case(i, setup="FAILED_BREAKOUT_SHORT", timeframe="5m", direction="SHORT")
        for i in range(1, 13)
    )
    result = HistoricalProbabilityEngine(cases).assess(hp_candidate())
    assert result.calibrated
    assert result.scope == "FAMILY_ALL_TIMEFRAMES"


def test_direction_timeframe_same_cohort_calibrates():
    cases = tuple(
        case(i, setup="OTHER_LONG", direction="LONG")
        for i in range(1, 21)
    )
    result = HistoricalProbabilityEngine(cases).assess(
        hp_candidate(setup="CUSTOM_LONG")
    )
    assert result.calibrated
    assert result.scope == "DIRECTION_TIMEFRAME"


def test_direction_all_timeframes_same_cohort_calibrates():
    cases = tuple(
        case(i, setup="OTHER_LONG", timeframe="5m", direction="LONG")
        for i in range(1, 21)
    )
    result = HistoricalProbabilityEngine(cases).assess(
        hp_candidate(setup="CUSTOM_LONG")
    )
    assert result.calibrated
    assert result.scope == "DIRECTION_ALL_TIMEFRAMES"


def test_insufficient_same_cohort_all_levels_is_uncalibrated_fail_closed():
    cases = tuple(case(i) for i in range(1, 8))
    result = HistoricalProbabilityEngine(cases).assess(hp_candidate())
    assert not result.calibrated
    assert result.probability is None
    assert result.scope.endswith(":INSUFFICIENT_HISTORY")


def test_nearest_neighbors_cannot_cross_cohort():
    final_cases = tuple(case(i, quality=70 + i) for i in range(1, 9))
    legacy_cases = tuple(case(100 + i, cohort=None, quality=80) for i in range(1, 21))
    result = HistoricalProbabilityEngine(legacy_cases + final_cases).assess(hp_candidate())
    assert result.calibrated
    assert set(result.neighbor_signal_ids) == set(range(1, 9))


def test_configuration_version_alone_does_not_authorize_compatibility():
    candidate = hp_candidate()
    candidate.configuration_version = "same"
    cases = tuple(case(i, cohort=None) for i in range(1, 9))
    result = HistoricalProbabilityEngine(cases).assess(candidate)
    assert not result.calibrated


def test_failed_breakout_live_style_24_legacy_plus_2_final_is_blocked():
    cases = tuple(case(i, cohort=None) for i in range(1, 25)) + tuple(
        case(i) for i in range(25, 27)
    )
    result = HistoricalProbabilityEngine(cases).assess(
        hp_candidate(setup="FAILED_BREAKOUT_LONG")
    )
    assert not result.calibrated
    assert result.compatible_case_count == 2


def test_trading_range_fade_pre_wave14_history_isolated():
    cases = tuple(
        case(i, setup="TRADING_RANGE_FADE_LONG", cohort=None)
        for i in range(1, 9)
    ) + tuple(
        case(i, setup="TRADING_RANGE_FADE_LONG")
        for i in range(9, 11)
    )
    result = HistoricalProbabilityEngine(cases).assess(
        hp_candidate(setup="TRADING_RANGE_FADE_LONG")
    )
    assert not result.calibrated


def test_ma_gap_pre_wave13_history_isolated():
    cases = tuple(
        case(i, setup="FIRST_MA_GAP_BAR_LONG", cohort=None)
        for i in range(1, 9)
    ) + tuple(
        case(i, setup="FIRST_MA_GAP_BAR_LONG")
        for i in range(9, 11)
    )
    result = HistoricalProbabilityEngine(cases).assess(
        hp_candidate(setup="FIRST_MA_GAP_BAR_LONG")
    )
    assert not result.calibrated


def test_wave12_new_direct_participation_does_not_use_legacy_direction_pool():
    cases = tuple(
        case(i, setup="OTHER_LONG", cohort=None) for i in range(1, 30)
    )
    result = HistoricalProbabilityEngine(cases).assess(
        hp_candidate(setup="STRONG_TREND_BAR_DIRECT_ENTRY_LONG")
    )
    assert not result.calibrated


def test_wave15_same_setup_string_htf_semantics_remain_isolated():
    cases = tuple(case(i, setup="H2_CONFIRMED", cohort=None) for i in range(1, 9))
    result = HistoricalProbabilityEngine(cases).assess(
        hp_candidate(setup="H2_CONFIRMED")
    )
    assert not result.calibrated


def test_wave17_19_management_semantics_do_not_reuse_legacy_setup_history():
    cases = tuple(
        case(i, setup="MAJOR_TREND_REVERSAL_LONG", cohort=None)
        for i in range(1, 9)
    )
    result = HistoricalProbabilityEngine(cases).assess(
        hp_candidate(setup="MAJOR_TREND_REVERSAL_LONG")
    )
    assert not result.calibrated


def test_family_fallback_never_uses_legacy_family_rows():
    legacy = tuple(
        case(i, setup="FAILED_BREAKOUT_SHORT", direction="SHORT", cohort=None)
        for i in range(1, 13)
    )
    final = tuple(
        case(100 + i, setup="FAILED_BREAKOUT_SHORT", direction="SHORT")
        for i in range(1, 5)
    )
    result = HistoricalProbabilityEngine(legacy + final).assess(hp_candidate())
    assert not result.calibrated


def test_direction_fallback_never_uses_legacy_direction_rows():
    legacy = tuple(case(i, setup="OTHER_LONG", cohort=None) for i in range(1, 21))
    final = tuple(case(100 + i, setup="OTHER_LONG") for i in range(1, 5))
    result = HistoricalProbabilityEngine(legacy + final).assess(
        hp_candidate(setup="CUSTOM_LONG")
    )
    assert not result.calibrated


def test_legacy_candidate_without_cohort_preserves_existing_mixed_behavior():
    cases = tuple(case(i, cohort=None) for i in range(1, 9))
    result = HistoricalProbabilityEngine(cases).assess(hp_candidate(cohort=None))
    assert result.calibrated
    assert not result.cohort_isolation_applied


@pytest.mark.asyncio
async def test_paper_runtime_propagates_semantic_cohort():
    s = snap()
    c = to_paper_candidate(snapshot=s, decision=core_decision(s))
    integration = CaptureIntegration()
    service = PaperRuntimeService(
        SimpleNamespace(),
        publisher=SimpleNamespace(),
        private_test_channel_id=-1001,
        default_leverage=D("1"),
        integration_service_factory=lambda _: integration,
    )
    await service.process(c)
    assert integration.commands[0].semantic_cohort_id == FINAL


@pytest.mark.asyncio
async def test_live_runtime_propagates_semantic_cohort():
    s = snap()
    c = to_paper_candidate(snapshot=s, decision=core_decision(s))
    integration = CaptureIntegration()
    service = LiveVipRuntimeService(
        SimpleNamespace(),
        publisher=SimpleNamespace(),
        vip_channel_id=-1002,
        default_leverage=D("1"),
        integration_service_factory=lambda _: integration,
    )
    await service.process(c, signal_quality=SimpleNamespace())
    assert integration.commands[0].semantic_cohort_id == FINAL


@pytest.mark.asyncio
async def test_paper_live_semantic_cohort_parity():
    s = snap()
    c = to_paper_candidate(snapshot=s, decision=core_decision(s))
    pcap, lcap = CaptureIntegration(), CaptureIntegration()
    paper = PaperRuntimeService(
        SimpleNamespace(), publisher=SimpleNamespace(), private_test_channel_id=-1,
        default_leverage=D("1"), integration_service_factory=lambda _: pcap,
    )
    live = LiveVipRuntimeService(
        SimpleNamespace(), publisher=SimpleNamespace(), vip_channel_id=-2,
        default_leverage=D("1"), integration_service_factory=lambda _: lcap,
    )
    await paper.process(c)
    await live.process(c, signal_quality=SimpleNamespace())
    assert pcap.commands[0].semantic_cohort_id == lcap.commands[0].semantic_cohort_id == FINAL


def uncalibrated_assessment():
    return ProbabilityAssessment(
        calibrated=False,
        probability=None,
        empirical_win_rate=None,
        lower_bound=None,
        upper_bound=None,
        historical_reliability=0.0,
        sample_size=0,
        wins=0,
        losses=0,
        scope="DIRECTION_ALL_TIMEFRAMES:INSUFFICIENT_HISTORY",
        break_even_probability=None,
        expected_value_r=None,
        trader_equation_favorable=False,
        semantic_cohort_id=FINAL,
        cohort_isolation_applied=True,
        compatible_case_count=2,
        required_sample_size=20,
    )


def test_signal_intelligence_treats_uncalibrated_same_cohort_as_not_approved():
    quality = SimpleNamespace(
        final_score=80.0,
        conflicts=(),
        structure_quality=80.0,
        context_quality=80.0,
        entry_quality=80.0,
        risk_quality=80.0,
        brooks_certainty=80.0,
        unclassified_rule_ids=(),
    )
    candidate = SimpleNamespace(snapshot=None)
    with patch("app.modules.signal_intelligence.service.score_candidate", return_value=quality):
        result = SignalIntelligenceService().evaluate(
            candidate,
            ai_score=80,
            risk_score=80,
            probability=uncalibrated_assessment(),
        )
    assert result.approved is False
    assert result.metadata["probability_calibrated"] is False


def test_final_gate_rejects_uncalibrated_probability():
    quality = SimpleNamespace(
        quality_grade="A",
        confidence=0.0,
        metadata={
            "structure_quality": 100.0,
            "context_quality": 100.0,
            "risk_quality": 100.0,
            "probability_calibrated": False,
            "probability": None,
            "break_even_probability": None,
            "trader_equation_favorable": False,
            "evidence_conflicts": (),
        },
    )
    decision = SignalGateService().evaluate(quality)
    assert not decision.approved
    assert "PROBABILITY_UNCALIBRATED" in decision.metadata["failures"]


def test_risk_interface_remains_compatible_without_using_cohort():
    candidate = hp_candidate()
    candidate.snapshot = None
    assessment = RiskEngineService().evaluate(candidate)
    assert isinstance(assessment.risk_score, float)


def test_probability_threshold_constants_are_unchanged():
    assert (_MIN_EXACT, _MIN_FAMILY, _MIN_BROAD, _MAX_NEIGHBORS) == (8, 12, 20, 20)
