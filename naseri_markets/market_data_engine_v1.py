"""Stage 5: deterministic, offline-only, provider-neutral market data fan-out.

Input is explicit REPLAY/SYNTHETIC evidence, never an authenticated live feed.
No network, imports of third-party strategies, persistence, broker or Telegram.
The platform owns every feed and binding; strategy implementations are never
allowed to choose a venue, broker, symbol, account, leverage, or channel.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from .contracts import Instrument
from .core_api_v1 import (
    _TIMEFRAME_MINUTES, BidAskTick, ClosedCandle, CoreBinding, CoreEventType, CoreInput,
    CoreManifest, DataOrigin, content_digest, _token, _utc,
)


class MarketDataRefused(ValueError):
    """Closed-failure; do not route an invalid packet to any strategy."""


class PacketStatus(StrEnum):
    ACCEPTED = "accepted"
    DUPLICATE = "duplicate"
    WARMING = "warming"


class VolumeSemantics(StrEnum):
    TRADED = "traded"
    TICK_COUNT = "tick_count"
    UNKNOWN = "unknown"


class PriceBasis(StrEnum):
    TRADE = "trade"
    BID = "bid"
    ASK = "ask"
    MID = "mid"
    MARK = "mark"
    INDEX = "index"
    BID_ASK = "bid_ask"


@dataclass(frozen=True, slots=True)
class FeedDefinition:
    """Platform-administered immutable offline input lane, not an API client."""

    feed_id: str
    instrument: Instrument
    timeframe: str
    event: CoreEventType
    origin: DataOrigin
    source_ref: str
    price_basis: PriceBasis
    volume_semantics: VolumeSemantics = VolumeSemantics.UNKNOWN
    max_latency_seconds: int = 120
    history_limit: int = 128

    def __post_init__(self) -> None:
        _token(self.feed_id, "FEED_ID")
        _token(self.source_ref, "SOURCE_REF")
        if not isinstance(self.instrument, Instrument):
            raise MarketDataRefused("INVALID_INSTRUMENT")
        if not isinstance(self.origin, DataOrigin):
            raise MarketDataRefused("OFFLINE_ORIGIN_REQUIRED")
        if type(self.event) is not CoreEventType or self.event not in (CoreEventType.CLOSED_CANDLE, CoreEventType.QUOTE_TICK):
            raise MarketDataRefused("UNSUPPORTED_MARKET_EVENT")
        if self.timeframe not in ("1m", "5m", "15m", "30m", "1h", "4h", "12h", "1d"):
            raise MarketDataRefused("INVALID_TIMEFRAME")
        if not isinstance(self.price_basis, PriceBasis):
            raise MarketDataRefused("PRICE_BASIS_REQUIRED")
        if not isinstance(self.volume_semantics, VolumeSemantics):
            raise MarketDataRefused("UNKNOWN_VOLUME_SEMANTICS")
        if ((self.event is CoreEventType.QUOTE_TICK and
             self.price_basis is not PriceBasis.BID_ASK) or
                (self.event is CoreEventType.CLOSED_CANDLE and
                 self.price_basis is PriceBasis.BID_ASK)):
            raise MarketDataRefused("INVALID_PRICE_BASIS_FOR_EVENT")
        if (self.event is CoreEventType.QUOTE_TICK and
                self.volume_semantics is not VolumeSemantics.UNKNOWN):
            raise MarketDataRefused("TICK_HAS_NO_VOLUME")
        if (type(self.max_latency_seconds) is not int or
                not 0 <= self.max_latency_seconds <= 86400):
            raise MarketDataRefused("INVALID_MAX_LATENCY")
        if (type(self.history_limit) is not int or not 1 <= self.history_limit <= 512):
            raise MarketDataRefused("INVALID_HISTORY_LIMIT")


@dataclass(frozen=True, slots=True)
class MarketPacket:
    """One exact offline sample; timestamps are UTC-aware and causal."""

    feed_id: str
    sequence: int
    received_at: datetime
    source_ref: str
    candle: ClosedCandle | None = None
    tick: BidAskTick | None = None

    def __post_init__(self) -> None:
        _token(self.feed_id, "FEED_ID")
        _token(self.source_ref, "SOURCE_REF")
        if type(self.sequence) is not int or self.sequence <= 0:
            raise MarketDataRefused("INVALID_SEQUENCE")
        object.__setattr__(self, "received_at", _utc(self.received_at))
        if (self.candle is None) == (self.tick is None):
            raise MarketDataRefused("EXACTLY_ONE_SAMPLE_REQUIRED")
        if self.candle is not None and not isinstance(self.candle, ClosedCandle):
            raise MarketDataRefused("INVALID_CANDLE")
        if self.tick is not None and not isinstance(self.tick, BidAskTick):
            raise MarketDataRefused("INVALID_TICK")

    @property
    def observed_at(self) -> datetime:
        return self.candle.close_at if self.candle is not None else self.tick.occurred_at


@dataclass(frozen=True, slots=True)
class MarketDelivery:
    """An inert Core API event and its price/volume semantics; NOT a signal."""

    instance_id: str
    binding_id: str
    event: CoreInput
    price_basis: PriceBasis
    volume_semantics: VolumeSemantics


@dataclass(frozen=True, slots=True)
class MarketDispatch:
    feed_id: str
    sequence: int
    status: PacketStatus
    deliveries: tuple[MarketDelivery, ...]
    waiting_bindings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class FeedState:
    feed_id: str
    quarantined: bool
    last_sequence: int | None
    retained_bars: int
    subscriptions: int


class _FeedLane:
    def __init__(self, definition: FeedDefinition) -> None:
        self.definition = definition
        self.history: deque[ClosedCandle] = deque(maxlen=definition.history_limit)
        self.last_sequence: int | None = None
        self.last_digest: str | None = None
        self.last_observed_at: datetime | None = None
        self.last_received_at: datetime | None = None
        self.quarantined = False
        self.bindings: dict[str, tuple[CoreManifest, CoreBinding]] = {}


class OfflineMarketDataEngine:
    """A host-owned data distributor. It never calls a strategy or adapter.

    Subscribe first; ingest sequential typed packets. Failures quarantine the
    affected feed, never other feeds. Recovery requires explicit host reset.
    The orchestrator/secure-plugin host decides whether/how to evaluate inputs.
    """

    def __init__(self, *, enabled: bool = False) -> None:
        self.enabled = enabled
        self._lanes: dict[str, _FeedLane] = {}
        self._binding_owner: dict[str, str] = {}

    def register_feed(self, definition: FeedDefinition) -> None:
        if definition.feed_id in self._lanes:
            raise MarketDataRefused("FEED_ALREADY_REGISTERED")
        self._lanes[definition.feed_id] = _FeedLane(definition)

    def subscribe(self, feed_id: str, manifest: CoreManifest, binding: CoreBinding) -> None:
        if feed_id not in self._lanes:
            raise MarketDataRefused("UNKNOWN_FEED")
        lane = self._lanes[feed_id]
        spec = lane.definition
        if (not isinstance(manifest, CoreManifest) or
                not isinstance(binding, CoreBinding) or
                binding.instrument != spec.instrument or binding.timeframe != spec.timeframe or
                binding.instrument.market not in manifest.supported_markets or
                spec.event not in manifest.accepted_events or
                (spec.event is CoreEventType.CLOSED_CANDLE and
                 manifest.minimum_closed_candles > spec.history_limit)):
            raise MarketDataRefused("INCOMPATIBLE_SUBSCRIPTION")
        if binding.binding_id in self._binding_owner:
            raise MarketDataRefused("DUPLICATE_BINDING_ID")
        self._binding_owner[binding.binding_id] = feed_id
        lane.bindings[binding.binding_id] = (manifest, binding)

    def state(self, feed_id: str) -> FeedState:
        lane = self._lane(feed_id)
        return FeedState(feed_id, lane.quarantined, lane.last_sequence,
                         len(lane.history), len(lane.bindings))

    def _lane(self, feed_id: str) -> _FeedLane:
        try:
            return self._lanes[feed_id]
        except KeyError as exc:
            raise MarketDataRefused("UNKNOWN_FEED") from exc

    def reset_feed(self, feed_id: str, *, operator_ack: bool = False) -> None:
        """Rebuild state only following independent operator feed resynchronization."""
        if operator_ack is not True:
            raise MarketDataRefused("OPERATOR_RESYNC_REQUIRED")
        lane = self._lane(feed_id)
        lane.history.clear()
        lane.last_sequence = None
        lane.last_digest = None
        lane.last_observed_at = None
        lane.last_received_at = None
        lane.quarantined = False

    def ingest(self, packet: MarketPacket) -> MarketDispatch:
        if not self.enabled:
            raise MarketDataRefused("MARKET_DATA_ENGINE_DISABLED")
        if not isinstance(packet, MarketPacket):
            raise MarketDataRefused("INVALID_PACKET")
        lane = self._lane(packet.feed_id)
        if lane.quarantined:
            raise MarketDataRefused("FEED_QUARANTINED")
        spec = lane.definition
        packet_digest = content_digest(packet)
        if lane.last_sequence is not None and packet.sequence == lane.last_sequence:
            if packet_digest == lane.last_digest:
                return MarketDispatch(packet.feed_id, packet.sequence,
                                      PacketStatus.DUPLICATE, (), ())
            lane.quarantined = True
            raise MarketDataRefused("CONFLICTING_DUPLICATE_QUARANTINED")
        try:
            self._validate(lane, packet)
            history = tuple(lane.history)
            if packet.candle is not None:
                history = (*history, packet.candle)[-spec.history_limit:]
            deliveries: list[MarketDelivery] = []
            waiting: list[str] = []
            for key, (manifest, binding) in lane.bindings.items():
                if spec.event is CoreEventType.CLOSED_CANDLE:
                    if len(history) < manifest.minimum_closed_candles:
                        waiting.append(key)
                        continue
                    event = CoreInput(
                        manifest.core_id, manifest.core_version, binding,
                        CoreEventType.CLOSED_CANDLE, packet.observed_at,
                        spec.origin, spec.source_ref, history,
                    )
                else:
                    event = CoreInput(
                        manifest.core_id, manifest.core_version, binding,
                        CoreEventType.QUOTE_TICK, packet.observed_at,
                        spec.origin, spec.source_ref, tick=packet.tick,
                    )
                deliveries.append(MarketDelivery(binding.instance_id, key, event,
                                                 spec.price_basis, spec.volume_semantics))
            # Commit state only after ALL intended CoreInputs are validated.
            if packet.candle is not None:
                lane.history.append(packet.candle)
            lane.last_observed_at = packet.observed_at
            lane.last_received_at = packet.received_at
            lane.last_sequence = packet.sequence
            lane.last_digest = packet_digest
            status = PacketStatus.WARMING if waiting and not deliveries else PacketStatus.ACCEPTED
            return MarketDispatch(packet.feed_id, packet.sequence, status,
                                  tuple(deliveries), tuple(waiting))
        except Exception as exc:
            lane.quarantined = True
            if isinstance(exc, MarketDataRefused):
                raise
            raise MarketDataRefused("PACKET_OR_CORE_INPUT_REJECTED") from exc

    def _validate(self, lane: _FeedLane, packet: MarketPacket) -> None:
        spec = lane.definition
        if packet.source_ref != spec.source_ref:
            raise MarketDataRefused("SOURCE_IDENTITY_MISMATCH")
        if (spec.event is CoreEventType.CLOSED_CANDLE) != (packet.candle is not None):
            raise MarketDataRefused("WRONG_SAMPLE_TYPE")
        if packet.candle is not None:
            duration = packet.candle.close_at - packet.candle.open_at
            expected = timedelta(minutes=_TIMEFRAME_MINUTES[spec.timeframe])
            if ((spec.timeframe != "1d" and duration != expected) or
                    (spec.timeframe == "1d" and
                     not timedelta(hours=23) <= duration <= timedelta(hours=25))):
                raise MarketDataRefused("CANDLE_TIMEFRAME_MISMATCH")
        age = packet.received_at - packet.observed_at
        if age < timedelta(0) or age > timedelta(seconds=spec.max_latency_seconds):
            raise MarketDataRefused("LATE_OR_FUTURE_SAMPLE")
        if lane.last_sequence is not None:
            if packet.received_at < lane.last_received_at:
                raise MarketDataRefused("RECEIPT_TIME_ROLLBACK")
            if packet.sequence != lane.last_sequence + 1:
                raise MarketDataRefused("SEQUENCE_GAP_OR_ROLLBACK")
            if packet.observed_at < lane.last_observed_at:
                raise MarketDataRefused("OUT_OF_ORDER_MARKET_TIME")
            if packet.candle is not None and lane.history and (
                    packet.candle.open_at != lane.history[-1].close_at or
                    packet.observed_at <= lane.last_observed_at):
                raise MarketDataRefused("CANDLE_GAP_OR_OVERLAP")


__all__ = ["FeedDefinition", "FeedState", "MarketDataRefused", "MarketDelivery",
           "MarketDispatch", "MarketPacket", "OfflineMarketDataEngine",
           "PacketStatus", "PriceBasis", "VolumeSemantics"]
