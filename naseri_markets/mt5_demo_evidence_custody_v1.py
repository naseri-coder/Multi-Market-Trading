"""Stage 7: durable, restart-verified MT5 DEMO *diagnostic* evidence custody.

The local SQLite journal is append-only through this API with a SHA-256 hash
chain and immutable provider ticket payloads. SHA-256 is corruption detection,
NOT broker authentication, signed provenance, or a tamper-proof remote backup.
No live terminal setup, order sends, PAPER state mutation or risk authority.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote
from typing import Any

from .execution_contract_v1 import identity
from .mt5_demo_history_readonly_v1 import (
    MT5DemoHistoryReaderV1,
    MT5DemoHistorySnapshot,
    MT5HistoricalDeal,
)
from .mt5_demo_position_accounting_v1 import diagnose_position_history
from .mt5_demo_readonly_adapter_v1 import (
    DemoAccountExpectation,
    MT5DemoReadOnlyAdapterV1,
    _field,
)

_GENESIS = "0" * 64


class EvidenceCustodyRefused(ValueError):
    """Fail-closed incomplete, conflicting, drifting or corrupted local evidence."""


def _wire(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value: Any) -> str:
    return hashlib.sha256(_wire(value).encode("utf-8")).hexdigest()


def _snapshot_digest(wire: dict[str, Any]) -> str:
    content = dict(wire)
    content.pop("captured_at", None)
    return _digest(content)


def _margin_mode(provider: Any, guard: MT5DemoReadOnlyAdapterV1) -> str:
    # Use SDK's own constants rather than guessing their numeric values.
    _, info = guard._guard()
    margin_mode = _field(info, "margin_mode")
    hedge = getattr(provider, "ACCOUNT_MARGIN_MODE_RETAIL_HEDGING", None)
    netting = getattr(provider, "ACCOUNT_MARGIN_MODE_RETAIL_NETTING", None)
    if (
        type(margin_mode) is not int or type(hedge) is not int
        or type(netting) is not int or hedge == netting
    ):
        raise EvidenceCustodyRefused("UNVERIFIED_ACCOUNT_MARGIN_MODE")
    if margin_mode == hedge:
        return "HEDGING"
    if margin_mode == netting:
        return "NETTING"
    # Exchange margin treatment is distinct; not quietly called netting.
    raise EvidenceCustodyRefused("UNSUPPORTED_ACCOUNT_MARGIN_MODE")


class DemoHistoryEvidenceCustodyV1:
    """Account-locked, window-contiguous, nonproduction DEMO evidence ledger.

    Accounts enroll against exact DEMO login/server/margin mode. Each process
    must open a new volatile read session; a token from a prior instance
    cannot authorize a new history capture. No token can authorize trading.
    """

    def __init__(self, path: str | Path, *, read_only: bool = False):
        p = Path(path)
        if p.is_symlink() or (p.exists() and not p.is_file()):
            raise EvidenceCustodyRefused("NONREGULAR_CUSTODY_PATH")
        self._read_only = read_only
        if read_only and not p.is_file():
            raise EvidenceCustodyRefused("CUSTODY_READ_ONLY_SOURCE_MISSING")
        if not read_only:
            p.parent.mkdir(parents=True, exist_ok=True)
        uri = (
            "file:" + quote(p.resolve().as_posix(), safe="/:") + "?mode=ro"
            if read_only else str(p)
        )
        self._db = sqlite3.connect(
            uri, timeout=5, isolation_level=None, uri=read_only,
        )
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA busy_timeout=5000")
        if read_only:
            self._db.execute("PRAGMA query_only=ON")
        else:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=FULL")
            self._db.execute("PRAGMA foreign_keys=ON")
        if not read_only:
            self._install_schema()
        self._sessions: dict[str, tuple[str, str]] = {}

    def _install_schema(self) -> None:
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS mt5_demo_accounts ("
            "account_id TEXT PRIMARY KEY, login INTEGER NOT NULL, "
            "server TEXT NOT NULL, margin_mode TEXT NOT NULL, "
            "epoch TEXT NOT NULL, head TEXT NOT NULL, "
            "last_end TEXT, receipt_count INTEGER NOT NULL)"
        )
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS mt5_demo_receipts ("
            "seq INTEGER PRIMARY KEY AUTOINCREMENT, "
            "account_id TEXT NOT NULL, action_id TEXT NOT NULL UNIQUE, "
            "window_start TEXT NOT NULL, window_end TEXT NOT NULL, "
            "digest TEXT NOT NULL, previous_hash TEXT NOT NULL, "
            "chain_hash TEXT NOT NULL, payload TEXT NOT NULL, "
            "UNIQUE(account_id,window_start,window_end), "
            "FOREIGN KEY(account_id) REFERENCES mt5_demo_accounts(account_id))"
        )
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS mt5_demo_tickets ("
            "account_id TEXT NOT NULL, kind TEXT NOT NULL, "
            "ticket INTEGER NOT NULL, payload TEXT NOT NULL, "
            "PRIMARY KEY(account_id,kind,ticket), "
            "FOREIGN KEY(account_id) REFERENCES mt5_demo_accounts(account_id))"
        )
    def close(self) -> None:
        self._sessions.clear()
        self._db.close()

    def __enter__(self) -> DemoHistoryEvidenceCustodyV1:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _account(self, account_id: str) -> sqlite3.Row:
        row = self._db.execute(
            "SELECT * FROM mt5_demo_accounts WHERE account_id=?", (account_id,)
        ).fetchone()
        if row is None:
            raise EvidenceCustodyRefused("DEMO_ACCOUNT_NOT_ENROLLED")
        return row

    def _verify_identity(
        self, row: sqlite3.Row, expected: DemoAccountExpectation, mode: str,
    ) -> None:
        if (
            row["login"] != expected.login or row["server"] != expected.server
            or row["margin_mode"] != mode
        ):
            raise EvidenceCustodyRefused("CUSTODY_ACCOUNT_IDENTITY_OR_MODE_DRIFT")

    def verify(self, account_id: str) -> dict[str, Any]:
        """Recompute local chain, every ticket, and session head after restart."""
        identity(account_id, "account_id")
        row = self._account(account_id)
        receipts = self._db.execute(
            "SELECT * FROM mt5_demo_receipts WHERE account_id=? ORDER BY seq",
            (account_id,),
        ).fetchall()
        head = _GENESIS
        last_end: str | None = None
        expected_tickets: dict[tuple[str, int], str] = {}
        try:
            for index, entry in enumerate(receipts, 1):
                data = json.loads(entry["payload"])
                if (
                    _snapshot_digest(data) != entry["digest"]
                    or entry["previous_hash"] != head
                    or entry["window_start"] != data["start_utc"]
                    or entry["window_end"] != data["end_utc"]
                    or data["account_id"] != account_id
                    or data["login"] != row["login"]
                    or data["server"] != row["server"]
                    or data["source"] != "MT5_DEMO_BOUNDED_HISTORY_READONLY_V1"
                    or data["all_time_history_complete"] is not False
                    or data["execution_authority"] is not False
                    or data["stage4_reconciliation_authority"] is not False
                ):
                    raise EvidenceCustodyRefused("CUSTODY_RECEIPT_CONTENT_CORRUPTED")
                expected_head = _digest({
                    "account": account_id, "epoch": row["epoch"],
                    "seq": index, "action_id": entry["action_id"],
                    "start": entry["window_start"], "end": entry["window_end"],
                    "digest": entry["digest"], "previous": head,
                })
                if entry["chain_hash"] != expected_head:
                    raise EvidenceCustodyRefused("CUSTODY_CHAIN_CORRUPTED")
                if last_end is not None and (
                    entry["window_start"] > last_end
                    or entry["window_end"] <= last_end
                ):
                    raise EvidenceCustodyRefused("CUSTODY_WINDOW_CHAIN_CORRUPTED")
                for kind, values in (
                    ("ORDER", data["orders"]), ("DEAL", data["deals"])
                ):
                    for item in values:
                        key = (kind, item["ticket"])
                        serialized = _wire(item)
                        prior = expected_tickets.get(key)
                        if prior is not None and prior != serialized:
                            raise EvidenceCustodyRefused("CUSTODY_TICKET_DRIFT")
                        expected_tickets[key] = serialized
                last_end, head = entry["window_end"], expected_head
            actual = self._db.execute(
                "SELECT kind,ticket,payload FROM mt5_demo_tickets "
                "WHERE account_id=?", (account_id,),
            ).fetchall()
            if {(r["kind"], r["ticket"]): r["payload"] for r in actual} != expected_tickets:
                raise EvidenceCustodyRefused("CUSTODY_TICKET_INDEX_CORRUPTED")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            if isinstance(exc, EvidenceCustodyRefused):
                raise
            raise EvidenceCustodyRefused("CUSTODY_RECORD_INVALID") from exc
        if (
            row["head"] != head or row["last_end"] != last_end
            or row["receipt_count"] != len(receipts)
        ):
            raise EvidenceCustodyRefused("CUSTODY_HEAD_OR_COUNT_CORRUPTED")
        return {
            "mode": "MT5_DEMO_EVIDENCE_CUSTODY_DIAGNOSTIC_ONLY",
            "account_id": account_id, "account_mode": row["margin_mode"],
            "epoch": row["epoch"], "head": head, "windows": len(receipts),
            "ticket_count": len(expected_tickets),
            "last_end": last_end, "locally_integrity_checked": True,
            "broker_authenticated": False, "tamper_proof": False,
            "may_unlock_recovery": False, "may_send_order": False,
        }

    def open_read_session(
        self, provider: Any, expected: DemoAccountExpectation,
    ) -> str:
        """Only a *fresh* pinned DEMO identity may open a new local session."""
        if self._read_only:
            raise EvidenceCustodyRefused("READONLY_CUSTODY_CANNOT_MUTATE")
        if not isinstance(expected, DemoAccountExpectation):
            raise TypeError("EXPECTED_DEMO_ACCOUNT_REQUIRED")
        guard = MT5DemoReadOnlyAdapterV1(provider, expected)
        mode = _margin_mode(provider, guard)
        if _margin_mode(provider, guard) != mode:
            raise EvidenceCustodyRefused("ACCOUNT_MARGIN_MODE_SWITCHED")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            existing = self._db.execute(
                "SELECT * FROM mt5_demo_accounts WHERE account_id=?",
                (expected.account_id,),
            ).fetchone()
            if existing is None:
                self._db.execute(
                    "INSERT INTO mt5_demo_accounts VALUES (?,?,?,?,?,?,?,?)",
                    (expected.account_id, expected.login, expected.server,
                     mode, uuid.uuid4().hex, _GENESIS, None, 0),
                )
            else:
                self._verify_identity(existing, expected, mode)
                self.verify(expected.account_id)
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        session = uuid.uuid4().hex
        self._sessions[expected.account_id] = (session, mode)
        return session

    def capture_and_append(
        self, provider: Any, expected: DemoAccountExpectation,
        start: datetime, end: datetime, *,
        session: str, action_id: str, captured_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Read a complete bounded window before storing it atomically."""
        if self._read_only:
            raise EvidenceCustodyRefused("READONLY_CUSTODY_CANNOT_MUTATE")
        if not isinstance(expected, DemoAccountExpectation):
            raise TypeError("EXPECTED_DEMO_ACCOUNT_REQUIRED")
        allowed = self._sessions.get(expected.account_id)
        if allowed is None or session != allowed[0]:
            raise EvidenceCustodyRefused("FRESH_READ_SESSION_REQUIRED")
        guard = MT5DemoReadOnlyAdapterV1(provider, expected)
        if _margin_mode(provider, guard) != allowed[1]:
            raise EvidenceCustodyRefused("ACCOUNT_MARGIN_MODE_SWITCHED")
        snapshot = MT5DemoHistoryReaderV1(provider, expected).capture(
            start, end, captured_at=captured_at,
        )
        if _margin_mode(provider, guard) != allowed[1]:
            raise EvidenceCustodyRefused("ACCOUNT_MARGIN_MODE_SWITCHED")
        return self._append(snapshot, expected, allowed[1], action_id)

    def _after_tickets_before_receipt(self) -> None:
        """Fault-injection seam: failure here must undo all tentative rows."""

    def _append(
        self, snapshot: MT5DemoHistorySnapshot,
        expected: DemoAccountExpectation,
        mode: str, action_id: str,
    ) -> dict[str, Any]:
        """Write only freshly captured DEMO snapshots; internal integration seam."""
        if self._read_only:
            raise EvidenceCustodyRefused("READONLY_CUSTODY_CANNOT_MUTATE")
        identity(action_id, "action_id")
        if (
            not isinstance(snapshot, MT5DemoHistorySnapshot)
            or snapshot.source != "MT5_DEMO_BOUNDED_HISTORY_READONLY_V1"
            or (snapshot.account_id, snapshot.login, snapshot.server)
            != (expected.account_id, expected.login, expected.server)
        ):
            raise EvidenceCustodyRefused("HISTORY_SNAPSHOT_IDENTITY_MISMATCH")
        # Re-reading custody before mutation exposes corruption / rollback.
        self.verify(expected.account_id)
        content = snapshot.wire()
        payload = _wire(content)
        digest = _snapshot_digest(content)
        start, end = content["start_utc"], content["end_utc"]
        self._db.execute("BEGIN IMMEDIATE")
        try:
            account = self._account(expected.account_id)
            self._verify_identity(account, expected, mode)
            replay = self._db.execute(
                "SELECT * FROM mt5_demo_receipts WHERE action_id=?",
                (action_id,),
            ).fetchone()
            if replay is not None:
                if (
                    replay["account_id"] != expected.account_id
                    or replay["window_start"] != start
                    or replay["window_end"] != end or replay["digest"] != digest
                ):
                    raise EvidenceCustodyRefused("CUSTODY_ACTION_KEY_CONFLICT")
                result = self._receipt_result(replay, replayed=True)
                self._db.execute("COMMIT")
                return result
            window = self._db.execute(
                "SELECT digest FROM mt5_demo_receipts "
                "WHERE account_id=? AND window_start=? AND window_end=?",
                (expected.account_id, start, end),
            ).fetchone()
            if window is not None:
                raise EvidenceCustodyRefused("CUSTODY_WINDOW_ALREADY_RECORDED")
            last_end = account["last_end"]
            if last_end is not None and (
                start > last_end or end <= last_end
            ):
                raise EvidenceCustodyRefused("CUSTODY_GAP_OR_ROLLBACK_ATTEMPT")
            for kind, records in (("ORDER", snapshot.orders), ("DEAL", snapshot.deals)):
                for record in records:
                    serialized = _wire(record.wire())
                    existing = self._db.execute(
                        "SELECT payload FROM mt5_demo_tickets "
                        "WHERE account_id=? AND kind=? AND ticket=?",
                        (expected.account_id, kind, record.ticket),
                    ).fetchone()
                    if existing is not None:
                        if existing["payload"] != serialized:
                            raise EvidenceCustodyRefused("CUSTODY_TICKET_CONTENT_CONFLICT")
                    else:
                        self._db.execute(
                            "INSERT INTO mt5_demo_tickets VALUES (?,?,?,?)",
                            (expected.account_id, kind, record.ticket, serialized),
                        )
            self._after_tickets_before_receipt()
            seq = int(account["receipt_count"]) + 1
            head = _digest({
                "account": expected.account_id, "epoch": account["epoch"],
                "seq": seq, "action_id": action_id,
                "start": start, "end": end, "digest": digest,
                "previous": account["head"],
            })
            self._db.execute(
                "INSERT INTO mt5_demo_receipts "
                "(account_id,action_id,window_start,window_end,digest,"
                "previous_hash,chain_hash,payload) VALUES (?,?,?,?,?,?,?,?)",
                (expected.account_id, action_id, start, end, digest,
                 account["head"], head, payload),
            )
            self._db.execute(
                "UPDATE mt5_demo_accounts SET head=?,last_end=?,receipt_count=? "
                "WHERE account_id=?",
                (head, end, seq, expected.account_id),
            )
            row = self._db.execute(
                "SELECT * FROM mt5_demo_receipts WHERE action_id=?", (action_id,)
            ).fetchone()
            result = self._receipt_result(row, replayed=False)
            self._db.execute("COMMIT")
            return result
        except BaseException:
            self._db.execute("ROLLBACK")
            raise

    @staticmethod
    def _receipt_result(row: sqlite3.Row, *, replayed: bool) -> dict[str, Any]:
        return {
            "mode": "MT5_DEMO_HISTORY_EVIDENCE_ONLY",
            "account_id": row["account_id"],
            "action_id": row["action_id"],
            "window_start": row["window_start"],
            "window_end": row["window_end"],
            "content_digest": row["digest"],
            "chain_hash": row["chain_hash"],
            "replayed": replayed,
            "broker_authenticated": False, "may_send_order": False,
            "may_unlock_recovery": False, "may_release_risk": False,
        }

    def verified_window(
        self, account_id: str, start_utc: datetime, end_utc: datetime,
    ) -> dict[str, Any]:
        """Read exact persisted window only after full local integrity verification."""
        from datetime import UTC

        def normalized(value: datetime) -> str:
            if (
                not isinstance(value, datetime) or value.tzinfo is None
                or value.utcoffset() is None
            ):
                raise EvidenceCustodyRefused("UTC_AWARE_WINDOW_REQUIRED")
            return value.astimezone(UTC).isoformat()

        self.verify(account_id)
        row = self._db.execute(
            "SELECT payload,digest,chain_hash FROM mt5_demo_receipts "
            "WHERE account_id=? AND window_start=? AND window_end=?",
            (account_id, normalized(start_utc), normalized(end_utc)),
        ).fetchone()
        if row is None:
            raise EvidenceCustodyRefused("CUSTODY_EXACT_WINDOW_NOT_FOUND")
        content = json.loads(row["payload"])
        if _snapshot_digest(content) != row["digest"]:
            raise EvidenceCustodyRefused("CUSTODY_WINDOW_DIGEST_MISMATCH")
        return {
            "payload": content, "digest": row["digest"],
            "chain_hash": row["chain_hash"],
        }

    def accounting(self, account_id: str) -> dict[str, Any]:
        """Replay all locally checked tickets after a new-instance verification."""
        verified = self.verify(account_id)
        deals = []
        for row in self._db.execute(
            "SELECT payload FROM mt5_demo_tickets "
            "WHERE account_id=? AND kind='DEAL' ORDER BY ticket",
            (account_id,),
        ):
            value = json.loads(row["payload"])
            deals.append(MT5HistoricalDeal(
                ticket=value["ticket"], order_ticket=value["order_ticket"],
                position_id=value["position_id"], symbol=value["symbol"],
                type_code=value["type_code"], entry_code=value["entry_code"],
                time_msc=value["time_msc"], volume=Decimal(value["volume"]),
                price=Decimal(value["price"]), profit=Decimal(value["profit"]),
                commission=Decimal(value["commission"]),
                swap=Decimal(value["swap"]), fee=Decimal(value["fee"]),
            ))
        result = diagnose_position_history(
            tuple(deals), margin_mode=verified["account_mode"],
        )
        result["custody_head"] = verified["head"]
        result["read_only_recovered_after_restart"] = True
        return result
