"""LIVE VIP delivery contracts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class LiveVipPublishPayload:
    signal_id: int
    symbol: str
    timeframe: str
    direction: str
    setup_type: str | None
    entry_price: Decimal
    stop_loss: Decimal
    targets: tuple[Decimal, ...]
    leverage: Decimal
    market_snapshot_id: str
    chart_path: str
    quality_grade: str
    final_score: Decimal
    confidence: Decimal
    market_regime: str | None


@dataclass(frozen=True, slots=True)
class LiveVipRunResult:
    signal_id: int
    signal_created: bool
    delivery_status: str
    external_message_id: str | None
