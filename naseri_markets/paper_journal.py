"""A7 persistent PAPER-only journal; separate from live Telegram outbox."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .contracts import EvidenceMode, SignalIntent
from .delivery_ledger import IdentityConflict, _wire_intent, open_sqlite


@dataclass(frozen=True, slots=True)
class JournalCounts:
    inserted: int
    duplicate: int


class PaperJournal:
    """Atomic storage of validated paper signals, never delivery attempts."""

    def __init__(self, path: str | Path) -> None:
        p = Path(path)
        if p.is_symlink() or (p.exists() and not p.is_file()):
            raise ValueError("A7_NONREGULAR_JOURNAL_PATH")
        self._db = open_sqlite(p)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS a7_paper_intents ("
            "engine_id TEXT NOT NULL, signal_id TEXT NOT NULL,"
            "digest TEXT NOT NULL, payload TEXT NOT NULL,"
            "PRIMARY KEY(engine_id,signal_id))"
        )

    def close(self) -> None:
        self._db.close()

    def count(self) -> int:
        return int(self._db.execute(
            "SELECT count(*) FROM a7_paper_intents"
        ).fetchone()[0])

    def record_batch(self, signals: Sequence[SignalIntent]) -> JournalCounts:
        prepared = []
        for item in signals:
            if not isinstance(item, SignalIntent) or item.evidence_mode is not EvidenceMode.PAPER:
                raise ValueError("A7_PAPER_ONLY")
            payload = _wire_intent(item)
            digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            prepared.append((item.engine_id, item.signal_id, digest, payload))
        inserted = duplicate = 0
        self._db.execute("BEGIN IMMEDIATE")
        try:
            for eid, sid, digest, payload in prepared:
                row = self._db.execute(
                    "SELECT digest FROM a7_paper_intents "
                    "WHERE engine_id=? AND signal_id=?", (eid, sid),
                ).fetchone()
                if row is not None:
                    if row["digest"] != digest:
                        raise IdentityConflict("A7_IDENTITY_PAYLOAD_CONFLICT")
                    duplicate += 1
                else:
                    self._db.execute(
                        "INSERT INTO a7_paper_intents VALUES (?,?,?,?)",
                        (eid, sid, digest, payload),
                    )
                    inserted += 1
            self._db.execute("COMMIT")
        except BaseException:
            self._db.execute("ROLLBACK")
            raise
        return JournalCounts(inserted, duplicate)

    def get(self, engine_id: str, signal_id: str) -> dict | None:
        row = self._db.execute(
            "SELECT payload FROM a7_paper_intents "
            "WHERE engine_id=? AND signal_id=?", (engine_id, signal_id),
        ).fetchone()
        return json.loads(row["payload"]) if row else None
