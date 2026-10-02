from types import SimpleNamespace as NS
import pytest
from app.modules.signal_intelligence.cold_start_policy import (
    COLD_START_LABEL, EXIT_CLOSED_NATIVE_COMPATIBLE, evaluate_cold_start_fallback,
    persistence_metadata,
)

def objects(*, status="COLD_START_INSUFFICIENT_COMPATIBLE_HISTORY", failures=("PROBABILITY_UNCALIBRATED",),
            structure=80, context=80, entry=100, risk=90, certainty=.85, conflicts=()):
    p=NS(calibration_status=status,compatible_case_count=0,required_sample_size=20)
    q=NS(metadata={"structure_quality":structure,"context_quality":context,"entry_quality":entry,
                   "risk_quality":risk,"brooks_certainty":certainty,"evidence_conflicts":conflicts})
    g=NS(metadata={"failures":failures})
    return p,q,g

def decide(**kw):
    p,q,g=objects(**{k:kw.pop(k) for k in list(kw) if k in {"status","failures","structure","context","entry","risk","certainty","conflicts"}})
    args=dict(probability=p,signal_quality=q,final_gate=g,ai_approved=True,risk_approved=True,
              geometry_valid=True,structural_valid=True,absolute_brooks_veto=False,
              closed_native_compatible_count=0)
    args.update(kw)
    return evaluate_cold_start_fallback(**args),p

def test_strong_cold_start_can_pass_only_missing_probability_gate():
    d,p=decide(); assert d.approved and d.label==COLD_START_LABEL
    assert persistence_metadata(d,p)["statistically_calibrated_at_admission"] is False

@pytest.mark.parametrize("status",["COHORT_MATCHED_MINIMUM_MET","COHORT_MISMATCH","COHORT_UNSPECIFIED"])
def test_non_cold_start_never_uses_fallback(status):
    assert not decide(status=status)[0].approved

def test_exit_threshold_disables_fallback():
    d,_=decide(closed_native_compatible_count=EXIT_CLOSED_NATIVE_COMPATIBLE)
    assert not d.approved and d.reason=="COLD_START_EXIT_THRESHOLD_REACHED"

@pytest.mark.parametrize("name,value,reason",[
    ("ai_approved",False,"AI_REJECTED"),("risk_approved",False,"RISK_REJECTED"),
    ("geometry_valid",False,"INVALID_GEOMETRY"),("structural_valid",False,"STRUCTURAL_INVALIDATION"),
    ("absolute_brooks_veto",True,"ABSOLUTE_BROOKS_VETO")])
def test_hard_guards_are_never_overridden(name,value,reason):
    d,_=decide(**{name:value}); assert not d.approved and d.reason==reason

def test_major_conflict_is_never_overridden():
    d,_=decide(conflicts=("MAJOR:X:opposition",)); assert not d.approved and d.reason=="MAJOR_EVIDENCE_CONFLICT"

def test_unrelated_final_gate_failure_is_never_overridden():
    d,_=decide(failures=("STRUCTURE_NOT_CONFIRMED","PROBABILITY_UNCALIBRATED"))
    assert not d.approved and d.reason.startswith("UNRELATED_FINAL_GATE_FAILURE")

@pytest.mark.parametrize("field,value",[("structure",74.99),("context",74.99),("entry",89.99),("risk",84.99),("certainty",.7999)])
def test_conservative_thresholds_fail_closed(field,value):
    d,_=decide(**{field:value}); assert not d.approved
