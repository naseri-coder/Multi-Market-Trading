"""Stage 19: durable PRE-call intent journal for Stage-17 -> Stage-16 PAPER.

An intent is written and committed BEFORE each target-ledger mutation.
A crash can still split two SQLite commits: inspect evidence, NEVER auto retry.
This is not a distributed transaction, recovery authority, or live executor.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
from decimal import Decimal
from pathlib import Path
from urllib.parse import quote

from .core_api_v1 import content_digest
from .offline_runtime_supervisor_v1 import ReplayJob, Stage16ReplayExecutor

_HEX = re.compile(r"[0-9a-f]{64}\Z")
_KINDS = frozenset({"PAPER_RESERVE", "PAPER_PLAN", "DRY_SIGNAL"})
_MAX = 5000


class IntentRefused(ValueError):
    """Stable fail-closed exception with no user-source or secret disclosure."""


def _wire(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_file(path: Path, *, exists: bool) -> Path:
    path = Path(path)
    if (not path.is_absolute() or path.is_symlink() or not path.parent.is_dir()
            or path.parent.is_symlink() or path.parent.stat().st_uid != os.geteuid()
            or stat.S_IMODE(path.parent.stat().st_mode) & 0o077):
        raise IntentRefused("PRIVATE_ABSOLUTE_STATE_REQUIRED")
    if path.exists():
        st = path.stat()
        if (not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid()
                or st.st_nlink != 1 or stat.S_IMODE(st.st_mode) & 0o077):
            raise IntentRefused("UNSAFE_EVIDENCE_FILE")
    elif exists:
        raise IntentRefused("EXISTING_EVIDENCE_REQUIRED")
    return path


class OfflineJobEffectLedger:
    """Dedicated journal, never mounted in broker, Telegram or live pathways."""

    def __init__(self, path: Path, *, enabled: bool = False):
        if (enabled is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
                or os.environ.get("MMT_PRODUCTION") == "1"):
            raise IntentRefused("EXPLICIT_NONPRODUCTION_LEDGER_REQUIRED")
        path = _safe_file(Path(path), exists=False)
        first = not path.exists()
        if first:
            fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
        db = sqlite3.connect(path, isolation_level=None, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            db.execute("PRAGMA busy_timeout=5000")
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("PRAGMA synchronous=FULL")
            if not first:
                tables = {r[0] for r in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
                if not {"effect19_intents", "effect19_events"} <= tables:
                    raise IntentRefused("UNKNOWN_INTENT_DATABASE")
            db.execute("""CREATE TABLE IF NOT EXISTS effect19_intents(
                intent_id TEXT PRIMARY KEY, job_id TEXT NOT NULL,
                kind TEXT NOT NULL CHECK(kind IN('PAPER_RESERVE','PAPER_PLAN','DRY_SIGNAL')),
                target_id TEXT NOT NULL, request_digest TEXT NOT NULL,
                instance_id TEXT NOT NULL, binding_id TEXT NOT NULL,
                decision_id TEXT NOT NULL, source_ref TEXT NOT NULL,
                event_digest TEXT NOT NULL, state TEXT NOT NULL
                  CHECK(state IN('PREPARED','RECORDED')),
                receipt_sha256 TEXT,
                UNIQUE(job_id,kind,target_id), UNIQUE(kind,target_id))""")
            db.execute("""CREATE TABLE IF NOT EXISTS effect19_events(
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                intent_id TEXT NOT NULL REFERENCES effect19_intents(intent_id),
                action TEXT NOT NULL CHECK(action IN('PREPARED','RECORDED')),
                payload_hash TEXT NOT NULL, prev_hash TEXT NOT NULL,
                chain_hash TEXT NOT NULL)""")
        except BaseException:
            db.close()
            raise
        self.db = db

    def close(self) -> None:
        self.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _event(self, intent_id: str, action: str, packet: object) -> None:
        prior = self.db.execute(
            "SELECT chain_hash FROM effect19_events ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        prev = prior["chain_hash"] if prior else "0" * 64
        payload = _sha(_wire(packet))
        chain = _sha(_wire([prev, intent_id, action, payload]))
        self.db.execute("INSERT INTO effect19_events(intent_id,action,payload_hash,"
                        "prev_hash,chain_hash) VALUES(?,?,?,?,?)",
                        (intent_id, action, payload, prev, chain))

    def prepare(self, job: ReplayJob, *, kind: str, target_id: str,
                request_digest: str, decision_id: str,
                event_digest: str) -> str:
        if (not isinstance(job, ReplayJob) or kind not in _KINDS
                or not isinstance(target_id, str) or len(target_id) > 130
                or not isinstance(decision_id, str) or len(decision_id) > 130
                or not isinstance(request_digest, str) or not _HEX.fullmatch(request_digest)
                or not isinstance(event_digest, str) or not _HEX.fullmatch(event_digest)):
            raise IntentRefused("INVALID_EFFECT_INTENT")
        packet = {"job_id": job.job_id, "kind": kind, "target_id": target_id,
                  "request_digest": request_digest, "instance_id": job.instance_id,
                  "binding_id": job.binding_id, "decision_id": decision_id,
                  "source_ref": job.source_ref, "event_digest": event_digest}
        intent_id = "ef19_" + _sha(_wire(packet))
        self.db.execute("BEGIN IMMEDIATE")
        try:
            prior = self.db.execute(
                "SELECT intent_id FROM effect19_intents WHERE kind=? AND target_id=?",
                (kind, target_id)).fetchone()
            if prior is not None:
                # PREPARED might already have committed remotely; RECORDED must
                # likewise never be treated as a fresh dispatch authorization.
                raise IntentRefused("EFFECT_ALREADY_ATTEMPTED_NO_AUTO_REPLAY")
            self.db.execute("INSERT INTO effect19_intents VALUES(" + ",".join("?" * 12) + ")",
                            (intent_id, job.job_id, kind, target_id, request_digest,
                             job.instance_id, job.binding_id, decision_id,
                             job.source_ref, event_digest, "PREPARED", None))
            self._event(intent_id, "PREPARED", packet)
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return intent_id

    def recorded(self, intent_id: str, *, target_id: str, receipt: object) -> None:
        if not isinstance(intent_id, str) or not isinstance(target_id, str):
            raise IntentRefused("INVALID_EFFECT_RECEIPT")
        digest = _sha(_wire(receipt))
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute("SELECT * FROM effect19_intents WHERE intent_id=?",
                                  (intent_id,)).fetchone()
            if row is None or row["state"] != "PREPARED" or row["target_id"] != target_id:
                raise IntentRefused("STALE_OR_MISMATCHED_RECEIPT")
            self.db.execute("UPDATE effect19_intents SET state='RECORDED',"
                            "receipt_sha256=? WHERE intent_id=?", (digest, intent_id))
            self._event(intent_id, "RECORDED", {"target_id": target_id,
                                                "receipt_sha256": digest})
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def intents(self, *, job_id: str | None = None) -> tuple[dict, ...]:
        if job_id is not None:
            rows = self.db.execute("SELECT * FROM effect19_intents WHERE job_id=? "
                                   "ORDER BY intent_id LIMIT ?", (job_id, _MAX + 1)).fetchall()
        else:
            rows = self.db.execute("SELECT * FROM effect19_intents ORDER BY intent_id "
                                   "LIMIT ?", (_MAX + 1,)).fetchall()
        if len(rows) > _MAX:
            raise IntentRefused("TOO_MANY_EFFECTS")
        return tuple(dict(r) for r in rows)


def _paper_order_id(binding: str, decision: str) -> str:
    digest = hashlib.sha256(json.dumps((binding, decision),
                   separators=(",", ":")).encode("utf-8")).hexdigest()
    return "pc8_" + digest[:60]


def _signal_contract(manifest, event, result, decision, *, channel_id,
                     price_basis, volume_semantics, expires_at) -> tuple[str, str]:
    # Mirrors the v1 exact identity and initial_digest contract. Any upstream
    # semantic change will fail evidence verification, not silently rekey.
    from .offline_signal_lifecycle_v1 import _digest, _utc
    identity = {"core": event.core_id, "version": event.core_version,
                "instance": event.binding.instance_id,
                "binding": event.binding.binding_id, "decision": decision.decision_id}
    target = _digest(identity)
    contract = {"identity": identity, "event": event.input_digest,
                "result": _digest(result), "channel": channel_id,
                "basis": price_basis.value, "volume": volume_semantics.value,
                "expires_at": _utc(expires_at).isoformat()}
    return target, _digest(contract)


class _Proxy:
    def __init__(self, target, ledger: OfflineJobEffectLedger, job: ReplayJob):
        self._target, self._ledger, self._job = target, ledger, job

    def __getattr__(self, name):
        return getattr(self._target, name)

    def _guard(self, event) -> None:
        if (event.binding.instance_id != self._job.instance_id
                or event.binding.binding_id != self._job.binding_id
                or event.source_ref != self._job.source_ref
                or event.origin.value not in ("replay", "synthetic")):
            raise IntentRefused("CROSS_JOB_EFFECT_REFUSED")


class _PaperProxy(_Proxy):
    def reserve_entry(self, manifest, event, result, *, decision_id,
                      quantity, price_basis, volume_semantics,
                      expected_allocation_revision, operator_ack=False):
        self._guard(event)
        if operator_ack is not True:
            raise IntentRefused("OPERATOR_ACK_REQUIRED")
        expected = _paper_order_id(event.binding.binding_id, decision_id)
        digest = content_digest({"manifest": manifest, "event": event, "result": result,
                                 "decision_id": decision_id, "quantity": quantity,
                                 "price_basis": price_basis,
                                 "volume_semantics": volume_semantics,
                                 "expected_revision": expected_allocation_revision})
        iid = self._ledger.prepare(self._job, kind="PAPER_RESERVE",
                        target_id=expected, request_digest=digest,
                        decision_id=decision_id, event_digest=event.input_digest)
        receipt = self._target.reserve_entry(
            manifest, event, result, decision_id=decision_id, quantity=quantity,
            price_basis=price_basis, volume_semantics=volume_semantics,
            expected_allocation_revision=expected_allocation_revision,
            operator_ack=True)
        if receipt.order_id != expected:
            raise IntentRefused("PAPER_ORDER_ID_DRIFT")
        self._ledger.recorded(iid, target_id=expected, receipt={
            "order_id": receipt.order_id, "decision_id": receipt.decision_id,
            "allocation_revision": receipt.allocation_revision})
        return receipt

    def register_plan(self, manifest, event, result, *, decision_id,
                      order_id, targets, operator_ack=False):
        self._guard(event)
        if operator_ack is not True or order_id != _paper_order_id(
                event.binding.binding_id, decision_id):
            raise IntentRefused("TARGET_PLAN_AUTHORIZATION_REFUSED")
        decision = next((d for d in result.decisions
                         if d.decision_id == decision_id), None)
        if decision is None:
            raise IntentRefused("PLAN_DECISION_MISSING")
        plan = {"decision_id": decision_id, "core_id": manifest.core_id,
                "core_version": manifest.core_version,
                "binding_id": event.binding.binding_id,
                "instance_id": event.binding.instance_id,
                "source_ref": event.source_ref, "timeframe": event.binding.timeframe,
                "market": event.binding.instrument.market.value,
                "targets": [{"price": str(t.price), "fraction": str(t.fraction)}
                            for t in targets]}
        digest = _sha(_wire(plan))
        iid = self._ledger.prepare(self._job, kind="PAPER_PLAN", target_id=order_id,
                      request_digest=digest, decision_id=decision_id,
                      event_digest=event.input_digest)
        receipt = self._target.register_plan(manifest, event, result,
                         decision_id=decision_id, order_id=order_id,
                         targets=targets, operator_ack=True)
        if receipt.get("order_id") != order_id or receipt.get("status") != "REGISTERED":
            raise IntentRefused("PAPER_PLAN_RECEIPT_INVALID")
        self._ledger.recorded(iid, target_id=order_id, receipt=receipt)
        return receipt


class _SignalProxy(_Proxy):
    def register(self, manifest, event, result, decision, *, channel_id,
                 price_basis, volume_semantics, expires_at, operator_ack=False):
        self._guard(event)
        if operator_ack is not True:
            raise IntentRefused("OPERATOR_ACK_REQUIRED")
        key, digest = _signal_contract(manifest, event, result, decision,
               channel_id=channel_id, price_basis=price_basis,
               volume_semantics=volume_semantics, expires_at=expires_at)
        iid = self._ledger.prepare(self._job, kind="DRY_SIGNAL", target_id=key,
                      request_digest=digest, decision_id=decision.decision_id,
                      event_digest=event.input_digest)
        receipt = self._target.register(manifest, event, result, decision,
                             channel_id=channel_id, price_basis=price_basis,
                             volume_semantics=volume_semantics,
                             expires_at=expires_at, operator_ack=True)
        if receipt.key != key or receipt.message_id is not None:
            raise IntentRefused("SIGNAL_IDENTITY_OR_SEND_VIOLATION")
        self._ledger.recorded(iid, target_id=key, receipt={"signal_key": key,
                                      "revision": receipt.revision})
        return receipt


class JobEffectIntentExecutor:
    """Stage-17 callback using Stage-16, with pre-call exact effect intents.

    Deliberately not installed in any bot or background runner. One operator
    call is necessary; restart never automatically resumes an uncertain job.
    """

    def __init__(self, *, supervisor, ledger: OfflineJobEffectLedger,
                 integration, paper=None, signals=None, quantity: Decimal | None = None,
                 dry_run_channel_id: int | None = None):
        from .offline_runtime_supervisor_v1 import OfflineRuntimeSupervisor
        if not isinstance(supervisor, OfflineRuntimeSupervisor) or not isinstance(
                ledger, OfflineJobEffectLedger):
            raise IntentRefused("OPERATOR_SUPERVISOR_REQUIRED")
        self.supervisor, self.ledger = supervisor, ledger
        self.integration, self.paper, self.signals = integration, paper, signals
        self.quantity, self.channel = quantity, dry_run_channel_id

    def __call__(self, job: ReplayJob) -> dict:
        row = self.supervisor.db.execute(
            "SELECT status,instance_id,binding_id FROM runtime17_jobs WHERE job_id=?",
            (job.job_id,)).fetchone()
        if (row is None or row["status"] != "CLAIMED"
                or row["instance_id"] != job.instance_id
                or row["binding_id"] != job.binding_id):
            raise IntentRefused("ONLY_CURRENTLY_CLAIMED_JOB")
        if self.ledger.intents(job_id=job.job_id):
            raise IntentRefused("EXISTING_JOB_EFFECTS_REQUIRE_MANUAL_REVIEW")
        paper = _PaperProxy(self.paper, self.ledger, job) if self.paper is not None else None
        signals = _SignalProxy(self.signals, self.ledger, job) if self.signals is not None else None
        delegate = Stage16ReplayExecutor(self.integration, paper=paper, signals=signals,
                                         quantity=self.quantity,
                                         dry_run_channel_id=self.channel)
        return delegate(job)


__all__ = ["OfflineJobEffectLedger", "JobEffectIntentExecutor", "IntentRefused"]
