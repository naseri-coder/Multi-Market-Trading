from __future__ import annotations

import ast
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
import unittest

from app.modules.brooks_core_v3.runtime_bridge import (
    BrooksCoreV3ShadowOrchestrator,
    assert_no_chart_render,
    assert_shadow_only,
    shadow_signal_diagnostics,
    to_domain_snapshot,
)
from app.modules.market_data.entities import Candle, MarketSnapshot

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def make_snapshot(*, timeframe: str = "15m", count: int = 90) -> MarketSnapshot:
    minutes = {"15m": 15, "1h": 60}[timeframe]
    candles: list[Candle] = []
    price = Decimal("100")
    for index in range(count):
        open_price = price
        close = open_price + Decimal("0.7")
        candles.append(Candle(
            open_time=BASE + timedelta(minutes=minutes * index),
            close_time=BASE + timedelta(minutes=minutes * (index + 1)),
            open=open_price,
            high=close + Decimal("0.1"),
            low=open_price - Decimal("0.1"),
            close=close,
            volume=Decimal("10"),
        ))
        price = close
    return MarketSnapshot(
        exchange="binance",
        market_type="spot",
        symbol="BTCUSDT",
        timeframe=timeframe,
        candles=tuple(candles),
        captured_at=candles[-1].close_time,
        source="PHASE4_SHADOW_TEST",
    )


class BrooksCoreV3Phase4ShadowTests(unittest.TestCase):
    def test_adapter_preserves_source_snapshot_identity(self):
        source = make_snapshot()
        domain = to_domain_snapshot(source)
        self.assertEqual(domain.market_snapshot_id, source.snapshot_id)
        self.assertEqual(domain.market_snapshot_hash, source.snapshot_hash)
        self.assertEqual(domain.as_of, source.captured_at)

    def test_shadow_orchestrator_is_never_publishable(self):
        result = BrooksCoreV3ShadowOrchestrator().evaluate(make_snapshot())
        self.assertFalse(result.publication_allowed)
        assert_shadow_only(result)
        assert_no_chart_render(result)

    def test_shadow_result_exposes_no_trade_geometry(self):
        result = BrooksCoreV3ShadowOrchestrator().evaluate(make_snapshot())
        for name in ("decision", "entry_price", "stop_loss", "targets", "leverage"):
            self.assertFalse(hasattr(result, name), name)
        self.assertIn("phase4_shadow_no_publication", result.blockers)
        self.assertIn("phase4_shadow_no_database_write", result.blockers)

    def test_shadow_evaluation_is_deterministic_for_same_snapshot(self):
        snapshot = make_snapshot()
        engine = BrooksCoreV3ShadowOrchestrator()
        first = engine.evaluate(snapshot)
        second = engine.evaluate(snapshot)
        self.assertEqual(first.source_snapshot_hash, second.source_snapshot_hash)
        self.assertEqual(first.crypto.input_fingerprint, second.crypto.input_fingerprint)
        self.assertEqual(first.diagnostics, second.diagnostics)

    def test_shadow_diagnostics_are_explicitly_non_publishable(self):
        result = BrooksCoreV3ShadowOrchestrator().evaluate(make_snapshot())
        data = shadow_signal_diagnostics(result)
        self.assertIs(data["publication_allowed"], False)
        self.assertEqual(data["source_snapshot_id"], result.source_snapshot_id)
        self.assertEqual(data["source_snapshot_hash"], result.source_snapshot_hash)

    def test_runtime_bridge_contains_no_delivery_or_database_dependencies(self):
        root = Path(__file__).resolve().parents[2]
        bridge = root / "app/modules/brooks_core_v3/runtime_bridge"
        forbidden_roots = {
            "telegram", "sqlalchemy", "app.modules.live_vip_runtime",
            "app.modules.paper_runtime", "app.modules.signal_automation",
        }
        offenders: list[tuple[str, str]] = []
        for path in bridge.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                for name in names:
                    if any(name == root_name or name.startswith(root_name + ".") for root_name in forbidden_roots):
                        offenders.append((path.name, name))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
