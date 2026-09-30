"""Brooks Core v3 Trader's Equation roadmap stage."""

from .adapter import from_phase3_contracts
from .entities import (
    TraderEquationAssessment,
    TraderEquationInput,
    TraderEquationStatus,
)
from .evaluator import BrooksTraderEquationEvaluator
from .source import FORMULA_VERSION, RULE_ID, TraderEquationSourceEvidence

__all__ = [
    "BrooksTraderEquationEvaluator",
    "FORMULA_VERSION",
    "RULE_ID",
    "TraderEquationAssessment",
    "TraderEquationInput",
    "TraderEquationSourceEvidence",
    "TraderEquationStatus",
    "from_phase3_contracts",
]
