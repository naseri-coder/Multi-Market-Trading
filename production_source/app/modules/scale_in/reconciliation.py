"""Connector-agnostic restart/reconciliation contracts.

The current project has no exchange order connector.  This module therefore
compares durable local truth with an externally supplied execution snapshot and
fails closed; it never sends an order.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from .entities import ReconciliationResult, ReconciliationStatus


@dataclass(frozen=True, slots=True)
class ExchangeExecutionTruth:
    open_qty: Decimal
    fill_keys: tuple[str, ...]
    order_state: str | None = None
    unknown_fill_keys: tuple[str, ...] = ()


class ExecutionTruthProvider(Protocol):
    async def fetch_truth(self, *, position_id: int | str) -> ExchangeExecutionTruth: ...


def reconcile(*, local_open_qty: Decimal, local_fill_keys: tuple[str, ...],
              exchange: ExchangeExecutionTruth) -> ReconciliationResult:
    local = set(local_fill_keys)
    remote = set(exchange.fill_keys)
    missing = tuple(sorted(remote - local))
    local_only = tuple(sorted(local - remote))
    if exchange.unknown_fill_keys:
        status = ReconciliationStatus.UNKNOWN_EXECUTION
    elif missing:
        status = ReconciliationStatus.EXCHANGE_AHEAD
    elif local_only:
        status = ReconciliationStatus.DB_AHEAD
    elif local_open_qty != exchange.open_qty:
        status = ReconciliationStatus.QUANTITY_MISMATCH
    elif exchange.order_state == "CANCELLED_WITH_LOCAL_PENDING":
        status = ReconciliationStatus.CANCEL_MISMATCH
    else:
        status = ReconciliationStatus.IN_SYNC
    return ReconciliationResult(
        status=status, missing_exchange_fill_keys=missing,
        local_only_fill_keys=local_only, local_open_qty=local_open_qty,
        exchange_open_qty=exchange.open_qty,
        details={"order_state": exchange.order_state, "unknown_fill_keys": exchange.unknown_fill_keys},
    )
