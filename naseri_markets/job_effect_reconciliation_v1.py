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
            or "MMT_PRODUCTION" in os.environ
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



# Stage 9: an operator-facing DECISION TABLE over the existing Stage-19 proof.
# This is NOT an additional ledger or a capability to re-dispatch unknown work.
_ALLOWED_RECOVERY_KINDS = frozenset({"PAPER_RESERVE", "PAPER_PLAN", "DRY_SIGNAL"})


@dataclass(frozen=True, slots=True)
class RecoveryDecision:
    job_id: str
    kind: str
    intent_id: str | None
    classification: str
    action: str


@dataclass(frozen=True, slots=True)
class RecoveryDecisionTable:
    source_evidence_sha256: str
    decision_sha256: str
    decisions: tuple[RecoveryDecision, ...]
    reviewed_jobs: int
    blocking_decisions: int
    operator_review_required: bool
    verdict: str = "STAGE9_OFFLINE_SNAPSHOT_DECISIONS_ONLY"
    operator_expected_set_independently_attested: bool = False
    cross_database_atomicity_proven: bool = False
    exactly_once_proven: bool = False
    auto_retry_authorized: bool = False
    ledger_repair_authorized: bool = False
    telegram_send_authorized: bool = False
    broker_orders_authorized: bool = False
    live_trading_authorized: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


def _classify_recovery(finding: EffectFinding) -> str:
    """Only classify validated Stage-19 evidence, never infer a safe retry."""
    if finding.job_state == "MISSING":
        return "MISSING_JOB"
    if finding.target_evidence in ("TARGET_CONFLICT", "INVALID_EFFECT_KIND"):
        return "TARGET_CONFLICT"
    if finding.target_evidence == "AMBIGUOUS_OUTBOX":
        return "AMBIGUOUS_SIGNAL_OUTBOX"
    if finding.target_evidence == "NO_TARGET_RECORD":
        return ("RECORDED_TARGET_MISSING_CONFLICT" if
                finding.journal_state == "RECORDED" else "PREPARED_NO_TARGET_UNKNOWN")
    if finding.target_evidence == "EXACT_TARGET":
        if finding.journal_state == "PREPARED":
            return "TARGET_EXISTS_RECEIPT_GAP"
        if finding.journal_state == "RECORDED" and finding.job_state == "DONE":
            return "EXACT_TARGET_AND_RECEIPT"
        return "EXACT_TARGET_JOB_UNFINISHED"
    return "UNCLASSIFIED_EVIDENCE_BLOCKED"


def evaluate_recovery_decisions(
    paths: EffectEvidencePaths,
    *,
    expected_effect_kinds_by_job: dict[str, tuple[str, ...]],
    operator_ack: bool = False,
    all_writers_stopped: bool = False,
) -> RecoveryDecisionTable:
    """Require a frozen, owner-private snapshot and *complete* declared job inventory.

    Declared expected effects are OPERATOR ASSERTIONS, not publisher attestations.
    Even an all-exact result never authorizes retries, signals or trading.
    """
    if operator_ack is not True or all_writers_stopped is not True:
        raise IntentRefused("STAGE9_STOP_WRITERS_AND_EXPLICIT_ACK_REQUIRED")
    if (type(expected_effect_kinds_by_job) is not dict
            or not 1 <= len(expected_effect_kinds_by_job) <= 5000):
        raise IntentRefused("STAGE9_COMPLETE_EXPECTED_JOB_MAP_REQUIRED")
    for job_id, kinds in expected_effect_kinds_by_job.items():
        if (type(job_id) is not str or not 1 <= len(job_id) <= 130
                or type(kinds) is not tuple or len(kinds) > 3
                or any(type(k) is not str or k not in _ALLOWED_RECOVERY_KINDS
                       for k in kinds)
                or tuple(sorted(set(kinds))) != kinds):
            raise IntentRefused("STAGE9_INVALID_EXPECTED_EFFECT_SET")

    prior = evaluate_effect_evidence(paths)
    # Each database is read-only. Independent operator-frozen snapshots, not
    # sequential reads alone, are the mandatory precondition across DB roles.
    with _read(paths.runtime) as db:
        jobs = db.execute(
            "SELECT job_id,status FROM runtime17_jobs ORDER BY job_id LIMIT 5001"
        ).fetchall()
    if len(jobs) > 5000:
        raise IntentRefused("STAGE9_BOUNDED_RUNTIME_JOBS_REQUIRED")
    known_jobs = {job["job_id"]: job["status"] for job in jobs}
    if len(known_jobs) != len(jobs):
        raise IntentRefused("STAGE9_DUPLICATE_RUNTIME_JOBS")
    # A deleted/missing runtime row must be reported as MISSING_JOB, not
    # discarded from the evidence population or converted to an invented job.
    for finding in prior.findings:
        if finding.job_state == "MISSING" and finding.job_id not in known_jobs:
            known_jobs[finding.job_id] = "MISSING"
    if not known_jobs or len(known_jobs) > 5000:
        raise IntentRefused("STAGE9_BOUNDED_RUNTIME_JOBS_REQUIRED")
    if set(known_jobs) != set(expected_effect_kinds_by_job):
        raise IntentRefused("STAGE9_INCOMPLETE_JOB_INVENTORY")
    if any(
        finding.job_id not in known_jobs
        or finding.job_state != known_jobs[finding.job_id]
        for finding in prior.findings
    ):
        raise IntentRefused("STAGE9_NONFROZEN_OR_ORPHAN_JOB_EVIDENCE")

    decisions: list[RecoveryDecision] = []
    by_job: dict[str, list[EffectFinding]] = {key: [] for key in known_jobs}
    for finding in prior.findings:
        by_job[finding.job_id].append(finding)
        reason = _classify_recovery(finding)
        decisions.append(RecoveryDecision(
            finding.job_id, finding.kind, finding.intent_id, reason,
            "VERIFIED_ONLY_NO_REDISPATCH" if reason == "EXACT_TARGET_AND_RECEIPT"
            else "BLOCKED_OPERATOR_REVIEW",
        ))
    for job_id in sorted(known_jobs):
        actual = [f.kind for f in by_job[job_id]]
        expected = expected_effect_kinds_by_job[job_id]
        for kind in expected:
            if kind not in actual:
                decisions.append(RecoveryDecision(
                    job_id, kind, None, "MISSING_EFFECT_INTENT",
                    "BLOCKED_OPERATOR_REVIEW",
                ))
        for kind in sorted(set(actual)):
            if actual.count(kind) != 1 or kind not in expected:
                decisions.append(RecoveryDecision(
                    job_id, kind, None, "UNEXPECTED_OR_DUPLICATE_EFFECT_INTENT",
                    "BLOCKED_OPERATOR_REVIEW",
                ))
        if not actual:
            # PENDING with empty expected effects has no observed dispatch.
            # DONE with no effects cannot be shown to have completed any action.
            if known_jobs[job_id] == "PENDING" and not expected:
                classification, action = "PENDING_NO_DISPATCH", "NO_ACTION_AUTHORIZED"
            else:
                classification, action = "JOB_HAS_NO_EFFECT_PROOF", "BLOCKED_OPERATOR_REVIEW"
            decisions.append(RecoveryDecision(
                job_id, "JOB", None, classification, action,
            ))
    decisions.sort(key=lambda v: (v.job_id, v.kind, v.intent_id or "", v.classification))
    blocked = sum(d.action == "BLOCKED_OPERATOR_REVIEW" for d in decisions)
    digest_packet = {
        "source": prior.evidence_sha256,
        "expected": [
            (job_id, expected_effect_kinds_by_job[job_id])
            for job_id in sorted(expected_effect_kinds_by_job)
        ],
        "jobs": [(job_id, known_jobs[job_id]) for job_id in sorted(known_jobs)],
        "decisions": [asdict(d) for d in decisions],
    }
    return RecoveryDecisionTable(
        prior.evidence_sha256, _sha(_wire(digest_packet)),
        tuple(decisions), len(known_jobs), blocked, bool(blocked),
    )


__all__ = ["EffectEvidencePaths", "EffectEvidenceReport", "EffectFinding",
           "evaluate_effect_evidence", "RecoveryDecision", "RecoveryDecisionTable",
           "evaluate_recovery_decisions"]
