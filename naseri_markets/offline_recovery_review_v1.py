"""Stage 18: human reconciliation journal, strictly no executor/queue mutation.

A review receipt cannot upgrade Stage-17 status, dismiss ambiguity, or retry a
PAPER action. Operator explicitly declares all workers stopped; this claim is
not independently proven by this local journal.
"""
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import stat
from pathlib import Path

from .operational_reconciliation_v1 import (
    RecoveryPaths, RecoveryRefused, evaluate_operational_recovery,
)

_SHA = re.compile(r"[0-9a-f]{64}\Z")


def record_operator_review(
    evidence: RecoveryPaths, review_db: Path, *, job_id: str,
    evidence_sha256: str, note: str, operator_id: int,
    operator_ack: bool = False, all_workers_stopped: bool = False,
) -> dict:
    if (operator_ack is not True or all_workers_stopped is not True
            or type(operator_id) is not int or operator_id <= 0):
        raise RecoveryRefused("REVIEW_REQUIRES_STOPPED_WORKERS_AND_OPERATOR")
    if (type(note) is not str or not 8 <= len(note) <= 240
            or not note.isprintable() or any(x in note for x in "\r\n")):
        raise RecoveryRefused("SANITIZED_REVIEW_NOTE_REQUIRED")
    if type(evidence_sha256) is not str or not _SHA.fullmatch(evidence_sha256):
        raise RecoveryRefused("EXPECTED_EVIDENCE_HASH_REQUIRED")
    report = evaluate_operational_recovery(evidence)
    if report.evidence_sha256 != evidence_sha256:
        raise RecoveryRefused("EVIDENCE_CHANGED_REAUDIT_REQUIRED")
    selected = next((item for item in report.jobs if item.job_id == job_id), None)
    if selected is None or selected.status not in ("CLAIMED", "QUARANTINED"):
        raise RecoveryRefused("ONLY_INTERRUPTED_JOBS_MAY_BE_REVIEWED")
    path = Path(review_db)
    if not path.is_absolute() or path.is_symlink() or not path.parent.is_dir():
        raise RecoveryRefused("DEDICATED_REVIEW_FILE_REQUIRED")
    if (path.parent.is_symlink() or path.parent.stat().st_uid != os.geteuid()
            or stat.S_IMODE(path.parent.stat().st_mode) & 0o077):
        raise RecoveryRefused("PRIVATE_REVIEW_DIRECTORY_REQUIRED")
    sources = [getattr(evidence, name).resolve()
               for name in ("runtime", "control", "paper", "signal")]
    if ((path.exists() and (not path.is_file() or path.stat().st_nlink != 1
                            or path.stat().st_uid != os.geteuid()
                            or stat.S_IMODE(path.stat().st_mode) & 0o077))
            or path.resolve() in sources):
        raise RecoveryRefused("INVALID_OR_OVERLAPPING_REVIEW_DB")
    existing_file = path.exists()
    if not existing_file:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        os.close(fd)
    db = sqlite3.connect(path, timeout=3, isolation_level=None)
    try:
        db.execute("PRAGMA busy_timeout=3000")
        if existing_file and not db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='stage18_manual_reviews'").fetchone():
            raise RecoveryRefused("UNRELATED_REVIEW_DATABASE")
        db.execute("CREATE TABLE IF NOT EXISTS stage18_manual_reviews ("
                   "job_id TEXT NOT NULL, evidence_sha256 TEXT NOT NULL, "
                   "operator_id INTEGER NOT NULL, note_sha256 TEXT NOT NULL, "
                   "verdict TEXT NOT NULL CHECK(verdict='REVIEW_RECORDED_NO_RETRY'), "
                   "PRIMARY KEY(job_id,evidence_sha256))")
        digest = hashlib.sha256(note.encode("utf-8")).hexdigest()
        db.execute("BEGIN IMMEDIATE")
        try:
            existing = db.execute("SELECT operator_id,note_sha256 "
                "FROM stage18_manual_reviews WHERE job_id=? AND evidence_sha256=?",
                (job_id, evidence_sha256)).fetchone()
            if existing is None:
                db.execute("INSERT INTO stage18_manual_reviews VALUES(?,?,?,?,?)",
                           (job_id, evidence_sha256, operator_id, digest,
                            "REVIEW_RECORDED_NO_RETRY"))
            elif existing != (operator_id, digest):
                raise RecoveryRefused("CONFLICTING_MANUAL_REVIEW")
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
    finally:
        db.close()
    return {"status": "REVIEW_RECORDED_NO_RETRY", "job_id": job_id,
            "evidence_sha256": evidence_sha256, "operator_id": operator_id,
            "runtime_state_changed": False, "replay_authorized": False,
            "telegram_sent": False, "broker_order_sent": False}


__all__ = ["record_operator_review"]
