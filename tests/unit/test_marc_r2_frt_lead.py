"""Tests for MARC R2 FRT Lead Reversal."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.modules.market_data.entities import Candle
from research_layer.marc_r2_lead.engine import _latest_closed_30m_alignment

BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _candle(index: int) -> Candle:
    start = BASE + timedelta(minutes=30 * index)
    return Candle(
        open_time=start,
        close_time=start + timedelta(minutes=30) - timedelta(milliseconds=1),
        open=100,
        high=101,
        low=99,
        close=100,
        volume=1,
    )


def _frame(*, close: int, ma7: int, ma25: int, ma99: int):
    return SimpleNamespace(close=close, ma7=ma7, ma25=ma25, ma99=ma99)


def test_lead_alignment_uses_only_latest_fully_closed_30m_bar():
    candles = (_candle(0), _candle(1))
    frames = (
        _frame(close=99, ma7=98, ma25=99, ma99=100),
        _frame(close=101, ma7=102, ma25=101, ma99=100),
    )

    before_second_close = candles[1].close_time - timedelta(seconds=1)
    after_second_close = candles[1].close_time

    assert _latest_closed_30m_alignment(
        candles_30m=candles,
        frames_30m=frames,
        signal_close_time=before_second_close,
        direction="LONG",
    ) == "OPPOSED"
    assert _latest_closed_30m_alignment(
        candles_30m=candles,
        frames_30m=frames,
        signal_close_time=after_second_close,
        direction="LONG",
    ) == "ALIGNED"


def test_mixed_30m_context_is_a_lead_state_not_alignment():
    candles = (_candle(0),)
    frames = (_frame(close=101, ma7=99, ma25=100, ma99=100),)

    assert _latest_closed_30m_alignment(
        candles_30m=candles,
        frames_30m=frames,
        signal_close_time=candles[0].close_time,
        direction="LONG",
    ) == "MIXED"
