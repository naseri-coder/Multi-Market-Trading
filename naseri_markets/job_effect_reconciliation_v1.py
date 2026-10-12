"""Stage 19 exact-ID evidence reconciliation; read-only, no automatic replay."""
from __future__ import annotations

import os
import sqlite3
from contextlib import ExitStack, contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator
from urllib.parse import quote

from .job_effect_intent_v1 import _safe_file, _sha, _wire, IntentRefused


@dataclass(frozen=True, slots=True)
class EffectEvidencePaths:
    effects: Path
    runtime: Path
    paper: Path
    signal: Path


@dataclass(frozen=True, slots=True)
class EffectFinding:
    intent_id: str
    job_id: str
    kind: str
    target_id: str
    journal_state: str
    target_evidence: str
    job_state: str
    verdict: str


@dataclass(frozen=True, slots=True)
class EffectEvidenceReport:
    evidence_sha256: str
    findings: tuple[EffectFinding, ...]
    blocking_effects: int
    exact_local_effects: int
    operator_review_required: bool
    verdict: str = "OFFLINE_EVIDENCE_ONLY_NOT_RELEASE_AUTHORIZATION"
    auto_retry_authorized: bool = False
    telegram_send_authorized: bool = False
    broker_orders_authorized: bool = False
    live_trading_authorized: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


@contextmanager
def _read(path: Path) -> Iterator[sqlite3.Connection]:
    db = sqlite3.connect("file:" + quote(str(path), safe="/") + "?mode=ro",
                         uri=True, isolation_level=None, timeout=2)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        if db.execute("PRAGMA quick_check(1)").fetchone()[0] != "ok":
            raise IntentRefused("INVALID_SQLITE_INTEGRITY")
        yield db
    finally:
        db.close()


def _proof(r: sqlite3.Row, paper: sqlite3.Connection, signal: sqlite3.Connection) -> str:
    kind = r["kind"]
    if kind == "PAPER_RESERVE":
        record = paper.execute(
            "SELECT d.request_digest,d.decision_id,d.order_id,o.instance_id,"
            "o.binding_id FROM paper_core_decisions d "
            "JOIN paper_core_orders o ON o.order_id=d.order_id "
            "WHERE d.binding_id=? AND d.decision_id=?",
            (r["binding_id"], r["decision_id"])).fetchone()
        if record is None:
            return "NO_TARGET_RECORD"
        matches = (record["order_id"] == r["target_id"]
                   and record["request_digest"] == r["request_digest"]
                   and record["instance_id"] == r["instance_id"]
                   and record["binding_id"] == r["binding_id"])
        return "EXACT_TARGET" if matches else "TARGET_CONFLICT"
    if kind == "PAPER_PLAN":
        record = paper.execute(
            "SELECT plan_json,binding_digest FROM paper_stage9_plans WHERE order_id=?",
            (r["target_id"],)).fetchone()
        if record is None:
            return "NO_TARGET_RECORD"
        try:
            import json
            plan = json.loads(record["plan_json"])
            matches = (_wire(plan) == record["plan_json"]
                       and _sha(record["plan_json"]) == r["request_digest"]
                       and plan["decision_id"] == r["decision_id"]
                       and plan["instance_id"] == r["instance_id"]
                       and plan["binding_id"] == r["binding_id"]
                       and plan["source_ref"] == r["source_ref"])
        except (ValueError, KeyError, TypeError):
            matches = False
        return "EXACT_TARGET" if matches else "TARGET_CONFLICT"
    if kind == "DRY_SIGNAL":
        record = signal.execute(
            "SELECT initial_digest,instance_id,binding_id,decision_id,source_ref "
            "FROM offline_signal_states WHERE signal_key=?", (r["target_id"],)).fetchone()
        if record is None:
            return "NO_TARGET_RECORD"
        matches = (record["initial_digest"] == r["request_digest"]
                   and record["instance_id"] == r["instance_id"]
                   and record["binding_id"] == r["binding_id"]
                   and record["decision_id"] == r["decision_id"]
                   and record["source_ref"] == r["source_ref"])
        unknown = signal.execute(
            "SELECT 1 FROM offline_signal_commands WHERE signal_key=? "
            "AND state IN('UNKNOWN','CLAIMED') LIMIT 1", (r["target_id"],)).fetchone()
        return "TARGET_CONFLICT" if not matches else (
            "AMBIGUOUS_OUTBOX" if unknown else "EXACT_TARGET")
    return "INVALID_EFFECT_KIND"


def _verify_chain(intents: list[sqlite3.Row], events: list[sqlite3.Row]) -> None:
    source = {r["intent_id"]: r for r in intents}
    previous, actions = "0" * 64, {}
    for row in events:
        intent = source.get(row["intent_id"])
        if intent is None:
            raise IntentRefused("ORPHAN_EFFECT_AUDIT")
        action = row["action"]
        if action == "PREPARED":
            data = {key: intent[key] for key in (
                "job_id", "kind", "target_id", "request_digest", "instance_id",
                "binding_id", "decision_id", "source_ref", "event_digest")}
        elif action == "RECORDED":
            data = {"target_id": intent["target_id"],
                    "receipt_sha256": intent["receipt_sha256"]}
        else:
            raise IntentRefused("UNKNOWN_EFFECT_AUDIT_EVENT")
        payload = _sha(_wire(data))
        chain = _sha(_wire([previous, row["intent_id"], action, payload]))
        if (row["prev_hash"] != previous or row["payload_hash"] != payload
                or row["chain_hash"] != chain):
            raise IntentRefused("TAMPERED_EFFECT_AUDIT_CHAIN")
        actions.setdefault(row["intent_id"], []).append(action)
        previous = chain
    for r in intents:
        expected = ["PREPARED", "RECORDED"] if r["state"] == "RECORDED" else ["PREPARED"]
        packet = {key: r[key] for key in (
            "job_id", "kind", "target_id", "request_digest", "instance_id",
            "binding_id", "decision_id", "source_ref", "event_digest")}
        if (actions.get(r["intent_id"]) != expected
                or r["intent_id"] != "ef19_" + _sha(_wire(packet))
                or r["state"] not in ("PREPARED", "RECORDED")
                or (r["state"] == "RECORDED") != bool(r["receipt_sha256"])):
            raise IntentRefused("EFFECT_AUDIT_OR_IDENTITY_MISMATCH")


def evaluate_effect_evidence(paths: EffectEvidencePaths) -> EffectEvidenceReport:
    """No writes, retries, dispatches, private code imports or live services."""
    if (os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"
            or not isinstance(paths, EffectEvidencePaths)):
        raise IntentRefused("EXPLICIT_READONLY_NONPRODUCTION_REQUIRED")
    inputs = tuple(_safe_file(getattr(paths, name), exists=True)
                   for name in ("effects", "runtime", "paper", "signal"))
    if len({(p.stat().st_dev, p.stat().st_ino) for p in inputs}) != len(inputs):
        raise IntentRefused("SHARED_EVIDENCE_FILES_REFUSED")
    with ExitStack() as stack:
        effects, runtime, paper, signal = (
            stack.enter_context(_read(path)) for path in inputs)
        intents = effects.execute("SELECT * FROM effect19_intents ORDER BY intent_id "
                                  "LIMIT 5001").fetchall()
        events = effects.execute("SELECT * FROM effect19_events ORDER BY seq "
                                 "LIMIT 10002").fetchall()
        if not intents or len(intents) > 5000 or len(events) > 10000:
            raise IntentRefused("NO_BOUNDED_INTENT_EVIDENCE")
        _verify_chain(intents, events)
        findings, rows = [], []
        for record in intents:
            job = runtime.execute(
                "SELECT status,instance_id,binding_id,payload FROM runtime17_jobs "
                "WHERE job_id=?", (record["job_id"],)).fetchone()
            job_state = job["status"] if job is not None else "MISSING"
            valid_job = (job is not None
                         and job["instance_id"] == record["instance_id"]
                         and job["binding_id"] == record["binding_id"])
            proof = _proof(record, paper, signal)
            if not valid_job or proof in ("TARGET_CONFLICT", "INVALID_EFFECT_KIND"):
                verdict = "BLOCKED_INCONSISTENT_EVIDENCE"
            elif proof == "AMBIGUOUS_OUTBOX":
                verdict = "BLOCKED_AMBIGUOUS_DELIVERY"
            elif proof == "NO_TARGET_RECORD":
                verdict = "UNKNOWN_NO_TARGET_NOT_SAFE_TO_RETRY"
            elif record["state"] == "PREPARED":
                verdict = "EFFECT_PRESENT_RECEIPT_GAP_MANUAL_REVIEW"
            elif job_state != "DONE":
                verdict = "EXACT_EFFECT_JOB_UNFINISHED_REVIEW"
            else:
                verdict = "EXACT_OFFLINE_EFFECT_CONFIRMED"
            findings.append(EffectFinding(
                record["intent_id"], record["job_id"], record["kind"],
                record["target_id"], record["state"], proof, job_state, verdict))
            rows.append({"effect": dict(record), "job": dict(job) if job else None,
                         "proof": proof})
        blocking = sum(f.verdict != "EXACT_OFFLINE_EFFECT_CONFIRMED" for f in findings)
        return EffectEvidenceReport(
            _sha(_wire({"effects": rows, "events": [dict(x) for x in events]})),
            tuple(findings), blocking,
            sum(f.verdict == "EXACT_OFFLINE_EFFECT_CONFIRMED" for f in findings),
            bool(blocking))


__all__ = ["EffectEvidencePaths", "EffectEvidenceReport", "EffectFinding",
           "evaluate_effect_evidence"]