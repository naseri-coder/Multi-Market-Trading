"""Causal, read-only Phase 8 shadow replay service."""

from __future__ import annotations

from app.modules.brooks_core.engine_contract import ActualBrooksStrategyEngine
from app.modules.market_data.entities import (
    Candle,
    MarketSnapshot,
    validate_candle_sequence,
)
from app.modules.shadow_replay.entities import (
    ShadowObservation,
    ShadowReplayMetrics,
    ShadowReplayReport,
    classify_engine_result,
)


class ShadowReplaySafetyError(RuntimeError):
    """Raised when a Phase 8 evaluation attempts to become tradeable."""


class CausalShadowReplayService:
    def __init__(
        self,
        *,
        engine: ActualBrooksStrategyEngine,
        window_size: int = 100,
    ) -> None:
        if window_size < 20:
            raise ValueError("window_size must be at least 20")
        self.engine = engine
        self.window_size = window_size

    async def replay(
        self,
        *,
        exchange: str,
        market_type: str,
        symbol: str,
        timeframe: str,
        candles: tuple[Candle, ...],
    ) -> ShadowReplayReport:
        candles = validate_candle_sequence(candles, timeframe=timeframe)
        if len(candles) < self.window_size:
            raise ValueError("not enough candles for configured replay window")

        observations: list[ShadowObservation] = []

        for end_index in range(self.window_size - 1, len(candles)):
            first_index = end_index - self.window_size + 1
            window = candles[first_index : end_index + 1]
            captured_at = window[-1].close_time

            snapshot = MarketSnapshot(
                exchange=exchange,
                market_type=market_type,
                symbol=symbol.upper(),
                timeframe=timeframe,
                candles=window,
                captured_at=captured_at,
                source="SHADOW_REPLAY",
            )

            result = await self.engine.evaluate(snapshot)

            # Phase 8 is observation-only. A LONG/SHORT result would mean a caller
            # enabled execution policy and must be rejected rather than persisted,
            # published, or interpreted as an actionable signal.
            if result.decision != "NO_SIGNAL":
                raise ShadowReplaySafetyError(
                    "Phase 8 shadow replay requires non-tradeable NO_SIGNAL results"
                )

            observations.append(
                ShadowObservation(
                    sequence=len(observations) + 1,
                    snapshot_id=snapshot.snapshot_id,
                    snapshot_hash=snapshot.snapshot_hash,
                    captured_at=snapshot.captured_at,
                    window_first_open=window[0].open_time,
                    window_last_close=window[-1].close_time,
                    classification=classify_engine_result(result),
                    decision=result.decision,
                    setup_type=result.setup_type,
                    reasoning=result.reasoning,
                    rule_ids=result.rule_ids,
                    failed_rules=result.failed_rules,
                    engine_version=result.engine_version,
                    rule_set_version=result.rule_set_version,
                    configuration_version=result.configuration_version,
                )
            )

        frozen = tuple(observations)
        return ShadowReplayReport(
            exchange=exchange,
            market_type=market_type,
            symbol=symbol.upper(),
            timeframe=timeframe,
            window_size=self.window_size,
            source_candle_count=len(candles),
            observations=frozen,
            metrics=ShadowReplayMetrics.from_observations(frozen),
        )
