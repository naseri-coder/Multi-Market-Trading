from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
import unittest

from app.modules.brooks_core_v3.domain import (
    DOMAIN_MODELS,
    DOMAIN_PROTOCOLS,
    Candle,
    ChartSpecification,
    RiskPlan,
    Signal,
    SignalEvent,
    SwingPoint,
    assert_signal_chart_same_snapshot,
    build_market_snapshot,
)
from app.modules.brooks_core_v3.domain.enums import (
    SignalDecision,
    SignalEventType,
    SwingKind,
)

BASE = datetime(2026, 1, 1, tzinfo=UTC)

def make_candle(index: int = 0, *, closed: bool = True) -> Candle:
    open_time = BASE + timedelta(minutes=15 * index)
    return Candle(
        open_time=open_time,
        close_time=open_time + timedelta(minutes=15),
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100.5"),
        volume=Decimal("10"),
        is_closed=closed,
        source="UNIT_TEST",
    )


def make_snapshot():
    candles = tuple(make_candle(i) for i in range(4))
    return build_market_snapshot(
        symbol="BTCUSDT",
        timeframe="15m",
        candles=candles,
        as_of=candles[-1].close_time,
        data_version="phase3-test-v1",
    )


class BrooksCoreV3Phase3DomainTests(unittest.TestCase):
    def test_required_domain_models_are_exactly_fifteen(self):
        self.assertEqual(len(DOMAIN_MODELS), 15)
        self.assertEqual(len({model.__name__ for model in DOMAIN_MODELS}), 15)

    def test_required_protocols_are_exactly_two(self):
        self.assertEqual(len(DOMAIN_PROTOCOLS), 2)
        self.assertEqual(
            {protocol.__name__ for protocol in DOMAIN_PROTOCOLS},
            {"MarketDataProvider", "SignalPublisher"},
        )

    def test_snapshot_is_immutable_and_deterministic(self):
        first = make_snapshot()
        second = make_snapshot()
        self.assertEqual(first.market_snapshot_id, second.market_snapshot_id)
        self.assertEqual(first.market_snapshot_hash, second.market_snapshot_hash)
        with self.assertRaises(FrozenInstanceError):
            first.symbol = "ETHUSDT"  # type: ignore[misc]

    def test_snapshot_rejects_unfinished_candle(self):
        candles = (make_candle(0), make_candle(1, closed=False))
        with self.assertRaises(ValueError):
            build_market_snapshot(
                symbol="BTCUSDT",
                timeframe="15m",
                candles=candles,
                as_of=candles[-1].close_time,
                data_version="phase3-test-v1",
            )

    def test_snapshot_rejects_future_candle(self):
        candles = (make_candle(0), make_candle(1))
        with self.assertRaises(ValueError):
            build_market_snapshot(
                symbol="BTCUSDT",
                timeframe="15m",
                candles=candles,
                as_of=candles[0].close_time,
                data_version="phase3-test-v1",
            )

    def test_swing_confirmation_cannot_precede_pivot(self):
        snapshot = make_snapshot()
        with self.assertRaises(ValueError):
            SwingPoint(
                swing_id="s1",
                market_snapshot_id=snapshot.market_snapshot_id,
                timeframe=snapshot.timeframe,
                kind=SwingKind.HIGH,
                price=Decimal("101"),
                pivot_time=BASE + timedelta(minutes=30),
                confirmed_at=BASE + timedelta(minutes=15),
            )

    def test_risk_plan_is_contract_only_and_may_be_unpopulated(self):
        snapshot = make_snapshot()
        plan = RiskPlan(
            market_snapshot_id=snapshot.market_snapshot_id,
            setup_candidate_id="setup-1",
        )
        self.assertIsNone(plan.entry_price)
        self.assertIsNone(plan.stop_price)
        self.assertEqual(plan.targets, ())

    def _make_signal(self) -> Signal:
        snapshot = make_snapshot()
        return Signal(
            signal_id="signal-1",
            decision=SignalDecision.NO_SIGNAL,
            market_snapshot_id=snapshot.market_snapshot_id,
            market_snapshot_hash=snapshot.market_snapshot_hash,
            rule_set_version="rules-v1",
            engine_version="engine-v1",
            configuration_version="config-v1",
            reasons=("architecture_contract_test",),
            rule_ids=(),
            failed_rules=(),
            approved_at=snapshot.as_of,
        )

    def test_signal_is_immutable(self):
        signal = self._make_signal()
        with self.assertRaises(FrozenInstanceError):
            signal.signal_id = "changed"  # type: ignore[misc]

    def test_signal_event_is_immutable_append_only_record(self):
        event = SignalEvent(
            event_id="event-1",
            signal_id="signal-1",
            event_type=SignalEventType.CREATED,
            occurred_at=BASE,
            payload=(("source", "unit"),),
        )
        with self.assertRaises(FrozenInstanceError):
            event.signal_id = "changed"  # type: ignore[misc]

    def test_signal_and_chart_must_share_snapshot_identity(self):
        signal = self._make_signal()
        chart = ChartSpecification(
            chart_id="chart-1",
            signal_id=signal.signal_id,
            market_snapshot_id=signal.market_snapshot_id,
            market_snapshot_hash=signal.market_snapshot_hash,
            timeframe="15m",
            title="Phase 3 contract chart",
            drawing_instructions=(),
            data_references=("snapshot",),
            created_at=signal.approved_at,
        )
        assert_signal_chart_same_snapshot(signal, chart)

    def test_signal_chart_hash_mismatch_fails_hard(self):
        signal = self._make_signal()
        chart = ChartSpecification(
            chart_id="chart-1",
            signal_id=signal.signal_id,
            market_snapshot_id=signal.market_snapshot_id,
            market_snapshot_hash="0" * 64,
            timeframe="15m",
            title="Mismatch",
            drawing_instructions=(),
            data_references=(),
            created_at=signal.approved_at,
        )
        with self.assertRaises(ValueError):
            assert_signal_chart_same_snapshot(signal, chart)

    def test_domain_has_no_exchange_or_telegram_dependencies(self):
        root = Path(__file__).resolve().parents[2]
        domain = root / "app/modules/brooks_core_v3/domain"
        forbidden = {"telegram", "ccxt", "binance", "bybit"}
        offenders: list[tuple[str, str]] = []
        for path in domain.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                module = None
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name.split(".")[0].lower() in forbidden:
                            offenders.append((path.name, alias.name))
                elif isinstance(node, ast.ImportFrom) and node.module:
                    module = node.module.split(".")[0].lower()
                    if module in forbidden:
                        offenders.append((path.name, node.module))
        self.assertEqual(offenders, [])

    def test_phase3_contains_no_strategy_detector_or_scorer(self):
        root = Path(__file__).resolve().parents[2]
        domain = root / "app/modules/brooks_core_v3/domain"
        forbidden_prefixes = ("detect_", "score_", "calculate_entry", "calculate_stop")
        offenders: list[str] = []
        for path in domain.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name.startswith(forbidden_prefixes):
                        offenders.append(f"{path.name}:{node.name}")
        self.assertEqual(offenders, [])

    def test_unresolved_numeric_thresholds_do_not_leak_into_domain(self):
        root = Path(__file__).resolve().parents[2]
        domain = root / "app/modules/brooks_core_v3/domain"
        needles = (
            "atr_multiplier",
            "body_ratio_threshold",
            "support_width",
            "confidence_cutoff",
            "momentum_weight",
            "breakout_follow_through_threshold",
        )
        offenders: list[tuple[str, str]] = []
        for path in domain.glob("*.py"):
            text = path.read_text(encoding="utf-8").lower()
            for needle in needles:
                if needle in text:
                    offenders.append((path.name, needle))
        self.assertEqual(offenders, [])

    def test_existing_phase1_phase2_files_remain_byte_identical(self):
        import hashlib

        root = Path(__file__).resolve().parents[2]
        expected = {
            "app/modules/brooks_core_v3/source_catalog.py": "144c201f8a5a8e6f55aed39f792a39c0c31992030394560e559f58187a0a6c29",
            "app/modules/brooks_core_v3/crypto_adaptation.py": "62b8e7d89ed97c3b01bf542df69a43fe7107b2cd18d9c5f88ded4e2bfa48ac3c",
            "app/modules/brooks_core_v3/foundation.py": "b438ba7e09da1bf3ed78a17dd22e1b9f10c600978dbf3ed8c941cad553f4d0a9",
        }
        actual = {
            relative: hashlib.sha256((root / relative).read_bytes()).hexdigest()
            for relative in expected
        }
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
