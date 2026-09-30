from datetime import UTC, datetime
from decimal import Decimal as D
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.modules.brooks_core.engine_contract import (
    BrooksEngineResult,
    ReversalOutcomeContext,
    StopSourceIdentity,
    TargetPlanLifecycle,
    TargetSourceEvidence,
    TargetSourceIdentity,
)
from app.modules.live_vip_runtime.service import LiveVipRuntimeService
from app.modules.market_data.entities import Candle, MarketSnapshot
from app.modules.operations.lifecycle import LiveSignalLifecycleService
from app.modules.operations.trade_management import validate_brooks_execution_contract
from app.modules.paper_runtime.entities import PaperSignalCandidate
from app.modules.paper_runtime.service import PaperRuntimeService
from app.modules.signal_automation.entities import BrooksSignalImport
from app.modules.signal_automation.repository import _brooks_core_typed_metadata


BASE = datetime(2026, 9, 18, tzinfo=UTC)


def typed_contract():
    a = TargetSourceEvidence(
        "PATTERN_MEASURED_MOVE", "SRC:A", 5, 8, "LONG", "PAT:A"
    )
    b = TargetSourceEvidence(
        "FAILED_REVERSAL_ENTRY_PRICE", "SRC:B", 6, 8, "LONG", "FAIL:B"
    )
    target = TargetSourceIdentity(1, D("110"), (a, b), 20)
    stop = StopSourceIdentity(
        D("95"),
        "INITIAL_PROTECTIVE_STOP",
        "STOP:ORIGIN",
        D("96"),
        7,
        20,
        "SETUP_STRUCTURE",
        direction="LONG",
    )
    plan = TargetPlanLifecycle(
        "PLAN:REV:1",
        "REVERSAL_OR_TRANSITION",
        "LONG",
        20,
        target_source_ids=("SRC:A", "SRC:B"),
        initial_stop_source_id="STOP:ORIGIN",
    )
    outcome = ReversalOutcomeContext(
        "OUTCOME:1",
        "OPPORTUNITY:REV:1",
        "LONG",
        "PENDING_REVERSAL_OUTCOME",
        20,
        20,
        ("SRC:A", "SRC:B"),
        "STOP:ORIGIN",
        "PLAN:REV:1",
        "REVERSAL_OR_TRANSITION",
    )
    return target, stop, plan, outcome


def snapshot():
    candle = Candle(
        open_time=BASE,
        close_time=BASE.replace(minute=15),
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
        source="FINAL_GATE_TARGETED_REPAIR",
    )


def candidate():
    target, stop, plan, outcome = typed_contract()
    snap = snapshot()
    return PaperSignalCandidate(
        source_signal_id="final-gate-typed-1",
        symbol="BTCUSDT",
        timeframe="15m",
        direction="LONG",
        entry_price=D("100"),
        stop_loss=D("95"),
        targets=(D("110"),),
        exchange="binance",
        market_type="futures",
        setup_type="MTR",
        market_snapshot_id=snap.snapshot_id,
        market_snapshot_hash=snap.snapshot_hash,
        engine_version="wave19",
        rule_set_version="brooks-final",
        configuration_version="final-gate-targeted-repair",
        reasoning=("typed transport",),
        rule_ids=("BROOKS-GAP-079", "BROOKS-GAP-050", "BROOKS-GAP-080"),
        failed_rules=(),
        rule_evidence=(),
        chart_path="/tmp/final-gate.png",
        snapshot=snap,
        target_source_identities=(target,),
        stop_source_identity=stop,
        target_plan_lifecycle=plan,
        reversal_outcome_context=outcome,
    )


def import_command(**overrides):
    c = candidate()
    values = dict(
        source_signal_id=c.source_signal_id,
        symbol=c.symbol,
        direction=c.direction,
        entry_price=c.entry_price,
        stop_loss=c.stop_loss,
        targets=c.targets,
        leverage=D("1"),
        exchange=c.exchange,
        market_type=c.market_type,
        timeframe=c.timeframe,
        setup_type=c.setup_type,
        market_snapshot_id=c.market_snapshot_id,
        market_snapshot_hash=c.market_snapshot_hash,
        engine_version=c.engine_version,
        rule_set_version=c.rule_set_version,
        configuration_version=c.configuration_version,
        reasoning=c.reasoning,
        rule_ids=c.rule_ids,
        failed_rules=c.failed_rules,
        rule_evidence=c.rule_evidence,
        generation_mode="PAPER",
        publication_scope="PRIVATE_TEST",
        target_source_identities=c.target_source_identities,
        stop_source_identity=c.stop_source_identity,
        target_plan_lifecycle=c.target_plan_lifecycle,
        reversal_outcome_context=c.reversal_outcome_context,
    )
    values.update(overrides)
    return BrooksSignalImport(**values)


class CaptureIntegration:
    def __init__(self):
        self.commands = []

    async def import_signal(self, command):
        self.commands.append(command)
        return SimpleNamespace(
            signal_id=9001,
            created=False,
            disposition="BLOCKED_FINAL_GATE_TEST",
        )


@pytest.mark.asyncio
async def test_paper_runtime_preserves_all_four_typed_contracts():
    c = candidate()
    integration = CaptureIntegration()
    service = PaperRuntimeService(
        SimpleNamespace(),
        publisher=SimpleNamespace(),
        private_test_channel_id=-1001,
        default_leverage=D("1"),
        integration_service_factory=lambda _: integration,
    )
    await service.process(c)
    command = integration.commands[0]
    assert command.target_source_identities == c.target_source_identities
    assert command.stop_source_identity == c.stop_source_identity
    assert command.target_plan_lifecycle == c.target_plan_lifecycle
    assert command.reversal_outcome_context == c.reversal_outcome_context


@pytest.mark.asyncio
async def test_live_runtime_preserves_all_four_typed_contracts():
    c = candidate()
    integration = CaptureIntegration()
    service = LiveVipRuntimeService(
        SimpleNamespace(),
        publisher=SimpleNamespace(),
        vip_channel_id=-1002,
        default_leverage=D("1"),
        integration_service_factory=lambda _: integration,
    )
    await service.process(c, signal_quality=SimpleNamespace())
    command = integration.commands[0]
    assert command.target_source_identities == c.target_source_identities
    assert command.stop_source_identity == c.stop_source_identity
    assert command.target_plan_lifecycle == c.target_plan_lifecycle
    assert command.reversal_outcome_context == c.reversal_outcome_context


@pytest.mark.asyncio
async def test_paper_live_typed_contract_parity():
    c = candidate()
    paper_integration = CaptureIntegration()
    live_integration = CaptureIntegration()
    paper = PaperRuntimeService(
        SimpleNamespace(),
        publisher=SimpleNamespace(),
        private_test_channel_id=-1001,
        default_leverage=D("1"),
        integration_service_factory=lambda _: paper_integration,
    )
    live = LiveVipRuntimeService(
        SimpleNamespace(),
        publisher=SimpleNamespace(),
        vip_channel_id=-1002,
        default_leverage=D("1"),
        integration_service_factory=lambda _: live_integration,
    )
    await paper.process(c)
    await live.process(c, signal_quality=SimpleNamespace())
    p = paper_integration.commands[0]
    l = live_integration.commands[0]
    assert p.target_source_identities == l.target_source_identities
    assert p.stop_source_identity == l.stop_source_identity
    assert p.target_plan_lifecycle == l.target_plan_lifecycle
    assert p.reversal_outcome_context == l.reversal_outcome_context


def test_import_contract_has_additive_backward_compatible_defaults():
    legacy = import_command(
        target_source_identities=(),
        stop_source_identity=None,
        target_plan_lifecycle=None,
        reversal_outcome_context=None,
    )
    assert legacy.target_source_identities == ()
    assert legacy.stop_source_identity is None
    assert legacy.target_plan_lifecycle is None
    assert legacy.reversal_outcome_context is None
    assert _brooks_core_typed_metadata(legacy) == {}


def test_all_canonical_types_roundtrip_losslessly():
    target, stop, plan, outcome = typed_contract()
    assert TargetSourceIdentity.from_metadata(target.to_metadata()) == target
    assert StopSourceIdentity.from_metadata(stop.to_metadata()) == stop
    assert TargetPlanLifecycle.from_metadata(plan.to_metadata()) == plan
    assert ReversalOutcomeContext.from_metadata(outcome.to_metadata()) == outcome


def test_persistence_payload_keeps_all_typed_contracts_and_source_multiplicity():
    command = import_command()
    payload = _brooks_core_typed_metadata(command)["brooks_core_typed_contract"]
    assert len(payload["target_source_identities"][0]["sources"]) == 2
    assert payload["target_source_identities"][0]["sources"][0]["source_id"] == "SRC:A"
    assert payload["target_source_identities"][0]["sources"][1]["source_id"] == "SRC:B"
    assert payload["stop_source_identity"]["source_id"] == "STOP:ORIGIN"
    assert payload["target_plan_lifecycle"]["plan_id"] == "PLAN:REV:1"
    assert payload["reversal_outcome_context"]["reversal_origin_id"] == "OPPORTUNITY:REV:1"


def test_operations_reload_restores_exact_core_typed_objects():
    command = import_command()
    metadata = SimpleNamespace(
        signal_id=1,
        analysis_metadata=_brooks_core_typed_metadata(command),
    )
    service = object.__new__(LiveSignalLifecycleService)
    targets, stop, plan, outcome = service._load_core_execution_contract(metadata=metadata)
    assert targets == command.target_source_identities
    assert stop == command.stop_source_identity
    assert plan == command.target_plan_lifecycle
    assert outcome == command.reversal_outcome_context


def test_operations_legacy_reload_is_safe_and_does_not_fabricate_typed_objects():
    metadata = SimpleNamespace(signal_id=2, analysis_metadata={})
    service = object.__new__(LiveSignalLifecycleService)
    assert service._load_core_execution_contract(metadata=metadata) == ((), None, None, None)


@pytest.mark.asyncio
async def test_operations_reversal_reload_prefers_imported_typed_context_without_backdating():
    _, _, _, outcome = typed_contract()
    metadata = SimpleNamespace(signal_id=3, analysis_metadata={})
    session = SimpleNamespace(flush=AsyncMock())
    service = object.__new__(LiveSignalLifecycleService)
    loaded = await service._load_reversal_outcome_context(
        session=session,
        metadata=metadata,
        imported_context=outcome,
    )
    assert loaded == outcome
    assert loaded.available_at_index == outcome.available_at_index
    assert metadata.analysis_metadata["brooks_reversal_outcome"] == outcome.to_metadata()
    session.flush.assert_awaited_once()


def test_tm_consumes_exact_typed_contract_without_economic_reconstruction():
    target, stop, plan, outcome = typed_contract()
    tm_target = SimpleNamespace(target_number=1, target_price=D("110"), status="PENDING")
    validate_brooks_execution_contract(
        direction="LONG",
        targets=(tm_target,),
        target_source_identities=(target,),
        stop_source_identity=stop,
        target_plan_lifecycle=plan,
        reversal_outcome_context=outcome,
    )


def test_tm_rejects_numeric_target_without_matching_typed_identity():
    target, stop, plan, outcome = typed_contract()
    wrong_numeric = SimpleNamespace(target_number=1, target_price=D("111"), status="PENDING")
    with pytest.raises(ValueError, match="typed target identity"):
        validate_brooks_execution_contract(
            direction="LONG",
            targets=(wrong_numeric,),
            target_source_identities=(target,),
            stop_source_identity=stop,
            target_plan_lifecycle=plan,
            reversal_outcome_context=outcome,
        )


def test_initial_stop_identity_and_target_history_survive_roundtrip():
    target, stop, plan, outcome = typed_contract()
    restored_target = TargetSourceIdentity.from_metadata(target.to_metadata())
    restored_stop = StopSourceIdentity.from_metadata(stop.to_metadata())
    restored_plan = TargetPlanLifecycle.from_metadata(plan.to_metadata())
    restored_outcome = ReversalOutcomeContext.from_metadata(outcome.to_metadata())
    assert restored_stop.source_id == "STOP:ORIGIN"
    assert restored_stop.stop_price == D("95")
    assert tuple(x.source_id for x in restored_target.sources) == ("SRC:A", "SRC:B")
    assert restored_plan.initial_stop_source_id == restored_stop.source_id
    assert set(restored_outcome.target_source_ids) == {"SRC:A", "SRC:B"}


def test_target_plan_identity_continuity_after_roundtrip():
    _, _, plan, outcome = typed_contract()
    restored_plan = TargetPlanLifecycle.from_metadata(plan.to_metadata())
    restored_outcome = ReversalOutcomeContext.from_metadata(outcome.to_metadata())
    assert restored_plan.plan_id == outcome.target_plan_id
    assert restored_plan.state == outcome.target_plan_state


def test_reversal_outcome_origin_continuity_after_roundtrip():
    _, _, _, outcome = typed_contract()
    restored = ReversalOutcomeContext.from_metadata(outcome.to_metadata())
    assert restored.context_id == outcome.context_id
    assert restored.reversal_origin_id == outcome.reversal_origin_id
    assert restored.available_at_index == outcome.available_at_index
    assert restored.transition_available_at is None


def test_malformed_persisted_bundle_fails_closed_without_price_reconstruction():
    metadata = SimpleNamespace(
        signal_id=4,
        analysis_metadata={
            "brooks_core_typed_contract": {
                "target_source_identities": [{"target_price": "110"}],
                "stop_source_identity": {"stop_price": "95"},
                "target_plan_lifecycle": None,
                "reversal_outcome_context": None,
            }
        },
    )
    service = object.__new__(LiveSignalLifecycleService)
    assert service._load_core_execution_contract(metadata=metadata) == ((), None, None, None)


def test_no_signal_execution_identity_contract_remains_strict():
    _, _, plan, outcome = typed_contract()
    with pytest.raises(ValueError, match="NO_SIGNAL"):
        BrooksEngineResult(
            decision="NO_SIGNAL",
            entry_price=None,
            stop_loss=None,
            targets=(),
            setup_type=None,
            reasoning=(),
            rule_ids=(),
            failed_rules=(),
            rule_evidence=(),
            engine_version="e",
            rule_set_version="r",
            configuration_version="c",
            target_plan_lifecycle=plan,
            reversal_outcome_context=outcome,
        )


def test_import_idempotency_is_not_changed_by_transport_metadata():
    typed = import_command()
    legacy = import_command(
        target_source_identities=(),
        stop_source_identity=None,
        target_plan_lifecycle=None,
        reversal_outcome_context=None,
    )
    assert typed.idempotency_key == legacy.idempotency_key


def test_transport_does_not_create_a_second_economic_opportunity():
    typed = import_command()
    legacy = import_command(
        target_source_identities=(),
        stop_source_identity=None,
        target_plan_lifecycle=None,
        reversal_outcome_context=None,
    )
    assert typed.source_signal_id == legacy.source_signal_id
    assert typed.idempotency_key == legacy.idempotency_key


def test_serialization_preserves_decimal_geometry_without_using_it_as_identity():
    target, stop, _, _ = typed_contract()
    target_payload = target.to_metadata()
    stop_payload = stop.to_metadata()
    assert target_payload["target_price"] == "110"
    assert target_payload["sources"][0]["source_id"] == "SRC:A"
    assert stop_payload["stop_price"] == "95"
    assert stop_payload["source_id"] == "STOP:ORIGIN"


def test_causal_indices_are_preserved_exactly():
    target, stop, plan, outcome = typed_contract()
    rt_target = TargetSourceIdentity.from_metadata(target.to_metadata())
    rt_stop = StopSourceIdentity.from_metadata(stop.to_metadata())
    rt_plan = TargetPlanLifecycle.from_metadata(plan.to_metadata())
    rt_outcome = ReversalOutcomeContext.from_metadata(outcome.to_metadata())
    assert rt_target.available_at_index == 20
    assert tuple(src.confirmed_at_index for src in rt_target.sources) == (8, 8)
    assert rt_stop.origin_index == 7 and rt_stop.available_at_index == 20
    assert rt_plan.evaluated_index == 20
    assert rt_outcome.available_at_index == 20


def test_tm_validator_does_not_change_entry_method_or_economic_identity_fields():
    c = candidate()
    target, stop, plan, outcome = typed_contract()
    tm_target = SimpleNamespace(target_number=1, target_price=D("110"), status="PENDING")
    before = (c.setup_type, c.entry_price, c.stop_loss, c.targets)
    validate_brooks_execution_contract(
        direction=c.direction,
        targets=(tm_target,),
        target_source_identities=(target,),
        stop_source_identity=stop,
        target_plan_lifecycle=plan,
        reversal_outcome_context=outcome,
    )
    after = (c.setup_type, c.entry_price, c.stop_loss, c.targets)
    assert after == before
