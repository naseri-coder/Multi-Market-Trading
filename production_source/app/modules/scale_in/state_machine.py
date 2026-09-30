"""Explicit Scale-In order/execution state transitions."""
from __future__ import annotations

from .entities import ScaleExecutionState

_ALLOWED: dict[ScaleExecutionState, frozenset[ScaleExecutionState]] = {
    ScaleExecutionState.SCALE_IN_PROPOSED: frozenset({
        ScaleExecutionState.SCALE_IN_APPROVED,
        ScaleExecutionState.SCALE_IN_REJECTED,
        ScaleExecutionState.SCALE_IN_CANCELLED,
    }),
    ScaleExecutionState.SCALE_IN_APPROVED: frozenset({
        ScaleExecutionState.SCALE_IN_ORDER_PENDING,
        ScaleExecutionState.SCALE_IN_CANCELLED,
        ScaleExecutionState.SCALE_IN_FAILED,
    }),
    ScaleExecutionState.SCALE_IN_ORDER_PENDING: frozenset({
        ScaleExecutionState.SCALE_IN_PARTIALLY_FILLED,
        ScaleExecutionState.SCALE_IN_FILLED,
        ScaleExecutionState.SCALE_IN_CANCELLED,
        ScaleExecutionState.SCALE_IN_FAILED,
    }),
    ScaleExecutionState.SCALE_IN_PARTIALLY_FILLED: frozenset({
        ScaleExecutionState.SCALE_IN_PARTIALLY_FILLED,
        ScaleExecutionState.SCALE_IN_FILLED,
        ScaleExecutionState.SCALE_IN_CANCELLED,
        ScaleExecutionState.SCALE_IN_FAILED,
    }),
    ScaleExecutionState.SCALE_IN_FILLED: frozenset(),
    ScaleExecutionState.SCALE_IN_CANCELLED: frozenset(),
    ScaleExecutionState.SCALE_IN_REJECTED: frozenset(),
    ScaleExecutionState.SCALE_IN_FAILED: frozenset(),
}


def transition(current: ScaleExecutionState, target: ScaleExecutionState, *, recovery: bool = False) -> ScaleExecutionState:
    if target in _ALLOWED[current]:
        return target
    if recovery and current is ScaleExecutionState.SCALE_IN_APPROVED and target in {
        ScaleExecutionState.SCALE_IN_PARTIALLY_FILLED,
        ScaleExecutionState.SCALE_IN_FILLED,
    }:
        # Exchange may fill after approval but before ORDER_PENDING persistence.
        return target
    raise ValueError(f"invalid Scale-In state transition: {current} -> {target}")
