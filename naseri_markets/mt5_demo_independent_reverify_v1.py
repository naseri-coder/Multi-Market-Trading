"""Stage 8: independent MT5 DEMO requery and position-lifespan diagnostics.

Independence here means fresh *read-only calls* that do not trust the
persisted Stage-7 payload. All calls still depend on the SAME MT5 terminal
and broker API: no cryptographic provider attestation or all-time guarantee.
There is deliberately no database write, broker order, risk or unlock API.
"""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from .mt5_demo_evidence_custody_v1 import (
    DemoHistoryEvidenceCustodyV1,
    EvidenceCustodyRefused,
    _margin_mode,
)
from .mt5_demo_history_readonly_v1 import (
    MT5DemoHistoryReaderV1,
    MT5HistoricalDeal,
    MT5HistoricalOrder,
)
from .mt5_demo_position_accounting_v1 import diagnose_position_history
from .mt5_demo_readonly_adapter_v1 import (
    DemoAccountExpectation,
    MT5DemoReadOnlyAdapterV1,
    _amount,
    _field,
    _name,
    _ticket,
)


class MT5ReverificationRefused(ValueError):
    """A mismatch or incomplete MT5 read cannot become trusted evidence."""


def _checked_rows(raw: Any, kind: str) -> tuple[Any, ...]:
    if not isinstance(raw, (tuple, list)):
        raise MT5ReverificationRefused("TARGETED_HISTORY_QUERY_INCOMPLETE")
    factory = MT5HistoricalDeal.parse if kind == "DEAL" else MT5HistoricalOrder.parse
    data = tuple(factory(x) for x in raw)
    ids = [x.ticket for x in data]
    if len(set(ids)) != len(ids):
        raise MT5ReverificationRefused("DUPLICATE_TARGETED_TICKETS")
    return data


def _positions(provider: Any, guard: MT5DemoReadOnlyAdapterV1) -> dict[int, dict]:
    """Read all open MT5 positions, keyed by stable POSITION_IDENTIFIER."""
    guard._guard()
    try:
        raw = provider.positions_get()
    except Exception as exc:
        raise MT5ReverificationRefused("MT5_ACTIVE_POSITIONS_QUERY_FAILED") from exc
    guard._guard()
    if not isinstance(raw, (tuple, list)):
        raise MT5ReverificationRefused("MT5_ACTIVE_POSITIONS_INCOMPLETE")
    seen_tickets: set[int] = set()
    positions: dict[int, dict] = {}
    for item in raw:
        identifier = _ticket(item, "identifier")
        ticket = _ticket(item, "ticket")
        direction = _field(item, "type")
        if type(direction) is not int or direction not in (0, 1):
            raise MT5ReverificationRefused("ACTIVE_POSITION_SIDE_INVALID")
        if ticket in seen_tickets or identifier in positions:
            raise MT5ReverificationRefused("DUPLICATE_ACTIVE_POSITION_ID")
        seen_tickets.add(ticket)
        positions[identifier] = {
            "identifier": identifier,
            "ticket": ticket,
            "symbol": _name(item, "symbol"),
            "type": direction,
            "volume": _amount(item, "volume"),
        }
    return positions


def _position_details(
    provider: Any, guard: MT5DemoReadOnlyAdapterV1,
    position_id: int, *, window: Any, account_mode: str,
    active_positions: dict[int, dict],
) -> dict:
    """Targeted independent query for a single MT5 POSITION_IDENTIFIER."""
    guard._guard()
    try:
        orders_raw = provider.history_orders_get(position=position_id)
        deals_raw = provider.history_deals_get(position=position_id)
    except Exception as exc:
        raise MT5ReverificationRefused("TARGETED_POSITION_QUERY_FAILED") from exc
    guard._guard()
    orders = _checked_rows(orders_raw, "ORDER")
    deals = _checked_rows(deals_raw, "DEAL")
    if not deals:
        raise MT5ReverificationRefused("TARGETED_POSITION_DEALS_MISSING")
    if any(x.position_id != position_id for x in deals + orders):
        raise MT5ReverificationRefused("TARGETED_POSITION_IDENTITY_LEAK")
    interval_start = int(window.start_utc.timestamp() * 1000)
    interval_end = int(window.end_utc.timestamp() * 1000)
    interval_orders = {
        x.ticket: x.wire() for x in orders
        if interval_start <= x.time_done_msc <= interval_end
    }
    interval_deals = {
        x.ticket: x.wire() for x in deals
        if interval_start <= x.time_msc <= interval_end
    }
    original_orders = {
        x.ticket: x.wire() for x in window.orders if x.position_id == position_id
    }
    original_deals = {
        x.ticket: x.wire() for x in window.deals if x.position_id == position_id
    }
    # Fresh queried position should contain the exact window events, too.
    if interval_orders != original_orders or interval_deals != original_deals:
        raise MT5ReverificationRefused("TARGETED_VS_WINDOW_HISTORY_CONFLICT")
    issues: list[str] = []
    trade_deals = tuple(x for x in deals if x.type_code in (0, 1))
    known_orders = {x.ticket for x in orders}
    for deal in trade_deals:
        if deal.order_ticket not in known_orders:
            issues.append("POSITION_DEAL_ORDER_NOT_IN_TARGETED_HISTORY")
        if deal.entry_code == 3:
            issues.append("CLOSE_BY_COUNTERPART_NOT_VERIFIED")
    accounting = diagnose_position_history(trade_deals, margin_mode=account_mode)
    issues.extend(entry["code"] for entry in accounting["issues"])
    active = active_positions.get(position_id)
    signed = Decimal("0")
    if accounting["positions"]:
        signed = Decimal(accounting["positions"][0]["signed_lots_window_only"])
    if active is None:
        if signed != 0:
            issues.append("RECORDED_POSITION_NOT_CURRENTLY_ACTIVE")
    else:
        expected_sign = 0 if signed > 0 else 1
        if (
            signed == 0
            or expected_sign != active["type"]
            or abs(signed) != active["volume"]
            or not accounting["positions"]
            or accounting["positions"][0]["symbol"] != active["symbol"]
        ):
            issues.append("ACTIVE_POSITION_MISMATCH")
    return {
        "position_id": position_id,
        "targeted_orders": len(orders),
        "targeted_deals": len(deals),
        "earlier_history_observed": any(
            x.time_msc < interval_start for x in deals
        ),
        "later_history_observed": any(
            x.time_msc > interval_end for x in deals
        ),
        "active_ticket": active["ticket"] if active is not None else None,
        "active_identifier_confirmed": active is not None,
        "accounting": accounting,
        "issues": sorted(set(issues)),
        # Even empty issues means no complete provider-side proof.
        "entire_position_lifespan_proven": False,
    }


class MT5DemoIndependentReverifierV1:
    """Read-only requery against a verified Stage-7 custody database.

    This class does not open any MT5 session. The provider must be an
    *already initialized* DEMO MT5 terminal connection.
    """

    def __init__(
        self, provider: Any, expected: DemoAccountExpectation,
        *, custody_path: str | Path, max_positions: int = 20,
    ):
        if not isinstance(expected, DemoAccountExpectation):
            raise TypeError("EXPECTED_DEMO_ACCOUNT_REQUIRED")
        if type(max_positions) is not int or not 1 <= max_positions <= 100:
            raise ValueError("INVALID_TARGETED_POSITION_LIMIT")
        self._provider = provider
        self._expected = expected
        self._path = Path(custody_path)
        self._limit = max_positions

    def verify(
        self, start: datetime, end: datetime,
        *, observed_at: datetime | None = None,
    ) -> dict[str, Any]:
        guard = MT5DemoReadOnlyAdapterV1(self._provider, self._expected)
        mode_before = _margin_mode(self._provider, guard)
        # The custody is opened with true SQLite mode=ro; a verification
        # cannot enroll accounts or update receipts, counters or tickets.
        with DemoHistoryEvidenceCustodyV1(self._path, read_only=True) as custody:
            local = custody.verify(self._expected.account_id)
            if (
                local["account_mode"] != mode_before
                or custody._account(self._expected.account_id)["login"] != self._expected.login
                or custody._account(self._expected.account_id)["server"] != self._expected.server
            ):
                raise MT5ReverificationRefused("CUSTODY_DEMO_ACCOUNT_MODE_DRIFT")
            receipt = custody.verified_window(self._expected.account_id, start, end)
            fresh = MT5DemoHistoryReaderV1(self._provider, self._expected).capture(
                start, end, captured_at=observed_at or datetime.now(UTC),
            )
            mode_after = _margin_mode(self._provider, guard)
            if mode_before != mode_after:
                raise MT5ReverificationRefused("ACCOUNT_MODE_SWITCHED_DURING_REQUERY")
            if fresh.digest != receipt["digest"]:
                raise MT5ReverificationRefused("INDEPENDENT_HISTORY_CONTENT_MISMATCH")
            ids = sorted({
                deal.position_id for deal in fresh.deals
                if deal.type_code in (0, 1)
            })
            if len(ids) > self._limit:
                raise MT5ReverificationRefused("TARGETED_POSITION_LIMIT_EXCEEDED")
            active = _positions(self._provider, guard)
            if mode_before == "NETTING":
                symbols = [x["symbol"] for x in active.values()]
                if len(set(symbols)) != len(symbols):
                    raise MT5ReverificationRefused("NETTING_MULTIPLE_OPEN_POSITIONS_PER_SYMBOL")
            details = [
                _position_details(
                    self._provider, guard, position_id,
                    window=fresh, account_mode=mode_before,
                    active_positions=active,
                )
                for position_id in ids
            ]
            if _margin_mode(self._provider, guard) != mode_before:
                raise MT5ReverificationRefused("ACCOUNT_MODE_SWITCHED_DURING_REQUERY")
            matched = set(ids)
            unmatched_active = sorted(set(active) - matched)
            mismatches = sum(len(x["issues"]) for x in details)
            # A new exposure omitted from the historical window cannot
            # be silently marked as broker-observed safe.
            return {
                "mode": "MT5_DEMO_INDEPENDENT_REQUERY_DIAGNOSTICS_ONLY",
                "account_id": self._expected.account_id,
                "account_mode": mode_before,
                "login": self._expected.login,
                "server": self._expected.server,
                "start_utc": fresh.start_utc.isoformat(),
                "end_utc": fresh.end_utc.isoformat(),
                "custody_head": local["head"],
                "receipt_digest": receipt["digest"],
                "fresh_window_digest": fresh.digest,
                "content_matches_stored_window": True,
                "targeted_positions_checked": len(details),
                "position_checks": details,
                "unmatched_open_position_identifiers": unmatched_active,
                "needs_review": mismatches > 0 or bool(unmatched_active),
                "same_terminal_requery": True,
                "broker_cryptographically_authenticated": False,
                "all_time_history_proven": False,
                "all_position_lifespans_proven": False,
                "account_snapshot_atomic": False,
                "may_unlock_stage4": False,
                "may_release_paper_risk": False,
                "may_execute_order": False,
            }
