"""Immutable MARC backtest result contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class TradeFill:
    time: datetime
    price: float
    fraction: float
    reason: str


@dataclass(frozen=True, slots=True)
class BacktestTrade:
    symbol: str
    timeframe: str
    direction: str
    source_signal_id: str
    entry_time: datetime
    entry_price: float
    stop_loss: float
    exit_time: datetime
    duration_bars: int
    fills: tuple[TradeFill, ...]
    gross_r: float
    base_net_r: float
    stress_net_r: float
    tp1_hit: bool
    tp2_hit: bool
    terminal_reason: str
