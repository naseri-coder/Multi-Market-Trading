"""Stage 18: bounded, read-only reconciliation of four OFFLINE ledgers.

No worker execution, retries, order mutation, network, Telegram or LIVE grants.
A Stage-17 DONE hash has no job-level receipt mapping: NEVER infer end-to-end
completion from an approximate binding/source association.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
from contextlib import ExitStack, contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator
from urllib.parse import quote

from .reliability_acceptance_v1 import (
    AcceptanceRefused, LedgerPaths, evaluate_offline_reliability,
)

MAX_JOBS = 5000
MAX_BYTES = 512 * 1024 * 1024
HEX = re.compile(r"[0-9a-f]{64}\Z")
JOB = re.compile(r"job17_[0-9a-f]{64}\Z")
STATUSES = frozenset({"PENDING", "CLAIMED", "DONE", "QUARANTINED"})


class RecoveryRefused(ValueError):
    """Evidence or operator decision failed closed."""


def _json(data: object) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class RecoveryPaths:
    runtime: Path
    control: Path
    paper: Path
    signal: Path


@dataclass(frozen=True, slots=True)
class JobFinding:
    job_id: str
    status: str
    verdict: str
    attempt: int
    candidate_paper_orders: int
    candidate_signals: int
    issues: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RecoveryReport:
    schema_version: int
    status: str
    evidence_sha256: str
    cross_ledger_verdict: str
    cross_ledger_evidence_sha256: str
    cross_ledger_blockers: tuple[str, ...]
    jobs: tuple[JobFinding, ...]
    blocking_jobs: int
    unverified_done_jobs: int
    operator_review_required: bool
    replay_authorized: bool = False
    telegram_authorized: bool = False
    broker_authorized: bool = False
    live_authorized: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


def _path(path: Path, role: str) -> Path:
    if not isinstance(path, Path):
        raise RecoveryRefused("PATH_OBJECT_REQUIRED:" + role)
    path = path.absolute()
    if (path.is_symlink() or not path.is_file()
            or path.stat().st_nlink != 1
            or not 100 <= path.stat().st_size <= MAX_BYTES
            or path.stat().st_uid != os.geteuid()
            or stat.S_IMODE(path.stat().st_mode) & 0o077):
        raise RecoveryRefused("PRIVATE_EXISTING_EVIDENCE_REQUIRED:" + role)
    return path


@contextmanager
def _ro(path: Path) -> Iterator[sqlite3.Connection]:
    db = None
    try:
        db = sqlite3.connect("file:" + quote(str(path), safe="/") + "?mode=ro",
                             uri=True, isolation_level=None, timeout=2)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        yield db
    except sqlite3.DatabaseError as exc:
        raise RecoveryRefused("INVALID_READONLY_SQLITE") from exc
    finally:
        if db is not None:
            db.close()


def _query(db: sqlite3.Connection, sql: str) -> list[sqlite3.Row]:
    result = db.execute(sql + " LIMIT ?", (MAX_JOBS + 1,)).fetchall()
    if len(result) > MAX_JOBS:
        raise RecoveryRefused("EVIDENCE_TOO_LARGE")
    return result


def evaluate_operational_recovery(paths: RecoveryPaths) -> RecoveryReport:
    """Inspect *existing* independent snapshots. Never change their state."""
    if os.environ.get("MMT_NONPRODUCTION") != "1" or os.environ.get("MMT_PRODUCTION") == "1":
        raise RecoveryRefused("NONPRODUCTION_ONLY")
    if not isinstance(paths, RecoveryPaths):
        raise RecoveryRefused("FOUR_PATHS_REQUIRED")
    names = {role: _path(getattr(paths, role), role)
             for role in ("runtime", "control", "paper", "signal")}
    if len({(p.stat().st_dev, p.stat().st_ino) for p in names.values()}) != 4:
        raise RecoveryRefused("SHARED_EVIDENCE_ROLES")
    with ExitStack() as stack:
        dbs = {role: stack.enter_context(_ro(path)) for role, path in names.items()}
        for role, db in dbs.items():
            if db.execute("PRAGMA quick_check(1)").fetchone()[0] != "ok":
                raise RecoveryRefused("SQLITE_INTEGRITY_FAILED:" + role)
        jobs = _query(dbs["runtime"],
                      "SELECT * FROM runtime17_jobs ORDER BY due_at,job_id")
        if not jobs:
            raise RecoveryRefused("NO_SUPERVISOR_EVIDENCE")
        orders = _query(dbs["paper"],
                        "SELECT order_id,instance_id,binding_id FROM paper_core_orders")
        signals = _query(dbs["signal"],
                         "SELECT signal_key,instance_id,binding_id,source_ref "
                         "FROM offline_signal_states")
        commands = _query(dbs["signal"],
                          "SELECT signal_key,state FROM offline_signal_commands")
        instances = _query(dbs["control"],
                           "SELECT instance_id,revision FROM t12_instances")
        bindings = _query(dbs["control"],
                          "SELECT binding_id,instance_id FROM t12_bindings")
        instance_ids = {r["instance_id"] for r in instances}
        binding_keys = {(r["instance_id"], r["binding_id"]) for r in bindings}
        uncertain_signal_keys = {r["signal_key"] for r in commands
                                 if r["state"] in ("UNKNOWN", "CLAIMED")}
        findings = []
        evidence_jobs = []
        for row in jobs:
            issues = []
            payload = row["payload"]
            try:
                packet = json.loads(payload)
                canonical = _json(packet)
                if (canonical != payload or type(packet) is not dict
                        or row["digest"] != _hash(payload)
                        or row["job_id"] != "job17_" + _hash(payload)
                        or not JOB.fullmatch(row["job_id"])):
                    issues.append("JOB_DIGEST_OR_IDENTITY_INVALID")
                if (packet["instance_id"] != row["instance_id"]
                        or packet["binding_id"] != row["binding_id"]
                        or packet["panel_revision"] != row["panel_revision"]
                        or not isinstance(packet["source_ref"], str)
                        or not isinstance(packet["candles"], list)
                        or not packet["candles"]):
                    issues.append("JOB_PAYLOAD_OR_BINDING_MISMATCH")
                source_ref = packet["source_ref"]
            except (ValueError, TypeError, KeyError, AttributeError):
                issues.append("JOB_PAYLOAD_UNREADABLE")
                source_ref = None
            if (row["status"] not in STATUSES or type(row["attempt"]) is not int
                    or row["attempt"] not in (0, 1)):
                issues.append("INVALID_JOB_LIFECYCLE")
            if (row["instance_id"] not in instance_ids
                    or (row["instance_id"], row["binding_id"]) not in binding_keys):
                issues.append("ORPHAN_JOB_BINDING")
            possible_orders = [r for r in orders if r["instance_id"] == row["instance_id"]
                               and r["binding_id"] == row["binding_id"]]
            possible_signals = [r for r in signals if r["instance_id"] == row["instance_id"]
                                and r["binding_id"] == row["binding_id"]
                                and source_ref is not None and r["source_ref"] == source_ref]
            if any(r["signal_key"] in uncertain_signal_keys for r in possible_signals):
                issues.append("AMBIGUOUS_SIGNAL_DELIVERY_STATE")
            if row["status"] in ("CLAIMED", "QUARANTINED"):
                issues.append("INTERRUPTED_OR_QUARANTINED_NO_AUTO_RETRY")
                verdict = "BLOCKED_MANUAL_RECONCILIATION"
            elif row["status"] == "DONE":
                if (not isinstance(row["result_hash"], str)
                        or not HEX.fullmatch(row["result_hash"])):
                    issues.append("MISSING_RESULT_HASH")
                issues.append("NO_EXACT_JOB_TO_OUTPUT_ATTESTATION")
                verdict = "DONE_UNVERIFIED_CROSS_LEDGER"
            else:
                verdict = "PENDING_NOT_EXECUTED"
            if issues and any(i in issues for i in (
                "JOB_DIGEST_OR_IDENTITY_INVALID", "JOB_PAYLOAD_OR_BINDING_MISMATCH",
                "JOB_PAYLOAD_UNREADABLE", "INVALID_JOB_LIFECYCLE", "ORPHAN_JOB_BINDING",
                "AMBIGUOUS_SIGNAL_DELIVERY_STATE", "MISSING_RESULT_HASH")):
                verdict = "BLOCKED_EVIDENCE_INVALID"
            findings.append(JobFinding(row["job_id"], row["status"], verdict,
                                       row["attempt"], len(possible_orders),
                                       len(possible_signals), tuple(sorted(set(issues)))))
            evidence_jobs.append(dict(row))
        try:
            cross = evaluate_offline_reliability(LedgerPaths(
                names["control"], names["paper"], names["signal"]))
            cross_verdict, cross_digest = cross.integrity_verdict, cross.evidence_digest
            blockers = cross.blockers
        except (AcceptanceRefused, sqlite3.DatabaseError):
            cross_verdict, cross_digest = "INVALID_EVIDENCE", ""
            blockers = ("CROSS_LEDGER_EVIDENCE_INVALID",)
        blocked = sum(f.verdict.startswith("BLOCKED") for f in findings)
        unverified = sum(f.status == "DONE" for f in findings)
        output_hash = _hash(_json({"jobs": evidence_jobs,
                                  "paper_candidates": [dict(r) for r in orders],
                                  "signal_candidates": [dict(r) for r in signals],
                                  "command_states": [dict(r) for r in commands],
                                  "control": [dict(r) for r in instances],
                                  "bindings": [dict(r) for r in bindings],
                                  "cross_digest": cross_digest,
                                  "cross_verdict": cross_verdict,
                                  "blockers": blockers}))
        verdict = ("BLOCKED_MANUAL_RECONCILIATION" if blocked
                   else "BLOCKED_CROSS_LEDGER_EVIDENCE" if cross_verdict != "PASS"
                   else "UNATTESTED_OFFLINE_ONLY")
        return RecoveryReport(1, verdict, output_hash, cross_verdict,
                              cross_digest, tuple(blockers), tuple(findings),
                              blocked, unverified, bool(blocked or unverified
                                                         or cross_verdict != "PASS"))


__all__ = ["RecoveryPaths", "RecoveryReport", "JobFinding", "RecoveryRefused",
           "evaluate_operational_recovery"]
