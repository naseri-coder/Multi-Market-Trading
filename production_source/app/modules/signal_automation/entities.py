"""Framework-independent Brooks automation import contracts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from typing import TYPE_CHECKING

from app.modules.signals.entities import CreateSignal

if TYPE_CHECKING:
    from app.modules.brooks_core.engine_contract import (
        ReversalOutcomeContext,
        StopSourceIdentity,
        TargetPlanLifecycle,
        TargetSourceIdentity,
    )

_ALLOWED_DIRECTIONS = {"LONG", "SHORT"}
_ALLOWED_MODES = {"SHADOW", "PAPER", "LIVE"}
_ALLOWED_SCOPES = {"INTERNAL", "PRIVATE_TEST", "PUBLIC", "VIP", "PUBLIC_VIP"}
_ALLOWED_RULE_STATUS = {"PASS", "FAIL", "NOT_APPLICABLE", "AMBIGUOUS"}

FINAL_BROOKS_HP_SEMANTIC_COHORT_ID = "BROOKS_HP_SEMANTIC_COHORT_W01_W19_V1"
BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1 = (
    "BROOKS_HP_OUTCOME_POLICY_EVENT_PLUS_REALIZED_R_V1"
)
BROOKS_HP_STATISTICS_CONTRACT_ID = (
    "brooks-v5v6-realized-r-mean-studentized-bootstrap-ci95-b100k-v1"
)
HP_COLD_START_BOOTSTRAP_POLICY_ID = "BROOKS_HP_COLD_START_SHADOW_W01_W19_V1"


def _hp_cold_start_shadow_opportunity_identity(
    *,
    identity_kind: str,
    semantic_cohort_id: str,
    economic_opportunity_id: str,
    symbol: str,
    timeframe: str,
    direction: str,
) -> str:
    """Derive one bootstrap identity from the stable economic-opportunity namespace."""
    values = {
        "identity_kind": identity_kind,
        "semantic_cohort_id": semantic_cohort_id,
        "economic_opportunity_id": economic_opportunity_id,
        "symbol": symbol,
        "timeframe": timeframe,
        "direction": direction,
    }
    if any(not isinstance(value, str) or not value.strip() for value in values.values()):
        raise ValueError("complete bootstrap economic-opportunity identity is required")
    canonical = "|".join(
        (
            "BROOKS",
            "SHADOW",
            HP_COLD_START_BOOTSTRAP_POLICY_ID,
            semantic_cohort_id,
            symbol.upper(),
            timeframe,
            direction.upper(),
            economic_opportunity_id,
            identity_kind,
        )
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def hp_cold_start_shadow_source_signal_id(
    original_source_signal_id: str,
    semantic_cohort_id: str,
    *,
    economic_opportunity_id: str | None = None,
    symbol: str | None = None,
    timeframe: str | None = None,
    direction: str | None = None,
) -> str:
    """Derive the persisted SHADOW source identity."""
    if economic_opportunity_id is not None:
        return _hp_cold_start_shadow_opportunity_identity(
            identity_kind="SOURCE_SIGNAL",
            semantic_cohort_id=semantic_cohort_id,
            economic_opportunity_id=economic_opportunity_id,
            symbol=symbol or "",
            timeframe=timeframe or "",
            direction=direction or "",
        )
    if not original_source_signal_id.strip() or not semantic_cohort_id.strip():
        raise ValueError("original source identity and semantic cohort are required")
    canonical = "|".join(
        (
            "BROOKS",
            "HP_COLD_START_BOOTSTRAP",
            "SHADOW",
            HP_COLD_START_BOOTSTRAP_POLICY_ID,
            semantic_cohort_id,
            original_source_signal_id,
        )
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def hp_cold_start_shadow_idempotency_key(
    *,
    semantic_cohort_id: str,
    economic_opportunity_id: str,
    symbol: str,
    timeframe: str,
    direction: str,
) -> str:
    """Derive the idempotency barrier for the same bootstrap opportunity."""
    return _hp_cold_start_shadow_opportunity_identity(
        identity_kind="IDEMPOTENCY",
        semantic_cohort_id=semantic_cohort_id,
        economic_opportunity_id=economic_opportunity_id,
        symbol=symbol,
        timeframe=timeframe,
        direction=direction,
    )


@dataclass(frozen=True, slots=True)
class BrooksRuleEvidence:
    """One auditable rule evaluation attached to an imported Brooks signal."""

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
        if any(page <= 0 for page in self.source_pages):
            raise ValueError("source pages must be positive")


@dataclass(frozen=True, slots=True)
class BrooksSignalImport:
    """Command for atomically importing one tradeable Brooks decision."""

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
    target_source_identities: tuple["TargetSourceIdentity", ...] = ()
    stop_source_identity: "StopSourceIdentity | None" = None
    target_plan_lifecycle: "TargetPlanLifecycle | None" = None
    reversal_outcome_context: "ReversalOutcomeContext | None" = None
    semantic_cohort_id: str | None = None
    bootstrap_provenance: dict[str, object] | None = None
    opportunity_variant: str | None = None
    ii_first_open_time: datetime | None = None
    ii_second_open_time: datetime | None = None
    opportunity_view: str | None = None

    def __post_init__(self) -> None:
        if self.opportunity_variant is not None:
            if self.opportunity_variant != "CH6_II_PAIR_STOP_V1":
                raise ValueError("unsupported opportunity variant")
            if self.opportunity_view not in {"PENDING", "CONFIRMED"}:
                raise ValueError("ii pair view must be PENDING or CONFIRMED")
            pair = (self.ii_first_open_time, self.ii_second_open_time)
            if any(
                not isinstance(bar_time, datetime) or bar_time.tzinfo is None
                for bar_time in pair
            ):
                raise ValueError("ii pair requires two timezone-aware bar origins")
            if pair[0].astimezone(UTC) >= pair[1].astimezone(UTC):
                raise ValueError("ii pair origins must be ordered")
        elif any(
            value is not None
            for value in (
                self.ii_first_open_time,
                self.ii_second_open_time,
                self.opportunity_view,
            )
        ):
            raise ValueError("ii pair fields require the scoped opportunity variant")
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

        if self.semantic_cohort_id is not None and not self.semantic_cohort_id.strip():
            raise ValueError("semantic_cohort_id must be non-empty when provided")

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
            if any(target <= self.entry_price for target in self.targets):
                raise ValueError("LONG targets must be above entry")
            if tuple(sorted(self.targets)) != self.targets:
                raise ValueError("LONG targets must be ascending")
        else:
            if self.stop_loss <= self.entry_price:
                raise ValueError("SHORT stop must be above entry")
            if any(target >= self.entry_price for target in self.targets):
                raise ValueError("SHORT targets must be below entry")
            if tuple(sorted(self.targets, reverse=True)) != self.targets:
                raise ValueError("SHORT targets must be descending")

        if self.generation_mode == "SHADOW" and self.publication_scope != "INTERNAL":
            raise ValueError("SHADOW must use INTERNAL publication scope")
        if self.generation_mode == "PAPER" and self.publication_scope != "PRIVATE_TEST":
            raise ValueError("PAPER must use PRIVATE_TEST publication scope")
        if self.generation_mode != "LIVE" and self.counts_toward_performance:
            raise ValueError("only LIVE signals may count toward production performance")
        if self.bootstrap_provenance is not None:
            if self.generation_mode != "SHADOW" or self.publication_scope != "INTERNAL":
                raise ValueError("HP bootstrap provenance requires SHADOW/INTERNAL")
            if self.counts_toward_performance:
                raise ValueError("HP bootstrap observations must not count toward live performance")
            required_bootstrap = {
                "bootstrap",
                "policy_id",
                "semantic_cohort_id",
                "original_source_signal_id",
                "mode_scoped_source_signal_id",
                "state",
            }
            if not required_bootstrap.issubset(self.bootstrap_provenance):
                raise ValueError("incomplete HP bootstrap provenance")
            if self.bootstrap_provenance.get("bootstrap") is not True:
                raise ValueError("HP bootstrap provenance must be explicit")
            if self.bootstrap_provenance.get("policy_id") != HP_COLD_START_BOOTSTRAP_POLICY_ID:
                raise ValueError("unsupported HP bootstrap policy")
            if self.bootstrap_provenance.get("semantic_cohort_id") != self.semantic_cohort_id:
                raise ValueError("HP bootstrap cohort must match signal cohort")
            if self.bootstrap_provenance.get("mode_scoped_source_signal_id") != self.source_signal_id:
                raise ValueError("HP bootstrap source identity must match persisted source_signal_id")

    @property
    def opportunity_key(self) -> str | None:
        if self.opportunity_variant is None:
            return None
        assert self.ii_first_open_time is not None
        assert self.ii_second_open_time is not None
        origin = (
            "BROOKS",
            self.generation_mode,
            self.opportunity_variant,
            self.exchange.strip().lower(),
            self.market_type.strip().lower(),
            self.symbol.strip().upper(),
            self.timeframe.strip(),
            self.direction,
            self.ii_first_open_time.astimezone(UTC).isoformat(),
            self.ii_second_open_time.astimezone(UTC).isoformat(),
        )
        return sha256(json.dumps(origin, separators=(",", ":")).encode()).hexdigest()

    @property
    def idempotency_key(self) -> str:
        if (
            self.generation_mode == "SHADOW"
            and isinstance(self.bootstrap_provenance, dict)
            and self.bootstrap_provenance.get("bootstrap") is True
            and self.bootstrap_provenance.get("policy_id") == HP_COLD_START_BOOTSTRAP_POLICY_ID
            and self.semantic_cohort_id
        ):
            economic_opportunity_id = self.bootstrap_provenance.get("economic_opportunity_id")
            if isinstance(economic_opportunity_id, str) and economic_opportunity_id.strip():
                return hp_cold_start_shadow_idempotency_key(
                    semantic_cohort_id=self.semantic_cohort_id,
                    economic_opportunity_id=economic_opportunity_id,
                    symbol=self.symbol,
                    timeframe=self.timeframe,
                    direction=self.direction,
                )
        canonical = "|".join(
            [
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
            ]
        )
        return sha256(canonical.encode("utf-8")).hexdigest()

    def to_create_signal(self) -> CreateSignal:
        return CreateSignal(
            symbol=self.symbol,
            direction=self.direction,
            entry_price=self.entry_price,
            stop_loss=self.stop_loss,
            leverage=self.leverage,
            description=self.description,
            as_draft=False,
        )


@dataclass(frozen=True, slots=True)
class AutomationMetadataRecord:
    signal_id: int
    producer: str
    generation_mode: str
    exchange: str
    market_type: str
    timeframe: str
    setup_type: str | None
    source_signal_id: str
    idempotency_key: str
    market_snapshot_id: str
    market_snapshot_hash: str
    engine_version: str
    rule_set_version: str
    configuration_version: str
    reasoning: tuple[str, ...]
    rule_ids: tuple[str, ...]
    failed_rules: tuple[str, ...]
    counts_toward_performance: bool
    opportunity_variant: str | None = None
    opportunity_key: str | None = None


@dataclass(frozen=True, slots=True)
class BrooksSignalImportResult:
    signal_id: int
    created: bool
    idempotency_key: str
    publication_scope: str
    disposition: str = "CREATED"
