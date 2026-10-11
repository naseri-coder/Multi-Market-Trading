"""Stage 10: opt-in Brooks evidence -> independent risk-reserved PAPER order.

A verified CLOSED-CANDLE Brooks V5 PAPER intent can be linked once to an
operator-configured Stage-3 simulated order/risk portfolio. No automatic
provider, broker, Telegram, fills, ACKs, risk unlock, or publication route.
The source journal and destination PAPER lifecycle remain independent DBs.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .brooks_paper_receipts import _digest as receipt_hash
from .contracts import Direction, EvidenceMode, Instrument, Market, SignalIntent
from .delivery_ledger import _wire_intent
from .engine_control_store import BROOKS_ENGINE_ID, EngineControlStore
from .execution_contract_v1 import OrderKind, OrderSpec, identity, positive
from .execution_position_core_v1 import PaperExecutionOrchestratorV1

STAGE10_FILENAME = "brooks_stage10_paper.sqlite"


class BrooksStage10Refused(ValueError):
    """No trusted Brooks signal or reproducible PAPER order eligibility."""


def _sha(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _checked_positive(raw: object) -> Decimal:
    if type(raw) is not str or not 0 < len(raw) <= 64:
        raise BrooksStage10Refused("STAGE10_EXPLICIT_DECIMAL_REQUIRED")
    try:
        value = Decimal(raw)
        positive(value, "quantity")
    except (ValueError, InvalidOperation) as exc:
        raise BrooksStage10Refused("STAGE10_QUANTITY_INVALID") from exc
    return value


def _signal(payload: str, digest: str, signal_id: str) -> SignalIntent:
    if type(payload) is not str or _sha(payload) != digest:
        raise BrooksStage10Refused("STAGE10_A7_DIGEST_MISMATCH")
    try:
        obj = json.loads(payload)
        if type(obj) is not dict or set(obj) != {
            "signal_id", "engine_id", "engine_version", "market", "provider",
            "symbol", "timezone", "quote_currency", "direction", "observed_at",
            "entry", "stop", "targets", "evidence_mode",
        }:
            raise ValueError("intent fields")
        result = SignalIntent(
            signal_id=obj["signal_id"], engine_id=obj["engine_id"],
            engine_version=obj["engine_version"],
            instrument=Instrument(
                market=Market(obj["market"]), provider=obj["provider"],
                symbol=obj["symbol"], timezone=obj["timezone"],
                quote_currency=obj["quote_currency"],
            ),
            direction=Direction(obj["direction"]),
            observed_at=datetime.fromisoformat(obj["observed_at"]),
            entry=Decimal(obj["entry"]), stop=Decimal(obj["stop"]),
            targets=tuple(Decimal(t) for t in obj["targets"]),
            evidence_mode=EvidenceMode(obj["evidence_mode"]),
        )
        if _wire_intent(result) != payload:
            raise ValueError("noncanonical intent")
    except (KeyError, TypeError, ValueError, ArithmeticError, AttributeError) as exc:
        raise BrooksStage10Refused("STAGE10_A7_INTENT_INVALID") from exc
    if (
        result.engine_id != BROOKS_ENGINE_ID
        or result.signal_id != signal_id
        or result.evidence_mode is not EvidenceMode.PAPER
        or result.instrument.market is not Market.CRYPTO
        or not result.engine_version.startswith("brooks-trilogy-full-core-v5")
    ):
        raise BrooksStage10Refused("STAGE10_UNAUTHORIZED_SIGNAL_ORIGIN")
    return result


def _evidence(store: EngineControlStore, signal_id: str) -> tuple[SignalIntent, dict, dict]:
    identity(signal_id, "signal_id")
    state = store.get(BROOKS_ENGINE_ID)
    preferences = store.preferences(BROOKS_ENGINE_ID)
    if (
        state is None or not state.requested_enabled
        or preferences["signal_environment"] != "PAPER"
        or preferences["market_scope"] not in ("all", "crypto")
    ):
        raise BrooksStage10Refused("STAGE10_BROOKS_PAPER_NOT_ARMED")
    row = store._db.execute(
        "SELECT payload,digest FROM a7_paper_intents "
        "WHERE engine_id=? AND signal_id=?",
        (BROOKS_ENGINE_ID, signal_id),
    ).fetchone()
    if row is None:
        raise BrooksStage10Refused("STAGE10_NO_PERSISTED_BROOKS_SIGNAL")
    signal = _signal(row["payload"], row["digest"], signal_id)
    scan = store._db.execute(
        "SELECT scan_id,snapshot_hash,decision,source_sha256 FROM brooks_replay_scans "
        "WHERE signal_id=?", (signal_id,),
    ).fetchall()
    if len(scan) != 1:
        raise BrooksStage10Refused("STAGE10_UNIQUE_BROOKS_SCAN_REQUIRED")
    receipt_row = store._db.execute(
        "SELECT receipt_json,receipt_sha256 FROM brooks_paper_receipts "
        "WHERE scan_id=?", (scan[0]["scan_id"],),
    ).fetchone()
    if receipt_row is None or receipt_hash(receipt_row["receipt_json"]) != receipt_row["receipt_sha256"]:
        raise BrooksStage10Refused("STAGE10_SIGNED_LOCAL_RECEIPT_REQUIRED")
    try:
        receipt = json.loads(receipt_row["receipt_json"])
        if (
            type(receipt) is not dict or receipt.get("schema_version") != 1
            or receipt.get("engine_id") != BROOKS_ENGINE_ID
            or receipt.get("signal_id") != signal_id
            or receipt.get("decision") != ("LONG" if signal.direction is Direction.LONG else "SHORT")
            or scan[0]["decision"] != receipt["decision"]
            or receipt.get("outcome") not in ("RECORDED", "DUPLICATE_SIGNAL")
            or receipt.get("risk_check") != "VALIDATED_GEOMETRY"
            or receipt.get("signal_evidence") != "PAPER"
            or receipt.get("broker_order_authorized") is not False
            or receipt.get("telegram_delivery_authorized") is not False
            or receipt.get("source_manifest_sha256") != scan[0]["source_sha256"]
            or receipt.get("snapshot_hash") != scan[0]["snapshot_hash"]
            or receipt.get("symbol") != signal.instrument.symbol
            or receipt.get("provider") != signal.instrument.provider
            or receipt.get("quote_currency") != signal.instrument.quote_currency
            or receipt.get("venue") is None
            or not isinstance(receipt.get("timeframe"), str)
            or receipt.get("timeframe") != preferences["timeframe"]
            or receipt.get("closed_candle_time") != signal.observed_at.isoformat()
            or Decimal(receipt.get("per_unit_risk", "")) != abs(signal.entry - signal.stop)
            or [Decimal(n) for n in receipt.get("target_reward_r", [])]
            != [abs(t - signal.entry) / abs(signal.entry - signal.stop) for t in signal.targets]
        ):
            raise BrooksStage10Refused("STAGE10_BROOKS_EVIDENCE_CONFLICT")
    except (KeyError, ValueError, TypeError, ArithmeticError) as exc:
        raise BrooksStage10Refused("STAGE10_BROOKS_EVIDENCE_CONFLICT") from exc
    # Same broker identity must match the admin's selected pair if this is
    # the frozen Kraken replay. Offline-only non-Kraken fixtures have no
    # provider authorisation from this bridge either.
    if signal.instrument.provider == "kraken_futures_trade_public" and (
        preferences["futures_exchange"] != "kraken"
        or preferences["futures_symbol"] != signal.instrument.symbol
        or receipt["venue"] != "kraken_futures"
    ):
        raise BrooksStage10Refused("STAGE10_SELECTED_FUTURES_IDENTITY_DRIFT")
    return signal, receipt, {
        "engine_revision": state.revision,
        "preference_revision": preferences["revision"],
        "signal_sha256": row["digest"],
        "receipt_sha256": receipt_row["receipt_sha256"],
    }


class BrooksStage10PaperBridge:
    """No implicit operation; call link() only with explicit operator consent.

    The source SQLite writer lock prevents concurrent admin toggles until
    Stage-3 has committed, preventing a mid-link configuration race.
    One unique (account,signal) => one immutable order in the Stage-3 DB.
    """

    def __init__(self, state_dir: str | Path, *, paper_db: str | Path | None = None):
        root = Path(state_dir).absolute()
        self.state_dir = root
        self.paper_db = Path(paper_db) if paper_db is not None else root / STAGE10_FILENAME
        if self.paper_db.absolute() == root / "custom_paper.db":
            raise BrooksStage10Refused("STAGE10_SEPARATE_PAPER_DATABASE_REQUIRED")

    def link(self, *, signal_id: str, account_id: str, quantity: str,
             ack_paper_risk: bool = False) -> dict[str, Any]:
        if ack_paper_risk is not True:
            raise BrooksStage10Refused("STAGE10_EXPLICIT_PAPER_RISK_OPTIN_REQUIRED")
        identity(account_id, "account_id")
        identity(signal_id, "signal_id")
        units = _checked_positive(quantity)
        with EngineControlStore(self.state_dir) as store:
            # The Brooks data and operator settings stay immutable for this
            # acceptance point (WAL source BEGIN IMMEDIATE, no row writes).
            store._db.execute("BEGIN IMMEDIATE")
            try:
                signal, receipt, provenance = _evidence(store, signal_id)
                key = _sha(account_id + ":" + signal_id)
                order_id = "brk10-" + key[:48]
                spec = OrderSpec(
                    order_id=order_id, signal_id=signal.signal_id,
                    account_id=account_id, engine_id=BROOKS_ENGINE_ID,
                    instrument=signal.instrument, direction=signal.direction,
                    kind=OrderKind.LIMIT, quantity=units,
                    reference_entry=signal.entry, stop=signal.stop,
                    target=signal.targets[0], mode=EvidenceMode.PAPER,
                )
                content = {
                    "account_id": account_id, "signal_id": signal_id,
                    "signal_digest": provenance["signal_sha256"],
                    "receipt_digest": provenance["receipt_sha256"],
                    "quantity": str(units), "order_id": order_id,
                    "engine_revision": provenance["engine_revision"],
                    "preference_revision": provenance["preference_revision"],
                }
                digest = _sha(json.dumps(content, sort_keys=True, separators=(",", ":")))
                with PaperExecutionOrchestratorV1(self.paper_db) as core:
                    core._db.execute(
                        "CREATE TABLE IF NOT EXISTS brooks_stage10_links("
                        "account_id TEXT NOT NULL,signal_id TEXT NOT NULL,"
                        "order_id TEXT NOT NULL UNIQUE, request_digest TEXT NOT NULL,"
                        "content_json TEXT NOT NULL,"
                        "PRIMARY KEY(account_id,signal_id))"
                    )

                    def reserve_once() -> dict[str, Any]:
                        existing = core._db.execute(
                            "SELECT order_id,request_digest FROM brooks_stage10_links "
                            "WHERE account_id=? AND signal_id=?",
                            (account_id, signal_id),
                        ).fetchone()
                        if existing is not None:
                            if existing["order_id"] != order_id or existing["request_digest"] != digest:
                                raise BrooksStage10Refused("STAGE10_SIGNAL_ORDER_IDENTITY_CONFLICT")
                            order = core.order_state(order_id)
                            if order is None:
                                raise BrooksStage10Refused("STAGE10_LINKED_ORDER_MISSING")
                            return {
                                "status": "EXISTING_PAPER_ORDER",
                                "order": order, "risk_reservation_created": False,
                            }
                        result = core.create(spec, action_id="brk10-create-" + key[:40])
                        core._db.execute(
                            "INSERT INTO brooks_stage10_links VALUES(?,?,?,?,?)",
                            (account_id, signal_id, order_id, digest,
                             json.dumps(content, sort_keys=True, separators=(",", ":"))),
                        )
                        return {
                            "status": "PAPER_ORDER_CREATED",
                            "order": result["order"],
                            "risk_reservation_created": True,
                        }

                    outcome = core._transaction(reserve_once)
                store._db.execute("COMMIT")
            except BaseException:
                store._db.execute("ROLLBACK")
                raise
        return {
            "mode": "OFFLINE_BROOKS_PAPER_RISK_LINK_ONLY",
            "status": outcome["status"], "signal_id": signal_id,
            "account_id": account_id, "order_id": order_id,
            "order_status": outcome["order"]["status"],
            "requested_quantity": str(units),
            "risk_reservation_created": outcome["risk_reservation_created"],
            "engine_revision": provenance["engine_revision"],
            "paper_fill_confirmed": False, "broker_fill_confirmed": False,
            "live_orders_authorized": False, "telegram_publication_authorized": False,
            "automated_execution": False,
        }


def panel_stage10_overview(state_dir: str | Path) -> dict[str, Any]:
    """Read-only panel diagnostics. Never create Stage-3 risk DB on render."""
    path = Path(state_dir).absolute() / STAGE10_FILENAME
    if path.is_symlink() or not path.is_file():
        return {"status": "NOT_CONFIGURED", "linked_orders": 0,
                "active_paper_reservations": 0, "broker_execution": False}
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=2)
        try:
            conn.execute("PRAGMA query_only=ON")
            count = conn.execute(
                "SELECT COUNT(*) FROM brooks_stage10_links"
            ).fetchone()[0]
            active = conn.execute(
                "SELECT COUNT(*) FROM paper_risk_reservations "
                "WHERE engine_id=? AND status='ACTIVE'",
                (BROOKS_ENGINE_ID,),
            ).fetchone()[0]
        finally:
            conn.close()
    except sqlite3.Error:
        return {"status": "UNAVAILABLE", "linked_orders": 0,
                "active_paper_reservations": 0, "broker_execution": False}
    return {"status": "OFFLINE_PAPER_ONLY", "linked_orders": int(count),
            "active_paper_reservations": int(active), "broker_execution": False}
