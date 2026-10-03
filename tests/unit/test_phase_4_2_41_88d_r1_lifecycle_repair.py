from __future__ import annotations
import copy, json, tempfile
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from pathlib import Path
import pytest
from app.modules.market_data.entities import Candle
from research_layer.phase_4_2_41_88e.contract import *
from research_layer.phase_4_2_41_88e.lifecycle import advance, new_state
from research_layer.phase_4_2_41_88e.store import ShadowStore
from research_layer.phase_4_2_41_88d.lifecycle import advance as old_advance, new_state as old_new_state
BASE=datetime(2026,1,1,tzinfo=UTC); CUT=BASE; ROOT=Path(__file__).resolve().parents[2]
def bar(i,h,l,c=None):
    o=BASE+timedelta(minutes=i); hi,lo=D(str(h)),D(str(l)); cl=D(str(c)) if c is not None else (hi+lo)/2
    return Candle(o,o+timedelta(seconds=59),cl,hi,lo,cl,D('1'))
def plan(context='REVERSAL_OR_TRANSITION',fractions=None,runner='0',be='AFTER_PARTIAL'):
    return {'policy_version':MGMT,'context_class':context,'initial_stop_loss':'90','initial_risk':'10','target_exit_fractions':fractions or {'1':'0.5','2':'0.5'},'runner_fraction':runner,'breakeven_mode':be,'source_rule_ids':['X']}
def cand(p=None,targets=None):
    return {'candidate_identity':'c1','candidate_timestamp':BASE.isoformat(),'snapshot_captured_at':(BASE-timedelta(seconds=1)).isoformat(),'symbol':'BTCUSDT','timeframe':'15m','direction':'LONG','setup_type':'FAILED_BREAKOUT_LONG','entry':'100','initial_stop':'90','targets':targets or ['110','120'],'management_plan':p or plan(),'engine_version':ENGINE,'rule_set_version':RULES,'configuration_version':CONFIGURATION,'artifact_schema_version':ARTIFACT_SCHEMA_VERSION,'risk_semantic_model':RISK_SEMANTIC_MODEL,'runner_policy':RUNNER_POLICY,'exchange':'binance','market_type':'futures','management_version':MGMT,'statistics_contract_version':STAT,'source_frozen_contract_sha':CONTRACT_SHA}
def run(c,s,candles,e=(),as_of=None):
    if as_of is None: as_of=(max((x.close_time for x in candles),default=BASE)+timedelta(seconds=1))
    return advance(c,s,candles,e,cutover_at=CUT,as_of=as_of)
def test_01_old_empty_poll_reproduces_incident():
    c=cand()
    with pytest.raises(AttributeError): old_advance(c,old_new_state(c),[],[])
def test_02_empty_poll_before_entry_is_explicit_noop():
    c=cand(); s=new_state(c); before=copy.deepcopy(s); r=run(c,s,[]); assert r.poll_status=='NO_NEW_ELIGIBLE_CLOSED_CANDLE' and r.processed_candles==0 and r.state==before and s==before
def test_03_repeated_empty_polls_are_idempotent():
    c=cand(); s=new_state(c); a=run(c,s,[]); b=run(c,a.state,[]); assert a.state==b.state==s
def test_04_empty_poll_for_open_position_is_noop():
    c=cand(); s=new_state(c); s.update(status='ACTIVE',entry_activated_at=(BASE+timedelta(minutes=1,seconds=59)).isoformat(),last_processed_candle_close=(BASE+timedelta(minutes=1,seconds=59)).isoformat()); before=copy.deepcopy(s); assert run(c,s,[]).state==before
def test_05_next_valid_closed_candle_after_empty_polls_processes():
    c=cand(); s=run(c,new_state(c),[]).state; r=run(c,s,[bar(1,99,98,98.5)]); assert r.poll_status=='PROCESSED' and r.state['last_processed_candle_close']==bar(1,99,98,98.5).close_time.isoformat()
def test_06_entry_activation_after_empty_polls():
    c=cand(); s=run(c,new_state(c),[]).state; r=run(c,s,[bar(1,101,99,100)]); assert r.state['status']=='ACTIVE' and r.state['entry_activated_at'] is not None
def test_07_partial_target_after_empty_polls():
    c=cand(); s=run(c,new_state(c),[]).state; r=run(c,s,[bar(1,101,99,100),bar(2,111,101,108)]); assert 1 in r.state['targets_hit'] and r.state['status']=='ACTIVE'
def test_08_breakeven_path_after_partial():
    c=cand(); r=run(c,new_state(c),[bar(1,101,99,100),bar(2,111,101,108),bar(3,105,99,100)]); assert r.state['terminal_reason']=='BREAKEVEN'
def test_09_structural_trailing_path():
    c=cand(plan(fractions={'1':'1','2':'0'},runner='0',be='STRUCTURE_ONLY'),targets=['150','160'])
    vals=[('101','100'),('103','101'),('105','102'),('104','100'),('103','99'),('104','100'),('106','102'),('108','104'),('107','103'),('106','102'),('107','103'),('109','105'),('111','107'),('110','106'),('109','105')]
    cs=[bar(i+1,h,l) for i,(h,l) in enumerate(vals)]; r=run(c,new_state(c),cs); assert any(x['reason']=='STRUCTURAL_TRAIL' for x in r.state['stop_updates'])
def test_10_staged_completion():
    c=cand(); r=run(c,new_state(c),[bar(1,101,99,100),bar(2,111,101,108),bar(3,121,111,120)]); assert r.state['terminal_reason']=='TARGET_STAGED_COMPLETION'
def test_11_runner_remains_open_without_reversal_evidence():
    p=plan('STRONG_TREND',{'1':'0.5','2':'0'},'0.5','STRUCTURE_ONLY'); c=cand(p)
    r=run(c,new_state(c),[bar(1,101,99,100),bar(2,111,101,108),bar(3,109,104,106)]); assert r.state['status']=='ACTIVE' and r.state['runner_event'] is None
def test_12_runner_reversal():
    p=plan('STRONG_TREND',{'1':'0.5','2':'0'},'0.5','STRUCTURE_ONLY'); c=cand(p)
    ev=[{'candidate_identity':'c1','approved_at':BASE.isoformat(),'candle_closed_at':(BASE-timedelta(seconds=1)).isoformat(),'symbol':'BTCUSDT','timeframe':'15m','direction':'LONG','always_in':'LONG'},{'candidate_identity':'opp','approved_at':(BASE+timedelta(minutes=2,seconds=30)).isoformat(),'candle_closed_at':(BASE+timedelta(minutes=2,seconds=30)).isoformat(),'symbol':'BTCUSDT','timeframe':'15m','direction':'SHORT','always_in':'SHORT'}]
    r=run(c,new_state(c),[bar(1,101,99,100),bar(2,111,101,108),bar(3,109,104,105)],ev); assert r.state['terminal_reason']=='RUNNER_REVERSAL'
def test_13_ambiguous_outcome():
    c=cand(); r=run(c,new_state(c),[bar(1,111,89,100)]); assert r.state['status']=='AMBIGUOUS' and r.state['realized_r'] is None
def test_14_duplicate_poll_does_not_reprocess_candle():
    c=cand(); first=run(c,new_state(c),[bar(1,99,98,98.5)]); second=run(c,first.state,[bar(1,99,98,98.5)]); assert second.poll_status=='NO_NEW_ELIGIBLE_CLOSED_CANDLE' and second.state==first.state
def test_15_delayed_binance_empty_then_arrival_is_safe():
    c=cand(); s=new_state(c)
    for _ in range(5): s=run(c,s,[]).state
    r=run(c,s,[bar(1,101,99,100)]); assert r.state['status']=='ACTIVE'
def test_16_incomplete_future_candle_excluded():
    c=cand(); x=bar(1,101,99,100); as_of=x.close_time-timedelta(microseconds=1); r=run(c,new_state(c),[x],as_of=as_of); assert r.poll_status=='NO_NEW_ELIGIBLE_CLOSED_CANDLE' and r.state==new_state(c)
def test_17_candle_exactly_at_evaluation_boundary_excluded():
    c=cand(); x=bar(1,101,99,100); r=run(c,new_state(c),[x],as_of=x.close_time); assert r.poll_status=='NO_NEW_ELIGIBLE_CLOSED_CANDLE'
def test_18_restart_persisted_state_recovery():
    c=cand()
    with tempfile.TemporaryDirectory() as td:
        p=Path(td)/'s.sqlite'; st=ShadowStore(p); st.add_candidate(c,{'status':'HIDDEN_FOR_TEST'},new_state(c)); s=run(c,new_state(c),[bar(1,101,99,100)]).state; st.update_lifecycle('c1',s); st.close(); st=ShadowStore(p); rc,_,rs=st.candidates()[0]; assert rs==s and rc['candidate_identity']=='c1'; st.close()
def test_19_decision_payload_immutable_and_no_duplicate_candidate():
    c=cand()
    with tempfile.TemporaryDirectory() as td:
        st=ShadowStore(Path(td)/'s.sqlite'); st.add_candidate(c,{'status':'ORIGINAL'},new_state(c)); st.add_candidate(c,{'status':'MUTATED'},new_state(c)); rows=st.candidates(); assert len(rows)==1 and rows[0][1]['status']=='ORIGINAL'; st.close()
def test_20_no_duplicate_terminal_realization_after_restart():
    c=cand(); terminal=run(c,new_state(c),[bar(1,101,99,100),bar(2,89,88,89)]).state; assert terminal['status']=='COMPLETE'
    with tempfile.TemporaryDirectory() as td:
        st=ShadowStore(Path(td)/'s.sqlite'); st.add_candidate(c,{'status':'HIDDEN_FOR_TEST'},terminal); st.close(); st=ShadowStore(Path(td)/'s.sqlite'); assert st.candidates(open_only=True)==[]; st.close()

def test_21_binance_query_start_includes_floor_minute():
    import ast
    import hashlib
    archive = ROOT / "docs/legacy/research_layer/phase_4_2_41_88e/live_shadow.py.txt"
    raw = archive.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "d90134653bc6ea317b98ffc4f75ed86b281f526f5d05ed364d165f9b38ebd3c4"
    assert "4fa03bb9fc2ac42046a2dd971955f9c472cda4b72116459b77dfdf400c68b34c" in raw.decode()
    body = raw.decode()[raw.decode().index("from __future__") :]
    node = next(n for n in ast.parse(body).body if isinstance(n, ast.FunctionDef) and n.name == "one_minute_query_start")
    expected = ast.parse("def one_minute_query_start(floor):\n    return floor.astimezone(UTC).replace(second=0, microsecond=0)").body[0]
    assert ast.dump(node, include_attributes=False) == ast.dump(expected, include_attributes=False)
    floor = datetime(2026, 9, 14, 10, 15, 5, tzinfo=UTC)
    assert floor.astimezone(UTC).replace(second=0, microsecond=0) == datetime(2026, 9, 14, 10, 15, 0, tzinfo=UTC)
