"""Stage 21: operator-invoked KuCoin Futures public OHLC -> offline REPLAY.

This is a research data adapter, NOT a live execution feed or permission for
PAPER allocations, signal sending, broker routing, or trading. No background IO.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Callable

from .contracts import Market
from .core_api_v1 import (
    ClosedCandle, CoreBinding, CoreEventType, CoreManifest, DataOrigin,
)
from .market_data_engine_v1 import (
    FeedDefinition, MarketPacket, OfflineMarketDataEngine, PriceBasis,
    VolumeSemantics,
)

BASE_URL = "https://api-futures.kucoin.com/api/v1/kline/query"
PERIODS = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60,
           "4h": 240, "12h": 720, "1d": 1440}
SYMBOL = re.compile(r"[A-Z][A-Z0-9]{4,19}\Z")
MAX_BYTES = 256 * 1024


class VenueReplayRefused(ValueError):
    """Fail-closed read-only data and identity error."""


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise VenueReplayRefused("UTC_AWARE_TIME_REQUIRED")
    return value.astimezone(UTC)


def _ms(value: datetime) -> int:
    dt = _utc(value)
    if dt.microsecond % 1000:
        raise VenueReplayRefused("MILLISECOND_ALIGNED_TIME_REQUIRED")
    return int(dt.timestamp() * 1000)


@dataclass(frozen=True)
class FuturesKlineRequest:
    symbol: str
    timeframe: str
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if (type(self.symbol) is not str or not SYMBOL.fullmatch(self.symbol)
                or self.timeframe not in PERIODS):
            raise VenueReplayRefused("FUTURES_INSTRUMENT_OR_TIMEFRAME_INVALID")
        start, end = _utc(self.start), _utc(self.end)
        minutes = PERIODS[self.timeframe]
        step = minutes * 60000
        count, remainder = divmod(_ms(end) - _ms(start), step)
        if (_ms(start) % step or _ms(end) % step or remainder
                or not 2 <= count <= 128):
            raise VenueReplayRefused("BOUNDED_ALIGNED_CANDLE_WINDOW_REQUIRED")
        object.__setattr__(self, "start", start)
        object.__setattr__(self, "end", end)

    @property
    def expected_bars(self) -> int:
        return (_ms(self.end) - _ms(self.start)) // (PERIODS[self.timeframe] * 60000)

    @property
    def url(self) -> str:
        # Absolute fixed trusted hostname; symbol cannot inject query parameters.
        query = urllib.parse.urlencode({
            "symbol": self.symbol, "granularity": PERIODS[self.timeframe],
            "from": _ms(self.start), "to": _ms(self.end),
        })
        return BASE_URL + "?" + query


@dataclass(frozen=True)
class FuturesKlineCapture:
    request: FuturesKlineRequest
    observed_at: datetime
    raw_sha256: str
    origin: str
    candles: tuple[ClosedCandle, ...]

    @property
    def source_ref(self) -> str:
        return "kucoin_futures_" + self.raw_sha256[:40]

    def report(self) -> dict:
        return {
            "provider": "kucoin_futures", "symbol": self.request.symbol,
            "timeframe": self.request.timeframe,
            "count": len(self.candles), "raw_sha256": self.raw_sha256,
            "source_ref": self.source_ref, "origin": self.origin,
            "first_open_at": self.candles[0].open_at.isoformat(),
            "last_closed_at": self.candles[-1].close_at.isoformat(),
            "data_origin": "replay", "network_order_calls": False,
            "telegram_sent": False, "broker_order_sent": False,
            "paper_orders_authorized": False, "trading_authorized": False,
            "venue_fill_verified": False, "independent_provenance_verified": False,
        }


def _pairs(values: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in values:
        if key in result:
            raise VenueReplayRefused("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise VenueReplayRefused("INVALID_NONFINITE_NUMBER")


def _decimal(raw: object, *, zero_allowed: bool = False) -> Decimal:
    if type(raw) is bool or type(raw) not in (str, int, Decimal):
        raise VenueReplayRefused("INVALID_OHLC_NUMBER")
    try:
        value = Decimal(str(raw))
    except InvalidOperation as exc:
        raise VenueReplayRefused("INVALID_DECIMAL") from exc
    if not value.is_finite() or value < 0 or (not zero_allowed and value == 0):
        raise VenueReplayRefused("INVALID_NONPOSITIVE_PRICE_OR_VOLUME")
    return value


def parse_futures_klines(raw: bytes, request: FuturesKlineRequest, *,
                         observed_at: datetime,
                         origin: str = "UNVERIFIED_OFFLINE_RESPONSE") -> FuturesKlineCapture:
    """Strict closed-candle parsing, never silently repair missing venue bars."""
    if (type(raw) is not bytes or not 1 <= len(raw) <= MAX_BYTES
            or not isinstance(request, FuturesKlineRequest)):
        raise VenueReplayRefused("BOUNDED_OFFICIAL_FORMAT_RESPONSE_REQUIRED")
    observed = _utc(observed_at)
    if request.end > observed:
        raise VenueReplayRefused("INCOMPLETE_OR_FUTURE_CANDLE_WINDOW")
    try:
        body = json.loads(raw.decode("utf-8"), parse_float=Decimal,
                          parse_constant=_reject_nonfinite, object_pairs_hook=_pairs)
    except (UnicodeError, ValueError, TypeError) as exc:
        raise VenueReplayRefused("INVALID_VENUE_JSON") from exc
    if (type(body) is not dict or body.get("code") != "200000"
            or type(body.get("data")) is not list
            or not 2 <= len(body["data"]) <= 128):
        raise VenueReplayRefused("VENUE_ERROR_OR_TRUNCATED_RESPONSE")
    duration = timedelta(minutes=PERIODS[request.timeframe])
    candles = []
    stamps = set()
    for row in body["data"]:
        if type(row) is not list or len(row) != 7:
            raise VenueReplayRefused("UNEXPECTED_KLINE_SCHEMA")
        timestamp = row[0]
        if type(timestamp) is not int or timestamp in stamps:
            raise VenueReplayRefused("DUPLICATE_OR_INVALID_KLINE_TIME")
        stamps.add(timestamp)
        try:
            open_at = datetime.fromtimestamp(timestamp / 1000, tz=UTC)
            candle = ClosedCandle(
                open_at, open_at + duration, _decimal(row[1]), _decimal(row[2]),
                _decimal(row[3]), _decimal(row[4]),
                _decimal(row[5], zero_allowed=True))
            _decimal(row[6], zero_allowed=True)  # turnover schema check
        except (ValueError, OverflowError, OSError) as exc:
            raise VenueReplayRefused("INVALID_KLINE_GEOMETRY") from exc
        if _ms(candle.open_at) != timestamp:
            raise VenueReplayRefused("UNALIGNED_VENUE_TIMESTAMP")
        candles.append(candle)
    candles.sort(key=lambda candle: candle.open_at)
    if (len(candles) != request.expected_bars
            or candles[0].open_at != request.start
            or candles[-1].close_at != request.end
            or any(a.close_at != b.open_at for a, b in zip(candles, candles[1:]))
            or any(candle.close_at > observed for candle in candles)):
        raise VenueReplayRefused("KLINE_GAP_TRUNCATION_OR_PARTIAL_BAR")
    if type(origin) is not str or origin not in (
            "PUBLIC_HTTPS_UNATTESTED", "INJECTED_TEST_TRANSPORT",
            "UNVERIFIED_OFFLINE_RESPONSE"):
        raise VenueReplayRefused("UNTRUSTED_ORIGIN_LABEL")
    return FuturesKlineCapture(
        request, observed, hashlib.sha256(raw).hexdigest(), origin, tuple(candles))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise VenueReplayRefused("REDIRECT_REFUSED")


def _public_get(url: str) -> bytes:
    # No ambient proxies, redirects, credentials, or non-HTTPS endpoints.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    request = urllib.request.Request(url, method="GET", headers={
        "Accept": "application/json", "User-Agent": "MMT-Stage21-Research/1"})
    with opener.open(request, timeout=7) as response:
        if response.status != 200:
            raise VenueReplayRefused("PUBLIC_HTTP_NOT_SUCCESS")
        data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise VenueReplayRefused("PUBLIC_RESPONSE_TOO_LARGE")
        return data


def observe_public_futures_klines(request: FuturesKlineRequest, *,
                                  observed_at: datetime, operator_ack: bool = False,
                                  transport: Callable[[str], bytes] | None = None
                                  ) -> FuturesKlineCapture:
    """One explicit public GET, no poller. Injected transports never claim network."""
    if (operator_ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or "MMT_PRODUCTION" in os.environ):
        raise VenueReplayRefused("EXPLICIT_NONPRODUCTION_RESEARCH_ACK_REQUIRED")
    if not isinstance(request, FuturesKlineRequest):
        raise VenueReplayRefused("EXPLICIT_FIXED_FUTURES_REQUEST_REQUIRED")
    observed = _utc(observed_at)
    if request.end > observed:
        raise VenueReplayRefused("UNFINISHED_CANDLES_REFUSED_BEFORE_NETWORK")
    if transport is not None and not callable(transport):
        raise VenueReplayRefused("INVALID_TEST_TRANSPORT")
    try:
        raw = (_public_get if transport is None else transport)(request.url)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise VenueReplayRefused("PUBLIC_DATA_UNAVAILABLE") from exc
    return parse_futures_klines(
        raw, request, observed_at=observed,
        origin=("PUBLIC_HTTPS_UNATTESTED" if transport is None
                else "INJECTED_TEST_TRANSPORT"))


def offline_replay_to_core_inputs(
        capture: FuturesKlineCapture, *, manifest: CoreManifest,
        binding: CoreBinding) -> tuple[object, ...]:
    """Offline Stage-5 typed REPLAY CoreInputs only; no strategy execution."""
    if (not isinstance(capture, FuturesKlineCapture)
            or not isinstance(manifest, CoreManifest)
            or not isinstance(binding, CoreBinding)
            or binding.instrument.market is not Market.CRYPTO
            or binding.instrument.provider != "kucoin_futures"
            or binding.instrument.symbol != capture.request.symbol
            or binding.timeframe != capture.request.timeframe):
        raise VenueReplayRefused("BINDING_PROVIDER_SYMBOL_TIMEFRAME_MISMATCH")
    feed_id = "s21_" + capture.raw_sha256[:40]
    engine = OfflineMarketDataEngine(enabled=True)
    engine.register_feed(FeedDefinition(
        feed_id, binding.instrument, binding.timeframe,
        CoreEventType.CLOSED_CANDLE, DataOrigin.REPLAY, capture.source_ref,
        PriceBasis.TRADE, VolumeSemantics.TRADED, max_latency_seconds=120,
        history_limit=128))
    engine.subscribe(feed_id, manifest, binding)
    events = []
    for seq, candle in enumerate(capture.candles, 1):
        # Historical simulated intake time, NEVER claimed to be actual receipt time.
        packet = MarketPacket(feed_id, seq, candle.close_at + timedelta(seconds=1),
                              capture.source_ref, candle=candle)
        outcome = engine.ingest(packet)
        events.extend(delivery.event for delivery in outcome.deliveries)
    return tuple(events)


__all__ = ["FuturesKlineRequest", "FuturesKlineCapture", "VenueReplayRefused",
           "parse_futures_klines", "observe_public_futures_klines",
           "offline_replay_to_core_inputs"]
