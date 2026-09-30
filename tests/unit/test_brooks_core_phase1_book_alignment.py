from __future__ import annotations

from types import SimpleNamespace
import unittest

from app.modules.brooks_core.candidate_scoring import score_candidate
from app.modules.brooks_core.evidence_weighting import summarize_evidence
from app.modules.brooks_core.higher_probability import (
    ProbabilityBand,
    assess_higher_probability,
)
from app.modules.signal_automation.entities import BrooksRuleEvidence
from app.modules.signal_intelligence.service import SignalIntelligenceService


def ev(rule_id: str, status: str) -> BrooksRuleEvidence:
    return BrooksRuleEvidence(rule_id=rule_id, status=status, source_pages=(1,))


def candidate_with(evidence):
    return SimpleNamespace(rule_evidence=tuple(evidence), snapshot=None)


class EvidenceWeightingTests(unittest.TestCase):
    def test_strong_rule_outweighs_weak_rule(self):
        strong_pass = summarize_evidence((
            ev("BB-TRD-19-TREND-STRENGTH", "PASS"),
            ev("BB-RNG-26-TWO-REASONS", "FAIL"),
        ))
        weak_pass = summarize_evidence((
            ev("BB-TRD-19-TREND-STRENGTH", "FAIL"),
            ev("BB-RNG-26-TWO-REASONS", "PASS"),
        ))
        self.assertGreater(strong_pass.brooks_certainty, weak_pass.brooks_certainty)

    def test_quality_is_split_into_four_dimensions(self):
        item = candidate_with((
            ev("BB-TRD-19-TREND-STRENGTH", "PASS"),
            ev("BB-REV-15-ALWAYS-IN", "PASS"),
            ev("BB-RNG-17-HL-BAR-COUNT", "PASS"),
        ))
        score = score_candidate(item, risk_score=80)
        self.assertEqual(score.structure_quality, 100.0)
        self.assertEqual(score.context_quality, 100.0)
        self.assertEqual(score.entry_quality, 100.0)
        self.assertEqual(score.risk_quality, 80.0)
        self.assertEqual(score.final_score, 95.0)

    def test_ai_score_does_not_change_brooks_final_quality(self):
        item = candidate_with((
            ev("BB-TRD-19-TREND-STRENGTH", "PASS"),
            ev("BB-REV-15-ALWAYS-IN", "PASS"),
            ev("BB-RNG-17-HL-BAR-COUNT", "PASS"),
        ))
        service = SignalIntelligenceService()
        low_ai = service.evaluate(item, ai_score=20, risk_score=80, council_confidence=0.8)
        high_ai = service.evaluate(item, ai_score=95, risk_score=80, council_confidence=0.8)
        self.assertEqual(low_ai.final_score, high_ai.final_score)
        self.assertEqual(low_ai.final_score, 95.0)


class HigherProbabilityTests(unittest.TestCase):
    def test_failed_failure_is_higher_probability_second_signal(self):
        candidate = SimpleNamespace(
            family="FAILED_FAILURE", direction="LONG", setup_type="FAILED_FAILURE_LONG"
        )
        context = SimpleNamespace(
            regime="BULL_TREND", breakout_streak=1, always_in="LONG"
        )
        result = assess_higher_probability(candidate, context)
        self.assertEqual(result.band, ProbabilityBand.HIGHER)

    def test_countertrend_tight_channel_is_lower_probability(self):
        candidate = SimpleNamespace(
            family="WEDGE_REVERSAL", direction="SHORT", setup_type="WEDGE_REVERSAL_SHORT"
        )
        context = SimpleNamespace(regime="AMBIGUOUS", breakout_streak=0, always_in="UNRESOLVED")
        advanced = SimpleNamespace(tight_channel_direction="LONG")
        result = assess_higher_probability(candidate, context, advanced)
        self.assertEqual(result.band, ProbabilityBand.LOWER)




from datetime import UTC, datetime, timedelta
from decimal import Decimal
from app.modules.brooks_core.advanced_context import assess_advanced_context
from app.modules.brooks_core.books_full_patterns import (
    detect_final_flag,
    detect_micro_double_top_bottom,
)
from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
from app.modules.market_data.entities import Candle, MarketSnapshot

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def bar(i: int, o: str, h: str, l: str, c: str) -> Candle:
    opened = BASE + timedelta(minutes=15 * i)
    return Candle(
        open_time=opened,
        close_time=opened + timedelta(minutes=15),
        open=Decimal(o), high=Decimal(h), low=Decimal(l), close=Decimal(c),
        volume=Decimal("10"),
    )


def snapshot(candles) -> MarketSnapshot:
    items = tuple(candles)
    return MarketSnapshot(
        exchange="binance", market_type="spot", symbol="BTCUSDT", timeframe="15m",
        candles=items, captured_at=items[-1].close_time, source="UNIT_TEST",
    )


class PatternAlignmentTests(unittest.TestCase):
    def test_micro_double_top_is_reversal_candidate_outside_strong_bull_trend(self):
        candles = [bar(i, str(100+i), str(101+i), str(99+i), str(100.5+i)) for i in range(18)]
        candles.append(bar(18, "118", "121.0", "117.5", "120.5"))
        candles.append(bar(19, "120.4", "121.1", "118.8", "119.0"))
        ctx = SimpleNamespace(regime="TRADING_RANGE", always_in="UNRESOLVED")
        found = detect_micro_double_top_bottom(snapshot(candles), ctx, BrooksFullCorePolicy())
        self.assertTrue(any(x.setup_type == "MICRO_DOUBLE_TOP_SHORT" for x in found))

    def test_micro_double_top_is_not_countertrend_signal_in_always_in_bull(self):
        candles = [bar(i, str(100+i), str(101+i), str(99+i), str(100.5+i)) for i in range(18)]
        candles.append(bar(18, "118", "121.0", "117.5", "120.5"))
        candles.append(bar(19, "120.4", "121.1", "118.8", "119.0"))
        ctx = SimpleNamespace(regime="BULL_TREND", always_in="LONG")
        found = detect_micro_double_top_bottom(snapshot(candles), ctx, BrooksFullCorePolicy())
        self.assertFalse(any(x.direction == "SHORT" for x in found))

    def test_final_flag_accepts_one_bar_pause_variant(self):
        candles = []
        for i in range(23):
            base = Decimal("100") + Decimal(i)
            candles.append(bar(i, str(base), str(base + 1), str(base - Decimal("0.2")), str(base + Decimal("0.8"))))
        candles.append(bar(23, "122.8", "123.0", "122.4", "122.7"))
        candles.append(bar(24, "122.6", "122.7", "120.8", "121.0"))
        ctx = SimpleNamespace(structure_direction="BULL_TREND", regime="BULL_TREND")
        found = detect_final_flag(snapshot(candles), ctx, BrooksFullCorePolicy())
        self.assertTrue(any(x.setup_type == "FINAL_FLAG_REVERSAL_SHORT" for x in found))

    def test_advanced_context_marks_opening_reversal_unavailable_without_session(self):
        candles = []
        for i in range(20):
            base = Decimal("100") + Decimal(i)
            candles.append(bar(i, str(base), str(base + 1), str(base - Decimal("0.1")), str(base + Decimal("0.8"))))
        result = assess_advanced_context(snapshot(candles), policy=BrooksFullCorePolicy())
        self.assertFalse(result.opening_reversal_available)
        self.assertEqual(result.tight_channel_direction, "LONG")

if __name__ == "__main__":
    unittest.main()
