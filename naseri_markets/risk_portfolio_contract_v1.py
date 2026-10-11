"""Risk & Portfolio Manager V1 policy contracts (offline, PAPER-only).

Values are operator-supplied research snapshots, NOT authenticated balances.
A trusted account adapter and atomic live risk service are later phases.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .execution_contract_v1 import identity, nonnegative, positive


def _fraction(value: Decimal, name: str) -> None:
    positive(value, name)
    if value > 1:
        raise ValueError(f"{name} must be <= 1")


def _count(value: int, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 10000:
        raise ValueError(f"{name} must be an integer in 1..10000")


@dataclass(frozen=True, slots=True)
class PortfolioRiskPolicy:
    portfolio_id: str
    currency: str
    max_reserved_risk: Decimal
    max_notional: Decimal
    max_daily_loss: Decimal
    max_group_risk: Decimal
    max_engine_risk: Decimal
    max_active_orders: int

    def __post_init__(self) -> None:
        identity(self.portfolio_id, "portfolio_id")
        identity(self.currency, "currency")
        for name in (
            "max_reserved_risk", "max_notional", "max_daily_loss",
            "max_group_risk", "max_engine_risk",
        ):
            positive(getattr(self, name), name)
        _count(self.max_active_orders, "max_active_orders")


@dataclass(frozen=True, slots=True)
class AccountRiskPolicy:
    account_id: str
    portfolio_id: str
    currency: str
    equity: Decimal
    max_order_risk_fraction: Decimal
    max_total_risk_fraction: Decimal
    max_daily_loss_fraction: Decimal
    max_notional_fraction: Decimal
    max_margin_fraction: Decimal
    max_leverage: Decimal
    contract_multiplier: Decimal
    quantity_step: Decimal
    roundtrip_fee_fraction: Decimal
    worst_slippage_fraction: Decimal
    max_active_orders: int
    # Explicit red flag for *any* exposure not represented by this local ledger.
    # Stage V1 has NO account reconciliation and must refuse unknown exposure.
    external_exposure_cleared: bool = False

    def __post_init__(self) -> None:
        for name in ("account_id", "portfolio_id", "currency"):
            identity(getattr(self, name), name)
        for name in (
            "equity", "max_leverage", "contract_multiplier", "quantity_step",
        ):
            positive(getattr(self, name), name)
        for name in (
            "max_order_risk_fraction", "max_total_risk_fraction",
            "max_daily_loss_fraction", "max_margin_fraction",
        ):
            _fraction(getattr(self, name), name)
        positive(self.max_notional_fraction, "max_notional_fraction")
        if self.max_notional_fraction > self.max_leverage:
            raise ValueError("max_notional_fraction exceeds leverage limit")
        for name in ("roundtrip_fee_fraction", "worst_slippage_fraction"):
            nonnegative(getattr(self, name), name)
            if getattr(self, name) >= 1:
                raise ValueError(f"{name} must be < 1")
        if not isinstance(self.external_exposure_cleared, bool):
            raise ValueError("external_exposure_cleared must be an explicit boolean")
        _count(self.max_active_orders, "max_active_orders")
