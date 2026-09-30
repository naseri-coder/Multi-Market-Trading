from decimal import Decimal as D
from types import SimpleNamespace

from app.modules.brooks_core.books_full_engine import BrooksTrilogyFullCoreEngine
from app.modules.operations.trade_management import (
    advance_reversal_outcome_context,
    build_trade_management_plan,
    reversal_outcome_management_mode,
)
from test_brooks_wave18_semantics import P, candidate
from test_brooks_wave19_semantics import pending_context, tm_targets, typed_foundations


def test_s01_080_positive_opposite_trend():
    out = advance_reversal_outcome_context(
        pending_context(), observed_direction="LONG", observed_always_in="LONG",
        observed_regime="BULL_TREND", transition_available_at="2026-09-18T10:00:00+00:00",
        transition_source_signal_id="TREND",
    )
    assert out.state == "OPPOSITE_TREND_OUTCOME"
    assert reversal_outcome_management_mode(out) == "SWING_RUNNER_MANAGEMENT"


def test_s02_080_near_miss_ambiguous_stays_pending():
    ctx = pending_context()
    out = advance_reversal_outcome_context(
        ctx, observed_direction="LONG", observed_always_in="UNRESOLVED",
        observed_regime="TRANSITION", transition_available_at="2026-09-18T10:00:00+00:00",
        transition_source_signal_id="AMB",
    )
    assert out is ctx


def test_s03_079_to_080_identity_continuity():
    ctx = pending_context()
    assert ctx.target_source_ids == ("SRC:A", "SRC:B")
    assert ctx.initial_stop_source_id == "STOP:ORIGIN"


def test_s04_wave18_target_plan_consumed_directly():
    engine = BrooksTrilogyFullCoreEngine(policy=P)
    target, stop, plan = typed_foundations()
    out = engine._reversal_outcome_context(
        candidate("LONG", "MAJOR_TREND_REVERSAL", setup="MTR"),
        context=SimpleNamespace(regime="BEAR_TREND", always_in="SHORT"),
        target_source_identities=(target,), stop_source_identity=stop,
        target_plan_lifecycle=plan,
    )
    assert out.target_plan_id == plan.plan_id
    assert out.target_plan_state == plan.state


def test_s05_numeric_only_target_stop_cannot_create_080():
    engine = BrooksTrilogyFullCoreEngine(policy=P)
    _, _, plan = typed_foundations()
    out = engine._reversal_outcome_context(
        candidate("LONG", "MAJOR_TREND_REVERSAL", setup="MTR"),
        context=SimpleNamespace(regime="BULL_TREND", always_in="LONG"),
        target_source_identities=(), stop_source_identity=None, target_plan_lifecycle=plan,
    )
    assert out is None


def test_s06_range_outcome_uses_existing_range_plan():
    ctx = advance_reversal_outcome_context(
        pending_context(), observed_direction="LONG", observed_always_in="LONG",
        observed_regime="TRADING_RANGE", transition_available_at="2026-09-18T10:00:00+00:00",
        transition_source_signal_id="RANGE",
    )
    plan = build_trade_management_plan(
        direction="LONG", entry_price=D("100"), initial_stop_loss=D("95"),
        targets=tm_targets(), market_regime="BEAR_TREND", reversal_outcome_context=ctx,
    )
    assert plan.context_class == "TRADING_RANGE"


def test_s07_failed_reversal_retains_stop_origin():
    ctx = advance_reversal_outcome_context(
        pending_context(), observed_direction="SHORT", observed_always_in="SHORT",
        observed_regime="BEAR_TREND", transition_available_at="2026-09-18T10:00:00+00:00",
        transition_source_signal_id="FAIL",
    )
    assert ctx.state == "FAILED_REVERSAL_OUTCOME"
    assert ctx.initial_stop_source_id == "STOP:ORIGIN"


def test_s08_coincident_target_semantics_survive_transition():
    ctx = advance_reversal_outcome_context(
        pending_context(), observed_direction="LONG", observed_always_in="LONG",
        observed_regime="BULL_TREND", transition_available_at="2026-09-18T10:00:00+00:00",
        transition_source_signal_id="TREND",
    )
    assert ctx.target_source_ids == ("SRC:A", "SRC:B")


def test_s09_terminal_state_not_backdated_or_rewritten():
    first = advance_reversal_outcome_context(
        pending_context(), observed_direction="LONG", observed_always_in="LONG",
        observed_regime="BULL_TREND", transition_available_at="2026-09-18T10:00:00+00:00",
        transition_source_signal_id="E1",
    )
    second = advance_reversal_outcome_context(
        first, observed_direction="SHORT", observed_always_in="SHORT",
        observed_regime="BEAR_TREND", transition_available_at="2026-09-18T11:00:00+00:00",
        transition_source_signal_id="E2",
    )
    assert second is first


def test_s10_context_is_not_entry_or_second_economic_signal():
    ctx = pending_context()
    assert ctx.trade_eligible is False


def test_s11_entry_method_policy_is_outside_080():
    ctx = pending_context()
    assert not hasattr(ctx, "entry_method")


def test_s12_tm_v6_numeric_policies_not_added_to_080_context():
    ctx = pending_context()
    data = ctx.to_metadata()
    assert "runner_fraction" not in data
    assert "target_exit_fractions" not in data
    assert "breakeven_distance" not in data


def test_s13_gate3_direction_contract_is_not_overridden():
    ctx = pending_context("LONG")
    out = advance_reversal_outcome_context(
        ctx, observed_direction="SHORT", observed_always_in="LONG",
        observed_regime="BULL_TREND", transition_available_at="2026-09-18T10:00:00+00:00",
        transition_source_signal_id="MIXED",
    )
    assert out.state == "PENDING_REVERSAL_OUTCOME"


def test_s14_mtr_gt12_policy_not_reintroduced():
    import inspect
    from app.modules.operations import trade_management
    assert "<=12" not in inspect.getsource(trade_management.advance_reversal_outcome_context)


def test_s15_final_flag_gt6_policy_not_reintroduced():
    import inspect
    from app.modules.operations import trade_management
    assert "<=6" not in inspect.getsource(trade_management.advance_reversal_outcome_context)
