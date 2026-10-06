"""MA 7/25/99 Regime & Momentum Core (MARC)."""

from app.modules.marc_core.engine import MARCSignalEngine, evaluate_indicator_frames
from app.modules.marc_core.entities import (
    MARC_CONFIGURATION_VERSION,
    MARC_ENGINE_VERSION,
    MARC_EXIT_MODEL,
    MARC_RULE_SET_VERSION,
    MARC_SETUP_TYPE,
    MARCCandidate,
    MARCDecision,
    MARCEntryPlan,
    MARCIndicatorFrame,
    MARCState,
)
from app.modules.marc_core.policy import MARCPolicy
from app.modules.marc_core.replay import replay_entry_plans

__all__ = [
    "MARC_CONFIGURATION_VERSION",
    "MARC_ENGINE_VERSION",
    "MARC_EXIT_MODEL",
    "MARC_RULE_SET_VERSION",
    "MARC_SETUP_TYPE",
    "MARCCandidate",
    "MARCDecision",
    "MARCEntryPlan",
    "MARCIndicatorFrame",
    "MARCPolicy",
    "MARCSignalEngine",
    "MARCState",
    "evaluate_indicator_frames",
    "replay_entry_plans",
]
