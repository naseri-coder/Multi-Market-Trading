"""Stage 10: no-send lifecycle, source isolation, recovery and mock-outbox safety."""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from naseri_markets.contracts import Direction, Instrument, Market
from naseri_markets.core_api_v1 import (
    BidAskTick, ClosedCandle, CoreBinding, CoreDecision, CoreEventType, CoreInput,
    CoreManifest, CoreResult, DataOrigin, DecisionKind, ManagementAction,
    PositionSnapshot, SetupSpec,
)
from naseri_markets.market_data_engine_v1 import PriceBasis, VolumeSemantics
from naseri_markets.offline_signal_lifecycle_v1 import (
    OfflineSignalLifecycle, OutboxState, SignalLifecycleRefused, SignalState,
    render_signal,
)

T0 = datetime(2026, 10, 12, 0, 0, tzinfo=UTC)
BASE_INSTRUMENT = Instrument(Market.CRYPTO,"synthetic_venue","BTCUSDT","UTC","USDT")
MANIFEST = CoreManifest("sample.core","1.0.0",
    (SetupSpec("breakout","Example",True),), frozenset({Market.CRYPTO, Market.FOREX}),
    frozenset({CoreEventType.CLOSED_CANDLE, CoreEventType.POSITION_UPDATE}),1)


def entry_context(*,instrument=BASE_INSTRUMENT,instance="instance_a",binding_id="binding_a",targets=(D("110"),D("120")),direction=Direction.LONG):
    binding=CoreBinding(instance,binding_id,instrument,"15m")
    bar=ClosedCandle(T0-timedelta(minutes=15),T0,D("100"),D("106"),D("92"),D("100"),D("5"))
    event=CoreInput(MANIFEST.core_id,MANIFEST.core_version,binding,CoreEventType.CLOSED_CANDLE,
                    T0,DataOrigin.REPLAY,"frozen_source",(bar,))
    decision=CoreDecision("decision_"+binding_id,DecisionKind.ENTRY_INTENT,"breakout",
                          direction=direction, entry=D("100"),
                          stop=D("90") if direction is Direction.LONG else D("110"),
                          targets=targets)
    result=CoreResult(MANIFEST.core_id,MANIFEST.core_version,instance,binding_id,T0,
                      event.input_digest,(decision,))
    return event,result,decision


def register(store,*,context=None,channel=-10099,**kw):
    e,r,d=context or entry_context()
    return store.register(MANIFEST,e,r,d,channel_id=channel,
        price_basis=kw.get("price_basis",PriceBasis.TRADE),
        volume_semantics=VolumeSemantics.TRADED,
        expires_at=kw.get("expires_at",T0+timedelta(hours=1)),operator_ack=True)


def tick(minute,bid,ask=None):
    return BidAskTick(T0+timedelta(minutes=minute),D(str(bid)),D(str(ask or bid)))


def obs(store,snap,seq,minute,bid,ask=None,*,source="frozen_source",instrument=BASE_INSTRUMENT):
    return store.observe(snap.key,instrument=instrument,tick=tick(minute,bid,ask),
                         origin=DataOrigin.REPLAY,source_ref=source,sequence=seq,operator_ack=True)


@pytest.fixture
def store(tmp_path):
    with OfflineSignalLifecycle(tmp_path/'signal.sqlite',enabled=True) as s:
        yield s


def test_disabled_requires_explicit_ack_and_separate_disk(tmp_path):
    with pytest.raises(SignalLifecycleRefused,match="ISOLATED_DISK"):
        OfflineSignalLifecycle(':memory:')
    with OfflineSignalLifecycle(tmp_path/'x.db') as s:
        e,r,d=entry_context()
        with pytest.raises(SignalLifecycleRefused,match="DISABLED"):
            register(s)
        with pytest.raises(SignalLifecycleRefused,match="DISABLED"):
            s.claim_dry_run("0"*64)


def test_registration_idempotent_and_no_auto_send(store):
    s=register(store)
    assert s.state is SignalState.WAITING_ENTRY and s.revision==1
    assert s.message_id is None
    assert register(store).key==s.key
    assert len(store.events(s.key))==1
    assert len(store.commands(s.key))==1
    cmd=store.commands(s.key)[0]
    assert cmd.command=='SEND' and cmd.state is OutboxState.PENDING
    assert cmd.message_id is None and 'NOT SENT' in cmd.text
    assert 'no actual execution' in cmd.text
    assert not hasattr(store,'send_message')


def test_channel_reuse_payload_conflict(store):
    register(store)
    with pytest.raises(SignalLifecycleRefused,match="PAYLOAD_CONFLICT"):
        register(store,channel=-100100)


def test_two_bindings_same_core_isolated(store):
    s1=register(store)
    s2=register(store,context=entry_context(instance='instance_b',binding_id='binding_b'))
    assert s1.key != s2.key
    assert len(store.commands(s1.key))==len(store.commands(s2.key))==1
    assert obs(store,s1,1,1,99,100).state is SignalState.ACTIVE
    assert store.snapshot(s2.key).state is SignalState.WAITING_ENTRY


def test_entry_then_targets_sequential_and_gross_r(store):
    s=register(store)
    active=obs(store,s,1,1,99,100)
    assert active.state is SignalState.ACTIVE
    assert active.hit_targets==0 and active.observed_r==0
    t1=obs(store,s,2,2,112,113)
    assert t1.state is SignalState.ACTIVE and t1.hit_targets==1
    assert t1.observed_r==D('0.5')
    complete=obs(store,s,3,3,121,122)
    assert complete.state is SignalState.TARGETS_COMPLETE
    assert complete.hit_targets==2 and complete.observed_r==D('1.5')
    assert len(store.events(s.key))==4
    assert [c.command for c in store.commands(s.key)]==['SEND','EDIT','EDIT','EDIT']
    assert obs(store,s,4,4,77,78).state is SignalState.TARGETS_COMPLETE


def test_gap_stop_first_and_multi_target_partial_result(store):
    s=register(store)
    obs(store,s,1,1,99,100)
    obs(store,s,2,2,112,113)
    stopped=obs(store,s,3,3,85,86)
    assert stopped.state is SignalState.STOPPED
    # T1 = +1R on half; remaining half exits at -1.5R adverse gap.
    assert stopped.observed_r==D('-0.25')
    assert stopped.hit_targets==1
    assert 'NO costs/fills' in render_signal(stopped)


def test_ambiguous_spread_stop_takes_precedence(store):
    s=register(store)
    obs(store,s,1,1,99,100)
    state=obs(store,s,2,2,89,121)
    assert state.state is SignalState.STOPPED and state.hit_targets==0
    assert state.observed_r==D('-1.1')


def test_short_entry_and_target(store):
    short=entry_context(direction=Direction.SHORT,targets=(D('90'),D('80')))
    s=register(store,context=short)
    assert obs(store,s,1,1,100,101).state is SignalState.ACTIVE
    assert obs(store,s,2,2,89,90).hit_targets==1
    assert obs(store,s,3,3,79,80).state is SignalState.TARGETS_COMPLETE


def test_expires_only_before_entry(store):
    s=register(store,expires_at=T0+timedelta(minutes=1))
    old=obs(store,s,1,1,101,102)
    assert old.state is SignalState.WAITING_ENTRY
    expired=obs(store,s,2,2,95,96)
    assert expired.state is SignalState.EXPIRED
    assert obs(store,s,3,3,94,95).state is SignalState.EXPIRED


def test_identical_duplicate_durable_and_conflicting_sequence_refused(store):
    s=register(store)
    active=obs(store,s,1,1,99,100)
    assert obs(store,s,1,1,99,100)==active
    assert len(store.events(s.key))==2
    with pytest.raises(SignalLifecycleRefused,match="CONFLICTING"):
        obs(store,s,1,1,98,100)
    with pytest.raises(SignalLifecycleRefused,match="SEQUENCE_GAP"):
        obs(store,s,3,3,105,106)
    assert store.snapshot(s.key).last_sequence==1
    with pytest.raises(SignalLifecycleRefused,match="NOT_CAUSAL"):
        obs(store,s,2,0,105,106)


def test_cross_market_and_source_rejected_without_mutation(store):
    s=register(store)
    other=Instrument(Market.FOREX,"broker", "EURUSD", "UTC","USD")
    with pytest.raises(SignalLifecycleRefused,match="INSTRUMENT_OR_SOURCE"):
        obs(store,s,1,1,99,100,instrument=other)
    with pytest.raises(SignalLifecycleRefused,match="INSTRUMENT_OR_SOURCE"):
        obs(store,s,1,1,99,100,source='forged')
    assert store.snapshot(s.key).last_sequence is None


def test_reject_forex_bid_only_or_nonentry(store):
    i=Instrument(Market.FOREX,"demo", "EURUSD", "UTC","USD")
    with pytest.raises(SignalLifecycleRefused,match="FOREX_EXECUTABLE"):
        register(store,context=entry_context(instrument=i),price_basis=PriceBasis.BID)
    e,r,d=entry_context()
    no=CoreDecision('nothing',DecisionKind.NO_SETUP)
    r=replace(r,decisions=(no,))
    with pytest.raises(SignalLifecycleRefused,match="OFFLINE_ENTRY"):
        store.register(MANIFEST,e,r,no,channel_id=-1,price_basis=PriceBasis.TRADE,
                       volume_semantics=VolumeSemantics.TRADED,
                       expires_at=T0+timedelta(hours=1),operator_ack=True)


def test_dry_run_ordering_edits_wait_for_acked_send(store):
    s=register(store)
    obs(store,s,1,1,99,100)
    first=store.claim_dry_run(s.key,operator_ack=True)
    assert first.command=='SEND' and first.state is OutboxState.CLAIMED
    assert store.claim_dry_run(s.key,operator_ack=True) is None
    ack=store.acknowledge_dry_run(s.key,1,fake_message_id=123,operator_ack=True)
    assert ack.state is OutboxState.SIMULATED_ACK
    edit=store.claim_dry_run(s.key,operator_ack=True)
    assert edit.command=='EDIT' and edit.message_id==123
    with pytest.raises(SignalLifecycleRefused,match="MISMATCH"):
        store.acknowledge_dry_run(s.key,2,fake_message_id=444,operator_ack=True)
    store.acknowledge_dry_run(s.key,2,fake_message_id=123,operator_ack=True)
    assert store.snapshot(s.key).message_id==123


def test_outbox_unknown_after_restart_no_blind_retry(tmp_path):
    p=tmp_path/'a.sqlite'
    with OfflineSignalLifecycle(p,enabled=True) as service:
        s=register(service)
        service.claim_dry_run(s.key,operator_ack=True)
    with OfflineSignalLifecycle(p,enabled=True) as service:
        assert service.quarantine_inflight()==1
        assert service.claim_dry_run(s.key,operator_ack=True) is None
        assert service.commands(s.key)[0].state is OutboxState.UNKNOWN
        with pytest.raises(SignalLifecycleRefused,match="NO_SIMULATED"):
            service.acknowledge_dry_run(s.key,1,fake_message_id=987,operator_ack=True)
        service.acknowledge_dry_run(s.key,1,fake_message_id=987,operator_ack=True,
                                    reconciled_unknown=True)
        assert service.snapshot(s.key).message_id==987


def test_simulated_ack_for_send_cannot_be_replaced(store):
    s=register(store)
    store.claim_dry_run(s.key,operator_ack=True)
    store.acknowledge_dry_run(s.key,1,fake_message_id=888,operator_ack=True)
    with pytest.raises(SignalLifecycleRefused,match="NO_SIMULATED"):
        store.acknowledge_dry_run(s.key,1,fake_message_id=889,operator_ack=True)


def test_core_stop_only_validated_signal_position_and_revision(store):
    s=register(store)
    active=obs(store,s,1,1,99,100)
    bar=ClosedCandle(T0+timedelta(minutes=1),T0+timedelta(minutes=16),
                     D('100'),D('112'),D('98'),D('111'),D('10'))
    p=PositionSnapshot(s.key,s.setup_id,Direction.LONG,s.entry,s.initial_stop,
                       s.stop,active.revision)
    event=CoreInput(MANIFEST.core_id,MANIFEST.core_version,
                    CoreBinding(s.instance_id,s.binding_id,s.instrument,'15m'),
                    CoreEventType.POSITION_UPDATE,bar.close_at,DataOrigin.REPLAY,
                    'frozen_source',(bar,),position=p)
    d=CoreDecision('move_to_breakeven',DecisionKind.MANAGEMENT_INTENT,s.setup_id,
                   action=ManagementAction.MOVE_STOP,position_id=s.key,
                   expected_position_revision=active.revision,new_stop=D('100'))
    result=CoreResult(MANIFEST.core_id,MANIFEST.core_version,s.instance_id,s.binding_id,
                      event.observed_at,event.input_digest,(d,))
    changed=store.tighten_stop_from_core(s.key,MANIFEST,event,result,d,
                                         expected_revision=active.revision,operator_ack=True)
    assert changed.stop==D('100')
    assert changed.revision==active.revision+1
    with pytest.raises(SignalLifecycleRefused,match="REVISION"):
        store.tighten_stop_from_core(s.key,MANIFEST,event,result,d,
                                     expected_revision=active.revision,operator_ack=True)


def test_input_expiry_contract_and_target_order_refused(store):
    with pytest.raises(SignalLifecycleRefused,match="INVALID_ENTRY_EXPIRY"):
        register(store,expires_at=T0+timedelta(days=8))
    e,r,d=entry_context(targets=(D('120'),D('110')))
    with pytest.raises(SignalLifecycleRefused,match="TARGET_ORDER"):
        register(store,context=(e,r,d))


def test_no_trade_or_real_delivery_methods_or_dependencies():
    import ast, inspect
    from naseri_markets import offline_signal_lifecycle_v1 as mod
    tree=ast.parse(inspect.getsource(mod))
    imports=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
    assert not any(name in ("telegram", "requests", "httpx", "socket", "subprocess")
                   for name in imports)
    assert all(not hasattr(mod.OfflineSignalLifecycle,thing)
               for thing in ('submit_order','place_order','send_message','edit_message',
                             'publish','execute_trade'))


def test_malicious_label_newline_rejected_before_durable_record(store):
    instrument = Instrument(Market.CRYPTO, "provider\nFORGED WIN", "BTCUSDT", "UTC", "USDT")
    with pytest.raises(SignalLifecycleRefused,match="UNSAFE_PROVIDER"):
        register(store,context=entry_context(instrument=instrument))
    assert store._db.execute("SELECT count(*) FROM offline_signal_states").fetchone()[0]==0


def test_record_exactly_one_nonproduction_route_per_signal(store):
    s=register(store)
    assert store.snapshot(s.key).channel_id==-10099
    with pytest.raises(SignalLifecycleRefused,match="OPERATOR_CHANNEL"):
        register(store,channel=10099)
    with pytest.raises(SignalLifecycleRefused,match="OPERATOR_CHANNEL"):
        e,r,d=entry_context()
        store.register(MANIFEST,e,r,d,channel_id=-10099,
                       price_basis=PriceBasis.TRADE,
                       volume_semantics=VolumeSemantics.TRADED,
                       expires_at=T0+timedelta(hours=1),operator_ack=False)


def test_candle_must_not_masquerade_as_bidask_quote(store):
    with pytest.raises(SignalLifecycleRefused, match="INVALID_SIGNAL_PRICE_BASIS"):
        register(store,price_basis=PriceBasis.BID_ASK)
