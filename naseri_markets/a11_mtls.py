"""A11 mTLS localhost-only transport for Multi Market Trading.

This is a real encrypted two-process rehearsal, not a production remote
connector. It cannot contact non-loopback hosts and has no retry on
ambiguous failures. Certificate files are supplied by the CI operator.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import re
import ssl
import struct
import time
from dataclasses import dataclass
from pathlib import Path

from .private_protocol import MAX_PACKET

MAX_FRAME = MAX_PACKET


class TransportRefused(RuntimeError):
    """Local transport rejected connection, certificate or frame."""


def _file(value: str | Path) -> str:
    path = Path(value)
    if path.is_symlink() or not path.is_file():
        raise TransportRefused("A11_CERTIFICATE_FILE_REQUIRED")
    return str(path)


def make_client_context(*, ca: str | Path, cert: str | Path,
                        key: str | Path) -> ssl.SSLContext:
    """Mutual TLS, server CA and hostname verification always enabled."""
    context = ssl.create_default_context(
        ssl.Purpose.SERVER_AUTH, cafile=_file(ca),
    )
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = True
    context.load_cert_chain(_file(cert), _file(key))
    return context


def make_fixture_server_context(*, ca: str | Path, cert: str | Path,
                                key: str | Path) -> ssl.SSLContext:
    """Server-side certificate chain and mandatory client certificate."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(_file(cert), _file(key))
    context.load_verify_locations(cafile=_file(ca))
    context.verify_mode = ssl.CERT_REQUIRED
    return context


async def read_frame(reader: asyncio.StreamReader) -> bytes:
    """Exactly one length-delimited, bounded frame per connection."""
    size = struct.unpack("!I", await reader.readexactly(4))[0]
    if not 0 < size <= MAX_FRAME:
        raise TransportRefused("A11_FRAME_SIZE")
    return await reader.readexactly(size)


async def send_frame(writer: asyncio.StreamWriter, content: bytes) -> None:
    if type(content) is not bytes or not 0 < len(content) <= MAX_FRAME:
        raise TransportRefused("A11_FRAME_SIZE")
    writer.write(struct.pack("!I", len(content)) + content)
    await writer.drain()


@dataclass(frozen=True, slots=True)
class TransportHealth:
    mode: str
    state: str
    consecutive_failures: int
    live_engine_authorized: bool = False
    owner_identity_production_verified: bool = False


class LoopbackMtlsExchange:
    """One-shot secure local exchange with fail-closed circuit breaker.

    Serializes requests intentionally: no parallel ambiguity in the
    rehearsal; a retry after unknown delivery MUST NOT happen automatically.
    """

    def __init__(
        self, *, port: int, expected_owner_dns: str,
        context: ssl.SSLContext, timeout: float = 2.0,
        failure_limit: int = 2, cooldown: float = 1.0,
        expected_owner_cert_sha256: str | None = None,
    ) -> None:
        if type(port) is not int or not 0 < port <= 65535:
            raise TransportRefused("A11_PORT_REQUIRED")
        if (
            type(expected_owner_dns) is not str
            or not expected_owner_dns.endswith(".fixture")
            or len(expected_owner_dns) > 120
            or not expected_owner_dns.replace(".", "").replace("-", "").isalnum()
        ):
            raise TransportRefused("A11_FIXTURE_DNS_REQUIRED")
        if (
            not isinstance(context, ssl.SSLContext)
            or not context.check_hostname
            or context.verify_mode != ssl.CERT_REQUIRED
        ):
            raise TransportRefused("A11_VERIFIED_TLS_CONTEXT_REQUIRED")
        if not 0 < timeout <= 10 or not 1 <= failure_limit <= 10:
            raise TransportRefused("A11_INVALID_TRANSPORT_POLICY")
        if not 0 < cooldown <= 60:
            raise TransportRefused("A11_INVALID_COOLDOWN")
        if expected_owner_cert_sha256 is not None and (
            type(expected_owner_cert_sha256) is not str
            or re.fullmatch(r"[0-9a-f]{64}", expected_owner_cert_sha256) is None
        ):
            raise TransportRefused("A12_INVALID_OWNER_CERT_PIN")
        self._cert_pin = expected_owner_cert_sha256
        self._port = port
        self._expected_owner_dns = expected_owner_dns
        self._context = context
        self._timeout = timeout
        self._failure_limit = failure_limit
        self._cooldown = cooldown
        self._failures = 0
        self._blocked_until = 0.0
        self._lock = asyncio.Lock()

    @property
    def health(self) -> TransportHealth:
        state = (
            "OPEN" if self._failures >= self._failure_limit
            and time.monotonic() < self._blocked_until
            else "DEGRADED" if self._failures else "READY_FOR_OFFLINE_TEST"
        )
        return TransportHealth("LOOPBACK_MTLS_FIXTURE_ONLY", state, self._failures)

    async def __call__(self, packet: bytes) -> bytes:
        if type(packet) is not bytes or not 0 < len(packet) <= MAX_FRAME:
            raise TransportRefused("A11_FRAME_SIZE")
        async with self._lock:
            if (self._failures >= self._failure_limit
                    and time.monotonic() < self._blocked_until):
                raise TransportRefused("A11_CIRCUIT_OPEN")
            try:
                # Only fixed loopback; never resolves arbitrary DNS or URLs.
                answer = await asyncio.wait_for(
                    self._exchange_once(packet), timeout=self._timeout,
                )
            except asyncio.CancelledError:
                raise
            except (OSError, ssl.SSLError, asyncio.TimeoutError,
                    asyncio.IncompleteReadError, TransportRefused) as exc:
                self._failures += 1
                if self._failures >= self._failure_limit:
                    self._blocked_until = time.monotonic() + self._cooldown
                raise TransportRefused("A11_EXCHANGE_UNAVAILABLE") from exc
            self._failures = 0
            self._blocked_until = 0.0
            return answer

    async def _exchange_once(self, packet: bytes) -> bytes:
        reader, writer = await asyncio.open_connection(
            host="127.0.0.1", port=self._port, ssl=self._context,
            server_hostname=self._expected_owner_dns,
        )
        try:
            if self._cert_pin is not None:
                tls = writer.get_extra_info("ssl_object")
                leaf = tls.getpeercert(binary_form=True) if tls else None
                if not leaf or not hmac.compare_digest(
                    hashlib.sha256(leaf).hexdigest(), self._cert_pin
                ):
                    raise TransportRefused("A12_UNTRUSTED_OWNER_CERT")
            await send_frame(writer, packet)
            answer = await read_frame(reader)
            # One-message response and no hidden auto-retry.
            return answer
        finally:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), timeout=0.3)
            except (asyncio.TimeoutError, OSError, ssl.SSLError):
                pass
