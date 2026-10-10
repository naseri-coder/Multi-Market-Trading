"""A8 durable engine settings: no plugin downloader, loader, credentials or network.

Registering means METADATA ON FILE, not executable installation. Enabled
means approved for this offline PAPER demo only, never live or publish.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .delivery_ledger import open_sqlite
from .plugin_descriptor import parse_descriptor


class RevisionConflict(ValueError):
    """Concurrent settings modification; refresh state before retry."""


class PluginConflict(ValueError):
    """Existing engine ID belongs to different immutable plugin metadata."""


@dataclass(frozen=True, slots=True)
class PluginState:
    engine_id: str
    engine_version: str
    visibility: str
    adapter: str
    markets: frozenset[str]
    digest: str
    enabled: bool
    revision: int
    status: str


class PluginManager:
    """One SQLite file per operator-owned installation, explicitly supplied.

    No self-approval: caller must independently acquire an approved digest.
    A matching pin is NOT a signature or proof of licensing.
    """

    def __init__(self, path: str | Path) -> None:
        path = Path(path)
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError("A8_SETTINGS_FILE_UNSAFE")
        self._db = open_sqlite(path)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS a8_plugins (
                engine_id TEXT PRIMARY KEY,
                engine_version TEXT NOT NULL,
                publisher TEXT NOT NULL,
                visibility TEXT NOT NULL,
                adapter TEXT NOT NULL,
                markets TEXT NOT NULL,
                digest TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 0 CHECK(enabled IN (0, 1)),
                revision INTEGER NOT NULL DEFAULT 1 CHECK(revision >= 1)
            )
        """)
        # Persistent tombstones stop a removed/re-registered engine from
        # reusing revision 1 (the ABA race with async dispatch).
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS a9_plugin_tombstones (
                engine_id TEXT PRIMARY KEY,
                last_revision INTEGER NOT NULL CHECK(last_revision >= 1),
                last_digest TEXT NOT NULL,
                removed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)

    def close(self) -> None:
        self._db.close()

    @staticmethod
    def _state(row: sqlite3.Row) -> PluginState:
        visibility = row["visibility"]
        return PluginState(
            engine_id=row["engine_id"],
            engine_version=row["engine_version"],
            visibility=visibility,
            adapter=row["adapter"],
            markets=frozenset(row["markets"].split(",")),
            digest=row["digest"],
            enabled=bool(row["enabled"]),
            revision=row["revision"],
            status=(
                "OFFLINE_PAPER_ENABLED" if row["enabled"]
                else "PRIVATE_PROVISIONING_REQUIRED" if visibility == "private"
                else "OFFLINE_PAPER_DISABLED"
            ),
        )

    def incarnation(self, engine_id: str) -> int:
        """Stable install generation, advancing across deletion/re-registration.

        Consulted by the paper dispatch guard; no actual plugin is loaded.
        """
        row = self._db.execute(
            "SELECT last_revision FROM a9_plugin_tombstones WHERE engine_id=?",
            (engine_id,),
        ).fetchone()
        return int(row["last_revision"]) if row is not None else 0

    def get(self, engine_id: str) -> PluginState | None:
        row = self._db.execute(
            "SELECT * FROM a8_plugins WHERE engine_id=?", (engine_id,)
        ).fetchone()
        return self._state(row) if row is not None else None

    def list(self) -> tuple[PluginState, ...]:
        rows = self._db.execute(
            "SELECT * FROM a8_plugins ORDER BY engine_id"
        ).fetchall()
        return tuple(self._state(row) for row in rows)

    def register(self, raw: bytes, *, approved_sha256: str) -> PluginState:
        """Persist a pinned descriptor; ALL newly registered plugins are OFF."""
        descriptor = parse_descriptor(raw, approved_sha256=approved_sha256)
        self._db.execute("BEGIN IMMEDIATE")
        try:
            row = self._db.execute(
                "SELECT * FROM a8_plugins WHERE engine_id=?",
                (descriptor.engine_id,),
            ).fetchone()
            if row is not None:
                if row["digest"] != descriptor.digest:
                    raise PluginConflict("A8_PLUGIN_CHANGE_REQUIRES_DISABLED_REPLACEMENT")
            else:
                # Tombstone revision is monotonic even across unregistration.
                # Never execute a callback or recover a previous enable state.
                tombstone = self._db.execute(
                    "SELECT last_revision FROM a9_plugin_tombstones "
                    "WHERE engine_id=?", (descriptor.engine_id,),
                ).fetchone()
                next_revision = (
                    tombstone["last_revision"] + 1 if tombstone is not None else 1
                )
                self._db.execute(
                    "INSERT INTO a8_plugins("
                    "engine_id,engine_version,publisher,visibility,adapter,"
                    "markets,digest,enabled,revision) VALUES(?,?,?,?,?,?,?,0,?)",
                    (
                        descriptor.engine_id, descriptor.engine_version,
                        descriptor.publisher, descriptor.visibility, descriptor.adapter,
                        ",".join(sorted(m.value for m in descriptor.markets)),
                        descriptor.digest, next_revision,
                    ),
                )
            row = self._db.execute(
                "SELECT * FROM a8_plugins WHERE engine_id=?",
                (descriptor.engine_id,),
            ).fetchone()
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        return self._state(row)

    def set_enabled(
        self, engine_id: str, *, enabled: bool, expected_revision: int
    ) -> PluginState:
        """CAS toggle for offline PAPER dispatch; no real engine activation."""
        if type(enabled) is not bool:
            raise ValueError("A8_EXPLICIT_BOOLEAN_REQUIRED")
        if type(expected_revision) is not int or expected_revision < 1:
            raise ValueError("A8_REVISION_REQUIRED")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            row = self._db.execute(
                "SELECT * FROM a8_plugins WHERE engine_id=?", (engine_id,)
            ).fetchone()
            if row is None:
                raise ValueError("A8_PLUGIN_NOT_REGISTERED")
            if row["revision"] != expected_revision:
                raise RevisionConflict("A8_STALE_SETTINGS_REVISION")
            if bool(row["enabled"]) != enabled:
                self._db.execute(
                    "UPDATE a8_plugins SET enabled=?, revision=revision+1 "
                    "WHERE engine_id=? AND revision=?",
                    (int(enabled), engine_id, expected_revision),
                )
            updated = self._db.execute(
                "SELECT * FROM a8_plugins WHERE engine_id=?", (engine_id,)
            ).fetchone()
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        return self._state(updated)

    def replace(
        self, raw: bytes, *, approved_sha256: str, expected_revision: int
    ) -> PluginState:
        """Version/owner/visibility changes require an explicitly disabled plugin."""
        descriptor = parse_descriptor(raw, approved_sha256=approved_sha256)
        if type(expected_revision) is not int or expected_revision < 1:
            raise ValueError("A8_REVISION_REQUIRED")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            row = self._db.execute(
                "SELECT * FROM a8_plugins WHERE engine_id=?",
                (descriptor.engine_id,),
            ).fetchone()
            if row is None or row["revision"] != expected_revision:
                raise RevisionConflict("A8_STALE_OR_MISSING_PLUGIN")
            if row["enabled"]:
                raise PluginConflict("A8_DISABLE_BEFORE_REPLACEMENT")
            self._db.execute(
                "UPDATE a8_plugins SET engine_version=?,publisher=?,visibility=?,"
                "adapter=?,markets=?,digest=?,revision=revision+1 "
                "WHERE engine_id=? AND revision=?",
                (
                    descriptor.engine_version, descriptor.publisher,
                    descriptor.visibility, descriptor.adapter,
                    ",".join(sorted(m.value for m in descriptor.markets)),
                    descriptor.digest, descriptor.engine_id, expected_revision,
                ),
            )
            updated = self._db.execute(
                "SELECT * FROM a8_plugins WHERE engine_id=?",
                (descriptor.engine_id,),
            ).fetchone()
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        return self._state(updated)

    def unregister(self, engine_id: str, *, expected_revision: int) -> int:
        """Remove only DISABLED plugin metadata, never installed strategy files.

        Atomically store a monotonic revision fence for re-registration.
        This does not delete PAPER observations or the independent audit log.
        """
        if type(expected_revision) is not int or expected_revision < 1:
            raise ValueError("A9_REVISION_REQUIRED")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            row = self._db.execute(
                "SELECT * FROM a8_plugins WHERE engine_id=?", (engine_id,)
            ).fetchone()
            if row is None or row["revision"] != expected_revision:
                raise RevisionConflict("A9_STALE_OR_MISSING_PLUGIN")
            if row["enabled"]:
                raise PluginConflict("A9_DISABLE_BEFORE_UNREGISTER")
            fence = row["revision"] + 1
            self._db.execute(
                "INSERT INTO a9_plugin_tombstones("
                "engine_id,last_revision,last_digest,removed_at) "
                "VALUES(?,?,?,CURRENT_TIMESTAMP) "
                "ON CONFLICT(engine_id) DO UPDATE SET "
                "last_revision=excluded.last_revision,"
                "last_digest=excluded.last_digest,"
                "removed_at=CURRENT_TIMESTAMP",
                (engine_id, fence, row["digest"]),
            )
            self._db.execute(
                "DELETE FROM a8_plugins WHERE engine_id=? AND revision=?",
                (engine_id, expected_revision),
            )
            self._db.execute("COMMIT")
            return fence
        except BaseException:
            self._db.execute("ROLLBACK")
            raise

    def allowed_paper_engines(self) -> dict[str, PluginState]:
        """Read for EACH input tick: disabled engines are not dispatched."""
        return {row.engine_id: row for row in self.list() if row.enabled}
