"""Stage30 offline-only, fail-closed ASGI HTTP *contract*, not a server.

No socket binding, listener, reverse proxy, web UI, remote identity service or
plugin execution. A separately authorized, secure host is needed before this
application can be deployed. HTTPS ASGI scheme / client address are assertions
FROM A TRUSTED SERVER; they do not establish TLS security by themselves.

Only one authenticated one-use ZIP submission via Stage29/28/27 is permitted.
No public core installation, Telegram send or brokerage actions exist here.
"""
from __future__ import annotations

import base64
import binascii
import ipaddress
import json
import sqlite3
from dataclasses import dataclass

from .a24_publisher_admission import canonical
from .authenticated_developer_intake_stage29_v1 import (
    AuthenticatedDeveloperIntake, Stage29Refused,
)
from .core_api_v1 import CoreBinding, CoreManifest
from .publisher_package_registry_stage28_v1 import Stage28Refused
from .signed_core_candidate_stage23_v1 import SignedCandidateWitness

_MAX_BODY = 132000
_MAX_CHUNKS = 32
_MAX_HEADER_COUNT = 8
_ALLOWED_HEADERS = frozenset({
    "authorization", "content-type", "content-length", "accept",
})
_CONTENT_TYPE = "application/json"
_ENDPOINTS = {
    "/v1/developers/challenge": "challenge",
    "/v1/developers/session": "session",
    "/v1/developers/quarantine": "quarantine",
    "/v1/developers/logout": "logout",
    "/v1/developers/me": "me",
}


class Stage30Refused(ValueError):
    """No credentials, signed claims, client IPs or source echoed in errors."""

    def __init__(self, status: int, code: str):
        super().__init__(code)
        self.status = status
        self.code = code


@dataclass(frozen=True, slots=True)
class ReviewedUploadTarget:
    """Trusted-operator allowlist; never deserialized from an HTTP payload."""

    manifest: CoreManifest
    binding: CoreBinding
    signed_witness: SignedCandidateWitness
    pinned_image: str


class OfflineDeveloperAsgiGateway:
    """In-process ASGI application. Construction has NO network side effects.

    Challenges are available only to Stage28 ACTIVE previously enrolled keys.
    The scoped one-time bearer is verified by Stage29. Client address must be
    supplied by a trusted ASGI server, not X-Forwarded-For request headers.
    """

    def __init__(self, intake: AuthenticatedDeveloperIntake, *,
                 reviewed_targets: dict[str, ReviewedUploadTarget],
                 operator_ack: bool = False):
        if operator_ack is not True:
            raise Stage30Refused(403, "OPERATOR_REVIEW_REQUIRED")
        if type(intake) is not AuthenticatedDeveloperIntake:
            raise Stage30Refused(403, "EXACT_NONPRODUCTION_INTAKE_REQUIRED")
        # Stage29 gate checks MMT_NONPRODUCTION and refuses MMT_PRODUCTION.
        from .publisher_package_registry_stage28_v1 import _guard
        _guard(True)
        if (type(reviewed_targets) is not dict or len(reviewed_targets) > 32
                or any(type(k) is not str or not 1 <= len(k) <= 128
                       or type(v) is not ReviewedUploadTarget
                       or type(v.manifest) is not CoreManifest
                       or type(v.binding) is not CoreBinding
                       or type(v.signed_witness) is not SignedCandidateWitness
                       or v.binding.binding_id != k
                       or type(v.pinned_image) is not str
                       or v.pinned_image != intake.registry.stage22.host.policy.image
                       for k, v in reviewed_targets.items())):
            raise Stage30Refused(403, "TRUSTED_UPLOAD_ALLOWLIST_REQUIRED")
        self.intake = intake
        self.targets = dict(reviewed_targets)
        self.db = intake.registry.stage22.db
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS secure30_client_rates (
              client_ip TEXT NOT NULL, minute INTEGER NOT NULL,
              attempts INTEGER NOT NULL CHECK(attempts>=1),
              PRIMARY KEY(client_ip,minute)
            );
        """)

    def _rate(self, client_ip: str) -> None:
        """Durable per-SERVER-peer-IP budget; no attacker-supplied XFF."""
        now = self.intake._now()
        minute = now // 60
        with self.intake.registry.stage22._tx():
            self.db.execute(
                "DELETE FROM secure30_client_rates WHERE minute<?",
                (minute - 3,))
            current = self.db.execute(
                "SELECT attempts FROM secure30_client_rates "
                "WHERE client_ip=? AND minute=?",
                (client_ip, minute)).fetchone()
            if current is not None and current[0] >= 12:
                raise Stage30Refused(429, "REQUEST_RATE_LIMITED")
            if current is None:
                if self.db.execute(
                        "SELECT COUNT(*) FROM secure30_client_rates "
                        "WHERE minute=?", (minute,)).fetchone()[0] >= 256:
                    raise Stage30Refused(429, "GLOBAL_CLIENT_RATE_LIMIT")
                self.db.execute(
                    "INSERT INTO secure30_client_rates VALUES(?,?,1)",
                    (client_ip, minute))
            else:
                self.db.execute(
                    "UPDATE secure30_client_rates "
                    "SET attempts=attempts+1 WHERE client_ip=? AND minute=?",
                    (client_ip, minute))

    @staticmethod
    def _headers(raw) -> dict[str, str]:
        if type(raw) is not list or len(raw) > _MAX_HEADER_COUNT:
            raise Stage30Refused(400, "INVALID_HEADERS")
        result = {}
        for pair in raw:
            if (not isinstance(pair, (tuple, list)) or len(pair) != 2
                    or type(pair[0]) is not bytes or type(pair[1]) is not bytes):
                raise Stage30Refused(400, "INVALID_HEADERS")
            try:
                name = pair[0].decode("ascii").lower()
                val = pair[1].decode("ascii")
            except UnicodeError as exc:
                raise Stage30Refused(400, "INVALID_HEADERS") from exc
            if (name not in _ALLOWED_HEADERS or name in result
                    or len(val) > 128 or any(ord(ch) < 32 or ord(ch) > 126
                                             for ch in val)
                    or "\r" in val or "\n" in val):
                raise Stage30Refused(400, "UNTRUSTED_OR_DUPLICATE_HEADER")
            result[name] = val
        if "content-type" in result and result["content-type"] != _CONTENT_TYPE:
            raise Stage30Refused(415, "JSON_CONTENT_TYPE_REQUIRED")
        return result

    @staticmethod
    def _object(pairs):
        parsed = {}
        for key, value in pairs:
            if key in parsed:
                raise Stage30Refused(400, "DUPLICATE_JSON_KEY")
            parsed[key] = value
        return parsed

    @classmethod
    def _json(cls, body: bytes, keys: frozenset[str]) -> dict:
        if not body or len(body) > _MAX_BODY:
            raise Stage30Refused(400, "BOUNDED_JSON_REQUIRED")
        try:
            parsed = json.loads(
                body.decode("ascii"), object_pairs_hook=cls._object,
                parse_constant=lambda _: (_ for _ in ()).throw(
                    Stage30Refused(400, "NONFINITE_JSON_FORBIDDEN")))
        except Stage30Refused:
            raise
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise Stage30Refused(400, "MALFORMED_JSON") from exc
        if type(parsed) is not dict or set(parsed) != keys:
            raise Stage30Refused(400, "EXACT_JSON_FIELDS_REQUIRED")
        return parsed

    @staticmethod
    def _base64(value, *, limit: int) -> bytes:
        if type(value) is not str or not 1 <= len(value) <= ((limit+2)//3)*4:
            raise Stage30Refused(400, "BOUNDED_BASE64_REQUIRED")
        try:
            result = base64.b64decode(value, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise Stage30Refused(400, "CANONICAL_BASE64_REQUIRED") from exc
        if (not 1 <= len(result) <= limit
                or base64.b64encode(result).decode("ascii") != value):
            raise Stage30Refused(400, "CANONICAL_BASE64_REQUIRED")
        return result

    @staticmethod
    def _bearer(headers: dict[str, str]) -> str:
        authorization = headers.get("authorization", "")
        if (not authorization.startswith("Bearer ")
                or len(authorization) != len("Bearer ") + 43):
            raise Stage30Refused(401, "BEARER_REQUIRED")
        return authorization[7:]

    def _dispatch(self, endpoint: str, headers: dict[str, str],
                  body: bytes) -> tuple[int, dict]:
        if endpoint == "challenge":
            if "authorization" in headers:
                raise Stage30Refused(400, "UNEXPECTED_AUTHORIZATION")
            value = self._json(body, frozenset({
                "tenant_id", "publisher", "key_id"}))
            if any(type(v) is not str or len(v) > 80 for v in value.values()):
                raise Stage30Refused(400, "INVALID_LOGIN_IDENTITY")
            claim = self.intake.begin_login(
                tenant_id=value["tenant_id"],
                publisher=value["publisher"],
                key_id=value["key_id"], operator_ack=True)
            return 200, {"challenge": claim,
                         "public_plugin_install_authorized": False}
        if endpoint == "session":
            if "authorization" in headers:
                raise Stage30Refused(400, "UNEXPECTED_AUTHORIZATION")
            value = self._json(body, frozenset({
                "challenge", "signature_b64"}))
            signature = self._base64(value["signature_b64"], limit=64)
            ticket = self.intake.complete_login(
                challenge=value["challenge"],
                signature=signature, operator_ack=True)
            return 200, {
                "token": ticket.token, "expires_at": ticket.expires_at,
                "scope": ticket.scope,
                "public_plugin_install_authorized": False,
                "broker_order_authorized": False,
            }
        token = self._bearer(headers)
        if endpoint == "me":
            if body:
                raise Stage30Refused(400, "GET_BODY_FORBIDDEN")
            return 200, self.intake.status(token=token)
        if endpoint == "logout":
            self._json(body, frozenset())
            self.intake.revoke_session(token=token, operator_ack=True)
            return 200, {"state": "SESSION_REVOKED"}
        if endpoint == "quarantine":
            value = self._json(body, frozenset({
                "binding_id", "package_b64", "candidate_b64"}))
            bid = value["binding_id"]
            if type(bid) is not str or bid not in self.targets:
                raise Stage30Refused(403, "UNREVIEWED_BINDING_TARGET")
            # Never accept manifest, trusted CoreBinding, host image, signer,
            # source code or tenant identity from network-provided JSON.
            target = self.targets[bid]
            package = self._base64(value["package_b64"], limit=90000)
            signed = self._base64(value["candidate_b64"], limit=4096)
            receipt = self.intake.submit_package(
                token=token, stage23=target.signed_witness,
                package=package, signed_candidate=signed,
                manifest=target.manifest, binding=target.binding,
                expected_image=target.pinned_image, operator_ack=True)
            return 202, {
                "state": receipt.state,
                "binding_id": receipt.binding_id,
                "package_sha256": receipt.package_sha256,
                "public_plugin_install_authorized": False,
                "source_execution_authorized": False,
                "telegram_publish_authorized": False,
                "broker_order_authorized": False,
            }
        raise Stage30Refused(404, "UNKNOWN_ENDPOINT")

    @staticmethod
    async def _send(send, status: int, data: dict) -> None:
        payload = canonical(data)
        await send({
            "type": "http.response.start", "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"cache-control", b"no-store, max-age=0"),
                (b"pragma", b"no-cache"),
                (b"x-content-type-options", b"nosniff"),
                (b"content-security-policy", b"default-src 'none'"),
                (b"strict-transport-security", b"max-age=31536000"),
            ],
        })
        await send({"type": "http.response.body", "body": payload,
                    "more_body": False})

    async def __call__(self, scope, receive, send) -> None:
        """ASGI entrypoint. Explicitly DOES NOT create a network listener."""
        try:
            if (type(scope) is not dict or scope.get("type") != "http"
                    or scope.get("scheme") != "https"):
                raise Stage30Refused(403, "HTTPS_HOST_ADAPTER_REQUIRED")
            client = scope.get("client")
            if (not isinstance(client, (list, tuple)) or len(client) != 2
                    or type(client[0]) is not str):
                raise Stage30Refused(403, "TRUSTED_CLIENT_ADDRESS_REQUIRED")
            try:
                address = ipaddress.ip_address(client[0]).compressed
            except ValueError as exc:
                raise Stage30Refused(403, "TRUSTED_CLIENT_ADDRESS_REQUIRED") from exc
            # Rate control occurs before JSON, auth and any expensive crypto.
            self._rate(address)
            path = scope.get("path")
            method = scope.get("method")
            if type(path) is not str or path not in _ENDPOINTS:
                raise Stage30Refused(404, "UNKNOWN_ENDPOINT")
            endpoint = _ENDPOINTS[path]
            if (method != ("GET" if endpoint == "me" else "POST")
                    or scope.get("query_string", b"") not in (b"", None)):
                raise Stage30Refused(405, "METHOD_OR_QUERY_NOT_ALLOWED")
            headers = self._headers(scope.get("headers", []))
            if method == "POST" and headers.get("content-type") != _CONTENT_TYPE:
                raise Stage30Refused(415, "JSON_CONTENT_TYPE_REQUIRED")
            declared = headers.get("content-length")
            if declared is not None and (
                    not declared.isascii() or not declared.isdecimal()
                    or len(declared) > 6 or int(declared) > _MAX_BODY):
                raise Stage30Refused(413, "BOUNDED_CONTENT_LENGTH_REQUIRED")
            if endpoint != "quarantine" and declared is not None and int(declared) > 8192:
                raise Stage30Refused(413, "SMALL_AUTH_BODY_REQUIRED")
            chunks = []
            total = 0
            for _ in range(_MAX_CHUNKS):
                message = await receive()
                if (type(message) is not dict
                        or message.get("type") != "http.request"
                        or type(message.get("body", b"")) is not bytes):
                    raise Stage30Refused(400, "INVALID_HTTP_BODY")
                piece = message.get("body", b"")
                total += len(piece)
                if total > _MAX_BODY or (endpoint != "quarantine" and total > 8192):
                    raise Stage30Refused(413, "REQUEST_TOO_LARGE")
                chunks.append(piece)
                if message.get("more_body", False) is not True:
                    break
            else:
                raise Stage30Refused(413, "TOO_MANY_REQUEST_CHUNKS")
            body = b"".join(chunks)
            if declared is not None and int(declared) != len(body):
                raise Stage30Refused(400, "CONTENT_LENGTH_MISMATCH")
            code, response = self._dispatch(endpoint, headers, body)
        except Stage30Refused as exc:
            code, response = exc.status, {"error": exc.code}
        except (Stage28Refused, Stage29Refused, ValueError, TypeError):
            code, response = 403, {"error": "AUTHORIZATION_OR_INTAKE_REFUSED"}
        except sqlite3.DatabaseError:
            code, response = 503, {"error": "SECURE_GATE_UNAVAILABLE"}
        await self._send(send, code, response)


__all__ = [
    "Stage30Refused", "ReviewedUploadTarget", "OfflineDeveloperAsgiGateway",
]
