"""Stage 21D: immutable per-instrument, quote-settled PAPER contract economics.

ONLY linear, USDT-quoted/settled, non-inverse KuCoin-format perpetuals.
Maker rebates, funding, liquidation, impact, mark/last divergence and actual
fills remain unmodeled. Two taker fees and operator-supplied conservative
slippage are explicitly *modeled*, not certified real trading costs.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from decimal import Decimal

from .execution_contract_v1 import identity


class ContractEconomicsRefused(ValueError):
    """Invalid per-instrument PAPER economics; never authorizes live trading."""


def _positive(v: Decimal, name: str, *, zero: bool = False) -> None:
    if (type(v) is not Decimal or not v.is_finite() or v < 0
            or (not zero and v == 0)):
        raise ContractEconomicsRefused("INVALID_" + name)


@dataclass(frozen=True, slots=True)
class PaperContractEconomics:
    provider: str
    symbol: str
    contract_multiplier: Decimal
    quantity_step: Decimal
    price_tick: Decimal
    taker_fee_fraction: Decimal
    maker_fee_fraction: Decimal
    worst_slippage_fraction: Decimal
    metadata_sha256: str
    settle_currency: str = "USDT"
    contract_kind: str = "LINEAR_USDT_PERPETUAL"
    origin: str = "PUBLIC_CONTRACT_SNAPSHOT_UNATTESTED"

    def __post_init__(self) -> None:
        identity(self.provider, "provider")
        identity(self.symbol, "symbol")
        if (self.provider != "kucoin_futures" or not self.symbol.endswith("USDTM")
                or self.settle_currency != "USDT"
                or self.contract_kind != "LINEAR_USDT_PERPETUAL"
                or self.origin not in ("PUBLIC_CONTRACT_SNAPSHOT_UNATTESTED",
                                       "INJECTED_TEST_CONTRACT_FIXTURE")
                or type(self.metadata_sha256) is not str
                or len(self.metadata_sha256) != 64
                or any(c not in "0123456789abcdef" for c in self.metadata_sha256)):
            raise ContractEconomicsRefused("UNSUPPORTED_ECONOMIC_CONTRACT_OR_ORIGIN")
        for field in ("contract_multiplier", "quantity_step", "price_tick",
                      "taker_fee_fraction", "maker_fee_fraction",
                      "worst_slippage_fraction"):
            _positive(getattr(self, field), field,
                      zero=field.endswith("fraction"))
        if (self.quantity_step != self.quantity_step.to_integral_value()
                or self.quantity_step < 1 or self.contract_multiplier > 1000000
                or self.taker_fee_fraction >= 1 or self.maker_fee_fraction >= 1
                or self.worst_slippage_fraction >= 1):
            raise ContractEconomicsRefused("ECONOMIC_CONTRACT_LIMITS")

    @classmethod
    def from_public(cls, item, *, metadata_sha256: str,
                    worst_slippage_fraction: Decimal = Decimal("0.003"),
                    origin: str = "PUBLIC_CONTRACT_SNAPSHOT_UNATTESTED"):
        # Import inside method avoids cycle with Stage21C, which imports Stage21B.
        from .public_forward_capture_stage21c_v1 import PublicContractGeometry
        if (type(item) is not PublicContractGeometry
                or item.settle_currency != "USDT" or item.is_inverse is not False
                or item.is_quanto is not True):
            raise ContractEconomicsRefused("NONLINEAR_OR_INCOMPLETE_PROVIDER_GEOMETRY")
        try:
            return cls("kucoin_futures", item.symbol,
                       Decimal(item.base_units_per_contract),
                       Decimal(item.lot_contracts), Decimal(item.price_tick),
                       Decimal(item.taker_fee_fraction),
                       Decimal(item.maker_fee_fraction),
                       worst_slippage_fraction, metadata_sha256,
                       origin=origin)
        except (ValueError, ArithmeticError) as exc:
            raise ContractEconomicsRefused("INVALID_PROVIDER_DECIMAL_GEOMETRY") from exc

    def wire(self) -> dict:
        return {k: str(v) if type(v) is Decimal else v
                for k, v in asdict(self).items()}

    @classmethod
    def from_wire(cls, value: dict):
        try:
            if type(value) is not dict or set(value) != set(cls.__dataclass_fields__):
                raise ValueError("fields")
            return cls(**{k: Decimal(v) if k in (
                "contract_multiplier", "quantity_step", "price_tick",
                "taker_fee_fraction", "maker_fee_fraction",
                "worst_slippage_fraction") else v for k, v in value.items()})
        except (ValueError, TypeError, ArithmeticError) as exc:
            raise ContractEconomicsRefused("NONCANONICAL_ECONOMIC_SNAPSHOT") from exc

    @property
    def digest(self) -> str:
        return hashlib.sha256(json.dumps(self.wire(), sort_keys=True,
                            separators=(",", ":")).encode("utf-8")).hexdigest()

    def validate_order(self, quantity: Decimal, entry: Decimal,
                       stop: Decimal) -> None:
        for name, value in (("QTY", quantity), ("ENTRY", entry), ("STOP", stop)):
            _positive(value, name)
        if ((quantity / self.quantity_step) !=
                (quantity / self.quantity_step).to_integral_value()):
            raise ContractEconomicsRefused("CONTRACT_LOT_STEP_VIOLATION")
        for price in (entry, stop):
            if (price / self.price_tick) != (price / self.price_tick).to_integral_value():
                raise ContractEconomicsRefused("CONTRACT_PRICE_TICK_VIOLATION")

    def notional(self, quantity: Decimal, entry: Decimal) -> Decimal:
        return quantity * self.contract_multiplier * entry

    def reserved_risk(self, quantity: Decimal, entry: Decimal,
                      stop: Decimal) -> Decimal:
        self.validate_order(quantity, entry, stop)
        worst_exit = max(entry, stop)
        return quantity * self.contract_multiplier * (
            abs(entry - stop) + entry * self.taker_fee_fraction
            + worst_exit * (self.taker_fee_fraction +
                            self.worst_slippage_fraction))

    def modeled_exit(self, *, quantity: Decimal, entry: Decimal,
                     exit_price: Decimal, direction: str) -> tuple[Decimal, Decimal]:
        _positive(quantity, "EXIT_QUANTITY")
        _positive(entry, "ENTRY_PRICE")
        _positive(exit_price, "EXIT_PRICE")
        if direction not in ("long", "short"):
            raise ContractEconomicsRefused("INVALID_EXIT_DIRECTION")
        gross = (Decimal(1) if direction == "long" else Decimal(-1)) * (
            exit_price - entry) * quantity * self.contract_multiplier
        friction = quantity * self.contract_multiplier * (
            entry * self.taker_fee_fraction
            + exit_price * self.taker_fee_fraction
            + max(entry, exit_price) * self.worst_slippage_fraction)
        return gross, friction


def require_contract_research_ack(operator_ack: bool) -> None:
    if (operator_ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or "MMT_PRODUCTION" in os.environ):
        raise ContractEconomicsRefused("EXPLICIT_NONPRODUCTION_ECONOMIC_RESEARCH_REQUIRED")


__all__ = ["PaperContractEconomics", "ContractEconomicsRefused",
           "require_contract_research_ack"]
