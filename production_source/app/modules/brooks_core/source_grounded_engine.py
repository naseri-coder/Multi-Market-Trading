"""Fail-closed source-grounded Phase 7A engine.

It is intentionally not a trade-generating strategy yet. It evaluates deterministic source
rules and returns NO_SIGNAL until the unresolved causal classifiers are explicitly specified.
"""

from __future__ import annotations

from app.modules.brooks_core.engine_contract import BrooksEngineResult
from app.modules.brooks_core.phase7_blockers import BLOCKERS
from app.modules.brooks_core.source_rules import (
    br012_default_ema_length,
    br019_range_breakout_failure_heuristic,
    br020_volume_optional_policy,
    br027_candlestick_confirmation_guard,
    br029_market_inertia_heuristic,
    br030_reversal_failure_heuristic,
    br035_indicators_secondary_guard,
    evaluate_br010_inside_bar,
    evaluate_br011_outside_bar,
)
from app.modules.market_data.entities import MarketSnapshot
from app.modules.signal_automation.entities import BrooksRuleEvidence


class SourceGroundedPhase7Engine:
    """Evaluate deterministic rules without inventing missing strategy thresholds."""

    engine_version = "phase7a-source-grounded-v1"
    rule_set_version = "brooks-slides-150-rule-catalog-v1"
    configuration_version = "no-engineering-thresholds-v1"

    async def evaluate(self, snapshot: MarketSnapshot) -> BrooksEngineResult:
        evidence: list[BrooksRuleEvidence] = []
        rule_ids: list[str] = []

        if len(snapshot.candles) >= 2:
            previous, current = snapshot.candles[-2], snapshot.candles[-1]
            for result in (
                evaluate_br010_inside_bar(current, previous),
                evaluate_br011_outside_bar(current, previous),
            ):
                evidence.append(result.to_evidence())
                rule_ids.append(result.rule_id)

        for result in (
            br012_default_ema_length(),
            br019_range_breakout_failure_heuristic(),
            br020_volume_optional_policy(),
            br027_candlestick_confirmation_guard(),
            br029_market_inertia_heuristic(),
            br030_reversal_failure_heuristic(),
            br035_indicators_secondary_guard(),
        ):
            evidence.append(result.to_evidence())
            rule_ids.append(result.rule_id)

        # Fail closed: the raw snapshot cannot be converted to LONG/SHORT without
        # causal definitions for regime, swing structure, H1/H2/L1/L2 counting,
        # Always-In flips, momentum, S/R construction and breakout follow-through.
        blocker_summary = tuple(
            f"{b.hypothesis_id}:{b.name}" for b in BLOCKERS
        )

        return BrooksEngineResult(
            decision="NO_SIGNAL",
            entry_price=None,
            stop_loss=None,
            targets=(),
            setup_type=None,
            reasoning=(
                "Source-grounded deterministic primitives evaluated.",
                "Autonomous directional decision blocked by unresolved engineering hypotheses.",
                *blocker_summary,
            ),
            rule_ids=tuple(rule_ids),
            failed_rules=(),
            rule_evidence=tuple(evidence),
            engine_version=self.engine_version,
            rule_set_version=self.rule_set_version,
            configuration_version=self.configuration_version,
        )
