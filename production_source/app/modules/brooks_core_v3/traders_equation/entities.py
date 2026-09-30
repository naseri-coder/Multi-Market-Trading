"""Immutable contracts for the Brooks Trader's Equation roadmap stage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from .source import FORMULA_VERSION, TraderEquationSourceEvidence


class TraderEquationStatus(StrEnum):
    FAVORABLE = "FAVORABLE"
    MARGINAL = "MARGINAL"
    UNFAVORABLE = "UNFAVORABLE"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True, slots=True)
class TraderEquationInput:
    market_snapshot_id: str
    setup_candidate_id: str
    probability_success: Decimal | None
    risk: Decimal | None
    reward: Decimal | None
    probability_basis: str | None
    risk_basis: str | None
    reward_basis: str | None
    evaluated_at: datetime

    def __post_init__(self) -> None:
        for value, name in (
            (self.market_snapshot_id, "market_snapshot_id"),
            (self.setup_candidate_id, "setup_candidate_id"),
        ):
            if not value.strip():
                raise ValueError(f"{name} cannot be blank")
        if self.evaluated_at.tzinfo is None or self.evaluated_at.utcoffset() is None:
            raise ValueError("evaluated_at must be timezone-aware")
        if self.probability_success is not None and not (
            Decimal("0") <= self.probability_success <= Decimal("1")
        ):
            raise ValueError("probability_success must be between 0 and 1")
        for value, name in ((self.risk, "risk"), (self.reward, "reward")):
            if value is not None and value <= 0:
                raise ValueError(f"{name} must be positive when supplied")
        self._validate_basis(self.probability_success, self.probability_basis, "probability")
        self._validate_basis(self.risk, self.risk_basis, "risk")
        self._validate_basis(self.reward, self.reward_basis, "reward")

    @staticmethod
    def _validate_basis(value: object | None, basis: str | None, label: str) -> None:
        if value is not None and (basis is None or not basis.strip()):
            raise ValueError(f"{label}_basis is required when {label} is supplied")
        if value is None and basis is not None:
            raise ValueError(f"{label}_basis requires a corresponding value")


@dataclass(frozen=True, slots=True)
class TraderEquationAssessment:
    market_snapshot_id: str
    setup_candidate_id: str
    status: TraderEquationStatus
    probability_success: Decimal | None
    probability_failure: Decimal | None
    risk: Decimal | None
    reward: Decimal | None
    probability_basis: str | None
    risk_basis: str | None
    reward_basis: str | None
    weighted_reward: Decimal | None
    weighted_risk: Decimal | None
    expected_edge: Decimal | None
    break_even_probability: Decimal | None
    blockers: tuple[str, ...]
    source_evidence: TraderEquationSourceEvidence
    formula_version: str = FORMULA_VERSION

    def __post_init__(self) -> None:
        if any(not item.strip() for item in self.blockers):
            raise ValueError("blockers cannot contain blank values")
        if not self.formula_version.strip():
            raise ValueError("formula_version cannot be blank")
        if self.status is TraderEquationStatus.UNRESOLVED:
            if self.expected_edge is not None:
                raise ValueError("unresolved assessment cannot claim expected edge")
        elif self.expected_edge is None or self.break_even_probability is None:
            raise ValueError("resolved assessment requires mathematical outputs")

    @property
    def publication_allowed(self) -> bool:
        return False
