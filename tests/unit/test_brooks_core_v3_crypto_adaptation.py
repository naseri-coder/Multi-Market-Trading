from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
import unittest

from app.modules.brooks_core_v3 import (
    CryptoAdaptationEngine,
    CryptoAdaptationInput,
    CryptoAdaptationPolicy,
    DerivativesObservation,
    LiquidityObservation,
)
from app.modules.brooks_core_v3.enums import (
    DerivativesBias,
    FakeBreakoutState,
    LiquidityState,
    MTFAlignment,
    RelativeVolumeState,
    VolatilityState,
)
from app.modules.market_data.entities import Candle, MarketSnapshot

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def make_trend_snapshot(
    *,
    timeframe: str = "15m",
    direction: str = "LONG",
    count: int = 90,
    last_volume: Decimal = Decimal("10"),
    end_at: datetime | None = None,
) -> MarketSnapshot:
    minutes = {"15m": 15, "1h": 60, "4h": 240}[timeframe]
    start = BASE if end_at is None else end_at - timedelta(minutes=minutes * count)
    candles: list[Candle] = []
    price = Decimal("100")
    sign = Decimal("1") if direction == "LONG" else Decimal("-1")
    for index in range(count):
        open_price = price
        close = open_price + sign * Decimal("0.8")
        high = max(open_price, close) + Decimal("0.1")
        low = min(open_price, close) - Decimal("0.1")
        volume = last_volume if index == count - 1 else Decimal("10")
        candles.append(
            Candle(
                open_time=start + timedelta(minutes=minutes * index),
                close_time=start + timedelta(minutes=minutes * (index + 1)),
                open=open_price,
                high=high,
                low=low,
                close=close,
                volume=volume,
            )
        )
        price = close
    return MarketSnapshot(
        exchange="binance",
        market_type="perpetual",
        symbol="BTCUSDT",
        timeframe=timeframe,
        candles=tuple(candles),
        captured_at=candles[-1].close_time,
        source="PHASE2_TEST",
    )


def make_volatility_snapshot() -> MarketSnapshot:
    candles: list[Candle] = []
    for index in range(90):
        spread = Decimal("4") if index >= 70 else Decimal("1")
        half = spread / Decimal("2")
        candles.append(
            Candle(
                open_time=BASE + timedelta(minutes=15 * index),
                close_time=BASE + timedelta(minutes=15 * (index + 1)),
                open=Decimal("100"),
                high=Decimal("100") + half,
                low=Decimal("100") - half,
                close=Decimal("100"),
                volume=Decimal("10"),
            )
        )
    return MarketSnapshot(
        exchange="binance",
        market_type="perpetual",
        symbol="BTCUSDT",
        timeframe="15m",
        candles=tuple(candles),
        captured_at=candles[-1].close_time,
        source="PHASE2_VOL_TEST",
    )


def make_bull_trap_snapshot() -> MarketSnapshot:
    candles: list[Candle] = []
    for index in range(40):
        high = Decimal("101")
        low = Decimal("99")
        open_price = Decimal("100")
        close = Decimal("100")
        if index == 39:
            high = Decimal("102.5")
            low = Decimal("99.5")
            open_price = Decimal("100.6")
            close = Decimal("100.5")
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
    return MarketSnapshot(
        exchange="binance",
        market_type="perpetual",
        symbol="BTCUSDT",
        timeframe="15m",
        candles=tuple(candles),
        captured_at=candles[-1].close_time,
        source="PHASE2_FAKEOUT_TEST",
    )


class CryptoAdaptationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = CryptoAdaptationEngine()

    def test_configuration_version_covers_crypto_threshold_groups(self):
        version = CryptoAdaptationPolicy().configuration_version
        for token in (
            "vol20/60",
            "volume20",
            "fake20/3/0.02",
            "liqSpread2/8",
            "liqImb2",
            "liqDepth0.05/0.25",
            "fund0.0005",
            "oi0.03",
            "mtf2",
        ):
            self.assertIn(token, version)

    def test_missing_optional_crypto_feeds_fail_closed(self):
        assessment = self.engine.evaluate(CryptoAdaptationInput(make_trend_snapshot()))
        self.assertEqual(assessment.liquidity_state, LiquidityState.UNKNOWN)
        self.assertEqual(assessment.derivatives_bias, DerivativesBias.UNKNOWN)
        self.assertEqual(assessment.mtf_alignment, MTFAlignment.UNKNOWN)
        self.assertIn("liquidity_observation_unavailable", assessment.blockers)
        self.assertIn("derivatives_observation_unavailable", assessment.blockers)
        self.assertIn("mtf_context_unavailable", assessment.blockers)
        self.assertFalse(hasattr(assessment, "decision"))
        self.assertFalse(hasattr(assessment, "entry_price"))
        self.assertFalse(hasattr(assessment, "score"))

    def test_relative_volume_spike_is_detected_from_closed_candles(self):
        snapshot = make_trend_snapshot(last_volume=Decimal("30"))
        assessment = self.engine.evaluate(CryptoAdaptationInput(snapshot))
        self.assertEqual(assessment.relative_volume_state, RelativeVolumeState.SPIKE)
        self.assertEqual(assessment.relative_volume_ratio, Decimal("3"))

    def test_recent_volatility_expansion_is_extreme(self):
        assessment = self.engine.evaluate(CryptoAdaptationInput(make_volatility_snapshot()))
        self.assertEqual(assessment.volatility_state, VolatilityState.EXTREME)
        self.assertIsNotNone(assessment.volatility_ratio)
        self.assertGreaterEqual(assessment.volatility_ratio, Decimal("2.25"))

    def test_bull_fake_breakout_is_detected_without_creating_short_signal(self):
        assessment = self.engine.evaluate(CryptoAdaptationInput(make_bull_trap_snapshot()))
        self.assertEqual(assessment.fake_breakout_state, FakeBreakoutState.BULL_TRAP)
        self.assertEqual(assessment.fake_breakout_reference_level, Decimal("101"))
        self.assertFalse(hasattr(assessment, "decision"))

    def test_liquidity_observation_can_classify_deep_market(self):
        snapshot = make_trend_snapshot()
        liquidity = LiquidityObservation(
            captured_at=snapshot.captured_at,
            source="PUBLIC_ORDER_BOOK_TEST",
            spread_bps=Decimal("1"),
            bid_ask_depth_ratio=Decimal("1.1"),
            depth_to_volume_ratio=Decimal("0.30"),
        )
        assessment = self.engine.evaluate(
            CryptoAdaptationInput(snapshot, liquidity=liquidity)
        )
        self.assertEqual(assessment.liquidity_state, LiquidityState.DEEP)
        self.assertNotIn("liquidity_observation_unavailable", assessment.blockers)

    def test_depth_imbalance_has_precedence_over_deep_spread(self):
        snapshot = make_trend_snapshot()
        liquidity = LiquidityObservation(
            captured_at=snapshot.captured_at,
            source="PUBLIC_ORDER_BOOK_TEST",
            spread_bps=Decimal("1"),
            bid_ask_depth_ratio=Decimal("3"),
            depth_to_volume_ratio=Decimal("0.40"),
        )
        assessment = self.engine.evaluate(
            CryptoAdaptationInput(snapshot, liquidity=liquidity)
        )
        self.assertEqual(assessment.liquidity_state, LiquidityState.IMBALANCED)

    def test_positive_funding_plus_rising_oi_marks_long_crowding(self):
        snapshot = make_trend_snapshot()
        derivatives = DerivativesObservation(
            captured_at=snapshot.captured_at,
            source="PUBLIC_DERIVATIVES_TEST",
            funding_rate=Decimal("0.0008"),
            open_interest=Decimal("1000000"),
            open_interest_change_fraction=Decimal("0.05"),
        )
        assessment = self.engine.evaluate(
            CryptoAdaptationInput(snapshot, derivatives=derivatives)
        )
        self.assertEqual(assessment.derivatives_bias, DerivativesBias.LONG_CROWDED)

    def test_negative_funding_plus_rising_oi_marks_short_crowding(self):
        snapshot = make_trend_snapshot()
        derivatives = DerivativesObservation(
            captured_at=snapshot.captured_at,
            source="PUBLIC_DERIVATIVES_TEST",
            funding_rate=Decimal("-0.0008"),
            open_interest_change_fraction=Decimal("0.05"),
        )
        assessment = self.engine.evaluate(
            CryptoAdaptationInput(snapshot, derivatives=derivatives)
        )
        self.assertEqual(assessment.derivatives_bias, DerivativesBias.SHORT_CROWDED)

    def test_incomplete_derivatives_observation_stays_unknown(self):
        snapshot = make_trend_snapshot()
        derivatives = DerivativesObservation(
            captured_at=snapshot.captured_at,
            source="PUBLIC_DERIVATIVES_TEST",
            funding_rate=Decimal("0.0008"),
        )
        assessment = self.engine.evaluate(
            CryptoAdaptationInput(snapshot, derivatives=derivatives)
        )
        self.assertEqual(assessment.derivatives_bias, DerivativesBias.UNKNOWN)
        self.assertIn("derivatives_observation_incomplete", assessment.blockers)

    def test_mtf_alignment_uses_resolved_foundation_contexts(self):
        primary = make_trend_snapshot(timeframe="15m", direction="LONG")
        higher = make_trend_snapshot(
            timeframe="1h", direction="LONG", end_at=primary.captured_at
        )
        data = CryptoAdaptationInput(
            primary_snapshot=primary,
            higher_timeframe_snapshots=(higher,),
        )
        assessment = self.engine.evaluate(data)
        self.assertEqual(assessment.mtf_alignment, MTFAlignment.ALIGNED_LONG)

    def test_mtf_opposition_is_mixed_not_directional_override(self):
        primary = make_trend_snapshot(timeframe="15m", direction="LONG")
        higher = make_trend_snapshot(
            timeframe="1h", direction="SHORT", end_at=primary.captured_at
        )
        assessment = self.engine.evaluate(
            CryptoAdaptationInput(primary, higher_timeframe_snapshots=(higher,))
        )
        self.assertEqual(assessment.mtf_alignment, MTFAlignment.MIXED)
        self.assertFalse(hasattr(assessment, "decision"))

    def test_future_observation_is_rejected(self):
        snapshot = make_trend_snapshot()
        liquidity = LiquidityObservation(
            captured_at=snapshot.captured_at + timedelta(seconds=1),
            source="FUTURE_TEST",
            spread_bps=Decimal("1"),
        )
        with self.assertRaises(ValueError, msg="future observations must fail closed"):
            CryptoAdaptationInput(snapshot, liquidity=liquidity)

    def test_mtf_snapshot_for_different_market_is_rejected(self):
        primary = make_trend_snapshot(timeframe="15m")
        higher = make_trend_snapshot(timeframe="1h")
        foreign = MarketSnapshot(
            exchange=higher.exchange,
            market_type=higher.market_type,
            symbol="ETHUSDT",
            timeframe=higher.timeframe,
            candles=higher.candles,
            captured_at=higher.captured_at,
            source=higher.source,
        )
        with self.assertRaises(ValueError, msg="MTF market identity must match"):
            CryptoAdaptationInput(primary, higher_timeframe_snapshots=(foreign,))

    def test_input_fingerprint_is_deterministic_and_observation_sensitive(self):
        snapshot = make_trend_snapshot()
        first = DerivativesObservation(
            captured_at=snapshot.captured_at,
            source="PUBLIC_DERIVATIVES_TEST",
            funding_rate=Decimal("0.0008"),
            open_interest_change_fraction=Decimal("0.05"),
        )
        second = DerivativesObservation(
            captured_at=snapshot.captured_at,
            source="PUBLIC_DERIVATIVES_TEST",
            funding_rate=Decimal("0.0009"),
            open_interest_change_fraction=Decimal("0.05"),
        )
        a = self.engine.evaluate(CryptoAdaptationInput(snapshot, derivatives=first))
        b = self.engine.evaluate(CryptoAdaptationInput(snapshot, derivatives=first))
        c = self.engine.evaluate(CryptoAdaptationInput(snapshot, derivatives=second))
        self.assertEqual(a.input_fingerprint, b.input_fingerprint)
        self.assertNotEqual(a.input_fingerprint, c.input_fingerprint)

    def test_crypto_evidence_is_separate_from_brooks_source_rule_registry(self):
        assessment = self.engine.evaluate(CryptoAdaptationInput(make_trend_snapshot()))
        self.assertTrue(assessment.evidence)
        self.assertTrue(all(item.evidence_id.startswith("CA-") for item in assessment.evidence))
        self.assertTrue(all(not item.evidence_id.startswith("BB-") for item in assessment.evidence))

    def test_phase2_has_no_existing_production_wiring(self):
        root = Path(__file__).resolve().parents[2]
        needles = ("crypto_adaptation", "CryptoAdaptationEngine")
        offenders: list[Path] = []
        for path in (root / "app").rglob("*.py"):
            if "brooks_core_v3" in path.parts or "__pycache__" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            if any(needle in text for needle in needles):
                offenders.append(path)
        self.assertEqual(offenders, [])

    def test_mtf_must_be_higher_than_primary_timeframe(self):
        primary = make_trend_snapshot(timeframe="1h")
        lower = make_trend_snapshot(
            timeframe="15m", end_at=primary.captured_at
        )
        with self.assertRaises(ValueError, msg="lower timeframe must be rejected"):
            CryptoAdaptationInput(primary, higher_timeframe_snapshots=(lower,))

    def test_future_mtf_capture_time_is_rejected_even_with_closed_candles(self):
        primary = make_trend_snapshot(timeframe="15m")
        aligned = make_trend_snapshot(
            timeframe="1h", end_at=primary.captured_at
        )
        future_capture = MarketSnapshot(
            exchange=aligned.exchange,
            market_type=aligned.market_type,
            symbol=aligned.symbol,
            timeframe=aligned.timeframe,
            candles=aligned.candles,
            captured_at=primary.captured_at + timedelta(seconds=1),
            source=aligned.source,
        )
        with self.assertRaises(ValueError, msg="future HTF capture must fail closed"):
            CryptoAdaptationInput(
                primary, higher_timeframe_snapshots=(future_capture,)
            )


if __name__ == "__main__":
    unittest.main()
