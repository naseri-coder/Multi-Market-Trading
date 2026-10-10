"""A7 explicitly enabled OFFLINE quote -> engine -> PAPER journal rehearsal.

Live quotes, Telegram publication and broker orders are not supported here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .paper_journal import PaperJournal
from .quotes import QuoteOrigin, QuoteTick, QuoteVerdict
from .runtime import MultiEngineRunner


@dataclass(frozen=True, slots=True)
class RehearsalResult:
    status: str
    quote_verdict: QuoteVerdict
    stored: int = 0
    duplicate: int = 0
    faulted_engines: tuple[str, ...] = ()


class A7ReplayPipeline:
    def __init__(
        self, runner: MultiEngineRunner, journal: PaperJournal,
        *, enabled: bool = False,
    ) -> None:
        self._runner = runner
        self._journal = journal
        self._enabled = enabled

    async def process(self, tick: QuoteTick, *, now: datetime) -> RehearsalResult:
        if tick.origin not in (QuoteOrigin.REPLAY, QuoteOrigin.SYNTHETIC):
            raise ValueError("A7_LIVE_TICK_REFUSED")
        if not self._enabled:
            return RehearsalResult("DISABLED", QuoteVerdict.UNVERIFIED)
        result = await self._runner.process(
            tick, now=now, trusted_live_source=False
        )
        if result.quote_verdict is not QuoteVerdict.ACCEPTED:
            return RehearsalResult("QUOTE_REJECTED", result.quote_verdict)
        signals = tuple(
            signal for batch in result.by_engine.values() for signal in batch
        )
        counts = self._journal.record_batch(signals)
        return RehearsalResult(
            "ENGINE_FAULTED" if result.faulted_engines else "RECORDED",
            result.quote_verdict, counts.inserted, counts.duplicate,
            result.faulted_engines,
        )
