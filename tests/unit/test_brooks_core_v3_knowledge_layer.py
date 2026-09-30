from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.modules.brooks_core.books_full_entities import BrooksPatternCandidate, BrooksPatternObservation
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.brooks_core_v3.knowledge import (
    Bias,
    BrooksKnowledgeEngine,
    FindingState,
    KnowledgeCategory,
    ProbabilityBand,
    SourceTaxonomy,
    SessionAnchor,
    all_rule_origins,
    rule_origin,
)
from app.modules.brooks_core_v3.knowledge import rules as knowledge_rules
from app.modules.brooks_core_v3.knowledge.coverage import all_concepts
from app.modules.market_data.entities import Candle, MarketSnapshot

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def bar(i: int, o: str, h: str, l: str, c: str, v: str = '10') -> Candle:
    opened = BASE + timedelta(minutes=15 * i)
    return Candle(opened, opened + timedelta(minutes=15), Decimal(o), Decimal(h), Decimal(l), Decimal(c), Decimal(v))


def snapshot(candles: list[Candle] | tuple[Candle, ...]) -> MarketSnapshot:
    items = tuple(candles)
    return MarketSnapshot('binance', 'spot', 'BTCUSDT', '15m', items, items[-1].close_time, 'KNOWLEDGE_TEST')


def trend_snapshot(count: int = 80) -> MarketSnapshot:
    items=[]
    price=Decimal('100')
    for i in range(count):
        opened=price
        closed=opened+Decimal('1')
        items.append(bar(i, str(opened), str(closed+Decimal('.1')), str(opened-Decimal('.1')), str(closed)))
        price=closed
    return snapshot(items)


@pytest.mark.parametrize('origin', all_rule_origins(), ids=lambda x: x.rule_id)
def test_every_rule_has_independent_source_contract(origin):
    assert rule_origin(origin.rule_id) == origin
    assert origin.rule_id.startswith('BB-')
    assert origin.concept.strip()
    assert origin.source_book.strip()
    assert origin.chapter.strip()
    assert origin.taxonomy in set(SourceTaxonomy)


def test_rule_ids_are_unique_and_complete():
    origins = all_rule_origins()
    ids = [item.rule_id for item in origins]
    assert len(ids) == len(set(ids)) == 72


def test_knowledge_package_has_no_forbidden_layer_imports():
    forbidden = ('ai_council', 'risk_engine', 'telegram', 'signal_quality', 'signal_gate', 'paper_runtime', 'live_vip_runtime', 'signal_intelligence', 'signal_automation', 'signals.models')
    root = Path('app/modules/brooks_core_v3/knowledge')
    hits=[]
    for path in root.glob('*.py'):
        tree=ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module=node.module or ''
                if any(item in module for item in forbidden):
                    hits.append((path.name,module))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if any(item in alias.name for item in forbidden):
                        hits.append((path.name,alias.name))
    assert hits == []


def test_engine_is_deterministic_immutable_and_has_no_trade_decision_fields():
    engine=BrooksKnowledgeEngine()
    market=trend_snapshot()
    first=engine.evaluate(market)
    second=engine.evaluate(market)
    assert first == second
    output_fields={item.name for item in fields(first)}
    assert output_fields == {
        'snapshot_id','snapshot_hash','detected_structures','detected_context','detected_trend',
        'detected_range','detected_channel','detected_pressure','detected_traps','detected_entries',
        'detected_failures','detected_probabilities','detected_evidence',
    }
    assert not ({'decision','entry_price','stop_loss','targets','approved','risk_score','quality_grade'} & output_fields)
    with pytest.raises(FrozenInstanceError):
        first.snapshot_id = 'changed'


def test_engine_forces_trade_decisions_off_even_if_policy_requests_them():
    engine=BrooksKnowledgeEngine(policy=BrooksFullCorePolicy(enable_trade_decisions=True))
    assert engine.policy.enable_trade_decisions is False


def test_successful_breakout_is_first_class_market_fact():
    context=SimpleNamespace(breakout_direction='LONG', breakout_streak=3, regime='BULL_TREND')
    result=knowledge_rules.detect_successful_breakout(trend_snapshot(), context)
    assert {item.category for item in result} == {KnowledgeCategory.STRUCTURE, KnowledgeCategory.PRESSURE, KnowledgeCategory.PROBABILITY}
    assert all(item.bias is Bias.BULLISH for item in result)
    assert next(x for x in result if x.category is KnowledgeCategory.PROBABILITY).probability_band is ProbabilityBand.HIGHER


def test_nested_trading_range_is_neutral_source_interpretation():
    items=[]
    for i in range(30):
        o=Decimal('100') + Decimal(i % 4)
        items.append(bar(i,str(o),str(o+Decimal('8')),str(o-Decimal('8')),str(o+Decimal('1'))))
    for i in range(30,40):
        o=Decimal('102') + Decimal(i % 2)
        items.append(bar(i,str(o),str(o+Decimal('2')),str(o-Decimal('2')),str(o+Decimal('.5'))))
    result=knowledge_rules.detect_nested_trading_range(snapshot(items))
    assert len(result) == 1
    item=result[0]
    assert item.rule_id == 'BB-RNG-02-NESTED-TRADING-RANGE'
    assert item.category is KnowledgeCategory.RANGE
    assert item.bias is Bias.NEUTRAL
    assert item.source.taxonomy is SourceTaxonomy.SOURCE_INTERPRETATION


def test_nested_ioi_is_mapped_to_explicit_interpretation_rule():
    obs=BrooksPatternObservation('NESTED_IOI','Nested ioi','BREAKOUT_MODE',5,direction='UNRESOLVED',source_rule_ids=('BB-TRD-06-IOI',))
    finding=knowledge_rules.observation_findings(obs)[0]
    assert finding.rule_id == 'BB-TRD-06-NESTED-IOI'
    assert finding.source.taxonomy is SourceTaxonomy.SOURCE_INTERPRETATION


def test_session_only_opening_swing_fails_closed():
    finding=knowledge_rules.opening_swing_unavailable(trend_snapshot())
    assert finding.rule_id == 'BB-REV-19-OPENING-SWING'
    assert finding.state is FindingState.NOT_APPLICABLE
    assert finding.source.taxonomy is SourceTaxonomy.SESSION_REQUIRED


def test_final_flag_failure_becomes_failure_and_trap(monkeypatch):
    market=trend_snapshot(30)
    fake_context=SimpleNamespace(regime='BULL_TREND', structure_direction='BULL_TREND', always_in='LONG')
    prior_flag=BrooksPatternCandidate(
        direction='SHORT', setup_type='FINAL_FLAG_REVERSAL_SHORT', family='FINAL_FLAG_REVERSAL',
        signal_index=28, reasons=('late_flag','reversal_trigger'), source_rule_ids=('BB-REV-07-FINAL-FLAG',),
        taxonomy='SOURCE_INTERPRETATION', priority=1, context_required='LATE_TREND_TWO_SIDED')
    monkeypatch.setattr(knowledge_rules, 'assess_books_context', lambda *a, **k: fake_context)
    monkeypatch.setattr(knowledge_rules, 'detect_final_flag', lambda *a, **k: (prior_flag,))
    result=knowledge_rules.detect_final_flag_failure(market, BrooksFullCorePolicy())
    assert {x.category for x in result} == {KnowledgeCategory.FAILURE, KnowledgeCategory.TRAP}
    assert all(x.rule_id == 'BB-REV-07-FINAL-FLAG-FAILURE' for x in result)
    assert all(x.bias is Bias.BULLISH for x in result)


def test_failed_always_in_flip_preserves_prior_pressure(monkeypatch):
    base=list(trend_snapshot(50).candles)
    # Replace final two bars after a fully mature context window.
    i=48; prev=base[47].close
    base[48]=bar(i,str(prev),str(prev+Decimal('.2')),str(prev-Decimal('2')),str(prev-Decimal('1.8')))
    next_open=base[48].close
    base[49]=bar(49,str(next_open),str(next_open+Decimal('2')),str(next_open-Decimal('.1')),str(next_open+Decimal('1.8')))
    fake=SimpleNamespace(always_in='LONG')
    monkeypatch.setattr(knowledge_rules, 'assess_books_context', lambda *a, **k: fake)
    result=knowledge_rules.detect_always_in_failure(snapshot(base), BrooksFullCorePolicy())
    assert {x.category for x in result} == {KnowledgeCategory.FAILURE, KnowledgeCategory.TRAP}
    assert all(x.rule_id == 'BB-REV-15-ALWAYS-IN-FAILURE' for x in result)
    assert all(x.bias is Bias.BULLISH for x in result)


def test_not_applicable_session_observation_never_appears_as_detected_structure():
    obs=BrooksPatternObservation('OPENING_SWING','Opening Swing','NOT_APPLICABLE_SESSION',7,source_rule_ids=('BB-REV-19-OPENING-REVERSAL',))
    finding=knowledge_rules.observation_findings(obs)[0]
    assert finding.category is KnowledgeCategory.EVIDENCE
    assert finding.state is FindingState.NOT_APPLICABLE
    assert finding.rule_id == 'BB-REV-19-OPENING-SWING'


def test_channel_observation_is_classified_as_channel_not_generic_trend():
    obs=BrooksPatternObservation('BULL_MICRO_CHANNEL','Bull Micro Channel','TREND_CONTEXT',7,direction='LONG',source_rule_ids=('BB-TRD-16-MICRO-CHANNEL',))
    finding=knowledge_rules.observation_findings(obs)[0]
    assert finding.category is KnowledgeCategory.CHANNEL
    assert finding.bias is Bias.BULLISH


@pytest.mark.parametrize('concept', all_concepts(), ids=lambda x: x.concept)
def test_every_operational_book_concept_maps_to_registered_rules(concept):
    registered={item.rule_id for item in all_rule_origins()}
    assert concept.rule_ids
    assert set(concept.rule_ids).issubset(registered)
    assert concept.status in {'ACTIVE','ACTIVE_INTERPRETATION','SESSION_REQUIRED'}


def test_mission_required_concepts_are_present():
    names={item.concept for item in all_concepts()}
    required={'Always In','Spike','Spike & Channel','Channel','Broad Channel','Tight Channel','Trading Range','Breakout','Successful Breakout','Failed Breakout','Breakout Pullback','Measured Move','Measured Move Failure','Final Flag','Final Flag Failure','Micro Double Top','Micro Double Bottom','Double Top','Double Bottom','Wedge','Parabolic Wedge','Three Push','Opening Reversal','Opening Swing','Major Trend Reversal','Minor Trend Reversal','Trend Resumption','Exhaustion','Inside Bar','Outside Bar','IOI','Nested IOI','Gap Bar','Nested Trading Range','Always In Failure'}
    assert required.issubset(names)


def opening_reversal_snapshot() -> MarketSnapshot:
    items = [
        bar(0, '100', '104', '99.8', '103.8'),
        bar(1, '103.8', '104', '98.5', '98.8'),
        bar(2, '98.8', '99', '96.5', '96.7'),
    ]
    price = Decimal('96.7')
    for i in range(3, 80):
        opened = price
        closed = opened + Decimal('.2')
        items.append(
            bar(i, str(opened), str(closed + Decimal('.1')),
                str(opened - Decimal('.1')), str(closed))
        )
        price = closed
    return snapshot(items)


def test_explicit_session_anchor_detects_opening_reversal_and_swing():
    market = opening_reversal_snapshot()
    session = SessionAnchor(BASE, 'TEST_OPEN')
    findings = knowledge_rules.opening_session_findings(
        market, BrooksFullCorePolicy(), session
    )
    concepts = {item.concept for item in findings}
    assert {'Opening Reversal', 'Opening Swing', 'Opening Swing Probability'} <= concepts
    assert all(item.bias is Bias.BEARISH for item in findings)


def test_engine_wires_explicit_session_findings_into_neutral_output_contract():
    market = opening_reversal_snapshot()
    result = BrooksKnowledgeEngine().evaluate(
        market, session=SessionAnchor(BASE, 'TEST_OPEN')
    )
    structures = {item.concept for item in result.detected_structures}
    probabilities = {item.concept for item in result.detected_probabilities}
    assert {'Opening Reversal', 'Opening Swing'} <= structures
    assert 'Opening Swing Probability' in probabilities
    assert not hasattr(result, 'decision')


def test_engine_without_session_anchor_fails_closed_for_both_opening_concepts():
    result = BrooksKnowledgeEngine().evaluate(trend_snapshot())
    session_items = [
        item for item in result.detected_evidence
        if item.rule_id in {
            'BB-REV-19-OPENING-REVERSAL',
            'BB-REV-19-OPENING-SWING',
        }
        and item.state is FindingState.NOT_APPLICABLE
    ]
    assert {item.rule_id for item in session_items} == {
        'BB-REV-19-OPENING-REVERSAL',
        'BB-REV-19-OPENING-SWING',
    }
