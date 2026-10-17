"""One inert installed-wheel strategy smoke; never sends/executes orders.

Run only with explicit isolated-nonproduction flags. The integration fixture
is synthetic and does not prove a real-data feed, venue, Telegram or trader.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from importlib.metadata import PackageNotFoundError, version

from .contracts import Instrument, Market
from .core_api_v1 import ClosedCandle, CoreBinding, CoreEventType, DataOrigin, OfflineCoreHarness
from ._contract_acceptance_fixture_v1 import OfflineContractFixture
from .market_data_engine_v1 import (
    FeedDefinition, MarketPacket, OfflineMarketDataEngine, PriceBasis, VolumeSemantics,
)
from .platform_version_policy_v1 import require_offline_platform_version
from .strategy_orchestrator_v1 import (
    EvaluationStatus, OfflineStrategyOrchestrator, TrustedCoreEvaluator,
)


class PreviewSmokeRefused(ValueError):
    pass


def run_offline_preview() -> dict:
    """Synchronous, no network, DB, Telegram, credentials or external plugins."""
    try:
        release = version("multi-market-trading")
    except PackageNotFoundError as exc:
        raise PreviewSmokeRefused("INSTALLED_WHEEL_REQUIRED") from exc
    try:
        require_offline_platform_version(release)
    except ValueError as exc:
        raise PreviewSmokeRefused("RELEASE_VERSION_DRIFT") from exc
    core = OfflineContractFixture()
    instrument = Instrument(Market.CRYPTO, "offline_fixture", "ABCUSD", "UTC", "USD")
    binding = CoreBinding("demo_instance", "demo_binding", instrument, "15m")
    feed = FeedDefinition("demo_feed", instrument, "15m", CoreEventType.CLOSED_CANDLE,
                          DataOrigin.SYNTHETIC, "stage15_known_fixture", PriceBasis.TRADE,
                          VolumeSemantics.TRADED)
    market = OfflineMarketDataEngine(enabled=True)
    market.register_feed(feed)
    manager = OfflineStrategyOrchestrator(market, enabled=True)
    manager.attach(feed.feed_id, core.manifest, binding,
                   TrustedCoreEvaluator(OfflineCoreHarness(core, enabled=True), core.manifest))
    state = manager.state(binding.binding_id)
    manager.set_enabled(binding.binding_id, enabled=True,
                        expected_revision=state.revision, operator_ack=True)
    t = datetime(2026, 10, 12, 10, tzinfo=UTC)
    closes = (Decimal("100"), Decimal("106"))
    reports = []
    for i, close in enumerate(closes):
        start = t + timedelta(minutes=15*i)
        candle = ClosedCandle(start, start + timedelta(minutes=15), Decimal("100"),
                              Decimal("102") if i == 0 else Decimal("108"),
                              Decimal("98") if i == 0 else Decimal("99"),
                              close, Decimal("10"))
        reports.append(manager.ingest(MarketPacket(
            feed.feed_id, i + 1, candle.close_at + timedelta(seconds=1),
            feed.source_ref, candle=candle,
        )))
    if (len(reports[-1].outcomes) != 1 or
            reports[-1].outcomes[0].status is not EvaluationStatus.EVALUATED or
            not reports[-1].outcomes[0].actionable_decisions or
            reports[-1].telegram_sent or reports[-1].broker_order_sent):
        raise PreviewSmokeRefused("INERT_WHEEL_EVALUATION_FAILED")
    return {
        "schema_version": 1, "release": release,
        "scope": "ISOLATED_INSTALLED_WHEEL_SYNTHETIC_ONLY",
        "strategy_decision_validated": True,
        "telegram_sent": False, "broker_order_sent": False,
        "live_feed_verified": False, "external_plugin_executed": False,
        "product_release_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ack-isolated-preview", action="store_true")
    args = parser.parse_args(argv)
    if (not args.ack_isolated_preview or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        print("STAGE15_PREVIEW_REFUSED:NONPRODUCTION_ACK_REQUIRED", file=sys.stderr)
        return 2
    try:
        result = run_offline_preview()
    except (ValueError, TypeError) as exc:
        print(f"STAGE15_PREVIEW_REFUSED:{type(exc).__name__}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
