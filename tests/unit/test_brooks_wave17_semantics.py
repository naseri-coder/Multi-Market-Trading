from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from app.modules.brooks_core.books_full_engine import BrooksTrilogyFullCoreEngine
from app.modules.brooks_core.books_full_entities import BrooksPatternCandidate
from app.modules.brooks_core.engine_contract import (
    BrooksEngineResult,
    StopSourceIdentity,
    TargetSourceEvidence,
    TargetSourceIdentity,
)
from app.modules.brooks_core.entities import BrooksCoreDecision
from app.modules.brooks_core.mapper import to_paper_candidate
from app.modules.market_data.entities import Candle, MarketSnapshot

BASE=datetime(2026,9,18,tzinfo=UTC)

def bar(i,o,h,l,c):
    t=BASE+timedelta(minutes=15*i)
    return Candle(t,t+timedelta(minutes=15),D(str(o)),D(str(h)),D(str(l)),D(str(c)),D("1"))

def snap(direction="LONG"):
    cs=[bar(i,100,105,95,100) for i in range(20)]
    if direction=="LONG":
        cs.append(bar(20,100,105,95,104))
    else:
        cs.append(bar(20,100,105,95,96))
    return MarketSnapshot("binance","futures","BTCUSDT","15m",tuple(cs),cs[-1].close_time,"W17")

def candidate(direction="LONG", metadata=()):
    return BrooksPatternCandidate(
        direction, "W17_"+direction, "WEDGE_REVERSAL", 20,
        ("origin","signal"), ("BB-REV-05-WEDGE-THREE-PUSH",),
        "SOURCE_INTERPRETATION", 1, "REVERSAL_OR_TRANSITION", metadata=metadata
    )

def identity_fixture(price=D("115")):
    src=TargetSourceEvidence("RECENT_STRUCTURE_MEASURED_MOVE","SRC:1",0,20)
    tid=TargetSourceIdentity(1,price,(src,),20)
    sid=StopSourceIdentity(D("94"),"INITIAL_PROTECTIVE_STOP","STOP:1",D("95"),20,20,"SETUP_OR_PULLBACK_LOW_PLUS_RECENT_VOLATILITY_BUFFER")
    return tid,sid

def test_079_typed_identity_contract_validates_target_and_stop_prices():
    tid,sid=identity_fixture()
    r=BrooksEngineResult("LONG",D("105.1"),D("94"),(D("115"),),"X",(),(),(),(),"e","r","c",(tid,),sid)
    assert r.target_source_identities[0].sources[0].source_type=="RECENT_STRUCTURE_MEASURED_MOVE"
    assert r.stop_source_identity.management_role=="INITIAL_PROTECTIVE_STOP"

def test_079_target_identity_price_mismatch_fails_closed():
    tid,sid=identity_fixture(D("116"))
    with pytest.raises(ValueError,match="target identity"):
        BrooksEngineResult("LONG",D("105.1"),D("94"),(D("115"),),"X",(),(),(),(),"e","r","c",(tid,),sid)

def test_079_stop_identity_price_mismatch_fails_closed():
    tid,sid=identity_fixture()
    bad=StopSourceIdentity(D("93"),sid.source_type,sid.source_id,sid.structural_reference_price,20,20,sid.adjustment_policy)
    with pytest.raises(ValueError,match="stop identity"):
        BrooksEngineResult("LONG",D("105.1"),D("94"),(D("115"),),"X",(),(),(),(),"e","r","c",(tid,),bad)

def test_079_future_confirmed_target_source_is_rejected():
    src=TargetSourceEvidence("OPPOSING_CAUSAL_SWING","S",10,21)
    with pytest.raises(ValueError,match="confirmed after"):
        TargetSourceIdentity(1,D("115"),(src,),20)

def test_079_geometry_preserves_existing_prices_and_adds_typed_sources_long():
    e=BrooksTrilogyFullCoreEngine()
    s=snap("LONG")
    adv=SimpleNamespace(measured_move_target=None,measured_move_direction="UNRESOLVED")
    legacy=e._execution_geometry(s,candidate("LONG"),adv)
    rich=e._execution_geometry_with_identity(s,candidate("LONG"),adv)
    assert legacy==rich[:5]
    assert rich[2]==tuple(x.target_price for x in rich[5])
    assert rich[6].stop_price==rich[1]
    assert rich[6].source_type=="INITIAL_PROTECTIVE_STOP"

def test_079_geometry_directional_mirror_short():
    e=BrooksTrilogyFullCoreEngine()
    s=snap("SHORT")
    adv=SimpleNamespace(measured_move_target=None,measured_move_direction="UNRESOLVED")
    rich=e._execution_geometry_with_identity(s,candidate("SHORT"),adv)
    assert rich[1]>rich[0]
    assert rich[2] and all(t<rich[0] for t in rich[2])
    assert tuple(x.target_price for x in rich[5])==rich[2]

def test_079_mapper_preserves_typed_identity_without_new_entry_method():
    s=snap("LONG"); tid,sid=identity_fixture()
    d=BrooksCoreDecision("LONG","sig",D("105.1"),D("94"),(D("115"),),"X",(),(),(),(),"e","r","c",s.snapshot_id,s.snapshot_hash,"chart.png",(tid,),sid)
    p=to_paper_candidate(snapshot=s,decision=d)
    assert p is not None
    assert p.target_source_identities==(tid,)
    assert p.stop_source_identity==sid

def test_079_no_signal_cannot_carry_execution_identity():
    tid,sid=identity_fixture()
    with pytest.raises(ValueError,match="NO_SIGNAL"):
        BrooksEngineResult("NO_SIGNAL",None,None,(),"X",(),(),(),(),"e","r","c",(tid,),sid)

def test_079_deferred_dependents_are_not_rule_ids_or_entry_promotions():
    e=BrooksTrilogyFullCoreEngine()
    s=snap("LONG")
    adv=SimpleNamespace(measured_move_target=None,measured_move_direction="UNRESOLVED")
    rich=e._execution_geometry_with_identity(s,candidate("LONG"),adv)
    flattened="|".join(src.source_id for t in rich[5] for src in t.sources)
    for gap in ("BROOKS-GAP-047","BROOKS-GAP-048","BROOKS-GAP-050","BROOKS-GAP-080"):
        assert gap not in flattened
