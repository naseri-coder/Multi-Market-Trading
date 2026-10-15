"""Stage 11: read-only reproducible evidence audit of Stage-8/9 PAPER trades.

This module does not generate market data, call a core, send Telegram messages,
trade, change databases, or claim edge from an unverified replay. It refuses
invalid or incomplete evidence rather than silently omitting losers.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import stat
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median
from typing import Any

from .research_walk_forward_v1 import (
    WalkForwardRefused, WalkForwardSettings, evaluate_walk_forward,
)

MAX_MANIFEST = 65536
MAX_ORDERS = 10000
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z")
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_KEYS = frozenset({
    "schema_version", "study_id", "core_id", "instance_id", "account_id",
    "window_start_utc", "training_end_utc", "validation_end_utc",
    "window_end_utc", "expected_order_ids", "dataset_origin",
    "declared_dataset_sha256", "initial_equity", "min_closed_per_segment",
    "claimed_protocol_frozen_before_outcomes",
})
_REQUIRED_TABLES = frozenset({"paper_stage9_plans", "paper_stage9_exits", "paper_stage9_bars",
                             "paper_core_orders", "paper_orders", "risk_accounts",
                             "paper_core_allocations", "paper_core_bindings", "paper_core_decisions"})


class ResearchLabRefused(ValueError):
    """Explicit fail-closed diagnostic error; no source/trade details leaked."""


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise ResearchLabRefused("DUPLICATE_JSON_FIELD")
        obj[key] = value
    return obj


def _load_json(raw: str | bytes) -> dict:
    if not isinstance(raw, (str, bytes)) or len(raw) > MAX_MANIFEST * 16:
        raise ResearchLabRefused("JSON_BOUNDS")
    try:
        o = json.loads(raw, object_pairs_hook=_unique,
                       parse_float=Decimal,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
    except ResearchLabRefused:
        raise
    except (ValueError, UnicodeError, TypeError) as exc:
        raise ResearchLabRefused("INVALID_JSON") from exc
    if type(o) is not dict:
        raise ResearchLabRefused("JSON_OBJECT_REQUIRED")
    return o


def _when(value: object) -> datetime:
    if type(value) is not str or not 15 <= len(value) <= 48:
        raise ResearchLabRefused("INVALID_UTC_TIMESTAMP")
    try:
        t = datetime.fromisoformat(value)
        if t.tzinfo is None or t.utcoffset() != timedelta(0):
            raise ValueError("non-UTC")
        return t.astimezone(UTC)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ResearchLabRefused("INVALID_UTC_TIMESTAMP") from exc


def _decimal(value: object, *, positive: bool = False, nonnegative: bool = False) -> Decimal:
    if type(value) is not str or not 1 <= len(value) <= 64:
        raise ResearchLabRefused("DECIMAL_STRING_REQUIRED")
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise ResearchLabRefused("INVALID_DECIMAL") from exc
    if not result.is_finite() or (positive and result <= 0) or (nonnegative and result < 0):
        raise ResearchLabRefused("INVALID_DECIMAL")
    return result


def _wire(value: object) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, default=lambda x: str(x) if isinstance(x, Decimal) else _fail())


def _fail() -> object:
    raise ResearchLabRefused("NONCANONICAL_EVIDENCE")


def _digest(value: object) -> str:
    return hashlib.sha256(_wire(value).encode("utf-8")).hexdigest()


def parse_protocol(raw: bytes) -> dict:
    """Predeclared scope; claimed freeze is not independent timestamp proof."""
    if type(raw) is not bytes or not 1 <= len(raw) <= MAX_MANIFEST:
        raise ResearchLabRefused("PROTOCOL_BYTES_BOUND")
    d = _load_json(raw)
    if set(d) != _KEYS or type(d["schema_version"]) is not int or d["schema_version"] != 1:
        raise ResearchLabRefused("PROTOCOL_SCHEMA")
    for key in ("study_id", "core_id", "instance_id", "account_id"):
        if type(d[key]) is not str or not _ID.fullmatch(d[key]):
            raise ResearchLabRefused("INVALID_PROTOCOL_ID")
    ids = d["expected_order_ids"]
    if type(ids) is not list or len(ids) > MAX_ORDERS or any(
        type(x) is not str or not _ID.fullmatch(x) for x in ids
    ) or len(set(ids)) != len(ids):
        raise ResearchLabRefused("INVALID_EXPECTED_ORDER_SET")
    if (d["dataset_origin"] not in ("synthetic_fixture", "operator_offline_unverified")
            or type(d["declared_dataset_sha256"]) is not str
            or not _HASH.fullmatch(d["declared_dataset_sha256"])):
        raise ResearchLabRefused("DATASET_PROVENANCE_UNVERIFIED")
    if (type(d["claimed_protocol_frozen_before_outcomes"]) is not bool
            or d["claimed_protocol_frozen_before_outcomes"] is not True):
        raise ResearchLabRefused("PROTOCOL_FREEZE_CLAIM_REQUIRED")
    if (type(d["min_closed_per_segment"]) is not int
            or not 1 <= d["min_closed_per_segment"] <= 10000):
        raise ResearchLabRefused("INVALID_MINIMUM_SAMPLE")
    _decimal(d["initial_equity"], positive=True)
    bounds = [_when(d[key]) for key in ("window_start_utc", "training_end_utc",
                                       "validation_end_utc", "window_end_utc")]
    if not bounds[0] < bounds[1] < bounds[2] < bounds[3] or bounds[-1]-bounds[0] > timedelta(days=400):
        raise ResearchLabRefused("INVALID_STUDY_BOUNDARIES")
    return d


def _partition(when: datetime, boundaries: tuple[datetime, ...]) -> str:
    for index, name in enumerate(("training", "validation", "holdout")):
        if boundaries[index] <= when < boundaries[index+1]:
            return name
    return "outside"


def _metrics(records: list[dict], initial_equity: Decimal) -> dict:
    """Equity drawdown uses CLOSED-trade chronological cash PnL only."""
    closed = sorted((r for r in records if r["outcome"] == "CLOSED_PAPER"),
                    key=lambda r: (r["exit_at"], r["order_id"]))
    rs = [r["net_r"] for r in closed]
    profits = [r["net"] for r in closed if r["net"] > 0]
    losses = [r["net"] for r in closed if r["net"] < 0]
    start = initial_equity
    equity, peak, max_dd = start, start, Decimal(0)
    for row in closed:
        equity += row["net"]
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak-equity)/peak)
    total_costs = sum((r["cost"] for r in closed), Decimal(0))
    return {
        "population": len(records),
        "closed": len(closed),
        "unfilled": sum(r["outcome"] == "UNFILLED" for r in records),
        "open_or_incomplete": sum(r["outcome"] == "INCOMPLETE" for r in records),
        "cross_split_closes": sum(bool(r["cross_split"]) for r in records),
        "winners": sum(r["net"] > 0 for r in closed),
        "losers": sum(r["net"] < 0 for r in closed),
        "breakeven": sum(r["net"] == 0 for r in closed),
        "win_rate": str(Decimal(sum(r["net"] > 0 for r in closed))/len(closed)) if closed else None,
        "mean_net_r": str(sum(rs, Decimal(0))/len(rs)) if rs else None,
        "median_net_r": str(median(rs)) if rs else None,
        "gross_pnl": str(sum((r["gross"] for r in closed), Decimal(0))),
        "modeled_costs": str(total_costs),
        "net_pnl": str(sum((r["net"] for r in closed), Decimal(0))),
        "profit_factor": str(sum(profits, Decimal(0))/-sum(losses, Decimal(0))) if losses else None,
        "profit_factor_note": "NO_LOSSES_OR_NO_CLOSED_TRADES" if not losses else None,
        "stress_2x_cost_net_pnl": str(sum((r["gross"]-2*r["cost"] for r in closed), Decimal(0))),
        "stress_2x_cost_mean_r": str(sum((r["net_r"]-r["cost"]/r["initial_risk"] for r in closed), Decimal(0))/len(closed)) if closed else None,
        "closed_trade_equity_end": str(equity),
        "closed_trade_max_drawdown_fraction": str(max_dd),
        "drawdown_note": "EXCLUDES_UNREALIZED_EXPOSURE_AND_OVERLAPPING_POSITION_MARK_TO_MARKET",
    }


def evaluate_stage9_research(
    db_path: str | Path, protocol_bytes: bytes, *,
    walk_forward_folds: int | None = None, embargo_seconds: int = 0,
) -> dict:
    """Analyze full scoped Stage-9 population from a read-only SQLite snapshot.

    Research judgments intentionally never assert profitable real-money edge.
    No mutation, code execution, plugin import, network, broker or Telegram.
    """
    protocol = parse_protocol(protocol_bytes)
    if walk_forward_folds is None:
        if type(embargo_seconds) is not int or embargo_seconds != 0:
            raise ResearchLabRefused("WF_FOLDS_REQUIRED_FOR_EMBARGO")
        wf_settings = None
    else:
        try:
            wf_settings = WalkForwardSettings(walk_forward_folds, embargo_seconds)
        except WalkForwardRefused as exc:
            raise ResearchLabRefused("INVALID_WALK_FORWARD_SETTINGS") from exc
    p = Path(db_path)
    if str(db_path) == ":memory:" or p.is_symlink() or not p.is_file():
        raise ResearchLabRefused("EXISTING_REGULAR_RESEARCH_DB_REQUIRED")
    try:
        if not stat.S_ISREG(p.stat().st_mode):
            raise ResearchLabRefused("NONREGULAR_RESEARCH_DB")
        # URI mode=ro; immutable=1 is deliberately NOT used: would hide WAL.
        from urllib.parse import quote
        conn = sqlite3.connect("file:" + quote(str(p.resolve()), safe="/") + "?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        names = {x[0] for x in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not _REQUIRED_TABLES.issubset(names):
            raise ResearchLabRefused("MISSING_STAGE8_OR_STAGE9_EVIDENCE")
        start, train_end, validation_end, end = (
            _when(protocol[x]) for x in ("window_start_utc", "training_end_utc",
                                        "validation_end_utc", "window_end_utc")
        )
        boundaries = (start, train_end, validation_end, end)
        cur = conn.execute("""
            SELECT p.order_id,p.input_close,p.entry_bar_close,p.last_bar_close,
                   p.plan_json,p.setup_id,p.manifest_digest,p.binding_digest,
                   m.account_id,m.instance_id,m.binding_id,o.snapshot,
                   a.policy AS account_policy, b.manifest_digest AS registered_manifest_digest,
                   b.binding_digest AS registered_binding_digest,
                   alloc.policy_json AS allocation_policy, d.decision_id AS source_decision_id
              FROM paper_stage9_plans p
              JOIN paper_core_orders m ON m.order_id=p.order_id
              JOIN paper_orders o ON o.order_id=p.order_id
              JOIN risk_accounts a ON a.account_id=m.account_id
              JOIN paper_core_bindings b ON b.binding_id=m.binding_id
              JOIN paper_core_allocations alloc ON alloc.instance_id=m.instance_id
              JOIN paper_core_decisions d ON d.order_id=p.order_id AND d.binding_id=m.binding_id
             WHERE m.account_id=? AND m.instance_id=?
             ORDER BY p.order_id LIMIT ?
        """, (protocol["account_id"], protocol["instance_id"], MAX_ORDERS + 1))
        all_rows = cur.fetchall()
        # Inventory the base plan table BEFORE inner joins: missing evidence
        # must never disappear from the studied denominator.
        base_plans = conn.execute(
            "SELECT order_id,input_close,plan_json FROM paper_stage9_plans LIMIT ?",
            (MAX_ORDERS + 1,),
        ).fetchall()
        if len(base_plans) > MAX_ORDERS:
            raise ResearchLabRefused("STUDY_PLAN_POPULATION_EXCEEDS_LIMIT")
        base_scope = set()
        for base in base_plans:
            bp = _load_json(base["plan_json"])
            if (bp.get("core_id") == protocol["core_id"] and
                    bp.get("instance_id") == protocol["instance_id"] and
                    start <= _when(base["input_close"]) < end):
                base_scope.add(base["order_id"])
        missing_plan_rows = conn.execute(
            "SELECT s.order_id FROM paper_core_orders s "
            "LEFT JOIN paper_stage9_plans p ON p.order_id=s.order_id "
            "WHERE s.account_id=? AND s.instance_id=? AND p.order_id IS NULL LIMIT ?",
            (protocol["account_id"], protocol["instance_id"], MAX_ORDERS + 1),
        ).fetchall()
        if len(missing_plan_rows) > MAX_ORDERS:
            raise ResearchLabRefused("STUDY_UNLINKED_ORDER_POPULATION_EXCEEDS_LIMIT")
        if len(all_rows) > MAX_ORDERS:
            raise ResearchLabRefused("STUDY_POPULATION_EXCEEDS_LIMIT")
        scoped: list[sqlite3.Row] = []
        for row in all_rows:
            plan = _load_json(row["plan_json"])
            if plan.get("core_id") != protocol["core_id"]:
                continue
            at = _when(row["input_close"])
            if start <= at < end:
                scoped.append(row)
        ids = {r["order_id"] for r in scoped}
        if ids != base_scope or ids != set(protocol["expected_order_ids"]):
            raise ResearchLabRefused("NONEXHAUSTIVE_OR_DRIFTED_COHORT")
        records: list[dict] = []
        evidence: list[dict] = []
        for row in scoped:
            plan = _load_json(row["plan_json"])
            snap = _load_json(row["snapshot"])
            policy = _load_json(row["account_policy"])
            allocation = _load_json(row["allocation_policy"])
            spec = snap.get("spec")
            if (type(spec) is not dict or spec.get("account_id") != protocol["account_id"]
                    or spec.get("engine_id") != protocol["core_id"]
                    or plan.get("instance_id") != protocol["instance_id"]
                    or plan.get("binding_id") != row["binding_id"]
                    or plan.get("core_id") != protocol["core_id"]
                    or plan.get("decision_id") != row["source_decision_id"]
                    or plan.get("core_version") != allocation.get("core_version")
                    or allocation.get("account_id") != protocol["account_id"]
                    or allocation.get("core_id") != protocol["core_id"]
                    or allocation.get("instance_id") != protocol["instance_id"]
                    or not _HASH.fullmatch(row["manifest_digest"]) or not _HASH.fullmatch(row["binding_digest"])
                    or row["manifest_digest"] != row["registered_manifest_digest"]
                    or row["binding_digest"] != row["registered_binding_digest"]):
                raise ResearchLabRefused("CROSS_CORE_OR_ACCOUNT_EVIDENCE")
            instrument = spec.get("instrument", {})
            if (type(instrument) is not dict or
                    instrument.get("market") != plan.get("market") or
                    type(instrument.get("provider")) is not str or
                    type(instrument.get("symbol")) is not str or
                    type(plan.get("timeframe")) is not str or
                    plan.get("timeframe") not in ("1m", "5m", "15m", "30m", "1h", "4h", "12h", "1d")):
                raise ResearchLabRefused("INSTRUMENT_OR_TIMEFRAME_MISMATCH")
            qty = _decimal(snap.get("filled_quantity"), nonnegative=True)
            closed_qty = _decimal(snap.get("closed_quantity"), nonnegative=True)
            entry = _decimal(spec.get("reference_entry"), positive=True)
            stop = _decimal(spec.get("stop"), positive=True)
            mul = _decimal(policy.get("contract_multiplier"), positive=True)
            if qty < closed_qty or entry == stop or spec.get("direction") not in ("long", "short"):
                raise ResearchLabRefused("INVALID_ORDER_GEOMETRY_OR_QUANTITY")
            status = snap.get("status")
            exit_rows = conn.execute(
                "SELECT action_id,reason,quantity,price,gross,modeled_cost,net,evidence_digest "
                "FROM paper_stage9_exits WHERE order_id=? ORDER BY action_id", (row["order_id"],)
            ).fetchall()
            bars = conn.execute(
                "SELECT bar_close,bar_digest,receipt_json FROM paper_stage9_bars WHERE order_id=?",
                (row["order_id"],)
            ).fetchall()
            bar_evidence: dict[str, datetime] = {}
            for bar in bars:
                t = _when(bar["bar_close"])
                if not _HASH.fullmatch(bar["bar_digest"]):
                    raise ResearchLabRefused("INVALID_BAR_EVIDENCE_DIGEST")
                if bar["bar_digest"] in bar_evidence:
                    raise ResearchLabRefused("AMBIGUOUS_BAR_EVIDENCE")
                receipt = _load_json(bar["receipt_json"])
                if receipt.get("order_id") != row["order_id"] or receipt.get("closed_bar") != bar["bar_close"]:
                    raise ResearchLabRefused("BAR_RECEIPT_IDENTITY_MISMATCH")
                bar_evidence[bar["bar_digest"]] = t
            gross = cost = net = sum_qty = Decimal(0)
            exit_times: list[datetime] = []
            bar_exit_usage: dict[str, int] = {}
            signed = Decimal(1) if spec["direction"] == "long" else Decimal(-1)
            avg_raw = snap.get("average_fill_price")
            avg = _decimal(avg_raw, positive=True) if qty > 0 else None
            for x in exit_rows:
                q = _decimal(x["quantity"], positive=True)
                price = _decimal(x["price"], positive=True)
                g = _decimal(x["gross"])
                c = _decimal(x["modeled_cost"], nonnegative=True)
                n = _decimal(x["net"])
                if n != g-c or avg is None or x["evidence_digest"] not in bar_evidence:
                    raise ResearchLabRefused("UNVERIFIED_EXIT_COST_OR_BAR")
                fee = _decimal(policy.get("roundtrip_fee_fraction"), nonnegative=True)
                slip = _decimal(policy.get("worst_slippage_fraction"), nonnegative=True)
                if c != max(avg, price)*q*mul*(fee+slip):
                    raise ResearchLabRefused("MODELED_COST_POLICY_MISMATCH")
                associated = next((b for b in bars if b["bar_digest"] == x["evidence_digest"]), None)
                expected_exit = {"reason": x["reason"], "quantity": x["quantity"],
                                 "price": x["price"], "gross": x["gross"],
                                 "modeled_cost": x["modeled_cost"], "net": x["net"]}
                receipt = _load_json(associated["receipt_json"])
                if not any(type(e) is dict and all(e.get(k) == v for k, v in expected_exit.items())
                           for e in receipt.get("exits", [])):
                    raise ResearchLabRefused("EXIT_NOT_IN_SOURCE_BAR_RECEIPT")
                bar_exit_usage[x["evidence_digest"]] = bar_exit_usage.get(x["evidence_digest"], 0) + 1
                # Compatible with Stage 9's actual gross-profit equation.
                if g != signed*(price-avg)*q*mul:
                    raise ResearchLabRefused("EXIT_GROSS_INCONSISTENT")
                sum_qty += q
                gross += g
                cost += c
                net += n
                exit_times.append(bar_evidence[x["evidence_digest"]])
            if sum_qty != closed_qty:
                raise ResearchLabRefused("CLOSED_QUANTITY_DISAGREES_WITH_EXITS")
            for bar in bars:
                count = len(_load_json(bar["receipt_json"]).get("exits", []))
                if count != bar_exit_usage.get(bar["bar_digest"], 0):
                    raise ResearchLabRefused("MISSING_OR_EXTRA_BAR_EXITS")
            outcome = "INCOMPLETE"
            if status == "CLOSED" and qty > 0 and closed_qty == qty and exit_times:
                outcome = "CLOSED_PAPER"
            elif status in ("CANCELED", "REJECTED") and qty == 0 and closed_qty == 0 and not exit_times:
                outcome = "UNFILLED"
            elif status == "CLOSED" or (status in ("CANCELED", "REJECTED") and qty > 0):
                raise ResearchLabRefused("INCONSISTENT_TERMINAL_STATE")
            entry_at = _when(row["input_close"])
            segment = _partition(entry_at, boundaries)
            exit_at = max(exit_times) if exit_times else None
            if any(t <= entry_at for t in exit_times):
                raise ResearchLabRefused("NONCAUSAL_EXIT_TIME")
            cross = bool(exit_at is not None and _partition(exit_at, boundaries) != segment)
            risk = qty*abs(entry-stop)*mul
            if outcome == "CLOSED_PAPER" and risk <= 0:
                raise ResearchLabRefused("ZERO_INITIAL_RISK")
            # Stage 9 only knows modeled costs, NOT live fills or genuine sourcing.
            result = {"order_id": row["order_id"], "segment": segment, "outcome": outcome,
                      "entry_at": entry_at.isoformat(), "exit_at": exit_at.isoformat() if exit_at else None,
                      "cross_split": cross, "setup_id":row["setup_id"],
                      "market":instrument["market"], "provider":instrument["provider"],
                      "symbol":instrument["symbol"], "timeframe":plan["timeframe"],
                      "gross":gross, "cost":cost, "net":net, "initial_risk":risk,
                      "net_r": net/risk if outcome == "CLOSED_PAPER" else None}
            records.append(result)
            evidence.append({"order_id":row["order_id"], "plan":plan,
                             "snapshot":snap, "exits":[dict(x) for x in exit_rows],
                             "bars":[dict(b) for b in bars]})
        equity = _decimal(protocol["initial_equity"], positive=True)
        groups = {name: _metrics([r for r in records if r["segment"] == name], equity)
                  for name in ("training", "validation", "holdout")}
        overall = _metrics(records, equity)
        setup_ids = sorted({r["setup_id"] for r in records})
        if len(setup_ids) > 32:
            raise ResearchLabRefused("TOO_MANY_RESEARCH_SETUPS")
        by_setup = {setup: _metrics([r for r in records if r["setup_id"] == setup], equity)
                    for setup in setup_ids}
        minimum = protocol["min_closed_per_segment"]
        blockers = []
        if any(g["closed"] < minimum for g in groups.values()):
            blockers.append("INSUFFICIENT_SEGMENT_SAMPLE")
        if overall["open_or_incomplete"]:
            blockers.append("INCOMPLETE_PAPER_OUTCOMES")
        if overall["cross_split_closes"]:
            blockers.append("CROSS_PARTITION_EXIT_LEAKAGE")
        if not ids:
            blockers.append("NO_OBSERVED_ORDERS")
        if missing_plan_rows:
            blockers.append("UNLINKED_STAGE8_ORDERS_WINDOW_UNKNOWN")
        # This is descriptive even when no blockers: provider authenticity,
        # prospective freeze and independent out-of-sample untouchedness UNKNOWN.
        serialized = {"study_id":protocol["study_id"], "mode":"OFFLINE_PAPER_RESEARCH_ONLY",
                      "protocol_sha256":hashlib.sha256(protocol_bytes).hexdigest(),
                      "declared_dataset_sha256":protocol["declared_dataset_sha256"],
                      "dataset_origin":protocol["dataset_origin"],
                      "evidence_sha256":_digest(evidence),
                      "expected_order_count":len(ids),
                      "unlinked_stage8_order_count":len(missing_plan_rows),
                      "metrics":{"training":groups["training"], "validation":groups["validation"],
                                 "holdout":groups["holdout"], "overall":overall,
                                 "by_setup":by_setup},
                      "blockers":blockers,
                      "readiness":"DESCRIPTIVE_ONLY_NOT_PROFITABILITY_PROOF",
                      "independent_provider_data_verified":False,
                      "prospective_holdout_verified":False,
                      "telegram_sent":False,"broker_order_sent":False}
        if wf_settings is not None:
            try:
                serialized["walk_forward"] = evaluate_walk_forward(
                    records,
                    window_start=start, training_end=train_end,
                    validation_end=validation_end, window_end=end,
                    settings=wf_settings, min_closed_per_segment=minimum,
                )
            except WalkForwardRefused as exc:
                raise ResearchLabRefused("INVALID_WALK_FORWARD_EVIDENCE") from exc
        serialized["report_sha256"] = _digest(serialized)
        return serialized
    except ResearchLabRefused:
        raise
    except (sqlite3.Error, OSError, TypeError, KeyError, OverflowError) as exc:
        raise ResearchLabRefused("RESEARCH_EVIDENCE_READ_REFUSED") from exc
    finally:
        if "conn" in locals():
            conn.close()


__all__ = ["ResearchLabRefused", "parse_protocol", "evaluate_stage9_research"]
