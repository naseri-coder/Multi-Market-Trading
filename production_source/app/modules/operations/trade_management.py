"""Brooks trilogy V6 context-aware post-target trade management.

Book examples define families of valid management, not one universal target rule.
This module freezes one auditable plan before the mutable stop begins to trail.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Any, Protocol

from app.modules.brooks_core.engine_contract import (
    ReversalOutcomeContext,
    StopSourceIdentity,
    TargetPlanLifecycle,
    TargetSourceIdentity,
)

POLICY_VERSION = "brooks-trilogy-trade-management-v6"
TREND_REGIMES = frozenset({"TREND", "BULL_TREND", "BEAR_TREND"})
RANGE_REGIMES = frozenset({"RANGE", "TRADING_RANGE", "TIGHT_TRADING_RANGE", "BARB_WIRE"})


class TargetLike(Protocol):
    target_number: int
    target_price: Decimal
    status: str


@dataclass(frozen=True, slots=True)
class TradeManagementPlan:
    """Immutable scale-out and runner plan expressed as fractions of initial size."""

    context_class: str
    initial_stop_loss: Decimal
    initial_risk: Decimal
    target_exit_fractions: tuple[tuple[int, Decimal], ...]
    runner_fraction: Decimal
    breakeven_mode: str
    source_rule_ids: tuple[str, ...]
    policy_version: str = POLICY_VERSION

    def fraction_for_target(self, target_number: int) -> Decimal:
        return dict(self.target_exit_fractions).get(target_number, Decimal("0"))

    def realized_fraction(self, targets: Iterable[TargetLike]) -> Decimal:
        return sum(
            (
                self.fraction_for_target(target.target_number)
                for target in targets
                if target.status == "HIT"
            ),
            Decimal("0"),
        )

    def remaining_fraction(self, targets: Iterable[TargetLike]) -> Decimal:
        return max(Decimal("0"), Decimal("1") - self.realized_fraction(targets))

    def has_secured_partial(self, targets: Iterable[TargetLike]) -> bool:
        return self.realized_fraction(targets) > 0

    def to_metadata(self) -> dict[str, object]:
        return {
            "policy_version": self.policy_version,
            "context_class": self.context_class,
            "initial_stop_loss": str(self.initial_stop_loss),
            "initial_risk": str(self.initial_risk),
            "target_exit_fractions": {
                str(number): str(fraction) for number, fraction in self.target_exit_fractions
            },
            "runner_fraction": str(self.runner_fraction),
            "breakeven_mode": self.breakeven_mode,
            "source_rule_ids": list(self.source_rule_ids),
        }

    @classmethod
    def from_metadata(cls, value: Mapping[str, Any]) -> TradeManagementPlan:
        if value.get("policy_version") != POLICY_VERSION:
            raise ValueError("unsupported trade-management policy version")
        raw_fractions = value.get("target_exit_fractions")
        if not isinstance(raw_fractions, Mapping):
            raise ValueError("target_exit_fractions must be an object")
        fractions = tuple(
            sorted(
                (
                    (int(number), Decimal(str(fraction)))
                    for number, fraction in raw_fractions.items()
                ),
                key=lambda item: item[0],
            )
        )
        return cls(
            context_class=str(value["context_class"]),
            initial_stop_loss=Decimal(str(value["initial_stop_loss"])),
            initial_risk=Decimal(str(value["initial_risk"])),
            target_exit_fractions=fractions,
            runner_fraction=Decimal(str(value["runner_fraction"])),
            breakeven_mode=str(value["breakeven_mode"]),
            source_rule_ids=tuple(str(item) for item in value.get("source_rule_ids", ())),
        )


def validate_brooks_execution_contract(
    *,
    direction: str,
    targets: Iterable[TargetLike],
    target_source_identities: Iterable[TargetSourceIdentity] = (),
    stop_source_identity: StopSourceIdentity | None = None,
    target_plan_lifecycle: TargetPlanLifecycle | None = None,
    reversal_outcome_context: ReversalOutcomeContext | None = None,
) -> None:
    """Consume/validate Core typed identity without changing TM_V6 economics."""
    target_rows = tuple(targets)
    identities = tuple(target_source_identities)
    source_ids = {
        source.source_id
        for identity in identities
        for source in identity.sources
    }

    if identities:
        by_number = {item.target_number: item for item in target_rows}
        if len(identities) != len(target_rows):
            raise ValueError("typed target identity count must match persisted targets")
        for identity in identities:
            target = by_number.get(identity.target_number)
            if target is None or target.target_price != identity.target_price:
                raise ValueError("typed target identity must match persisted target geometry")

    if stop_source_identity is not None and stop_source_identity.direction not in {
        direction,
        "UNRESOLVED",
    }:
        raise ValueError("typed stop identity direction must match signal")

    if target_plan_lifecycle is not None:
        if target_plan_lifecycle.direction != direction:
            raise ValueError("typed target-plan direction must match signal")
        if (
            target_plan_lifecycle.target_source_ids
            and not set(target_plan_lifecycle.target_source_ids).issubset(source_ids)
        ):
            raise ValueError("target plan must retain typed target source identity")
        if (
            target_plan_lifecycle.initial_stop_source_id is not None
            and stop_source_identity is not None
            and target_plan_lifecycle.initial_stop_source_id != stop_source_identity.source_id
        ):
            raise ValueError("target plan must retain initial stop source identity")

    if reversal_outcome_context is not None:
        if not identities or stop_source_identity is None or target_plan_lifecycle is None:
            raise ValueError("reversal outcome requires complete Core typed contract")
        if reversal_outcome_context.direction != direction:
            raise ValueError("reversal outcome direction must match signal")
        if not set(reversal_outcome_context.target_source_ids).issubset(source_ids):
            raise ValueError("reversal outcome must retain target source identity")
        if reversal_outcome_context.initial_stop_source_id != stop_source_identity.source_id:
            raise ValueError("reversal outcome must retain initial stop source identity")
        if reversal_outcome_context.target_plan_id != target_plan_lifecycle.plan_id:
            raise ValueError("reversal outcome must retain target-plan identity")


def reversal_outcome_management_mode(
    context: ReversalOutcomeContext | None,
) -> str:
    """BROOKS-GAP-080 source-semantic management family without numeric retuning."""
    if context is None:
        return "NOT_APPLICABLE"
    return {
        "PENDING_REVERSAL_OUTCOME": "PENDING_REVERSAL_MANAGEMENT",
        "OPPOSITE_TREND_OUTCOME": "SWING_RUNNER_MANAGEMENT",
        "TRADING_RANGE_OUTCOME": "AGGRESSIVE_RANGE_PROFIT_TAKING",
        "FAILED_REVERSAL_OUTCOME": "EXIT_OR_CONTINUATION",
    }[context.state]


def market_regime_for_reversal_outcome(
    context: ReversalOutcomeContext | None,
    fallback_market_regime: str | None,
) -> str | None:
    """Map typed outcome to an already-existing TM_V6 context family."""
    if context is None:
        return fallback_market_regime
    if context.state == "OPPOSITE_TREND_OUTCOME":
        return "TREND"
    if context.state == "TRADING_RANGE_OUTCOME":
        return "TRADING_RANGE"
    return fallback_market_regime


def advance_reversal_outcome_context(
    context: ReversalOutcomeContext,
    *,
    observed_direction: str,
    observed_always_in: str,
    observed_regime: str | None,
    transition_available_at: str,
    transition_source_signal_id: str,
) -> ReversalOutcomeContext:
    """Causally advance one preserved reversal origin from approved typed evidence."""
    if context.state != "PENDING_REVERSAL_OUTCOME":
        return context

    direction = observed_direction.strip().upper()
    always_in = observed_always_in.strip().upper()
    regime = (observed_regime or "").strip().upper()
    opposite = "SHORT" if context.direction == "LONG" else "LONG"

    if regime in RANGE_REGIMES:
        state = "TRADING_RANGE_OUTCOME"
    elif (
        direction == context.direction
        and always_in == context.direction
        and regime in TREND_REGIMES
    ):
        state = "OPPOSITE_TREND_OUTCOME"
    elif direction == opposite and always_in == opposite:
        state = "FAILED_REVERSAL_OUTCOME"
    else:
        return context

    return replace(
        context,
        state=state,
        transition_available_at=transition_available_at,
        transition_source_signal_id=transition_source_signal_id,
    )


def _context_class(market_regime: str | None) -> str:
    normalized = (market_regime or "").strip().upper()
    if normalized in TREND_REGIMES:
        return "STRONG_TREND"
    if normalized in RANGE_REGIMES:
        return "TRADING_RANGE"
    return "REVERSAL_OR_TRANSITION"


def _range_fractions(target_numbers: tuple[int, ...]) -> dict[int, Decimal]:
    """Exit in the range rather than leave an exposed runner beyond its far target."""
    if not target_numbers:
        return {}
    if len(target_numbers) == 1:
        return {target_numbers[0]: Decimal("1")}
    return {
        number: (
            Decimal("0.5") if number in {target_numbers[0], target_numbers[-1]} else Decimal("0")
        )
        for number in target_numbers
    }


def _swing_fractions(
    *,
    target_numbers: tuple[int, ...],
    reward_multiples: Mapping[int, Decimal],
    minimum_first_exit_r: Decimal,
) -> dict[int, Decimal]:
    fractions = {number: Decimal("0") for number in target_numbers}
    eligible = tuple(
        number for number in target_numbers if reward_multiples[number] >= minimum_first_exit_r
    )
    if not eligible:
        return fractions
    fractions[eligible[0]] = Decimal("0.5")
    if len(eligible) > 1:
        fractions[eligible[1]] = Decimal("0.25")
    return fractions


def build_trade_management_plan(
    *,
    direction: str,
    entry_price: Decimal,
    initial_stop_loss: Decimal,
    targets: Iterable[TargetLike],
    market_regime: str | None,
    rule_ids: Iterable[str] = (),
    context_metadata: Mapping[str, Any] | None = None,
    reversal_outcome_context: ReversalOutcomeContext | None = None,
) -> TradeManagementPlan:
    """Build the precommitted plan from initial risk and Brooks market context."""
    del direction  # Distance is symmetric; direction geometry is validated upstream.
    ordered = tuple(sorted(targets, key=lambda item: item.target_number))
    initial_risk = abs(entry_price - initial_stop_loss)
    if initial_risk <= 0:
        raise ValueError("initial risk must be positive")

    target_numbers = tuple(item.target_number for item in ordered)
    reward_multiples = {
        item.target_number: abs(item.target_price - entry_price) / initial_risk for item in ordered
    }
    effective_regime = market_regime_for_reversal_outcome(
        reversal_outcome_context, market_regime
    )
    context = _context_class(effective_regime)
    if context == "TRADING_RANGE":
        fractions = _range_fractions(target_numbers)
    else:
        threshold = Decimal("2") if context == "STRONG_TREND" else Decimal("1")
        fractions = _swing_fractions(
            target_numbers=target_numbers,
            reward_multiples=reward_multiples,
            minimum_first_exit_r=threshold,
        )

    allocated = sum(fractions.values(), Decimal("0"))
    runner = Decimal("1") - allocated
    del rule_ids  # The catalog does not prove that any one rule fired.
    metadata = context_metadata or {}
    # rule_ids is a source/evaluation catalog, not proof that a rule fired.
    # Use only observed context metadata for the tight-channel exception.
    tight_trend = (
        context == "STRONG_TREND" and str(metadata.get("channel_quality", "")).upper() == "TIGHT"
    )
    breakeven_mode = "STRUCTURE_ONLY" if tight_trend else "AFTER_PARTIAL"

    return TradeManagementPlan(
        context_class=context,
        initial_stop_loss=initial_stop_loss,
        initial_risk=initial_risk,
        target_exit_fractions=tuple((number, fractions[number]) for number in target_numbers),
        runner_fraction=runner,
        breakeven_mode=breakeven_mode,
        source_rule_ids=(
            "BOOKS-V5-TRADE-MANAGEMENT",
            "BOOKS-V5-TRAILING-STOP",
            "BOOKS-V5-TRADERS-EQUATION",
        ) + (("BROOKS-GAP-080",) if reversal_outcome_context is not None else ()),
    )


def build_legacy_carryover_plan(
    *,
    entry_price: Decimal,
    initial_stop_loss: Decimal,
    targets: Iterable[TargetLike],
) -> TradeManagementPlan:
    """Freeze V5 equal-target accounting after any target was already reported."""
    ordered = tuple(sorted(targets, key=lambda item: item.target_number))
    initial_risk = abs(entry_price - initial_stop_loss)
    if initial_risk <= 0:
        raise ValueError("initial risk must be positive")
    if not ordered:
        fractions: tuple[tuple[int, Decimal], ...] = ()
        runner = Decimal("1")
    else:
        equal = Decimal("1") / Decimal(len(ordered))
        fractions = tuple(
            (
                target.target_number,
                (
                    equal
                    if index < len(ordered) - 1
                    else Decimal("1") - equal * Decimal(len(ordered) - 1)
                ),
            )
            for index, target in enumerate(ordered)
        )
        runner = Decimal("0")
    return TradeManagementPlan(
        context_class="V5_LEGACY_CARRYOVER",
        initial_stop_loss=initial_stop_loss,
        initial_risk=initial_risk,
        target_exit_fractions=fractions,
        runner_fraction=runner,
        breakeven_mode="AFTER_PARTIAL",
        source_rule_ids=("V5_LEGACY_CARRYOVER",),
    )


def weighted_close_return(
    *,
    plan: TradeManagementPlan,
    targets: Iterable[TargetLike],
    target_returns: Mapping[int, Decimal],
    terminal_return: Decimal,
) -> Decimal:
    """Return weighted P/L for realized scale-outs plus all size still open."""
    realized = Decimal("0")
    realized_fraction = Decimal("0")
    for target in targets:
        if target.status != "HIT":
            continue
        fraction = plan.fraction_for_target(target.target_number)
        realized += fraction * target_returns[target.target_number]
        realized_fraction += fraction
    remaining = max(Decimal("0"), Decimal("1") - realized_fraction)
    return realized + remaining * terminal_return
