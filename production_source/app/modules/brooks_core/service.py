from app.modules.brooks_core.mapper import to_paper_candidate
from app.modules.brooks_core.protocols import BrooksCoreAnalyzer
from app.modules.market_data.protocols import MarketDataProvider
from app.modules.paper_runtime.entities import PaperSignalCandidate

class BrooksMarketAnalysisService:
    def __init__(self, *, provider: MarketDataProvider, analyzer: BrooksCoreAnalyzer) -> None:
        self.provider = provider
        self.analyzer = analyzer

    async def analyze_once(
        self,
        *,
        symbol: str,
        timeframe: str,
        limit: int,
        market_type: str,
    ) -> PaperSignalCandidate | None:
        snapshot = await self.provider.get_snapshot(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            market_type=market_type,
        )
        decision = await self.analyzer.analyze(snapshot)
        return to_paper_candidate(snapshot=snapshot, decision=decision)
