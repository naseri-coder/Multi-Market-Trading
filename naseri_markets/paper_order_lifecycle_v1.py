"""Stage 9: offline PAPER lifecycle and modeled outcomes atop Stage 8/3.

No live provider, Telegram, credentials, sockets, strategy import or automation.
Operator injects explicit synthetic/replay evidence; all changes share Stage-3
SQLite transactions and its existing account/portfolio risk release logic.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_DOWN
from pathlib import Path

from .contracts import Direction, Market
from .core_api_v1 import (
    ClosedCandle, CoreEventType, CoreInput, CoreManifest, CoreResult,
    DataOrigin, DecisionKind, ExitAction, ManagementAction, _TIMEFRAME_MINUTES,
    content_digest, validate_core_result,
)
from .execution_contract_v1 import identity
from .paper_core_risk_bridge_v1 import PaperCoreRiskBridge
from .market_data_engine_v1 import PriceBasis, VolumeSemantics


class PaperLifecycleRefused(ValueError):
    """No side effects on refusal; no strategy exception or credential leakage."""


def _positive(value: object, name: str) -> Decimal:
    if type(value) is not Decimal or not value.is_finite() or value <= 0:
        raise PaperLifecycleRefused("INVALID_" + name)
    return value


def _record(row: object) -> dict:
    return json.loads(row["receipt_json"])


def _wire(data: object) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hash(data: object) -> str:
    return hashlib.sha256(_wire(data).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class TargetStep:
    price: Decimal
    fraction: Decimal

    def __post_init__(self) -> None:
        _positive(self.price, "TARGET_PRICE")
        _positive(self.fraction, "TARGET_FRACTION")
        if self.fraction > 1:
            raise PaperLifecycleRefused("TARGET_FRACTION_ABOVE_ONE")


class OfflinePaperPositionLifecycle(PaperCoreRiskBridge):
    """Default-offline ledger, never automatically connected to Stage-7 output.

    Registration is attached to an existing Stage-8 reserved order. Only
    simulated operator evidence can advance order states; there is no venue API.
    On restart, any open plan needs explicit reconciliation before mutations.
    """

    def __init__(self, path: str | Path) -> None:
        super().__init__(path)
        for ddl in (
            "CREATE TABLE IF NOT EXISTS paper_stage9_plans ("
            "order_id TEXT PRIMARY KEY REFERENCES paper_core_orders(order_id),"
            "setup_id TEXT NOT NULL, manifest_digest TEXT NOT NULL,"
            "binding_digest TEXT NOT NULL, plan_json TEXT NOT NULL,"
            "input_close TEXT NOT NULL, entry_bar_close TEXT,"
            "last_bar_close TEXT, bar_sequence INTEGER NOT NULL DEFAULT 0)",
            "CREATE TABLE IF NOT EXISTS paper_stage9_actions ("
            "action_id TEXT PRIMARY KEY, request_digest TEXT NOT NULL,"
            "receipt_json TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS paper_stage9_bars ("
            "order_id TEXT NOT NULL, bar_close TEXT NOT NULL,"
            "bar_digest TEXT NOT NULL, receipt_json TEXT NOT NULL,"
            "PRIMARY KEY(order_id,bar_close))",
            "CREATE TABLE IF NOT EXISTS paper_stage9_exits ("
            "order_id TEXT NOT NULL, action_id TEXT PRIMARY KEY,"
            "reason TEXT NOT NULL, quantity TEXT NOT NULL, price TEXT NOT NULL,"
            "gross TEXT NOT NULL, modeled_cost TEXT NOT NULL, net TEXT NOT NULL,"
            "evidence_digest TEXT NOT NULL)",
            "CREATE TABLE IF NOT EXISTS paper_stage9_targets ("
            "order_id TEXT NOT NULL, target_index INTEGER NOT NULL,"
            "PRIMARY KEY(order_id,target_index))",
        ):
            self._db.execute(ddl)
        self._needs_recovery = any(
            (snapshot["status"] not in ("CLOSED", "REJECTED") and
             not (snapshot["status"] == "CANCELED" and
                  Decimal(snapshot["filled_quantity"]) == 0))
            for snapshot in (
                self._engine.order_state(row["order_id"])
                for row in self._db.execute("SELECT order_id FROM paper_stage9_plans")
            ) if snapshot is not None
        )

    def register_plan(self, manifest: CoreManifest, event: CoreInput, result: CoreResult,
                      *, decision_id: str, order_id: str, targets: tuple[TargetStep, ...],
                      operator_ack: bool = False) -> dict:
        if operator_ack is not True or type(targets) is not tuple or not 1 <= len(targets) <= 5:
            raise PaperLifecycleRefused("EXPLICIT_TARGET_PLAN_REQUIRED")
        validate_core_result(manifest, event, result)
        if event.origin not in (DataOrigin.REPLAY, DataOrigin.SYNTHETIC):
            raise PaperLifecycleRefused("OFFLINE_ORIGIN_REQUIRED")
        if any(type(t) is not TargetStep for t in targets) or sum((t.fraction for t in targets), Decimal(0)) != 1:
            raise PaperLifecycleRefused("INVALID_TARGET_FRACTIONS")
        if type(decision_id) is not str or type(order_id) is not str:
            raise PaperLifecycleRefused("INVALID_PLAN_IDENTITY")
        decisions = [d for d in result.decisions if d.decision_id == decision_id and d.kind is DecisionKind.ENTRY_INTENT]
        if len(decisions) != 1:
            raise PaperLifecycleRefused("ENTRY_DECISION_REQUIRED")
        d = decisions[0]
        if tuple(t.price for t in targets) != d.targets:
            raise PaperLifecycleRefused("TARGETS_MUST_MATCH_CORE")
        if d.direction is Direction.LONG and any(a.price >= b.price for a,b in zip(targets,targets[1:])):
            raise PaperLifecycleRefused("TARGET_ORDER_INVALID")
        if d.direction is Direction.SHORT and any(a.price <= b.price for a,b in zip(targets,targets[1:])):
            raise PaperLifecycleRefused("TARGET_ORDER_INVALID")
        def commit():
            self._require_ready()
            row = self._db.execute(
                "SELECT s.binding_id,s.instance_id,d.decision_id,d.receipt_json,d.request_digest "
                "FROM paper_core_orders AS s JOIN paper_core_decisions AS d "
                "ON d.order_id=s.order_id WHERE s.order_id=?",(order_id,)).fetchone()
            if row is None or row["binding_id"] != event.binding.binding_id or row["instance_id"] != event.binding.instance_id or row["decision_id"] != decision_id:
                raise PaperLifecycleRefused("STAGE8_ORDER_PROOF_REQUIRED")
            route = self._db.execute("SELECT manifest_digest,binding_digest FROM paper_core_bindings WHERE binding_id=?",(event.binding.binding_id,)).fetchone()
            if route is None or route["manifest_digest"] != content_digest(manifest) or route["binding_digest"] != content_digest(event.binding):
                raise PaperLifecycleRefused("DRIFTED_MANIFEST_OR_BINDING")
            snap = self._engine.order_state(order_id)
            if snap is None or snap["status"] != "CREATED" or snap["revision"] != 0 or snap["spec"]["direction"] != d.direction.value or Decimal(snap["spec"]["reference_entry"]) != d.entry or Decimal(snap["spec"]["stop"]) != d.stop or Decimal(snap["spec"]["target"]) != d.targets[0]:
                raise PaperLifecycleRefused("ORDER_SPEC_OR_STATE_MISMATCH")
            risk_receipt=json.loads(row["receipt_json"])
            if event.binding.instrument.market is Market.CRYPTO:
                basis=PriceBasis.TRADE
                volume=VolumeSemantics.TRADED
            elif event.binding.instrument.market is Market.FOREX:
                basis=PriceBasis.BID_ASK
                volume=VolumeSemantics.UNKNOWN
            else:
                raise PaperLifecycleRefused("UNSUPPORTED_STAGE9_MARKET")
            expected=content_digest({
                "manifest":manifest,"event":event,"result":result,
                "decision_id":decision_id,"quantity":Decimal(snap["spec"]["quantity"]),
                "price_basis":basis,"volume_semantics":volume,
                "expected_revision":risk_receipt["allocation_revision"],
            })
            if row["request_digest"] != expected:
                raise PaperLifecycleRefused("STAGE8_DECISION_DIGEST_MISMATCH")
            existing = self._db.execute("SELECT plan_json FROM paper_stage9_plans WHERE order_id=?",(order_id,)).fetchone()
            plan = {"decision_id":decision_id,"core_id":manifest.core_id,"core_version":manifest.core_version,
                    "binding_id":event.binding.binding_id,"instance_id":event.binding.instance_id,
                    "source_ref":event.source_ref,"timeframe":event.binding.timeframe,
                    "market":event.binding.instrument.market.value,
                    "targets":[{"price":str(t.price),"fraction":str(t.fraction)} for t in targets]}
            raw = _wire(plan)
            if existing is not None:
                if existing["plan_json"] != raw:
                    raise PaperLifecycleRefused("TARGET_PLAN_CONFLICT")
                return {"order_id":order_id,"status":"REGISTERED"}
            self._db.execute("INSERT INTO paper_stage9_plans(order_id,setup_id,manifest_digest,binding_digest,plan_json,input_close) VALUES(?,?,?,?,?,?)",
                             (order_id,d.setup_id,content_digest(manifest),content_digest(event.binding),raw,event.observed_at.isoformat()))
            return {"order_id":order_id,"status":"REGISTERED"}
        return self._engine._transaction(commit)

    def _plan(self, order_id: str):
        identity(order_id,"order_id")
        row = self._db.execute("SELECT * FROM paper_stage9_plans WHERE order_id=?",(order_id,)).fetchone()
        if row is None:
            raise PaperLifecycleRefused("TARGET_PLAN_MISSING")
        return row,json.loads(row["plan_json"])

    def _require_ready(self):
        if self._needs_recovery:
            raise PaperLifecycleRefused("OFFLINE_RECONCILIATION_REQUIRED")

    def reconcile_offline(self, *, operator_ack: bool = False) -> dict:
        """Verifies local Stage3/8 journal consistency, NOT an external broker."""
        if operator_ack is not True:
            raise PaperLifecycleRefused("EXPLICIT_OFFLINE_RECONCILIATION_REQUIRED")
        for row in self._db.execute("SELECT order_id FROM paper_stage9_plans").fetchall():
            order_id=row["order_id"]
            snap=self._engine.order_state(order_id)
            risk=self._db.execute("SELECT status FROM paper_risk_reservations WHERE order_id=?",(order_id,)).fetchone()
            if snap is None or risk is None:
                raise PaperLifecycleRefused("RECONCILIATION_MISSING_LEDGER")
            terminal = (snap["status"] in ("CLOSED","REJECTED") or (snap["status"]=="CANCELED" and Decimal(snap["filled_quantity"])==0))
            if risk["status"] != ("RELEASED" if terminal else "ACTIVE"):
                raise PaperLifecycleRefused("RECONCILIATION_RISK_MISMATCH")
            self._verified_exits(order_id, snap)
        self._needs_recovery=False
        return {
            "mode": "OFFLINE_RECONCILED_LOCAL_ONLY", "broker_verified": False,
            "orders_checked": self._db.execute(
                "SELECT count(*) FROM paper_stage9_plans"
            ).fetchone()[0],
        }

    def _once(self, action_id: str, payload: object, callback):
        identity(action_id,"action_id")
        digest=_hash(payload)
        def commit():
            previous=self._db.execute("SELECT request_digest,receipt_json FROM paper_stage9_actions WHERE action_id=?",(action_id,)).fetchone()
            if previous is not None:
                if previous["request_digest"] != digest:
                    raise PaperLifecycleRefused("LIFECYCLE_ACTION_ID_CONFLICT")
                return _record(previous)
            self._require_ready()
            receipt=callback()
            self._db.execute("INSERT INTO paper_stage9_actions VALUES (?,?,?)",(action_id,digest,_wire(receipt)))
            return receipt
        return self._engine._transaction(commit)

    def apply_paper_event(self, order_id: str, *, action_id: str, event: str,
                          expected_revision: int, operator_ack: bool = False,
                          quantity: Decimal | None = None, price: Decimal | None = None,
                          evidence: str | None = None, remote_order_id: str | None = None,
                          entry_bar: ClosedCandle | None = None) -> dict:
        """Explicit modeled state injection. ACK/FILL are never real confirmations."""
        allowed={"SUBMIT","ACK","FILL","CANCEL","REJECT","MARK_UNKNOWN","RECONCILE_ACK","RECONCILE_REJECT"}
        if operator_ack is not True or event not in allowed or type(expected_revision) is not int:
            raise PaperLifecycleRefused("EXPLICIT_OFFLINE_EVENT_REQUIRED")
        if event=="FILL":
            _positive(quantity,"FILL_QUANTITY");_positive(price,"FILL_PRICE")
            if not isinstance(entry_bar,ClosedCandle):
                raise PaperLifecycleRefused("ENTRY_BAR_REQUIRED")
        elif any(x is not None for x in (quantity,price,entry_bar)):
            raise PaperLifecycleRefused("UNEXPECTED_FILL_FIELDS")
        payload={"kind":"EVENT","order_id":order_id,"event":event,"rev":expected_revision,
                 "quantity":str(quantity) if quantity is not None else None,
                 "price":str(price) if price is not None else None,
                 "entry_bar":content_digest(entry_bar) if entry_bar else None,
                 "remote_order_id":remote_order_id,"evidence":evidence}
        def commit():
            row,plan=self._plan(order_id)
            snap=self._engine.order_state(order_id)
            if snap is None or snap["revision"] != expected_revision:
                raise PaperLifecycleRefused("STALE_ORDER_REVISION")
            if event=="FILL":
                self._check_bar(row,plan,entry_bar)
                if Decimal(snap["filled_quantity"]) > 0 and row["entry_bar_close"] != entry_bar.close_at.isoformat():
                    raise PaperLifecycleRefused("PARTIAL_FILL_BAR_UNSUPPORTED")
                if not entry_bar.low <= price <= entry_bar.high:
                    raise PaperLifecycleRefused("FILL_OUTSIDE_MODELED_BAR")
                if entry_bar.close_at <= datetime.fromisoformat(row["input_close"]):
                    raise PaperLifecycleRefused("LOOKAHEAD_ENTRY_REJECTED")
            receipt=self._engine.apply(order_id,action_id="st9_"+_hash([action_id,"engine"])[:56],
                       event=event,quantity=str(quantity) if quantity is not None else None,
                       price=str(price) if price is not None else None,
                       evidence=evidence,remote_order_id=remote_order_id)
            if event=="FILL":
                self._db.execute("UPDATE paper_stage9_plans SET entry_bar_close=?,last_bar_close=? WHERE order_id=?",
                                 (entry_bar.close_at.isoformat(),entry_bar.close_at.isoformat(),order_id))
            return {"mode":"MODELED_PAPER_ONLY","order_id":order_id,"event":event,
                    "order_status":receipt["order"]["status"],"revision":receipt["order"]["revision"],
                    "risk_released":receipt["risk_released"],"broker_order_sent":False,"telegram_sent":False}
        return self._once(action_id,payload,commit)

    def _check_bar(self,row,plan,candle:ClosedCandle):
        if type(candle) is not ClosedCandle or plan["market"] != Market.CRYPTO.value:
            raise PaperLifecycleRefused("CRYPTO_OFFLINE_CANDLE_ONLY")
        interval=timedelta(minutes=_TIMEFRAME_MINUTES[plan["timeframe"]])
        if candle.close_at-candle.open_at != interval:
            raise PaperLifecycleRefused("BAR_TIMEFRAME_MISMATCH")

    def _exit(self,order_id,reason,quantity:Decimal,price:Decimal,evidence_digest:str,action_id:str):
        snap=self._engine.order_state(order_id)
        if snap["status"]=="PARTIALLY_FILLED":
            self._engine.apply(order_id,action_id=action_id+"_cancel",event="CANCEL")
            snap=self._engine.order_state(order_id)
        before=Decimal(snap["closed_quantity"])
        receipt=self._engine.apply(order_id,action_id=action_id,event="CLOSE_FILL",quantity=str(quantity),price=str(price))
        after=Decimal(receipt["order"]["closed_quantity"])
        if after-before != quantity:
            raise PaperLifecycleRefused("EXIT_QUANTITY_MISMATCH")
        ap=self._db.execute("SELECT policy FROM risk_accounts WHERE account_id=?",(snap["spec"]["account_id"],)).fetchone()
        if ap is None:
            raise PaperLifecycleRefused("RISK_POLICY_MISSING")
        policy=json.loads(ap["policy"])
        economics=self._engine._risk.order_economics(order_id)
        avg=Decimal(snap["average_fill_price"])
        if economics is None:
            multiplier=Decimal(policy["contract_multiplier"])
            friction=Decimal(policy["roundtrip_fee_fraction"])+Decimal(policy["worst_slippage_fraction"])
            sign=Decimal(1) if snap["spec"]["direction"]=="long" else Decimal(-1)
            gross=sign*(price-avg)*quantity*multiplier
            cost=max(price,avg)*quantity*multiplier*friction
        else:
            gross,cost=economics.modeled_exit(
                quantity=quantity,entry=avg,exit_price=price,
                direction=snap["spec"]["direction"])
        net=gross-cost
        self._db.execute("INSERT INTO paper_stage9_exits VALUES (?,?,?,?,?,?,?,?,?)",
                         (order_id,action_id,reason,str(quantity),str(price),str(gross),str(cost),str(net),evidence_digest))
        return {"reason":reason,"quantity":str(quantity),"price":str(price),
                "gross":str(gross),"modeled_cost":str(cost),"net":str(net),
                "risk_released":receipt["risk_released"]}

    def step_closed_bar(self,order_id:str,bar:ClosedCandle,*,operator_ack:bool=False) -> dict:
        """Causal crypto OHLC replay; stop before target on ambiguous bars.

        Explicitly synthetic assumptions: no venue execution, no same-entry-bar
        exits, adverse stop gap price; favorable target gaps get no extra credit.
        """
        if operator_ack is not True:
            raise PaperLifecycleRefused("EXPLICIT_OFFLINE_BAR_REQUIRED")
        digest=content_digest(bar)
        def commit():
            row,plan=self._plan(order_id)
            self._check_bar(row,plan,bar)
            replay=self._db.execute("SELECT * FROM paper_stage9_bars WHERE order_id=? AND bar_close=?",(order_id,bar.close_at.isoformat())).fetchone()
            if replay is not None:
                if replay["bar_digest"] != digest:
                    raise PaperLifecycleRefused("BAR_REPLAY_CONFLICT")
                return _record(replay)
            self._require_ready()
            snap=self._engine.order_state(order_id)
            if snap is None or snap["status"] not in ("FILLED","PARTIALLY_FILLED","CANCELED") or Decimal(snap["open_position_quantity"]) <= 0:
                raise PaperLifecycleRefused("OPEN_PAPER_POSITION_REQUIRED")
            if row["entry_bar_close"] is None or row["last_bar_close"] is None:
                raise PaperLifecycleRefused("NO_VERIFIED_ENTRY_BAR")
            if bar.open_at.isoformat() != row["last_bar_close"]:
                raise PaperLifecycleRefused("BAR_GAP_OR_REPLAY")
            if bar.close_at <= datetime.fromisoformat(row["entry_bar_close"]):
                raise PaperLifecycleRefused("SAME_ENTRY_BAR_EXIT_FORBIDDEN")
            action_root="st9_"+_hash([order_id,bar.close_at.isoformat()])[:49]
            outcomes=[]
            stop=Decimal(snap["current_stop"])
            side=snap["spec"]["direction"]
            stop_hit=(bar.low <= stop if side=="long" else bar.high >= stop)
            if stop_hit:
                gap=(bar.open <= stop if side=="long" else bar.open >= stop)
                fill_price=bar.open if gap else stop
                outcomes.append(self._exit(order_id,"STOP",Decimal(snap["open_position_quantity"]),
                                           fill_price,digest,action_root+"_stop"))
            else:
                original=Decimal(snap["filled_quantity"])
                economics=self._engine._risk.order_economics(order_id)
                step=(economics.quantity_step if economics is not None
                      else Decimal(json.loads(self._db.execute("SELECT policy FROM risk_accounts WHERE account_id=?",(snap["spec"]["account_id"],)).fetchone()["policy"])["quantity_step"]))
                for i,t in enumerate(plan["targets"]):
                    if self._db.execute("SELECT 1 FROM paper_stage9_targets WHERE order_id=? AND target_index=?",(order_id,i)).fetchone():
                        continue
                    target=Decimal(t["price"])
                    touched=(bar.high>=target if side=="long" else bar.low<=target)
                    if not touched:
                        # Ordered targets: cannot leapfrog a nearer target.
                        break
                    left=Decimal(self._engine.order_state(order_id)["open_position_quantity"])
                    if left<=0:break
                    amount=((original*Decimal(t["fraction"]))/step).to_integral_value(rounding=ROUND_DOWN)*step
                    if i==len(plan["targets"])-1:amount=left
                    else:amount=min(left,amount)
                    if amount<=0:
                        raise PaperLifecycleRefused("TARGET_QUANTITY_BELOW_STEP")
                    outcomes.append(self._exit(order_id,"TARGET_"+str(i+1),amount,target,digest,action_root+"_tp"+str(i)))
                    self._db.execute("INSERT INTO paper_stage9_targets VALUES (?,?)",(order_id,i))
            self._db.execute("UPDATE paper_stage9_plans SET last_bar_close=?,bar_sequence=bar_sequence+1 WHERE order_id=?",(bar.close_at.isoformat(),order_id))
            receipt={"mode":"MODELED_PAPER_ONLY","order_id":order_id,"closed_bar":bar.close_at.isoformat(),
                     "exits":outcomes,"status":self._engine.order_state(order_id)["status"],
                     "broker_order_sent":False,"telegram_sent":False}
            self._db.execute("INSERT INTO paper_stage9_bars VALUES (?,?,?,?)",(order_id,bar.close_at.isoformat(),digest,_wire(receipt)))
            return receipt
        return self._engine._transaction(commit)

    def apply_core_stop(self, manifest:CoreManifest,event:CoreInput,result:CoreResult,
                        *,decision_id:str,order_id:str,action_id:str,
                        expected_order_revision:int,operator_ack:bool=False) -> dict:
        """The core decides NEW stop; host validates and simulates amend."""
        if operator_ack is not True or type(expected_order_revision) is not int:
            raise PaperLifecycleRefused("EXPLICIT_CORE_MANAGEMENT_REQUIRED")
        validate_core_result(manifest,event,result)
        if event.event is not CoreEventType.POSITION_UPDATE or event.origin not in (DataOrigin.REPLAY,DataOrigin.SYNTHETIC):
            raise PaperLifecycleRefused("POSITION_UPDATE_REQUIRED")
        decisions=[d for d in result.decisions if d.decision_id==decision_id and d.kind is DecisionKind.MANAGEMENT_INTENT and d.action is ManagementAction.MOVE_STOP]
        if len(decisions)!=1:
            raise PaperLifecycleRefused("MOVE_STOP_DECISION_REQUIRED")
        d=decisions[0]
        payload={"mode":"core_stop","order_id":order_id,"decision":content_digest(d),"event":event.input_digest,"rev":expected_order_revision}
        def commit():
            row,plan=self._plan(order_id)
            if row["last_bar_close"] is None or event.observed_at.isoformat() != row["last_bar_close"]:
                raise PaperLifecycleRefused("MANAGEMENT_REQUIRES_PROCESSED_BAR")
            if (content_digest(manifest)!=row["manifest_digest"] or content_digest(event.binding)!=row["binding_digest"] or
                    plan["core_id"]!=event.core_id or plan["core_version"]!=event.core_version or
                    d.setup_id!=row["setup_id"] or d.position_id!=order_id or
                    event.source_ref!=plan["source_ref"]):
                raise PaperLifecycleRefused("MANAGEMENT_OWNERSHIP_MISMATCH")
            snap=self._engine.order_state(order_id)
            if snap is None or snap["revision"]!=expected_order_revision or d.expected_position_revision!=expected_order_revision or event.position is None:
                raise PaperLifecycleRefused("STALE_POSITION_REVISION")
            if (event.position.position_id!=order_id or event.position.setup_id!=row["setup_id"] or
                    event.position.current_stop!=Decimal(snap["current_stop"]) or event.position.entry!=Decimal(snap["spec"]["reference_entry"]) or
                    event.position.initial_stop!=Decimal(snap["spec"]["stop"]) or
                    event.position.direction.value!=snap["spec"]["direction"]):
                raise PaperLifecycleRefused("POSITION_SNAPSHOT_MISMATCH")
            received=self._engine.apply(order_id,action_id="st9_"+_hash([action_id,"stop"])[:55],event="AMEND_STOP",stop=str(d.new_stop))
            return {"mode":"MODELED_PAPER_ONLY","order_id":order_id,"status":received["order"]["status"],
                    "revision":received["order"]["revision"],"stop":received["order"]["current_stop"],
                    "broker_order_sent":False,"telegram_sent":False}
        return self._once(action_id,payload,commit)

    def apply_core_exit(self, manifest: CoreManifest, event: CoreInput, result: CoreResult,
                        *, decision_id: str, order_id: str, action_id: str,
                        execution_bar: ClosedCandle, expected_order_revision: int,
                        operator_ack: bool = False) -> dict:
        """Core's CLOSE_POSITION decision executes at NEXT synthetic bar OPEN.

        The first bar after the confirmed decision is a modeling assumption;
        a live broker fill, gap quote, slippage or stop-before-open cannot be
        inferred. This routine is never callable by a plugin without host gate.
        """
        if operator_ack is not True or type(expected_order_revision) is not int:
            raise PaperLifecycleRefused("EXPLICIT_CORE_EXIT_REQUIRED")
        validate_core_result(manifest,event,result)
        if event.event is not CoreEventType.POSITION_UPDATE or event.origin not in (DataOrigin.REPLAY, DataOrigin.SYNTHETIC):
            raise PaperLifecycleRefused("POSITION_UPDATE_REQUIRED")
        decision = [d for d in result.decisions if d.decision_id==decision_id and
                    d.kind is DecisionKind.EXIT_INTENT and d.action is ExitAction.CLOSE_POSITION]
        if len(decision)!=1:
            raise PaperLifecycleRefused("CLOSE_POSITION_INTENT_REQUIRED")
        d=decision[0]
        digest=content_digest(execution_bar)
        payload={"action":"CORE_EXIT","order_id":order_id,"decision":content_digest(d),
                 "event":event.input_digest,"bar":digest,"rev":expected_order_revision}
        def commit():
            row,plan=self._plan(order_id)
            self._check_bar(row,plan,execution_bar)
            if (content_digest(manifest)!=row["manifest_digest"] or
                    content_digest(event.binding)!=row["binding_digest"] or
                    event.source_ref!=plan["source_ref"] or
                    event.core_id!=plan["core_id"] or event.core_version!=plan["core_version"] or
                    d.position_id!=order_id or d.setup_id!=row["setup_id"]):
                raise PaperLifecycleRefused("EXIT_OWNERSHIP_MISMATCH")
            snap=self._engine.order_state(order_id)
            if (snap is None or snap["revision"]!=expected_order_revision or
                    d.expected_position_revision!=expected_order_revision or
                    event.position is None or event.position.position_id!=order_id or
                    event.position.setup_id!=row["setup_id"] or
                    event.position.revision!=expected_order_revision or
                    event.position.current_stop!=Decimal(snap["current_stop"]) or
                    event.position.direction.value!=snap["spec"]["direction"] or
                    event.position.initial_stop!=Decimal(snap["spec"]["stop"]) or
                    event.position.entry!=Decimal(snap["spec"]["reference_entry"])):
                raise PaperLifecycleRefused("STALE_OR_MISMATCHED_EXIT_POSITION")
            if (row["last_bar_close"]!=event.observed_at.isoformat() or
                    execution_bar.open_at!=event.observed_at):
                raise PaperLifecycleRefused("EXIT_REQUIRES_NEXT_BAR_OPEN")
            if (snap["status"] not in ("FILLED","PARTIALLY_FILLED","CANCELED") or
                    Decimal(snap["open_position_quantity"])<=0):
                raise PaperLifecycleRefused("EXIT_REQUIRES_OPEN_POSITION")
            existing=self._db.execute("SELECT 1 FROM paper_stage9_bars WHERE order_id=? AND bar_close=?",
                                      (order_id,execution_bar.close_at.isoformat())).fetchone()
            if existing is not None:
                raise PaperLifecycleRefused("EXECUTION_BAR_ALREADY_HANDLED")
            exit_record=self._exit(order_id,"CORE_EXIT",Decimal(snap["open_position_quantity"]),
                                   execution_bar.open,digest,"st9_"+_hash([action_id,"core_exit"])[:50])
            receipt={"mode":"MODELED_PAPER_ONLY","order_id":order_id,
                     "closed_bar":execution_bar.close_at.isoformat(),"exits":[exit_record],
                     "status":self._engine.order_state(order_id)["status"],
                     "broker_order_sent":False,"telegram_sent":False}
            self._db.execute("UPDATE paper_stage9_plans SET last_bar_close=?,bar_sequence=bar_sequence+1 WHERE order_id=?",
                             (execution_bar.close_at.isoformat(),order_id))
            self._db.execute("INSERT INTO paper_stage9_bars VALUES (?,?,?,?)",
                             (order_id,execution_bar.close_at.isoformat(),digest,_wire(receipt)))
            return receipt
        return self._once(action_id,payload,commit)

    def _verified_exits(self, order_id: str, snapshot: dict) -> list:
        """Reconcile PnL amounts with economics, bar receipts and closed lots.

        Read-only checks; corrupt PAPER settlement data must never be shown as
        verified performance, or accepted during an offline restart.
        """
        rows = self._db.execute(
            "SELECT reason,quantity,price,gross,modeled_cost,net,evidence_digest "
            "FROM paper_stage9_exits WHERE order_id=? ORDER BY rowid",
            (order_id,),
        ).fetchall()
        bars = self._db.execute(
            "SELECT bar_digest,receipt_json FROM paper_stage9_bars WHERE order_id=?",
            (order_id,),
        ).fetchall()
        expected = Counter()
        fields = ("reason", "quantity", "price", "gross", "modeled_cost", "net")
        try:
            for bar in bars:
                receipt = json.loads(bar["receipt_json"])
                if receipt["order_id"] != order_id:
                    raise PaperLifecycleRefused("PAPER_EXIT_RECEIPT_DRIFT")
                for exit_receipt in receipt["exits"]:
                    key = (bar["bar_digest"],) + tuple(
                        exit_receipt[field] for field in fields
                    )
                    expected[key] += 1

            closed = Decimal(snapshot["closed_quantity"])
            filled = Decimal(snapshot["filled_quantity"])
            if not closed.is_finite() or not filled.is_finite() or (
                closed < 0 or filled < closed
            ):
                raise PaperLifecycleRefused("PAPER_EXIT_QUANTITY_DRIFT")
            account_id = snapshot["spec"]["account_id"]
            account = self._db.execute(
                "SELECT policy FROM risk_accounts WHERE account_id=?",
                (account_id,),
            ).fetchone()
            if account is None:
                raise PaperLifecycleRefused("PAPER_EXIT_POLICY_MISSING")
            policy = json.loads(account["policy"])
            economics = self._engine._risk.order_economics(order_id)
            entry = (
                Decimal(snapshot["average_fill_price"])
                if filled > 0 else None
            )
            if entry is not None and (not entry.is_finite() or entry <= 0):
                raise PaperLifecycleRefused("PAPER_EXIT_ENTRY_INVALID")
            aggregate_quantity = Decimal(0)
            for row in rows:
                values = [Decimal(row[field]) for field in (
                    "quantity", "price", "gross", "modeled_cost", "net"
                )]
                quantity, price, gross, cost, net = values
                if (not all(value.is_finite() for value in values)
                        or quantity <= 0 or price <= 0 or cost < 0
                        or entry is None):
                    raise PaperLifecycleRefused("PAPER_EXIT_PNL_INVALID")
                aggregate_quantity += quantity
                if economics is None:
                    multiplier = Decimal(policy["contract_multiplier"])
                    friction = (
                        Decimal(policy["roundtrip_fee_fraction"])
                        + Decimal(policy["worst_slippage_fraction"])
                    )
                    sign = (Decimal(1) if snapshot["spec"]["direction"] == "long"
                            else Decimal(-1))
                    predicted_gross = sign * (price - entry) * quantity * multiplier
                    predicted_cost = max(price, entry) * quantity * multiplier * friction
                else:
                    predicted_gross, predicted_cost = economics.modeled_exit(
                        quantity=quantity, entry=entry, exit_price=price,
                        direction=snapshot["spec"]["direction"],
                    )
                if (gross != predicted_gross or cost != predicted_cost
                        or net != gross - cost):
                    raise PaperLifecycleRefused("PAPER_EXIT_PNL_DRIFT")
                key = (row["evidence_digest"],) + tuple(
                    row[field] for field in fields
                )
                if expected[key] <= 0:
                    raise PaperLifecycleRefused("PAPER_EXIT_RECEIPT_DRIFT")
                expected[key] -= 1
            if aggregate_quantity != closed:
                raise PaperLifecycleRefused("PAPER_EXIT_QUANTITY_DRIFT")
            if any(expected.values()):
                raise PaperLifecycleRefused("PAPER_EXIT_RECEIPT_DRIFT")
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            if isinstance(exc, PaperLifecycleRefused):
                raise
            raise PaperLifecycleRefused("PAPER_EXIT_LEDGER_INVALID") from exc
        return rows

    def performance(self,order_id:str)->dict:
        row,plan=self._plan(order_id)
        snap=self._engine.order_state(order_id)
        entries=self._verified_exits(order_id,snap)
        gross=sum((Decimal(x["gross"]) for x in entries),Decimal(0))
        cost=sum((Decimal(x["modeled_cost"]) for x in entries),Decimal(0))
        net=gross-cost
        initial=Decimal(snap["spec"]["reference_entry"])
        stop=Decimal(snap["spec"]["stop"])
        qty=Decimal(snap["filled_quantity"])
        ap=self._db.execute(
            "SELECT policy FROM risk_accounts WHERE account_id=?",
            (snap["spec"]["account_id"],),
        ).fetchone()
        economics=self._engine._risk.order_economics(order_id)
        mul=(economics.contract_multiplier if economics is not None
             else Decimal(json.loads(ap["policy"])["contract_multiplier"]))
        initial_risk=qty*abs(initial-stop)*mul
        return {"order_id":order_id,"mode":"MODELED_PAPER_ONLY","status":snap["status"],
                "filled_quantity":snap["filled_quantity"],"closed_quantity":snap["closed_quantity"],
                "gross":str(gross),"modeled_cost":str(cost),"net":str(net),
                "net_realized_r":str(net/initial_risk) if initial_risk>0 else None,
                "exits":[
                    {k:x[k] for k in (
                        "reason", "quantity", "price", "gross", "modeled_cost", "net"
                    )} for x in entries
                ],
                "economics_digest": economics.digest if economics else None,
                "quote_currency": economics.settle_currency if economics else None,
                "broker_verified":False,
                "telegram_sent":False,"broker_order_sent":False}


__all__=["OfflinePaperPositionLifecycle","PaperLifecycleRefused","TargetStep"]