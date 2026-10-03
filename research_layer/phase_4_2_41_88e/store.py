from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS history_cases(candidate_identity TEXT PRIMARY KEY,terminal_timestamp TEXT NOT NULL,source_role TEXT NOT NULL,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS candidates(candidate_identity TEXT PRIMARY KEY,candidate_timestamp TEXT NOT NULL,symbol TEXT NOT NULL,timeframe TEXT NOT NULL,direction TEXT NOT NULL,decision_status TEXT NOT NULL,candidate_payload TEXT NOT NULL,decision_payload TEXT NOT NULL,lifecycle_payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS evidence(candidate_identity TEXT PRIMARY KEY,approved_at TEXT NOT NULL,candle_closed_at TEXT NOT NULL,symbol TEXT NOT NULL,timeframe TEXT NOT NULL,direction TEXT NOT NULL,always_in TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS scan_cycles(scan_timestamp TEXT PRIMARY KEY,status TEXT NOT NULL,detail TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS operational_events(id INTEGER PRIMARY KEY AUTOINCREMENT,ts TEXT NOT NULL,event_type TEXT NOT NULL,detail TEXT NOT NULL);
"""


class ShadowStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.db.commit()

    def close(self):
        self.db.close()

    def set_meta(self, k, v):
        self.db.execute(
            "INSERT OR REPLACE INTO meta VALUES(?,?)", (k, json.dumps(v, sort_keys=True))
        )
        self.db.commit()

    def get_meta(self, k, default=None):
        r = self.db.execute("SELECT value FROM meta WHERE key=?", (k,)).fetchone()
        return default if r is None else json.loads(r["value"])

    def add_history(self, case, role):
        self.db.execute(
            "INSERT OR IGNORE INTO history_cases VALUES(?,?,?,?)",
            (
                case["candidate_identity"],
                case["terminal_timestamp"],
                role,
                json.dumps(case, sort_keys=True),
            ),
        )
        self.db.commit()

    def history(self):
        return [
            json.loads(r["payload"])
            for r in self.db.execute(
                "SELECT payload FROM history_cases ORDER BY terminal_timestamp,candidate_identity"
            )
        ]

    def has_candidate(self, cid):
        return (
            self.db.execute(
                "SELECT 1 FROM candidates WHERE candidate_identity=?", (cid,)
            ).fetchone()
            is not None
        )

    def add_candidate(self, c, d, lifecycle):
        self.db.execute(
            "INSERT OR IGNORE INTO candidates VALUES(?,?,?,?,?,?,?,?,?)",
            (
                c["candidate_identity"],
                c["candidate_timestamp"],
                c["symbol"],
                c["timeframe"],
                c["direction"],
                d["status"],
                json.dumps(c, sort_keys=True),
                json.dumps(d, sort_keys=True),
                json.dumps(lifecycle, sort_keys=True),
            ),
        )
        self.db.commit()

    def candidates(self, open_only=False):
        rows = self.db.execute(
            "SELECT * FROM candidates ORDER BY candidate_timestamp,candidate_identity"
        ).fetchall()
        out = []
        for r in rows:
            l = json.loads(r["lifecycle_payload"])
            if open_only and l.get("status") in {
                "COMPLETE",
                "AMBIGUOUS",
                "NEVER_ENTERED_FINAL",
                "UNRECONSTRUCTABLE",
            }:
                continue
            out.append((json.loads(r["candidate_payload"]), json.loads(r["decision_payload"]), l))
        return out

    def update_lifecycle(self, cid, lifecycle):
        self.db.execute(
            "UPDATE candidates SET lifecycle_payload=? WHERE candidate_identity=?",
            (json.dumps(lifecycle, sort_keys=True), cid),
        )
        self.db.commit()

    def add_evidence(self, e):
        self.db.execute(
            "INSERT OR IGNORE INTO evidence VALUES(?,?,?,?,?,?,?)",
            (
                e["candidate_identity"],
                e["approved_at"],
                e["candle_closed_at"],
                e["symbol"],
                e["timeframe"],
                e["direction"],
                e["always_in"],
            ),
        )
        self.db.commit()

    def evidence(self, symbol, timeframe):
        return [
            dict(r)
            for r in self.db.execute(
                "SELECT * FROM evidence WHERE symbol=? AND timeframe=? ORDER BY approved_at,candidate_identity",
                (symbol, timeframe),
            )
        ]

    def record_scan(self, ts, status, detail):
        self.db.execute(
            "INSERT OR REPLACE INTO scan_cycles VALUES(?,?,?)",
            (ts, status, json.dumps(detail, sort_keys=True)),
        )
        self.db.commit()

    def event(self, ts, typ, detail):
        self.db.execute(
            "INSERT INTO operational_events(ts,event_type,detail) VALUES(?,?,?)",
            (ts, typ, json.dumps(detail, sort_keys=True)),
        )
        self.db.commit()
