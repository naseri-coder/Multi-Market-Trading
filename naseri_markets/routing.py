"""Fail-closed signal delivery decision, deliberately without network or Telegram I/O."""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import EvidenceMode, Market, SignalIntent
from .registry import EngineRegistry


@dataclass(frozen=True, slots=True)
class ChannelRoute:
    engine_id: str
    market: Market
    private_channel_id: int | None = None
    enabled: bool = False
    channel_verified_private: bool = False
    realtime_feed_verified: bool = False


@dataclass(frozen=True, slots=True)
class RouteDecision:
    allowed: bool
    reason: str
    channel_id: int | None = None


def decide_delivery(
    signal: SignalIntent,
    registry: EngineRegistry,
    route: ChannelRoute,
) -> RouteDecision:
    """Forbid unverified publication. Decision alone never sends a message."""

    try:
        registry.validate_intent(signal)
    except ValueError:
        return RouteDecision(False, "ENGINE_CONTRACT_REJECTED")
    if route.engine_id != signal.engine_id or route.market != signal.instrument.market:
        return RouteDecision(False, "ROUTE_IDENTITY_MISMATCH")
    if not route.enabled:
        return RouteDecision(False, "ROUTE_DISABLED")
    if signal.evidence_mode is not EvidenceMode.FORWARD:
        return RouteDecision(False, "NOT_FORWARD_OBSERVATION")
    if not route.realtime_feed_verified:
        return RouteDecision(False, "FEED_NOT_VERIFIED")
    if (
        route.private_channel_id is None
        or isinstance(route.private_channel_id, bool)
        or route.private_channel_id >= 0
        or not route.channel_verified_private
    ):
        return RouteDecision(False, "PRIVATE_CHANNEL_NOT_VERIFIED")
    return RouteDecision(True, "DELIVERY_ALLOWED", route.private_channel_id)
