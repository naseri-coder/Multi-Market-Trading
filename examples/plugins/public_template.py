"""Example PUBLIC engine skeleton: no setup logic or implicit network access.

Copy into a separate approved public-plugin repository. A developer may
implement PAPER-only quote analysis without altering the main bot source.
"""
from __future__ import annotations

from naseri_markets.contracts import SignalIntent
from naseri_markets.quotes import QuoteTick


class PublicExampleEngine:
    engine_id = "public_demo"
    engine_version = "1.0.0"

    async def on_quote(self, tick: QuoteTick) -> tuple[SignalIntent, ...]:
        # Safe default: no strategy and no generated signals.
        return ()
