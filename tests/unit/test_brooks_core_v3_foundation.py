from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from app.modules.brooks_core_v3 import (
    BrooksCoreV3FoundationBuilder,
    EvidenceRegistry,
    brooks_rule_catalog,
    get_rule_reference,
    rule_ids,
)
from app.modules.brooks_core_v3.enums import EvidenceStatus, FoundationLayer, SourceBook
from app.modules.market_data.entities import Candle, MarketSnapshot

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def make_snapshot(count: int = 40) -> MarketSnapshot:
    candles = []
    price = Decimal("100")
    for index in range(count):
        direction = Decimal("0.40") if index % 4 else Decimal("-0.05")
        open_price = price
        close = open_price + direction
        high = max(open_price, close) + Decimal("0.25")
        low = min(open_price, close) - Decimal("0.25")
        candles.append(
            Candle(
                open_time=BASE + timedelta(minutes=15 * index),
                close_time=BASE + timedelta(minutes=15 * (index + 1)),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=Decimal("10"),
            )
        )
        price = close
    return MarketSnapshot(
        exchange="binance",
        market_type="spot",
        symbol="BTCUSDT",
        timeframe="15m",
        candles=tuple(candles),
        captured_at=candles[-1].close_time,
        source="PHASE1_UNIT",
    )


class BrooksCoreV3FoundationTests(unittest.TestCase):
    def test_source_catalog_uses_only_primary_brooks_books_and_unique_ids(self):
        catalog = brooks_rule_catalog()
        ids = [item.rule_id for item in catalog]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(ids), 10)
        allowed = {SourceBook.TRENDS, SourceBook.RANGES, SourceBook.REVERSALS}
        self.assertTrue(all(item.source_book in allowed for item in catalog))
        self.assertIn("BB-RNG-26-TWO-REASONS", rule_ids())

    def test_unknown_source_rule_fails_closed(self):
        with self.assertRaises(KeyError):
            get_rule_reference("BB-UNKNOWN")

    def test_foundation_entities_are_immutable(self):
        foundation = BrooksCoreV3FoundationBuilder().evaluate_foundation(make_snapshot())
        with self.assertRaises(FrozenInstanceError):
            foundation.market_state.symbol = "ETHUSDT"  # type: ignore[misc]

    def test_foundation_pipeline_outputs_state_context_narrative_evidence_only(self):
        foundation = BrooksCoreV3FoundationBuilder().evaluate_foundation(make_snapshot())
        self.assertEqual(foundation.market_state.symbol, "BTCUSDT")
        self.assertEqual(foundation.market_state.last_closed_index, 39)
        self.assertIn("production_behavior_unchanged=true", foundation.narrative_model.bullets)
        self.assertIn("BB-TRD-19-TREND-STRENGTH", foundation.evidence.rule_ids)
        self.assertIn("BB-REV-15-ALWAYS-IN", foundation.evidence.rule_ids)
        self.assertIn("BB-RNG-26-TWO-REASONS", foundation.evidence.rule_ids)
        self.assertFalse(hasattr(foundation, "entry_price"))
        self.assertFalse(hasattr(foundation, "targets"))

    def test_evidence_registry_rejects_duplicate_rule_layer_pairs(self):
        foundation = BrooksCoreV3FoundationBuilder().evaluate_foundation(make_snapshot())
        item = foundation.evidence.items[0]
        with self.assertRaises(ValueError):
            EvidenceRegistry(items=(item, item))

    def test_evidence_is_layered_for_phase1_contract(self):
        foundation = BrooksCoreV3FoundationBuilder().evaluate_foundation(make_snapshot())
        market_items = foundation.evidence.for_layer(FoundationLayer.MARKET_STATE)
        context_items = foundation.evidence.for_layer(FoundationLayer.CONTEXT_MODEL)
        self.assertTrue(market_items)
        self.assertTrue(context_items)
        resolved_statuses = {EvidenceStatus.PASS, EvidenceStatus.AMBIGUOUS}
        self.assertTrue(any(item.status in resolved_statuses for item in market_items))
        self.assertTrue(any(item.status is EvidenceStatus.NOT_APPLICABLE for item in context_items))

    def test_phase1_foundation_is_not_directly_wired_into_production(self):
        root = Path(__file__).resolve().parents[2]
        production_files = [
            path for path in (root / "app").rglob("*.py")
            if "brooks_core_v3" not in path.parts and "__pycache__" not in path.parts
        ]
        forbidden = (
            "app.modules.brooks_core_v3.foundation",
            "BrooksCoreV3FoundationBuilder",
        )
        offenders = [
            path for path in production_files
            if any(token in path.read_text(encoding="utf-8") for token in forbidden)
        ]
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
