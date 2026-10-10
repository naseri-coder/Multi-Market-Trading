"""Trusted, LOCAL public Custom Python engine host for offline PAPER/replay.

This is genuine operator-approved code execution, NOT a sandbox: a trusted
Python file runs with the invoking user's OS privileges. No public marketplace,
remote download, Telegram, live feeds, broker orders or private NYFR support.
A21 remains metadata-only; a separate explicit operator decision authorizes
LOCAL public script execution. Never interpret this as A24/A25 entitlement.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import stat
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from .a21_custom_contract import parse_custom_contract
from .contracts import Instrument, Market
from .delivery_ledger import IdentityConflict, _wire_intent, open_sqlite
from .external_abi import parse_paper_envelope
from .quotes import QuoteOrigin, QuoteQualityGate, QuoteTick, QuoteVerdict

MAX_SOURCE = 32768
MAX_DESCRIPTOR = 4096
MAX_PACKET = 8192
MAX_QUOTE = 2048
TRUST_ACK = "I_TRUST_THIS_LOCAL_PYTHON_CODE"


class LocalCustomRefused(ValueError):
    """Explicit trust, identity, PAPER, source or revision requirement failed."""


@dataclass(frozen=True, slots=True)
class LocalCustomState:
    engine_id: str
    engine_version: str
    descriptor_sha256: str
    code_sha256: str
    enabled: bool
    revision: int
    mode: str = "TRUSTED_LOCAL_PAPER_ONLY"
    sandboxed: bool = False
    publisher_authenticated: bool = False
    live_trading_permitted: bool = False


def _read_file(path: str | Path, maximum: int) -> bytes:
    name = Path(path).absolute()
    if name.is_symlink() or not name.is_file():
        raise LocalCustomRefused("CUSTOM_SOURCE_MUST_BE_REGULAR_FILE")
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(name, flags)
        with os.fdopen(fd, "rb") as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= maximum:
                raise LocalCustomRefused("CUSTOM_FILE_BOUNDS")
            data = source.read(maximum + 1)
    except OSError as exc:
        raise LocalCustomRefused("CUSTOM_SOURCE_UNREADABLE") from exc
    if not 0 < len(data) <= maximum:
        raise LocalCustomRefused("CUSTOM_FILE_BOUNDS")
    return data


def parse_offline_quote(raw: bytes) -> QuoteTick:
    """Strict public input: one timestamped synthetic/replay Bid/Ask quote."""
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_QUOTE:
        raise LocalCustomRefused("CUSTOM_QUOTE_BOUNDS")
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise LocalCustomRefused("CUSTOM_DUPLICATE_QUOTE_FIELD")
            result[key] = value
        return result
    try:
        obj = json.loads(raw.decode("utf-8"), object_pairs_hook=unique,
                         parse_constant=lambda _: (_ for _ in ()).throw(
                             LocalCustomRefused("CUSTOM_NONFINITE_QUOTE")))
    except (UnicodeError, ValueError) as exc:
        raise LocalCustomRefused("CUSTOM_QUOTE_JSON_INVALID") from exc
    expected = {"market", "provider", "symbol", "timezone", "quote_currency",
                "occurred_at", "bid", "ask", "origin"}
    if type(obj) is not dict or set(obj) != expected:
        raise LocalCustomRefused("CUSTOM_QUOTE_EXACT_FIELDS")
    if any(type(obj[key]) is not str for key in expected):
        raise LocalCustomRefused("CUSTOM_QUOTE_STRING_FIELDS")
    if obj["origin"] not in ("synthetic", "replay"):
        raise LocalCustomRefused("CUSTOM_LIVE_FEED_DENIED")
    if any(not 0 < len(obj[k]) <= 100 for k in
           ("market", "provider", "symbol", "timezone", "quote_currency")):
        raise LocalCustomRefused("CUSTOM_QUOTE_IDENTITY_BOUNDS")
    if any(not 0 < len(obj[k]) <= 64 for k in ("bid", "ask")):
        raise LocalCustomRefused("CUSTOM_QUOTE_PRICE_BOUNDS")
    try:
        tick = QuoteTick(
            Instrument(Market(obj["market"]), obj["provider"], obj["symbol"],
                       obj["timezone"], obj["quote_currency"]),
            datetime.fromisoformat(obj["occurred_at"]), Decimal(obj["bid"]),
            Decimal(obj["ask"]), QuoteOrigin(obj["origin"]))
    except (ValueError, TypeError, ArithmeticError) as exc:
        raise LocalCustomRefused("CUSTOM_QUOTE_INVALID") from exc
    return tick


class TrustedLocalCustomHost:
    """One private local store, atomic engine permission + PAPER journal writes.

    No implicit execution on open; operator must separately register
    SHA-pinned local code and enable it with CAS. Source is snapshotted into
    an operator-private 0700 state directory; only that immutable-byte
    snapshot is executed. A compromised local user can still run arbitrary
    actions: this is trusted code, NEVER an untrusted-code sandbox.
    """

    def __init__(self, state_dir: str | Path):
        root = Path(state_dir).absolute()
        if (not root.is_absolute() or root.is_symlink()
                or (root.exists() and not root.is_dir())
                or not root.parent.is_dir() or root.parent.is_symlink()):
            raise LocalCustomRefused("CUSTOM_EXPLICIT_SAFE_STATE_DIRECTORY")
        if not root.exists():
            root.mkdir(mode=0o700)
        if root.stat().st_mode & 0o077:
            raise LocalCustomRefused("CUSTOM_PRIVATE_STATE_MODE_REQUIRED")
        self.root = root
        self.snapshots = root / "trusted_scripts"
        if not self.snapshots.exists():
            self.snapshots.mkdir(mode=0o700)
        if (self.snapshots.is_symlink() or not self.snapshots.is_dir()
                or self.snapshots.stat().st_mode & 0o077):
            raise LocalCustomRefused("CUSTOM_PRIVATE_SNAPSHOT_DIRECTORY")
        db_path = root / "custom_paper.db"
        if db_path.is_symlink() or (db_path.exists() and not db_path.is_file()):
            raise LocalCustomRefused("CUSTOM_UNSAFE_DB_PATH")
        if db_path.exists() and db_path.stat().st_mode & 0o077:
            raise LocalCustomRefused("CUSTOM_DB_PRIVATE_MODE")
        self._db = open_sqlite(db_path)
        db_path.chmod(0o600)
        self._db.execute("""CREATE TABLE IF NOT EXISTS local_custom_engines(
            engine_id TEXT PRIMARY KEY,
            engine_version TEXT NOT NULL,
            descriptor BLOB NOT NULL,
            descriptor_sha256 TEXT NOT NULL,
            code_sha256 TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0,1)),
            revision INTEGER NOT NULL CHECK(revision>0))""")
        self._db.execute("""CREATE TABLE IF NOT EXISTS a7_paper_intents(
            engine_id TEXT NOT NULL, signal_id TEXT NOT NULL,
            digest TEXT NOT NULL, payload TEXT NOT NULL,
            PRIMARY KEY(engine_id,signal_id))""")

        self._db.execute("""CREATE TABLE IF NOT EXISTS custom_admin_routes(
            engine_id TEXT PRIMARY KEY REFERENCES local_custom_engines(engine_id),
            channel_id INTEGER,
            channel_title TEXT NOT NULL DEFAULT '',
            verification TEXT NOT NULL DEFAULT 'NOT_CONFIGURED',
            delivery_mode TEXT NOT NULL DEFAULT 'DISABLED'
              CHECK(delivery_mode='DISABLED'))""")
        self._db.execute("""CREATE TABLE IF NOT EXISTS custom_admin_audit(
            audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            engine_id TEXT NOT NULL, actor_id INTEGER NOT NULL,
            action TEXT NOT NULL, engine_revision INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        # Per-engine PAPER environment/market preferences are shared with
        # the integrated Telegram panel. The old standalone CLI defaults
        # to PAPER and all markets until the admin explicitly configures it.
        self._db.execute("""CREATE TABLE IF NOT EXISTS managed_engine_preferences(
            engine_id TEXT PRIMARY KEY,
            timeframe TEXT NOT NULL DEFAULT '15m',
            market_scope TEXT NOT NULL DEFAULT 'all',
            signal_environment TEXT NOT NULL DEFAULT 'PAPER'
              CHECK(signal_environment IN ('OFF','PAPER')),
            revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>=1)
        )""")

    def route(self, engine_id: str) -> dict:
        if self.get(engine_id) is None:
            raise LocalCustomRefused("CUSTOM_UNKNOWN_ENGINE")
        row = self._db.execute(
            "SELECT channel_id,channel_title,verification,delivery_mode "
            "FROM custom_admin_routes WHERE engine_id=?", (engine_id,)
        ).fetchone()
        return {
            "engine_id": engine_id,
            "channel_id": row["channel_id"] if row else None,
            "channel_title": row["channel_title"] if row else "",
            "channel_verification": row["verification"] if row else "NOT_CONFIGURED",
            "delivery_mode": "DISABLED",
            "paper_admin_preview_only": True,
            "live_publication_enabled": False,
        }

    def set_route(self, engine_id: str, *, channel_id: int,
                  channel_title: str, actor_id: int,
                  verified_private_channel: bool) -> dict:
        """Save a verified destination as DISABLED (no Telegram sends).

        The caller is responsible for independently verifying Telegram's
        private-channel identity and the bot's admin/post permissions.
        """
        if (type(actor_id) is not int or actor_id <= 0
                or type(channel_id) is not int or channel_id >= 0
                or type(channel_title) is not str
                or not 0 < len(channel_title) <= 160
                or verified_private_channel is not True):
            raise LocalCustomRefused("CUSTOM_PRIVATE_CHANNEL_PROOF_REQUIRED")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            state = self.get(engine_id)
            if state is None:
                raise LocalCustomRefused("CUSTOM_UNKNOWN_ENGINE")
            self._db.execute("""INSERT INTO custom_admin_routes
                (engine_id,channel_id,channel_title,verification,delivery_mode)
                VALUES(?,?,?,'PRIVATE_VERIFIED_AT_CONFIGURATION','DISABLED')
                ON CONFLICT(engine_id) DO UPDATE SET
                channel_id=excluded.channel_id,
                channel_title=excluded.channel_title,
                verification=excluded.verification,
                delivery_mode='DISABLED'""",
                (engine_id, channel_id, channel_title))
            self._db.execute(
                "INSERT INTO custom_admin_audit "
                "(engine_id,actor_id,action,engine_revision) VALUES(?,?,?,?)",
                (engine_id,actor_id,"SET_DISABLED_ROUTE",state.revision))
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        return self.route(engine_id)

    def clear_route(self, engine_id: str, *, actor_id: int) -> dict:
        if type(actor_id) is not int or actor_id <= 0:
            raise LocalCustomRefused("CUSTOM_ADMIN_ACTOR_REQUIRED")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            state = self.get(engine_id)
            if state is None:
                raise LocalCustomRefused("CUSTOM_UNKNOWN_ENGINE")
            self._db.execute(
                "DELETE FROM custom_admin_routes WHERE engine_id=?", (engine_id,))
            self._db.execute(
                "INSERT INTO custom_admin_audit "
                "(engine_id,actor_id,action,engine_revision) VALUES(?,?,?,?)",
                (engine_id,actor_id,"CLEAR_DISABLED_ROUTE",state.revision))
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        return self.route(engine_id)

    def toggle_as_admin(self, engine_id: str, *, enabled: bool,
                        expected_revision: int, actor_id: int,
                        descriptor_sha256: str | None = None) -> LocalCustomState:
        """CAS toggles and audit in one DB transaction; no partial admin logs."""
        if type(actor_id) is not int or actor_id <= 0:
            raise LocalCustomRefused("CUSTOM_ADMIN_ACTOR_REQUIRED")
        # toggle() owns BEGIN IMMEDIATE, so integrate the audit in its
        # existing transaction instead of a second transaction.
        return self.toggle(
            engine_id, enabled=enabled, expected_revision=expected_revision,
            descriptor_sha256=descriptor_sha256, admin_actor_id=actor_id)

    def admin_history(self, engine_id: str) -> list[dict]:
        if self.get(engine_id) is None:
            raise LocalCustomRefused("CUSTOM_UNKNOWN_ENGINE")
        return [dict(row) for row in self._db.execute(
            "SELECT actor_id,action,engine_revision,created_at "
            "FROM custom_admin_audit WHERE engine_id=? "
            "ORDER BY audit_id DESC LIMIT 30", (engine_id,))]

    def close(self) -> None:
        self._db.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    @staticmethod
    def _state(row: sqlite3.Row) -> LocalCustomState:
        return LocalCustomState(row["engine_id"], row["engine_version"],
                                row["descriptor_sha256"], row["code_sha256"],
                                bool(row["enabled"]), row["revision"])

    def get(self, engine_id: str) -> LocalCustomState | None:
        row = self._db.execute(
            "SELECT * FROM local_custom_engines WHERE engine_id=?",
            (engine_id,)).fetchone()
        return self._state(row) if row else None

    def list(self) -> tuple[LocalCustomState, ...]:
        return tuple(self._state(row) for row in self._db.execute(
            "SELECT * FROM local_custom_engines ORDER BY engine_id"))

    def register(self, descriptor_path: str | Path, code_path: str | Path, *,
                 descriptor_sha256: str, code_sha256: str, trust_ack: str
                 ) -> LocalCustomState:
        if trust_ack != TRUST_ACK:
            raise LocalCustomRefused("CUSTOM_EXPLICIT_TRUST_CONFIRMATION")
        descriptor = _read_file(descriptor_path, MAX_DESCRIPTOR)
        code = _read_file(code_path, MAX_SOURCE)
        contract = parse_custom_contract(descriptor,
                                         approved_sha256=descriptor_sha256)
        if (contract.access_policy != "public_custom"
                or contract.strategy_family != "generic_custom"
                or contract.protected_owner_core):
            raise LocalCustomRefused("CUSTOM_OWNER_PRIVATE_NEVER_PUBLIC")
        if (type(code_sha256) is not str or len(code_sha256) != 64
                or not all(c in "0123456789abcdef" for c in code_sha256)
                or not hmac.compare_digest(hashlib.sha256(code).hexdigest(),
                                           code_sha256)):
            raise LocalCustomRefused("CUSTOM_INDEPENDENT_CODE_PIN_REQUIRED")
        # Non-executable metadata from A21 does NOT authorize a code install;
        # this is a different, explicit, trusted-LOCAL operator decision.
        # Refuse obvious owner-private branding; content classification cannot
        # prove the absence of confidential code in arbitrary trusted scripts.
        try:
            lowered = code.decode("utf-8", errors="strict").lower()
        except UnicodeError as exc:
            raise LocalCustomRefused("CUSTOM_UTF8_PYTHON_REQUIRED") from exc
        if any(key in lowered for key in
               ("ny_first_reversal", "private_nyfr_core", "r0_engine")):
            raise LocalCustomRefused("CUSTOM_PROTECTED_OWNER_CORE_DENIED")
        snapshot = self.snapshots / f"{contract.engine_id}-{code_sha256}.py"
        if snapshot.exists() or snapshot.is_symlink():
            if not hmac.compare_digest(
                    hashlib.sha256(_read_file(snapshot, MAX_SOURCE)).hexdigest(),
                    code_sha256):
                raise LocalCustomRefused("CUSTOM_SNAPSHOT_COLLISION")
        else:
            try:
                fd = os.open(snapshot, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as target:
                    target.write(code)
                    target.flush()
                    os.fsync(target.fileno())
            except OSError as exc:
                raise LocalCustomRefused("CUSTOM_SNAPSHOT_WRITE_FAILED") from exc
        self._db.execute("BEGIN IMMEDIATE")
        try:
            if self.get(contract.engine_id) is not None:
                raise LocalCustomRefused("CUSTOM_DUPLICATE_REGISTRATION")
            self._db.execute(
                "INSERT INTO local_custom_engines VALUES(?,?,?,?,?,0,1)",
                (contract.engine_id, contract.engine_version, descriptor,
                 descriptor_sha256, code_sha256))
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        return self.get(contract.engine_id)

    def toggle(self, engine_id: str, *, enabled: bool, expected_revision: int,
               descriptor_sha256: str | None = None,
               admin_actor_id: int | None = None) -> LocalCustomState:
        if (type(enabled) is not bool or type(expected_revision) is not int):
            raise LocalCustomRefused("CUSTOM_EXACT_CAS_REQUIRED")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            state = self.get(engine_id)
            if state is None or state.revision != expected_revision:
                raise LocalCustomRefused("CUSTOM_STALE_REVISION")
            if enabled and (type(descriptor_sha256) is not str
                            or not hmac.compare_digest(
                                state.descriptor_sha256, descriptor_sha256)):
                raise LocalCustomRefused("CUSTOM_PIN_TO_ENABLE_REQUIRED")
            self._db.execute(
                "UPDATE local_custom_engines SET enabled=?,revision=revision+1 "
                "WHERE engine_id=?", (int(enabled), engine_id))
            if admin_actor_id is not None:
                self._db.execute(
                    "INSERT INTO custom_admin_audit "
                    "(engine_id,actor_id,action,engine_revision) VALUES(?,?,?,?)",
                    (engine_id,admin_actor_id,
                     "ENABLE_PAPER" if enabled else "DISABLE_PAPER",
                     state.revision + 1))
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        return self.get(engine_id)

    def _quarantine(self, engine_id: str, revision: int) -> None:
        self._db.execute(
            "UPDATE local_custom_engines SET enabled=0,revision=revision+1 "
            "WHERE engine_id=? AND enabled=1 AND revision=?",
            (engine_id, revision))

    def _check_paper_preferences(self, engine_id: str, market: str) -> None:
        row = self._db.execute(
            "SELECT signal_environment,market_scope "
            "FROM managed_engine_preferences WHERE engine_id=?",
            (engine_id,)).fetchone()
        if row is not None:
            if row["signal_environment"] != "PAPER":
                raise LocalCustomRefused("CUSTOM_PAPER_ENVIRONMENT_DISABLED")
            if row["market_scope"] not in ("all", market):
                raise LocalCustomRefused("CUSTOM_MARKET_SCOPE_BLOCKED")

    def paper(self, engine_id: str, quote_json: bytes, *, timeout_seconds: float = 2.0
              ) -> dict:
        if not 0 < timeout_seconds <= 5:
            raise LocalCustomRefused("CUSTOM_BOUNDED_TIMEOUT_REQUIRED")
        tick = parse_offline_quote(quote_json)
        state = self.get(engine_id)
        if state is None or not state.enabled:
            raise LocalCustomRefused("CUSTOM_ENGINE_DISABLED")
        row = self._db.execute(
            "SELECT descriptor FROM local_custom_engines WHERE engine_id=?",
            (engine_id,)).fetchone()
        contract = parse_custom_contract(
            row["descriptor"], approved_sha256=state.descriptor_sha256)
        if (contract.engine_id != engine_id or tick.instrument.market not in
                contract.markets):
            raise LocalCustomRefused("CUSTOM_CONTRACT_MARKET_DENIED")
        if QuoteQualityGate().inspect(
                tick, now=tick.occurred_at) is not QuoteVerdict.ACCEPTED:
            raise LocalCustomRefused("CUSTOM_QUOTE_REJECTED")
        self._check_paper_preferences(engine_id, tick.instrument.market.value)
        snapshot = self.snapshots / f"{engine_id}-{state.code_sha256}.py"
        script = _read_file(snapshot, MAX_SOURCE)
        if not hmac.compare_digest(
                hashlib.sha256(script).hexdigest(), state.code_sha256):
            raise LocalCustomRefused("CUSTOM_SCRIPT_PIN_CHANGED")
        request = {
            "abi_version": 1, "engine_id": engine_id,
            "engine_version": state.engine_version,
            "tick": json.loads(quote_json),
        }
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-S", str(snapshot)],
                input=json.dumps(request, separators=(",", ":")).encode("utf-8"),
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                cwd=self.root, timeout=timeout_seconds, check=False,
                env={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
                     "HOME": str(self.root)},
            )
            if proc.returncode or len(proc.stdout) > MAX_PACKET:
                raise LocalCustomRefused("CUSTOM_WORKER_FAILED_OR_OVERSIZED")
            if proc.stdout.strip() == b'{"status":"no_signal"}':
                signal = None
            else:
                signal = parse_paper_envelope(
                    proc.stdout.strip(), tick, engine_id=engine_id,
                    engine_version=state.engine_version)
        except (subprocess.TimeoutExpired, OSError, ValueError) as exc:
            self._quarantine(engine_id, state.revision)
            raise LocalCustomRefused("CUSTOM_WORKER_QUARANTINED") from exc
        # Re-verify permission and immutability while owning the same SQLite
        # writer lock as the PAPER insert: remote disable cannot race past it.
        self._db.execute("BEGIN IMMEDIATE")
        try:
            current = self.get(engine_id)
            if (current is None or not current.enabled
                    or current.revision != state.revision
                    or current.descriptor_sha256 != state.descriptor_sha256
                    or current.code_sha256 != state.code_sha256):
                raise LocalCustomRefused("CUSTOM_REVOKED_DURING_EXECUTION")
            # Same SQLite writer lock as PAPER insert prevents racing OFF
            # or market-scope changes from allowing an obsolete signal.
            self._check_paper_preferences(engine_id, tick.instrument.market.value)
            inserted = duplicate = 0
            if signal is not None:
                payload = _wire_intent(signal)
                digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
                existing = self._db.execute(
                    "SELECT digest FROM a7_paper_intents WHERE engine_id=? AND signal_id=?",
                    (engine_id, signal.signal_id)).fetchone()
                if existing is not None:
                    if existing["digest"] != digest:
                        raise IdentityConflict("CUSTOM_SIGNAL_IDENTITY_CONFLICT")
                    duplicate = 1
                else:
                    self._db.execute(
                        "INSERT INTO a7_paper_intents VALUES(?,?,?,?)",
                        (engine_id, signal.signal_id, digest, payload))
                    inserted = 1
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        return {
            "mode": "TRUSTED_LOCAL_PAPER_ONLY", "engine_id": engine_id,
            "result": "NO_SIGNAL" if signal is None else (
                "RECORDED" if inserted else "DUPLICATE"),
            "stored": inserted, "duplicate": duplicate,
            "revision": state.revision, "live_trading_permitted": False,
            "telegram_enabled": False, "sandboxed": False,
        }

    def signals(self, engine_id: str | None = None) -> list[dict]:
        if engine_id is not None and self.get(engine_id) is None:
            raise LocalCustomRefused("CUSTOM_UNKNOWN_ENGINE")
        if engine_id is None:
            rows = self._db.execute(
                "SELECT payload FROM a7_paper_intents ORDER BY engine_id,signal_id"
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT payload FROM a7_paper_intents WHERE engine_id=? "
                "ORDER BY signal_id", (engine_id,)).fetchall()
        return [json.loads(row["payload"]) for row in rows]
