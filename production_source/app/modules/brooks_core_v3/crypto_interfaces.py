"""Ports for Brooks Core v3 Phase 2 crypto-specific context providers."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.modules.brooks_core_v3.crypto_adaptation_entities import (
    CryptoAdaptationAssessment,
    CryptoAdaptationInput,
    DerivativesObservation,
    LiquidityObservation,
)


class CryptoAdaptationEvaluator(Protocol):
    def evaluate(self, data: CryptoAdaptationInput) -> CryptoAdaptationAssessment: ...


class LiquidityObservationProvider(Protocol):
    async def get_liquidity_observation(
        self,
        *,
        exchange: str,
        market_type: str,
        symbol: str,
        captured_at: datetime,
    ) -> LiquidityObservation | None: ...


class DerivativesObservationProvider(Protocol):
    async def get_derivatives_observation(
        self,
        *,
        exchange: str,
        market_type: str,
        symbol: str,
        captured_at: datetime,
    ) -> DerivativesObservation | None: ...
