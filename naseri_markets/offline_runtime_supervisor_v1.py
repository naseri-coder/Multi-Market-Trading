"""Stage 17: durable operator-driven OFFLINE scheduler for reviewed PAPER cores.

No polling loop, untrusted-code load, API transport, Telegram send, or live order.
Cross-ledger side effects are NOT atomic: interrupted attempts stay CLAIMED
until an operator quarantines them after independently stopping all workers.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import stat
from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Callable, Mapping

from .core_api_v1 import ClosedCandle, DataOrigin
from .trading_control_center_v1 import OfflineTradingControlCenter


class SupervisorRefused(ValueError):
    """Fail-closed, never a network or trading permission."""


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise SupervisorRefused("UTC_AWARE_TIME_REQUIRED")
    return value.astimezone(UTC)


def _wire(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _encode_candles(candles: tuple[ClosedCandle, ...]) -> list[dict]:
    if not isinstance(candles, tuple) or not 1 <= len(candles) <= 128:
        raise SupervisorRefused("BOUNDED_CANDLES_REQUIRED")
    result = []
    for bar in candles:
        if not isinstance(bar, ClosedCandle):
            raise SupervisorRefused("CLOSED_CANDLE_REQUIRED")
        result.append({"open_at": bar.open_at.isoformat(),
                       "close_at": bar.close_at.isoformat(),
                       **{key: str(getattr(bar, key))
                          for key in ("open", "high", "low", "close", "volume")}})
    if any(x.close_at != y.open_at for x, y in zip(candles, candles[1:])):
        raise SupervisorRefused("NONCONTIGUOUS_REPLAY")
    return result


def _decode_candles(value: object) -> tuple[ClosedCandle, ...]:
    if not isinstance(value, list) or not 1 <= len(value) <= 128:
        raise SupervisorRefused("INVALID_STORED_CANDLES")
    result = tuple(ClosedCandle(
        datetime.fromisoformat(v["open_at"]), datetime.fromisoformat(v["close_at"]),
        *(Decimal(v[name]) for name in ("open", "high", "low", "close", "volume")))
        for v in value)
    if _encode_candles(result) != value:
        raise SupervisorRefused("NONCANONICAL_STORED_CANDLES")
    return result


@dataclass(frozen=True, slots=True)
class ReplayJob:
    job_id: str
    instance_id: str
    binding_id: str
    expected_panel_revision: int
    source_ref: str
    candles: tuple[ClosedCandle, ...]


class OfflineRuntimeSupervisor:
    """Single local SQLite queue, no implicit scheduler startup or retries."""

    def __init__(self, db_path: str | Path, *, panel: OfflineTradingControlCenter,
                 actor_id: int, enabled: bool = False):
        if (enabled is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
                or os.environ.get("MMT_PRODUCTION") == "1"
                or not isinstance(panel, OfflineTradingControlCenter)
                or type(actor_id) is not int or actor_id <= 0):
            raise SupervisorRefused("NONPRODUCTION_OPERATOR_REQUIRED")
        panel._auth(actor_id)
        path = Path(db_path)
        parent = path.parent
        if (not path.is_absolute() or path.is_symlink() or not parent.is_dir()
                or parent.is_symlink() or stat.S_IMODE(parent.stat().st_mode) & 0o077
                or parent.stat().st_uid != os.geteuid()
                or (path.exists() and (not path.is_file()
                                      or path.stat().st_nlink != 1
                                      or stat.S_IMODE(path.stat().st_mode) & 0o077))):
            raise SupervisorRefused("PRIVATE_DEDICATED_STATE_REQUIRED")
        first = not path.exists()
        if first:
            try:
                fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError as exc:
                raise SupervisorRefused("STATE_CREATE_RACE") from exc
            os.close(fd)
        self.panel, self.actor_id = panel, actor_id
        self.db = sqlite3.connect(path, isolation_level=None, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.execute("PRAGMA foreign_keys=ON")
        if not first:
            tables = {row[0] for row in self.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            if "runtime17_jobs" not in tables:
                self.db.close()
                raise SupervisorRefused("UNKNOWN_DATABASE_REFUSED")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS runtime17_jobs (
                job_id TEXT PRIMARY KEY, instance_id TEXT NOT NULL,
                binding_id TEXT NOT NULL, panel_revision INTEGER NOT NULL,
                due_at TEXT NOT NULL, payload TEXT NOT NULL, digest TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN
                    ('PENDING','CLAIMED','DONE','QUARANTINED')),
                attempt INTEGER NOT NULL DEFAULT 0,
                claim_token TEXT, result_hash TEXT, error_code TEXT);
            CREATE INDEX IF NOT EXISTS runtime17_due ON runtime17_jobs(status,due_at);
        """)

    def close(self) -> None:
        self.db.close()

    def __enter__(self) -> OfflineRuntimeSupervisor:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _validate_panel(self, instance_id: str, binding_id: str,
                        revision: int, at: datetime) -> None:
        view = self.panel.inspect(self.actor_id, instance_id)
        if (view.revision != revision or
                not (view.analysis_requested or view.telegram_signals_requested
                     or view.paper_orders_requested) or view.telegram_publication_enabled
                or view.broker_orders_enabled or view.live_trading_enabled):
            raise SupervisorRefused("STALE_OR_DISABLED_PANEL")
        selected = self.panel.preview_bindings(self.actor_id, instance_id, now=at)
        if not any(b.binding_id == binding_id for b in selected):
            raise SupervisorRefused("BINDING_NOT_APPROVED")

    def schedule(self, instance_id: str, binding_id: str, *,
                 expected_panel_revision: int, candles: tuple[ClosedCandle, ...],
                 source_ref: str, due_at: datetime, operator_ack: bool = False) -> str:
        if (operator_ack is not True or type(expected_panel_revision) is not int
                or expected_panel_revision <= 0 or type(source_ref) is not str
                or not 1 <= len(source_ref) <= 120
                or not all(ch.isascii() and (ch.isalnum() or ch in "_.:-")
                           for ch in source_ref)):
            raise SupervisorRefused("EXPLICIT_SCHEDULE_INPUT_REQUIRED")
        packet = {"instance_id": instance_id, "binding_id": binding_id,
                  "panel_revision": expected_panel_revision,
                  "source_ref": source_ref, "candles": _encode_candles(candles)}
        when = _utc(due_at)
        if when < candles[-1].close_at:
            raise SupervisorRefused("CANNOT_SCHEDULE_OPEN_CANDLE")
        self._validate_panel(instance_id, binding_id, expected_panel_revision,
                             candles[-1].close_at)
        payload = _wire(packet)
        job_id = "job17_" + _hash(payload)
        self.db.execute("BEGIN IMMEDIATE")
        try:
            exists = self.db.execute(
                "SELECT digest FROM runtime17_jobs WHERE job_id=?", (job_id,)).fetchone()
            if exists is None:
                self.db.execute("INSERT INTO runtime17_jobs "
                                "(job_id,instance_id,binding_id,panel_revision,due_at,"
                                "payload,digest,status) VALUES (?,?,?,?,?,?,?,'PENDING')",
                                (job_id, instance_id, binding_id, expected_panel_revision,
                                 when.isoformat(), payload, _hash(payload)))
            elif exists["digest"] != _hash(payload):
                raise SupervisorRefused("QUEUE_IDENTITY_CONFLICT")
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return job_id

    def _claim(self, now: datetime) -> tuple[sqlite3.Row, str] | None:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            row = self.db.execute("""
                SELECT j.* FROM runtime17_jobs j
                WHERE j.status='PENDING' AND j.due_at<=?
                  AND NOT EXISTS (SELECT 1 FROM runtime17_jobs earlier
                      WHERE earlier.binding_id=j.binding_id
                        AND earlier.status IN ('CLAIMED','QUARANTINED'))
                ORDER BY j.due_at,j.job_id LIMIT 1
            """, (_utc(now).isoformat(),)).fetchone()
            if row is None:
                self.db.execute("COMMIT")
                return None
            token = secrets.token_hex(24)
            self.db.execute("UPDATE runtime17_jobs SET status='CLAIMED',attempt=1,"
                            "claim_token=? WHERE job_id=? AND status='PENDING'",
                            (token, row["job_id"]))
            self.db.execute("COMMIT")
            return row, token
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def _finalize(self, job_id: str, token: str, *, status: str,
                  result_hash: str | None = None, error_code: str | None = None) -> None:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            cur = self.db.execute(
                "UPDATE runtime17_jobs SET status=?,claim_token=NULL,result_hash=?,"
                "error_code=? WHERE job_id=? AND status='CLAIMED' AND claim_token=?",
                (status, result_hash, error_code, job_id, token))
            if cur.rowcount != 1:
                raise SupervisorRefused("CLAIM_FENCE_LOST")
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def run_due(self, execute: Callable[[ReplayJob], Mapping[str, object]], *,
                now: datetime, limit: int = 1,
                operator_ack: bool = False) -> tuple[dict, ...]:
        if (operator_ack is not True or not callable(execute)
                or type(limit) is not int or not 1 <= limit <= 25):
            raise SupervisorRefused("EXPLICIT_BOUNDED_EXECUTION_REQUIRED")
        outputs: list[dict] = []
        for _ in range(limit):
            claimed = self._claim(now)
            if claimed is None:
                break
            row, token = claimed
            try:
                if row["digest"] != _hash(row["payload"]):
                    raise SupervisorRefused("JOB_PAYLOAD_TAMPERED")
                packet = json.loads(row["payload"])
                bars = _decode_candles(packet["candles"])
                if (packet["instance_id"] != row["instance_id"]
                        or packet["binding_id"] != row["binding_id"]
                        or packet["panel_revision"] != row["panel_revision"]):
                    raise SupervisorRefused("JOB_IDENTITY_TAMPERED")
                self._validate_panel(row["instance_id"], row["binding_id"],
                                     row["panel_revision"], bars[-1].close_at)
                job = ReplayJob(row["job_id"], row["instance_id"],
                                row["binding_id"], row["panel_revision"],
                                packet["source_ref"], bars)
                outcome = execute(job)
                if (not isinstance(outcome, Mapping)
                        or outcome.get("status") not in
                        ("OFFLINE_JOURNALS_UPDATED", "NO_EVALUATION")
                        or outcome.get("broker_order_sent") is not False
                        or outcome.get("telegram_sent") is not False
                        or outcome.get("live_trading_enabled", False) is not False):
                    raise SupervisorRefused("UNSAFE_EXECUTOR_RECEIPT")
                self._validate_panel(row["instance_id"], row["binding_id"],
                                     row["panel_revision"], bars[-1].close_at)
                digest = _hash(_wire(dict(outcome)))
                self._finalize(job.job_id, token, status="DONE", result_hash=digest)
                outputs.append({"job_id": job.job_id, "status": "DONE",
                                "result_hash": digest})
            except Exception:
                # Even a failure may have written Stage-8/9/10 journals.
                # Never auto retry; operator must reconcile independently.
                self._finalize(row["job_id"], token, status="QUARANTINED",
                               error_code="RECONCILIATION_REQUIRED")
                outputs.append({"job_id": row["job_id"], "status": "QUARANTINED",
                                "reconciliation_required": True})
        return tuple(outputs)

    def quarantine_inflight(self, *, operator_ack: bool = False,
                            all_workers_stopped: bool = False) -> int:
        """ONLY after operator has positively stopped every possible worker.

        NEVER retries an interrupted call: it might have committed other DBs.
        """
        if operator_ack is not True or all_workers_stopped is not True:
            raise SupervisorRefused("STOP_ALL_WORKERS_AND_ACK_REQUIRED")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            count = self.db.execute(
                "UPDATE runtime17_jobs SET status='QUARANTINED',claim_token=NULL,"
                "error_code='CRASH_RECONCILIATION_REQUIRED' WHERE status='CLAIMED'").rowcount
            self.db.execute("COMMIT")
            return count
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def health(self) -> dict:
        counts = {row["status"]: row["n"] for row in self.db.execute(
            "SELECT status,COUNT(*) AS n FROM runtime17_jobs GROUP BY status")}
        return {"mode": "OFFLINE_OPERATOR_DRIVEN_SUPERVISOR",
                "counts": {k: counts.get(k, 0) for k in
                           ("PENDING", "CLAIMED", "DONE", "QUARANTINED")},
                "manual_reconciliation_required": bool(counts.get("CLAIMED", 0)
                                                       or counts.get("QUARANTINED", 0)),
                "background_poller": False, "telegram_sent": False,
                "broker_order_sent": False, "live_trading_enabled": False}

    def jobs(self) -> tuple[dict, ...]:
        return tuple(dict(row) for row in self.db.execute(
            "SELECT job_id,instance_id,binding_id,panel_revision,due_at,status,"
            "attempt,result_hash,error_code FROM runtime17_jobs "
            "ORDER BY due_at,job_id LIMIT 1000"))


class Stage16ReplayExecutor:
    """Explicitly preconfigured Stage-16 replay adapter; never authorizes PAPER."""

    def __init__(self, integration, *, paper=None, signals=None,
                 quantity: Decimal | None = None,
                 dry_run_channel_id: int | None = None,
                 data_origin: DataOrigin = DataOrigin.SYNTHETIC):
        from .offline_panel_paper_integration_v1 import OfflinePanelPaperIntegration
        if not isinstance(integration, OfflinePanelPaperIntegration):
            raise SupervisorRefused("REVIEWED_STAGE16_HOST_REQUIRED")
        self.integration, self.paper, self.signals = integration, paper, signals
        if data_origin not in (DataOrigin.REPLAY, DataOrigin.SYNTHETIC):
            raise SupervisorRefused("OFFLINE_ORIGIN_REQUIRED")
        self.quantity, self.channel = quantity, dry_run_channel_id
        self.data_origin = data_origin

    def __call__(self, job: ReplayJob) -> dict:
        outcome = self.integration.replay_candles(
            job.instance_id, job.binding_id, candles=job.candles,
            source_ref=job.source_ref,
            expected_panel_revision=job.expected_panel_revision,
            operator_ack=True, paper=self.paper, signals=self.signals,
            quantity=self.quantity, dry_run_channel_id=self.channel,
            data_origin=self.data_origin)
        if is_dataclass(outcome):
            # Compatibility with the Stage-16 local candidate dataclass;
            # the merged GitHub Stage-16 release returns a canonical dict.
            data = asdict(outcome)
            data["signal_keys"] = data.pop("dry_run_signal_keys", ())
            data["status"] = ("NO_EVALUATION" if data.get("status") in
                              ("NO_ENTRY_INTENT", "NO_EVALUATION_YET")
                              else data.get("status"))
            return data
        return outcome


__all__ = ["OfflineRuntimeSupervisor", "ReplayJob", "Stage16ReplayExecutor",
           "SupervisorRefused"]
