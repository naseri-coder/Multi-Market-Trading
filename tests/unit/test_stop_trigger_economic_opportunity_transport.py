"""Exact STOP_TRIGGER identity transport; no economic identity redesign."""
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace as NS
import runpy
import pytest
from app.modules.brooks_core.books_full_engine import BrooksTrilogyFullCoreEngine
from app.modules.brooks_core.mapper import to_paper_candidate
from app.modules.risk_engine.calculator import RiskCalculator
from app.modules.brooks_runtime import coordinator as cm
from app.modules.signal_automation.entities import BrooksRuleEvidence
from app.modules.signal_automation.repository import _brooks_core_typed_metadata
from app.modules.signal_intelligence.probability import (
    _stored_bootstrap_economic_opportunity_id, _stored_live_economic_opportunity_id,
    _deduplicate_hp_economic_opportunities,
)
HERE = Path(__file__).parent
H = runpy.run_path(str(HERE / "test_hp_semantic_cohort_repair.py"))
B = runpy.run_path(str(HERE / "test_hp_cold_start_bootstrap_repair.py"))
E = runpy.run_path(str(HERE / "test_bootstrap_economic_opportunity_dedup.py"))

def mapped(identity="Opaque:upstream:Case-075b", source="core-a"):
    metadata = () if identity is None else (("economic_opportunity_id", identity),)
    chosen = NS(metadata=metadata, family="BREAKOUT", setup_type="FAILED_BREAKOUT_LONG",
                direction="LONG", signal_index=0, symbol="BTCUSDT")
    intent = BrooksTrilogyFullCoreEngine()._entry_execution_intent(chosen)
    snapshot = H["snap"]()
    # Match Core's distinct source-index witness and generic stop witness.
    index_row = BrooksRuleEvidence("source-index", "PASS", (), (
        ("setup_type", chosen.setup_type), ("direction", "LONG"), ("signal_index", "0")))
    stop_row = BrooksRuleEvidence("BB-RNG-29-SIGNAL-BAR-STOP", "PASS", (), (
        ("setup_type", chosen.setup_type), ("direction", "LONG"),
        ("entry_method", intent.entry_method),
        ("entry_trigger_semantic", intent.entry_trigger_semantic),
        ("economic_opportunity_id", intent.economic_opportunity_id)))
    decision = replace(H["core_decision"](snapshot), source_signal_id=source,
                       rule_evidence=(index_row, stop_row))
    return intent, decision, to_paper_candidate(snapshot=snapshot, decision=decision)

async def collect(monkeypatch, candidate):
    captured = []
    class Capture:
        def __init__(self, session): pass
        async def import_signal(self, command):
            captured.append(command)
            return NS(signal_id=42, created=False)
    monkeypatch.setattr(cm, "BrooksSignalIntegrationService", Capture)
    service = cm.BrooksFullCoreCoordinator.__new__(cm.BrooksFullCoreCoordinator)
    service.settings = NS(brooks_runtime_mode="live")
    service.database = B["_Database"](object())
    service._signal_gate = B["SignalGateService"]()
    _, structural = RiskCalculator._structural_assessment(candidate)
    risk = NS(risk_score=93.25, metadata={
        "risk_semantic_breakdown": {"structural_validation": structural}})
    result = await service._collect_hp_cold_start_bootstrap(
        candidate=candidate, council_decision=NS(final_score=91),
        risk_assessment=risk, probability_assessment=B["_probability"](),
        signal_quality=B["_quality"](), leverage=D("1"))
    return result, captured, structural

@pytest.mark.parametrize("identity", ["Opaque:upstream:Case-075b", " keep exact whitespace "])
def test_origin_mapper_candidate_preserve_exact_identity(identity):
    intent, decision, candidate = mapped(identity)
    assert intent.economic_opportunity_id == f"BTCUSDT:{identity}"
    assert intent.economic_opportunity_id.removeprefix("BTCUSDT:") == identity
    assert candidate.rule_evidence == decision.rule_evidence
    expected = f"BTCUSDT:{identity}"
    assert dict(candidate.rule_evidence[1].evidence)["economic_opportunity_id"] == expected
    points, metadata = RiskCalculator._structural_assessment(candidate)
    assert points == D("15")
    assert metadata["economic_opportunity_id"] == expected

@pytest.mark.asyncio
async def test_transport_import_shadow_repository_hp_exact_identity(monkeypatch):
    intent, _, candidate = mapped()
    result, commands, structural = await collect(monkeypatch, candidate)
    assert result.signal_id == 42 and len(commands) == 1
    command = commands[0]
    assert command.rule_evidence == candidate.rule_evidence
    assert command.bootstrap_provenance["economic_opportunity_id"] == intent.economic_opportunity_id
    stored = NS(analysis_metadata=_brooks_core_typed_metadata(command))
    extracted = _stored_bootstrap_economic_opportunity_id(stored)
    assert extracted == intent.economic_opportunity_id
    live = _stored_live_economic_opportunity_id({
        "risk_semantic_breakdown": {"structural_validation": structural}})
    assert live == extracted
    cases = (E["_case"](1, econ=extracted), E["_case"](2, econ=live, mode="LIVE"))
    selected = _deduplicate_hp_economic_opportunities(cases)
    assert len(selected) == 1 and selected[0].generation_mode == "LIVE"
    assert selected[0].economic_opportunity_id == intent.economic_opportunity_id

@pytest.mark.asyncio
async def test_shadow_stability_under_source_snapshot_churn_and_distinctness(monkeypatch):
    _, _, a = mapped("opaque-same", "source-a")
    _, _, b = mapped("opaque-same", "source-b")
    b = replace(b, market_snapshot_id="different-snapshot", market_snapshot_hash="different-hash")
    _, _, c = mapped("opaque-distinct", "source-a")
    commands = []
    for candidate in (a, b, c):
        _, captured, _ = await collect(monkeypatch, candidate)
        commands.append(captured[0])
    assert commands[0].source_signal_id == commands[1].source_signal_id
    assert commands[0].idempotency_key == commands[1].idempotency_key
    assert commands[0].source_signal_id != commands[2].source_signal_id
    assert commands[0].idempotency_key != commands[2].idempotency_key
    assert len(_deduplicate_hp_economic_opportunities((
        E["_case"](1, econ="opaque-same"), E["_case"](2, econ="opaque-same")))) == 1

@pytest.mark.asyncio
async def test_legacy_missing_identity_fails_closed_without_regeneration(monkeypatch):
    _, _, candidate = mapped()
    rows = tuple(replace(r, evidence=tuple((k,v) for k,v in r.evidence
                       if k != "economic_opportunity_id")) for r in candidate.rule_evidence)
    candidate = replace(candidate, rule_evidence=rows)
    result, commands, structural = await collect(monkeypatch, candidate)
    assert structural["economic_opportunity_id"] is None
    assert result is None and commands == []

@pytest.mark.parametrize("method", [
    "LIMIT_OR_MARKET_FADE", "LIMIT_OR_MARKET_ANTICIPATION", "MARKET_OR_LIMIT_ANTICIPATION"])
@pytest.mark.asyncio
async def test_non_stop_methods_still_skip_bootstrap(monkeypatch, method):
    _, _, candidate = mapped()
    rows = tuple(replace(r, evidence=tuple((k,method if k=="entry_method" else v)
                       for k,v in r.evidence)) for r in candidate.rule_evidence)
    result, commands, _ = await collect(monkeypatch, replace(candidate, rule_evidence=rows))
    assert result is None and commands == []

def test_cross_symbol_economic_identity_isolated():
    core = BrooksTrilogyFullCoreEngine()
    ids = [core._entry_execution_intent(NS(metadata=(), family="BREAKOUT",
        setup_type="BREAKOUT_LONG", direction="LONG", signal_index=119, symbol=s
        )).economic_opportunity_id for s in ("BTCUSDT", "ETHUSDT")]
    assert ids == [
        "BTCUSDT:BREAKOUT:BREAKOUT_LONG:LONG:119",
        "ETHUSDT:BREAKOUT:BREAKOUT_LONG:LONG:119",
    ]

def test_transport_does_not_change_geometry_or_points():
    _, _, candidate = mapped()
    invalid = replace(candidate, entry_price=D("100"))
    for c, expected in ((candidate, D("15")), (invalid, D("0"))):
        points, structural = RiskCalculator._structural_assessment(c)
        assert points == expected
        assert structural["economic_opportunity_id"] == "BTCUSDT:Opaque:upstream:Case-075b"
        assert structural["validation_mode"] == "STOP_TRIGGER_SIGNAL_BAR_EXTREME"
