from types import SimpleNamespace
from decimal import Decimal as D

from test_brooks_wave17_semantics import candidate, snap
from app.modules.brooks_core.books_full_engine import BrooksTrilogyFullCoreEngine

def rich(direction="LONG", metadata=()):
    e=BrooksTrilogyFullCoreEngine()
    a=SimpleNamespace(measured_move_target=None,measured_move_direction="UNRESOLVED")
    return e._execution_geometry_with_identity(snap(direction),candidate(direction,metadata),a)

def test_scenario_079_positive_long():
    x=rich("LONG")
    assert x[5] and x[6].management_role=="INITIAL_PROTECTIVE_STOP"

def test_scenario_079_positive_short_mirror():
    x=rich("SHORT")
    assert x[5] and x[6].management_role=="INITIAL_PROTECTIVE_STOP"

def test_scenario_079_prefix_identity_available_at_signal_time():
    x=rich("LONG")
    assert all(t.available_at_index==20 for t in x[5])
    assert all((s.confirmed_at_index is None or s.confirmed_at_index<=20) for t in x[5] for s in t.sources)
    assert x[6].available_at_index==20

def test_scenario_079_identity_does_not_change_numeric_geometry():
    e=BrooksTrilogyFullCoreEngine(); s=snap("LONG")
    a=SimpleNamespace(measured_move_target=None,measured_move_direction="UNRESOLVED")
    assert e._execution_geometry(s,candidate("LONG"),a)==e._execution_geometry_with_identity(s,candidate("LONG"),a)[:5]

def test_scenario_gate3_entry_method_preserved():
    md=(("entry_method","MARKET_OR_LIMIT_ANTICIPATION"),("entry_trigger_semantic","SOURCE_ANTICIPATION"),("entry_reference_price","100"),("economic_opportunity_id","OPP:W17"))
    x=rich("LONG",md)
    assert x[0]==D("100")

def test_scenario_gate3_htf_contract_not_reimplemented():
    # 079 owns target/stop identity only; generated source identities carry no HTF alignment state.
    x=rich("LONG")
    text="|".join(s.source_id for t in x[5] for s in t.sources)
    assert "ALIGNED_WITH_CANDIDATE" not in text and "HTF_PATTERN" not in text

def test_scenario_gate3_failure_origin_not_reconstructed():
    x=rich("LONG")
    assert all("FAILED_BREAKOUT" not in s.source_id for t in x[5] for s in t.sources)

def test_scenario_gate3_nested_mtr_not_reconstructed():
    x=rich("LONG")
    assert all("MTR" not in s.source_id for t in x[5] for s in t.sources)

def test_scenario_002_003_dedup_contract_unchanged_by_079():
    # W17 creates no candidate producer and therefore cannot add a second economic signal.
    x=rich("LONG")
    assert len(x)==7 and x[5]

def test_scenario_mtr_gt12_and_final_flag_gt6_are_deferred_unchanged():
    x=rich("LONG")
    text="|".join(s.source_type for t in x[5] for s in t.sources)
    assert "MTR_TIMER" not in text and "FINAL_FLAG_TIMER" not in text

def test_scenario_wave18_wave19_semantics_absent():
    x=rich("LONG")
    text="|".join(s.source_id for t in x[5] for s in t.sources)
    for gap in ("047","048","050","080"):
        assert f"BROOKS-GAP-{gap}" not in text
