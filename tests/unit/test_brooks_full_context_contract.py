from decimal import Decimal
import unittest

from app.modules.brooks_core.books_entities import BrooksContextAssessment, ContextMetrics
from app.modules.brooks_core.books_full_engine import BrooksTrilogyFullCoreEngine
from app.modules.brooks_core.books_full_entities import BrooksPatternCandidate


def make_context(
    regime="BULL_TREND",
    *,
    always_in="LONG",
    breakout_direction="LONG",
):
    return BrooksContextAssessment(
        regime=regime,
        always_in=always_in,
        reason="test",
        structure_direction=regime,
        breakout_direction=breakout_direction,
        breakout_streak=2,
        metrics=ContextMetrics(
            directional_bar_fraction=Decimal("0.7"),
            body_overlap_rate=Decimal("0.2"),
            bar_overlap_rate=Decimal("0.2"),
            adjusted_displacement=Decimal("0.6"),
            close_path_efficiency=Decimal("0.5"),            ema_side_fraction=Decimal("0.8"),
            strong_bull_bar_count=5,
            strong_bear_bar_count=1,
            tight_range_like=False,
        ),
    )


def candidate(
    *,
    direction="LONG",
    family="BREAKOUT_PULLBACK",
    requirement="BREAKOUT_RESUMPTION",
    priority=20,
    setup_type="TEST_SETUP",
):
    return BrooksPatternCandidate(
        direction=direction,
        setup_type=setup_type,
        family=family,
        signal_index=10,
        reasons=("reason_one", "reason_two"),
        source_rule_ids=("BB-RNG-26-TWO-REASONS",),
        taxonomy="SOURCE_INTERPRETATION",
        priority=priority,
        context_required=requirement,
    )


class BrooksFullContextContractTests(unittest.TestCase):
    def setUp(self):
        self.engine = BrooksTrilogyFullCoreEngine()

    def test_exact_trend_contract_passes_only_matching_direction(self):
        ctx = make_context("BULL_TREND", always_in="LONG", breakout_direction="LONG")
        good = candidate(
            family="TREND_CONTINUATION",
            requirement="BULL_TREND",
            direction="LONG",
        )
        bad = candidate(
            family="TREND_CONTINUATION",
            requirement="BULL_TREND",
            direction="SHORT",
        )
        self.assertEqual(self.engine._context_contract_status(good, ctx)[0], "PASS")
        self.assertEqual(self.engine._context_contract_status(bad, ctx)[0], "REJECT")

    def test_trading_range_contract_rejects_non_range_context(self):
        ctx = make_context("BULL_TREND", always_in="LONG", breakout_direction="LONG")
        item = candidate(
            family="TRADING_RANGE_FADE",
            requirement="TRADING_RANGE",
            direction="SHORT",
        )
        self.assertEqual(self.engine._context_contract_status(item, ctx)[0], "REJECT")

    def test_countertrend_breakout_rejected_against_established_always_in(self):
        ctx = make_context("BEAR_TREND", always_in="SHORT", breakout_direction="SHORT")
        item = candidate(
            direction="LONG",
            family="BREAKOUT",
            requirement="BREAKOUT_OR_TREND",
        )
        status, reason = self.engine._context_contract_status(item, ctx)
        self.assertEqual(status, "REJECT")
        self.assertEqual(reason, "countertrend_against_established_always_in")

    def test_breakout_resumption_must_match_resolved_breakout_direction(self):
        ctx = make_context(
            "AMBIGUOUS",
            always_in="UNRESOLVED",
            breakout_direction="SHORT",
        )
        item = candidate(direction="LONG", requirement="BREAKOUT_RESUMPTION")
        status, reason = self.engine._context_contract_status(item, ctx)
        self.assertEqual(status, "REJECT")
        self.assertEqual(reason, "breakout_resumption_direction_mismatch")

    def test_location_dependent_contract_fails_closed_against_unbroken_always_in(self):
        ctx = make_context("BULL_TREND", always_in="LONG", breakout_direction="LONG")
        item = candidate(
            direction="SHORT",
            family="WEDGE_REVERSAL",
            requirement="TREND_EXTREME_OR_RANGE_EXTREME",
        )
        status, reason = self.engine._context_contract_status(item, ctx)
        self.assertEqual(status, "REJECT")
        self.assertEqual(reason, "reversal_against_unbroken_always_in")

    def test_unknown_contract_fails_closed(self):
        ctx = make_context()
        item = candidate(requirement="UNKNOWN_FUTURE_CONTEXT")
        status, reason = self.engine._context_contract_status(item, ctx)
        self.assertEqual(status, "REJECT")
        self.assertTrue(reason.startswith("unmapped_context_requirement:"))

    def test_choose_candidate_skips_rejected_higher_priority_item(self):
        ctx = make_context("BULL_TREND", always_in="LONG", breakout_direction="LONG")
        rejected = candidate(
            direction="SHORT",
            family="BREAKOUT",
            requirement="BREAKOUT_OR_TREND",
            priority=1,
            setup_type="REJECTED",
        )
        accepted = candidate(
            direction="LONG",
            family="BREAKOUT_PULLBACK",
            requirement="BREAKOUT_RESUMPTION",
            priority=20,
            setup_type="ACCEPTED",
        )
        chosen = self.engine._choose_candidate((rejected, accepted), ctx)
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen.setup_type, "ACCEPTED")


if __name__ == "__main__":
    unittest.main()
