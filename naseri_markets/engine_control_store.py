"""Unified NON-PRODUCTION engine controls for the new Multi Market Trading UI.

Brooks: built-in engine reference, existing frozen legacy logic NOT loaded.
Owner Custom: an optional private LOCAL metadata reference, invisible to
non-owner admins and all public listings; no proprietary source or plugin.
Public Custom: delegates actual PAPER permissions to TrustedLocalCustomHost.
Settings and destinations are per-engine, with OFF/PAPER only, never LIVE.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .trusted_custom import LocalCustomRefused, TrustedLocalCustomHost

BROOKS_ENGINE_ID = "brooks_price_action"
OWNER_CORE_ID = "ny_first_reversal"  # reserved identity only; NO private source
TIMEFRAMES = ("1m", "5m", "15m", "1h", "4h", "1d")
MARKET_SCOPES = ("all", "crypto", "forex", "index", "metal")
SIGNAL_ENVS = ("OFF", "PAPER")
_NONPUBLIC = "OWNER_CUSTOM"


@dataclass(frozen=True, slots=True)
class ManagedEngine:
    engine_id: str
    engine_version: str
    descriptor_sha256: str
    revision: int
    enabled: bool
    requested_enabled: bool
    engine_kind: str
    runtime_status: str


class EngineControlStore:
    """One local SQLite database with the executable public Custom host.

    Known built-in engine metadata != runtime adapter. Requested enabled on
    Brooks or owner custom is only an operator preference, never execution.
    """

    def __init__(self, state_dir: str | Path, *, owner_visible: bool = False):
        if type(owner_visible) is not bool:
            raise LocalCustomRefused("ENGINE_OWNER_SCOPE_REQUIRED")
        self.host = TrustedLocalCustomHost(state_dir)
        self._db = self.host._db
        self.owner_visible = owner_visible
        self._db.execute("""CREATE TABLE IF NOT EXISTS managed_engine_refs(
            engine_id TEXT PRIMARY KEY, engine_kind TEXT NOT NULL
              CHECK(engine_kind IN ('BUILTIN_BROOKS','OWNER_CUSTOM')),
            requested_enabled INTEGER NOT NULL DEFAULT 0
              CHECK(requested_enabled IN (0,1)),
            revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>=1)
        )""")
        self._db.execute("""CREATE TABLE IF NOT EXISTS managed_engine_preferences(
            engine_id TEXT PRIMARY KEY,
            timeframe TEXT NOT NULL DEFAULT '15m',
            market_scope TEXT NOT NULL DEFAULT 'all',
            signal_environment TEXT NOT NULL DEFAULT 'PAPER'
              CHECK(signal_environment IN ('OFF','PAPER')),
            revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>=1)
        )""")
        self._db.execute("""CREATE TABLE IF NOT EXISTS managed_engine_publication(
            engine_id TEXT PRIMARY KEY,
            requested_publication INTEGER NOT NULL DEFAULT 0
              CHECK(requested_publication IN (0,1)),
            revision INTEGER NOT NULL DEFAULT 1 CHECK(revision>=1)
        )""")
        self._db.execute("""CREATE TABLE IF NOT EXISTS managed_engine_routes(
            engine_id TEXT PRIMARY KEY,
            channel_id INTEGER,
            channel_title TEXT NOT NULL DEFAULT '',
            verification TEXT NOT NULL DEFAULT 'NOT_CONFIGURED',
            delivery_mode TEXT NOT NULL DEFAULT 'DISABLED'
              CHECK(delivery_mode='DISABLED')
        )""")
        self._db.execute("""INSERT OR IGNORE INTO managed_engine_refs
            (engine_id,engine_kind,requested_enabled,revision)
            VALUES(?,'BUILTIN_BROOKS',0,1)""", (BROOKS_ENGINE_ID,))
        self._db.execute("""INSERT OR IGNORE INTO managed_engine_preferences
            (engine_id,signal_environment) VALUES(?, 'OFF')""",
            (BROOKS_ENGINE_ID,))

    def close(self):
        self.host.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, tb):
        self.close()

    def register_owner_reference(self, *, engine_id: str, actor_id: int) -> None:
        """Private operator-provisioned metadata only; never installs code."""
        if (not self.owner_visible or engine_id != OWNER_CORE_ID
                or type(actor_id) is not int or actor_id <= 0):
            raise LocalCustomRefused("ENGINE_OWNER_ONLY_REFERENCE_DENIED")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            self._db.execute("""INSERT OR IGNORE INTO managed_engine_refs
                (engine_id,engine_kind,requested_enabled,revision)
                VALUES(?,'OWNER_CUSTOM',0,1)""", (engine_id,))
            self._db.execute("""INSERT OR IGNORE INTO managed_engine_preferences
                (engine_id,signal_environment) VALUES(?,'OFF')""", (engine_id,))
            self._db.execute("INSERT INTO custom_admin_audit "
                "(engine_id,actor_id,action,engine_revision) VALUES(?,?,?,1)",
                (engine_id, actor_id, "OWNER_PRIVATE_REFERENCE_INSPECTED"))
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise

    def _references(self):
        return self._db.execute(
            "SELECT * FROM managed_engine_refs ORDER BY engine_id").fetchall()

    def list(self) -> tuple[ManagedEngine, ...]:
        result = []
        for item in self._references():
            if item["engine_kind"] == _NONPUBLIC and not self.owner_visible:
                continue
            result.append(ManagedEngine(
                item["engine_id"], "legacy-reference" if
                item["engine_kind"] == "BUILTIN_BROOKS" else "private-reference",
                "", item["revision"], False, bool(item["requested_enabled"]),
                item["engine_kind"], "RUNTIME_NOT_MOUNTED"))
        for item in self.host.list():
            result.append(ManagedEngine(
                item.engine_id, item.engine_version, item.descriptor_sha256,
                item.revision, item.enabled, item.enabled, "PUBLIC_CUSTOM",
                "TRUSTED_LOCAL_PAPER" if item.enabled else "DISABLED"))
        return tuple(sorted(result, key=lambda x: x.engine_id))

    def get(self, engine_id: str) -> ManagedEngine | None:
        return next((item for item in self.list() if item.engine_id == engine_id), None)

    def _require(self, engine_id: str) -> ManagedEngine:
        state = self.get(engine_id)
        if state is None:
            raise LocalCustomRefused("ENGINE_UNKNOWN_OR_PRIVATE")
        return state

    def preferences(self, engine_id: str) -> dict:
        state = self._require(engine_id)
        row = self._db.execute(
            "SELECT * FROM managed_engine_preferences WHERE engine_id=?",
            (engine_id,)).fetchone()
        return {
            "engine_id": engine_id, "timeframe": row["timeframe"] if row else "15m",
            "market_scope": row["market_scope"] if row else "all",
            "signal_environment": row["signal_environment"] if row else "PAPER",
            "revision": row["revision"] if row else 0,
            "timeframe_runtime_applied": False,
            "runtime_connected": state.engine_kind == "PUBLIC_CUSTOM",
            "live_trading_permitted": False,
        }

    def change_preference(self, engine_id: str, *, field: str, value: str,
                          expected_revision: int, actor_id: int) -> dict:
        options = {
            "timeframe": TIMEFRAMES, "market_scope": MARKET_SCOPES,
            "signal_environment": SIGNAL_ENVS,
        }
        if (field not in options or type(value) is not str
                or value not in options[field]
                or type(expected_revision) is not int
                or type(actor_id) is not int or actor_id <= 0):
            raise LocalCustomRefused("ENGINE_SETTING_ALLOWLIST_REQUIRED")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            state = self._require(engine_id)
            existing = self._db.execute(
                "SELECT * FROM managed_engine_preferences WHERE engine_id=?",
                (engine_id,)).fetchone()
            version = existing["revision"] if existing else 0
            if version != expected_revision:
                raise LocalCustomRefused("ENGINE_STALE_SETTING_REVISION")
            if existing is None:
                self._db.execute(
                    "INSERT INTO managed_engine_preferences(engine_id) VALUES(?)",
                    (engine_id,))
            # Column is selected from a constant internal allowlist.
            self._db.execute(
                f"UPDATE managed_engine_preferences SET {field}=?,"
                " revision=revision+1 WHERE engine_id=?", (value, engine_id))
            self._db.execute(
                "INSERT INTO custom_admin_audit "
                "(engine_id,actor_id,action,engine_revision) VALUES(?,?,?,?)",
                (engine_id, actor_id, "SETTING_" + field.upper(), state.revision))
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        return self.preferences(engine_id)

    def toggle_as_admin(self, engine_id: str, *, enabled: bool,
                        expected_revision: int, actor_id: int,
                        descriptor_sha256: str | None = None) -> ManagedEngine:
        state = self._require(engine_id)
        if state.engine_kind == "PUBLIC_CUSTOM":
            self.host.toggle_as_admin(
                engine_id, enabled=enabled, expected_revision=expected_revision,
                actor_id=actor_id, descriptor_sha256=descriptor_sha256)
            return self._require(engine_id)
        if (type(enabled) is not bool or type(expected_revision) is not int
                or type(actor_id) is not int or actor_id <= 0):
            raise LocalCustomRefused("ENGINE_EXPLICIT_ADMIN_REQUIRED")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            row = self._db.execute(
                "SELECT revision FROM managed_engine_refs WHERE engine_id=?",
                (engine_id,)).fetchone()
            if row is None or row["revision"] != expected_revision:
                raise LocalCustomRefused("ENGINE_STALE_REVISION")
            self._db.execute(
                "UPDATE managed_engine_refs "
                "SET requested_enabled=?,revision=revision+1 WHERE engine_id=?",
                (int(enabled), engine_id))
            self._db.execute(
                "INSERT INTO custom_admin_audit "
                "(engine_id,actor_id,action,engine_revision) VALUES(?,?,?,?)",
                (engine_id, actor_id, "REQUEST_ENABLE_NOT_CONNECTED" if enabled
                 else "REQUEST_DISABLE_NOT_CONNECTED", expected_revision + 1))
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        return self._require(engine_id)

    def route(self, engine_id: str) -> dict:
        self._require(engine_id)
        if self.host.get(engine_id) is not None:
            return self.host.route(engine_id)
        row = self._db.execute(
            "SELECT * FROM managed_engine_routes WHERE engine_id=?",
            (engine_id,)).fetchone()
        return {
            "engine_id": engine_id,
            "channel_id": row["channel_id"] if row else None,
            "channel_title": row["channel_title"] if row else "",
            "channel_verification": row["verification"] if row else "NOT_CONFIGURED",
            "delivery_mode": "DISABLED",
            "paper_admin_preview_only": True, "live_publication_enabled": False,
        }

    def set_route(self, engine_id: str, *, channel_id: int,
                  channel_title: str, actor_id: int,
                  verified_private_channel: bool) -> dict:
        self._require(engine_id)
        if self.host.get(engine_id) is not None:
            return self.host.set_route(
                engine_id, channel_id=channel_id, channel_title=channel_title,
                actor_id=actor_id,
                verified_private_channel=verified_private_channel)
        if (type(channel_id) is not int or channel_id >= 0
                or type(actor_id) is not int or actor_id <= 0
                or type(channel_title) is not str or not 0 < len(channel_title) <= 160
                or verified_private_channel is not True):
            raise LocalCustomRefused("ENGINE_PRIVATE_CHANNEL_PROOF_REQUIRED")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            self._db.execute("""INSERT INTO managed_engine_routes
                (engine_id,channel_id,channel_title,verification,delivery_mode)
                VALUES(?,?,?,'PRIVATE_VERIFIED_AT_CONFIGURATION','DISABLED')
                ON CONFLICT(engine_id) DO UPDATE SET
                channel_id=excluded.channel_id,
                channel_title=excluded.channel_title,
                verification=excluded.verification,delivery_mode='DISABLED'""",
                (engine_id, channel_id, channel_title))
            self._db.execute(
                "INSERT INTO custom_admin_audit "
                "(engine_id,actor_id,action,engine_revision) VALUES(?,?,?,?)",
                (engine_id, actor_id, "SET_DISABLED_ROUTE",
                 self._require(engine_id).revision))
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        return self.route(engine_id)

    def clear_route(self, engine_id: str, *, actor_id: int) -> dict:
        self._require(engine_id)
        if self.host.get(engine_id) is not None:
            return self.host.clear_route(engine_id, actor_id=actor_id)
        if type(actor_id) is not int or actor_id <= 0:
            raise LocalCustomRefused("ENGINE_ADMIN_ACTOR_REQUIRED")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            self._db.execute("DELETE FROM managed_engine_routes WHERE engine_id=?",
                             (engine_id,))
            self._db.execute(
                "INSERT INTO custom_admin_audit "
                "(engine_id,actor_id,action,engine_revision) VALUES(?,?,?,?)",
                (engine_id, actor_id, "CLEAR_DISABLED_ROUTE",
                 self._require(engine_id).revision))
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        return self.route(engine_id)

    def publication(self, engine_id: str) -> dict:
        state = self._require(engine_id)
        row = self._db.execute(
            "SELECT requested_publication,revision FROM managed_engine_publication "
            "WHERE engine_id=?", (engine_id,)).fetchone()
        requested = bool(row["requested_publication"]) if row else False
        return {
            "engine_id": engine_id,
            "requested_publication": requested,
            "revision": row["revision"] if row else 0,
            "effective_publication": False,
            "runtime_connected": state.runtime_status != "RUNTIME_NOT_MOUNTED",
            "reason": "NO_AUTHENTICATED_FORWARD_PUBLISHER",
        }

    def request_publication(self, engine_id: str, *, enabled: bool,
                            expected_revision: int, actor_id: int) -> dict:
        state = self._require(engine_id)
        if (state.engine_kind != "BUILTIN_BROOKS"
                or type(enabled) is not bool
                or type(expected_revision) is not int
                or type(actor_id) is not int or actor_id <= 0):
            raise LocalCustomRefused("ENGINE_PUBLICATION_PERMISSION_DENIED")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            row = self._db.execute(
                "SELECT revision FROM managed_engine_publication WHERE engine_id=?",
                (engine_id,)).fetchone()
            revision = row["revision"] if row else 0
            if revision != expected_revision:
                raise LocalCustomRefused("ENGINE_STALE_PUBLICATION_REVISION")
            if row is None:
                self._db.execute(
                    "INSERT INTO managed_engine_publication "
                    "(engine_id,requested_publication,revision) VALUES(?,?,1)",
                    (engine_id, int(enabled)))
            else:
                self._db.execute(
                    "UPDATE managed_engine_publication "
                    "SET requested_publication=?,revision=revision+1 "
                    "WHERE engine_id=?", (int(enabled), engine_id))
            self._db.execute(
                "INSERT INTO custom_admin_audit "
                "(engine_id,actor_id,action,engine_revision) VALUES(?,?,?,?)",
                (engine_id, actor_id,
                 "REQUEST_PUBLICATION_ENABLE_NOT_CONNECTED" if enabled
                 else "REQUEST_PUBLICATION_DISABLE", state.revision))
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        return self.publication(engine_id)

    def signals(self, engine_id: str) -> list[dict]:
        state = self._require(engine_id)
        return self.host.signals(engine_id) if state.engine_kind == "PUBLIC_CUSTOM" else []

    def admin_history(self, engine_id: str) -> list[dict]:
        self._require(engine_id)
        return [dict(row) for row in self._db.execute(
            "SELECT actor_id,action,engine_revision,created_at "
            "FROM custom_admin_audit WHERE engine_id=? "
            "ORDER BY audit_id DESC LIMIT 30", (engine_id,))]
