"""A13 private-plugin offline provisioning rehearsal for Multi Market Trading.

PREPARED and OFFLINE_VERIFIED are METADATA states. Neither implies code
installation, remote service health, actual publisher identity, production
admission or permission to emit signals. No live transports or secrets.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from pathlib import Path

from .a12_trust import AdmissionRefused, OfflineAdmission, TrustStore
from .delivery_ledger import open_sqlite
from .plugin_manager import PluginManager

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_FIELDS = frozenset({
    "schema_version", "engine_id", "engine_version", "installation_id",
    "manifest_sha256",
    "trust_generation", "owner_dns", "owner_cert_sha256",
    "ca_sha256", "mode",
})


class ProvisioningRefused(ValueError):
    """Metadata lifecycle action rejected without changing active engines."""


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in pairs:
        if key in out:
            raise ProvisioningRefused("A13_DUPLICATE_FIELD")
        out[key] = value
    return out


@dataclass(frozen=True, slots=True)
class ProvisioningRecord:
    engine_id: str
    installation_id: str
    generation: int
    manifest_sha256: str
    plan_sha256: str
    incarnation: int
    status: str
    revision: int


@dataclass(frozen=True, slots=True)
class ProvisioningHealth:
    """Snapshot at a given time; never claim actual remote health."""
    engine_id: str
    state: str
    verified_offline: bool
    external_engine_connected: bool = False
    certificate_deployed: bool = False
    live_trading_permitted: bool = False
    telegram_enabled: bool = False


def parse_plan(raw: bytes, *, approved_sha256: str) -> dict:
    if type(raw) is not bytes or not 0 < len(raw) <= 8192:
        raise ProvisioningRefused("A13_INVALID_PLAN_SIZE")
    if type(approved_sha256) is not str or not _SHA.fullmatch(approved_sha256):
        raise ProvisioningRefused("A13_INDEPENDENT_SHA_APPROVAL_REQUIRED")
    digest = hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(digest, approved_sha256):
        raise ProvisioningRefused("A13_PLAN_PIN_MISMATCH")
    try:
        p = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                ProvisioningRefused("A13_NONFINITE")
            ),
        )
    except (UnicodeError, ValueError) as exc:
        raise ProvisioningRefused("A13_INVALID_JSON") from exc
    if not isinstance(p, dict) or set(p) != _FIELDS:
        raise ProvisioningRefused("A13_SCHEMA_MISMATCH")
    if type(p["schema_version"]) is not int or p["schema_version"] != 1:
        raise ProvisioningRefused("A13_SCHEMA_VERSION")
    if p["mode"] != "offline_paper_only" or type(p["mode"]) is not str:
        raise ProvisioningRefused("A13_FORBIDDEN_MODE")
    if type(p["trust_generation"]) is not int or p["trust_generation"] < 1:
        raise ProvisioningRefused("A13_GENERATION")
    for field in ("manifest_sha256", "owner_cert_sha256", "ca_sha256"):
        if type(p[field]) is not str or not _SHA.fullmatch(p[field]):
            raise ProvisioningRefused("A13_BAD_HASH")
    for field in ("engine_id", "engine_version", "owner_dns", "installation_id"):
        if type(p[field]) is not str or not 0 < len(p[field]) <= 100:
            raise ProvisioningRefused("A13_IDENTITY_REQUIRED")
    if re.fullmatch(r"[a-z][a-z0-9_-]{2,47}", p["installation_id"]) is None:
        raise ProvisioningRefused("A13_INSTALLATION_ID")
    if re.fullmatch(r"[a-z0-9-]{1,60}\.fixture", p["owner_dns"]) is None:
        raise ProvisioningRefused("A13_NONFIXTURE_HOST_FORBIDDEN")
    return p


class OfflineProvisioner:
    """Durable metadata-only stage/verify/suspend/reprepare/retire controller.

    A13 never changes A8 enable flags, imports plugin code or publishes.
    Fresh A12 verification is required for every trusted status query.
    """

    def __init__(
        self, path: str | Path, *, plugins: PluginManager, trust: TrustStore,
        installation_id: str,
    ) -> None:
        if (
            type(installation_id) is not str
            or re.fullmatch(r"[a-z][a-z0-9_-]{2,47}", installation_id) is None
        ):
            raise ProvisioningRefused("A13_TRUSTED_INSTALLATION_REQUIRED")
        self._installation_id = installation_id
        path = Path(path)
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ProvisioningRefused("A13_UNSAFE_STORE")
        self._db = open_sqlite(path)
        self._plugins = plugins
        self._trust = trust
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS a13_provision (
                engine_id TEXT PRIMARY KEY, installation_id TEXT NOT NULL,
                generation INTEGER NOT NULL,
                manifest_sha256 TEXT NOT NULL, plan_sha256 TEXT NOT NULL,
                incarnation INTEGER NOT NULL, status TEXT NOT NULL,
                revision INTEGER NOT NULL CHECK(revision >= 1)
            )
        """)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS a13_events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                engine_id TEXT NOT NULL, event TEXT NOT NULL,
                revision INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

    def close(self) -> None:
        self._db.close()

    @staticmethod
    def _as_record(row) -> ProvisioningRecord:
        return ProvisioningRecord(
            row["engine_id"], row["installation_id"],
            row["generation"], row["manifest_sha256"],
            row["plan_sha256"], row["incarnation"], row["status"],
            row["revision"],
        )

    def get(self, engine_id: str) -> ProvisioningRecord | None:
        row = self._db.execute(
            "SELECT * FROM a13_provision WHERE engine_id=?", (engine_id,),
        ).fetchone()
        return self._as_record(row) if row else None

    def history(self, engine_id: str) -> tuple[dict, ...]:
        rows = self._db.execute(
            "SELECT seq,event,revision,created_at FROM a13_events "
            "WHERE engine_id=? ORDER BY seq", (engine_id,),
        ).fetchall()
        return tuple(dict(row) for row in rows)

    def _event(self, ident: str, action: str, revision: int) -> None:
        self._db.execute(
            "INSERT INTO a13_events(engine_id,event,revision) VALUES(?,?,?)",
            (ident, action, revision),
        )

    def _match(self, p: dict) -> int:
        if p["installation_id"] != self._installation_id:
            raise ProvisioningRefused("A13_CROSS_INSTALLATION_PLAN")
        plugin = self._plugins.get(p["engine_id"])
        if plugin is None or (
            plugin.visibility, plugin.adapter
        ) != ("private", "external_contract") or plugin.enabled:
            raise ProvisioningRefused("A13_PRIVATE_DISABLED_PLUGIN_REQUIRED")
        if (
            plugin.engine_version != p["engine_version"]
            or plugin.digest != p["manifest_sha256"]
        ):
            raise ProvisioningRefused("A13_PLUGIN_MISMATCH")
        try:
            policy = self._trust.active(p["engine_id"])
        except AdmissionRefused as exc:
            raise ProvisioningRefused("A13_ACTIVE_POLICY_REQUIRED") from exc
        for name in ("generation", "manifest_sha256", "engine_version",
                     "owner_dns", "owner_cert_sha256", "ca_sha256"):
            planned = p["trust_generation"] if name == "generation" else p[name]
            if policy[name if name != "generation" else "generation"] != planned:
                raise ProvisioningRefused("A13_POLICY_MISMATCH")
        return self._plugins.incarnation(p["engine_id"])

    def prepare(
        self, raw: bytes, *, approved_sha256: str,
        expected_revision: int | None = None,
    ) -> ProvisioningRecord:
        p = parse_plan(raw, approved_sha256=approved_sha256)
        incarnation = self._match(p)
        ident = p["engine_id"]
        self._db.execute("BEGIN IMMEDIATE")
        try:
            existing = self._db.execute(
                "SELECT * FROM a13_provision WHERE engine_id=?", (ident,),
            ).fetchone()
            if existing is None:
                if expected_revision is not None:
                    raise ProvisioningRefused("A13_UNKNOWN_RECORD")
                revision, operation = 1, "PREPARE"
                self._db.execute(
                    "INSERT INTO a13_provision VALUES(?,?,?,?,?,?,?,?)",
                    (ident, self._installation_id, p["trust_generation"],
                     p["manifest_sha256"], approved_sha256, incarnation,
                     "PREPARED", revision),
                )
            else:
                prior = self._as_record(existing)
                if (
                    prior.status != "SUSPENDED"
                    or type(expected_revision) is not int
                    or prior.revision != expected_revision
                    or p["trust_generation"] < prior.generation
                ):
                    raise ProvisioningRefused("A13_SUSPEND_AND_CAS_REQUIRED")
                revision, operation = prior.revision + 1, "REPREPARE"
                self._db.execute(
                    "UPDATE a13_provision SET generation=?,manifest_sha256=?,"
                    "plan_sha256=?,incarnation=?,status='PREPARED',revision=? "
                    "WHERE engine_id=? AND revision=?",
                    (p["trust_generation"], p["manifest_sha256"],
                     approved_sha256, incarnation, revision, ident,
                     expected_revision),
                )
            self._event(ident, operation, revision)
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        return self.get(ident)

    def _require_current(self, record: ProvisioningRecord) -> None:
        if record.installation_id != self._installation_id:
            raise ProvisioningRefused("A13_INSTALLATION_STATE_MISMATCH")
        plugin = self._plugins.get(record.engine_id)
        if (
            plugin is None or plugin.visibility != "private"
            or plugin.adapter != "external_contract"
            or plugin.digest != record.manifest_sha256
            or self._plugins.incarnation(record.engine_id) != record.incarnation
            or plugin.enabled
        ):
            raise ProvisioningRefused("A13_PLUGIN_CHANGED_OR_ENABLED")
        try:
            policy = self._trust.active(record.engine_id)
        except AdmissionRefused as exc:
            raise ProvisioningRefused("A13_TRUST_DISABLED") from exc
        if (
            policy["generation"] != record.generation
            or policy["manifest_sha256"] != record.manifest_sha256
        ):
            raise ProvisioningRefused("A13_TRUST_GENERATION_CHANGED")

    def _verify_evidence(
        self, record: ProvisioningRecord, *, admission: OfflineAdmission,
        now: int,
    ) -> None:
        if not isinstance(admission, OfflineAdmission):
            raise ProvisioningRefused("A13_OFFLINE_ADMISSION_REQUIRED")
        # A12's in-memory gate MUST reference this exact trust authority,
        # never an untrusted alternate store with self-issued signing keys.
        if (
            admission._store is not self._trust
            or admission._installation_id != self._installation_id
        ):
            raise ProvisioningRefused("A13_CROSS_INSTALLATION_OR_TRUST_STORE")
        self._require_current(record)
        snapshot = admission.snapshot(now=now)
        if (
            snapshot.engine_id != record.engine_id
            or snapshot.generation != record.generation
            or snapshot.manifest_sha256 != record.manifest_sha256
        ):
            raise ProvisioningRefused("A13_SIGNED_GRANT_SCOPE_MISMATCH")
        self._require_current(record)

    def verify(
        self, engine_id: str, *, expected_revision: int,
        admission: OfflineAdmission, now: int,
    ) -> ProvisioningRecord:
        current = self.get(engine_id)
        if (
            current is None or current.status != "PREPARED"
            or type(expected_revision) is not int
            or current.revision != expected_revision
        ):
            raise ProvisioningRefused("A13_STALE_OR_NOT_PREPARED")
        self._verify_evidence(current, admission=admission, now=now)
        self._db.execute("BEGIN IMMEDIATE")
        try:
            row = self._db.execute(
                "SELECT status,revision FROM a13_provision WHERE engine_id=?",
                (engine_id,),
            ).fetchone()
            if row["revision"] != expected_revision or row["status"] != "PREPARED":
                raise ProvisioningRefused("A13_CONCURRENT_CHANGE")
            self._db.execute(
                "UPDATE a13_provision SET status='OFFLINE_VERIFIED',"
                "revision=revision+1 WHERE engine_id=?",
                (engine_id,),
            )
            self._event(engine_id, "VERIFY_LOCAL_ONLY", expected_revision + 1)
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        return self.get(engine_id)

    def health(
        self, engine_id: str, *, admission: OfflineAdmission | None = None,
        now: int | None = None,
    ) -> ProvisioningHealth:
        record = self.get(engine_id)
        if record is None:
            return ProvisioningHealth(engine_id, "NOT_PREPARED", False)
        if record.status != "OFFLINE_VERIFIED":
            return ProvisioningHealth(engine_id, record.status, False)
        if admission is None or type(now) is not int:
            return ProvisioningHealth(engine_id, "RECHECK_REQUIRED", False)
        try:
            self._verify_evidence(record, admission=admission, now=now)
        except (AdmissionRefused, ProvisioningRefused):
            return ProvisioningHealth(engine_id, "ADMISSION_INVALID", False)
        return ProvisioningHealth(engine_id, "OFFLINE_VERIFIED", True)

    def _transition(
        self, engine_id: str, *, expected_revision: int,
        required: frozenset[str], next_state: str, event: str,
    ) -> ProvisioningRecord:
        if type(expected_revision) is not int or expected_revision <= 0:
            raise ProvisioningRefused("A13_REVISION_REQUIRED")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            row = self._db.execute(
                "SELECT * FROM a13_provision WHERE engine_id=?", (engine_id,),
            ).fetchone()
            if (row is None or row["revision"] != expected_revision
                    or row["status"] not in required):
                raise ProvisioningRefused("A13_INVALID_TRANSITION")
            self._db.execute(
                "UPDATE a13_provision SET status=?,revision=revision+1 "
                "WHERE engine_id=? AND revision=?",
                (next_state, engine_id, expected_revision),
            )
            self._event(engine_id, event, expected_revision + 1)
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        return self.get(engine_id)

    def suspend(self, engine_id: str, *, expected_revision: int) -> ProvisioningRecord:
        return self._transition(
            engine_id, expected_revision=expected_revision,
            required=frozenset({"PREPARED", "OFFLINE_VERIFIED"}),
            next_state="SUSPENDED", event="SUSPEND",
        )

    def retire(self, engine_id: str, *, expected_revision: int) -> ProvisioningRecord:
        return self._transition(
            engine_id, expected_revision=expected_revision,
            required=frozenset({"SUSPENDED"}),
            next_state="RETIRED", event="RETIRE",
        )
