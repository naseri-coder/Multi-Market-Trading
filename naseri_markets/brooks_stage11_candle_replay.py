"""Stage 11 — causal, fully offline Brooks PAPER OHLC lifecycle.

Replay is operator-initiated only; input is an offline fixture, not a feed.
Bar-close decisions never look at future bars. Ambiguous stop/target collisions
take the adverse stop, and favorable movement on the entry bar is not credited.
Stage-3 PAPER events, risk release, and Stage-11 P&L journal commit atomically.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .brooks_stage10_paper_bridge import (
    STAGE10_FILENAME, _evidence,
)
from .brooks_replay import SECONDS, _unique
from .engine_control_store import EngineControlStore
from .execution_position_core_v1 import PaperExecutionOrchestratorV1

_MAX_BYTES = 524288
_MAX_BARS = 1024
_NUM = re.compile(r"[0-9]{1,16}(?:\.[0-9]{1,8})?\Z")


class BrooksStage11Refused(ValueError):
    """Untrusted candle, unsafe fill model or conflicting persisted replay."""


def _wire(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=True, sort_keys=True, separators=(",", ":"))


def _sha(obj: Any) -> str:
    return hashlib.sha256(_wire(obj).encode()).hexdigest()


def _instant(value: Any) -> datetime:
    if type(value) is not str or len(value) > 50:
        raise BrooksStage11Refused("CANDLE_UTC_TIME_INVALID")
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise ValueError("naive timestamp")
        return dt.astimezone(UTC)
    except ValueError as exc:
        raise BrooksStage11Refused("CANDLE_UTC_TIME_INVALID") from exc


def _number(value: Any, *, zero: bool = False) -> Decimal:
    if type(value) is not str or not _NUM.fullmatch(value):
        raise BrooksStage11Refused("CANDLE_FIXED_DECIMAL_REQUIRED")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise BrooksStage11Refused("CANDLE_FIXED_DECIMAL_REQUIRED") from exc
    if not result.is_finite() or result < 0 or (not zero and result == 0):
        raise BrooksStage11Refused("CANDLE_PRICE_VOLUME_INVALID")
    return result


def _parse(data: bytes, *, receipt: dict, signal_time: datetime) -> list[dict[str, Any]]:
    if type(data) is not bytes or not 0 < len(data) <= _MAX_BYTES:
        raise BrooksStage11Refused("OFFLINE_REPLAY_SIZE_LIMIT")
    try:
        raw = json.loads(
            data, object_pairs_hook=_unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                BrooksStage11Refused("NONFINITE_JSON")),
        )
    except BrooksStage11Refused:
        raise
    except (UnicodeError, ValueError) as exc:
        raise BrooksStage11Refused("OFFLINE_REPLAY_JSON_INVALID") from exc
    if type(raw) is not dict or set(raw) != {
        "schema_version", "origin", "market", "provider", "symbol",
        "quote_currency", "exchange", "market_type",
        "timezone", "timeframe", "candles",
    } or type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        raise BrooksStage11Refused("OFFLINE_REPLAY_SCHEMA")
    if (
        raw["origin"] != "offline_paper_replay"
        or raw["market"] != "crypto"
        or raw["timezone"] != "UTC"
        or raw["provider"] != receipt["provider"]
        or raw["symbol"] != receipt["symbol"]
        or raw["quote_currency"] != receipt["quote_currency"]
        or raw["exchange"] != receipt["venue"]
        or raw["market_type"] != receipt["market_type"]
        or raw["timeframe"] != receipt["timeframe"]
    ):
        raise BrooksStage11Refused("OFFLINE_REPLAY_INSTRUMENT_TIMEFRAME_DRIFT")
    if raw["timeframe"] not in SECONDS:
        raise BrooksStage11Refused("UNSUPPORTED_REPLAY_TIMEFRAME")
    candles = raw["candles"]
    if type(candles) is not list or not 1 <= len(candles) <= _MAX_BARS:
        raise BrooksStage11Refused("OFFLINE_REPLAY_CANDLE_COUNT")
    step = timedelta(seconds=SECONDS[raw["timeframe"]])
    last_close = signal_time
    clean: list[dict[str, Any]] = []
    for item in candles:
        if type(item) is not dict or set(item) != {
            "open_time", "close_time", "open", "high", "low", "close", "volume",
        }:
            raise BrooksStage11Refused("OFFLINE_REPLAY_BAR_FIELDS")
        opened, closed = _instant(item["open_time"]), _instant(item["close_time"])
        if opened != last_close or closed - opened != step:
            raise BrooksStage11Refused("OFFLINE_REPLAY_GAP_DUPLICATE_OR_LOOKAHEAD")
        prices = {k: _number(item[k], zero=(k == "volume")) for k in
                  ("open", "high", "low", "close", "volume")}
        if not (
            prices["low"] <= prices["open"] <= prices["high"]
            and prices["low"] <= prices["close"] <= prices["high"]
        ):
            raise BrooksStage11Refused("OFFLINE_REPLAY_OHLC_INVALID")
        clean.append({
            "open_time": opened.isoformat(),
            "close_time": closed.isoformat(),
            **{k: str(v) for k, v in prices.items()},
        })
        last_close = closed
    return clean


def _fills(bar: dict, spec: dict, phase: str) -> tuple[str, Decimal | None]:
    """Choose only outcomes justified by this closed OHLC bar.

    No intrabar paths are invented: stops dominate same-bar target ambiguity.
    Entry-bar target is never credited. Opening gap beyond stop after entry
    uses the adverse open, not an optimistic stop-level fill.
    """
    lo, hi = Decimal(bar["low"]), Decimal(bar["high"])
    opened = Decimal(bar["open"])
    entry, stop, target = (
        Decimal(spec[k]) for k in ("reference_entry", "stop", "target")
    )
    long = spec["direction"] == "long"
    if phase == "CREATED":
        filled = lo <= entry if long else hi >= entry
        if not filled:
            return "WAITING_ENTRY", None
        # An opening gap beyond the protective stop means fill sequence and
        # protective viability cannot be resolved conservatively.
        if (long and opened <= stop) or (not long and opened >= stop):
            raise BrooksStage11Refused("ENTRY_OPEN_GAP_BEYOND_STOP_UNRESOLVED")
        if (long and lo <= stop) or (not long and hi >= stop):
            return "ENTRY_AND_STOP_SAME_BAR", stop
        return "ENTRY_ONLY", None
    if phase != "FILLED":
        raise BrooksStage11Refused("UNEXPECTED_PAPER_LIFECYCLE_PHASE")
    stop_hit = lo <= stop if long else hi >= stop
    target_hit = hi >= target if long else lo <= target
    if stop_hit:
        # An adverse open crossing the stop is filled at the worse opening.
        adverse = min(opened, stop) if long else max(opened, stop)
        return ("STOP_WORST_CASE" if target_hit else "STOP"), adverse
    if target_hit:
        return "TARGET", target
    return "HOLD", None


def _report(core: PaperExecutionOrchestratorV1, order_id: str, meta: dict) -> dict:
    order = core.order_state(order_id)
    result = {
        "mode": "BROOKS_STAGE11_OFFLINE_CANDLE_PAPER_ONLY",
        "order_id": order_id,
        "quote_currency": order["spec"]["instrument"]["quote_currency"],
        "status": order["status"],
        "bars_committed": meta["bars_committed"],
        "entry_time_utc": meta["entry_time_utc"],
        "exit_time_utc": meta["exit_time_utc"],
        "exit_reason": meta["exit_reason"],
        "entry_price": meta["entry_price"],
        "exit_price": meta["exit_price"],
        "gross_pnl": meta["gross_pnl"],
        "estimated_fees": meta["estimated_fees"],
        "estimated_slippage": meta["estimated_slippage"],
        "net_realized_pnl": meta["net_realized_pnl"],
        "realized_r": meta["realized_r"],
        "open_position_quantity": order["open_position_quantity"],
        "paper_risk_released": meta["risk_released"],
        "all_execution_is_synthetic": True,
        "broker_orders_authorized": False,
        "telegram_signal_delivery_authorized": False,
        "live_pnl_proven": False,
    }
    return result


class BrooksStage11CandleReplay:
    """Read frozen Brooks signal + Stage-10 order, append verified bars atomically."""

    def __init__(self, state_dir: str | Path):
        self.state_dir = Path(state_dir).absolute()
        self.paper_db = self.state_dir / STAGE10_FILENAME

    def replay(self, *, account_id: str, signal_id: str,
               candles_json: bytes, ack_offline_only: bool = False) -> dict:
        if ack_offline_only is not True:
            raise BrooksStage11Refused("OPERATOR_OFFLINE_REPLAY_OPTIN_REQUIRED")
        if self.paper_db.is_symlink() or not self.paper_db.is_file():
            raise BrooksStage11Refused("STAGE10_PAPER_LEDGER_NOT_CONFIGURED")
        with EngineControlStore(self.state_dir) as source:
            source._db.execute("BEGIN IMMEDIATE")
            try:
                signal, receipt, evidence = _evidence(source, signal_id)
                bars = _parse(
                    candles_json, receipt=receipt, signal_time=signal.observed_at,
                )
                with PaperExecutionOrchestratorV1(self.paper_db) as core:
                    def execute() -> dict:
                        # Stage-10 link must be exactly one and account-locked.
                        row = core._db.execute(
                            "SELECT order_id,content_json,request_digest "
                            "FROM brooks_stage10_links WHERE account_id=? "
                            "AND signal_id=?", (account_id, signal_id),
                        ).fetchone()
                        if row is None:
                            raise BrooksStage11Refused("STAGE10_VERIFIED_LINK_REQUIRED")
                        bound = json.loads(row["content_json"])
                        if (
                            bound.get("signal_digest") != evidence["signal_sha256"]
                            or bound.get("receipt_digest") != evidence["receipt_sha256"]
                            or bound.get("account_id") != account_id
                            or bound.get("signal_id") != signal_id
                            or bound.get("order_id") != row["order_id"]
                            or _sha(bound) != row["request_digest"]
                        ):
                            raise BrooksStage11Refused("STAGE10_LINK_EVIDENCE_DRIFT")
                        order_id = row["order_id"]
                        order = core.order_state(order_id)
                        if order is None or (
                            order["spec"]["account_id"] != account_id
                            or order["spec"]["signal_id"] != signal_id
                            or order["spec"]["engine_id"] != signal.engine_id
                            or order["spec"]["kind"] != "LIMIT"
                            or order["spec"]["mode"] != "paper"
                            or order["spec"]["reference_entry"] != str(signal.entry)
                            or order["spec"]["stop"] != str(signal.stop)
                            or order["spec"]["target"] != str(signal.targets[0])
                            or order["spec"]["direction"] != signal.direction.value
                        ):
                            raise BrooksStage11Refused("STAGE10_ORDER_SPEC_CONFLICT")
                        policy = core._db.execute(
                            "SELECT policy FROM risk_accounts WHERE account_id=?",
                            (account_id,),
                        ).fetchone()
                        if policy is None:
                            raise BrooksStage11Refused("STAGE3_RISK_ACCOUNT_REQUIRED")
                        ap = json.loads(policy["policy"])
                        core._db.execute(
                            "CREATE TABLE IF NOT EXISTS brooks_stage11_bars("
                            "order_id TEXT NOT NULL, seq INTEGER NOT NULL,"
                            "bar_digest TEXT NOT NULL, decision TEXT NOT NULL,"
                            "close_time_utc TEXT NOT NULL,"
                            "PRIMARY KEY(order_id,seq))"
                        )
                        core._db.execute(
                            "CREATE TABLE IF NOT EXISTS brooks_stage11_positions("
                            "order_id TEXT PRIMARY KEY, metadata_json TEXT NOT NULL,"
                            "state_sha256 TEXT NOT NULL)"
                        )
                        existing = core._db.execute(
                            "SELECT metadata_json,state_sha256 FROM brooks_stage11_positions "
                            "WHERE order_id=?", (order_id,),
                        ).fetchone()
                        if existing is None:
                            if order["status"] != "CREATED" or len(core.order_events(order_id)) != 1:
                                raise BrooksStage11Refused("NON_STAGE11_ORDER_ALREADY_MUTATED")
                            meta = {
                                "quote_currency": order["spec"]["instrument"]["quote_currency"],
                                "bars_committed": 0, "entry_time_utc": None,
                                "exit_time_utc": None, "exit_reason": None,
                                "entry_price": None, "exit_price": None,
                                "gross_pnl": "0", "estimated_fees": "0",
                                "estimated_slippage": "0",
                                "net_realized_pnl": "0", "realized_r": None,
                                "risk_released": False,
                            }
                        else:
                            meta = json.loads(existing["metadata_json"])
                            if meta.get("quote_currency") != order["spec"]["instrument"]["quote_currency"]:
                                raise BrooksStage11Refused("STAGE11_QUOTE_CURRENCY_DRIFT")
                            if _sha(order) != existing["state_sha256"]:
                                raise BrooksStage11Refused("STAGE11_ORDER_STATE_DRIFT")
                        seen = int(meta["bars_committed"])
                        if len(bars) < seen:
                            raise BrooksStage11Refused("STAGE11_HISTORY_ROLLBACK")
                        for i in range(seen):
                            prior = core._db.execute(
                                "SELECT bar_digest FROM brooks_stage11_bars "
                                "WHERE order_id=? AND seq=?", (order_id, i+1),
                            ).fetchone()
                            if prior is None or prior["bar_digest"] != _sha(bars[i]):
                                raise BrooksStage11Refused("STAGE11_PREVIOUS_BAR_MUTATED")
                        if meta["exit_time_utc"] is not None and len(bars) > seen:
                            raise BrooksStage11Refused("STAGE11_TERMINAL_FROZEN")
                        for i in range(seen, len(bars)):
                            bar = bars[i]
                            phase = core.order_state(order_id)["status"]
                            if phase not in ("CREATED", "FILLED"):
                                raise BrooksStage11Refused("STAGE11_UNOWNED_ORDER_PHASE")
                            decision, exit_level = _fills(bar, order["spec"], phase)
                            action = "stage11-" + _sha({"order": order_id, "bar": bar})[:35]
                            if decision.startswith("ENTRY"):
                                # Synthetic lifecycle events only, never broker ACK.
                                core.apply(order_id, action_id=action+"-submit", event="SUBMIT")
                                core.apply(
                                    order_id, action_id=action+"-ack", event="ACK",
                                    remote_order_id="offline11-" + order_id[:50],
                                )
                                core.apply(
                                    order_id, action_id=action+"-entry", event="FILL",
                                    quantity=order["spec"]["quantity"],
                                    price=order["spec"]["reference_entry"],
                                )
                                meta["entry_time_utc"] = bar["close_time"]
                                meta["entry_price"] = order["spec"]["reference_entry"]
                            if decision in ("ENTRY_AND_STOP_SAME_BAR", "STOP", "STOP_WORST_CASE", "TARGET"):
                                qty = Decimal(order["spec"]["quantity"])
                                fill = Decimal(order["spec"]["reference_entry"])
                                assert exit_level is not None
                                closure = core.apply(
                                    order_id, action_id=action+"-exit",
                                    event="CLOSE_FILL", quantity=str(qty),
                                    price=str(exit_level),
                                )
                                if closure["risk_released"] is not True:
                                    raise BrooksStage11Refused("STAGE3_RISK_NOT_RELEASED")
                                multiplier = Decimal(ap["contract_multiplier"])
                                fee_rate = Decimal(ap["roundtrip_fee_fraction"])
                                slip_rate = Decimal(ap["worst_slippage_fraction"])
                                size = max(fill, exit_level) * qty * multiplier
                                direction = 1 if order["spec"]["direction"] == "long" else -1
                                gross = Decimal(direction) * (exit_level-fill)*qty*multiplier
                                fees, slip = size*fee_rate, size*slip_rate
                                net = gross-fees-slip
                                risk = abs(fill-Decimal(order["spec"]["stop"])) * qty * multiplier
                                meta.update({
                                    "exit_time_utc": bar["close_time"],
                                    "exit_reason": decision,
                                    "exit_price": str(exit_level),
                                    "gross_pnl": str(gross),
                                    "estimated_fees": str(fees),
                                    "estimated_slippage": str(slip),
                                    "net_realized_pnl": str(net),
                                    "realized_r": str(net/risk),
                                    "risk_released": True,
                                })
                            core._db.execute(
                                "INSERT INTO brooks_stage11_bars VALUES (?,?,?,?,?)",
                                (order_id, i+1, _sha(bar), decision, bar["close_time"]),
                            )
                            meta["bars_committed"] = i+1
                            if meta["exit_time_utc"] is not None and i+1 != len(bars):
                                raise BrooksStage11Refused("STAGE11_POST_EXIT_BARS_NOT_ACCEPTED")
                        snapshot = core.order_state(order_id)
                        core._db.execute(
                            "INSERT INTO brooks_stage11_positions "
                            "(order_id,metadata_json,state_sha256) VALUES(?,?,?) "
                            "ON CONFLICT(order_id) DO UPDATE SET "
                            "metadata_json=excluded.metadata_json,"
                            "state_sha256=excluded.state_sha256",
                            (order_id, _wire(meta), _sha(snapshot)),
                        )
                        return _report(core, order_id, meta)
                    result = core._transaction(execute)
                source._db.execute("COMMIT")
                return result
            except BaseException:
                source._db.execute("ROLLBACK")
                raise


def stage11_panel_summary(state_dir: str | Path) -> dict[str, Any]:
    """Never create a database, SQL schema or order during a panel view."""
    path = Path(state_dir).absolute() / STAGE10_FILENAME
    empty = {"status": "NOT_CONFIGURED", "replayed_orders": 0,
             "closed_paper_trades": 0, "aggregate_net_pnl": "0",
             "net_pnl_by_currency": {}, "broker_execution": False}
    if path.is_symlink() or not path.is_file():
        return empty
    from urllib.parse import quote
    try:
        con = sqlite3.connect(
            "file:" + quote(path.as_posix(), safe="/:") + "?mode=ro",
            uri=True, timeout=2,
        )
        try:
            con.execute("PRAGMA query_only=ON")
            existing = con.execute(
                "SELECT 1 FROM sqlite_master WHERE name='brooks_stage11_positions' "
                "AND type='table'",
            ).fetchone()
            if existing is None:
                return empty
            rows = con.execute(
                "SELECT metadata_json FROM brooks_stage11_positions"
            ).fetchall()
            reports = [json.loads(x[0]) for x in rows]
            per_currency: dict[str, Decimal] = {}
            for item in reports:
                currency = item["quote_currency"]
                if not isinstance(currency, str) or not currency:
                    raise ValueError("NO_QUOTE_CURRENCY")
                per_currency[currency] = (
                    per_currency.get(currency, Decimal(0))
                    + Decimal(item["net_realized_pnl"])
                )
            total = (
                str(next(iter(per_currency.values())))
                if len(per_currency) == 1
                else "0" if not per_currency else "MULTI_CURRENCY_NOT_ADDITIVE"
            )
            return {
                "status": "OFFLINE_PAPER_ONLY",
                "replayed_orders": len(rows),
                "closed_paper_trades": sum(x["risk_released"] is True for x in reports),
                "aggregate_net_pnl": total,
                "net_pnl_by_currency": {key: str(value) for key, value in sorted(per_currency.items())},
                "broker_execution": False,
            }
        finally:
            con.close()
    except (sqlite3.Error, ValueError, KeyError, TypeError):
        return {**empty, "status": "UNAVAILABLE"}
