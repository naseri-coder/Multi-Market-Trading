"""Phase 7B foundation engine.

It exercises causal structure infrastructure but still returns NO_SIGNAL. The engine remains
fail-closed because EH-006 and other blockers are not source-resolved yet.
"""

from __future__ import annotations

from app.modules.brooks_core.causal_structure import (
    confirm_swings_causally,
    evaluate_br031_structure,
)
from app.modules.brooks_core.engine_contract import BrooksEngineResult
from app.modules.brooks_core.pullback_guard import assess_h1_h2_l1_l2_counting_window
from app.modules.market_data.entities import MarketSnapshot


class Phase7BCausalStructureEngine:
    engine_version = "phase7b-causal-structure-v1"
    rule_set_version = "brooks-slides-150-rule-catalog-v1"
    configuration_version = "engineering-swings-L2-R2-v1"

    def __init__(self, *, left_bars: int = 2, right_bars: int = 2) -> None:
        if left_bars < 1 or right_bars < 1:
            raise ValueError("left_bars/right_bars must be >= 1")
        self.left_bars = left_bars
        self.right_bars = right_bars

    async def evaluate(self, snapshot: MarketSnapshot) -> BrooksEngineResult:
        scan = confirm_swings_causally(
            snapshot.candles,
            left_bars=self.left_bars,
            right_bars=self.right_bars,
        )
        structure = evaluate_br031_structure(scan)
        guard = assess_h1_h2_l1_l2_counting_window(snapshot.candles[-20:])

        reasoning = (
            "EH-002 engineering swing confirmation executed causally/non-repainting.",
            f"BR-031 structure={structure.direction}: {structure.reason}",
            f"EH-006 counting_guard_allowed={guard.allowed}: {guard.reason}",
            "Autonomous LONG/SHORT remains disabled pending source-resolved pullback counting and remaining blockers.",
        )

        return BrooksEngineResult(
            decision="NO_SIGNAL",
            entry_price=None,
            stop_loss=None,
            targets=(),
            setup_type=None,
            reasoning=reasoning,
            rule_ids=("BR-031",),
            failed_rules=(),
            rule_evidence=(),
            engine_version=self.engine_version,
            rule_set_version=self.rule_set_version,
            configuration_version=(
                f"engineering-swings-L{self.left_bars}-R{self.right_bars}-v1"
            ),
        )
