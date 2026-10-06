"""Pure, causal MARC R1 signal engine."""

from __future__ import annotations

import hashlib
from decimal import Decimal

from app.modules.market_data.entities import MarketSnapshot

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
from app.modules.marc_core.indicators import build_indicator_frames
from app.modules.marc_core.policy import MARCPolicy


def _directional_cross(
    previous: MARCIndicatorFrame,
    current: MARCIndicatorFrame,
) -> str | None:
    if (
        previous.ma7 is None
        or previous.ma25 is None
        or current.ma7 is None
        or current.ma25 is None
    ):
        return None
    if previous.ma7 <= previous.ma25 and current.ma7 > current.ma25:
        return "LONG"
    if previous.ma7 >= previous.ma25 and current.ma7 < current.ma25:
        return "SHORT"
    return None


def _cross_indices(frames: tuple[MARCIndicatorFrame, ...]) -> tuple[tuple[int, str], ...]:
    return tuple(
        (index, direction)
        for index in range(1, len(frames))
        if (direction := _directional_cross(frames[index - 1], frames[index]))
        is not None
    )


def _snapshot_reason(
    *,
    state: MARCState,
    direction: str | None,
    cross_index: int | None,
    confirmation_index: int | None,
) -> str:
    del confirmation_index
    if state == MARCState.LONG_READY:
        return "Bullish MA7/25 cross plus confirmed MA99 regime reclaim"
    if state == MARCState.SHORT_READY:
        return "Bearish MA7/25 cross plus confirmed MA99 regime breakdown"
    if state == MARCState.INVALIDATED_FALSE_BREAK:
        return "MA99 break failed across the opposite ATR band before persistence completed"
    if state == MARCState.NO_TRADE_CHOP:
        return "MA7/25 cross frequency exceeds the frozen chop filter"
    if state == MARCState.NO_TRADE_COMPRESSION:
        return "MA7/25/99 normalized spread is below the frozen compression threshold"
    if state == MARCState.NO_TRADE_OVEREXTENDED:
        return "Confirmation close is too far from MA99 in ATR units"
    if state == MARCState.SETUP_EXPIRED:
        return "MA99 persistence was not confirmed before the cross-validity deadline"
    if state == MARCState.PERSISTENCE_CONFIRMING:
        return "MA99 break has started but the required consecutive closes are incomplete"
    if state == MARCState.WAITING_FOR_MA99_RECLAIM:
        return "Bullish MA7/25 cross is valid; waiting for MA99 reclaim"
    if state == MARCState.WAITING_FOR_MA99_BREAKDOWN:
        return "Bearish MA7/25 cross is valid; waiting for MA99 breakdown"
    if state == MARCState.INSUFFICIENT_DATA:
        return "Insufficient closed candles for the MARC baseline indicators"
    if direction == "LONG":
        return f"Bullish MA7/25 cross detected at index {cross_index}"
    if direction == "SHORT":
        return f"Bearish MA7/25 cross detected at index {cross_index}"
    return "No current MARC R1 setup"


def evaluate_indicator_frames(
    frames: tuple[MARCIndicatorFrame, ...],
    *,
    symbol: str,
    timeframe: str,
    snapshot_id: str,
    snapshot_hash: str,
    policy: MARCPolicy | None = None,
) -> MARCDecision:
    """Evaluate MARC state from precomputed causal indicator frames."""
    selected = policy or MARCPolicy()
    validity = selected.cross_validity_bars(timeframe)

    latest = frames[-1] if frames else None

    def decision(
        state: MARCState,
        *,
        direction: str | None = None,
        cross_index: int | None = None,
        confirmation_index: int | None = None,
        persistence_count: int = 0,
        frame: MARCIndicatorFrame | None = None,
        spread: Decimal | None = None,
        extension: Decimal | None = None,
    ) -> MARCDecision:
        use_frame = frame or latest
        return MARCDecision(
            symbol=symbol,
            timeframe=timeframe,
            state=state,
            direction=direction,
            snapshot_id=snapshot_id,
            snapshot_hash=snapshot_hash,
            cross_index=cross_index,
            confirmation_index=confirmation_index,
            persistence_count=persistence_count,
            ma7=None if use_frame is None else use_frame.ma7,
            ma25=None if use_frame is None else use_frame.ma25,
            ma99=None if use_frame is None else use_frame.ma99,
            atr14=None if use_frame is None else use_frame.atr14,
            normalized_spread_atr=spread,
            extension_atr=extension,
            fresh=confirmation_index is not None and confirmation_index == len(frames) - 1,
            reason=_snapshot_reason(
                state=state,
                direction=direction,
                cross_index=cross_index,
                confirmation_index=confirmation_index,
            ),
        )

    if (
        not frames
        or latest is None
        or latest.ma99 is None
        or latest.atr14 is None
    ):
        return decision(MARCState.INSUFFICIENT_DATA)

    crosses = _cross_indices(frames)
    if not crosses:
        return decision(MARCState.NEUTRAL)

    cross_index, direction = crosses[-1]
    deadline = cross_index + validity
    scan_end = min(len(frames) - 1, deadline)

    persistence = 0
    first_qualifying_index: int | None = None
    confirmation_index: int | None = None

    for index in range(cross_index, scan_end + 1):
        frame = frames[index]
        if frame.ma99 is None or frame.atr14 is None:
            persistence = 0
            first_qualifying_index = None
            continue

        band = selected.ma99_band_atr * frame.atr14
        upper = frame.ma99 + band
        lower = frame.ma99 - band
        qualifies = frame.close > upper if direction == "LONG" else frame.close < lower

        if qualifies:
            if persistence == 0:
                first_qualifying_index = index
            persistence += 1
            if persistence >= selected.persistence_bars:
                confirmation_index = index
                break
            continue

        immediate_after_first = (
            persistence == 1
            and first_qualifying_index is not None
            and index == first_qualifying_index + 1
        )
        failed_opposite_band = (
            frame.close < lower if direction == "LONG" else frame.close > upper
        )
        if immediate_after_first and failed_opposite_band:
            return decision(
                MARCState.INVALIDATED_FALSE_BREAK,
                direction=direction,
                cross_index=cross_index,
                persistence_count=1,
                frame=frame,
            )

        persistence = 0
        first_qualifying_index = None

    if confirmation_index is None:
        if len(frames) - 1 > deadline:
            return decision(
                MARCState.SETUP_EXPIRED,
                direction=direction,
                cross_index=cross_index,
                persistence_count=persistence,
                frame=frames[scan_end],
            )
        if persistence:
            return decision(
                MARCState.PERSISTENCE_CONFIRMING,
                direction=direction,
                cross_index=cross_index,
                persistence_count=persistence,
            )
        state = (
            MARCState.WAITING_FOR_MA99_RECLAIM
            if direction == "LONG"
            else MARCState.WAITING_FOR_MA99_BREAKDOWN
        )
        return decision(
            state,
            direction=direction,
            cross_index=cross_index,
        )

    confirmation = frames[confirmation_index]
    assert confirmation.ma7 is not None
    assert confirmation.ma25 is not None
    assert confirmation.ma99 is not None
    assert confirmation.atr14 is not None

    chop_start = max(1, confirmation_index - selected.chop_lookback + 1)
    cross_count = sum(
        1
        for index in range(chop_start, confirmation_index + 1)
        if _directional_cross(frames[index - 1], frames[index]) is not None
    )
    if cross_count > selected.max_crosses_in_chop_window:
        return decision(
            MARCState.NO_TRADE_CHOP,
            direction=direction,
            cross_index=cross_index,
            confirmation_index=confirmation_index,
            persistence_count=selected.persistence_bars,
            frame=confirmation,
        )

    if confirmation.atr14 <= 0:
        return decision(
            MARCState.NO_TRADE_COMPRESSION,
            direction=direction,
            cross_index=cross_index,
            confirmation_index=confirmation_index,
            persistence_count=selected.persistence_bars,
            frame=confirmation,
            spread=Decimal("0"),
        )

    spread = (
        max(confirmation.ma7, confirmation.ma25, confirmation.ma99)
        - min(confirmation.ma7, confirmation.ma25, confirmation.ma99)
    ) / confirmation.atr14
    if spread < selected.compression_min_spread_atr:
        return decision(
            MARCState.NO_TRADE_COMPRESSION,
            direction=direction,
            cross_index=cross_index,
            confirmation_index=confirmation_index,
            persistence_count=selected.persistence_bars,
            frame=confirmation,
            spread=spread,
        )

    extension = abs(confirmation.close - confirmation.ma99) / confirmation.atr14
    if extension > selected.max_entry_extension_atr:
        return decision(
            MARCState.NO_TRADE_OVEREXTENDED,
            direction=direction,
            cross_index=cross_index,
            confirmation_index=confirmation_index,
            persistence_count=selected.persistence_bars,
            frame=confirmation,
            spread=spread,
            extension=extension,
        )

    state = MARCState.LONG_READY if direction == "LONG" else MARCState.SHORT_READY
    return decision(
        state,
        direction=direction,
        cross_index=cross_index,
        confirmation_index=confirmation_index,
        persistence_count=selected.persistence_bars,
        frame=confirmation,
        spread=spread,
        extension=extension,
    )


class MARCSignalEngine:
    """MARC R1 core. Pure analysis only; it never publishes or submits orders."""

    engine_id = "marc-ma-regime-core"
    engine_version = MARC_ENGINE_VERSION

    def __init__(self, *, policy: MARCPolicy | None = None) -> None:
        self.policy = policy or MARCPolicy()

    def evaluate(self, snapshot: MarketSnapshot) -> MARCDecision:
        self.policy.cross_validity_bars(snapshot.timeframe)
        frames = build_indicator_frames(snapshot, policy=self.policy)
        return evaluate_indicator_frames(
            frames,
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            snapshot_id=snapshot.snapshot_id,
            snapshot_hash=snapshot.snapshot_hash,
            policy=self.policy,
        )

    def build_entry_plan(
        self,
        snapshot: MarketSnapshot,
        decision: MARCDecision,
        *,
        entry_price: Decimal,
    ) -> MARCEntryPlan:
        """Build the next-bar-open plan from a fresh confirmed decision."""
        if not decision.trade_ready or not decision.fresh:
            return MARCEntryPlan(
                accepted=False,
                candidate=None,
                rejection_reason="DECISION_NOT_FRESH_AND_READY",
            )
        if decision.direction not in {"LONG", "SHORT"}:
            return MARCEntryPlan(
                accepted=False,
                candidate=None,
                rejection_reason="DIRECTION_UNAVAILABLE",
            )
        if decision.ma99 is None or decision.atr14 is None or decision.atr14 <= 0:
            return MARCEntryPlan(
                accepted=False,
                candidate=None,
                rejection_reason="VOLATILITY_UNAVAILABLE",
            )
        if len(snapshot.candles) < self.policy.structure_lookback:
            return MARCEntryPlan(
                accepted=False,
                candidate=None,
                rejection_reason="STRUCTURE_WINDOW_UNAVAILABLE",
            )

        actual_extension = abs(entry_price - decision.ma99) / decision.atr14
        if actual_extension > self.policy.max_entry_extension_atr:
            return MARCEntryPlan(
                accepted=False,
                candidate=None,
                rejection_reason="ENTRY_OVEREXTENDED",
            )

        structure = snapshot.candles[-self.policy.structure_lookback :]
        if decision.direction == "LONG":
            structural_stop = (
                min(candle.low for candle in structure)
                - self.policy.structure_buffer_atr * decision.atr14
            )
            ma_stop = decision.ma99 - self.policy.ma_stop_buffer_atr * decision.atr14
            stop = min(structural_stop, ma_stop)
            if stop >= entry_price:
                return MARCEntryPlan(
                    accepted=False,
                    candidate=None,
                    rejection_reason="INVALID_LONG_STOP_GEOMETRY",
                )
            risk = entry_price - stop
            targets = (
                entry_price + self.policy.tp1_r * risk,
                entry_price + self.policy.tp2_r * risk,
            )
        else:
            structural_stop = (
                max(candle.high for candle in structure)
                + self.policy.structure_buffer_atr * decision.atr14
            )
            ma_stop = decision.ma99 + self.policy.ma_stop_buffer_atr * decision.atr14
            stop = max(structural_stop, ma_stop)
            if stop <= entry_price:
                return MARCEntryPlan(
                    accepted=False,
                    candidate=None,
                    rejection_reason="INVALID_SHORT_STOP_GEOMETRY",
                )
            risk = stop - entry_price
            targets = (
                entry_price - self.policy.tp1_r * risk,
                entry_price - self.policy.tp2_r * risk,
            )

        risk_atr = risk / decision.atr14
        if risk_atr > self.policy.max_initial_risk_atr:
            return MARCEntryPlan(
                accepted=False,
                candidate=None,
                rejection_reason="MAX_INITIAL_RISK_ATR_EXCEEDED",
            )

        identity = "|".join(
            (
                "MARC",
                "R1",
                snapshot.symbol,
                snapshot.timeframe,
                decision.direction,
                snapshot.candles[-1].close_time.isoformat(),
            )
        ).encode()
        source_signal_id = "marc-r1-" + hashlib.sha256(identity).hexdigest()[:32]

        candidate = MARCCandidate(
            source_signal_id=source_signal_id,
            symbol=snapshot.symbol,
            timeframe=snapshot.timeframe,
            direction=decision.direction,
            entry_price=entry_price,
            stop_loss=stop,
            targets=targets,
            exchange=snapshot.exchange,
            market_type=snapshot.market_type,
            setup_type=MARC_SETUP_TYPE,
            market_snapshot_id=snapshot.snapshot_id,
            market_snapshot_hash=snapshot.snapshot_hash,
            engine_version=MARC_ENGINE_VERSION,
            rule_set_version=MARC_RULE_SET_VERSION,
            configuration_version=MARC_CONFIGURATION_VERSION,
            confirmation_close_time=snapshot.candles[-1].close_time,
            ma99=decision.ma99,
            atr14=decision.atr14,
            initial_risk_atr=risk_atr,
            risk_fraction=self.policy.risk_fraction,
            exit_model=MARC_EXIT_MODEL,
            reasoning=(
                "MA7 crossed MA25 in the trade direction",
                "MA99 regime boundary passed the ATR-normalized band",
                f"{self.policy.persistence_bars} consecutive confirmation closes completed",
                "chop, compression, overextension, and initial-risk gates passed",
            ),
        )
        return MARCEntryPlan(
            accepted=True,
            candidate=candidate,
            rejection_reason=None,
        )
