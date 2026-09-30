from decimal import Decimal as D
from types import SimpleNamespace as NS

import pytest

from app.modules.brooks_core.engine_contract import TargetPlanLifecycle
from app.modules.risk_engine.calculator import RiskCalculator
from app.modules.risk_engine.service import RiskEngineService


def evidence(setup, direction, method=None, **extra):
    data = {
        "setup_type": setup,
        "direction": direction,
        "signal_index": "0",
    }
    if method is not None:
        data["entry_method"] = method
    data.update({k: str(v) for k, v in extra.items()})
    return NS(status="PASS", evidence=tuple(data.items()))


def candidate(
    *,
    setup="TEST",
    direction="LONG",
    entry=D("100"),
    stop=D("99"),
    targets=(D("101"),),
    method="STOP_TRIGGER_CONFIRMATION",
    bar_high=D("99.5"),
    bar_low=D("98.5"),
    plan_state="TREND_TRADE",
    explicit_plan=True,
    evidence_extra=None,
):
    extra = dict(evidence_extra or {})
    if method == "STOP_TRIGGER_CONFIRMATION":
        extra.setdefault("entry_trigger_semantic", "SIGNAL_BAR_STOP_TRIGGER")
        extra.setdefault("economic_opportunity_id", f"OPP:{setup}")
    ev = evidence(setup, direction, method, **extra)
    obj = NS(
        setup_type=setup,
        direction=direction,
        entry_price=entry,
        stop_loss=stop,
        targets=tuple(targets),
        snapshot=NS(candles=(NS(high=bar_high, low=bar_low),)),
        rule_evidence=(ev,),
        rule_ids=(),
        reversal_outcome_context=None,
        target_source_identities=(),
        stop_source_identity=None,
    )
    obj.target_plan_lifecycle = (
        TargetPlanLifecycle(f"PLAN:{setup}", plan_state, direction, 0)
        if explicit_plan
        else None
    )
    return obj


@pytest.fixture(autouse=True)
def deterministic_context(monkeypatch):
    state = {"regime": "BULL_TREND", "channel_quality": "UNRESOLVED"}

    def fake_context(_snapshot):
        return NS(**state)

    monkeypatch.setattr("app.modules.risk_engine.calculator.build_market_context", fake_context)
    return state


def test_plan_rr_trend_consumes_real_tm_allocations(deterministic_context):
    c = candidate(targets=(D("100.5"), D("103")))
    score, meta = RiskCalculator().calculate_with_breakdown(c)
    reward = meta["plan_reward"]
    assert reward["mode"] == "PLAN_WEIGHTED_PRETRADE"
    assert reward["plan_rr"] == "1.5"
    assert reward["runner_fraction"] == "0.5"
    assert reward["runner_objective"] is None
    assert reward["weighted_runner_r"] == "0"
    assert score == 93.25


def test_plan_rr_range_consumes_real_tm_allocations(deterministic_context):
    deterministic_context["regime"] = "TRADING_RANGE"
    c = candidate(targets=(D("100.5"), D("102")), plan_state="RANGE_TRADE")
    score, meta = RiskCalculator().calculate_with_breakdown(c)
    reward = meta["plan_reward"]
    assert reward["plan_rr"] == "1.25"
    assert reward["runner_fraction"] == "0.0"
    assert score == 88.75


def test_same_t1_different_allocated_plan_changes_plan_rr(deterministic_context):
    c3 = candidate(targets=(D("100.5"), D("103")))
    c6 = candidate(targets=(D("100.5"), D("106")))
    _, m3 = RiskCalculator().calculate_with_breakdown(c3)
    _, m6 = RiskCalculator().calculate_with_breakdown(c6)
    assert m3["plan_rr"] == "1.5"
    assert m6["plan_rr"] == "3.0"
    assert m3["plan_rr"] != m6["plan_rr"]


def test_runner_without_explicit_objective_is_zero_conservative():
    c = candidate(targets=(D("100.5"), D("103")))
    _, meta = RiskCalculator().calculate_with_breakdown(c)
    reward = meta["plan_reward"]
    assert reward["runner_fraction"] == "0.5"
    assert reward["runner_objective"] is None
    assert reward["weighted_runner_r"] == "0"


def test_directionally_invalid_target_not_positive_reward():
    c = candidate(targets=(D("99.5"), D("103")))
    score, meta = RiskCalculator().calculate_with_breakdown(c)
    assert meta["plan_rr"] == "0"
    assert meta["plan_reward"]["mode"] == "INVALID_DIRECTIONAL_TARGET_FAIL_CLOSED"
    assert meta["geometry_points"] == "0"
    assert score < 75


def test_legacy_without_target_plan_preserves_target0_compatibility():
    c = candidate(explicit_plan=False, targets=(D("101"),))
    score, meta = RiskCalculator().calculate_with_breakdown(c)
    assert meta["risk_semantic_model"] == "LEGACY_TARGET0_COMPAT"
    assert meta["plan_rr"] == "1"
    assert score == 82


def test_stop_trigger_policy_preserved():
    c = candidate()
    points, meta = RiskCalculator._structural_assessment(c)
    assert points == D("15")
    assert meta["validation_mode"] == "STOP_TRIGGER_SIGNAL_BAR_EXTREME"


def test_invalid_stop_trigger_does_not_get_full_points():
    c = candidate(entry=D("99"), bar_high=D("100"))
    points, _ = RiskCalculator._structural_assessment(c)
    assert points == D("0")


@pytest.mark.parametrize(
    "direction,entry,stop,targets,high,low,extra",
    [
        ("LONG", D("90"), D("87"), (D("93"), D("100")), D("96"), D("89"), {
            "entry_reference_price":"90","entry_trigger_semantic":"AT_OR_NEAR_CANONICAL_RANGE_EDGE",
            "economic_opportunity_id":"RANGE_FADE:R:LONG:0","canonical_gap_id":"BROOKS-GAP-045",
            "range_id":"R","range_edge_state":"AT_LOWER_RANGE_EDGE","range_low":"90","range_high":"110",
        }),
        ("SHORT", D("110"), D("113"), (D("107"), D("100")), D("111"), D("104"), {
            "entry_reference_price":"110","entry_trigger_semantic":"AT_OR_NEAR_CANONICAL_RANGE_EDGE",
            "economic_opportunity_id":"RANGE_FADE:R:SHORT:0","canonical_gap_id":"BROOKS-GAP-045",
            "range_id":"R","range_edge_state":"AT_UPPER_RANGE_EDGE","range_low":"90","range_high":"110",
        }),
    ],
)
def test_range_fade_method_aware(direction,entry,stop,targets,high,low,extra,deterministic_context):
    deterministic_context["regime"] = "TRADING_RANGE"
    c = candidate(
        setup=f"TRADING_RANGE_FADE_{direction}",direction=direction,entry=entry,stop=stop,targets=targets,
        method="LIMIT_OR_MARKET_FADE",bar_high=high,bar_low=low,plan_state="RANGE_TRADE",
        evidence_extra=extra,
    )
    points, meta = RiskCalculator._structural_assessment(c)
    assert points == D("15")
    assert meta["validation_mode"] == "TYPED_ALTERNATIVE_EXECUTION_IDENTITY"


def test_invalid_range_fade_reference_fails_structural(deterministic_context):
    deterministic_context["regime"] = "TRADING_RANGE"
    c = candidate(
        setup="TRADING_RANGE_FADE_LONG",entry=D("90"),stop=D("87"),targets=(D("93"),D("100")),
        method="LIMIT_OR_MARKET_FADE",bar_high=D("96"),bar_low=D("89"),plan_state="RANGE_TRADE",
        evidence_extra={
            "entry_reference_price":"91","entry_trigger_semantic":"AT_OR_NEAR_CANONICAL_RANGE_EDGE",
            "economic_opportunity_id":"RANGE_FADE:R:LONG:0","canonical_gap_id":"BROOKS-GAP-045",
            "range_id":"R","range_edge_state":"AT_LOWER_RANGE_EDGE","range_low":"90","range_high":"110",
        },
    )
    assert RiskCalculator._structural_points(c) == D("0")


@pytest.mark.parametrize(
    "setup,direction,entry,stop,targets,method,high,low,extra",
    [
        ("MICRO_DOUBLE_TOP_ANTICIPATORY_SHORT","SHORT",D("103"),D("106"),(D("100"),D("97")),
         "LIMIT_OR_MARKET_ANTICIPATION",D("104"),D("96"),{
            "entry_reference_price":"103","entry_trigger_semantic":"MICRO_DOUBLE_SECOND_TEST_ANTICIPATION",
            "economic_opportunity_id":"MICRO:X:SHORT","canonical_gap_id":"BROOKS-GAP-068",
            "structure_id":"MICRO:TOP:1:2","entry_confirmation_state":"ANTICIPATORY_UNCONFIRMED",
         }),
        ("MICRO_DOUBLE_BOTTOM_ANTICIPATORY_LONG","LONG",D("97"),D("94"),(D("100"),D("103")),
         "LIMIT_OR_MARKET_ANTICIPATION",D("104"),D("95"),{
            "entry_reference_price":"97","entry_trigger_semantic":"MICRO_DOUBLE_SECOND_TEST_ANTICIPATION",
            "economic_opportunity_id":"MICRO:X:LONG","canonical_gap_id":"BROOKS-GAP-068",
            "structure_id":"MICRO:BOTTOM:1:2","entry_confirmation_state":"ANTICIPATORY_UNCONFIRMED",
         }),
        ("FINAL_FLAG_ANTICIPATORY_SHORT","SHORT",D("101"),D("105"),(D("97"),D("93")),
         "MARKET_OR_LIMIT_ANTICIPATION",D("104"),D("99"),{
            "entry_reference_price":"101","entry_trigger_semantic":"FINAL_FLAG_OPPOSITE_REVERSAL_MINIMUM_BEFORE_BREAKOUT",
            "economic_opportunity_id":"FINAL_FLAG:F:SHORT","canonical_gap_id":"BROOKS-GAP-068",
            "final_flag_id":"F","entry_confirmation_state":"ANTICIPATORY_UNCONFIRMED",
         }),
        ("FINAL_FLAG_ANTICIPATORY_LONG","LONG",D("99"),D("95"),(D("103"),D("107")),
         "MARKET_OR_LIMIT_ANTICIPATION",D("101"),D("96"),{
            "entry_reference_price":"99","entry_trigger_semantic":"FINAL_FLAG_OPPOSITE_REVERSAL_MINIMUM_BEFORE_BREAKOUT",
            "economic_opportunity_id":"FINAL_FLAG:F:LONG","canonical_gap_id":"BROOKS-GAP-068",
            "final_flag_id":"F","entry_confirmation_state":"ANTICIPATORY_UNCONFIRMED",
         }),
    ],
)
def test_anticipatory_methods_are_method_aware(setup,direction,entry,stop,targets,method,high,low,extra):
    c = candidate(
        setup=setup,direction=direction,entry=entry,stop=stop,targets=targets,method=method,
        bar_high=high,bar_low=low,plan_state="REVERSAL_OR_TRANSITION",evidence_extra=extra,
    )
    points, meta = RiskCalculator._structural_assessment(c)
    assert points == D("15")
    assert meta["validation_mode"] == "TYPED_ALTERNATIVE_EXECUTION_IDENTITY"


def test_invalid_anticipatory_reference_fails():
    c = candidate(
        setup="MICRO_DOUBLE_TOP_ANTICIPATORY_SHORT",direction="SHORT",entry=D("103"),stop=D("106"),
        targets=(D("100"),D("97")),method="LIMIT_OR_MARKET_ANTICIPATION",bar_high=D("104"),bar_low=D("96"),
        plan_state="REVERSAL_OR_TRANSITION",evidence_extra={
            "entry_reference_price":"102","entry_trigger_semantic":"MICRO_DOUBLE_SECOND_TEST_ANTICIPATION",
            "economic_opportunity_id":"MICRO:X:SHORT","canonical_gap_id":"BROOKS-GAP-068",
            "structure_id":"MICRO:TOP:1:2","entry_confirmation_state":"ANTICIPATORY_UNCONFIRMED",
        },
    )
    assert RiskCalculator._structural_points(c) == D("0")


def test_unknown_explicit_entry_method_fails_closed():
    c = candidate(method="UNKNOWN_METHOD")
    assert RiskCalculator._structural_points(c) == D("0")


def test_legacy_missing_entry_method_uses_existing_stop_trigger_policy():
    c = candidate(method=None)
    points, meta = RiskCalculator._structural_assessment(c)
    assert points == D("15")
    assert meta["validation_mode"] == "LEGACY_STOP_TRIGGER_COMPAT"


def test_risk_service_exposes_plan_and_structural_diagnostics():
    c = candidate(targets=(D("100.5"), D("103")))
    assessment = RiskEngineService().evaluate(c)
    data = assessment.metadata["risk_semantic_breakdown"]
    assert data["risk_semantic_model"] == "PLAN_WEIGHTED_PRETRADE"
    assert data["plan_rr"] == "1.5"
    assert data["rr_points"] == "38.25"
    assert data["geometry_points"] == "40"
    assert data["structural_points"] == "15"


def test_rr_bucket_policy_is_frozen():
    assert RiskCalculator._rr_points(D("2")) == D("45")
    assert RiskCalculator._rr_points(D("1.5")) == D("38.25")
    assert RiskCalculator._rr_points(D("1.25")) == D("33.75")
    assert RiskCalculator._rr_points(D("1")) == D("27")
    assert RiskCalculator._rr_points(D(".75")) == D("18")
    assert RiskCalculator._rr_points(D(".5")) == D("9")
