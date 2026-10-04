import inspect
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.modules.brooks_runtime.coordinator as coordinator_module
from app.modules.brooks_runtime.coordinator import (
    _REALIZED_R_BASELINE_LEVERAGE_CONFIDENCE,
    _REALIZED_R_LEVERAGE_POLICY_ID,
    BrooksFullCoreCoordinator,
    _leverage_confidence_input,
)
from app.modules.live_vip_runtime.publisher import TelegramLiveVipPublisher
from app.modules.live_vip_runtime.service import LiveVipRuntimeService as RealLiveVipRuntimeService
from app.modules.risk_engine.calculator import RiskCalculator
from app.modules.signal_automation.entities import (
    BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1,
    FINAL_BROOKS_HP_SEMANTIC_COHORT_ID,
)
from app.modules.signal_gate.service import SignalGateService
from app.modules.signal_intelligence.probability import ProbabilityAssessment
from app.modules.signal_intelligence.service import SignalIntelligenceService
from app.modules.signal_strategies.entities import SignalStrategyRecord


def test_realized_r_policy_routes_private_zero_sentinel():
    value, policy = _leverage_confidence_input(
        BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1,
        0.99,
    )
    assert value == 0.0
    assert value == _REALIZED_R_BASELINE_LEVERAGE_CONFIDENCE
    assert policy == _REALIZED_R_LEVERAGE_POLICY_ID


@pytest.mark.parametrize("display_confidence", [0.01, 0.50, 0.88, 0.99])
def test_realized_r_display_or_event_confidence_cannot_change_leverage_input(
    display_confidence,
):
    value, policy = _leverage_confidence_input(
        BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1,
        display_confidence,
    )
    assert value == 0.0
    assert policy == "BROOKS_REALIZED_R_BASELINE_ONLY_LEVERAGE_V1"


def test_leverage_split_does_not_mutate_generic_display_confidence():
    display_confidence = 0.73
    _leverage_confidence_input(
        BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1,
        display_confidence,
    )
    assert display_confidence == 0.73


def test_realized_r_zero_sentinel_selects_existing_no_uplift_path():
    calculator = RiskCalculator()
    leverage = calculator.calculate_leverage(
        entry_price=Decimal("100"),
        stop_loss=Decimal("99"),
        confidence=0.0,
        quality_grade="A",
        risk_score=95.0,
        market_regime="TREND",
    )
    assert leverage == Decimal("1.00")


def test_unknown_explicit_policy_does_not_fall_back_to_legacy_leverage():
    value, policy = _leverage_confidence_input("UNKNOWN_POLICY_V1", 0.99)
    assert value == 0.0
    assert policy == "UNKNOWN_POLICY_FAIL_CLOSED_NO_UPLIFT"


def test_legacy_policy_keeps_signal_quality_confidence_unchanged():
    value, policy = _leverage_confidence_input(
        "LEGACY_LATEST_TERMINAL_EVENT_V1",
        0.88,
    )
    assert value == 0.88
    assert policy == "LEGACY_SIGNAL_QUALITY_CONFIDENCE"


@pytest.mark.parametrize(
    ("confidence", "expected"),
    (
        (0.90, Decimal("3.00")),
        (0.88, Decimal("3.00")),
        (0.86, Decimal("2.00")),
        (0.84, Decimal("1.00")),
    ),
)
def test_legacy_leverage_threshold_behavior_is_unchanged(confidence, expected):
    calculator = RiskCalculator()
    leverage = calculator.calculate_leverage(
        entry_price=Decimal("100"),
        stop_loss=Decimal("99"),
        confidence=confidence,
        quality_grade="A",
        risk_score=95.0,
        market_regime="TREND",
    )
    assert leverage == expected


def test_coordinator_call_site_uses_private_leverage_confidence_only():
    source = inspect.getsource(BrooksFullCoreCoordinator._process_market)
    leverage_block = source.split(
        "dynamic_leverage = self._risk_engine.calculator.calculate_leverage(",
        1,
    )[1].split("logger.info(", 1)[0]
    assert "confidence=leverage_confidence" in leverage_block
    assert "confidence=signal_quality.confidence" not in leverage_block
    assert "signal_quality.confidence" in source


class _AsyncContext:
    def __init__(self, value):
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _TestSession:
    def begin(self):
        return _AsyncContext(self)

    async def commit(self):
        return None


class _TestDatabase:
    def session(self):
        return _AsyncContext(_TestSession())


class _Provider:
    async def get_snapshot(self, **kwargs):
        del kwargs
        close_time = datetime(2026, 9, 23, 7, 0, tzinfo=UTC)
        return SimpleNamespace(
            exchange="binance",
            market_type="futures",
            symbol="BTCUSDT",
            timeframe="15m",
            candles=(SimpleNamespace(close_time=close_time),),
        )


class _Analyzer:
    engine = SimpleNamespace(policy=SimpleNamespace(context=object()))

    async def analyze(self, snapshot):
        del snapshot
        return SimpleNamespace(setup_type="BREAKOUT_LONG")


class _CaptureRiskCalculator(RiskCalculator):
    def __init__(self):
        self.confidence_inputs = []

    def calculate_leverage(self, **kwargs):
        self.confidence_inputs.append(kwargs["confidence"])
        return super().calculate_leverage(**kwargs)


class _CaptureSignalIntelligence:
    def __init__(self):
        self.inner = SignalIntelligenceService()
        self.last = None

    def evaluate(self, *args, **kwargs):
        self.last = self.inner.evaluate(*args, **kwargs)
        return self.last


class _CaptureSignalGate:
    def __init__(self):
        self.inner = SignalGateService()
        self.last = None

    def evaluate(self, signal_quality):
        self.last = self.inner.evaluate(signal_quality)
        return self.last


class _CapturePublisher:
    def __init__(self):
        self.payload = None

    async def publish(self, payload):
        self.payload = payload
        return "777"


class _LiveIntegration:
    def __init__(self, session):
        del session

    async def import_signal(self, command):
        self.command = command
        return SimpleNamespace(signal_id=707, created=True, disposition="CREATED")


class _DeliveryRepository:
    async def get(self, **kwargs):
        del kwargs
        return None

    async def create_pending(self, **kwargs):
        del kwargs
        return SimpleNamespace(id=1, status="PENDING", external_message_id=None)

    async def mark_sending(self, delivery_id, **kwargs):
        del kwargs
        return SimpleNamespace(id=delivery_id, status="SENDING", external_message_id=None)

    async def mark_sent(self, delivery_id, **kwargs):
        del kwargs
        return SimpleNamespace(id=delivery_id, status="SENT", external_message_id="777")


class _QualityPersistenceCapture:
    def __init__(self):
        self.calls = []

    async def save_quality_assessment(self, **kwargs):
        self.calls.append(kwargs)


def _candidate_for_boundary_tests():
    return SimpleNamespace(
        source_signal_id="src-boundary-1",
        symbol="BTCUSDT",
        timeframe="15m",
        direction="LONG",
        entry_price=Decimal("100"),
        stop_loss=Decimal("99"),
        targets=(Decimal("102"),),
        exchange="binance",
        market_type="futures",
        setup_type="BREAKOUT_LONG",
        market_snapshot_id="snap-boundary-1",
        market_snapshot_hash="hash-boundary-1",
        engine_version="core-v5",
        rule_set_version="rules-v6",
        configuration_version="cfg",
        reasoning=("boundary-test",),
        rule_ids=("BR-TEST",),
        failed_rules=(),
        rule_evidence=(),
        chart_path="/tmp/not-used-by-capture-publisher.png",
        snapshot=None,
        semantic_cohort_id=FINAL_BROOKS_HP_SEMANTIC_COHORT_ID,
    )


def _score_fixture():
    return SimpleNamespace(
        final_score=95.0,
        conflicts=(),
        structure_quality=90.0,
        context_quality=90.0,
        risk_quality=90.0,
        entry_quality=90.0,
        brooks_certainty=0.95,
        unclassified_rule_ids=(),
    )


def _probability_assessment(policy_id, readiness_state):
    return ProbabilityAssessment(
        calibrated=True,
        probability=0.73,
        empirical_win_rate=0.73,
        lower_bound=0.70,
        upper_bound=0.76,
        historical_reliability=0.90,
        sample_size=20,
        wins=15,
        losses=5,
        scope="SETUP_TIMEFRAME",
        break_even_probability=0.90,
        expected_value_r=-0.10,
        trader_equation_favorable=False,
        semantic_cohort_id=FINAL_BROOKS_HP_SEMANTIC_COHORT_ID,
        cohort_isolation_applied=True,
        compatible_case_count=20,
        required_sample_size=8,
        outcome_policy_id=policy_id,
        readiness_state=readiness_state,
        structural_scope="SETUP_TIMEFRAME",
        economic_scope="SETUP_TIMEFRAME",
        structural_required_n=8,
        economic_required_n=20,
        valid_realized_r_count=20,
        mean_realized_r=0.20,
        median_realized_r=0.20,
        ci95_lower_r=0.10,
        ci95_upper_r=0.30,
        bootstrap_valid_fraction=1.0,
        realized_r_statistical_confidence=0.97,
    )


def _build_coordinator(probability_assessment, publisher):
    service = BrooksFullCoreCoordinator.__new__(BrooksFullCoreCoordinator)
    service.settings = SimpleNamespace(
        brooks_snapshot_limit=120,
        brooks_market_type="futures",
        brooks_runtime_mode="live",
        brooks_live_cutover_at=datetime(2026, 9, 22, tzinfo=UTC),
        brooks_historical_probability_domain="FINAL_COHORT_ONLY",
        brooks_vip_channel_id=-100123,
    )
    service.database = _TestDatabase()
    service._provider = _Provider()
    service._analyzer = _Analyzer()
    service._publisher = publisher
    service._bot = SimpleNamespace()
    service._last_snapshot_id = {}
    service._ai_council = SimpleNamespace(
        evaluate=lambda candidate: SimpleNamespace(
            approved=True,
            final_score=95.0,
            confidence=0.91,
            summary="approved",
        )
    )
    calculator = _CaptureRiskCalculator()
    service._risk_engine = SimpleNamespace(
        evaluate=lambda candidate: SimpleNamespace(
            approved=True,
            risk_score=95.0,
            reasons=(),
            metadata={
                "risk_semantic_breakdown": {
                    "structural_validation": {
                        "entry_method": "STOP_TRIGGER_CONFIRMATION",
                        "entry_trigger_semantic": "SIGNAL_BAR_STOP_TRIGGER",
                        "economic_opportunity_id": "opp-boundary-1",
                    }
                }
            },
        ),
        calculator=calculator,
    )
    intelligence = _CaptureSignalIntelligence()
    gate = _CaptureSignalGate()
    service._signal_intelligence = intelligence
    service._signal_gate = gate
    service._governance_auditor = SimpleNamespace(
        assess=lambda **kwargs: SimpleNamespace(
            status="PASS",
            mapped_rule_ids=(),
            unmapped_rule_ids=(),
            blockers=(),
        )
    )
    service._scale_in_shadow_observer = None
    engine = SimpleNamespace(
        assess_async=AsyncMock(return_value=probability_assessment)
    )
    return service, calculator, intelligence, gate, engine


@pytest.mark.asyncio
async def test_gap3_unknown_policy_full_coordinator_rejects_without_persistence(
    monkeypatch,
):
    unknown_policy = "UNKNOWN_TEST_POLICY_V1"
    assessment = _probability_assessment(unknown_policy, "MATURING")
    publisher = AsyncMock()
    service, calculator, intelligence, gate, engine = _build_coordinator(
        assessment,
        publisher,
    )
    candidate = _candidate_for_boundary_tests()

    monkeypatch.setattr(
        coordinator_module,
        "MarketSnapshot",
        lambda **kwargs: SimpleNamespace(
            snapshot_id="runtime-snapshot-1",
            captured_at=kwargs["candles"][-1].close_time,
        ),
    )
    monkeypatch.setattr(
        coordinator_module,
        "to_paper_candidate",
        lambda **kwargs: candidate,
    )
    load_probability = AsyncMock(return_value=engine)
    monkeypatch.setattr(coordinator_module, "load_probability_engine", load_probability)
    monkeypatch.setattr(
        "app.modules.signal_intelligence.service.score_candidate",
        lambda *args, **kwargs: _score_fixture(),
    )

    shadow_import = MagicMock(
        side_effect=AssertionError("unknown policy must not import SHADOW signal")
    )
    normal_persistence = MagicMock(
        side_effect=AssertionError("unknown policy must not persist quality")
    )
    live_runtime = MagicMock(
        side_effect=AssertionError("unknown policy must not enter LiveVip runtime")
    )
    approved_record = AsyncMock(
        side_effect=AssertionError("unknown policy must not record approved candidate")
    )
    monkeypatch.setattr(
        coordinator_module,
        "BrooksSignalIntegrationService",
        shadow_import,
    )
    monkeypatch.setattr(coordinator_module, "SignalQualityService", normal_persistence)
    monkeypatch.setattr(coordinator_module, "LiveVipRuntimeService", live_runtime)
    monkeypatch.setattr(coordinator_module, "record_approved_candidate", approved_record)

    await service._process_market(symbol="BTCUSDT", timeframe="15m")

    assert intelligence.last is not None
    assert intelligence.last.approved is False
    assert intelligence.last.metadata["hp_policy_routing_status"] == "UNKNOWN_POLICY_FAIL_CLOSED"
    assert intelligence.last.metadata["hp_policy_rejection_reason"] == "UNKNOWN_HP_OUTCOME_POLICY"
    assert calculator.confidence_inputs == [0.0]
    assert gate.last is not None
    assert gate.last.metadata["failures"] == ("HP_OUTCOME_POLICY_UNRECOGNIZED",)
    shadow_import.assert_not_called()
    approved_record.assert_not_awaited()
    live_runtime.assert_not_called()
    publisher.publish.assert_not_awaited()
    normal_persistence.assert_not_called()


@pytest.mark.asyncio
async def test_gap4_public_confidence_stays_separate_from_private_leverage_sentinel(
    monkeypatch,
):
    assessment = _probability_assessment(
        BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1,
        "CALIBRATED_FAVORABLE",
    )
    publisher = _CapturePublisher()
    service, calculator, intelligence, gate, engine = _build_coordinator(
        assessment,
        publisher,
    )
    candidate = _candidate_for_boundary_tests()
    quality_persistence = _QualityPersistenceCapture()

    monkeypatch.setattr(
        coordinator_module,
        "MarketSnapshot",
        lambda **kwargs: SimpleNamespace(
            snapshot_id="runtime-snapshot-2",
            captured_at=kwargs["candles"][-1].close_time,
        ),
    )
    monkeypatch.setattr(
        coordinator_module,
        "to_paper_candidate",
        lambda **kwargs: candidate,
    )
    monkeypatch.setattr(
        coordinator_module,
        "load_probability_engine",
        AsyncMock(return_value=engine),
    )
    monkeypatch.setattr(
        "app.modules.signal_intelligence.service.score_candidate",
        lambda *args, **kwargs: _score_fixture(),
    )
    monkeypatch.setattr(
        coordinator_module,
        "assess_books_context",
        lambda *args, **kwargs: SimpleNamespace(),
    )
    monkeypatch.setattr(coordinator_module, "record_approved_candidate", AsyncMock())
    monkeypatch.setattr(
        coordinator_module,
        "SQLAlchemySignalQualityRepository",
        lambda session: object(),
    )
    monkeypatch.setattr(
        coordinator_module,
        "SignalQualityService",
        lambda repository: quality_persistence,
    )

    monkeypatch.setattr(
        coordinator_module,
        "SignalStrategyService",
        lambda repository: SimpleNamespace(
            get=AsyncMock(
                return_value=SignalStrategyRecord(
                    id=1,
                    strategy_code="BROOKS",
                    display_name="Price Action (Al Brooks)",
                    enabled=True,
                    engine_ready=True,
                    private_channel_id=-100123,
                    private_channel_title="VIP 1",
                    private_channel_username=None,
                    updated_by_telegram_user_id=1,
                    created_at=datetime(2026, 10, 4, tzinfo=UTC),
                    updated_at=datetime(2026, 10, 4, tzinfo=UTC),
                )
            )
        ),
    )
    monkeypatch.setattr(
        coordinator_module,
        "TelegramStrategyVipPublisher",
        lambda **kwargs: publisher,
    )
    def live_runtime_factory(
        session,
        *,
        publisher,
        vip_channel_id,
        default_leverage,
    ):
        return RealLiveVipRuntimeService(
            session,
            publisher=publisher,
            vip_channel_id=vip_channel_id,
            default_leverage=default_leverage,
            integration_service_factory=_LiveIntegration,
            delivery_repository_factory=lambda session: _DeliveryRepository(),
        )

    monkeypatch.setattr(
        coordinator_module,
        "LiveVipRuntimeService",
        live_runtime_factory,
    )

    await service._process_market(symbol="BTCUSDT", timeframe="15m")

    assert intelligence.last is not None
    assert intelligence.last.approved is True
    assert intelligence.last.confidence == pytest.approx(0.73)
    assert gate.last is not None
    assert gate.last.approved is True
    assert calculator.confidence_inputs == [0.0]
    assert publisher.payload is not None
    assert publisher.payload.confidence == Decimal("0.73")
    assert publisher.payload.leverage == Decimal("1.00")
    assert intelligence.last.confidence == pytest.approx(0.73)
    assert quality_persistence.calls
    assert quality_persistence.calls[-1]["confidence"] == pytest.approx(0.73)

    caption = TelegramLiveVipPublisher._caption(publisher.payload)
    assert "Confidence: 73%" in caption
    assert "Leverage: 1x" in caption
    assert "Confidence: 0%" not in caption
