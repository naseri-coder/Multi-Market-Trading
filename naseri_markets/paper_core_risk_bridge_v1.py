"""Stage 8: per-core PAPER capital budgets atop the existing Stage-3 risk ledger.

NONPRODUCTION / OFFLINE only. No market fetch, broker, Telegram, real accounts,
secret handling or automatic signal-to-order dispatch. The operator explicitly
submits a Core API v1 result, identity-checked event, sizing and revisions.
All per-core caps and existing account/portfolio reservations are checked and
persisted inside the SAME Stage-3 SQLite IMMEDIATE transaction.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .contracts import Market
from .core_api_v1 import (
    CoreBinding, CoreInput, CoreManifest, CoreResult, DataOrigin, DecisionKind,
    CoreEventType, content_digest, validate_core_result,
)
from .execution_contract_v1 import OrderKind, OrderSpec, identity, positive
from .execution_position_core_v1 import PaperExecutionOrchestratorV1
from .market_data_engine_v1 import PriceBasis, VolumeSemantics


class CoreRiskRefused(ValueError):
    """Fail-closed risk refusal; never disclose plugin source or credentials."""


def _fraction(value: Decimal, label: str) -> None:
    if type(value) is not Decimal or not value.is_finite() or not Decimal(0) < value <= Decimal(1):
        raise CoreRiskRefused(f"INVALID_{label}")


def _count(value: int) -> None:
    if type(value) is not int or not 1 <= value <= 10000:
        raise CoreRiskRefused("INVALID_ORDER_LIMIT")


def _safe_hash(*parts: str) -> str:
    return hashlib.sha256(json.dumps(parts, separators=(",", ":")).encode("utf-8")).hexdigest()


def _decimal_total(rows, key: str) -> Decimal:
    return sum((Decimal(r[key]) for r in rows), Decimal(0))


@dataclass(frozen=True, slots=True)
class CoreCapitalAllocation:
    """Operator-assigned ONE account, ONE core instance budget (not core code)."""

    instance_id: str
    core_id: str
    core_version: str
    account_id: str
    portfolio_id: str
    max_reserved_risk_fraction: Decimal
    max_notional_fraction: Decimal
    max_order_risk_fraction: Decimal
    max_active_orders: int

    def __post_init__(self) -> None:
        for field in ("instance_id", "core_id", "core_version", "account_id", "portfolio_id"):
            identity(getattr(self, field), field)
        for field in ("max_reserved_risk_fraction", "max_notional_fraction", "max_order_risk_fraction"):
            _fraction(getattr(self, field), field.upper())
        if self.max_order_risk_fraction > self.max_reserved_risk_fraction:
            raise CoreRiskRefused("PER_ORDER_EXCEEDS_INSTANCE_CAP")
        _count(self.max_active_orders)


@dataclass(frozen=True, slots=True)
class PaperCoreRiskReceipt:
    """Receipt is a modeled local PAPER order CREATED, never an actual fill."""

    instance_id: str
    binding_id: str
    decision_id: str
    order_id: str
    allocation_revision: int
    modeled_risk: str
    modeled_notional: str
    modeled_margin: str
    status: str = "PAPER_CREATED"
    telegram_sent: bool = False
    broker_order_sent: bool = False


class PaperCoreRiskBridge:
    """Dedicated disposable SQLite state; legacy production DB is NEVER used.

    Stage-3's existing lifecycle and risk manager own account/portfolio policy,
    correlation caps, margin, idempotency and the CREATED order state. Stage 8
    only adds smaller per-instance ceilings and durable Core API binding proof.
    """

    def __init__(self, path: str | Path) -> None:
        self._engine = PaperExecutionOrchestratorV1(path)
        self._db = self._engine._db
        for ddl in (
            "CREATE TABLE IF NOT EXISTS paper_core_allocations ("
            "instance_id TEXT PRIMARY KEY, policy_json TEXT NOT NULL,"
            "policy_digest TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 0 "
            "CHECK(enabled IN (0,1)), revision INTEGER NOT NULL DEFAULT 1)",
            "CREATE TABLE IF NOT EXISTS paper_core_bindings ("
            "binding_id TEXT PRIMARY KEY, instance_id TEXT NOT NULL "
            "REFERENCES paper_core_allocations(instance_id),"
            "manifest_digest TEXT NOT NULL, binding_digest TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS paper_core_decisions ("
            "binding_id TEXT NOT NULL, decision_id TEXT NOT NULL,"
            "request_digest TEXT NOT NULL, order_id TEXT NOT NULL UNIQUE,"
            "receipt_json TEXT NOT NULL, PRIMARY KEY(binding_id,decision_id))",
            "CREATE TABLE IF NOT EXISTS paper_core_orders ("
            "order_id TEXT PRIMARY KEY, instance_id TEXT NOT NULL,"
            "binding_id TEXT NOT NULL, account_id TEXT NOT NULL)",
        ):
            self._db.execute(ddl)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def close(self) -> None:
        self._engine.close()

    def configure_portfolio(self, policy) -> None:
        """Delegates to the previously verified Stage-3 policy manager."""
        self._engine.configure_portfolio(policy)

    def configure_account(self, policy) -> None:
        self._engine.configure_account(policy)

    def register_instrument(self, *, portfolio_id: str, instrument, group_id: str) -> None:
        self._engine.register_instrument(portfolio_id=portfolio_id,
                                         instrument=instrument, group_id=group_id)

    def register_allocation(self, policy: CoreCapitalAllocation, *, operator_ack: bool = False) -> None:
        """Immutable budget registration; no silent policy widening after approval."""
        if type(policy) is not CoreCapitalAllocation or operator_ack is not True:
            raise CoreRiskRefused("EXPLICIT_POLICY_APPROVAL_REQUIRED")
        def operation() -> None:
            row = self._db.execute("SELECT portfolio_id FROM risk_accounts WHERE account_id=?",
                                   (policy.account_id,)).fetchone()
            if row is None or row["portfolio_id"] != policy.portfolio_id:
                raise CoreRiskRefused("ACCOUNT_PORTFOLIO_MISMATCH")
            if self._db.execute("SELECT 1 FROM paper_core_allocations WHERE instance_id=?",
                                (policy.instance_id,)).fetchone():
                raise CoreRiskRefused("ALLOCATION_ALREADY_REGISTERED")
            raw = json.dumps({
                "instance_id": policy.instance_id, "core_id": policy.core_id,
                "core_version": policy.core_version, "account_id": policy.account_id,
                "portfolio_id": policy.portfolio_id,
                "max_reserved_risk_fraction": str(policy.max_reserved_risk_fraction),
                "max_notional_fraction": str(policy.max_notional_fraction),
                "max_order_risk_fraction": str(policy.max_order_risk_fraction),
                "max_active_orders": policy.max_active_orders,
            }, sort_keys=True, separators=(",", ":"))
            self._db.execute(
                "INSERT INTO paper_core_allocations(instance_id,policy_json,policy_digest) "
                "VALUES (?,?,?)", (policy.instance_id, raw, hashlib.sha256(raw.encode()).hexdigest()))
        self._engine._transaction(operation)

    def register_binding(self, manifest: CoreManifest, binding: CoreBinding,
                         *, operator_ack: bool = False) -> None:
        if (operator_ack is not True or not isinstance(manifest, CoreManifest)
                or not isinstance(binding, CoreBinding)):
            raise CoreRiskRefused("EXPLICIT_BINDING_APPROVAL_REQUIRED")
        def operation() -> None:
            row = self._db.execute("SELECT policy_json FROM paper_core_allocations "
                                   "WHERE instance_id=?", (binding.instance_id,)).fetchone()
            if row is None:
                raise CoreRiskRefused("ALLOCATION_UNKNOWN")
            policy = json.loads(row["policy_json"])
            if (manifest.core_id != policy["core_id"] or manifest.core_version != policy["core_version"]
                    or binding.instrument.market not in manifest.supported_markets):
                raise CoreRiskRefused("CORE_OR_MARKET_MISMATCH")
            if self._db.execute("SELECT 1 FROM paper_core_bindings WHERE binding_id=?",
                                (binding.binding_id,)).fetchone():
                raise CoreRiskRefused("BINDING_ALREADY_REGISTERED")
            self._db.execute(
                "INSERT INTO paper_core_bindings VALUES (?,?,?,?)",
                (binding.binding_id, binding.instance_id, content_digest(manifest),
                 content_digest(binding)))
        self._engine._transaction(operation)

    def set_enabled(self, instance_id: str, *, enabled: bool,
                    expected_revision: int, operator_ack: bool = False) -> int:
        """Local CAS; never grants live trading. Auth must exist OUTSIDE this API."""
        if (type(instance_id) is not str or type(enabled) is not bool or
                type(expected_revision) is not int or operator_ack is not True):
            raise CoreRiskRefused("EXPLICIT_CAS_REQUIRED")
        def operation() -> int:
            row = self._db.execute("SELECT enabled,revision FROM paper_core_allocations "
                                   "WHERE instance_id=?", (instance_id,)).fetchone()
            if row is None or row["revision"] != expected_revision:
                raise CoreRiskRefused("STALE_ALLOCATION_REVISION")
            self._db.execute("UPDATE paper_core_allocations SET enabled=?,revision=revision+1 "
                             "WHERE instance_id=?", (int(enabled), instance_id))
            return expected_revision + 1
        return self._engine._transaction(operation)

    def status(self, instance_id: str) -> dict:
        row = self._db.execute("SELECT enabled,revision,policy_json FROM paper_core_allocations "
                               "WHERE instance_id=?", (instance_id,)).fetchone()
        if row is None:
            raise CoreRiskRefused("ALLOCATION_UNKNOWN")
        policy = json.loads(row["policy_json"])
        active = self._active_rows(instance_id)
        return {
            "instance_id": instance_id, "enabled": bool(row["enabled"]),
            "revision": row["revision"], "active_orders": len(active),
            "modeled_reserved_risk": str(_decimal_total(active, "risk")),
            "modeled_notional": str(_decimal_total(active, "notional")),
            "account_id": policy["account_id"], "live_trading_enabled": False,
            "telegram_publication_enabled": False,
        }

    def _active_rows(self, instance_id: str):
        return self._db.execute(
            "SELECT r.risk,r.notional,r.margin,r.order_id FROM paper_core_orders AS s "
            "JOIN paper_risk_reservations AS r ON r.order_id=s.order_id "
            "WHERE s.instance_id=? AND r.status='ACTIVE'", (instance_id,)
        ).fetchall()

    def reserve_entry(self, manifest: CoreManifest, event: CoreInput, result: CoreResult,
                      *, decision_id: str, quantity: Decimal,
                      price_basis: PriceBasis, volume_semantics: VolumeSemantics,
                      expected_allocation_revision: int,
                      operator_ack: bool = False) -> PaperCoreRiskReceipt:
        """Caller-selected, provenance-checked PAPER decision. No automatic dispatch.

        Atomicity: allocation cap check, Stage-3 account/portfolio reserve,
        Stage-3 CREATED order and stage-8 receipt in one SQLite transaction.
        """
        if operator_ack is not True or type(quantity) is not Decimal:
            raise CoreRiskRefused("EXPLICIT_OFFLINE_QUANTITY_REQUIRED")
        positive(quantity, "quantity")
        if (type(decision_id) is not str or type(expected_allocation_revision) is not int
                or not isinstance(manifest, CoreManifest) or
                not isinstance(event, CoreInput) or not isinstance(result, CoreResult) or
                not isinstance(price_basis, PriceBasis) or
                not isinstance(volume_semantics, VolumeSemantics)):
            raise CoreRiskRefused("INVALID_RISK_REQUEST")
        # Stage 3 + Stage 5 contracts, and the exact executable decision are
        # revalidated. A signal was NOT a filled trade and is NOT authenticated.
        validate_core_result(manifest, event, result)
        if event.origin not in (DataOrigin.REPLAY, DataOrigin.SYNTHETIC):
            raise CoreRiskRefused("NONPRODUCTION_DATA_REQUIRED")
        if event.binding.instrument.market is Market.CRYPTO:
            if (event.event is not CoreEventType.CLOSED_CANDLE or
                    price_basis is not PriceBasis.TRADE or
                    volume_semantics is not VolumeSemantics.TRADED):
                raise CoreRiskRefused("CRYPTO_EXECUTION_BASIS_UNVERIFIED")
        elif event.binding.instrument.market is Market.FOREX:
            if (event.event is not CoreEventType.QUOTE_TICK or
                    price_basis is not PriceBasis.BID_ASK or
                    volume_semantics is not VolumeSemantics.UNKNOWN):
                raise CoreRiskRefused("FX_EXECUTION_BASIS_UNVERIFIED")
        else:
            raise CoreRiskRefused("UNMODELED_MARKET_TYPE")
        matching = [d for d in result.decisions if d.decision_id == decision_id]
        if len(matching) != 1 or matching[0].kind is not DecisionKind.ENTRY_INTENT:
            raise CoreRiskRefused("ENTRY_INTENT_REQUIRED")
        decision = matching[0]
        request_digest = content_digest({
            "manifest": manifest, "event": event, "result": result,
            "decision_id": decision_id, "quantity": quantity,
            "price_basis": price_basis, "volume_semantics": volume_semantics,
            "expected_revision": expected_allocation_revision,
        })
        binding_id = event.binding.binding_id

        def operation() -> PaperCoreRiskReceipt:
            previous = self._db.execute(
                "SELECT request_digest,receipt_json,order_id FROM paper_core_decisions "
                "WHERE binding_id=? AND decision_id=?", (binding_id, decision_id)
            ).fetchone()
            if previous is not None:
                if previous["request_digest"] != request_digest:
                    raise CoreRiskRefused("DECISION_REPLAY_CONFLICT")
                check = self._db.execute(
                    "SELECT order_id FROM paper_risk_reservations WHERE order_id=?",
                    (previous["order_id"],)).fetchone()
                if check is None:
                    raise CoreRiskRefused("PAPER_RISK_LEDGER_INCONSISTENT")
                return PaperCoreRiskReceipt(**json.loads(previous["receipt_json"]))

            alloc = self._db.execute("SELECT * FROM paper_core_allocations WHERE instance_id=?",
                                     (event.binding.instance_id,)).fetchone()
            route = self._db.execute("SELECT * FROM paper_core_bindings WHERE binding_id=?",
                                     (binding_id,)).fetchone()
            if (alloc is None or route is None or route["instance_id"] != event.binding.instance_id
                    or route["manifest_digest"] != content_digest(manifest)
                    or route["binding_digest"] != content_digest(event.binding)):
                raise CoreRiskRefused("UNREGISTERED_OR_DRIFTED_BINDING")
            if alloc["revision"] != expected_allocation_revision or alloc["enabled"] != 1:
                raise CoreRiskRefused("ALLOCATION_DISABLED_OR_STALE")
            policy = json.loads(alloc["policy_json"])
            if (policy["core_id"] != manifest.core_id or
                    policy["core_version"] != manifest.core_version):
                raise CoreRiskRefused("ALLOCATION_CORE_MISMATCH")
            account = self._db.execute("SELECT portfolio_id,policy FROM risk_accounts "
                                       "WHERE account_id=?", (policy["account_id"],)).fetchone()
            if account is None or account["portfolio_id"] != policy["portfolio_id"]:
                raise CoreRiskRefused("RISK_ACCOUNT_MISSING_OR_DRIFTED")
            ap = json.loads(account["policy"])
            if ap.get("external_exposure_cleared") is not True:
                raise CoreRiskRefused("EXTERNAL_EXPOSURE_UNVERIFIED")
            equity = Decimal(ap["equity"])
            entry = decision.entry
            stop = decision.stop
            multiplier = Decimal(ap["contract_multiplier"])
            costs = Decimal(ap["roundtrip_fee_fraction"]) + Decimal(ap["worst_slippage_fraction"])
            model_risk = quantity * multiplier * (abs(entry - stop) + entry * costs)
            notional = quantity * multiplier * entry
            active = self._active_rows(event.binding.instance_id)
            if len(active) >= policy["max_active_orders"]:
                raise CoreRiskRefused("INSTANCE_ORDER_LIMIT")
            if model_risk > equity * Decimal(policy["max_order_risk_fraction"]):
                raise CoreRiskRefused("INSTANCE_ORDER_RISK_CAP")
            if _decimal_total(active, "risk") + model_risk > equity * Decimal(policy["max_reserved_risk_fraction"]):
                raise CoreRiskRefused("INSTANCE_TOTAL_RISK_CAP")
            if _decimal_total(active, "notional") + notional > equity * Decimal(policy["max_notional_fraction"]):
                raise CoreRiskRefused("INSTANCE_NOTIONAL_CAP")

            key = _safe_hash(binding_id, decision_id)
            order_id = "pc8_" + key[:60]
            action_id = "pa8_" + key[:60]
            spec = OrderSpec(
                order_id=order_id, signal_id="ps8_" + key[:60],
                account_id=policy["account_id"], engine_id=manifest.core_id,
                instrument=event.binding.instrument, direction=decision.direction,
                kind=OrderKind.LIMIT, quantity=quantity, reference_entry=entry,
                stop=stop, target=decision.targets[0],
            )
            created = self._engine.create(spec, action_id=action_id)
            reserved = created["risk_reservation"]
            if (reserved["order_id"] != order_id or reserved["status"] != "ACTIVE"
                    or Decimal(reserved["risk"]) != model_risk
                    or Decimal(reserved["notional"]) != notional):
                raise CoreRiskRefused("RISK_ATTESTATION_MISMATCH")
            self._db.execute("INSERT INTO paper_core_orders VALUES (?,?,?,?)",
                             (order_id, event.binding.instance_id, binding_id, policy["account_id"]))
            receipt = PaperCoreRiskReceipt(
                event.binding.instance_id, binding_id, decision_id, order_id,
                expected_allocation_revision, str(model_risk), str(notional),
                reserved["modeled_margin"],
            )
            self._db.execute(
                "INSERT INTO paper_core_decisions VALUES (?,?,?,?,?)",
                (binding_id, decision_id, request_digest, order_id,
                 json.dumps(receipt.__dict__ if hasattr(receipt, "__dict__") else {
                     key: getattr(receipt, key) for key in receipt.__dataclass_fields__
                 }, sort_keys=True)),
            )
            return receipt

        return self._engine._transaction(operation)

    def order_state(self, order_id: str):
        return self._engine.order_state(order_id)

    def risk_snapshot(self, portfolio_id: str):
        return self._engine.risk_snapshot(portfolio_id)


__all__ = ["CoreCapitalAllocation", "CoreRiskRefused", "PaperCoreRiskBridge", "PaperCoreRiskReceipt"]