"""DATA-A1 operator file intake: real local CSV/Parquet -> inert PAPER CoreInput.

Files are full-validated by historical_data_loader_a1 before any packet is
delivered; inputs come from a locally pinned SHA256, not a provider API.
No trading core, execution worker, broker, Telegram or DB is invoked.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from .contracts import Instrument, Market
from .core_api_v1 import (
    CoreBinding, CoreEventType, CoreManifest, DataOrigin, SetupSpec,
)
from .historical_data_loader_a1 import (
    HistoricalDataRefused, HistoricalFileSpec, validate_historical_file,
)
from .market_data_engine_v1 import (
    FeedDefinition, MarketDataRefused, OfflineMarketDataEngine,
    PacketStatus, PriceBasis, VolumeSemantics,
)


@dataclass(frozen=True, slots=True)
class HistoricalIntakeReport:
    """Integrity + typed PAPER data delivery; NOT market-source attestation."""

    status: str
    format: str
    market: str
    provider_claim: str
    symbol: str
    timezone: str
    quote_currency: str
    timeframe: str
    price_basis: str
    volume_semantics: str
    sha256: str
    feed_id: str
    source_ref: str
    rows_validated: int
    paper_core_inputs_validated: int
    first_observed_at: datetime
    last_observed_at: datetime
    first_available_at: datetime
    last_available_at: datetime
    lowest_observed_price: str
    highest_observed_price: str
    zero_volume_rows: int
    widest_bid_ask_spread: str | None
    quality_status: str = "STRUCTURAL_CHECKS_PASS_PROVIDER_PROVENANCE_UNVERIFIED"
    source_authenticated: bool = False
    point_in_time_feed_certified: bool = False
    exchange_calendar_verified: bool = False
    paper_strategy_executed: bool = False
    broker_order_sent: bool = False
    telegram_sent: bool = False
    worker_execution_authorized: bool = False


def inspect_historical_for_paper(
    path: Path, *, sha256: str, market: Market, provider: str,
    symbol: str, timezone: str, quote_currency: str, timeframe: str,
    event: CoreEventType, price_basis: PriceBasis,
    volume_semantics: VolumeSemantics, availability_lag_seconds: int = 0,
    max_rows: int = 5_000_000, operator_ack: bool = False,
) -> HistoricalIntakeReport:
    """Host-only offline intake into the existing Stage-5 PAPER data lane.

    One small typed inspector manifest is used ONLY to create inert CoreInputs.
    No strategy's evaluate method is called. No persistent side effects.
    Output is returned only after complete replay / quality validation.
    """
    if (os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"
            or operator_ack is not True):
        raise HistoricalDataRefused("DATA_A1_EXPLICIT_OFFLINE_PAPER_ACK_REQUIRED")
    if not isinstance(path, Path) or not path.is_absolute():
        raise HistoricalDataRefused("DATA_A1_ABSOLUTE_FILE_PATH_REQUIRED")
    if (type(provider) is not str or type(symbol) is not str
            or type(timezone) is not str or type(quote_currency) is not str
            or any(not 0 < len(x) <= 96 or not x.strip()
                   for x in (provider, symbol, timezone, quote_currency))):
        raise HistoricalDataRefused("DATA_A1_EXPLICIT_SOURCE_METADATA_REQUIRED")
    if not isinstance(market, Market):
        raise HistoricalDataRefused("DATA_A1_MARKET_REQUIRED")
    if type(event) is not CoreEventType or not isinstance(price_basis, PriceBasis):
        raise HistoricalDataRefused("DATA_A1_EVENT_AND_PRICE_BASIS_REQUIRED")
    if not isinstance(volume_semantics, VolumeSemantics):
        raise HistoricalDataRefused("DATA_A1_VOLUME_SEMANTICS_REQUIRED")
    # The host specifies identity and expected bytes. Neither is inferred
    # from a third-party file nor presented as exchange-authenticated data.
    try:
        instrument = Instrument(market, provider, symbol, timezone, quote_currency)
        feed = FeedDefinition(
            "data_a1_" + sha256[:32], instrument, timeframe,
            event, DataOrigin.REPLAY, "hist_" + sha256[:40],
            price_basis, volume_semantics,
            max_latency_seconds=120,
            history_limit=128,
        )
        spec = HistoricalFileSpec(
            feed, sha256, availability_lag_seconds, max_rows,
        )
        approved = validate_historical_file(path, spec)
        engine = OfflineMarketDataEngine(enabled=True)
        engine.register_feed(feed)
        inspector = CoreManifest(
            "DataA1Inspector", "1.0",
            (SetupSpec("no_strategy", "Read-only historical data validation"),),
            frozenset({market}), frozenset({event}),
            minimum_closed_candles=1,
        )
        engine.subscribe(
            feed.feed_id, inspector,
            CoreBinding("data_a1_inspector", "data_a1_binding",
                        instrument, timeframe),
        )
        inputs = zero_volume = 0
        lo: Decimal | None = None
        hi: Decimal | None = None
        widest: Decimal | None = None
        first_available: datetime | None = None
        last_available: datetime | None = None
        for packet in approved.packets():
            delivery = engine.ingest(packet)
            if delivery.status is not PacketStatus.ACCEPTED or len(delivery.deliveries) != 1:
                raise HistoricalDataRefused("DATA_A1_PAPER_DELIVERY_NOT_VALIDATED")
            record = delivery.deliveries[0]
            event_data = record.event
            if (event_data.origin is not DataOrigin.REPLAY
                    or event_data.observed_at != packet.observed_at
                    or event_data.observed_at > packet.received_at
                    or event_data.source_ref != feed.source_ref
                    or record.price_basis is not price_basis
                    or record.volume_semantics is not volume_semantics):
                raise HistoricalDataRefused("DATA_A1_PAPER_CAUSAL_SCOPE_DRIFT")
            if packet.candle is not None:
                if (event_data.candles[-1] != packet.candle
                        or event_data.candles[-1].close_at != packet.observed_at):
                    raise HistoricalDataRefused("DATA_A1_CANDLE_LOOKAHEAD_DETECTED")
                price_low = packet.candle.low
                price_high = packet.candle.high
                zero_volume += int(packet.candle.volume == 0)
            elif packet.tick is not None:
                if event_data.tick != packet.tick:
                    raise HistoricalDataRefused("DATA_A1_TICK_SCOPE_DRIFT")
                price_low = packet.tick.bid
                price_high = packet.tick.ask
                spread = price_high - price_low
                widest = spread if widest is None else max(widest, spread)
            else:
                raise HistoricalDataRefused("DATA_A1_MARKET_PACKET_MISSING_SAMPLE")
            lo = price_low if lo is None else min(lo, price_low)
            hi = price_high if hi is None else max(hi, price_high)
            if first_available is None:
                first_available = packet.received_at
            last_available = packet.received_at
            inputs += 1
        if (inputs != approved.report.rows_validated
                or lo is None or hi is None
                or first_available is None or last_available is None
                or engine.state(feed.feed_id).quarantined):
            raise HistoricalDataRefused("DATA_A1_INCOMPLETE_PAPER_VALIDATION")
        return HistoricalIntakeReport(
            status="DATA_A1_FILE_VALIDATED_OFFLINE_PAPER_INPUT_ONLY",
            format=approved.report.format,
            market=market.value, provider_claim=provider,
            symbol=symbol, timezone=timezone, quote_currency=quote_currency,
            timeframe=timeframe, price_basis=price_basis.value,
            volume_semantics=volume_semantics.value,
            sha256=approved.report.sha256,
            feed_id=feed.feed_id, source_ref=feed.source_ref,
            rows_validated=approved.report.rows_validated,
            paper_core_inputs_validated=inputs,
            first_observed_at=approved.report.first_observed_at,
            last_observed_at=approved.report.last_observed_at,
            first_available_at=first_available, last_available_at=last_available,
            lowest_observed_price=str(lo), highest_observed_price=str(hi),
            zero_volume_rows=zero_volume,
            widest_bid_ask_spread=str(widest) if widest is not None else None,
        )
    except (ValueError, TypeError) as exc:
        if isinstance(exc, HistoricalDataRefused):
            raise
        if isinstance(exc, MarketDataRefused):
            raise HistoricalDataRefused("DATA_A1_PAPER_LANE_REJECTED") from exc
        raise HistoricalDataRefused("DATA_A1_FILE_METADATA_OR_EVENT_REJECTED") from exc


__all__ = ["HistoricalIntakeReport", "inspect_historical_for_paper"]
