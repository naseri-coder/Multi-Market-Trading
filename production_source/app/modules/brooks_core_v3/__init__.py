"""Brooks Core v3 isolated architecture package.

Phase 1 provides the Brooks Foundation contracts. Phase 2 adds the crypto adaptation
layer without changing signal, risk, scoring, AI, Telegram, or production wiring.
"""

from app.modules.brooks_core_v3.crypto_adaptation import CryptoAdaptationEngine
from app.modules.brooks_core_v3.crypto_adaptation_entities import (
    CryptoAdaptationAssessment,
    CryptoAdaptationEvidence,
    CryptoAdaptationInput,
    DerivativesObservation,
    LiquidityObservation,
)
from app.modules.brooks_core_v3.crypto_adaptation_policy import CryptoAdaptationPolicy
from app.modules.brooks_core_v3.crypto_interfaces import (
    CryptoAdaptationEvaluator,
    DerivativesObservationProvider,
    LiquidityObservationProvider,
)
from app.modules.brooks_core_v3.entities import (
    ContextModel,
    EvidenceItem,
    EvidenceRegistry,
    FoundationSnapshot,
    MarketState,
    NarrativeModel,
)
from app.modules.brooks_core_v3.foundation import BrooksCoreV3FoundationBuilder
from app.modules.brooks_core_v3.source_catalog import (
    CATALOG_VERSION,
    RuleReference,
    brooks_rule_catalog,
    get_rule_reference,
    rule_ids,
)

__all__ = (
    "BrooksCoreV3FoundationBuilder",
    "CATALOG_VERSION",
    "ContextModel",
    "CryptoAdaptationAssessment",
    "CryptoAdaptationEngine",
    "CryptoAdaptationEvaluator",
    "CryptoAdaptationEvidence",
    "CryptoAdaptationInput",
    "CryptoAdaptationPolicy",
    "DerivativesObservation",
    "DerivativesObservationProvider",
    "EvidenceItem",
    "EvidenceRegistry",
    "FoundationSnapshot",
    "LiquidityObservation",
    "LiquidityObservationProvider",
    "MarketState",
    "NarrativeModel",
    "RuleReference",
    "brooks_rule_catalog",
    "get_rule_reference",
    "rule_ids",
)
