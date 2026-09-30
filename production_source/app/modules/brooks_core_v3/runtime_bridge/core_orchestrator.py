"""Fail-closed shadow orchestrator for Brooks Core v3 Phase 4.

This bridge deliberately stops at descriptive Foundation + Crypto Adaptation output.
It creates no Signal, entry/SL/TP, database row, chart file, or publication request.
"""

from __future__ import annotations

from app.modules.brooks_core_v3.crypto_adaptation import CryptoAdaptationEngine
from app.modules.brooks_core_v3.crypto_adaptation_entities import (
    CryptoAdaptationInput,
    DerivativesObservation,
    LiquidityObservation,
)
from app.modules.market_data.entities import MarketSnapshot

from .adapter import to_domain_snapshot
from .entities import RuntimeShadowResult


class BrooksCoreV3ShadowOrchestrator:
    def __init__(self, *, crypto_engine: CryptoAdaptationEngine | None = None) -> None:
        self.crypto_engine = crypto_engine or CryptoAdaptationEngine()

    def evaluate(
        self,
        snapshot: MarketSnapshot,
        *,
        higher_timeframe_snapshots: tuple[MarketSnapshot, ...] = (),
        liquidity: LiquidityObservation | None = None,
        derivatives: DerivativesObservation | None = None,
    ) -> RuntimeShadowResult:
        domain_snapshot = to_domain_snapshot(snapshot)
        crypto = self.crypto_engine.evaluate(
            CryptoAdaptationInput(
                primary_snapshot=snapshot,
                higher_timeframe_snapshots=higher_timeframe_snapshots,
                liquidity=liquidity,
                derivatives=derivatives,
            )
        )
        blockers = tuple(
            dict.fromkeys(
                (
                    *crypto.blockers,
                    "phase4_shadow_no_signal_generation",
                    "phase4_shadow_no_database_write",
                    "phase4_shadow_no_chart_render",
                    "phase4_shadow_no_publication",
                )
            )
        )
        state = crypto.foundation.market_state
        diagnostics = (
            ("symbol", snapshot.symbol),
            ("timeframe", snapshot.timeframe),
            ("regime", state.regime.value),
            ("always_in", state.always_in.value),
            ("volatility", crypto.volatility_state.value),
            ("relative_volume", crypto.relative_volume_state.value),
            ("mtf_alignment", crypto.mtf_alignment.value),
            ("input_fingerprint", crypto.input_fingerprint),
        )
        return RuntimeShadowResult(
            source_snapshot_id=snapshot.snapshot_id,
            source_snapshot_hash=snapshot.snapshot_hash,
            domain_snapshot=domain_snapshot,
            foundation=crypto.foundation,
            crypto=crypto,
            blockers=blockers,
            diagnostics=diagnostics,
        )
