from unittest.mock import AsyncMock
import pytest
from app.modules.brooks_core.entities import BrooksCoreDecision
from app.modules.brooks_core.service import BrooksMarketAnalysisService

@pytest.mark.asyncio
async def test_no_signal_is_valid_and_service_has_no_publisher_dependency():
    provider = AsyncMock()
    analyzer = AsyncMock()
    snapshot = AsyncMock()
    snapshot.snapshot_id = "s"
    snapshot.snapshot_hash = "h"
    provider.get_snapshot.return_value = snapshot
    analyzer.analyze.return_value = BrooksCoreDecision(
        decision="NO_SIGNAL",
        source_signal_id=None,
        entry_price=None,
        stop_loss=None,
        targets=(),
        setup_type=None,
        reasoning=(),
        rule_ids=(),
        failed_rules=(),
        rule_evidence=(),
        engine_version="v1",
        rule_set_version="r1",
        configuration_version="c1",
        market_snapshot_id="s",
        market_snapshot_hash="h",
        chart_path=None,
    )
    service = BrooksMarketAnalysisService(provider=provider, analyzer=analyzer)
    assert await service.analyze_once(
        symbol="BTCUSDT", timeframe="15m", limit=100, market_type="spot"
    ) is None
