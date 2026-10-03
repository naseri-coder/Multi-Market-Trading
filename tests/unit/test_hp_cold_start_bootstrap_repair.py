from __future__ import annotations

import inspect
from datetime import UTC, datetime
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from app.modules.brooks_runtime import coordinator as coordinator_module
from app.modules.brooks_runtime.coordinator import BrooksFullCoreCoordinator
from app.modules.operations.lifecycle import (
    ColdStartBootstrapLifecycleService,
    LiveSignalLifecycleService,
    _hp_bootstrap_metadata,
    _set_hp_bootstrap_state,
)
from app.modules.signal_automation.entities import (
    BrooksSignalImport,
    FINAL_BROOKS_HP_SEMANTIC_COHORT_ID,
    HP_COLD_START_BOOTSTRAP_POLICY_ID,
    hp_cold_start_shadow_source_signal_id,
)
from app.modules.signal_automation.repository import _brooks_core_typed_metadata
from app.modules.signal_gate.service import SignalGateService
from app.modules.signal_intelligence.probability import (
    HistoricalCase,
    HistoricalProbabilityEngine,
    HistoricalProbabilityRepository,
    historical_probability_sample_accounting,
)

FINAL = FINAL_BROOKS_HP_SEMANTIC_COHORT_ID
POLICY = HP_COLD_START_BOOTSTRAP_POLICY_ID
BASE = datetime(2026, 9, 19, tzinfo=UTC)


def _provenance(original: str = "core-event-1") -> dict[str, object]:
    scoped = hp_cold_start_shadow_source_signal_id(original, FINAL)
    return {
        "bootstrap": True,
        "policy_id": POLICY,
        "generation_mode": "SHADOW",
        "semantic_cohort_id": FINAL,
        "original_source_signal_id": original,
        "mode_scoped_source_signal_id": scoped,
        "state": "BOOTSTRAP_ENTRY_PENDING",
        "hp_eligible": False,
    }


def _command(*, original: str = "core-event-1") -> BrooksSignalImport:
    provenance = _provenance(original)
    return BrooksSignalImport(
        source_signal_id=str(provenance["mode_scoped_source_signal_id"]),
        symbol="BTCUSDT", direction="LONG", entry_price=D("100"),
        stop_loss=D("95"), targets=(D("110"),), leverage=D("1"),
        exchange="binance", market_type="futures", timeframe="15m",
        setup_type="H2_CONFIRMED", market_snapshot_id="snap-1",
        market_snapshot_hash="hash-1", engine_version="engine-final",
        rule_set_version="rules-final", configuration_version="cfg-final",
        reasoning=("bootstrap",), rule_ids=(), failed_rules=(), rule_evidence=(),
        generation_mode="SHADOW", publication_scope="INTERNAL",
        counts_toward_performance=False, semantic_cohort_id=FINAL,
        bootstrap_provenance=provenance,
    )


def _case(
    n: int,
    *,
    cohort: str | None = FINAL,
    mode: str = "SHADOW",
    policy: str | None = POLICY,
    setup: str = "H2_CONFIRMED",
    timeframe: str = "15m",
    direction: str = "LONG",
) -> HistoricalCase:
    return HistoricalCase(
        signal_id=n, setup_type=setup, timeframe=timeframe, direction=direction,
        structure_quality=80.0, context_quality=80.0, entry_quality=80.0,
        risk_feature=50.0, outcome=n % 2, rule_ids=(),
        semantic_cohort_id=cohort, generation_mode=mode,
        bootstrap_policy_id=policy,
    )

def _hp_candidate(**overrides):
    values = dict(
        setup_type="H2_CONFIRMED", timeframe="15m", direction="LONG",
        entry_price=D("100"), stop_loss=D("95"), targets=(D("110"),),
        rule_evidence=(), semantic_cohort_id=FINAL,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


class _EmptyRows:
    def all(self):
        return []


class _RecordingSession:
    def __init__(self):
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return _EmptyRows()


class _SessionContext:
    def __init__(self, session):
        self.value = session

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, tb):
        return False

class _Database:
    def __init__(self, session):
        self.value = session

    def session(self):
        return _SessionContext(self.value)


def test_bootstrap_source_identity_is_deterministic_mode_scoped_and_preserves_original():
    first = hp_cold_start_shadow_source_signal_id("event-1", FINAL)
    second = hp_cold_start_shadow_source_signal_id("event-1", FINAL)
    other = hp_cold_start_shadow_source_signal_id("event-2", FINAL)
    assert first == second
    assert first != "event-1"
    assert first != other
    assert len(first) == 64
    provenance = _provenance("event-1")
    assert provenance["original_source_signal_id"] == "event-1"
    assert provenance["mode_scoped_source_signal_id"] == first


def test_bootstrap_import_contract_is_shadow_internal_explicit_and_json_persisted():
    command = _command()
    assert command.generation_mode == "SHADOW"
    assert command.publication_scope == "INTERNAL"
    assert command.counts_toward_performance is False
    assert command.semantic_cohort_id == FINAL
    metadata = _brooks_core_typed_metadata(command)
    assert metadata["hp_semantic_cohort_id"] == FINAL
    assert metadata["hp_cold_start_bootstrap"] == command.bootstrap_provenance


def test_bootstrap_contract_rejects_live_or_unscoped_provenance():
    command = _command()
    values = {name: getattr(command, name) for name in command.__dataclass_fields__}
    values["generation_mode"] = "LIVE"
    values["publication_scope"] = "VIP"
    values["counts_toward_performance"] = True
    with pytest.raises(ValueError):
        BrooksSignalImport(**values)


def test_retry_identity_and_idempotency_are_stable_but_live_identity_is_unchanged():
    first = _command(original="same-event")
    second = _command(original="same-event")
    assert first.source_signal_id == second.source_signal_id
    assert first.idempotency_key == second.idempotency_key
    live = BrooksSignalImport(
        source_signal_id="same-event", symbol="BTCUSDT", direction="LONG",
        entry_price=D("100"), stop_loss=D("95"), targets=(D("110"),),
        leverage=D("1"), exchange="binance", market_type="futures",
        timeframe="15m", setup_type="H2_CONFIRMED",
        market_snapshot_id="snap-1", market_snapshot_hash="hash-1",
        engine_version="engine-final", rule_set_version="rules-final",
        configuration_version="cfg-final", reasoning=(), rule_ids=(),
        failed_rules=(), rule_evidence=(), generation_mode="LIVE",
        publication_scope="VIP", counts_toward_performance=True,
        semantic_cohort_id=FINAL,
    )
    assert live.source_signal_id == "same-event"
    assert live.source_signal_id != first.source_signal_id
    assert live.idempotency_key != first.idempotency_key


@pytest.mark.asyncio
async def test_hp_repository_sql_adds_only_explicit_bootstrap_shadow_branch():
    session = _RecordingSession()
    rows = await HistoricalProbabilityRepository(
        session, data_domain="FUTURES_ONLY", semantic_cohort_id=FINAL
    ).load_cases()
    assert rows == ()
    sql = str(session.statement.compile(compile_kwargs={"literal_binds": True}))
    assert "counts_toward_performance" in sql
    assert "SHADOW" in sql
    assert POLICY in sql
    assert "BOOTSTRAP_TERMINAL_ELIGIBLE" in sql
    assert FINAL in sql
    assert "futures" in sql and "binance" in sql


def test_hp_same_cohort_insufficient_history_remains_uncalibrated():
    cases = tuple(_case(i) for i in range(1, 8))
    result = HistoricalProbabilityEngine(cases).assess(_hp_candidate())
    assert result.calibrated is False
    assert result.compatible_case_count == 7
    assert result.scope.endswith(":INSUFFICIENT_HISTORY")


def test_hp_exact_existing_minimum_still_calibrates_at_eight():
    cases = tuple(_case(i) for i in range(1, 9))
    result = HistoricalProbabilityEngine(cases).assess(_hp_candidate())
    assert result.calibrated is True
    assert result.sample_size == 8
    assert result.scope == "SETUP_TIMEFRAME"


def test_hp_same_cohort_filter_rejects_legacy_and_different_cohort():
    cases = (
        tuple(_case(i, cohort=None, mode="LIVE", policy=None) for i in range(1, 30))
        + tuple(_case(i, cohort="OTHER") for i in range(30, 60))
        + tuple(_case(i) for i in range(60, 62))
    )
    result = HistoricalProbabilityEngine(cases).assess(_hp_candidate())
    assert result.calibrated is False
    assert result.compatible_case_count == 2
    assert set(result.neighbor_signal_ids).issubset({60, 61})


def test_bootstrap_sample_accounting_distinguishes_live_shadow_and_scopes():
    cases = (
        _case(1, mode="LIVE", policy=None),
        _case(2),
        _case(3, setup="H2_OTHER", timeframe="1h"),
        _case(4, cohort="OTHER"),
    )
    counts = historical_probability_sample_accounting(cases, _hp_candidate())
    assert counts["live_terminal"] == 1
    assert counts["bootstrap_shadow_terminal"] == 2
    assert counts["total_eligible_same_cohort"] == 3
    assert counts["setup_timeframe"] == 2


def test_bootstrap_metadata_state_is_explicit_and_never_fabricated_for_legacy():
    metadata = SimpleNamespace(
        generation_mode="SHADOW",
        analysis_metadata={"hp_cold_start_bootstrap": _provenance()},
    )
    assert _hp_bootstrap_metadata(metadata)["state"] == "BOOTSTRAP_ENTRY_PENDING"
    _set_hp_bootstrap_state(
        metadata, state="BOOTSTRAP_TERMINAL_ELIGIBLE", hp_eligible=True
    )
    assert _hp_bootstrap_metadata(metadata)["state"] == "BOOTSTRAP_TERMINAL_ELIGIBLE"
    assert _hp_bootstrap_metadata(metadata)["hp_eligible"] is True
    legacy = SimpleNamespace(generation_mode="SHADOW", analysis_metadata={})
    assert _hp_bootstrap_metadata(legacy) is None


@pytest.mark.asyncio
async def test_lifecycle_selector_contains_live_and_explicit_bootstrap_shadow_only():
    session = _RecordingSession()
    service = LiveSignalLifecycleService(
        database=_Database(session), provider=object(), bot=object(),
        vip_channel_id=1, cutover_at=BASE, candle_limit=20,
    )
    assert await service._load_items() == ()
    sql = str(session.statement.compile(compile_kwargs={"literal_binds": True}))
    assert "generation_mode = 'LIVE'" in sql
    assert "generation_mode = 'SHADOW'" in sql
    assert "publication_scope = 'INTERNAL'" in sql
    assert POLICY in sql


def test_bootstrap_reuses_canonical_lifecycle_tm_and_same_bar_ambiguity():
    source = inspect.getsource(LiveSignalLifecycleService._process_item)
    assert "_ensure_trade_management_plan" in source
    assert "_close_runner_on_reversal" in source
    assert "_tighten_active_stop" in source
    assert "ENTRY_AND_EXIT_SAME_1M_CANDLE" in source
    assert "STOP_AND_TARGET_SAME_1M_CANDLE" in source
    assert "not bootstrap_shadow" in source


def test_bootstrap_reversal_outcome_uses_same_causal_advancer():
    source = inspect.getsource(LiveSignalLifecycleService._advance_reversal_outcome)
    assert "_is_hp_bootstrap(metadata)" in source
    assert "ApprovedMarketEvidence" in source
    assert "candle.open_time" in source


def _coordinator_candidate():
    return SimpleNamespace(
        source_signal_id="core-event-42", symbol="BTCUSDT", timeframe="15m",
        direction="LONG", entry_price=D("100"), stop_loss=D("95"),
        targets=(D("110"),), exchange="binance", market_type="futures",
        setup_type="H2_CONFIRMED", market_snapshot_id="snap-42",
        market_snapshot_hash="hash-42", engine_version="engine-final",
        rule_set_version="rules-final", configuration_version="cfg-final",
        reasoning=("source valid",), rule_ids=(), failed_rules=(),
        rule_evidence=(), target_source_identities=(),
        stop_source_identity=None, target_plan_lifecycle=None,
        reversal_outcome_context=None, semantic_cohort_id=FINAL,
        snapshot=SimpleNamespace(captured_at=BASE),
    )


def _quality():
    return SimpleNamespace(
        final_score=90.0, confidence=0.0, quality_grade="A", approved=False,
        metadata={
            "structure_quality": 90.0, "context_quality": 90.0,
            "risk_quality": 93.25, "probability_calibrated": False,
            "trader_equation_favorable": False, "evidence_conflicts": (),
            "probability": None, "break_even_probability": None,
            "market_regime": "BULL_TREND",
        },
    )


def _probability():
    return SimpleNamespace(
        calibrated=False, scope="DIRECTION_ALL_TIMEFRAMES:INSUFFICIENT_HISTORY",
        cohort_isolation_applied=True,
    )


def _risk(method: str):
    return SimpleNamespace(
        risk_score=93.25,
        metadata={
            "risk_semantic_breakdown": {
                "structural_validation": {
                    "entry_method": method,
                    "entry_trigger_semantic": "SIGNAL_BAR_STOP_TRIGGER",
                    "economic_opportunity_id": "opp-42",
                }
            }
        },
    )


class _CaptureIntegration:
    command = None

    def __init__(self, session):
        pass

    async def import_signal(self, command):
        type(self).command = command
        return SimpleNamespace(signal_id=42, created=False)


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime_mode", ["paper", "live"])
async def test_coordinator_collects_only_authorized_stop_trigger_shadow(
    monkeypatch, runtime_mode
):
    monkeypatch.setattr(
        coordinator_module, "BrooksSignalIntegrationService", _CaptureIntegration
    )
    service = BrooksFullCoreCoordinator.__new__(BrooksFullCoreCoordinator)
    service.settings = SimpleNamespace(brooks_runtime_mode=runtime_mode)
    service.database = _Database(object())
    service._signal_gate = SignalGateService()
    result = await service._collect_hp_cold_start_bootstrap(
        candidate=_coordinator_candidate(),
        council_decision=SimpleNamespace(final_score=91.0),
        risk_assessment=_risk("STOP_TRIGGER_CONFIRMATION"),
        probability_assessment=_probability(),
        signal_quality=_quality(),
        leverage=D("1"),
    )
    assert result.signal_id == 42
    command = _CaptureIntegration.command
    assert command.generation_mode == "SHADOW"
    assert command.publication_scope == "INTERNAL"
    assert command.counts_toward_performance is False
    assert command.source_signal_id != command.bootstrap_provenance["original_source_signal_id"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method",
    [
        "LIMIT_OR_MARKET_FADE",
        "LIMIT_OR_MARKET_ANTICIPATION",
        "MARKET_OR_LIMIT_ANTICIPATION",
        "UNKNOWN",
    ],
)
async def test_coordinator_fails_closed_for_ambiguous_or_unknown_fill_methods(
    monkeypatch, method
):
    class _ForbiddenIntegration:
        def __init__(self, session):
            raise AssertionError("bootstrap import must not occur")

    monkeypatch.setattr(
        coordinator_module, "BrooksSignalIntegrationService", _ForbiddenIntegration
    )
    service = BrooksFullCoreCoordinator.__new__(BrooksFullCoreCoordinator)
    service.settings = SimpleNamespace(brooks_runtime_mode="live")
    service.database = _Database(object())
    service._signal_gate = SignalGateService()
    result = await service._collect_hp_cold_start_bootstrap(
        candidate=_coordinator_candidate(),
        council_decision=SimpleNamespace(final_score=91.0),
        risk_assessment=_risk(method),
        probability_assessment=_probability(),
        signal_quality=_quality(),
        leverage=D("1"),
    )
    assert result is None


def test_failed_qualitative_policy_is_not_reactivated_and_thresholds_unchanged():
    import app.modules.signal_intelligence.probability as probability
    assert probability._MIN_EXACT == 8
    assert probability._MIN_FAMILY == 12
    assert probability._MIN_BROAD == 20
    assert probability._MAX_NEIGHBORS == 20
    source = inspect.getsource(BrooksFullCoreCoordinator._collect_hp_cold_start_bootstrap)
    assert "qualitative" not in source.lower()
    assert "calibrated" in source

@pytest.mark.asyncio
async def test_bootstrap_only_lifecycle_selector_excludes_live_vip_rows():
    session = _RecordingSession()
    service = ColdStartBootstrapLifecycleService(
        database=_Database(session),
        provider=object(),
        bot=object(),
        candle_limit=240,
    )
    assert await service._load_items() == ()
    sql = str(session.statement.compile(compile_kwargs={"literal_binds": True}))
    assert "generation_mode = 'SHADOW'" in sql
    assert "publication_scope = 'INTERNAL'" in sql
    assert POLICY in sql
    assert "generation_mode = 'LIVE'" not in sql
    assert "TELEGRAM_VIP" not in sql


@pytest.mark.asyncio
async def test_bootstrap_only_lifecycle_never_retries_telegram_messages():
    service = ColdStartBootstrapLifecycleService(
        database=object(),
        provider=object(),
        bot=object(),
        candle_limit=240,
    )
    assert await service._retry_pending_message_updates() == 0


@pytest.mark.asyncio
async def test_paper_runtime_runs_shadow_only_bootstrap_lifecycle(monkeypatch):
    captured = {}

    class _Lifecycle:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def run_once(self):
            return {"tracked": 2, "changed": 1, "ambiguous": 0, "message_retries": 0}

    monkeypatch.setattr(
        coordinator_module,
        "ColdStartBootstrapLifecycleService",
        _Lifecycle,
    )
    service = BrooksFullCoreCoordinator.__new__(BrooksFullCoreCoordinator)
    service.settings = SimpleNamespace(
        brooks_runtime_mode="paper",
        signal_lifecycle_candle_limit=240,
    )
    service.database = object()
    service._provider = object()
    service._bot = object()

    await service._run_paper_bootstrap_lifecycle_once()

    assert captured["database"] is service.database
    assert captured["provider"] is service._provider
    assert captured["bot"] is service._bot
    assert captured["candle_limit"] == 240

