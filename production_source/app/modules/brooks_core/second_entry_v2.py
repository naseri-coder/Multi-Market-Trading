"""Book-grounded causal H1/H2/L1/L2 recurrence engine.

WAVE_06 delegates recurrence and reset identity to correction_lifecycle so there is
one correction-episode source of truth. H2/L2 use Brooks relative-bar recurrence; a
fresh adverse extreme is not required.
"""
from __future__ import annotations

from app.modules.brooks_core.books_entities import BarCountEvent, BookSecondEntryAssessment, BookSecondEntrySetup
from app.modules.brooks_core.correction_lifecycle import classify_hl_recurrence
from app.modules.market_data.entities import Candle


def detect_book_second_entry(candles: tuple[Candle, ...], *, trend_direction: str, start_index: int) -> BookSecondEntryAssessment:
    if trend_direction not in {"BULL_TREND", "BEAR_TREND"}:
        return BookSecondEntryAssessment(None, "resolved bull/bear trend required")
    if start_index < 0 or start_index >= len(candles) - 2:
        return BookSecondEntryAssessment(None, "invalid pullback start index")
    recurrence = classify_hl_recurrence(candles, trend_direction=trend_direction, start_index=start_index)
    if recurrence is None:
        return BookSecondEntryAssessment(None, "no causal correction recurrence state")
    events = tuple(BarCountEvent(item.index, item.number, item.label) for item in recurrence.events)
    last = len(candles) - 1
    second = next((item for item in recurrence.events if item.number == 2), None)
    if second is not None and second.index == last:
        first = recurrence.events[0]
        setup = BookSecondEntrySetup(
            direction=recurrence.direction,
            setup_type="H2_CONFIRMED" if recurrence.direction == "LONG" else "L2_CONFIRMED",
            start_index=recurrence.episode_origin_index,
            signal_index=second.index,
            entry_number=2,
            first_entry_index=first.index,
            second_excursion_index=second.continuation_index,
            events=events,
        )
        return BookSecondEntryAssessment(setup, "same-episode H/L recurrence after source-valid correction continuation", events, 2)
    if second is not None and second.index < last:
        return BookSecondEntryAssessment(None, f"{second.label} occurred before final closed bar; no second-entry signal now", events, recurrence.highest_entry_number)
    reason = "no final-bar H2 in active correction episode" if recurrence.direction == "LONG" else "no final-bar L2 in active correction episode"
    return BookSecondEntryAssessment(None, reason, events, recurrence.highest_entry_number)
