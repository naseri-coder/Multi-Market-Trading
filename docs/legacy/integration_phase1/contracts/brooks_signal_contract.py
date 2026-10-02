"""Historical reference only; not current release proof or runtime source.
Original source: integration_phase1/contracts/brooks_signal_contract.py
Original SHA256: b6941d4dd6434979bc5fcfb18f83e86cfbbf88cc5a7f906074228eb7ab74ce6f
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from typing import Iterable

from app.modules.signals.entities import CreateSignal

_ALLOWED_DIRECTIONS = {"LONG", "SHORT"}
_ALLOWED_MODES = {"SHADOW", "PAPER", "LIVE"}
_ALLOWED_SCOPES = {"INTERNAL", "PRIVATE_TEST", "PUBLIC", "VIP", "PUBLIC_VIP"}
_ALLOWED_RULE_STATUS = {"PASS", "FAIL", "NOT_APPLICABLE", "AMBIGUOUS"}

@dataclass(frozen=True, slots=True)
class BrooksRuleEvidence:
    rule_id: str
    status: str
    source_pages: tuple[int, ...]
    evidence: tuple[tuple[str, str], ...] = ()
    failed_conditions: tuple[str, ...] = ()
    confidence_components: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not self.rule_id.strip():
            raise ValueError("rule_id is required")
        if self.status not in _ALLOWED_RULE_STATUS:
            raise ValueError("invalid rule status")
        if any(p <= 0 for p in self.source_pages):
            raise ValueError("source pages must be positive")

@dataclass(frozen=True, slots=True)
class BrooksSignalImport:
    source_signal_id: str
    symbol: str
    direction: str
    entry_price: Decimal
    stop_loss: Decimal
    targets: tuple[Decimal, ...]
    leverage: Decimal
    exchange: str
    market_type: str
    timeframe: str
    setup_type: str | None
    market_snapshot_id: str
    market_snapshot_hash: str
    engine_version: str
    rule_set_version: str
    configuration_version: str
    reasoning: tuple[str, ...]
    rule_ids: tuple[str, ...]
    failed_rules: tuple[str, ...]
    rule_evidence: tuple[BrooksRuleEvidence, ...]
    generation_mode: str
    publication_scope: str
    counts_toward_performance: bool = False
    description: str | None = None

    def __post_init__(self) -> None:
        required = {
            "source_signal_id": self.source_signal_id,
            "symbol": self.symbol,
            "exchange": self.exchange,
            "market_type": self.market_type,
            "timeframe": self.timeframe,
            "market_snapshot_id": self.market_snapshot_id,
            "market_snapshot_hash": self.market_snapshot_hash,
            "engine_version": self.engine_version,
            "rule_set_version": self.rule_set_version,
            "configuration_version": self.configuration_version,
        }
        for name, value in required.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} is required")

        if self.direction not in _ALLOWED_DIRECTIONS:
            raise ValueError("direction must be LONG or SHORT")
        if self.generation_mode not in _ALLOWED_MODES:
            raise ValueError("invalid generation_mode")
        if self.publication_scope not in _ALLOWED_SCOPES:
            raise ValueError("invalid publication_scope")
        if self.entry_price <= 0 or self.stop_loss <= 0 or self.leverage <= 0:
            raise ValueError("entry, stop and leverage must be positive")
        if not self.targets:
            raise ValueError("at least one target is required")

        if self.direction == "LONG":
            if self.stop_loss >= self.entry_price:
                raise ValueError("LONG stop must be below entry")
            if any(t <= self.entry_price for t in self.targets):
                raise ValueError("LONG targets must be above entry")
            if tuple(sorted(self.targets)) != self.targets:
                raise ValueError("LONG targets must be ascending")
        else:
            if self.stop_loss <= self.entry_price:
                raise ValueError("SHORT stop must be above entry")
            if any(t >= self.entry_price for t in self.targets):
                raise ValueError("SHORT targets must be below entry")
            if tuple(sorted(self.targets, reverse=True)) != self.targets:
                raise ValueError("SHORT targets must be descending")

        if self.generation_mode == "SHADOW" and self.publication_scope != "INTERNAL":
            raise ValueError("SHADOW must use INTERNAL publication scope")
        if self.generation_mode == "PAPER" and self.publication_scope != "PRIVATE_TEST":
            raise ValueError("PAPER must use PRIVATE_TEST publication scope")
        if self.generation_mode != "LIVE" and self.counts_toward_performance:
            raise ValueError("only LIVE signals may count toward production performance")

    @property
    def idempotency_key(self) -> str:
        canonical = "|".join([
            "BROOKS",
            self.generation_mode,
            self.symbol.upper(),
            self.timeframe,
            self.market_snapshot_hash,
            self.direction,
            self.setup_type or "",
            self.engine_version,
            self.rule_set_version,
            self.configuration_version,
        ])
        return sha256(canonical.encode("utf-8")).hexdigest()

    def to_existing_create_signal(self) -> CreateSignal:
        """Map only fields supported by the existing SignalService command.

        Automation metadata and rule evidence are persisted separately by the
        integration repository in the same caller-owned database transaction.
        """
        return CreateSignal(
            symbol=self.symbol,
            direction=self.direction,
            entry_price=self.entry_price,
            stop_loss=self.stop_loss,
            leverage=self.leverage,
            description=self.description,
            as_draft=False,
        )

def target_prices(command: BrooksSignalImport) -> tuple[Decimal, ...]:
    return command.targets
