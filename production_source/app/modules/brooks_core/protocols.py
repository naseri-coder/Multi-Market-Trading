from typing import Protocol
from app.modules.brooks_core.entities import BrooksCoreDecision
from app.modules.market_data.entities import MarketSnapshot

class BrooksCoreAnalyzer(Protocol):
    async def analyze(self, snapshot: MarketSnapshot) -> BrooksCoreDecision: ...
