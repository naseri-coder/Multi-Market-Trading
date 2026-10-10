"""A7 exact, data-only PAPER ABI for an injected external engine.

No private source import, dynamic plugin loading, network or entitlement claim.
"""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Protocol

from .contracts import Direction, EvidenceMode, SignalIntent
from .quotes import QuoteOrigin, QuoteTick, _utc

ABI_VERSION = 1
_FIELDS = frozenset((
    "abi_version", "signal_id", "engine_id", "engine_version", "market",
    "provider", "symbol", "timezone", "quote_currency", "direction",
    "observed_at", "entry", "stop", "targets", "evidence_mode",
))


def _unique(pairs):
    data = {}
    for key, value in pairs:
        if key in data:
            raise ValueError("A7_DUPLICATE_KEY")
        data[key] = value
    return data


def _decimal(raw):
    if type(raw) is not str or len(raw) > 64:
        raise ValueError("A7_DECIMAL_STRING_REQUIRED")
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ValueError("A7_BAD_PRICE") from exc
    if not value.is_finite() or value <= 0:
        raise ValueError("A7_BAD_PRICE")
    return value


def parse_paper_envelope(blob: bytes, tick: QuoteTick, *,
                         engine_id: str, engine_version: str) -> SignalIntent:
    if tick.origin not in (QuoteOrigin.REPLAY, QuoteOrigin.SYNTHETIC):
        raise ValueError("A7_LIVE_REFUSED")
    if type(blob) is not bytes or not 0 < len(blob) <= 8192:
        raise ValueError("A7_PACKET_SIZE")
    try:
        data = json.loads(blob.decode("utf-8"), object_pairs_hook=_unique)
    except (UnicodeError, ValueError) as exc:
        raise ValueError("A7_INVALID_JSON") from exc
    if not isinstance(data, dict) or set(data) != _FIELDS:
        raise ValueError("A7_SCHEMA")
    if type(data["abi_version"]) is not int or data["abi_version"] != ABI_VERSION:
        raise ValueError("A7_ABI_VERSION")
    i = tick.instrument
    expected = (
        ("engine_id", engine_id), ("engine_version", engine_version),
        ("market", i.market.value), ("provider", i.provider),
        ("symbol", i.symbol), ("timezone", i.timezone),
        ("quote_currency", i.quote_currency), ("evidence_mode", "paper"),
    )
    if any(type(data[key]) is not str or data[key] != val for key, val in expected):
        raise ValueError("A7_IDENTITY_OR_EVIDENCE")
    if type(data["signal_id"]) is not str or not 0 < len(data["signal_id"]) <= 120:
        raise ValueError("A7_SIGNAL_ID")
    if type(data["observed_at"]) is not str or len(data["observed_at"]) > 48:
        raise ValueError("A7_TIMESTAMP")
    try:
        when = _utc(datetime.fromisoformat(data["observed_at"]))
    except ValueError as exc:
        raise ValueError("A7_TIMESTAMP") from exc
    if when != tick.occurred_at:
        raise ValueError("A7_NONCAUSAL")
    targets = data["targets"]
    if not isinstance(targets, list) or not 1 <= len(targets) <= 5:
        raise ValueError("A7_TARGETS")
    try:
        side = Direction(data["direction"])
    except (ValueError, TypeError) as exc:
        raise ValueError("A7_DIRECTION") from exc
    return SignalIntent(
        data["signal_id"], engine_id, engine_version, i, side, when,
        _decimal(data["entry"]), _decimal(data["stop"]),
        tuple(_decimal(x) for x in targets), EvidenceMode.PAPER,
    )


class EnvelopeProvider(Protocol):
    async def produce(self, tick: QuoteTick) -> bytes | None: ...


class ExternalPaperEngine:
    """Operator-injected callback adapter; not a sandbox or license verifier."""

    def __init__(self, engine_id: str, engine_version: str,
                 provider: EnvelopeProvider) -> None:
        if not engine_id or not engine_version or not callable(
            getattr(provider, "produce", None)
        ):
            raise ValueError("A7_INVALID_BINDING")
        self.engine_id = engine_id
        self.engine_version = engine_version
        self._provider = provider

    async def on_quote(self, tick: QuoteTick) -> tuple[SignalIntent, ...]:
        packet = await self._provider.produce(tick)
        return () if packet is None else (
            parse_paper_envelope(
                packet, tick, engine_id=self.engine_id,
                engine_version=self.engine_version,
            ),
        )
