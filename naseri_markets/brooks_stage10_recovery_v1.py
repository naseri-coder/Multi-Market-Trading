"""Read-only, bounded inspection of the TWO existing Brooks and PAPER ledgers.

This is an observational operator diagnostic, NOT a distributed transaction
or authorization to retry, release risks, execute trades or resume workers.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import stat
from pathlib import Path
from urllib.parse import quote

from .brooks_paper_receipts import _digest as receipt_hash
from .brooks_stage10_paper_bridge import STAGE10_FILENAME, _signal
from .engine_control_store import BROOKS_ENGINE_ID

LIMIT = 200
_TERMINAL = {"CLOSED", "CANCELED", "REJECTED"}


def _connection(path: Path) -> sqlite3.Connection | None:
    """Never create a missing SQLite file or follow an untrusted DB symlink."""
    if not path.exists() and not path.is_symlink():
        return None
    if path.is_symlink() or not path.is_file():
        raise ValueError("NONREGULAR_RECOVERY_DATABASE")
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError("UNSAFE_RECOVERY_DATABASE")
    uri = "file:" + quote(str(path.absolute()), safe="/") + "?mode=ro"
    db = sqlite3.connect(uri, uri=True, timeout=2, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    db.execute("BEGIN")
    return db


def _read_source(db: sqlite3.Connection) -> list[dict]:
    rows = db.execute(
        "SELECT s.scan_id,s.signal_id,s.snapshot_hash,s.source_sha256,"
        "s.decision,a.payload,a.digest,r.receipt_json,r.receipt_sha256 "
        "FROM brooks_replay_scans AS s "
        "LEFT JOIN a7_paper_intents AS a "
        "ON a.engine_id=? AND a.signal_id=s.signal_id "
        "LEFT JOIN brooks_paper_receipts AS r ON r.scan_id=s.scan_id "
        "ORDER BY s.scan_id LIMIT ?", (BROOKS_ENGINE_ID, LIMIT + 1),
    ).fetchall()
    result = []
    for r in rows:
        checked = False
        if r["signal_id"] is None:
            try:
                receipt = json.loads(r["receipt_json"])
                checked = (
                    type(receipt) is dict
                    and r["decision"] == "NO_SIGNAL"
                    and receipt_hash(r["receipt_json"]) == r["receipt_sha256"]
                    and receipt.get("decision") == "NO_SIGNAL"
                    and receipt.get("signal_id") is None
                    and receipt.get("broker_order_authorized") is False
                    and receipt.get("telegram_delivery_authorized") is False
                )
            except (ValueError, TypeError, KeyError, AttributeError):
                checked = False
        else:
            try:
                signal = _signal(r["payload"], r["digest"], r["signal_id"])
                receipt = json.loads(r["receipt_json"])
                checked = (
                    type(receipt) is dict
                    and receipt_hash(r["receipt_json"]) == r["receipt_sha256"]
                    and receipt.get("signal_id") == r["signal_id"]
                    and receipt.get("engine_id") == BROOKS_ENGINE_ID
                    and receipt.get("source_manifest_sha256") == r["source_sha256"]
                    and receipt.get("snapshot_hash") == r["snapshot_hash"]
                    and receipt.get("decision") == r["decision"]
                    and receipt.get("broker_order_authorized") is False
                    and receipt.get("telegram_delivery_authorized") is False
                    and receipt.get("risk_check") == "VALIDATED_GEOMETRY"
                    and receipt.get("closed_candle_time") == signal.observed_at.isoformat()
                    and receipt.get("symbol") == signal.instrument.symbol
                )
            except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError):
                checked = False
        result.append({
            "signal_id": r["signal_id"], "valid": checked,
            "signal_digest": r["digest"], "receipt_digest": r["receipt_sha256"],
        })
    return result


def _read_paper(db: sqlite3.Connection) -> list[dict]:
    present = db.execute(
        "SELECT 1 FROM sqlite_master "
        "WHERE type='table' AND name='brooks_stage10_links'"
    ).fetchone()
    if present is None:
        return []
    links = db.execute(
        "SELECT account_id,signal_id,order_id,request_digest,content_json "
        "FROM brooks_stage10_links ORDER BY order_id LIMIT ?", (LIMIT + 1,),
    ).fetchall()
    result = []
    for link in links:
        okay = False
        try:
            content = json.loads(link["content_json"])
            order = db.execute(
                "SELECT snapshot FROM paper_orders WHERE order_id=?",
                (link["order_id"],),
            ).fetchone()
            reserve = db.execute(
                "SELECT account_id,engine_id,status,contract_json "
                "FROM paper_risk_reservations WHERE order_id=?",
                (link["order_id"],),
            ).fetchone()
            if order is not None and reserve is not None:
                snapshot = json.loads(order["snapshot"])
                spec = snapshot["spec"]
                contract = json.loads(reserve["contract_json"])
                events = db.execute(
                    "SELECT COUNT(*) FROM paper_order_events WHERE order_id=?",
                    (link["order_id"],),
                ).fetchone()[0]
                status = snapshot["status"]
                okay = (
                    type(content) is dict
                    and type(spec) is dict
                    and hashlib.sha256(
                        json.dumps(content, sort_keys=True, separators=(",", ":"))
                        .encode("utf-8")
                    ).hexdigest() == link["request_digest"]
                    and content.get("account_id") == link["account_id"]
                    and content.get("signal_id") == link["signal_id"]
                    and content.get("order_id") == link["order_id"]
                    and reserve["account_id"] == link["account_id"]
                    and reserve["engine_id"] == BROOKS_ENGINE_ID
                    and spec.get("order_id") == link["order_id"]
                    and spec.get("signal_id") == link["signal_id"]
                    and spec.get("account_id") == link["account_id"]
                    and spec.get("engine_id") == BROOKS_ENGINE_ID
                    and contract == spec
                    and events >= 1
                    and status in {
                        "CREATED", "SUBMITTED", "ACKED", "PARTIAL", "FILLED",
                        "CLOSED", "CANCELED", "REJECTED",
                    }
                    and reserve["status"] == (
                        "RELEASED" if status in _TERMINAL else "ACTIVE"
                    )
                )
        except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError):
            okay = False
        result.append({
            "account_id": link["account_id"], "signal_id": link["signal_id"],
            "order_id": link["order_id"], "valid": okay,
            "content": content if okay else {},
        })
    return result


def reconcile_stage10_paper(
    state_dir: str | Path, *, signal_id: str | None = None,
    account_id: str | None = None,
) -> dict:
    """Inspect closed snapshots only; NEVER repair, retry, unlock or create.

    Cross-DB snapshots are not globally atomic. The result is intentionally
    not a recovery authorization; even MATCHED_PAPER_ORDER cannot resume.
    """
    root = Path(state_dir).absolute()
    report = {
        "mode": "READ_ONLY_BROOKS_PAPER_RECONCILIATION",
        "status": "MANUAL_RECONCILIATION_REQUIRED",
        "scans_checked": 0, "linked_orders": 0, "unlinked_signals": 0,
        "active_paper_reservations": 0, "inconsistent_links": 0,
        "source_evidence_invalid": 0,
        "can_automatically_resume": False,
        "live_orders_authorized": False,
        "telegram_publication_authorized": False,
    }
    if (not root.is_dir() or root.is_symlink()
            or signal_id is not None and (
                type(signal_id) is not str or not 1 <= len(signal_id) <= 100
            ) or account_id is not None and (
                type(account_id) is not str or not 1 <= len(account_id) <= 80
            )):
        return report
    source = paper = None
    try:
        source = _connection(root / "custom_paper.db")
        paper = _connection(root / STAGE10_FILENAME)
        if source is None and paper is None:
            report["status"] = "NOT_CONFIGURED"
            return report
        if source is None:
            return report
        scans = _read_source(source)
        report["scans_checked"] = len(scans)
        if len(scans) > LIMIT:
            return report
        positives = [s for s in scans if s["signal_id"] is not None]
        report["source_evidence_invalid"] = sum(not s["valid"] for s in scans)
        if paper is None:
            report["unlinked_signals"] = len(positives)
            report["status"] = (
                "CLEAN_NO_SIGNALS" if not positives
                and not report["source_evidence_invalid"]
                else "MANUAL_RECONCILIATION_REQUIRED"
            )
            return report
        links = _read_paper(paper)
        if len(links) > LIMIT:
            return report
        report["linked_orders"] = len(links)
        report["active_paper_reservations"] = paper.execute(
            "SELECT COUNT(*) FROM paper_risk_reservations "
            "WHERE engine_id=? AND status='ACTIVE'", (BROOKS_ENGINE_ID,),
        ).fetchone()[0]
        source_by_id = {s["signal_id"]: s for s in positives}
        if len(source_by_id) != len(positives):
            report["source_evidence_invalid"] += 1
        linked_by_signal = {}
        for link in links:
            linked_by_signal.setdefault(link["signal_id"], []).append(link)
            source_match = source_by_id.get(link["signal_id"])
            if (not link["valid"] or source_match is None or not source_match["valid"]
                    or link["content"].get("signal_digest")
                    != source_match["signal_digest"]
                    or link["content"].get("receipt_digest")
                    != source_match["receipt_digest"]):
                report["inconsistent_links"] += 1
        report["unlinked_signals"] = sum(
            not linked_by_signal.get(s["signal_id"]) for s in positives
        )
        report["inconsistent_links"] += sum(
            len(items) != 1 for items in linked_by_signal.values()
        )
        # An active Brooks reservation without any matched link requires
        # operator review, never an inferred automatic budget release.
        if report["active_paper_reservations"] > report["linked_orders"]:
            report["inconsistent_links"] += (
                report["active_paper_reservations"] - report["linked_orders"]
            )
        if signal_id is not None and signal_id not in source_by_id:
            report["source_evidence_invalid"] += 1
        if (report["inconsistent_links"] or report["unlinked_signals"]
                or report["source_evidence_invalid"]):
            return report
        if positives and (
            signal_id is None or
            len(linked_by_signal.get(signal_id, [])) == 1
            and (account_id is None or
                 linked_by_signal[signal_id][0]["account_id"] == account_id)
        ):
            report["status"] = "MATCHED_PAPER_ORDER"
        else:
            report["status"] = "CLEAN_NO_SIGNALS"
        return report
    except (sqlite3.Error, ValueError, OSError, TypeError, KeyError):
        return report
    finally:
        for db in (paper, source):
            if db is not None:
                db.close()
