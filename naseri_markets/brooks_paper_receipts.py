"""Immutable PAPER scan/risk receipts. This is NOT a broker risk approval.

Every receipt shares the exact BEGIN IMMEDIATE transaction as the existing
Brooks V5 scan and A7 PAPER intent. Old scans are not backfilled with invented
historical evidence. No Telegram sends, exchange orders or source-code changes.
"""
from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlite3 import Connection
    from .contracts import SignalIntent

SCHEMA = """CREATE TABLE IF NOT EXISTS brooks_paper_receipts(
    scan_id TEXT PRIMARY KEY,
    receipt_json TEXT NOT NULL,
    receipt_sha256 TEXT NOT NULL,
    FOREIGN KEY(scan_id) REFERENCES brooks_replay_scans(scan_id)
)"""


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_receipt(*, scan_id: str, raw: dict, snapshot_hash: str,
                 source_digest: str, decision: str, signal: SignalIntent | None,
                 outcome: str) -> dict:
    if decision not in ("NO_SIGNAL", "LONG", "SHORT"):
        raise ValueError("BROOKS_AUDIT_DECISION_INVALID")
    if outcome not in ("NO_SIGNAL", "RECORDED", "DUPLICATE_SIGNAL"):
        raise ValueError("BROOKS_AUDIT_OUTCOME_INVALID")
    if (signal is None) != (decision == "NO_SIGNAL"):
        raise ValueError("BROOKS_AUDIT_SIGNAL_MISMATCH")
    risk_per_unit = None
    target_r = []
    if signal is not None:
        # SignalIntent already validates strictly positive, finite geometry
        # and signed stop/target direction. No arbitrary min R tuning.
        risk = abs(signal.entry - signal.stop)
        if not risk.is_finite() or risk <= 0:
            raise ValueError("BROOKS_AUDIT_RISK_INVALID")
        multiples = tuple(abs(target - signal.entry) / risk
                          for target in signal.targets)
        if not multiples or any(not r.is_finite() or r <= 0 for r in multiples):
            raise ValueError("BROOKS_AUDIT_TARGET_INVALID")
        risk_per_unit = str(risk)
        target_r = [str(r) for r in multiples]
    return {
        "schema_version": 1, "scan_id": scan_id,
        "engine_id": "brooks_price_action",
        "snapshot_hash": snapshot_hash, "source_manifest_sha256": source_digest,
        "venue": raw["exchange"], "provider": raw["provider"],
        "symbol": raw["symbol"], "quote_currency": raw["quote_currency"],
        "timeframe": raw["timeframe"], "market_type": raw["market_type"],
        "closed_candle_time": raw["candles"][-1]["close_time"],
        "decision": decision, "outcome": outcome,
        "risk_check": "VALIDATED_GEOMETRY" if signal else "NO_SIGNAL",
        "per_unit_risk": risk_per_unit, "target_reward_r": target_r,
        "signal_id": signal.signal_id if signal else None,
        "signal_evidence": "PAPER" if signal else "NONE",
        "iran_resident_exchange_approval": False,
        "broker_order_authorized": False,
        "telegram_delivery_authorized": False,
    }


def record_receipt(db: Connection, receipt: dict) -> None:
    """Called under the replay journal's existing immediate transaction."""
    raw = json.dumps(receipt, sort_keys=True, separators=(",", ":"))
    db.execute(
        "INSERT INTO brooks_paper_receipts "
        "(scan_id,receipt_json,receipt_sha256) VALUES(?,?,?)",
        (receipt["scan_id"], raw, _digest(raw)))


def read_receipts(db: Connection, *, limit: int = 8) -> list[dict]:
    if type(limit) is not int or not 1 <= limit <= 30:
        raise ValueError("BROOKS_AUDIT_LIMIT_INVALID")
    rows = db.execute(
        "SELECT receipt_json,receipt_sha256 FROM brooks_paper_receipts "
        "ORDER BY rowid DESC LIMIT ?", (limit,)).fetchall()
    results = []
    for row in rows:
        if _digest(row["receipt_json"]) != row["receipt_sha256"]:
            raise ValueError("BROOKS_AUDIT_RECEIPT_CORRUPTED")
        obj = json.loads(row["receipt_json"])
        if (type(obj) is not dict or obj.get("schema_version") != 1
                or obj.get("telegram_delivery_authorized") is not False
                or obj.get("broker_order_authorized") is not False):
            raise ValueError("BROOKS_AUDIT_RECEIPT_INVALID")
        results.append(obj)
    return results
