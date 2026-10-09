"""Pure quote normalizers for Binance USD-M bookTicker and MetaTrader 5 ticks.

These are parsing adapters, NOT live authenticated network clients. They cannot
claim provider verification. Caller explicitly supplies provenance.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from .contracts import Instrument, Market
from .quotes import QuoteOrigin, QuoteTick


def _money(value: Any) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, Decimal)):
        raise ValueError("price must be a decimal string or integer")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid price") from exc
    if not result.is_finite() or result <= 0:
        raise ValueError("invalid price")
    return result


def _timestamp_ms(value: Any) -> datetime:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("positive integer UTC epoch milliseconds required")
    try:
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as exc:
        raise ValueError("invalid event timestamp") from exc


def normalize_binance_usdm_book_ticker(
    payload: Mapping[str, Any], instrument: Instrument,
    *, origin: QuoteOrigin = QuoteOrigin.REPLAY,
) -> QuoteTick:
    """Requires WebSocket-style E event-time; never fabricates an absent time."""
    if instrument.market is not Market.CRYPTO:
        raise ValueError("Binance USD-M adapter supports crypto only")
    if instrument.provider != "binance-usdm":
        raise ValueError("provider identity mismatch")
    if payload.get("s") != instrument.symbol:
        raise ValueError("symbol mismatch")
    try:
        return QuoteTick(
            instrument=instrument,
            occurred_at=_timestamp_ms(payload["E"]),
            bid=_money(payload["b"]),
            ask=_money(payload["a"]),
            origin=origin,
        )
    except (KeyError, TypeError) as exc:
        raise ValueError("incomplete bookTicker payload") from exc


def normalize_mt5_symbol_tick(
    tick: Mapping[str, Any], instrument: Instrument,
    *, origin: QuoteOrigin = QuoteOrigin.REPLAY,
) -> QuoteTick:
    """Read-only MT5 symbol_info_tick-like mapping; expects time_msc in UTC."""
    if not instrument.provider.startswith("mt5:"):
        raise ValueError("provider identity mismatch")
    if tick.get("symbol") != instrument.symbol:
        raise ValueError("symbol mismatch")
    try:
        return QuoteTick(
            instrument=instrument,
            occurred_at=_timestamp_ms(tick["time_msc"]),
            bid=_money(tick["bid"]),
            ask=_money(tick["ask"]),
            origin=origin,
        )
    except (KeyError, TypeError) as exc:
        raise ValueError("incomplete MT5 tick payload") from exc
