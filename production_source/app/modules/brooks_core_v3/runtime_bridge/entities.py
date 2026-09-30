"""Shadow-only runtime result contracts for Brooks Core v3 Phase 4."""

from __future__ import annotations

from dataclasses import dataclass

from app.modules.brooks_core_v3.crypto_adaptation_entities import CryptoAdaptationAssessment
from app.modules.brooks_core_v3.entities import FoundationSnapshot
from app.modules.brooks_core_v3.domain.models import MarketSnapshot as DomainMarketSnapshot


@dataclass(frozen=True, slots=True)
class RuntimeShadowResult:
    source_snapshot_id: str
    source_snapshot_hash: str
    domain_snapshot: DomainMarketSnapshot
    foundation: FoundationSnapshot
    crypto: CryptoAdaptationAssessment
    blockers: tuple[str, ...]
    diagnostics: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        if self.domain_snapshot.market_snapshot_id != self.source_snapshot_id:
            raise ValueError("domain/source snapshot id mismatch")
        if self.domain_snapshot.market_snapshot_hash != self.source_snapshot_hash:
            raise ValueError("domain/source snapshot hash mismatch")
        if any(not blocker.strip() for blocker in self.blockers):
            raise ValueError("runtime blockers cannot be blank")

    @property
    def publication_allowed(self) -> bool:
        return False
