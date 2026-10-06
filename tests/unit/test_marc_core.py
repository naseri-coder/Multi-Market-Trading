"""Frozen MARC v0.1 unit and causality contract tests."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.modules.market_data.entities import Candle, MarketSnapshot
from app.modules.marc_core.engine import MARCSignalEngine, evaluate_indicator_frames
from app.modules.marc_core.entities import MARCDecision, MARCIndicatorFrame, MARCState
from app.modules.marc_core.indicators import build_indicator_frames
from app.modules.marc_core.replay import replay_entry_plans


D = Decimal
BASE = datetime(2026, 1, 1, tzinfo=UTC)


def frame(i, *, close, ma7, ma25, ma99=100, atr=10, high=None, low=None):
    c = D(str(close))
    return MARCIndicatorFrame(
        index=i,
        close_time=BASE + timedelta(minutes=15 * (i + 1)),
        open=c,
        high=D(str(high if high is not None else c + 1)),
        low=D(str(low if low is not None else c - 1)),
        close=c,
        ma7=None if ma7 is None else D(str(ma7)),
        ma25=None if ma25 is None else D(str(ma25)),
        ma99=None if ma99 is None else D(str(ma99)),
        atr14=None if atr is None else D(str(atr)),
    )


def evaluate(frames, timeframe="15m"):
    return evaluate_indicator_frames(
        tuple(frames),
        symbol="BTCUSDT",
        timeframe=timeframe,
        snapshot_id="snap",
        snapshot_hash="hash",
    )


def test_long_ready_requires_cross_ma99_band_and_two_closes():
    frames = [
        frame(0, close=100, ma7=99, ma25=100),
        frame(1, close=100.5, ma7=101, ma25=100),
        frame(2, close=101.5, ma7=102, ma25=100),
        frame(3, close=102, ma7=103, ma25=100),
    ]
    result = evaluate(frames)
    assert result.state == MARCState.LONG_READY
    assert result.direction == "LONG"
    assert result.cross_index == 1
    assert result.confirmation_index == 3
    assert result.persistence_count == 2
    assert result.fresh is True


def test_short_ready_is_exact_directional_mirror():
    frames = [
        frame(0, close=100, ma7=101, ma25=100),
        frame(1, close=99.5, ma7=99, ma25=100),
        frame(2, close=98.5, ma7=98, ma25=100),
        frame(3, close=98, ma7=97, ma25=100),
    ]
    result = evaluate(frames)
    assert result.state == MARCState.SHORT_READY
    assert result.direction == "SHORT"
    assert result.fresh is True


def test_false_reclaim_invalidates_before_persistence_completes():
    frames = [
        frame(0, close=100, ma7=99, ma25=100),
        frame(1, close=100.2, ma7=101, ma25=100),
        frame(2, close=101.5, ma7=102, ma25=100),
        frame(3, close=98.5, ma7=103, ma25=100),
    ]
    result = evaluate(frames)
    assert result.state == MARCState.INVALIDATED_FALSE_BREAK
    assert result.direction == "LONG"


def test_chop_filter_blocks_third_cross_inside_twenty_bars():
    frames = [
        frame(0, close=100, ma7=99, ma25=100),
        frame(1, close=100, ma7=101, ma25=100),
        frame(2, close=100, ma7=99, ma25=100),
        frame(3, close=100, ma7=101, ma25=100),
        frame(4, close=101.5, ma7=102, ma25=100),
        frame(5, close=102, ma7=103, ma25=100),
    ]
    assert evaluate(frames).state == MARCState.NO_TRADE_CHOP


def test_compression_filter_blocks_tight_ma_cluster():
    frames = [
        frame(0, close=100, ma7=99.9, ma25=100),
        frame(1, close=100.2, ma7=100.05, ma25=100),
        frame(2, close=101.2, ma7=100.08, ma25=100),
        frame(3, close=101.3, ma7=100.1, ma25=100),
    ]
    assert evaluate(frames).state == MARCState.NO_TRADE_COMPRESSION


def test_overextension_filter_blocks_late_confirmation():
    frames = [
        frame(0, close=100, ma7=99, ma25=100),
        frame(1, close=100.2, ma7=101, ma25=100),
        frame(2, close=116, ma7=102, ma25=100),
        frame(3, close=117, ma7=103, ma25=100),
    ]
    result = evaluate(frames)
    assert result.state == MARCState.NO_TRADE_OVEREXTENDED
    assert result.extension_atr == D("1.7")


def test_cross_expires_without_ma99_confirmation():
    frames = [frame(0, close=100, ma7=99, ma25=100)]
    frames.append(frame(1, close=100, ma7=101, ma25=100))
    for i in range(2, 15):
        frames.append(frame(i, close=100.5, ma7=102, ma25=100))
    assert evaluate(frames).state == MARCState.SETUP_EXPIRED


def snapshot_for_candidate(*, low=99, high=103):
    candles = []
    for i in range(5):
        close = D("101") + D(i) / D("10")
        candles.append(
            Candle(
                open_time=BASE + timedelta(minutes=15 * i),
                close_time=BASE + timedelta(minutes=15 * (i + 1)),
                open=close,
                high=D(str(high)),
                low=D(str(low)),
                close=close,
                volume=D("1"),
            )
        )
    return MarketSnapshot(
        exchange="binance",
        market_type="futures",
        symbol="BTCUSDT",
        timeframe="15m",
        candles=tuple(candles),
        captured_at=candles[-1].close_time,
    )


def ready_decision(snapshot):
    return MARCDecision(
        symbol="BTCUSDT",
        timeframe="15m",
        state=MARCState.LONG_READY,
        direction="LONG",
        snapshot_id=snapshot.snapshot_id,
        snapshot_hash=snapshot.snapshot_hash,
        cross_index=1,
        confirmation_index=4,
        persistence_count=2,
        ma7=D("103"),
        ma25=D("100"),
        ma99=D("100"),
        atr14=D("10"),
        normalized_spread_atr=D("0.3"),
        extension_atr=D("0.14"),
        fresh=True,
        reason="test",
    )


def test_entry_plan_uses_structure_plus_ma_stop_and_1r_2r_targets():
    snap = snapshot_for_candidate()
    plan = MARCSignalEngine().build_entry_plan(
        snap, ready_decision(snap), entry_price=D("102")
    )
    assert plan.accepted is True
    assert plan.candidate is not None
    assert plan.candidate.stop_loss == D("95.00")
    assert plan.candidate.targets == (D("109.00"), D("116.00"))
    assert plan.candidate.initial_risk_atr == D("0.70")
    assert plan.candidate.risk_fraction == D("0.005")


def test_entry_plan_rejects_structural_risk_over_1_8_atr():
    snap = snapshot_for_candidate(low=80)
    plan = MARCSignalEngine().build_entry_plan(
        snap, ready_decision(snap), entry_price=D("102")
    )
    assert plan.accepted is False
    assert plan.rejection_reason == "MAX_INITIAL_RISK_ATR_EXCEEDED"


def test_default_indicators_are_sma_7_25_99_and_wilder_atr14():
    candles = []
    for i in range(100):
        close = D(i + 1)
        candles.append(
            Candle(
                open_time=BASE + timedelta(minutes=15 * i),
                close_time=BASE + timedelta(minutes=15 * (i + 1)),
                open=close,
                high=close + 1,
                low=max(D("0"), close - 1),
                close=close,
                volume=D("1"),
            )
        )
    snap = MarketSnapshot(
        exchange="binance",
        market_type="futures",
        symbol="BTCUSDT",
        timeframe="15m",
        candles=tuple(candles),
        captured_at=candles[-1].close_time,
    )
    last = build_indicator_frames(snap)[-1]
    assert last.ma7 == D("97")
    assert last.ma25 == D("88")
    assert last.ma99 == D("51")
    assert last.atr14 == D("2")


def test_engine_rejects_unsupported_timeframe():
    candle = Candle(
        open_time=BASE,
        close_time=BASE + timedelta(hours=1),
        open=D("100"),
        high=D("101"),
        low=D("99"),
        close=D("100"),
        volume=D("1"),
    )
    snap = MarketSnapshot(
        exchange="binance",
        market_type="futures",
        symbol="BTCUSDT",
        timeframe="1h",
        candles=(candle,),
        captured_at=candle.close_time,
    )
    with pytest.raises(ValueError, match="15m and 30m"):
        MARCSignalEngine().evaluate(snap)


def test_replay_returns_no_entry_for_monotonic_series_without_recent_cross():
    candles = []
    for i in range(110):
        close = D(100 + i)
        candles.append(
            Candle(
                open_time=BASE + timedelta(minutes=15 * i),
                close_time=BASE + timedelta(minutes=15 * (i + 1)),
                open=close,
                high=close + 1,
                low=close - 1,
                close=close,
                volume=D("1"),
            )
        )
    snap = MarketSnapshot(
        exchange="binance",
        market_type="futures",
        symbol="BTCUSDT",
        timeframe="15m",
        candles=tuple(candles),
        captured_at=candles[-1].close_time,
    )
    assert replay_entry_plans(snap) == ()
