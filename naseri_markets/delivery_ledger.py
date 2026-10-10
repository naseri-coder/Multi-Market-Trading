"""A3 persistent intent/outbox journal. No Telegram network API or trade execution.

The application must validate route privacy with a real Telegram API in a later
stage; ChannelRoute booleans alone are configuration, not remote attestation.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .contracts import Market, SignalIntent
from .registry import EngineRegistry
from .routing import ChannelRoute, decide_delivery
from .quotes import _utc


class IdentityConflict(ValueError):
    """An existing engine/signal identity was reused for different content."""


class UnsafeDelivery(RuntimeError):
    """Disallowed channel route or unsafe outbox transition."""


def _wire_intent(intent: SignalIntent) -> str:
    """Stable representation; never store a token or proprietary engine formula."""
    body = {
        "signal_id": intent.signal_id,
        "engine_id": intent.engine_id,
        "engine_version": intent.engine_version,
        "market": intent.instrument.market.value,
        "provider": intent.instrument.provider,
        "symbol": intent.instrument.symbol,
        "timezone": intent.instrument.timezone,
        "quote_currency": intent.instrument.quote_currency,
        "direction": intent.direction.value,
        "observed_at": intent.observed_at.astimezone(timezone.utc).isoformat(),
        "entry": str(intent.entry),
        "stop": str(intent.stop),
        "targets": [str(value) for value in intent.targets],
        "evidence_mode": intent.evidence_mode.value,
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def open_sqlite(path: str | Path) -> sqlite3.Connection:
    """Opens a user-provided persistent file; caller owns its lifecycle and storage."""
    if str(path) == ":memory:":
        raise ValueError("persistent on-disk SQLite path required")
    target = Path(path)
    if not target.parent.is_dir():
        raise ValueError("SQLite parent directory must already exist")
    conn = sqlite3.connect(str(target), isolation_level=None, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


_SCHEMA = """
CREATE TABLE IF NOT EXISTS signal_intents (
    engine_id TEXT NOT NULL,
    signal_id TEXT NOT NULL,
    intent_json TEXT NOT NULL,
    intent_sha256 TEXT NOT NULL,
    market TEXT NOT NULL,
    provider TEXT NOT NULL,
    symbol TEXT NOT NULL,
    PRIMARY KEY (engine_id, signal_id)
);
CREATE TABLE IF NOT EXISTS signal_outbox (
    engine_id TEXT NOT NULL,
    signal_id TEXT NOT NULL,
    channel_id INTEGER NOT NULL CHECK (channel_id < 0),
    state TEXT NOT NULL CHECK (state IN ('PENDING','CLAIMED','SENT','UNKNOWN','EXPIRED')),
    message_id INTEGER,
    PRIMARY KEY (engine_id, signal_id),
    FOREIGN KEY (engine_id, signal_id) REFERENCES signal_intents(engine_id, signal_id),
    CHECK ((state = 'SENT' AND message_id > 0)
           OR (state != 'SENT' AND message_id IS NULL))
);
CREATE INDEX IF NOT EXISTS outbox_state_idx ON signal_outbox(state, engine_id);
"""


@dataclass(frozen=True, slots=True)
class OutboxItem:
    engine_id: str
    signal_id: str
    channel_id: int
    state: str
    message_id: int | None


class SignalLedger:
    """Transactionally stores a signal and its one private delivery intent.

    An unknown delivery is NEVER automatically retried. True exactly-once
    Telegram delivery requires a separate read-back/reconciliation protocol.
    """

    def __init__(self, db_path: str | Path) -> None:
        self._db = open_sqlite(db_path)
        self._db.executescript(_SCHEMA)

    def close(self) -> None:
        self._db.close()

    def record(self, intent: SignalIntent, registry: EngineRegistry,
               route: ChannelRoute) -> bool:
        decision = decide_delivery(intent, registry, route)
        if not decision.allowed or decision.channel_id is None:
            raise UnsafeDelivery(decision.reason)
        raw = _wire_intent(intent)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        self._db.execute("BEGIN IMMEDIATE")
        try:
            current = self._db.execute(
                "SELECT intent_sha256 FROM signal_intents "
                "WHERE engine_id=? AND signal_id=?",
                (intent.engine_id, intent.signal_id),
            ).fetchone()
            if current is not None:
                if current["intent_sha256"] != digest:
                    raise IdentityConflict("same engine/signal ID with different payload")
                item = self.get(intent.engine_id, intent.signal_id)
                if item is None or item.channel_id != decision.channel_id:
                    raise IdentityConflict("signal identity routed to a different channel")
                self._db.execute("COMMIT")
                return False
            self._db.execute(
                "INSERT INTO signal_intents "
                "(engine_id,signal_id,intent_json,intent_sha256,market,provider,symbol) "
                "VALUES (?,?,?,?,?,?,?)",
                (intent.engine_id, intent.signal_id, raw, digest,
                 intent.instrument.market.value, intent.instrument.provider,
                 intent.instrument.symbol),
            )
            self._db.execute(
                "INSERT INTO signal_outbox "
                "(engine_id,signal_id,channel_id,state) VALUES (?,?,?,'PENDING')",
                (intent.engine_id, intent.signal_id, decision.channel_id),
            )
            self._db.execute("COMMIT")
            return True
        except BaseException:
            self._db.execute("ROLLBACK")
            raise

    def get(self, engine_id: str, signal_id: str) -> OutboxItem | None:
        row = self._db.execute(
            "SELECT engine_id,signal_id,channel_id,state,message_id "
            "FROM signal_outbox WHERE engine_id=? AND signal_id=?",
            (engine_id, signal_id),
        ).fetchone()
        return OutboxItem(**dict(row)) if row else None

    def claim(self, engine_id: str, signal_id: str,
              *, route: ChannelRoute, now: datetime,
              max_age_seconds: int = 60) -> OutboxItem | None:
        """Claim before calling an external publisher. No send occurs here.

        Caller must independently validate Telegram channel privacy at time of
        send; this local flag is not a network-based privacy verification.
        """
        if (isinstance(max_age_seconds, bool) or not isinstance(max_age_seconds, int)
                or not 0 < max_age_seconds <= 3600):
            raise ValueError("bounded positive signal freshness limit required")
        current_time = _utc(now)
        self._db.execute("BEGIN IMMEDIATE")
        try:
            row = self._db.execute(
                "SELECT o.channel_id,o.state,i.market,i.intent_json FROM signal_outbox o "
                "JOIN signal_intents i USING (engine_id,signal_id) "
                "WHERE o.engine_id=? AND o.signal_id=?",
                (engine_id, signal_id),
            ).fetchone()
            if row is None or row["state"] != "PENDING":
                self._db.execute("COMMIT")
                return None
            if (not route.enabled or not route.channel_verified_private
                    or not route.realtime_feed_verified or route.engine_id != engine_id
                    or route.market != Market(row["market"])
                    or route.private_channel_id != row["channel_id"]):
                raise UnsafeDelivery("route changed or no longer verified")
            observed = datetime.fromisoformat(json.loads(row["intent_json"])["observed_at"])
            age = (current_time - _utc(observed)).total_seconds()
            if age < 0 or age > max_age_seconds:
                self._db.execute(
                    "UPDATE signal_outbox SET state='EXPIRED' "
                    "WHERE engine_id=? AND signal_id=? AND state='PENDING'",
                    (engine_id, signal_id),
                )
                self._db.execute("COMMIT")
                return None
            self._db.execute(
                "UPDATE signal_outbox SET state='CLAIMED' "
                "WHERE engine_id=? AND signal_id=? AND state='PENDING'",
                (engine_id, signal_id),
            )
            self._db.execute("COMMIT")
            return self.get(engine_id, signal_id)
        except BaseException:
            self._db.execute("ROLLBACK")
            raise

    def acknowledge_sent(self, engine_id: str, signal_id: str, *, message_id: int
                         ) -> bool:
        """Ack must correspond to a separately confirmed Telegram API response."""
        if isinstance(message_id, bool) or not isinstance(message_id, int) or message_id <= 0:
            raise ValueError("positive Telegram message_id required")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            count = self._db.execute(
                "UPDATE signal_outbox SET state='SENT',message_id=? "
                "WHERE engine_id=? AND signal_id=? AND state IN ('CLAIMED','UNKNOWN')",
                (message_id, engine_id, signal_id),
            ).rowcount
            self._db.execute("COMMIT")
            return bool(count)
        except BaseException:
            self._db.execute("ROLLBACK")
            raise

    def quarantine_inflight(self) -> int:
        """Startup recovery: claimed but unacknowledged means UNKNOWN, not retry."""
        self._db.execute("BEGIN IMMEDIATE")
        try:
            count = self._db.execute(
                "UPDATE signal_outbox SET state='UNKNOWN' WHERE state='CLAIMED'"
            ).rowcount
            self._db.execute("COMMIT")
            return count
        except BaseException:
            self._db.execute("ROLLBACK")
            raise

    def pending(self, engine_id: str) -> tuple[OutboxItem, ...]:
        rows = self._db.execute(
            "SELECT engine_id,signal_id,channel_id,state,message_id FROM signal_outbox "
            "WHERE engine_id=? AND state='PENDING' ORDER BY rowid",
            (engine_id,),
        ).fetchall()
        return tuple(OutboxItem(**dict(row)) for row in rows)
