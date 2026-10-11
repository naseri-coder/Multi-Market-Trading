"""Risk & Portfolio Manager V1: durable PAPER-only cross-engine risk reservations.

No venue connectivity, real balance fetch, authenticated user, live order,
Telegram or trading runtime integration. All orders and balances are fixtures.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Mapping

from .contracts import EvidenceMode, Instrument
from .execution_contract_v1 import OrderSpec, identity, positive
from .risk_portfolio_contract_v1 import AccountRiskPolicy, PortfolioRiskPolicy


class RiskRefused(ValueError):
    """Fail-closed, machine-readable rejection."""


def _wire(data: Mapping[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(data: Mapping[str, Any]) -> str:
    return hashlib.sha256(_wire(data).encode("utf-8")).hexdigest()


def _policy(policy: AccountRiskPolicy | PortfolioRiskPolicy) -> dict[str, Any]:
    return {k: str(v) if isinstance(v, Decimal) else v for k, v in asdict(policy).items()}


def _order(spec: OrderSpec) -> dict[str, Any]:
    data = asdict(spec)
    data["direction"] = spec.direction.value
    data["kind"] = spec.kind.value
    data["mode"] = spec.mode.value
    data["instrument"]["market"] = spec.instrument.market.value
    for name in ("quantity", "reference_entry", "stop", "target"):
        data[name] = str(getattr(spec, name))
    return data


def _amount(value: Any, label: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, Decimal)):
        raise RiskRefused(f"INVALID_{label.upper()}")
    try:
        number = Decimal(value)
        positive(number, label)
    except (ValueError, ArithmeticError) as exc:
        raise RiskRefused(f"INVALID_{label.upper()}") from exc
    return number


def _total(rows: list[sqlite3.Row], field: str) -> Decimal:
    return sum((Decimal(row[field]) for row in rows), Decimal("0"))


class PaperRiskPortfolioManager:
    """SQLite writer serializes all budgets through BEGIN IMMEDIATE.

    Separate risk DB intentionally never authorizes stage-1 orders. Release is
    possible only from supplied terminal PAPER lifecycle evidence. No external
    balances, profits, engine grants or geographic trading permissions exist.
    """

    def __init__(self, path: str | Path, *, clock: Callable[[], date] | None = None):
        p = Path(path)
        if p.is_symlink() or (p.exists() and not p.is_file()):
            raise RiskRefused("NONREGULAR_RISK_DB_PATH")
        p.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(p), timeout=5, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA busy_timeout=5000")
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute("PRAGMA foreign_keys=ON")
        self._clock = clock or (lambda: datetime.now(timezone.utc).date())
        self._db.executescript(
            "CREATE TABLE IF NOT EXISTS risk_portfolios ("
            "portfolio_id TEXT PRIMARY KEY, policy TEXT NOT NULL, "
            "last_day TEXT, halted INTEGER NOT NULL DEFAULT 0);"
            "CREATE TABLE IF NOT EXISTS risk_accounts ("
            "account_id TEXT PRIMARY KEY, portfolio_id TEXT NOT NULL "
            "REFERENCES risk_portfolios(portfolio_id), "
            "policy TEXT NOT NULL, halted INTEGER NOT NULL DEFAULT 0);"
            "CREATE TABLE IF NOT EXISTS risk_instruments ("
            "portfolio_id TEXT NOT NULL REFERENCES risk_portfolios(portfolio_id), "
            "market TEXT NOT NULL, provider TEXT NOT NULL, symbol TEXT NOT NULL, "
            "currency TEXT NOT NULL, group_id TEXT NOT NULL, "
            "PRIMARY KEY(portfolio_id,market,provider,symbol));"
            "CREATE TABLE IF NOT EXISTS risk_engine_halts ("
            "portfolio_id TEXT NOT NULL REFERENCES risk_portfolios(portfolio_id), "
            "engine_id TEXT NOT NULL, PRIMARY KEY(portfolio_id,engine_id));"
            "CREATE TABLE IF NOT EXISTS paper_risk_reservations ("
            "order_id TEXT PRIMARY KEY, portfolio_id TEXT NOT NULL, "
            "account_id TEXT NOT NULL, engine_id TEXT NOT NULL, "
            "group_id TEXT NOT NULL, contract_json TEXT NOT NULL, "
            "risk TEXT NOT NULL, notional TEXT NOT NULL, margin TEXT NOT NULL, "
            "status TEXT NOT NULL CHECK(status IN ('ACTIVE','RELEASED')));"
            "CREATE TABLE IF NOT EXISTS paper_risk_losses ("
            "account_id TEXT NOT NULL REFERENCES risk_accounts(account_id), "
            "day TEXT NOT NULL, amount TEXT NOT NULL, "
            "PRIMARY KEY(account_id,day));"
            "CREATE TABLE IF NOT EXISTS paper_risk_actions ("
            "action_id TEXT PRIMARY KEY, digest TEXT NOT NULL, receipt TEXT NOT NULL);"
            "CREATE TABLE IF NOT EXISTS paper_risk_audit ("
            "seq INTEGER PRIMARY KEY AUTOINCREMENT, day TEXT NOT NULL, "
            "event TEXT NOT NULL, subject TEXT NOT NULL, detail TEXT NOT NULL);"
        )

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> PaperRiskPortfolioManager:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _begin(self) -> None:
        self._db.execute("BEGIN IMMEDIATE")

    def _commit(self) -> None:
        self._db.execute("COMMIT")

    def _rollback(self) -> None:
        self._db.execute("ROLLBACK")

    def _today(self) -> str:
        day = self._clock()
        if type(day) is not date:
            raise RiskRefused("UTC_DATE_CLOCK_REQUIRED")
        return day.isoformat()

    def _portfolio(self, portfolio_id: str) -> sqlite3.Row:
        row = self._db.execute(
            "SELECT * FROM risk_portfolios WHERE portfolio_id=?", (portfolio_id,)
        ).fetchone()
        if row is None:
            raise RiskRefused("UNKNOWN_PORTFOLIO")
        return row

    def _account(self, account_id: str) -> sqlite3.Row:
        row = self._db.execute(
            "SELECT * FROM risk_accounts WHERE account_id=?", (account_id,)
        ).fetchone()
        if row is None:
            raise RiskRefused("UNKNOWN_ACCOUNT")
        return row

    def _touch(self, portfolio_id: str) -> str:
        today = self._today()
        row = self._portfolio(portfolio_id)
        if row["last_day"] is not None and today < row["last_day"]:
            raise RiskRefused("CLOCK_ROLLBACK_REFUSED")
        if row["last_day"] != today:
            self._db.execute(
                "UPDATE risk_portfolios SET last_day=? WHERE portfolio_id=?",
                (today, portfolio_id),
            )
        return today

    def _audit(self, day: str, event: str, subject: str, detail: dict[str, Any]) -> None:
        self._db.execute(
            "INSERT INTO paper_risk_audit(day,event,subject,detail) VALUES (?,?,?,?)",
            (day, event, subject, _wire(detail)),
        )

    def audit(self) -> list[dict[str, Any]]:
        return [
            {"seq": row["seq"], "day": row["day"], "event": row["event"],
             "subject": row["subject"], "detail": json.loads(row["detail"])}
            for row in self._db.execute("SELECT * FROM paper_risk_audit ORDER BY seq")
        ]

    def configure_portfolio(self, policy: PortfolioRiskPolicy) -> None:
        if not isinstance(policy, PortfolioRiskPolicy):
            raise RiskRefused("PORTFOLIO_POLICY_REQUIRED")
        wire = _wire(_policy(policy))
        self._begin()
        try:
            old = self._db.execute(
                "SELECT policy FROM risk_portfolios WHERE portfolio_id=?",
                (policy.portfolio_id,),
            ).fetchone()
            if old:
                if old["policy"] != wire:
                    raise RiskRefused("PORTFOLIO_POLICY_IMMUTABLE")
            else:
                today = self._today()
                self._db.execute(
                    "INSERT INTO risk_portfolios(portfolio_id,policy,last_day) "
                    "VALUES (?,?,?)", (policy.portfolio_id, wire, today),
                )
                self._audit(today, "CONFIGURE_PORTFOLIO", policy.portfolio_id, _policy(policy))
            self._commit()
        except BaseException:
            self._rollback()
            raise

    def configure_account(self, policy: AccountRiskPolicy) -> None:
        if not isinstance(policy, AccountRiskPolicy):
            raise RiskRefused("ACCOUNT_POLICY_REQUIRED")
        wire = _wire(_policy(policy))
        self._begin()
        try:
            portfolio = self._portfolio(policy.portfolio_id)
            if json.loads(portfolio["policy"])["currency"] != policy.currency:
                raise RiskRefused("CURRENCY_MISMATCH")
            today = self._touch(policy.portfolio_id)
            old = self._db.execute(
                "SELECT policy FROM risk_accounts WHERE account_id=?", (policy.account_id,)
            ).fetchone()
            if old:
                if old["policy"] != wire:
                    raise RiskRefused("ACCOUNT_POLICY_IMMUTABLE")
            else:
                self._db.execute(
                    "INSERT INTO risk_accounts(account_id,portfolio_id,policy) VALUES (?,?,?)",
                    (policy.account_id, policy.portfolio_id, wire),
                )
                self._audit(today, "CONFIGURE_ACCOUNT", policy.account_id, _policy(policy))
            self._commit()
        except BaseException:
            self._rollback()
            raise

    def register_instrument(
        self, *, portfolio_id: str, instrument: Instrument, group_id: str,
    ) -> None:
        identity(portfolio_id, "portfolio_id")
        identity(group_id, "group_id")
        if not isinstance(instrument, Instrument):
            raise RiskRefused("INSTRUMENT_REQUIRED")
        self._begin()
        try:
            portfolio = self._portfolio(portfolio_id)
            if json.loads(portfolio["policy"])["currency"] != instrument.quote_currency:
                raise RiskRefused("CURRENCY_MISMATCH")
            today = self._touch(portfolio_id)
            key = (portfolio_id, instrument.market.value, instrument.provider, instrument.symbol)
            old = self._db.execute(
                "SELECT currency,group_id FROM risk_instruments "
                "WHERE portfolio_id=? AND market=? AND provider=? AND symbol=?", key,
            ).fetchone()
            if old:
                if (old["currency"], old["group_id"]) != (
                    instrument.quote_currency, group_id
                ):
                    raise RiskRefused("INSTRUMENT_GROUP_IMMUTABLE")
            else:
                self._db.execute(
                    "INSERT INTO risk_instruments VALUES (?,?,?,?,?,?)",
                    (*key, instrument.quote_currency, group_id),
                )
                self._audit(today, "REGISTER_INSTRUMENT", instrument.symbol,
                            {"portfolio_id": portfolio_id, "group_id": group_id,
                             "market": instrument.market.value,
                             "provider": instrument.provider})
            self._commit()
        except BaseException:
            self._rollback()
            raise

    def _replayed(self, action_id: str, digest: str) -> dict[str, Any] | None:
        row = self._db.execute(
            "SELECT digest,receipt FROM paper_risk_actions WHERE action_id=?", (action_id,)
        ).fetchone()
        if row is not None:
            if row["digest"] != digest:
                raise RiskRefused("ACTION_ID_PAYLOAD_CONFLICT")
            return json.loads(row["receipt"])
        return None

    def _action(
        self, action_id: str, digest: str, receipt: dict[str, Any],
    ) -> dict[str, Any]:
        self._db.execute(
            "INSERT INTO paper_risk_actions VALUES (?,?,?)",
            (action_id, digest, _wire(receipt)),
        )
        return receipt

    def _rows(self, portfolio_id: str) -> list[sqlite3.Row]:
        return self._db.execute(
            "SELECT * FROM paper_risk_reservations "
            "WHERE portfolio_id=? AND status='ACTIVE'", (portfolio_id,),
        ).fetchall()

    def _losses(self, portfolio_id: str, day: str) -> tuple[dict[str, Decimal], Decimal]:
        rows = self._db.execute(
            "SELECT a.account_id, l.amount FROM risk_accounts a "
            "JOIN paper_risk_losses l ON l.account_id=a.account_id "
            "WHERE a.portfolio_id=? AND l.day=?", (portfolio_id, day),
        ).fetchall()
        by_account = {row["account_id"]: Decimal(row["amount"]) for row in rows}
        return by_account, sum(by_account.values(), Decimal(0))

    def reserve(self, spec: OrderSpec, *, action_id: str) -> dict[str, Any]:
        """All cross-engine/portfolio caps are evaluated inside one write lock.

        Never submits any order. The result is a local PAPER risk reservation,
        not an authorization token for brokers, exchanges or MT5.
        """
        if not isinstance(spec, OrderSpec) or spec.mode is not EvidenceMode.PAPER:
            raise RiskRefused("PAPER_ORDER_ONLY")
        identity(action_id, "action_id")
        contract = _order(spec)
        digest = _digest({"type": "RESERVE", "contract": contract})
        self._begin()
        try:
            previous = self._replayed(action_id, digest)
            if previous is not None:
                self._commit()
                return previous
            if self._db.execute(
                "SELECT 1 FROM paper_risk_reservations WHERE order_id=?", (spec.order_id,)
            ).fetchone():
                raise RiskRefused("ORDER_ID_ALREADY_RESERVED")
            account = self._account(spec.account_id)
            ap = json.loads(account["policy"])
            portfolio_id = account["portfolio_id"]
            pp_row = self._portfolio(portfolio_id)
            pp = json.loads(pp_row["policy"])
            day = self._touch(portfolio_id)
            if account["halted"] or pp_row["halted"] or self._db.execute(
                "SELECT 1 FROM risk_engine_halts WHERE portfolio_id=? AND engine_id=?",
                (portfolio_id, spec.engine_id),
            ).fetchone():
                raise RiskRefused("NEW_RISK_HALTED")
            if ap["external_exposure_cleared"] is not True:
                raise RiskRefused("EXTERNAL_EXPOSURE_UNVERIFIED")
            if spec.instrument.quote_currency != ap["currency"]:
                raise RiskRefused("CURRENCY_MISMATCH")
            mapped = self._db.execute(
                "SELECT currency,group_id FROM risk_instruments WHERE "
                "portfolio_id=? AND market=? AND provider=? AND symbol=?",
                (portfolio_id, spec.instrument.market.value, spec.instrument.provider,
                 spec.instrument.symbol),
            ).fetchone()
            if mapped is None or mapped["currency"] != spec.instrument.quote_currency:
                raise RiskRefused("INSTRUMENT_UNMAPPED")
            group_id = mapped["group_id"]
            step = Decimal(ap["quantity_step"])
            if (spec.quantity / step) != (spec.quantity / step).to_integral_value():
                raise RiskRefused("QUANTITY_STEP_VIOLATION")
            price = spec.reference_entry
            multiplier = Decimal(ap["contract_multiplier"])
            notional = spec.quantity * price * multiplier
            risk = spec.quantity * multiplier * (
                abs(price - spec.stop)
                + price * (
                    Decimal(ap["roundtrip_fee_fraction"])
                    + Decimal(ap["worst_slippage_fraction"])
                )
            )
            # This is modeled initial margin, not verified broker margin.
            margin = notional / Decimal(ap["max_leverage"])
            active = self._rows(portfolio_id)
            account_active = [r for r in active if r["account_id"] == spec.account_id]
            group_active = [r for r in active if r["group_id"] == group_id]
            engine_active = [r for r in active if r["engine_id"] == spec.engine_id]
            day_loss, portfolio_loss = self._losses(portfolio_id, day)
            account_loss = day_loss.get(spec.account_id, Decimal(0))
            if account_loss >= Decimal(ap["equity"]) * Decimal(
                ap["max_daily_loss_fraction"]
            ) or portfolio_loss >= Decimal(pp["max_daily_loss"]):
                raise RiskRefused("DAILY_LOSS_CIRCUIT_BREAKER")

            def check(value: Decimal, cap: Decimal, code: str) -> None:
                if value > cap:
                    raise RiskRefused(code)

            check(risk, Decimal(ap["equity"]) * Decimal(ap["max_order_risk_fraction"]),
                  "PER_ORDER_RISK_CAP")
            check(_total(account_active, "risk") + risk,
                  Decimal(ap["equity"]) * Decimal(ap["max_total_risk_fraction"]),
                  "ACCOUNT_RESERVED_RISK_CAP")
            check(_total(account_active, "risk") + risk + account_loss,
                  Decimal(ap["equity"]) * Decimal(ap["max_daily_loss_fraction"]),
                  "ACCOUNT_DAILY_WORST_CASE_CAP")
            check(_total(account_active, "notional") + notional,
                  Decimal(ap["equity"]) * Decimal(ap["max_notional_fraction"]),
                  "ACCOUNT_NOTIONAL_CAP")
            check(_total(account_active, "margin") + margin,
                  Decimal(ap["equity"]) * Decimal(ap["max_margin_fraction"]),
                  "ACCOUNT_MODELED_MARGIN_CAP")
            check(_total(active, "risk") + risk, Decimal(pp["max_reserved_risk"]),
                  "PORTFOLIO_RESERVED_RISK_CAP")
            check(_total(active, "risk") + risk + portfolio_loss,
                  Decimal(pp["max_daily_loss"]), "PORTFOLIO_DAILY_WORST_CASE_CAP")
            check(_total(active, "notional") + notional, Decimal(pp["max_notional"]),
                  "PORTFOLIO_NOTIONAL_CAP")
            check(_total(group_active, "risk") + risk, Decimal(pp["max_group_risk"]),
                  "CORRELATION_GROUP_CAP")
            check(_total(engine_active, "risk") + risk, Decimal(pp["max_engine_risk"]),
                  "ENGINE_CONCENTRATION_CAP")
            if len(account_active) >= ap["max_active_orders"]:
                raise RiskRefused("ACCOUNT_ACTIVE_ORDER_CAP")
            if len(active) >= pp["max_active_orders"]:
                raise RiskRefused("PORTFOLIO_ACTIVE_ORDER_CAP")
            receipt = {
                "mode": "PAPER_RISK_RESERVATION_ONLY",
                "order_id": spec.order_id, "account_id": spec.account_id,
                "portfolio_id": portfolio_id, "engine_id": spec.engine_id,
                "group_id": group_id, "day": day,
                "risk": str(risk), "notional": str(notional),
                "modeled_margin": str(margin), "status": "ACTIVE",
            }
            self._db.execute(
                "INSERT INTO paper_risk_reservations "
                "(order_id,portfolio_id,account_id,engine_id,group_id,"
                "contract_json,risk,notional,margin,status) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (spec.order_id, portfolio_id, spec.account_id, spec.engine_id,
                 group_id, _wire(contract), str(risk), str(notional),
                 str(margin), "ACTIVE"),
            )
            self._audit(day, "RESERVE", spec.order_id, receipt)
            result = self._action(action_id, digest, receipt)
            self._commit()
            return result
        except BaseException:
            self._rollback()
            raise

    def release(
        self, order_id: str, *, action_id: str,
        lifecycle_snapshot: Mapping[str, Any], evidence: str,
    ) -> dict[str, Any]:
        """Release only after a terminal snapshot from the Stage-1 PAPER simulator.

        This verifies structure and full spec identity; V1 cannot authenticate
        a caller's evidence nor atomically read a separate broker database.
        """
        identity(order_id, "order_id")
        identity(action_id, "action_id")
        if not isinstance(evidence, str) or len(evidence.strip()) < 8:
            raise RiskRefused("TERMINAL_EVIDENCE_REQUIRED")
        if not isinstance(lifecycle_snapshot, Mapping):
            raise RiskRefused("TERMINAL_SNAPSHOT_REQUIRED")
        snapshot = dict(lifecycle_snapshot)
        digest = _digest({
            "type": "RELEASE", "order_id": order_id,
            "snapshot": snapshot, "evidence": evidence,
        })
        self._begin()
        try:
            previous = self._replayed(action_id, digest)
            if previous is not None:
                self._commit()
                return previous
            row = self._db.execute(
                "SELECT * FROM paper_risk_reservations WHERE order_id=?", (order_id,)
            ).fetchone()
            if row is None or row["status"] != "ACTIVE":
                raise RiskRefused("NO_ACTIVE_RESERVATION")
            if snapshot.get("order_id") != order_id or snapshot.get("spec") != json.loads(
                row["contract_json"]
            ):
                raise RiskRefused("TERMINAL_IDENTITY_MISMATCH")
            try:
                filled = _amount(snapshot.get("filled_quantity"), "filled_quantity") if (
                    snapshot.get("filled_quantity") != "0"
                ) else Decimal(0)
                closed = _amount(snapshot.get("closed_quantity"), "closed_quantity") if (
                    snapshot.get("closed_quantity") != "0"
                ) else Decimal(0)
                open_qty = Decimal(snapshot["open_position_quantity"])
            except (KeyError, ValueError, ArithmeticError) as exc:
                raise RiskRefused("INVALID_TERMINAL_QUANTITIES") from exc
            if not open_qty.is_finite() or (
                filled < 0 or closed < 0 or closed > filled or filled - closed != open_qty
            ) or filled > Decimal(json.loads(row["contract_json"])["quantity"]):
                raise RiskRefused("INVALID_TERMINAL_QUANTITIES")
            status = snapshot.get("status")
            if not (
                (status in {"CANCELED", "REJECTED"} and filled == 0 and closed == 0)
                or (status == "CLOSED" and filled > 0 and filled == closed)
            ):
                raise RiskRefused("RESERVATION_STILL_AT_RISK")
            day = self._touch(row["portfolio_id"])
            self._db.execute(
                "UPDATE paper_risk_reservations SET status='RELEASED' WHERE order_id=?",
                (order_id,),
            )
            receipt = {"mode": "PAPER_RISK_RESERVATION_ONLY", "order_id": order_id,
                       "status": "RELEASED", "day": day,
                       "terminal_status": status, "evidence": evidence}
            self._audit(day, "RELEASE", order_id, receipt)
            result = self._action(action_id, digest, receipt)
            self._commit()
            return result
        except BaseException:
            self._rollback()
            raise

    def record_loss(
        self, account_id: str, *, action_id: str, amount: Decimal,
    ) -> dict[str, Any]:
        """Cumulative positive PAPER losses; no netting a profit to erase a trip."""
        identity(account_id, "account_id")
        identity(action_id, "action_id")
        positive(amount, "loss")
        digest = _digest({"type": "LOSS", "account_id": account_id, "amount": str(amount)})
        self._begin()
        try:
            old = self._replayed(action_id, digest)
            if old is not None:
                self._commit()
                return old
            account = self._account(account_id)
            day = self._touch(account["portfolio_id"])
            row = self._db.execute(
                "SELECT amount FROM paper_risk_losses WHERE account_id=? AND day=?",
                (account_id, day),
            ).fetchone()
            total = (Decimal(row["amount"]) if row else Decimal(0)) + amount
            self._db.execute(
                "INSERT INTO paper_risk_losses(account_id,day,amount) VALUES (?,?,?) "
                "ON CONFLICT(account_id,day) DO UPDATE SET amount=excluded.amount",
                (account_id, day, str(total)),
            )
            receipt = {"account_id": account_id, "day": day,
                       "recorded_loss": str(amount), "daily_loss": str(total),
                       "mode": "PAPER_LOSS_ONLY"}
            self._audit(day, "RECORD_LOSS", account_id, receipt)
            result = self._action(action_id, digest, receipt)
            self._commit()
            return result
        except BaseException:
            self._rollback()
            raise

    def halt(
        self, *, portfolio_id: str, scope: str, subject_id: str, action_id: str,
    ) -> dict[str, Any]:
        """One-way new-risk kill switch. Unhalt is deliberately NOT available."""
        identity(portfolio_id, "portfolio_id")
        identity(subject_id, "subject_id")
        identity(action_id, "action_id")
        if scope not in {"portfolio", "account", "engine"}:
            raise RiskRefused("UNKNOWN_HALT_SCOPE")
        if scope == "portfolio" and subject_id != portfolio_id:
            raise RiskRefused("PORTFOLIO_HALT_ID_MISMATCH")
        digest = _digest({"type": "HALT", "portfolio_id": portfolio_id,
                          "scope": scope, "subject_id": subject_id})
        self._begin()
        try:
            old = self._replayed(action_id, digest)
            if old is not None:
                self._commit()
                return old
            self._portfolio(portfolio_id)
            day = self._touch(portfolio_id)
            if scope == "portfolio":
                self._db.execute(
                    "UPDATE risk_portfolios SET halted=1 WHERE portfolio_id=?",
                    (portfolio_id,),
                )
            elif scope == "account":
                row = self._account(subject_id)
                if row["portfolio_id"] != portfolio_id:
                    raise RiskRefused("HALT_ACCOUNT_PORTFOLIO_MISMATCH")
                self._db.execute(
                    "UPDATE risk_accounts SET halted=1 WHERE account_id=?", (subject_id,)
                )
            else:
                self._db.execute(
                    "INSERT OR IGNORE INTO risk_engine_halts VALUES (?,?)",
                    (portfolio_id, subject_id),
                )
            receipt = {"portfolio_id": portfolio_id, "scope": scope,
                       "subject_id": subject_id, "halt_new_risk": True, "day": day}
            self._audit(day, "HALT", subject_id, receipt)
            result = self._action(action_id, digest, receipt)
            self._commit()
            return result
        except BaseException:
            self._rollback()
            raise

    def snapshot(self, portfolio_id: str) -> dict[str, Any]:
        """Read-only current budgets, never provider account balances."""
        identity(portfolio_id, "portfolio_id")
        portfolio = self._portfolio(portfolio_id)
        active = self._rows(portfolio_id)
        today = self._today()
        by_account, loss = self._losses(portfolio_id, today)
        return {
            "portfolio_id": portfolio_id, "mode": "PAPER_ONLY",
            "halted": bool(portfolio["halted"]), "day": today,
            "active_orders": len(active),
            "reserved_risk": str(_total(active, "risk")),
            "reserved_notional": str(_total(active, "notional")),
            "modeled_margin": str(_total(active, "margin")),
            "daily_realized_loss_magnitude": str(loss),
            "account_losses": {key: str(v) for key, v in sorted(by_account.items())},
        }
