"""Tests for MARC R2 Lead Reversal Transition."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from app.modules.market_data.entities import Candle
from research_layer.marc_r2_lead.engine import (
    _htf_is_aligned,
    _latest_closed_htf_index,
)

D = Decimal
BASE = datetime(2026, 1, 1, tzinfo=UTC)


def _candle(index: int) -> Candle:
    start = BASE + timedelta(minutes=30 * index)
    price = D("100") + D(index)
    return Candle(
        open_time=start,
        close_time=start + timedelta(minutes=30) - timedelta(milliseconds=1),
        open=price,
        high=price + D("1"),
        low=price - D("1"),
        close=price,
        volume=D("1"),
    )


def test_latest_closed_htf_never_uses_incomplete_30m_bar():
    candles = tuple(_candle(i) for i in range(4))

    before_second_close = candles[1].close_time - timedelta(seconds=1)
    at_second_close = candles[1].close_time

    assert _latest_closed_htf_index(
        candles,
        signal_close_time=before_second_close,
    ) == 0
    assert _latest_closed_htf_index(
        candles,
        signal_close_time=at_second_close,
    ) == 1


def test_htf_alignment_rule_rejects_mature_direction_but_allows_lead_state():
    bull = SimpleNamespace(
        ma7=D("103"),
        ma25=D("102"),
        ma99=D("100"),
        close=D("104"),
    )
    mixed = SimpleNamespace(
        ma7=D("101"),
        ma25=D("102"),
        ma99=D("100"),
        close=D("103"),
    )
    bear = SimpleNamespace(
        ma7=D("97"),
        ma25=D("98"),
        ma99=D("100"),
        close=D("96"),
    )

    assert _htf_is_aligned(htf_frame=bull, direction="LONG") is True
    assert _htf_is_aligned(htf_frame=mixed, direction="LONG") is False
    assert _htf_is_aligned(htf_frame=bear, direction="LONG") is False

    assert _htf_is_aligned(htf_frame=bear, direction="SHORT") is True
    assert _htf_is_aligned(htf_frame=mixed, direction="SHORT") is False
    assert _htf_is_aligned(htf_frame=bull, direction="SHORT") is False
