"""Legacy market compatibility isolated from primary Brooks production routing.

This module exists only to continue lifecycle management for archived Spot LIVE
records created before the Futures production cutover. New Brooks runtime/provider
selection must not depend on this module.
"""

from app.modules.market_data.binance import BinanceSpotMarketDataProvider


def build_legacy_spot_lifecycle_provider() -> BinanceSpotMarketDataProvider:
    """Create a Spot provider only for pre-existing legacy lifecycle records."""
    return BinanceSpotMarketDataProvider()
