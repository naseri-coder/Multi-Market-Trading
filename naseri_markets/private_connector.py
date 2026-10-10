"""A10 owner-controlled PRIVATE engine connection seam: OFFLINE transport only.

This module has NO HTTP client, socket, filesystem plugin loader, TLS client,
broker, Telegram sender, or private strategy implementation. The injected
exchange callback is a deterministic fixture in CI. A *real* transport would
need independently reviewed mTLS, endpoint identity and key custody.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from .external_abi import parse_paper_envelope
from .plugin_manager import PluginManager
from .private_protocol import (
    ProtocolRefused, ReplayFence, sign_packet, verify_packet,
)
from .quotes import QuoteOrigin, QuoteTick

Exchange = Callable[[bytes], Awaitable[bytes]]


@dataclass(frozen=True, slots=True)
class ConnectorKeys:
    client_key_id: str
    client_key: bytes
    owner_key_id: str
    owner_key: bytes

    def __post_init__(self) -> None:
        if (
            self.client_key_id == self.owner_key_id
            or type(self.client_key) is not bytes
            or type(self.owner_key) is not bytes
            or len(self.client_key) < 32 or len(self.owner_key) < 32
            or self.client_key == self.owner_key
        ):
            raise ProtocolRefused("A10_SEPARATE_DIRECTIONAL_KEYS_REQUIRED")


@dataclass(frozen=True, slots=True)
class ConnectorStatus:
    mode: str = "OFFLINE_INJECTED_TRANSPORT_ONLY"
    real_owner_authenticated: bool = False
    real_network_connected: bool = False
    license_authority_verified: bool = False
    live_feed_approved: bool = False
    telegram_allowed: bool = False
    trading_allowed: bool = False


def _request_tick(tick: QuoteTick) -> dict:
    return {
        "market": tick.instrument.market.value,
        "provider": tick.instrument.provider,
        "symbol": tick.instrument.symbol,
        "timezone": tick.instrument.timezone,
        "quote_currency": tick.instrument.quote_currency,
        "bid": str(tick.bid),
        "ask": str(tick.ask),
        "origin": tick.origin.value,
        "occurred_at": tick.occurred_at.isoformat(),
    }


class PrivatePaperConnector:
    """Owner-provided transport + independently provisioned directional keys.

    Every request is restricted to PAPER replay/synthetic origin and to one
    exact installed plugin incarnation. Verification is strictly fail-closed.
    Implements the A7 EnvelopeProvider protocol so ExternalPaperEngine can
    convert the verified envelope to a typed PAPER SignalIntent.
    """

    def __init__(
        self, *, manager: PluginManager, fence: ReplayFence,
        engine_id: str, engine_version: str, approved_digest: str,
        keys: ConnectorKeys, exchange: Exchange, timeout_seconds: float = 1.0,
        now_seconds: Callable[[], int] | None = None,
    ) -> None:
        if (
            not callable(exchange) or not 0 < timeout_seconds <= 10
            or type(approved_digest) is not str or len(approved_digest) != 64
        ):
            raise ProtocolRefused("A10_CONNECTOR_CONTRACT_INVALID")
        self._manager = manager
        self._fence = fence
        self._engine_id = engine_id
        self._engine_version = engine_version
        self._digest = approved_digest
        self._keys = keys
        self._exchange = exchange
        self._timeout = timeout_seconds
        self._clock = now_seconds or (lambda: int(time.time()))
        self._incarnation = manager.incarnation(engine_id)
        # Fail closed upon construction if plugin is not explicitly prepared.
        self._require_registered()

    def _require_registered(self):
        plugin = self._manager.get(self._engine_id)
        if (
            plugin is None or plugin.visibility != "private"
            or plugin.adapter != "external_contract"
            or plugin.engine_version != self._engine_version
            or plugin.digest != self._digest
            or self._manager.incarnation(self._engine_id) != self._incarnation
            or not plugin.enabled
        ):
            raise ProtocolRefused("A10_PLUGIN_DISABLED_UNPROVISIONED_OR_CHANGED")
        self._fence.require_active(self._keys.client_key_id)
        self._fence.require_active(self._keys.owner_key_id)
        return plugin

    @property
    def status(self) -> ConnectorStatus:
        return ConnectorStatus()

    async def produce(self, tick: QuoteTick) -> bytes:
        if tick.origin not in (QuoteOrigin.REPLAY, QuoteOrigin.SYNTHETIC):
            raise ProtocolRefused("A10_LIVE_DATA_FORBIDDEN")
        old = self._require_registered()
        now = self._clock()
        if type(now) is not int or now <= 0:
            raise ProtocolRefused("A10_INVALID_CLOCK")
        nonce = secrets.token_hex(16)
        request = {
            "version": 1,
            "key_id": self._keys.client_key_id,
            "direction": "to_owner",
            "engine_id": self._engine_id,
            "engine_version": self._engine_version,
            "nonce": nonce,
            "request_nonce": "",
            "issued_at": now,
            "expires_at": now + 20,
            "payload": {"operation": "paper_analysis", "tick": _request_tick(tick)},
        }
        wire_request = sign_packet(request, key=self._keys.client_key)
        try:
            wire_response = await asyncio.wait_for(
                self._exchange(wire_request), timeout=self._timeout,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise ProtocolRefused("A10_TRANSPORT_UNAVAILABLE") from exc
        body = verify_packet(
            wire_response, key=self._keys.owner_key,
            key_id=self._keys.owner_key_id, direction="to_bot",
            engine_id=self._engine_id, engine_version=self._engine_version,
            now=self._clock(),
        )
        if body["request_nonce"] != nonce:
            raise ProtocolRefused("A10_CHALLENGE_MISMATCH")
        payload = body["payload"]
        if (
            set(payload) != {"operation", "paper_envelope_b64"}
            or payload["operation"] != "paper_analysis"
            or type(payload["paper_envelope_b64"]) is not str
            or len(payload["paper_envelope_b64"]) > 11000
        ):
            raise ProtocolRefused("A10_RESPONSE_PAYLOAD_INVALID")
        try:
            output = base64.b64decode(
                payload["paper_envelope_b64"], validate=True,
            )
        except (binascii.Error, ValueError) as exc:
            raise ProtocolRefused("A10_RESPONSE_BASE64_INVALID") from exc
        # Perform A7 instrument identity, observed-time, risk and PAPER
        # validation BEFORE a signed packet can be accepted.
        parse_paper_envelope(
            output, tick, engine_id=self._engine_id,
            engine_version=self._engine_version,
        )
        if self._require_registered() != old:
            raise ProtocolRefused("A10_SETTINGS_CHANGED_DURING_EXCHANGE")
        self._fence.consume(
            direction="to_bot", key_id=self._keys.owner_key_id,
            nonce=body["nonce"],
        )
        self._require_registered()
        return output
