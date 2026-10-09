"""Open, strategy-neutral signal bot. NO proprietary strategy or broker orders.

Importing this module does not start a bot or perform network I/O.
The private engine, if authorized by its owner, supplies a SignalIntent only.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from .contracts import SignalIntent
from .delivery_ledger import SignalLedger, UnsafeDelivery
from .quotes import _utc
from .registry import EngineRegistry
from .routing import ChannelRoute, decide_delivery


class PrivateChannelTransport(Protocol):
    def verify_private_channel(self, channel_id: int) -> bool: ...
    def send_message(self, channel_id: int, body: str) -> int: ...


@dataclass(frozen=True)
class PublicationResult:
    status: str
    signal_id: str
    message_id: int | None = None


def format_signal(intent: SignalIntent) -> str:
    """Render only generic fields. No engine decision trace or secret features."""
    timestamp = _utc(intent.observed_at).isoformat(timespec="seconds")
    targets = ", ".join(str(target) for target in intent.targets)
    return (
        f"PAPER SIGNAL — {intent.instrument.symbol}\n"
        f"Engine: {intent.engine_id} / {intent.engine_version}\n"
        f"Market: {intent.instrument.market.value} | {intent.instrument.provider}\n"
        f"ID: {intent.signal_id}\n"
        f"Side: {intent.direction.value.upper()}\n"
        f"Observed entry: {intent.entry} | Stop: {intent.stop}\n"
        f"Target(s): {targets}\n"
        f"UTC: {timestamp}\n"
        "Quote observation only; NOT a broker fill or investment guarantee."
    )


class TelegramPrivateChannel:
    """Public Telegram Bot API client with independently verified channel privacy.

    Token is injected and never stored to disk or returned to callers. Remote
    error messages are REDACTED because request URLs contain the token.
    """

    def __init__(self, token: str, *, timeout_seconds: float = 8.0) -> None:
        if not isinstance(token, str) or not token.strip():
            raise ValueError("bot token required")
        if not 0 < timeout_seconds <= 30:
            raise ValueError("invalid timeout")
        self._token = token
        self._timeout = timeout_seconds

    def _api(self, method: str, data: dict[str, str]) -> dict:
        if method not in ("getMe", "getChat", "getChatMember", "sendMessage"):
            raise ValueError("unsupported Telegram method")
        url = f"https://api.telegram.org/bot{self._token}/{method}"
        req = urllib.request.Request(
            url, data=urllib.parse.urlencode(data).encode(), method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as response:
                result = json.loads(response.read(64000))
        except (OSError, ValueError, urllib.error.URLError):
            raise RuntimeError("TELEGRAM_NETWORK_OR_RESPONSE_ERROR") from None
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise RuntimeError("TELEGRAM_REJECTED_OR_UNVERIFIED")
        payload = result.get("result")
        if not isinstance(payload, dict):
            raise RuntimeError("TELEGRAM_RESPONSE_INVALID")
        return payload

    def verify_private_channel(self, channel_id: int) -> bool:
        if isinstance(channel_id, bool) or not isinstance(channel_id, int) or channel_id >= 0:
            return False
        account = self._api("getMe", {})
        if isinstance(account.get("id"), bool) or not isinstance(account.get("id"), int):
            return False
        channel = self._api("getChat", {"chat_id": str(channel_id)})
        if channel.get("type") != "channel" or channel.get("username"):
            return False
        member = self._api(
            "getChatMember",
            {"chat_id": str(channel_id), "user_id": str(account["id"])},
        )
        return member.get("status") == "creator" or (
            member.get("status") == "administrator"
            and member.get("can_post_messages") is True
        )

    def send_message(self, channel_id: int, body: str) -> int:
        if not isinstance(body, str) or not body.strip():
            raise ValueError("message text required")
        result = self._api(
            "sendMessage",
            {"chat_id": str(channel_id), "text": body,
             "disable_web_page_preview": "true"},
        )
        ident = result.get("message_id")
        if isinstance(ident, bool) or not isinstance(ident, int) or ident <= 0:
            raise RuntimeError("TELEGRAM_DELIVERY_RECEIPT_INVALID")
        return ident


class PublicSignalBot:
    """Strategy-neutral delivery; disabled by default and never places an order.

    A verified live-feed attestation must be supplied by an independent
    authenticated provider; this bot does not have any broker credentials.
    """

    def __init__(self, ledger: SignalLedger, registry: EngineRegistry,
                 transport: PrivateChannelTransport, *, enabled: bool = False,
                 max_signal_age_seconds: int = 30) -> None:
        if not 1 <= max_signal_age_seconds <= 120:
            raise ValueError("invalid max signal age")
        self._ledger = ledger
        self._registry = registry
        self._transport = transport
        self._enabled = enabled
        self._max_age = max_signal_age_seconds
        self._ledger.quarantine_inflight()

    def publish(self, intent: SignalIntent, route: ChannelRoute, *, now: datetime,
                verified_live_feed: bool = False) -> PublicationResult:
        current = _utc(now)
        age = (current - _utc(intent.observed_at)).total_seconds()
        if not self._enabled:
            return PublicationResult("BOT_DISABLED", intent.signal_id)
        if age < 0 or age > self._max_age:
            return PublicationResult("SIGNAL_STALE_OR_FUTURE", intent.signal_id)
        if not verified_live_feed or not route.realtime_feed_verified:
            return PublicationResult("FEED_NOT_VERIFIED", intent.signal_id)
        decision = decide_delivery(intent, self._registry, route)
        if not decision.allowed or decision.channel_id is None:
            return PublicationResult(decision.reason, intent.signal_id)
        try:
            verified = self._transport.verify_private_channel(decision.channel_id)
        except Exception:
            return PublicationResult("CHANNEL_PREFLIGHT_FAILED", intent.signal_id)
        if not verified:
            return PublicationResult("CHANNEL_NOT_PRIVATE_OR_NOT_ADMIN", intent.signal_id)
        try:
            self._ledger.record(intent, self._registry, route)
            item = self._ledger.claim(
                intent.engine_id, intent.signal_id, route=route,
                now=current, max_age_seconds=self._max_age,
            )
        except UnsafeDelivery:
            return PublicationResult("DELIVERY_DISALLOWED", intent.signal_id)
        if item is None:
            state = self._ledger.get(intent.engine_id, intent.signal_id)
            if state and state.state in ("CLAIMED", "UNKNOWN"):
                return PublicationResult("DELIVERY_UNKNOWN_MANUAL_REVIEW", intent.signal_id)
            return PublicationResult(
                "ALREADY_HANDLED" if state and state.state != "EXPIRED" else "EXPIRED",
                intent.signal_id, state.message_id if state else None,
            )
        # Sending is one attempt only; unknown network result is NOT retried.
        try:
            ident = self._transport.send_message(item.channel_id, format_signal(intent))
            if isinstance(ident, bool) or not isinstance(ident, int) or ident <= 0:
                raise ValueError("invalid Telegram receipt")
        except Exception:
            return PublicationResult("DELIVERY_UNKNOWN_MANUAL_REVIEW", intent.signal_id)
        if not self._ledger.acknowledge_sent(
            intent.engine_id, intent.signal_id, message_id=ident
        ):
            return PublicationResult("ACK_PERSISTENCE_FAILED_MANUAL_REVIEW", intent.signal_id)
        return PublicationResult("SENT", intent.signal_id, ident)
