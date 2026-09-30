from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.modules.brooks_core.books_full_engine import BrooksTrilogyFullCoreEngine
from app.modules.brooks_core.books_full_entities import BrooksPatternScan
from app.modules.brooks_core.engine_contract import (
    BrooksEngineResult,
    ReversalOutcomeContext,
    StopSourceIdentity,
    TargetPlanLifecycle,
    TargetSourceEvidence,
    TargetSourceIdentity,
)
from app.modules.brooks_core.entities import BrooksCoreDecision
from app.modules.brooks_core.mapper import to_paper_candidate
from app.modules.operations.lifecycle import LiveSignalLifecycleService
from app.modules.operations.trade_management import (
    advance_reversal_outcome_context,
    build_trade_management_plan,
    market_regime_for_reversal_outcome,
    reversal_outcome_management_mode,
)
from test_brooks_wave18_semantics import P, adv_none, candidate, flat_bars, snap

BASE = datetime(2026, 9, 18, tzinfo=UTC)


def typed_foundations(direction="LONG", plan_state="REVERSAL_OR_TRANSITION"):
    a = TargetSourceEvidence("PATTERN_MEASURED_MOVE", "SRC:A", 5, 8, direction, "PAT:A")
    b = TargetSourceEvidence("FAILED_REVERSAL_ENTRY_PRICE", "SRC:B", 6, 8, direction, "FAIL:B")
    target = TargetSourceIdentity(1, D("110") if direction == "LONG" else D("90"), (a, b), 20)
    stop = StopSourceIdentity(
        D("95") if direction == "LONG" else D("105"),
        "INITIAL_PROTECTIVE_STOP",
        "STOP:ORIGIN",
        D("96") if direction == "LONG" else D("104"),
        7,
        20,
        "SETUP_STRUCTURE",
        direction=direction,
    )
    plan = TargetPlanLifecycle(
        "PLAN:REV:1",
        plan_state,
        direction,
        20,
        target_source_ids=("SRC:A", "SRC:B"),
        initial_stop_source_id="STOP:ORIGIN",
    )
    return target, stop, plan


def pending_context(direction="LONG"):
    target, stop, plan = typed_foundations(direction)
    return ReversalOutcomeContext(
        "OUTCOME:1",
        "OPPORTUNITY:REV:1",
        direction,
        "PENDING_REVERSAL_OUTCOME",
        20,
        20,
        tuple(x.source_id for x in target.sources),
        stop.source_id,
        plan.plan_id,
        plan.state,
    )


def tm_targets(direction="LONG"):
    return (
        SimpleNamespace(target_number=1, target_price=D("110") if direction == "LONG" else D("90"), status="PENDING"),
        SimpleNamespace(target_number=2, target_price=D("120") if direction == "LONG" else D("80"), status="PENDING"),
    )


def test_080_core_pending_context_consumes_079_and_050_identity():
    engine = BrooksTrilogyFullCoreEngine(policy=P)
    c = candidate("LONG", "MAJOR_TREND_REVERSAL", setup="MTR")
    target, stop, plan = typed_foundations()
    out = engine._reversal_outcome_context(
        c,
        context=SimpleNamespace(regime="BEAR_TREND", always_in="SHORT"),
        target_source_identities=(target,),
        stop_source_identity=stop,
        target_plan_lifecycle=plan,
    )
    assert out is not None
    assert out.state == "PENDING_REVERSAL_OUTCOME"
    assert out.target_source_ids == ("SRC:A", "SRC:B")
    assert out.initial_stop_source_id == stop.source_id
    assert out.target_plan_id == plan.plan_id
    assert out.reversal_origin_id


def test_080_core_opposite_trend_outcome_is_candidate_relative():
    engine = BrooksTrilogyFullCoreEngine(policy=P)
    target, stop, plan = typed_foundations()
    c = candidate("LONG", "MAJOR_TREND_REVERSAL", setup="MTR")
    out = engine._reversal_outcome_context(
        c,
        context=SimpleNamespace(regime="BULL_TREND", always_in="LONG"),
        target_source_identities=(target,),
        stop_source_identity=stop,
        target_plan_lifecycle=plan,
    )
    assert out.state == "OPPOSITE_TREND_OUTCOME"


def test_080_core_range_outcome_is_typed_not_entry():
    engine = BrooksTrilogyFullCoreEngine(policy=P)
    target, stop, plan = typed_foundations()
    c = candidate("LONG", "WEDGE_REVERSAL", setup="WEDGE")
    out = engine._reversal_outcome_context(
        c,
        context=SimpleNamespace(regime="TRADING_RANGE", always_in="LONG"),
        target_source_identities=(target,),
        stop_source_identity=stop,
        target_plan_lifecycle=plan,
    )
    assert out.state == "TRADING_RANGE_OUTCOME"
    assert out.trade_eligible is False


def test_080_numeric_geometry_without_079_identity_fails_closed():
    engine = BrooksTrilogyFullCoreEngine(policy=P)
    c = candidate("LONG", "MAJOR_TREND_REVERSAL", setup="MTR")
    _, _, plan = typed_foundations()
    assert engine._reversal_outcome_context(
        c,
        context=SimpleNamespace(regime="BULL_TREND", always_in="LONG"),
        target_source_identities=(),
        stop_source_identity=None,
        target_plan_lifecycle=plan,
    ) is None


def test_080_non_reversal_family_does_not_create_management_context():
    engine = BrooksTrilogyFullCoreEngine(policy=P)
    target, stop, plan = typed_foundations()
    c = candidate("LONG", "TREND_CONTINUATION", setup="H2")
    assert engine._reversal_outcome_context(
        c,
        context=SimpleNamespace(regime="BULL_TREND", always_in="LONG"),
        target_source_identities=(target,),
        stop_source_identity=stop,
        target_plan_lifecycle=plan,
    ) is None


def test_080_079_identity_is_enforced_by_engine_result():
    target, stop, plan = typed_foundations()
    ctx = pending_context()
    good = BrooksEngineResult(
        decision="LONG", entry_price=D("100"), stop_loss=D("95"), targets=(D("110"),),
        setup_type="MTR", reasoning=("r",), rule_ids=(), failed_rules=(), rule_evidence=(),
        engine_version="e", rule_set_version="r", configuration_version="c",
        target_source_identities=(target,), stop_source_identity=stop,
        target_plan_lifecycle=plan, reversal_outcome_context=ctx,
    )
    assert good.reversal_outcome_context is ctx
    wrong = ReversalOutcomeContext(
        ctx.context_id, ctx.reversal_origin_id, ctx.direction, ctx.state, 20, 20,
        ("NOT:THE:SOURCE",), ctx.initial_stop_source_id, ctx.target_plan_id, ctx.target_plan_state,
    )
    with pytest.raises(ValueError):
        BrooksEngineResult(
            decision="LONG", entry_price=D("100"), stop_loss=D("95"), targets=(D("110"),),
            setup_type="MTR", reasoning=("r",), rule_ids=(), failed_rules=(), rule_evidence=(),
            engine_version="e", rule_set_version="r", configuration_version="c",
            target_source_identities=(target,), stop_source_identity=stop,
            target_plan_lifecycle=plan, reversal_outcome_context=wrong,
        )


def test_080_no_signal_cannot_carry_management_context():
    with pytest.raises(ValueError):
        BrooksEngineResult(
            decision="NO_SIGNAL", entry_price=None, stop_loss=None, targets=(), setup_type=None,
            reasoning=("none",), rule_ids=(), failed_rules=(), rule_evidence=(),
            engine_version="e", rule_set_version="r", configuration_version="c",
            reversal_outcome_context=pending_context(),
        )


def test_080_context_propagates_decision_to_paper_without_new_candidate():
    target, stop, plan = typed_foundations()
    ctx = pending_context()
    snapshot = snap(flat_bars())
    decision = BrooksCoreDecision(
        decision="LONG", source_signal_id="SIG", entry_price=D("100"), stop_loss=D("95"),
        targets=(D("110"),), setup_type="MTR", reasoning=("r",), rule_ids=(),
        failed_rules=(), rule_evidence=(), engine_version="e", rule_set_version="r",
        configuration_version="c", market_snapshot_id=snapshot.snapshot_id,
        market_snapshot_hash=snapshot.snapshot_hash, chart_path="/tmp/x.png",
        target_source_identities=(target,), stop_source_identity=stop,
        target_plan_lifecycle=plan, reversal_outcome_context=ctx,
    )
    paper = to_paper_candidate(snapshot=snapshot, decision=decision)
    assert paper is not None
    assert paper.reversal_outcome_context is ctx
    assert paper.target_plan_lifecycle is plan
    assert paper.target_source_identities == (target,)
    assert paper.stop_source_identity is stop


@pytest.mark.asyncio
async def test_080_evaluate_emits_typed_context_and_rule_evidence():
    engine = BrooksTrilogyFullCoreEngine(policy=replace(P, enable_trade_decisions=True))
    snapshot = snap(flat_bars(80))
    c = candidate("LONG", "MAJOR_TREND_REVERSAL", signal_index=79, setup="MTR")
    src = TargetSourceEvidence("PATTERN_MEASURED_MOVE", "SRC:EVAL", 70, 75, "LONG", "MTR:70")
    target = TargetSourceIdentity(1, D("110"), (src,), 79)
    stop = StopSourceIdentity(
        D("95"), "INITIAL_PROTECTIVE_STOP", "STOP:EVAL", D("96"), 70, 79,
        "SETUP_STRUCTURE", direction="LONG",
    )
    plan = TargetPlanLifecycle(
        "PLAN:EVAL", "REVERSAL_OR_TRANSITION", "LONG", 79,
        target_source_ids=("SRC:EVAL",), initial_stop_source_id="STOP:EVAL",
    )
    ctx = SimpleNamespace(regime="BULL_TREND", structure_direction="UP", always_in="LONG")
    probability = SimpleNamespace(band=SimpleNamespace(value="HIGHER"), reasons=("source-valid",))
    scan = BrooksPatternScan((c,), (), ())

    with patch("app.modules.brooks_core.books_full_engine.assess_books_context", return_value=ctx),          patch("app.modules.brooks_core.books_full_engine.assess_advanced_context", return_value=adv_none()),          patch("app.modules.brooks_core.books_full_engine.build_market_context", return_value=SimpleNamespace()),          patch("app.modules.brooks_core.books_full_engine.scan_full_brooks_patterns", return_value=scan),          patch("app.modules.brooks_core.books_full_engine.assess_higher_probability", return_value=probability),          patch.object(engine, "_context_contract_status", return_value=("PASS", "ok")),          patch.object(engine, "_barbwire_stop_entry_veto", return_value=False),          patch.object(engine, "_context_evidence", return_value=()),          patch.object(engine, "_observation_evidence", return_value=()),          patch.object(engine, "_candidate_evidence", return_value=()),          patch.object(engine, "_choose_candidate", return_value=c),          patch.object(engine, "_execution_geometry_with_identity", return_value=(D("100"), D("95"), (D("110"),), "existing", "pattern", (target,), stop)),          patch.object(engine, "_target_plan_lifecycle", return_value=plan):
        result = await engine.evaluate(snapshot)

    assert result.reversal_outcome_context is not None
    assert result.reversal_outcome_context.state == "OPPOSITE_TREND_OUTCOME"
    assert result.reversal_outcome_context.target_plan_id == plan.plan_id
    assert "SRC:EVAL" in result.reversal_outcome_context.target_source_ids
    evidence = [x for x in result.rule_evidence if x.rule_id == "BROOKS-GAP-080"]
    assert len(evidence) == 1
    pairs = dict(evidence[0].evidence)
    assert pairs["state"] == "OPPOSITE_TREND_OUTCOME"
    assert pairs["initial_stop_source_id"] == "STOP:EVAL"


def test_080_transition_to_opposite_trend_preserves_origin_identity():
    ctx = pending_context()
    out = advance_reversal_outcome_context(
        ctx,
        observed_direction="LONG",
        observed_always_in="LONG",
        observed_regime="BULL_TREND",
        transition_available_at="2026-09-18T10:00:00+00:00",
        transition_source_signal_id="EVIDENCE:TREND",
    )
    assert out.state == "OPPOSITE_TREND_OUTCOME"
    assert out.reversal_origin_id == ctx.reversal_origin_id
    assert out.target_source_ids == ctx.target_source_ids
    assert out.initial_stop_source_id == ctx.initial_stop_source_id
    assert reversal_outcome_management_mode(out) == "SWING_RUNNER_MANAGEMENT"


def test_080_transition_to_range_preserves_origin_identity():
    ctx = pending_context()
    out = advance_reversal_outcome_context(
        ctx,
        observed_direction="SHORT",
        observed_always_in="SHORT",
        observed_regime="TRADING_RANGE",
        transition_available_at="2026-09-18T10:00:00+00:00",
        transition_source_signal_id="EVIDENCE:RANGE",
    )
    assert out.state == "TRADING_RANGE_OUTCOME"
    assert out.context_id == ctx.context_id
    assert reversal_outcome_management_mode(out) == "AGGRESSIVE_RANGE_PROFIT_TAKING"


def test_080_transition_to_failed_reversal_preserves_initial_stop_history():
    ctx = pending_context()
    out = advance_reversal_outcome_context(
        ctx,
        observed_direction="SHORT",
        observed_always_in="SHORT",
        observed_regime="BEAR_TREND",
        transition_available_at="2026-09-18T10:00:00+00:00",
        transition_source_signal_id="EVIDENCE:FAIL",
    )
    assert out.state == "FAILED_REVERSAL_OUTCOME"
    assert out.initial_stop_source_id == "STOP:ORIGIN"
    assert reversal_outcome_management_mode(out) == "EXIT_OR_CONTINUATION"


def test_080_near_miss_ambiguous_evidence_keeps_pending():
    ctx = pending_context()
    out = advance_reversal_outcome_context(
        ctx,
        observed_direction="LONG",
        observed_always_in="UNRESOLVED",
        observed_regime="TRANSITION",
        transition_available_at="2026-09-18T10:00:00+00:00",
        transition_source_signal_id="EVIDENCE:AMB",
    )
    assert out is ctx


def test_080_terminal_outcome_is_not_rewritten_by_later_evidence():
    ctx = advance_reversal_outcome_context(
        pending_context(),
        observed_direction="LONG", observed_always_in="LONG", observed_regime="BULL_TREND",
        transition_available_at="2026-09-18T10:00:00+00:00", transition_source_signal_id="E1",
    )
    later = advance_reversal_outcome_context(
        ctx,
        observed_direction="SHORT", observed_always_in="SHORT", observed_regime="BEAR_TREND",
        transition_available_at="2026-09-18T11:00:00+00:00", transition_source_signal_id="E2",
    )
    assert later is ctx


def test_080_tm_range_context_reuses_existing_range_economics():
    targets = tm_targets()
    baseline = build_trade_management_plan(
        direction="LONG", entry_price=D("100"), initial_stop_loss=D("95"),
        targets=targets, market_regime="TRADING_RANGE",
    )
    ctx = pending_context()
    resolved = advance_reversal_outcome_context(
        ctx, observed_direction="LONG", observed_always_in="LONG", observed_regime="TRADING_RANGE",
        transition_available_at="2026-09-18T10:00:00+00:00", transition_source_signal_id="R",
    )
    routed = build_trade_management_plan(
        direction="LONG", entry_price=D("100"), initial_stop_loss=D("95"),
        targets=targets, market_regime="BEAR_TREND", reversal_outcome_context=resolved,
    )
    assert routed.context_class == "TRADING_RANGE"
    assert routed.target_exit_fractions == baseline.target_exit_fractions
    assert routed.runner_fraction == baseline.runner_fraction


def test_080_tm_trend_context_reuses_existing_trend_economics():
    targets = tm_targets()
    baseline = build_trade_management_plan(
        direction="LONG", entry_price=D("100"), initial_stop_loss=D("95"),
        targets=targets, market_regime="BULL_TREND",
    )
    resolved = advance_reversal_outcome_context(
        pending_context(), observed_direction="LONG", observed_always_in="LONG",
        observed_regime="BULL_TREND", transition_available_at="2026-09-18T10:00:00+00:00",
        transition_source_signal_id="T",
    )
    routed = build_trade_management_plan(
        direction="LONG", entry_price=D("100"), initial_stop_loss=D("95"),
        targets=targets, market_regime="TRADING_RANGE", reversal_outcome_context=resolved,
    )
    assert routed.context_class == "STRONG_TREND"
    assert routed.target_exit_fractions == baseline.target_exit_fractions
    assert routed.runner_fraction == baseline.runner_fraction


@pytest.mark.asyncio
async def test_080_runtime_loads_serialized_core_evidence_not_price():
    svc = LiveSignalLifecycleService(
        database=None, provider=None, bot=None, vip_channel_id=1, cutover_at=BASE, candle_limit=10
    )
    row = SimpleNamespace(
        evidence=[
            ["context_id", "OUT:1"], ["reversal_origin_id", "ORIGIN:1"], ["direction", "LONG"],
            ["state", "PENDING_REVERSAL_OUTCOME"], ["evaluated_index", "20"],
            ["available_at_index", "20"], ["target_source_ids", "SRC:A|SRC:B"],
            ["initial_stop_source_id", "STOP:ORIGIN"], ["target_plan_id", "PLAN:REV:1"],
            ["target_plan_state", "REVERSAL_OR_TRANSITION"],
        ]
    )
    session = SimpleNamespace(scalar=AsyncMock(return_value=row), flush=AsyncMock())
    metadata = SimpleNamespace(signal_id=7, analysis_metadata={})
    out = await svc._load_reversal_outcome_context(session=session, metadata=metadata)
    assert out is not None
    assert out.target_source_ids == ("SRC:A", "SRC:B")
    assert out.initial_stop_source_id == "STOP:ORIGIN"
    assert metadata.analysis_metadata["brooks_reversal_outcome"]["target_plan_id"] == "PLAN:REV:1"


@pytest.mark.asyncio
async def test_080_runtime_transition_uses_only_supplied_causal_approved_evidence():
    svc = LiveSignalLifecycleService(
        database=None, provider=None, bot=None, vip_channel_id=1, cutover_at=BASE, candle_limit=10
    )
    evidence = SimpleNamespace(
        exchange="binance", market_type="futures", symbol="BTCUSDT", timeframe="15m",
        direction="LONG", always_in="LONG", context={"regime": "BULL_TREND"},
        approved_at=BASE + timedelta(minutes=20), candle_closed_at=BASE + timedelta(minutes=15),
        source_signal_id="APPROVED:2",
    )
    session = SimpleNamespace(
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [evidence])),
        flush=AsyncMock(),
    )
    repo = SimpleNamespace(append_event=AsyncMock(return_value=SimpleNamespace(id=1)))
    metadata = SimpleNamespace(
        signal_id=7, analysis_metadata={"brooks_reversal_outcome": pending_context().to_metadata()},
        generation_mode="LIVE", exchange="binance", market_type="futures", timeframe="15m",
    )
    signal = SimpleNamespace(id=7, symbol="BTCUSDT")
    candle = SimpleNamespace(open_time=BASE + timedelta(minutes=30), close_time=BASE + timedelta(minutes=31))
    out = await svc._advance_reversal_outcome(
        session=session, repo=repo, signal=signal, metadata=metadata,
        entry_at=BASE + timedelta(minutes=5), candle=candle, context=pending_context(),
    )
    assert out.state == "OPPOSITE_TREND_OUTCOME"
    assert metadata.analysis_metadata["brooks_reversal_outcome"]["state"] == "OPPOSITE_TREND_OUTCOME"
    assert repo.append_event.await_count == 1


@pytest.mark.asyncio
async def test_080_prefix_without_available_evidence_stays_pending():
    svc = LiveSignalLifecycleService(
        database=None, provider=None, bot=None, vip_channel_id=1, cutover_at=BASE, candle_limit=10
    )
    session = SimpleNamespace(
        scalars=AsyncMock(return_value=SimpleNamespace(all=lambda: [])),
        flush=AsyncMock(),
    )
    repo = SimpleNamespace(append_event=AsyncMock())
    metadata = SimpleNamespace(
        signal_id=7, analysis_metadata={}, generation_mode="LIVE",
        exchange="binance", market_type="futures", timeframe="15m",
    )
    signal = SimpleNamespace(id=7, symbol="BTCUSDT")
    candle = SimpleNamespace(open_time=BASE + timedelta(minutes=10), close_time=BASE + timedelta(minutes=11))
    ctx = pending_context()
    out = await svc._advance_reversal_outcome(
        session=session, repo=repo, signal=signal, metadata=metadata,
        entry_at=BASE + timedelta(minutes=5), candle=candle, context=ctx,
    )
    assert out is ctx
    repo.append_event.assert_not_awaited()


def test_080_metadata_roundtrip_preserves_coincident_sources_and_initial_stop():
    ctx = pending_context()
    restored = ReversalOutcomeContext.from_metadata(ctx.to_metadata())
    assert restored == ctx
    assert restored.target_source_ids == ("SRC:A", "SRC:B")
    assert restored.initial_stop_source_id == "STOP:ORIGIN"


def test_080_management_context_is_not_trade_eligibility_or_new_candidate():
    ctx = pending_context()
    assert ctx.trade_eligible is False
    assert market_regime_for_reversal_outcome(ctx, "BEAR_TREND") == "BEAR_TREND"
    assert reversal_outcome_management_mode(ctx) == "PENDING_REVERSAL_MANAGEMENT"
