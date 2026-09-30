from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.modules.operations.trade_management import build_trade_management_plan
from app.modules.scale_in.accounting import PositionLedger
from app.modules.scale_in.entities import (
    EntryFill, ExitFill, PositionState, ReconciliationStatus,
    ScaleExecutionState, ScaleInCategory,
)
from app.modules.scale_in.policy import ScaleInPolicyContext, evaluate_policy
from app.modules.scale_in.reconciliation import ExchangeExecutionTruth, reconcile
from app.modules.scale_in.risk import assess_scale_in, max_safe_add_qty
from app.modules.scale_in.state_machine import transition
from app.modules.scale_in.tm_adapter import (
    planned_runner_qty, planned_target_qty, remaining_runner_qty,
    remaining_target_qty, stop_order_qty,
)

NOW = datetime(2026, 9, 14, tzinfo=UTC)
D = Decimal


def entry(key: str, price: str, qty: str, *, requested: str | None = None,
          direction: str = "LONG", seq: int = 0, fee: str = "0",
          buffer: str = "0", metadata=None) -> EntryFill:
    return EntryFill(
        execution_key=key, position_id="P1", direction=direction,
        filled_qty=D(qty), requested_qty=D(requested or qty), fill_price=D(price),
        fill_time=NOW, entry_reason="TEST", scale_sequence_number=seq,
        structural_stop_at_entry=D("90") if direction == "LONG" else D("110"),
        risk_budget_at_entry=D("100"), fee=D(fee), risk_buffer_per_unit=D(buffer),
        metadata=metadata or {},
    )


def exit_fill(key: str, price: str, qty: str, *, fee: str = "0", target=None, reason="TARGET") -> ExitFill:
    return ExitFill(
        execution_key=key, position_id="P1", filled_qty=D(qty), fill_price=D(price),
        fill_time=NOW, exit_reason=reason, fee=D(fee), target_number=target,
    )


def ledger(*, budget="100", stop="90", direction="LONG") -> PositionLedger:
    return PositionLedger(position_id="P1", direction=direction,
                          initial_trade_risk_budget=D(budget), executable_stop=D(stop))


def test_single_entry_backwards_compatible_basis():
    p = ledger()
    assert p.apply_entry_fill(entry("f1", "100", "5")) is True
    assert p.open_qty == 5 and p.avg_entry == 100 and p.current_aggregate_risk == 50


def test_two_entry_weighted_average():
    p = ledger(budget="200")
    p.apply_entry_fill(entry("f1", "100", "2"))
    p.apply_entry_fill(entry("f2", "95", "2", seq=1))
    assert p.avg_entry == D("97.5") and p.open_qty == 4


def test_three_entry_weighted_average():
    p = ledger(budget="300")
    p.apply_entry_fill(entry("f1", "100", "1"))
    p.apply_entry_fill(entry("f2", "96", "2", seq=1))
    p.apply_entry_fill(entry("f3", "94", "3", seq=2))
    assert p.avg_entry == D("95.66666666666666666666666667")


def test_partial_fill_only_filled_quantity_changes_basis():
    p = ledger(budget="200")
    p.apply_entry_fill(entry("order1-fill1", "100", "2", requested="5"))
    assert p.open_qty == 2 and p.avg_entry == 100


def test_multiple_partial_fills_same_order_are_distinct_confirmed_fills():
    p = ledger(budget="200")
    p.apply_entry_fill(entry("o1:t1", "100", "2", requested="5"))
    p.apply_entry_fill(entry("o1:t2", "98", "3", requested="5"))
    assert p.open_qty == 5 and p.avg_entry == D("98.8")


def test_unfilled_cancel_state_never_touches_accounting():
    p = ledger()
    state = transition(ScaleExecutionState.SCALE_IN_PROPOSED, ScaleExecutionState.SCALE_IN_APPROVED)
    state = transition(state, ScaleExecutionState.SCALE_IN_CANCELLED)
    assert state is ScaleExecutionState.SCALE_IN_CANCELLED
    assert p.open_qty == 0 and p.avg_entry is None


def test_rejected_add_never_touches_accounting():
    p = ledger(budget="10")
    p.apply_entry_fill(entry("f1", "100", "1"))
    before = (p.open_qty, p.avg_entry)
    decision = assess_scale_in(direction="LONG", lots=p.open_lots(), executable_stop=D("90"),
                               initial_trade_risk_budget=D("10"), requested_qty=D("1"),
                               expected_price=D("100"), qty_step=D("0.001"))
    assert not decision.approved and (p.open_qty, p.avg_entry) == before


def test_duplicate_entry_fill_exactly_once():
    p = ledger()
    f = entry("same", "100", "2")
    assert p.apply_entry_fill(f) is True
    before = (p.open_qty, p.avg_entry, p.realized_net_pnl)
    assert p.apply_entry_fill(f) is False
    assert (p.open_qty, p.avg_entry, p.realized_net_pnl) == before


def test_duplicate_exit_fill_exactly_once():
    p = ledger()
    p.apply_entry_fill(entry("f1", "100", "2"))
    f = exit_fill("x1", "105", "1")
    assert p.apply_exit_fill(f) is True
    before = (p.open_qty, p.realized_net_pnl)
    assert p.apply_exit_fill(f) is False
    assert (p.open_qty, p.realized_net_pnl) == before


def test_out_of_order_fill_requires_recovery_flag():
    with pytest.raises(ValueError):
        transition(ScaleExecutionState.SCALE_IN_APPROVED, ScaleExecutionState.SCALE_IN_FILLED)
    assert transition(ScaleExecutionState.SCALE_IN_APPROVED, ScaleExecutionState.SCALE_IN_FILLED,
                      recovery=True) is ScaleExecutionState.SCALE_IN_FILLED


def test_restart_after_pending_add_reconciles_in_sync():
    result = reconcile(local_open_qty=D("2"), local_fill_keys=("f1",),
                       exchange=ExchangeExecutionTruth(D("2"), ("f1",), "OPEN"))
    assert result.status is ReconciliationStatus.IN_SYNC


def test_restart_after_exchange_fill_detects_exchange_ahead_and_never_resends_by_itself():
    result = reconcile(local_open_qty=D("1"), local_fill_keys=("f1",),
                       exchange=ExchangeExecutionTruth(D("2"), ("f1", "f2"), "FILLED"))
    assert result.status is ReconciliationStatus.EXCHANGE_AHEAD
    assert result.missing_exchange_fill_keys == ("f2",)


def test_db_ahead_of_exchange_fails_closed():
    result = reconcile(local_open_qty=D("2"), local_fill_keys=("f1", "f2"),
                       exchange=ExchangeExecutionTruth(D("1"), ("f1",), "OPEN"))
    assert result.status is ReconciliationStatus.DB_AHEAD


def test_risk_budget_exact_boundary_approved():
    p = ledger(budget="20")
    p.apply_entry_fill(entry("f1", "100", "1"))
    d = assess_scale_in(direction="LONG", lots=p.open_lots(), executable_stop=D("90"),
                        initial_trade_risk_budget=D("20"), requested_qty=D("1"),
                        expected_price=D("100"), qty_step=D("0.1"))
    assert d.approved and d.post_scale_aggregate_risk == 20


def test_risk_budget_one_unit_over_rejected_without_clamp():
    p = ledger(budget="19")
    p.apply_entry_fill(entry("f1", "100", "1"))
    d = assess_scale_in(direction="LONG", lots=p.open_lots(), executable_stop=D("90"),
                        initial_trade_risk_budget=D("19"), requested_qty=D("1"),
                        expected_price=D("100"), qty_step=D("0.1"))
    assert not d.approved and d.max_safe_add_qty == D("0.9")


def test_zero_remaining_budget_rejected():
    p = ledger(budget="10")
    p.apply_entry_fill(entry("f1", "100", "1"))
    assert max_safe_add_qty(remaining_risk_budget=p.remaining_risk_budget, direction="LONG",
                            expected_price=D("100"), executable_stop=D("90"), desired_qty=D("1"),
                            qty_step=D("0.1")) == 0


def test_wrong_direction_fill_rejected():
    p = ledger()
    with pytest.raises(ValueError):
        p.apply_entry_fill(entry("f1", "100", "1", direction="SHORT"))


def test_position_already_closing_rejects_add():
    p = ledger(); p.state = PositionState.EXIT_PENDING
    with pytest.raises(ValueError):
        p.apply_entry_fill(entry("f1", "100", "1"))


def test_stop_widening_is_forbidden():
    p = ledger(); p.apply_entry_fill(entry("f1", "100", "1"))
    with pytest.raises(ValueError):
        p.update_executable_stop(D("89"))
    p.update_executable_stop(D("95"))
    assert p.executable_stop == 95


def test_exchange_precision_rounds_down():
    qty = max_safe_add_qty(remaining_risk_budget=D("5"), direction="LONG",
                           expected_price=D("100"), executable_stop=D("97"),
                           desired_qty=D("2"), qty_step=D("0.01"))
    assert qty == D("1.66")


def test_minimum_notional_can_make_safe_quantity_untradable():
    qty = max_safe_add_qty(remaining_risk_budget=D("1"), direction="LONG",
                           expected_price=D("10"), executable_stop=D("9"),
                           desired_qty=D("1"), qty_step=D("0.1"), min_notional=D("20"))
    assert qty == 0


def test_fee_slippage_risk_buffer_reduces_max_safe_quantity():
    plain = max_safe_add_qty(remaining_risk_budget=D("10"), direction="LONG",
                             expected_price=D("100"), executable_stop=D("95"), desired_qty=D("5"),
                             qty_step=D("0.01"))
    buffered = max_safe_add_qty(remaining_risk_budget=D("10"), direction="LONG",
                                expected_price=D("100"), executable_stop=D("95"), desired_qty=D("5"),
                                qty_step=D("0.01"), risk_buffer_per_unit=D("1"))
    assert buffered < plain


def test_partial_exit_after_scale_in_uses_average_cost_and_preserves_basis():
    p = ledger(budget="200")
    p.apply_entry_fill(entry("f1", "100", "1"))
    p.apply_entry_fill(entry("f2", "96", "1", seq=1))
    assert p.avg_entry == 98
    p.apply_exit_fill(exit_fill("x1", "102", "1"))
    assert p.open_qty == 1 and p.avg_entry == 98 and p.realized_net_pnl == 4
    assert sum(l.open_qty for l in p.lots) == 1


def test_multiple_exits_after_multiple_entries_reconcile():
    p = ledger(budget="300")
    p.apply_entry_fill(entry("f1", "100", "2")); p.apply_entry_fill(entry("f2", "95", "2", seq=1))
    p.apply_exit_fill(exit_fill("x1", "105", "1")); p.apply_exit_fill(exit_fill("x2", "110", "2"))
    assert p.open_qty == 1 and sum(l.open_qty for l in p.lots) == 1


def test_full_stop_after_scale_in_closes_position():
    p = ledger(budget="200")
    p.apply_entry_fill(entry("f1", "100", "1")); p.apply_entry_fill(entry("f2", "95", "1", seq=1))
    p.apply_exit_fill(exit_fill("stop", "90", "2", reason="STOP"))
    assert p.state is PositionState.CLOSED and p.open_qty == 0 and p.avg_entry is None


@dataclass
class Target:
    target_number: int
    target_price: Decimal
    status: str = "PENDING"


def tm_metadata(entry_price=D("100")):
    plan = build_trade_management_plan(direction="LONG", entry_price=entry_price,
        initial_stop_loss=D("90"), targets=(Target(1,D("120")), Target(2,D("130"))),
        market_regime="BULL_TREND", context_metadata={"channel_quality":"TIGHT"})
    return {"tm_plan": plan.to_metadata()}


def test_tm_v6_multi_lot_target_and_runner_quantities_are_additive():
    p = ledger(budget="300")
    p.apply_entry_fill(entry("f1","100","2", metadata=tm_metadata()))
    p.apply_entry_fill(entry("f2","95","1",seq=1, metadata=tm_metadata(D("95"))))
    assert planned_target_qty(p.lots, 1) == D("1.5")
    assert planned_runner_qty(p.lots) == D("0.75")
    assert stop_order_qty(p.open_qty) == 3


def test_tm_v6_target_and_runner_remaining_after_exits():
    class E:
        def __init__(self,q,target=None,reason="TARGET"):
            self.filled_qty=D(q); self.target_number=target; self.exit_reason=reason
    p = ledger(budget="300"); p.apply_entry_fill(entry("f1","100","2", metadata=tm_metadata()))
    exits=(E("0.5",1), E("0.25",None,"RUNNER"))
    assert remaining_target_qty(p.lots, exits, 1) == D("0.5")
    assert remaining_runner_qty(p.lots, exits) == D("0.25")


def test_realized_unrealized_and_total_r_use_immutable_budget():
    p = ledger(budget="100")
    p.apply_entry_fill(entry("f1","100","5",fee="1"))
    p.apply_exit_fill(exit_fill("x1","110","2",fee="1"))
    assert p.realized_net_pnl == 18
    assert p.realized_r == D("0.18")
    assert p.unrealized_pnl(D("105")) == 15
    assert p.unrealized_r(D("105")) == D("0.15")
    assert p.total_trade_r(D("105")) == D("0.33")


def ctx(**kwargs):
    base=dict(direction="LONG", position_state=PositionState.OPEN, always_in="LONG",
              market_regime="BULL_TREND", setup_type="BREAKOUT_PULLBACK_LONG",
              full_pipeline_approved=True, premise_valid=True, unrealized_pnl=D("5"))
    base.update(kwargs); return ScaleInPolicyContext(**base)


def test_source_policy_pullback_positive():
    d=evaluate_policy(ctx())
    assert d.approved and d.category is ScaleInCategory.ADD_ON_PULLBACK


def test_source_policy_winner_positive():
    d=evaluate_policy(ctx(setup_type="BREAKOUT_LONG"))
    assert d.approved and d.category is ScaleInCategory.ADD_TO_WINNER


def test_source_policy_after_confirmation_positive():
    d=evaluate_policy(ctx(setup_type="TWO_BAR_REVERSAL_LONG",unrealized_pnl=D("0")))
    assert d.approved and d.category is ScaleInCategory.ADD_AFTER_CONFIRMATION


def test_source_policy_wrong_context_rejects_range_for_v1():
    assert not evaluate_policy(ctx(market_regime="TRADING_RANGE")).approved


def test_source_policy_always_in_flip_rejects():
    assert not evaluate_policy(ctx(always_in="SHORT")).approved


def test_source_policy_adverse_averaging_category_is_not_enabled():
    d=evaluate_policy(ctx(), category=ScaleInCategory.AVERAGE_INTO_ADVERSE_MOVE)
    assert not d.approved and d.reason == "CATEGORY_NOT_ENABLED_V1"


def test_source_policy_requires_fresh_full_pipeline_confirmation():
    assert not evaluate_policy(ctx(full_pipeline_approved=False)).approved


def test_property_invariants_many_generated_valid_states():
    rng=random.Random(260914)
    for case in range(250):
        stop=D(str(rng.randint(80,95)))
        p=ledger(budget="10000",stop=str(stop))
        for i in range(rng.randint(1,5)):
            price=D(str(rng.randint(96,120)))
            qty=D(str(rng.randint(1,5)))
            p.apply_entry_fill(entry(f"{case}-e{i}",str(price),str(qty),seq=i))
        if p.open_qty > 0:
            close_qty=D(str(rng.randint(0,int(p.open_qty))))
            if close_qty > 0:
                p.apply_exit_fill(exit_fill(f"{case}-x",str(rng.randint(90,125)),str(close_qty)))
        assert p.open_qty >= 0
        assert sum(l.open_qty for l in p.lots) == p.open_qty
        assert p.current_aggregate_risk <= p.initial_trade_risk_budget
        assert p.realized_net_pnl.is_finite()
        assert p.remaining_risk_budget >= 0
        if p.open_qty == 0:
            assert p.state is PositionState.CLOSED

from app.modules.scale_in.shadow import ShadowScaleInEvaluator
from app.modules.scale_in.shadow_runtime import seed_shadow_position, evaluate_shadow_candidate


def test_shadow_evaluator_never_mutates_real_ledger():
    p=ledger(budget="100")
    p.apply_entry_fill(entry("f1","100","2"))
    before=(p.open_qty,p.avg_entry,p.current_aggregate_risk,tuple(l.open_qty for l in p.lots))
    result=ShadowScaleInEvaluator().evaluate(
        position=p, context=ctx(), desired_qty=D("1"), expected_price=D("102"),
        structural_stop=D("90"), qty_step=D("0.01"))
    assert result.approved
    assert (p.open_qty,p.avg_entry,p.current_aggregate_risk,tuple(l.open_qty for l in p.lots)) == before


def test_shadow_rejects_stop_widening_without_mutation():
    p=ledger(); p.apply_entry_fill(entry("f1","100","1"))
    r=ShadowScaleInEvaluator().evaluate(position=p, context=ctx(), desired_qty=D("1"),
        expected_price=D("102"), structural_stop=D("89"), qty_step=D("0.01"))
    assert not r.approved and r.reason == "STRUCTURAL_STOP_WOULD_WIDEN_POSITION_STOP"
    assert p.executable_stop == 90 and p.open_qty == 1


def test_normalized_shadow_runtime_seeds_half_risk_and_never_applies_add_fill():
    class C:
        source_signal_id="SIG1"; direction="LONG"; entry_price=D("100"); stop_loss=D("90")
        setup_type="BREAKOUT_LONG"
    state=seed_shadow_position(C())
    assert state.ledger.current_aggregate_risk <= D("0.5")
    before=(state.ledger.open_qty,state.ledger.avg_entry)
    class C2:
        source_signal_id="SIG2"; direction="LONG"; entry_price=D("105"); stop_loss=D("95")
        setup_type="BREAKOUT_LONG"
    decision=evaluate_shadow_candidate(state=state,candidate=C2(),market_regime="BULL_TREND",
                                       always_in="LONG",full_pipeline_approved=True)
    assert decision.action in {"SHADOW_SCALE_APPROVED","SHADOW_SCALE_REJECTED"}
    assert (state.ledger.open_qty,state.ledger.avg_entry)==before
