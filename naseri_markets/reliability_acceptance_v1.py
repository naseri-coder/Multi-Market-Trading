"""Stage 13: read-only NONPRODUCTION cross-ledger reliability acceptance.

This code neither joins operational databases nor grants ANY execution,
publication, feed or hostile plugin permission. It inspects three *dedicated*
existing offline SQLite journals from Stages 12, 8/9, and 10. It is a proof
checker, not an orchestrator, telemetry service, deployment, or live gate.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from contextlib import ExitStack, contextmanager
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterator
from urllib.parse import quote


class AcceptanceRefused(ValueError):
    """Invalid or unbounded evidence is not a clean audit result."""


_ROLE_TABLES = {
    "control": {"t12_instances", "t12_bindings", "t12_audit"},
    "paper": {"paper_core_orders", "paper_core_allocations", "paper_core_bindings",
              "paper_core_decisions", "paper_risk_reservations", "paper_orders",
              "paper_stage9_plans", "paper_stage9_exits", "paper_stage9_bars"},
    "signal": {"offline_signal_states", "offline_signal_events", "offline_signal_commands"},
}
_HASH = re.compile(r"[0-9a-f]{64}\Z")
MAX_ROWS_PER_TABLE = 50_000
MAX_DATABASE_BYTES = 512 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class LedgerPaths:
    control: Path
    paper: Path
    signal: Path


@dataclass(frozen=True, slots=True)
class GateResult:
    schema_version: int
    mode: str
    integrity_verdict: str
    release_verdict: str
    counts: dict[str, int]
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    evidence_digest: str
    telegram_sent: bool = False
    broker_order_sent: bool = False
    production_authorized: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


def _json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False)


def _checked_path(value: Path, role: str) -> Path:
    if not isinstance(value, Path):
        raise AcceptanceRefused("PATH_OBJECT_REQUIRED")
    if (value.is_symlink() or not value.is_file() or value.stat().st_size > MAX_DATABASE_BYTES
            or value.stat().st_size < 100):
        raise AcceptanceRefused("EXISTING_REGULAR_OFFLINE_DB_REQUIRED:" + role)
    return value.absolute()


@contextmanager
def _readonly(path: Path) -> Iterator[sqlite3.Connection]:
    # Explicit `ro`, never `rwc`, avoids silently creating missing evidence.
    url = "file:" + quote(str(path), safe="/") + "?mode=ro"
    try:
        connection = sqlite3.connect(url, uri=True, timeout=3, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA busy_timeout=3000")
        connection.execute("BEGIN")  # stable WAL read snapshot
        try:
            yield connection
        finally:
            connection.execute("ROLLBACK")
            connection.close()
    except sqlite3.DatabaseError as exc:
        raise AcceptanceRefused("UNREADABLE_SQLITE_EVIDENCE") from exc


def _rows(db: sqlite3.Connection, table: str) -> list[sqlite3.Row]:
    if table not in set().union(*_ROLE_TABLES.values()):
        raise AcceptanceRefused("UNKNOWN_EVIDENCE_TABLE")
    sample = db.execute(f"SELECT * FROM {table} LIMIT ?", (MAX_ROWS_PER_TABLE + 1,)).fetchall()
    if len(sample) > MAX_ROWS_PER_TABLE:
        raise AcceptanceRefused("EVIDENCE_ROWS_EXCEED_BOUND:" + table)
    return sample


def _schema(db: sqlite3.Connection, role: str) -> None:
    found = {r["name"] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    if not _ROLE_TABLES[role].issubset(found):
        raise AcceptanceRefused("STAGE_SCHEMA_MISSING:" + role)
    if db.execute("PRAGMA quick_check(1)").fetchone()[0] != "ok":
        raise AcceptanceRefused("SQLITE_QUICK_CHECK_FAILED:" + role)
    if db.execute("SELECT * FROM pragma_foreign_key_check LIMIT 1").fetchone():
        raise AcceptanceRefused("SQLITE_FOREIGN_KEY_CHECK_FAILED:" + role)


def _number(value: object) -> Decimal:
    if not isinstance(value, str):
        raise AcceptanceRefused("NONCANONICAL_NUMERIC_EVIDENCE")
    try:
        num = Decimal(value)
    except InvalidOperation as exc:
        raise AcceptanceRefused("INVALID_NUMERIC_EVIDENCE") from exc
    if not num.is_finite():
        raise AcceptanceRefused("NONFINITE_EVIDENCE")
    return num


def _snapshot(value: str) -> dict:
    try:
        obj = json.loads(value)
        if type(obj) is not dict:
            raise ValueError()
    except (ValueError, TypeError) as exc:
        raise AcceptanceRefused("INVALID_ORDER_SNAPSHOT") from exc
    return obj


def evaluate_offline_reliability(paths: LedgerPaths) -> GateResult:
    """Check independent offline journals without mutation or permissive fallback.

    PASS means these on-disk *local* invariants hold. The release verdict is
    always BLOCKED: no real provider/Telegram attestation and no certified
    adversarial sandbox are established by these evidence files.
    """
    if not isinstance(paths, LedgerPaths):
        raise AcceptanceRefused("THREE_EVIDENCE_PATHS_REQUIRED")
    names = {role: _checked_path(getattr(paths, role), role) for role in _ROLE_TABLES}
    if (len(set(names.values())) != 3 or
            len({(p.stat().st_dev, p.stat().st_ino) for p in names.values()}) != 3):
        raise AcceptanceRefused("SHARED_DATABASE_ROLES_FORBIDDEN")
    findings: set[str] = set()
    warnings: set[str] = set()
    evidence: dict[str, object] = {}
    with ExitStack() as stack:
        dbs = {role: stack.enter_context(_readonly(path)) for role, path in names.items()}
        for role, conn in dbs.items():
            _schema(conn, role)
        instances = _rows(dbs["control"], "t12_instances")
        bindings = _rows(dbs["control"], "t12_bindings")
        audit = _rows(dbs["control"], "t12_audit")
        allocations = _rows(dbs["paper"], "paper_core_allocations")
        paper_bindings = _rows(dbs["paper"], "paper_core_bindings")
        paper_orders = _rows(dbs["paper"], "paper_core_orders")
        decisions = _rows(dbs["paper"], "paper_core_decisions")
        reservations = _rows(dbs["paper"], "paper_risk_reservations")
        orders = _rows(dbs["paper"], "paper_orders")
        plans = _rows(dbs["paper"], "paper_stage9_plans")
        exits = _rows(dbs["paper"], "paper_stage9_exits")
        bars = _rows(dbs["paper"], "paper_stage9_bars")
        signals = _rows(dbs["signal"], "offline_signal_states")
        signal_events = _rows(dbs["signal"], "offline_signal_events")
        commands = _rows(dbs["signal"], "offline_signal_commands")

        by_instance = {r["instance_id"]: r for r in instances}
        by_binding = {r["binding_id"]: r for r in bindings}
        by_allocation = {r["instance_id"]: r for r in allocations}
        by_paper_binding = {r["binding_id"]: r for r in paper_bindings}
        by_order = {r["order_id"]: _snapshot(r["snapshot"]) for r in orders}
        by_plan = {r["order_id"]: r for r in plans}
        by_reservation = {r["order_id"]: r for r in reservations}
        by_core_order = {r["order_id"]: r for r in paper_orders}
        by_signal = {r["signal_key"]: r for r in signals}
        if not instances:
            findings.add("NO_CONFIGURED_CORE_INSTANCE")
        if not bindings:
            findings.add("NO_CONFIGURED_BINDING")
        if not (paper_orders or signals):
            findings.add("NO_EVALUATED_OUTPUT_EVIDENCE")
        # The settings database intentionally contains requests, not grants.
        for row in instances:
            if row["revision"] < 1 or row["created_by"] <= 0:
                findings.add("CONTROL_REVISION_OR_ACTOR_INVALID")
            if row["core_id"] == "ny_first_reversal":
                warnings.add("OWNER_ONLY_METADATA_PRESENT_NOT_PLUGIN_CODE")
        for row in bindings:
            if row["instance_id"] not in by_instance:
                findings.add("ORPHAN_CONTROL_BINDING")
        for row in allocations:
            if row["instance_id"] not in by_instance:
                findings.add("UNTRACKED_PAPER_CORE_INSTANCE")
        for row in paper_bindings:
            ctrl = by_binding.get(row["binding_id"])
            if ctrl is None or ctrl["instance_id"] != row["instance_id"]:
                findings.add("PAPER_BINDING_NOT_IN_CONTROL_CENTER")
            if row["instance_id"] not in by_allocation:
                findings.add("UNALLOCATED_PAPER_BINDING")
        for row in paper_orders:
            ctrl = by_binding.get(row["binding_id"])
            if (ctrl is None or ctrl["instance_id"] != row["instance_id"] or
                    row["binding_id"] not in by_paper_binding):
                findings.add("PAPER_ORDER_BINDING_MISMATCH")
            allocation = by_allocation.get(row["instance_id"])
            if allocation is None:
                findings.add("PAPER_ORDER_ALLOCATION_MISSING")
            else:
                try:
                    policy = json.loads(allocation["policy_json"])
                    if (row["instance_id"] not in by_instance or
                            policy["account_id"] != row["account_id"] or
                            policy["instance_id"] != row["instance_id"] or
                            policy["core_id"] != by_instance[row["instance_id"]]["core_id"]):
                        findings.add("PAPER_ACCOUNT_OR_CORE_MISMATCH")
                    else:
                        control_policy = by_instance[row["instance_id"]]
                        allocations_to_compare = (
                            ("max_reserved", "max_reserved_risk_fraction"),
                            ("max_notional", "max_notional_fraction"),
                            ("max_order", "max_order_risk_fraction"),
                        )
                        if (any(_number(control_policy[local]) != _number(policy[remote])
                                for local,remote in allocations_to_compare)
                                or control_policy["max_orders"] != policy["max_active_orders"]):
                            findings.add("PANEL_TO_PAPER_RISK_BUDGET_DRIFT")
                except (ValueError, KeyError, TypeError, AcceptanceRefused):
                    findings.add("INVALID_PAPER_ALLOCATION_POLICY")
            snap = by_order.get(row["order_id"])
            if snap is None:
                findings.add("ORPHAN_PAPER_ORDER")
                continue
            try:
                spec = snap["spec"]
                inst = spec["instrument"]
                if (row["instance_id"] not in by_instance or ctrl is None or
                        spec["account_id"] != row["account_id"] or
                        spec["engine_id"] != by_instance[row["instance_id"]]["core_id"] or
                        inst["market"] != ctrl["market"] or
                        inst["provider"] != ctrl["provider"] or
                        inst["symbol"] != ctrl["symbol"]):
                    findings.add("PAPER_INSTRUMENT_IDENTITY_MISMATCH")
            except (KeyError, TypeError):
                findings.add("INVALID_PAPER_ORDER_SPEC")
            if row["order_id"] not in by_reservation:
                findings.add("PAPER_ORDER_RISK_RESERVATION_MISSING")
            if row["order_id"] not in by_plan:
                warnings.add("PAPER_ORDER_STAGE9_PLAN_NOT_REGISTERED")
        for row in reservations:
            snap = by_order.get(row["order_id"])
            if snap is None or row["order_id"] not in by_core_order:
                findings.add("ORPHAN_RISK_RESERVATION")
                continue
            try:
                filled = _number(snap["filled_quantity"])
                closed = _number(snap["closed_quantity"])
                if filled < closed or closed < 0:
                    findings.add("NEGATIVE_OR_OVERCLOSED_POSITION")
                terminal = (snap["status"] in ("REJECTED", "CLOSED") or
                            (snap["status"] == "CANCELED" and filled == 0))
                if row["status"] == "RELEASED" and not terminal:
                    findings.add("RISK_RELEASED_ON_OPEN_POSITION")
                if row["status"] == "ACTIVE" and terminal:
                    findings.add("TERMINAL_ORDER_RISK_STILL_RESERVED")
            except (KeyError, TypeError, AcceptanceRefused):
                findings.add("INVALID_ORDER_POSITION_STATE")
        for row in decisions:
            if row["order_id"] not in by_core_order:
                findings.add("ORPHAN_CORE_DECISION")
        for row in plans:
            if row["order_id"] not in by_core_order:
                findings.add("ORPHAN_STAGE9_PLAN")
        for row in exits:
            if row["order_id"] not in by_plan:
                findings.add("ORPHAN_MODELED_EXIT")
        for row in bars:
            if row["order_id"] not in by_plan:
                findings.add("ORPHAN_REPLAY_BAR")
        for row in signals:
            ctrl = by_binding.get(row["binding_id"])
            if (ctrl is None or row["instance_id"] not in by_instance or
                    ctrl["instance_id"] != row["instance_id"] or
                    row["core_id"] != by_instance[row["instance_id"]]["core_id"] or
                    row["market"] != ctrl["market"] or row["provider"] != ctrl["provider"] or
                    row["symbol"] != ctrl["symbol"]):
                findings.add("ORPHAN_OR_MISMATCHED_SIGNAL_BINDING")
            if row["status"] not in ("WAITING_ENTRY", "ACTIVE", "STOPPED", "TARGETS_COMPLETE", "EXPIRED"):
                findings.add("UNKNOWN_SIGNAL_STATE")
        for row in signal_events:
            if row["signal_key"] not in by_signal:
                findings.add("ORPHAN_SIGNAL_EVENT")
            if not isinstance(row["payload_sha256"], str) or not _HASH.fullmatch(row["payload_sha256"]):
                findings.add("INVALID_SIGNAL_EVENT_HASH")
            elif hashlib.sha256(row["payload_json"].encode("utf-8")).hexdigest() != row["payload_sha256"]:
                findings.add("SIGNAL_EVENT_CONTENT_TAMPERED")
        for row in commands:
            signal = by_signal.get(row["signal_key"])
            if signal is None:
                findings.add("ORPHAN_SIGNAL_OUTBOX_COMMAND")
                continue
            if row["channel_id"] != signal["channel_id"]:
                findings.add("CROSS_CHANNEL_SIGNAL_COMMAND")
            if row["state"] in ("CLAIMED", "UNKNOWN"):
                findings.add("DELIVERY_AMBIGUOUS_REQUIRES_OPERATOR_RECONCILIATION")
            if row["state"] == "SIMULATED_ACK" and (
                    row["message_id"] is None or row["message_id"] <= 0):
                findings.add("ACK_WITHOUT_SIMULATED_MESSAGE_ID")
        linked_bindings = set(by_binding) & (set(by_paper_binding) | {r["binding_id"] for r in signals})
        if not linked_bindings:
            findings.add("NO_CROSS_STAGE_BINDING_EVIDENCE")
        if not audit:
            warnings.add("NO_CONTROL_AUDIT_TRAIL")
        else:
            # Stage-12 global append-only hash chain; a digest can detect local
            # mutation, not prove who wrote the payload or when it was written.
            chain_prev = "0" * 64
            last_rev: dict[str, int] = {}
            for row in sorted(audit, key=lambda r: r["seq"]):
                try:
                    raw = _json([chain_prev, row["instance_id"], row["actor_id"],
                                 row["revision"], row["action"], row["payload_hash"]])
                    expected = hashlib.sha256(raw.encode("utf-8")).hexdigest()
                    if (row["prev_hash"] != chain_prev or row["entry_hash"] != expected or
                            not _HASH.fullmatch(row["payload_hash"])):
                        findings.add("CONTROL_AUDIT_HASH_CHAIN_TAMPERED")
                    previous = last_rev.get(row["instance_id"], 0)
                    if row["revision"] != previous + 1:
                        findings.add("CONTROL_AUDIT_REVISION_GAP")
                    last_rev[row["instance_id"]] = row["revision"]
                    chain_prev = row["entry_hash"]
                except (KeyError, TypeError, ValueError):
                    findings.add("INVALID_CONTROL_AUDIT_EVENT")
            for item in instances:
                if last_rev.get(item["instance_id"]) != item["revision"]:
                    findings.add("CONTROL_STATE_AUDIT_REVISION_MISMATCH")
        if not paper_orders:
            warnings.add("NO_PAPER_ORDER_EVIDENCE_SIGNAL_ONLY_IS_VALID")
        if not signals:
            warnings.add("NO_SIGNAL_EVIDENCE_PAPER_ONLY_IS_VALID")
        counts = {
            "control_instances": len(instances), "control_bindings": len(bindings),
            "paper_allocations": len(allocations), "paper_orders": len(paper_orders),
            "paper_plans": len(plans), "paper_exits": len(exits),
            "paper_bars": len(bars), "signal_states": len(signals),
            "signal_events": len(signal_events), "signal_commands": len(commands),
            "cross_stage_bindings": len(linked_bindings),
        }
        # Deterministic digest of bounded evidence contents, NOT a provenance
        # attestation of market data, code, Telegram or execution.
        for role, conn in dbs.items():
            evidence[role] = {table: [dict(row) for row in _rows(conn, table)]
                              for table in sorted(_ROLE_TABLES[role])}
        digest = hashlib.sha256(_json(evidence).encode("utf-8")).hexdigest()
    return GateResult(
        schema_version=1, mode="OFFLINE_EVIDENCE_INSPECTION_ONLY",
        integrity_verdict="PASS" if not findings else "BLOCKED",
        release_verdict="BLOCKED_NONPRODUCTION_UNATTESTED",
        counts=counts, blockers=tuple(sorted(findings)), warnings=tuple(sorted(warnings)),
        evidence_digest=digest,
    )


__all__ = ["AcceptanceRefused", "GateResult", "LedgerPaths", "evaluate_offline_reliability"]
