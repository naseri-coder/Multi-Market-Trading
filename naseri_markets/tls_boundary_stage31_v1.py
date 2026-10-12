"""Stage31 hermetic TLS-1.3 channel verification and strict ASGI authority gate.

No DNS, socket listeners, certificates, real host provisioning or public API.
TLS proof accepts an actual *client-side* SSLObject after OpenSSL handshake
against the operator's trusted CA and hostname; it is a laboratory result,
NOT proof that a future HTTP reverse proxy terminates real TLS correctly.
Authority checks only validate ASGI host-supplied metadata, not the network.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import ssl
from dataclasses import dataclass

from .offline_developer_api_stage30_v1 import (
    OfflineDeveloperAsgiGateway, Stage30Refused,
)
from .publisher_package_registry_stage28_v1 import _guard

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_HOSTNAME = re.compile(
    r"(?=.{3,253}\Z)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+\Z"
)
_TLS13_CIPHERS = frozenset({
    "TLS_AES_128_GCM_SHA256",
    "TLS_AES_256_GCM_SHA384",
    "TLS_CHACHA20_POLY1305_SHA256",
})


class Stage31Refused(ValueError):
    """Operator-only transport evidence cannot be escalated to authorization."""


@dataclass(frozen=True, slots=True)
class LaboratoryTlsReceipt:
    hostname: str
    tls_version: str
    cipher: str
    certificate_der_sha256: str
    state: str = "IN_MEMORY_CLIENT_TLS13_PEER_VERIFIED"
    lab_certificate_chain_and_hostname_checked: bool = True
    public_https_service_tested: bool = False
    reverse_proxy_trust_independently_verified: bool = False
    external_host_or_kernel_attested: bool = False
    public_api_deployment_authorized: bool = False
    public_plugin_install_authorized: bool = False
    untrusted_core_execution_authorized: bool = False
    broker_order_authorized: bool = False


def verify_hermetic_tls_client(
    channel: ssl.SSLObject, *, trusted_hostname: str,
    expected_certificate_sha256: str, operator_ack: bool = False,
) -> LaboratoryTlsReceipt:
    """Validate an actually completed SSLObject CLIENT-side TLS1.3 handshake.

    The caller must build the context with operator-pinned CA and hostname
    validation. This never accepts user-asserted 'https' ASGI scope fields.
    """
    _guard(operator_ack)
    if (not isinstance(channel, ssl.SSLObject)
            or type(trusted_hostname) is not str
            or not _HOSTNAME.fullmatch(trusted_hostname)
            or type(expected_certificate_sha256) is not str
            or not _SHA.fullmatch(expected_certificate_sha256)):
        raise Stage31Refused("PINNED_CLIENT_TLS_EVIDENCE_REQUIRED")
    context = channel.context
    if (context.protocol != ssl.PROTOCOL_TLS_CLIENT
            or context.verify_mode != ssl.CERT_REQUIRED
            or context.check_hostname is not True
            or context.minimum_version < ssl.TLSVersion.TLSv1_3
            or channel.server_hostname != trusted_hostname):
        raise Stage31Refused("CLIENT_CA_HOSTNAME_TLS13_POLICY_REQUIRED")
    try:
        version = channel.version()
        cipher = channel.cipher()
        peer = channel.getpeercert(binary_form=True)
    except (ValueError, ssl.SSLError) as exc:
        raise Stage31Refused("HANDSHAKE_AND_CERTIFICATE_REQUIRED") from exc
    if (version != "TLSv1.3" or not cipher
            or cipher[0] not in _TLS13_CIPHERS
            or type(peer) is not bytes or not peer
            or not hmac.compare_digest(
                hashlib.sha256(peer).hexdigest(),
                expected_certificate_sha256)):
        raise Stage31Refused("NEGOTIATED_TLS_OR_CERTIFICATE_PIN_MISMATCH")
    return LaboratoryTlsReceipt(
        hostname=trusted_hostname, tls_version=version, cipher=cipher[0],
        certificate_der_sha256=hashlib.sha256(peer).hexdigest())


class StrictDeveloperAuthorityGate:
    """Offline opt-in ASGI authority/URI guard around the Stage30 application.

    A genuine network server must separately establish a TLS connection,
    authenticate its proxy peer and derive the ASGI metadata. This adapter
    DOES NOT infer TLS from HTTPS scope or from a developer-supplied header.
    """

    def __init__(self, delegate: OfflineDeveloperAsgiGateway, *,
                 approved_authority: str, operator_ack: bool = False):
        _guard(operator_ack)
        if (type(delegate) is not OfflineDeveloperAsgiGateway
                or type(approved_authority) is not str
                or not _HOSTNAME.fullmatch(approved_authority)):
            raise Stage31Refused("OPERATOR_PINNED_AUTHORITY_REQUIRED")
        self.delegate = delegate
        self.authority = approved_authority

    def _checked_scope(self, scope: dict) -> dict:
        if (type(scope) is not dict or scope.get("type") != "http"
                or scope.get("scheme") != "https"
                or scope.get("http_version") not in ("1.1", "2")
                or scope.get("root_path", "") != ""
                or type(scope.get("path")) is not str
                or not scope["path"].isascii()
                or "%" in scope["path"] or "\\" in scope["path"]
                or "//" in scope["path"] or "/./" in scope["path"]
                or "/../" in scope["path"]
                or scope.get("query_string", b"") != b""):
            raise Stage30Refused(403, "TRUSTED_EXACT_TLS_EDGE_SCOPE_REQUIRED")
        raw_path = scope.get("raw_path")
        if (raw_path is not None
                and (type(raw_path) is not bytes
                     or raw_path != scope["path"].encode("ascii"))):
            raise Stage30Refused(400, "RAW_PATH_NORMALIZATION_FORBIDDEN")
        server = scope.get("server")
        if (not isinstance(server, (tuple, list)) or len(server) != 2
                or server[0] != self.authority or server[1] != 443):
            raise Stage30Refused(403, "WRONG_REVIEWED_TLS_AUTHORITY")
        headers = scope.get("headers")
        if type(headers) is not list or not 1 <= len(headers) <= 9:
            raise Stage30Refused(400, "EXACT_HOST_HEADER_REQUIRED")
        found = 0
        passed = []
        for header in headers:
            if (not isinstance(header, (tuple, list)) or len(header) != 2
                    or type(header[0]) is not bytes
                    or type(header[1]) is not bytes):
                raise Stage30Refused(400, "MALFORMED_AUTHORITY_HEADER")
            name, value = header
            if name.lower() == b"host":
                found += 1
                if (name != b"host" or
                        value != self.authority.encode("ascii")):
                    raise Stage30Refused(400, "HOST_AUTHORITY_MISMATCH")
            else:
                passed.append((name, value))
        if found != 1:
            raise Stage30Refused(400, "DUPLICATE_OR_ABSENT_HOST")
        # Host is validated and removed because Stage30 deliberately rejects
        # every inbound header except its four protocol-necessary fields.
        return {**scope, "headers": passed}

    async def __call__(self, scope, receive, send):
        try:
            _guard(True)
            normalized = self._checked_scope(scope)
        except Stage30Refused as exc:
            await self.delegate._send(send, exc.status, {"error": exc.code})
            return
        except ValueError:
            await self.delegate._send(
                send, 403, {"error": "NONPRODUCTION_TLS_EDGE_REQUIRED"})
            return
        await self.delegate(normalized, receive, send)


__all__ = [
    "Stage31Refused", "LaboratoryTlsReceipt",
    "verify_hermetic_tls_client", "StrictDeveloperAuthorityGate",
]
