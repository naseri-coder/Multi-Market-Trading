"""Public illustrative two-setup OFFLINE core; not a profitable strategy.

No provider, symbol, account, risk, leverage, network, broker or Telegram SDK.
All market selection is supplied by the host-selected CoreBinding.
"""
from __future__ import annotations

from dataclasses import dataclass

from .contracts import Direction, Market
from .core_api_v1 import (
    ClosedCandle, CoreDecision, CoreEventType, CoreInput, CoreManifest,
    CoreResult, DecisionKind, ManagementAction, SetupSpec,
    content_digest,
)


@dataclass(frozen=True)
class DualSetupExampleCore:
    manifest: CoreManifest = CoreManifest(
        core_id="example.dual.setup",
        core_version="1.0.0",
        setups=(
            SetupSpec("close_above_previous_high", "Illustrative previous-high close", True),
            SetupSpec("close_below_previous_low", "Illustrative previous-low close", False),
        ),
        supported_markets=frozenset({Market.CRYPTO, Market.FOREX}),
        accepted_events=frozenset({CoreEventType.CLOSED_CANDLE, CoreEventType.POSITION_UPDATE}),
        minimum_closed_candles=2,
    )

    def evaluate(self, event: CoreInput) -> CoreResult:
        digest = event.input_digest
        decisions: list[CoreDecision] = []
        if event.event is CoreEventType.CLOSED_CANDLE:
            previous, latest = event.candles[-2:]
            if latest.close > previous.high and latest.low < latest.close:
                decisions.append(CoreDecision(
                    decision_id=self._id(event, "close_above_previous_high", "entry"),
                    kind=DecisionKind.ENTRY_INTENT,
                    setup_id="close_above_previous_high", direction=Direction.LONG,
                    entry=latest.close, stop=latest.low,
                    targets=(latest.close + (latest.close - latest.low),),
                    reason_codes=("CLOSE_ABOVE_PREV_HIGH",),
                ))
            elif (latest.close < previous.low and latest.high > latest.close and
                  latest.close * 2 > latest.high):
                decisions.append(CoreDecision(
                    decision_id=self._id(event, "close_below_previous_low", "entry"),
                    kind=DecisionKind.ENTRY_INTENT,
                    setup_id="close_below_previous_low", direction=Direction.SHORT,
                    entry=latest.close, stop=latest.high,
                    targets=(latest.close - (latest.high - latest.close),),
                    reason_codes=("CLOSE_BELOW_PREV_LOW",),
                ))
        elif event.event is CoreEventType.POSITION_UPDATE:
            position = event.position
            last: ClosedCandle = event.candles[-1]
            if (position.setup_id == "close_above_previous_high" and
                    position.direction is Direction.LONG and
                    position.current_stop < position.entry and
                    last.close >= position.entry + (position.entry - position.initial_stop)):
                decisions.append(CoreDecision(
                    decision_id=self._id(event, position.setup_id, "breakeven"),
                    kind=DecisionKind.MANAGEMENT_INTENT,
                    setup_id=position.setup_id,
                    action=ManagementAction.MOVE_STOP,
                    position_id=position.position_id,
                    expected_position_revision=position.revision,
                    new_stop=position.entry,
                    reason_codes=("BREAK_EVEN_AFTER_ONE_R",),
                ))
        if not decisions:
            decisions.append(CoreDecision(
                decision_id=self._id(event, "none", "no_setup"),
                kind=DecisionKind.NO_SETUP, reason_codes=("CONDITIONS_NOT_MET",),
            ))
        return CoreResult(
            core_id=self.manifest.core_id, core_version=self.manifest.core_version,
            instance_id=event.binding.instance_id, binding_id=event.binding.binding_id,
            observed_at=event.observed_at, input_digest=digest, decisions=tuple(decisions),
        )

    def _id(self, event: CoreInput, setup: str, action: str) -> str:
        return "d_" + content_digest((self.manifest.core_id, self.manifest.core_version,
                                      event.binding.instance_id, event.binding.binding_id,
                                      setup, action, event.input_digest))[:48]
