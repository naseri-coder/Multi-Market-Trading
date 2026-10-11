"""Stage 9 offline PAPER lifecycle: no broker/network/Telegram activity."""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal as D

import pytest

from naseri_markets.contracts import Instrument, Market
from naseri_markets.core_api_v1 import (
    ClosedCandle, CoreBinding, CoreEventType, CoreInput, DataOrigin,
    PositionSnapshot, CoreDecision, DecisionKind, ManagementAction, ExitAction,
)
from naseri_markets.example_dual_setup_core_v1 import DualSetupExampleCore
from naseri_markets.market_data_engine_v1 import PriceBasis, VolumeSemantics
from naseri_markets.paper_core_risk_bridge_v1 import CoreCapitalAllocation
from naseri_markets.paper_order_lifecycle_v1 import (
    OfflinePaperPositionLifecycle, PaperLifecycleRefused, TargetStep,
)
from naseri_markets.risk_portfolio_contract_v1 import AccountRiskPolicy, PortfolioRiskPolicy

CORE = DualSetupExampleCore()
BASE = datetime(2026, 10, 11, 10, tzinfo=UTC)


def instrument():
    return Instrument(Market.CRYPTO,"example_offline_venue","ABCUSD","UTC","USD")


def event_and_result(binding=None, *, targets=None):
    binding = binding or CoreBinding("inst_one","binding_one",instrument(),"15m")
    before=ClosedCandle(BASE,BASE+timedelta(minutes=15),D(100),D(102),D(98),D(100),D(12))
    latest=ClosedCandle(BASE+timedelta(minutes=15),BASE+timedelta(minutes=30),D(100),D(108),D(99),D(106),D(13))
    event=CoreInput(CORE.manifest.core_id,CORE.manifest.core_version,binding,CoreEventType.CLOSED_CANDLE,
                    latest.close_at,DataOrigin.SYNTHETIC,"toy_fixture",(before,latest))
    result=CORE.evaluate(event)
    assert result.decisions[0].entry==D(106)
    if targets:
        entry=replace(result.decisions[0],targets=targets)
        result=replace(result,decisions=(entry,))
    return event,result


def port():
    return PortfolioRiskPolicy("portfolio","USD",D(100),D(5000),D(100),D(90),D(90),25)


def acct():
    return AccountRiskPolicy("account","portfolio","USD",D(1000),D("0.05"),D("0.20"),D("0.20"),
                             D(2),D("0.90"),D(3),D(1),D("0.01"),D("0.002"),D("0.003"),25,True)


def prepared(path, *,targets=None,fractions=None):
    service=OfflinePaperPositionLifecycle(path)
    service.configure_portfolio(port())
    service.configure_account(acct())
    service.register_instrument(portfolio_id="portfolio",instrument=instrument(),group_id="CRYPTO")
    service.register_allocation(CoreCapitalAllocation("inst_one",CORE.manifest.core_id,CORE.manifest.core_version,
                         "account","portfolio",D("0.10"),D("0.50"),D("0.05"),10),operator_ack=True)
    event,result=event_and_result(targets=targets)
    service.register_binding(CORE.manifest,event.binding,operator_ack=True)
    service.set_enabled("inst_one",enabled=True,expected_revision=1,operator_ack=True)
    decision=result.decisions[0]
    reserved=service.reserve_entry(CORE.manifest,event,result,decision_id=decision.decision_id,quantity=D(1),
                                   price_basis=PriceBasis.TRADE,volume_semantics=VolumeSemantics.TRADED,
                                   expected_allocation_revision=2,operator_ack=True)
    steps=tuple(TargetStep(p,f) for p,f in zip(decision.targets,fractions or (D(1),)))
    service.register_plan(CORE.manifest,event,result,decision_id=decision.decision_id,order_id=reserved.order_id,
                          targets=steps,operator_ack=True)
    return service,reserved.order_id,event,result


def candle(start, *,open="106",high="108",low="104",close="107"):
    return ClosedCandle(start,start+timedelta(minutes=15),D(open),D(high),D(low),D(close),D(10))


def state(s,order_id):
    return s._engine.order_state(order_id)


def inject(s,order_id,kind,rev,*,action=None,quantity=None,price=None,bar=None,evidence=None,remote_order_id=None):
    return s.apply_paper_event(order_id,action_id=action or "event_"+str(rev),event=kind,
                 expected_revision=rev,quantity=quantity,price=price,entry_bar=bar,
                 evidence=evidence,remote_order_id=remote_order_id,operator_ack=True)


def fill(s,order_id,*,quantity=D(1)):
    inject(s,order_id,"SUBMIT",0)
    inject(s,order_id,"ACK",1,remote_order_id="paper_receipt_only")
    c=candle(BASE+timedelta(minutes=30))
    inject(s,order_id,"FILL",2,quantity=quantity,price=D(106),bar=c)
    return c


def test_register_preserves_stage8_risk_and_never_fills(tmp_path):
    with prepared(tmp_path/"a.sqlite")[0] as s:
        row=s._db.execute("SELECT order_id FROM paper_stage9_plans").fetchone()
        assert row is not None
        assert state(s,row[0])["status"]=="CREATED"
        assert s.risk_snapshot("portfolio")["active_orders"]==1


def test_full_target_exit_and_modeled_net_r_and_release(tmp_path):
    s,oid,_,_=prepared(tmp_path/"b.sqlite")
    with s:
        fill(s,oid)
        bar=candle(BASE+timedelta(minutes=45),open="107",high="114",low="104",close="113")
        receipt=s.step_closed_bar(oid,bar,operator_ack=True)
        assert receipt["status"]=="CLOSED"
        assert len(receipt["exits"])==1 and receipt["exits"][0]["reason"]=="TARGET_1"
        perf=s.performance(oid)
        assert D(perf["gross"])==D(7)
        assert D(perf["modeled_cost"])==D("0.565")
        assert D(perf["net"])==D("6.435")
        assert D(perf["net_realized_r"])==D("6.435")/D(7)
        assert s.risk_snapshot("portfolio")["active_orders"]==0
        assert s.step_closed_bar(oid,bar,operator_ack=True)==receipt
        assert len(s.performance(oid)["exits"])==1


def test_stop_priority_and_adverse_gap(tmp_path):
    s,oid,_,_=prepared(tmp_path/"c.sqlite")
    with s:
        fill(s,oid)
        bar=candle(BASE+timedelta(minutes=45),open="98",high="115",low="97",close="103")
        receipt=s.step_closed_bar(oid,bar,operator_ack=True)
        assert receipt["exits"][0]["reason"]=="STOP"
        assert receipt["exits"][0]["price"]=="98"
        assert D(s.performance(oid)["net"])<D(-8)
        assert s.risk_snapshot("portfolio")["active_orders"]==0


def test_multitarget_partial_and_complete(tmp_path):
    s,oid,_,_=prepared(tmp_path/"d.sqlite",targets=(D(110),D(113)),fractions=(D("0.4"),D("0.6")))
    with s:
        fill(s,oid)
        a=s.step_closed_bar(oid,candle(BASE+timedelta(minutes=45),open="107",high="111",low="104",close="109"),operator_ack=True)
        assert len(a["exits"])==1 and a["exits"][0]["quantity"]=="0.40"
        assert s.risk_snapshot("portfolio")["active_orders"]==1
        b=s.step_closed_bar(oid,candle(BASE+timedelta(minutes=60),open="109",high="114",low="108",close="113"),operator_ack=True)
        assert b["status"]=="CLOSED" and b["exits"][0]["quantity"]=="0.60"
        assert s.risk_snapshot("portfolio")["active_orders"]==0
        assert len(s.performance(oid)["exits"])==2


def test_partial_entry_fill_cancels_remaining_before_exit(tmp_path):
    s,oid,_,_=prepared(tmp_path/"e.sqlite")
    with s:
        fill(s,oid,quantity=D("0.50"))
        bar=candle(BASE+timedelta(minutes=45),open="107",high="115",low="104",close="113")
        receipt=s.step_closed_bar(oid,bar,operator_ack=True)
        assert receipt["status"]=="CLOSED"
        assert D(receipt["exits"][0]["quantity"])==D("0.50")
        assert s.risk_snapshot("portfolio")["active_orders"]==0


def test_duplicate_changed_bar_refused_without_mutation(tmp_path):
    s,oid,_,_=prepared(tmp_path/"f.sqlite")
    with s:
        fill(s,oid)
        bar=candle(BASE+timedelta(minutes=45),open="107",high="110",low="104",close="108")
        before=s.step_closed_bar(oid,bar,operator_ack=True)
        with pytest.raises(PaperLifecycleRefused,match="BAR_REPLAY_CONFLICT"):
            s.step_closed_bar(oid,candle(BASE+timedelta(minutes=45),open="107",high="109",low="104",close="108"),operator_ack=True)
        assert s.step_closed_bar(oid,bar,operator_ack=True)==before
        assert len(s.performance(oid)["exits"])==0


def test_missing_bar_gap_rejected(tmp_path):
    s,oid,_,_=prepared(tmp_path/"g.sqlite")
    with s:
        fill(s,oid)
        with pytest.raises(PaperLifecycleRefused,match="BAR_GAP"):
            s.step_closed_bar(oid,candle(BASE+timedelta(minutes=60)),operator_ack=True)
        assert state(s,oid)["status"]=="FILLED"


def test_restart_reconciliation_gate_and_idempotency(tmp_path):
    path=tmp_path/"h.sqlite"
    s,oid,_,_=prepared(path)
    with s:fill(s,oid)
    with OfflinePaperPositionLifecycle(path) as s:
        with pytest.raises(PaperLifecycleRefused,match="RECONCILIATION_REQUIRED"):
            s.step_closed_bar(oid,candle(BASE+timedelta(minutes=45)),operator_ack=True)
        assert not s.reconcile_offline(operator_ack=True)["broker_verified"]
        out=s.step_closed_bar(oid,candle(BASE+timedelta(minutes=45),open="107",high="114",low="104",close="113"),operator_ack=True)
        assert out["status"]=="CLOSED"


def test_double_action_id_conflict_and_no_repeated_fill(tmp_path):
    s,oid,_,_=prepared(tmp_path/"i.sqlite")
    with s:
        out=inject(s,oid,"SUBMIT",0,action="fixed")
        assert inject(s,oid,"SUBMIT",0,action="fixed")==out
        with pytest.raises(PaperLifecycleRefused,match="ACTION_ID_CONFLICT"):
            inject(s,oid,"ACK",1,action="fixed",remote_order_id="simulated")
        assert state(s,oid)["revision"]==1


def test_core_stop_decision_requires_processed_bar_and_exact_revision(tmp_path):
    s,oid,event,result=prepared(tmp_path/"j.sqlite")
    with s:
        fill(s,oid)
        one=candle(BASE+timedelta(minutes=45),open="107",high="110",low="105",close="108")
        prior=candle(BASE+timedelta(minutes=30),open="106",high="108",low="104",close="107")
        snap=state(s,oid)
        pos=PositionSnapshot(oid,result.decisions[0].setup_id,result.decisions[0].direction,
                             D(106),D(99),D(99),snap["revision"])
        event2=CoreInput(CORE.manifest.core_id,CORE.manifest.core_version,event.binding,
                         CoreEventType.POSITION_UPDATE,one.close_at,DataOrigin.SYNTHETIC,"toy_fixture",
                         (prior,one),position=pos)
        manual=CoreDecision("move_stop_test",DecisionKind.MANAGEMENT_INTENT,
                            setup_id=pos.setup_id,action=ManagementAction.MOVE_STOP,
                            position_id=oid,expected_position_revision=snap["revision"],new_stop=D(103))
        result2=replace(CORE.evaluate(event2),decisions=(manual,))
        with pytest.raises(PaperLifecycleRefused,match="MANAGEMENT_REQUIRES_PROCESSED_BAR"):
            s.apply_core_stop(CORE.manifest,event2,result2,decision_id=manual.decision_id,order_id=oid,
                              action_id="too_early",expected_order_revision=snap["revision"],operator_ack=True)
        s.step_closed_bar(oid,one,operator_ack=True)
        moved=s.apply_core_stop(CORE.manifest,event2,result2,decision_id=manual.decision_id,order_id=oid,
                                action_id="trail_once",expected_order_revision=snap["revision"],operator_ack=True)
        assert moved["stop"]=="103"
        assert s.apply_core_stop(CORE.manifest,event2,result2,decision_id=manual.decision_id,order_id=oid,
                                action_id="trail_once",expected_order_revision=snap["revision"],operator_ack=True)==moved
        with pytest.raises(PaperLifecycleRefused,match="ACTION_ID_CONFLICT"):
            s.apply_core_stop(CORE.manifest,event2,result2,decision_id=manual.decision_id,order_id=oid,
                              action_id="trail_once",expected_order_revision=999,operator_ack=True)


def test_no_source_side_effects_and_explicit_ack(tmp_path):
    s,oid,_,_=prepared(tmp_path/"k.sqlite")
    with s:
        with pytest.raises(PaperLifecycleRefused,match="EXPLICIT_OFFLINE_EVENT"):
            s.apply_paper_event(oid,action_id="nothing",event="SUBMIT",expected_revision=0)
        with pytest.raises(PaperLifecycleRefused,match="EXPLICIT_OFFLINE_BAR"):
            s.step_closed_bar(oid,candle(BASE+timedelta(minutes=45)))
        from inspect import getsource
        import naseri_markets.paper_order_lifecycle_v1 as module
        src=getsource(module)
        assert "order_send(" not in src and "send_message(" not in src
        assert not hasattr(s, "send_order")


def test_core_exit_executes_only_on_next_bar_open(tmp_path):
    s,oid,event,result=prepared(tmp_path/"exit.sqlite")
    with s:
        fill(s,oid)
        c=candle(BASE+timedelta(minutes=45),open="107",high="110",low="105",close="108")
        s.step_closed_bar(oid,c,operator_ack=True)
        snap=state(s,oid)
        pos=PositionSnapshot(oid,result.decisions[0].setup_id,result.decisions[0].direction,
                             D(106),D(99),D(99),snap["revision"])
        before=candle(BASE+timedelta(minutes=30),open="106",high="108",low="104",close="107")
        position_event=CoreInput(CORE.manifest.core_id,CORE.manifest.core_version,event.binding,
                  CoreEventType.POSITION_UPDATE,c.close_at,DataOrigin.SYNTHETIC,"toy_fixture",
                  (before,c),position=pos)
        core_decision=CoreDecision("core_close_one",DecisionKind.EXIT_INTENT,
                                  setup_id=pos.setup_id,action=ExitAction.CLOSE_POSITION,
                                  position_id=oid,expected_position_revision=snap["revision"])
        response=replace(CORE.evaluate(position_event),decisions=(core_decision,))
        next_bar=candle(BASE+timedelta(minutes=60),open="108",high="111",low="106",close="109")
        outcome=s.apply_core_exit(CORE.manifest,position_event,response,decision_id=core_decision.decision_id,
                                  order_id=oid,action_id="core_exit_one",execution_bar=next_bar,
                                  expected_order_revision=snap["revision"],operator_ack=True)
        assert outcome["status"]=="CLOSED" and outcome["exits"][0]["price"]=="108"
        assert outcome==s.apply_core_exit(CORE.manifest,position_event,response,decision_id=core_decision.decision_id,
                                  order_id=oid,action_id="core_exit_one",execution_bar=next_bar,
                                  expected_order_revision=snap["revision"],operator_ack=True)
        assert len(s.performance(oid)["exits"])==1


def test_atomic_rollback_when_exit_audit_fails(tmp_path,monkeypatch):
    s,oid,_,_=prepared(tmp_path/"rollback.sqlite")
    with s:
        fill(s,oid)
        original=s._exit
        def sabotage(*args,**kwargs):
            original(*args,**kwargs)
            raise RuntimeError("INJECTED_POST_EXIT_FAILURE")
        monkeypatch.setattr(s,"_exit",sabotage)
        bar=candle(BASE+timedelta(minutes=45),open="107",high="114",low="104",close="113")
        with pytest.raises(RuntimeError,match="INJECTED_POST_EXIT_FAILURE"):
            s.step_closed_bar(oid,bar,operator_ack=True)
        assert state(s,oid)["status"]=="FILLED"
        assert s.risk_snapshot("portfolio")["active_orders"]==1
        assert s.performance(oid)["exits"]==[]
        monkeypatch.setattr(s,"_exit",original)
        assert s.step_closed_bar(oid,bar,operator_ack=True)["status"]=="CLOSED"


def test_target_mismatch_and_invalid_fraction_fail_closed(tmp_path):
    s,oid,event,result=prepared(tmp_path/"mismatch.sqlite")
    with s:
        with pytest.raises(PaperLifecycleRefused,match="TARGETS_MUST_MATCH_CORE"):
            s.register_plan(CORE.manifest,event,result,decision_id=result.decisions[0].decision_id,
                            order_id=oid,targets=(TargetStep(D(114),D(1)),),operator_ack=True)
        with pytest.raises(PaperLifecycleRefused,match="INVALID_TARGET_FRACTIONS"):
            s.register_plan(CORE.manifest,event,result,decision_id=result.decisions[0].decision_id,
                            order_id=oid,targets=(TargetStep(D(113),D("0.5")),),operator_ack=True)