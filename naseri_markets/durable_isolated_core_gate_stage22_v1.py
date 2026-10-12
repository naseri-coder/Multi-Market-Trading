"""Stage 22: durable tenant-fenced admission for Stage-4 isolated Core API.

No plugin import, code loader, network, broker, Telegram, risk bypass or live
execution. A reviewed SHA256 pin authenticates bytes, NOT publisher identity.
Container isolation requires a separately accepted rootless Docker/gVisor host.
The lease is persisted *before* external evaluation; unfinished leases after a
crash can never be automatically resumed or silently retried.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import sqlite3
import stat
from contextlib import contextmanager
from pathlib import Path

from .core_api_v1 import (
    CoreBinding, CoreInput, CoreManifest, CoreResult, DataOrigin,
    content_digest, validate_core_result,
)
from .secure_plugin_runtime_v1 import SecureOfflineCoreHost

_TENANT = re.compile(r"[a-z][a-z0-9_-]{1,31}\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")


class Stage22Refused(ValueError):
    """Operator-visible refusal contains no plugin payload or private identity."""


def _gate(operator_ack: bool) -> None:
    if (operator_ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        raise Stage22Refused("EXPLICIT_NONPRODUCTION_REVIEW_REQUIRED")


def _tenant(value: str) -> None:
    if type(value) is not str or not _TENANT.fullmatch(value):
        raise Stage22Refused("TRUSTED_TENANT_ID_REQUIRED")


def _pin(value: str) -> None:
    if type(value) is not str or not _SHA.fullmatch(value):
        raise Stage22Refused("REVIEWED_DIGEST_REQUIRED")


class DurableIsolatedCoreGate:
    """One private SQLite ledger, explicit CAS changes, max 2 in-flight/tenant.

    Tenant identity comes from a *trusted host caller*, NOT this module.
    Never expose this object to arbitrary plugin code or treat tenant_id as
    authentication. Results are inert CoreResult only, not trade approval.
    """

    def __init__(self, path: Path, *, host: SecureOfflineCoreHost) -> None:
        _gate(True)
        if type(host) is not SecureOfflineCoreHost or not host.policy.enabled:
            raise Stage22Refused("REAL_ISOLATED_HOST_POLICY_REQUIRED")
        if (not isinstance(path, Path) or not path.is_absolute() or path.is_symlink()
                or not path.parent.is_dir() or path.parent.is_symlink()
                or path.parent.stat().st_uid != os.geteuid()
                or stat.S_IMODE(path.parent.stat().st_mode) & 0o077):
            raise Stage22Refused("OWNER_PRIVATE_LEDGER_DIRECTORY_REQUIRED")
        if path.exists():
            info = path.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_uid != os.geteuid()
                    or stat.S_IMODE(info.st_mode) & 0o077):
                raise Stage22Refused("PRIVATE_LEDGER_FILE_REQUIRED")
        else:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY
                         | os.O_NOFOLLOW, 0o600)
            os.close(fd)
        self.path = path
        self.host = host
        self.db = sqlite3.connect(path, timeout=0.2, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=200")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS secure22_bindings(
              binding_id TEXT PRIMARY KEY,
              tenant_id TEXT NOT NULL,
              instance_id TEXT NOT NULL,
              core_id TEXT NOT NULL,
              core_version TEXT NOT NULL,
              manifest_digest TEXT NOT NULL,
              binding_digest TEXT NOT NULL,
              source_sha256 TEXT NOT NULL,
              state TEXT NOT NULL CHECK(state IN
                ('DISABLED','ENABLED','EVALUATING','QUARANTINED','REVOKED')),
              revision INTEGER NOT NULL CHECK(revision >= 1),
              last_error TEXT,
              verified_evaluations INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS secure22_attempts(
              binding_id TEXT NOT NULL REFERENCES secure22_bindings(binding_id),
              input_digest TEXT NOT NULL,
              lease_revision INTEGER NOT NULL,
              status TEXT NOT NULL CHECK(status IN
                ('IN_FLIGHT','VERIFIED','FAILED','DISCARDED')),
              result_digest TEXT,
              PRIMARY KEY(binding_id,input_digest)
            );
            CREATE TABLE IF NOT EXISTS secure26_public_fence(
              binding_id TEXT PRIMARY KEY REFERENCES secure22_bindings(binding_id),
              tenant_id TEXT NOT NULL, candidate_sha256 TEXT NOT NULL,
              observation_sha256 TEXT NOT NULL,
              source_sha256 TEXT NOT NULL, sealed_revision INTEGER NOT NULL,
              state TEXT NOT NULL CHECK(state='PENDING_INDEPENDENT_HOST_REVIEW')
            );
            CREATE TRIGGER IF NOT EXISTS secure26_fence_initial
            BEFORE INSERT ON secure26_public_fence
            WHEN NOT EXISTS (
                  SELECT 1 FROM secure22_bindings b WHERE b.binding_id=NEW.binding_id
                    AND b.tenant_id=NEW.tenant_id AND b.state='DISABLED'
                    AND b.revision=NEW.sealed_revision
                    AND b.source_sha256=NEW.source_sha256
                 ) OR EXISTS (
                  SELECT 1 FROM secure22_attempts a
                  WHERE a.binding_id=NEW.binding_id
                 )
            BEGIN
              SELECT RAISE(ABORT,'STAGE26_PREEXISTING_CORE_NOT_SAFE_TO_SEAL');
            END;
            CREATE TRIGGER IF NOT EXISTS secure26_no_enable
            BEFORE UPDATE OF state ON secure22_bindings
            WHEN NEW.state IN ('ENABLED','EVALUATING')
              AND EXISTS (
                SELECT 1 FROM secure26_public_fence p
                WHERE p.binding_id=NEW.binding_id
              )
            BEGIN
              SELECT RAISE(ABORT,'STAGE26_PUBLIC_EXECUTION_BLOCKED');
            END;
            CREATE TRIGGER IF NOT EXISTS secure26_no_delete
            BEFORE DELETE ON secure26_public_fence
            BEGIN
              SELECT RAISE(ABORT,'STAGE26_FENCE_IS_PERMANENT');
            END;
            CREATE TRIGGER IF NOT EXISTS secure26_no_mutate
            BEFORE UPDATE ON secure26_public_fence
            BEGIN
              SELECT RAISE(ABORT,'STAGE26_FENCE_IS_IMMUTABLE');
            END;
        """)

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def close(self) -> None:
        self.db.close()

    @contextmanager
    def _tx(self):
        try:
            self.db.execute("BEGIN IMMEDIATE")
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def _row(self, tenant_id: str, binding_id: str):
        _tenant(tenant_id)
        if type(binding_id) is not str or not 1 <= len(binding_id) <= 128:
            raise Stage22Refused("VALID_BINDING_REQUIRED")
        row = self.db.execute(
            "SELECT * FROM secure22_bindings WHERE binding_id=? AND tenant_id=?",
            (binding_id, tenant_id)).fetchone()
        if row is None:
            raise Stage22Refused("TENANT_BINDING_NOT_AUTHORIZED")
        return row

    def register(self, tenant_id: str, manifest: CoreManifest,
                 binding: CoreBinding, *,
                 approved_manifest_digest: str, approved_source_sha256: str,
                 operator_ack: bool = False) -> dict:
        """Immutable data-only registration: no source bytes, code or execute."""
        _gate(operator_ack)
        _tenant(tenant_id)
        _pin(approved_manifest_digest)
        _pin(approved_source_sha256)
        if (type(manifest) is not CoreManifest or type(binding) is not CoreBinding
                or binding.instrument.market not in manifest.supported_markets):
            raise Stage22Refused("VALID_MANIFEST_BINDING_REQUIRED")
        if not hmac.compare_digest(content_digest(manifest), approved_manifest_digest):
            raise Stage22Refused("MANIFEST_PIN_MISMATCH")
        # Registration is limited to pure strategy metadata and a host-owned
        # market binding. The worker does not learn tenant identity or tokens.
        with self._tx():
            if self.db.execute(
                "SELECT 1 FROM secure22_bindings WHERE binding_id=?",
                (binding.binding_id,)).fetchone():
                raise Stage22Refused("BINDING_ID_RESERVED_GLOBAL")
            if self.db.execute(
                "SELECT COUNT(*) FROM secure22_bindings").fetchone()[0] >= 64:
                raise Stage22Refused("GLOBAL_BINDING_QUOTA")
            if self.db.execute(
                "SELECT COUNT(*) FROM secure22_bindings WHERE tenant_id=?",
                (tenant_id,)).fetchone()[0] >= 8:
                raise Stage22Refused("TENANT_BINDING_QUOTA")
            self.db.execute(
                "INSERT INTO secure22_bindings("
                "binding_id,tenant_id,instance_id,core_id,core_version,"
                "manifest_digest,binding_digest,source_sha256,state,revision)"
                " VALUES (?,?,?,?,?,?,?,?,?,1)",
                (binding.binding_id, tenant_id, binding.instance_id,
                 manifest.core_id, manifest.core_version, approved_manifest_digest,
                 content_digest(binding), approved_source_sha256, "DISABLED"))
        return self.state(tenant_id, binding.binding_id)

    def state(self, tenant_id: str, binding_id: str) -> dict:
        row = self._row(tenant_id, binding_id)
        return {
            "binding_id": row["binding_id"], "core_id": row["core_id"],
            "state": row["state"], "revision": row["revision"],
            "verified_evaluations": row["verified_evaluations"],
            "last_error": row["last_error"],
            "paper_only": True, "telegram_send_authorized": False,
            "broker_order_authorized": False,
            "public_untrusted_candidate_locked": bool(self.db.execute(
                "SELECT 1 FROM secure26_public_fence WHERE binding_id=?",
                (binding_id,)).fetchone()),
        }

    def set_enabled(self, tenant_id: str, binding_id: str, *,
                    enabled: bool, expected_revision: int,
                    operator_ack: bool = False) -> dict:
        _gate(operator_ack)
        if type(enabled) is not bool or type(expected_revision) is not int:
            raise Stage22Refused("BOOLEAN_AND_CAS_REVISION_REQUIRED")
        with self._tx():
            row = self._row(tenant_id, binding_id)
            if row["revision"] != expected_revision:
                raise Stage22Refused("STALE_OPERATOR_REVISION")
            if enabled:
                if self.db.execute(
                        "SELECT 1 FROM secure26_public_fence WHERE binding_id=?",
                        (binding_id,)).fetchone():
                    raise Stage22Refused("STAGE26_PUBLIC_UNTRUSTED_CORE_LOCKED")
                if row["state"] != "DISABLED":
                    raise Stage22Refused("FRESH_REVIEW_REQUIRED_FOR_RECOVERY")
                next_state = "ENABLED"
            else:
                if row["state"] in ("REVOKED", "QUARANTINED"):
                    raise Stage22Refused("NONRECOVERABLE_BINDING")
                # Disabling during an external invocation revokes the entire
                # incarnation: no output is admissible and no auto-reenable.
                next_state = ("REVOKED" if row["state"] == "EVALUATING"
                              else "DISABLED")
            self.db.execute(
                "UPDATE secure22_bindings SET state=?,revision=revision+1 "
                "WHERE binding_id=?", (next_state, binding_id))
        return self.state(tenant_id, binding_id)

    def _finish(self, binding_id: str, digest: str, revision: int, *,
                success: bool, result_digest: str | None = None) -> bool:
        with self._tx():
            row = self.db.execute(
                "SELECT revision,state FROM secure22_bindings WHERE binding_id=?",
                (binding_id,)).fetchone()
            if row is None:
                raise Stage22Refused("PERSISTED_BINDING_MISSING")
            valid = (row["revision"] == revision
                     and row["state"] == "EVALUATING")
            self.db.execute(
                "UPDATE secure22_attempts SET status=?,result_digest=? "
                "WHERE binding_id=? AND input_digest=? AND status='IN_FLIGHT'",
                (("VERIFIED" if success else "FAILED") if valid else "DISCARDED",
                 result_digest if success and valid else None, binding_id, digest))
            if valid:
                self.db.execute(
                    "UPDATE secure22_bindings SET state=?,revision=revision+1,"
                    "last_error=?,verified_evaluations=verified_evaluations+? "
                    "WHERE binding_id=?",
                    ("ENABLED" if success else "QUARANTINED",
                     None if success else "ISOLATED_EVALUATION_REJECTED",
                     1 if success else 0, binding_id))
            return valid

    def evaluate(self, tenant_id: str, manifest: CoreManifest,
                 event: CoreInput, *, source: bytes,
                 operator_ack: bool = False) -> CoreResult:
        """Persisted single-use lease *before* initiating isolated execution."""
        _gate(operator_ack)
        _tenant(tenant_id)
        if (type(manifest) is not CoreManifest or type(event) is not CoreInput
                or type(source) is not bytes
                or not 0 < len(source) <= 65536
                or event.origin not in (DataOrigin.SYNTHETIC, DataOrigin.REPLAY)):
            raise Stage22Refused("NONPRODUCTION_CORE_EVENT_REQUIRED")
        with self._tx():
            row = self._row(tenant_id, event.binding.binding_id)
            if self.db.execute(
                    "SELECT 1 FROM secure26_public_fence WHERE binding_id=?",
                    (event.binding.binding_id,)).fetchone():
                raise Stage22Refused("STAGE26_PUBLIC_UNTRUSTED_CORE_LOCKED")
            if row["state"] != "ENABLED":
                raise Stage22Refused("BINDING_DISABLED_OR_QUARANTINED")
            if (event.core_id != row["core_id"]
                    or event.core_version != row["core_version"]
                    or event.binding.instance_id != row["instance_id"]
                    or content_digest(event.binding) != row["binding_digest"]
                    or content_digest(manifest) != row["manifest_digest"]
                    or not hmac.compare_digest(hashlib.sha256(source).hexdigest(),
                                               row["source_sha256"])):
                raise Stage22Refused("SOURCE_OR_MARKET_BINDING_PIN_MISMATCH")
            if self.db.execute(
                "SELECT COUNT(*) FROM secure22_bindings "
                "WHERE tenant_id=? AND state='EVALUATING'",
                (tenant_id,)).fetchone()[0] >= 2:
                raise Stage22Refused("TENANT_CONCURRENT_CORE_QUOTA")
            digest = event.input_digest
            try:
                lease_rev = row["revision"] + 1
                self.db.execute(
                    "INSERT INTO secure22_attempts VALUES (?,?,?,'IN_FLIGHT',NULL)",
                    (event.binding.binding_id, digest, lease_rev))
            except sqlite3.IntegrityError as exc:
                raise Stage22Refused("DURABLE_INPUT_REPLAY_DENIED") from exc
            self.db.execute(
                "UPDATE secure22_bindings SET state='EVALUATING', "
                "revision=? WHERE binding_id=?",
                (lease_rev, event.binding.binding_id))
        try:
            # NEVER execute the source in this process or fall back to the
            # old trusted-local python -I subprocess path.
            result = self.host.evaluate(
                manifest, event, source=source,
                approved_source_sha256=row["source_sha256"])
            if type(result) is not CoreResult:
                raise Stage22Refused("UNTRUSTED_RESULT_TYPE")
            validate_core_result(manifest, event, result)
            result_sha = content_digest(result)
        except Exception as exc:
            self._finish(event.binding.binding_id, digest, lease_rev, success=False)
            raise Stage22Refused("PERSISTENT_CORE_QUARANTINE") from exc
        if not self._finish(event.binding.binding_id, digest, lease_rev,
                            success=True, result_digest=result_sha):
            raise Stage22Refused("DISABLED_DURING_UNTRUSTED_EVALUATION")
        return result

    def audit(self, tenant_id: str, binding_id: str) -> dict:
        """Only own binding's inert evidence; no source or arbitrary SQL."""
        self._row(tenant_id, binding_id)
        rows = self.db.execute(
            "SELECT status,COUNT(*) as n FROM secure22_attempts "
            "WHERE binding_id=? GROUP BY status", (binding_id,)).fetchall()
        return {
            "binding_id": binding_id,
            "attempt_states": {row["status"]: row["n"] for row in rows},
            "quarantined_or_revoked": self.state(tenant_id, binding_id)["state"]
            in ("QUARANTINED", "REVOKED", "EVALUATING"),
            "trusted_external_publisher": False,
            "real_sandbox_verified": False,
            "public_install_authorized": False,
            "telegram_send_authorized": False,
            "broker_order_authorized": False,
        }


__all__ = ["Stage22Refused", "DurableIsolatedCoreGate"]
