"""Stage29: offline Ed25519 login challenge and scoped one-use ZIP intake.

Real possession-of-key authentication for Stage28 registered publisher keys.
Not a deployed HTTP login, human legal identity verification or authorization
to execute a strategy. A future TLS/authenticated adapter must pass only
server-derived identities and use a trusted clock, never client-supplied time.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import time
from dataclasses import dataclass
from typing import Callable

from .a24_publisher_admission import canonical
from .core_api_v1 import CoreBinding, CoreManifest
from .publisher_package_registry_stage28_v1 import (
    PublisherPackageRegistry, Stage28Refused, _guard, _identity, _proof,
)
from .signed_core_candidate_stage23_v1 import SignedCandidateWitness

_LOGIN_DOMAIN = b"MMT-STAGE29-DEVELOPER-LOGIN-V1\x00"
_TOKEN = re.compile(r"[a-zA-Z0-9_-]{43}\Z")
_CHALLENGE_FIELDS = frozenset({
    "schema", "scope", "tenant_id", "publisher", "publisher_key_id",
    "publisher_revision", "nonce", "issued_at", "expires_at",
})


class Stage29Refused(ValueError):
    """Sanitized authentication/permission refusal: no bearer token leaks."""


@dataclass(frozen=True, slots=True)
class LoginSession:
    """Bearer token is returned once, never logged or stored in plaintext."""

    token: str
    expires_at: int
    scope: str = "QUARANTINE_SUBMIT_ONCE"
    public_plugin_install_authorized: bool = False
    broker_order_authorized: bool = False
    telegram_publication_authorized: bool = False


class AuthenticatedDeveloperIntake:
    """Owner-controlled, no-network session broker for signed Stage28 ZIPs.

    All data and immutable audit live on the SAME Stage22 SQLite connection
    as Stage28. The only upload entrypoint derives identities from a hashed,
    single-use bearer token; Stage28 consumes it *in the same transaction*
    as Stage27 classification and quarantine receipt insertion.
    """

    def __init__(self, registry: PublisherPackageRegistry, *,
                 operator_ack: bool = False,
                 clock: Callable[[], float] | None = None) -> None:
        _guard(operator_ack)
        if type(registry) is not PublisherPackageRegistry:
            raise Stage29Refused("EXACT_OWNER_REGISTERED_PUBLISHERS_REQUIRED")
        self.registry = registry
        self.clock = clock if clock is not None else time.time
        if not callable(self.clock):
            raise Stage29Refused("TRUSTED_SERVER_CLOCK_REQUIRED")
        self.db = registry.stage22.db
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS secure29_policy(
              singleton INTEGER PRIMARY KEY CHECK(singleton=1),
              mode TEXT NOT NULL CHECK(mode='AUTHENTICATED_ONCE_ONLY')
            );
            INSERT OR IGNORE INTO secure29_policy VALUES
              (1,'AUTHENTICATED_ONCE_ONLY');
            CREATE TRIGGER IF NOT EXISTS secure29_no_policy_delete
            BEFORE DELETE ON secure29_policy BEGIN
              SELECT RAISE(ABORT,'STAGE29_POLICY_PERMANENT');
            END;
            CREATE TRIGGER IF NOT EXISTS secure29_no_policy_update
            BEFORE UPDATE ON secure29_policy BEGIN
              SELECT RAISE(ABORT,'STAGE29_POLICY_IMMUTABLE');
            END;
            CREATE TABLE IF NOT EXISTS secure29_challenges(
              digest TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
              publisher TEXT NOT NULL, key_id TEXT NOT NULL,
              publisher_revision INTEGER NOT NULL,
              issued_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
              state TEXT NOT NULL CHECK(state IN ('PENDING','CONSUMED'))
            );
            CREATE TABLE IF NOT EXISTS secure29_sessions(
              session_sha256 TEXT PRIMARY KEY, tenant_id TEXT NOT NULL,
              publisher TEXT NOT NULL, key_id TEXT NOT NULL,
              publisher_revision INTEGER NOT NULL,
              issued_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
              state TEXT NOT NULL CHECK(state IN
                ('ACTIVE','CONSUMED','REVOKED'))
            );
        """)

    def _now(self) -> int:
        n = self.clock()
        if type(n) not in (int, float) or not 1 <= n < 2**53:
            raise Stage29Refused("INVALID_TRUSTED_HOST_TIME")
        return int(n)

    def _active(self, tenant: str, publisher: str, key_id: str):
        person = self.registry._publisher(tenant, publisher)
        key = self.db.execute(
            "SELECT public_key, state FROM secure28_keys WHERE tenant_id=?"
            " AND publisher=? AND key_id=?", (tenant, publisher, key_id)).fetchone()
        if (person is None or person["state"] != "ACTIVE"
                or key is None or key["state"] != "ACTIVE"):
            raise Stage29Refused("PUBLISHER_NOT_AUTHORIZED")
        return person, key

    def begin_login(self, *, tenant_id: str, publisher: str, key_id: str,
                    operator_ack: bool = False) -> dict:
        """One short-lived, signed domain-separated challenge. Never a token."""
        _guard(operator_ack)
        _identity(tenant_id, publisher, key_id)
        now = self._now()
        with self.registry.stage22._tx():
            person, _key = self._active(tenant_id, publisher, key_id)
            # Bounded quotas, no unbounded replay table growth.
            self.db.execute(
                "DELETE FROM secure29_challenges WHERE expires_at<?",
                (now-3600,))
            self.db.execute(
                "DELETE FROM secure29_sessions WHERE expires_at<?",
                (now-86400,))
            if self.db.execute(
                "SELECT COUNT(*) FROM secure29_challenges "
                "WHERE tenant_id=? AND publisher=? AND state='PENDING'"
                " AND expires_at>?", (tenant_id, publisher, now)).fetchone()[0] >= 4:
                raise Stage29Refused("PUBLISHER_LOGIN_RATE_LIMIT")
            if self.db.execute(
                "SELECT COUNT(*) FROM secure29_challenges").fetchone()[0] >= 512:
                raise Stage29Refused("CHALLENGE_LEDGER_QUOTA")
            claim = {
                "schema": 1,
                "scope": "QUARANTINE_SUBMIT_ONCE",
                "tenant_id": tenant_id, "publisher": publisher,
                "publisher_key_id": key_id,
                "publisher_revision": person["revision"],
                "nonce": secrets.token_hex(24),
                "issued_at": now, "expires_at": now+120,
            }
            digest = hashlib.sha256(canonical(claim)).hexdigest()
            self.db.execute(
                "INSERT INTO secure29_challenges VALUES(?,?,?,?,?,?,?,?)",
                (digest, tenant_id, publisher, key_id, person["revision"],
                 now, now+120, "PENDING"))
        return claim

    def complete_login(self, *, challenge: dict, signature: bytes,
                       operator_ack: bool = False) -> LoginSession:
        """Verify currently active Stage28 Ed25519 key, consume challenge."""
        _guard(operator_ack)
        now = self._now()
        if (type(challenge) is not dict or set(challenge) != _CHALLENGE_FIELDS
                or type(challenge["schema"]) is not int
                or challenge["schema"] != 1
                or challenge["scope"] != "QUARANTINE_SUBMIT_ONCE"
                or type(signature) is not bytes or len(signature) != 64):
            raise Stage29Refused("INVALID_SIGNED_LOGIN_CHALLENGE")
        try:
            digest = hashlib.sha256(canonical(challenge)).hexdigest()
            _identity(challenge["tenant_id"], challenge["publisher"],
                      challenge["publisher_key_id"])
        except (ValueError, TypeError, KeyError) as exc:
            raise Stage29Refused("INVALID_LOGIN_IDENTITY") from exc
        with self.registry.stage22._tx():
            row = self.db.execute(
                "SELECT * FROM secure29_challenges WHERE digest=?",
                (digest,)).fetchone()
            if (row is None or row["state"] != "PENDING"
                    or type(challenge["publisher_revision"]) is not int
                    or type(challenge["issued_at"]) is not int
                    or type(challenge["expires_at"]) is not int
                    or row["tenant_id"] != challenge["tenant_id"]
                    or row["publisher"] != challenge["publisher"]
                    or row["key_id"] != challenge["publisher_key_id"]
                    or row["publisher_revision"] != challenge["publisher_revision"]
                    or not row["issued_at"] <= now < row["expires_at"]
                    or row["issued_at"] != challenge["issued_at"]
                    or row["expires_at"] != challenge["expires_at"]):
                raise Stage29Refused("EXPIRED_USED_OR_TAMPERED_LOGIN_CHALLENGE")
            person, key = self._active(
                row["tenant_id"], row["publisher"], row["key_id"])
            if person["revision"] != row["publisher_revision"]:
                raise Stage29Refused("LOGIN_REVOKED_BY_KEY_CHANGE")
            try:
                _proof(key["public_key"], signature, _LOGIN_DOMAIN, challenge)
            except Stage28Refused as exc:
                raise Stage29Refused("INVALID_LOGIN_SIGNATURE") from exc
            if self.db.execute(
                "SELECT COUNT(*) FROM secure29_sessions WHERE tenant_id=?"
                " AND publisher=? AND state='ACTIVE' AND expires_at>?",
                (row["tenant_id"], row["publisher"], now)).fetchone()[0] >= 4:
                raise Stage29Refused("PUBLISHER_SESSION_QUOTA")
            token = secrets.token_urlsafe(32)
            token_sha = hashlib.sha256(token.encode("ascii")).hexdigest()
            self.db.execute(
                "UPDATE secure29_challenges SET state='CONSUMED' WHERE digest=?",
                (digest,))
            self.db.execute(
                "INSERT INTO secure29_sessions VALUES(?,?,?,?,?,?,?,?)",
                (token_sha, row["tenant_id"], row["publisher"], row["key_id"],
                 row["publisher_revision"], now, now+300, "ACTIVE"))
            self.registry._audit(row["tenant_id"], row["publisher"],
                                 "AUTHENTICATED", row["key_id"], token_sha, now)
        return LoginSession(token=token, expires_at=now+300)

    def _session(self, token: str):
        if type(token) is not str or not _TOKEN.fullmatch(token):
            raise Stage29Refused("VALID_ONE_TIME_SESSION_TOKEN_REQUIRED")
        digest = hashlib.sha256(token.encode("ascii")).hexdigest()
        row = self.db.execute(
            "SELECT * FROM secure29_sessions WHERE session_sha256=?",
            (digest,)).fetchone()
        if row is None or row["state"] != "ACTIVE":
            raise Stage29Refused("SESSION_INVALID_OR_CONSUMED")
        person, _key = self._active(row["tenant_id"], row["publisher"],
                                    row["key_id"])
        now = self._now()
        if (not row["issued_at"] <= now < row["expires_at"]
                or row["publisher_revision"] != person["revision"]):
            raise Stage29Refused("SESSION_EXPIRED_OR_REVOKED")
        return row, digest, now

    def submit_package(self, *, token: str, stage23: SignedCandidateWitness,
                       package: bytes, signed_candidate: bytes,
                       manifest: CoreManifest, binding: CoreBinding,
                       expected_image: str, operator_ack: bool = False):
        """Only public submission method: derives tenant/publisher from session.

        Registry's Stage29 hook checks+consumes the bearer in the Stage22
        transaction that inserts immutable signed ZIP+Stage27 classification.
        """
        _guard(operator_ack)
        row, digest, now = self._session(token)
        try:
            return self.registry.submit(
                tenant_id=row["tenant_id"], publisher=row["publisher"],
                key_id=row["key_id"], stage23=stage23, package=package,
                signed_candidate=signed_candidate, manifest=manifest,
                binding=binding, expected_image=expected_image, now=now,
                operator_ack=True, _auth_session_sha256=digest)
        except (Stage28Refused, ValueError, TypeError) as exc:
            raise Stage29Refused("AUTHENTICATED_QUARANTINE_REFUSED") from exc

    def revoke_session(self, *, token: str, operator_ack: bool = False) -> None:
        """Session holder logs out; no other caller identifiers accepted."""
        _guard(operator_ack)
        _row, digest, now = self._session(token)
        with self.registry.stage22._tx():
            row = self.db.execute(
                "SELECT * FROM secure29_sessions WHERE session_sha256=?",
                (digest,)).fetchone()
            if row is None or row["state"] != "ACTIVE":
                raise Stage29Refused("SESSION_ALREADY_REVOKED")
            self.db.execute(
                "UPDATE secure29_sessions SET state='REVOKED' "
                "WHERE session_sha256=?", (digest,))
            self.registry._audit(row["tenant_id"], row["publisher"],
                                 "SESSION_REVOKED", row["key_id"], digest, now)

    def status(self, *, token: str) -> dict:
        """Inert authenticated identity view. Never exposes keys or source."""
        row, _digest, _now = self._session(token)
        return {
            "tenant_id": row["tenant_id"], "publisher": row["publisher"],
            "key_id": row["key_id"], "scope": "QUARANTINE_SUBMIT_ONCE",
            "expires_at": row["expires_at"],
            "public_install_authorized": False,
            "broker_order_authorized": False,
            "telegram_signal_authorized": False,
        }


__all__ = [
    "Stage29Refused", "LoginSession", "AuthenticatedDeveloperIntake",
    "_LOGIN_DOMAIN",
]
