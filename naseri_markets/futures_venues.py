"""Twenty public derivatives-market venues: DISCOVERY catalog, not 20 live feeds.

Listings and Iranian geographic eligibility MUST NOT be conflated.
Venue inclusion does not establish trust, legal permission or live runtime.
Evidence reviewed 2026-10-10: CMC derivatives venues / official policies.
"""
from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class FuturesVenue:
    key: str
    name: str
    iran_access: str
    feed_status: str
    product_status: str = "FUTURES_MARKET_LISTED"

# Iran access:
# EXPLICIT_RESTRICTION = official source names Iran, or official geo-fencing;
# UNVERIFIED = no current official proof of eligibility (NOT "Iran supported").
# Feed:
# VERIFIED_PUBLIC_PAPER = Kraken BTC/USD public market-data -> genuine Brooks;
# HTTP_BLOCKED = Binance USDM 451 observed in github Actions; may vary;
# CATALOG_ONLY = no validated feed mapping, no market data or signal publication.
FUTURES_VENUES: tuple[FuturesVenue, ...] = (
    FuturesVenue("kraken", "Kraken Futures", "EXPLICIT_RESTRICTION", "VERIFIED_PUBLIC_PAPER"),
    FuturesVenue("binance", "Binance Futures", "UNVERIFIED", "HTTP_BLOCKED"),
    FuturesVenue("okx", "OKX", "UNVERIFIED", "CATALOG_ONLY"),
    FuturesVenue("bybit", "Bybit", "UNVERIFIED", "CATALOG_ONLY"),
    FuturesVenue("gate", "Gate", "UNVERIFIED", "CATALOG_ONLY"),
    FuturesVenue("bitget", "Bitget", "UNVERIFIED", "CATALOG_ONLY"),
    FuturesVenue("mexc", "MEXC", "UNVERIFIED", "CATALOG_ONLY"),
    FuturesVenue("kucoin", "KuCoin", "UNVERIFIED", "CATALOG_ONLY"),
    FuturesVenue("bingx", "BingX", "UNVERIFIED", "CATALOG_ONLY"),
    FuturesVenue("xt", "XT.COM", "UNVERIFIED", "CATALOG_ONLY"),
    FuturesVenue("htx", "HTX", "UNVERIFIED", "CATALOG_ONLY"),
    FuturesVenue("lbank", "LBank", "UNVERIFIED", "CATALOG_ONLY"),
    FuturesVenue("toobit", "Toobit", "UNVERIFIED", "CATALOG_ONLY"),
    FuturesVenue("bitunix", "Bitunix", "EXPLICIT_RESTRICTION", "CATALOG_ONLY"),
    FuturesVenue("weex", "WEEX", "EXPLICIT_RESTRICTION", "CATALOG_ONLY"),
    FuturesVenue("blofin", "BloFin", "UNVERIFIED", "CATALOG_ONLY"),
    FuturesVenue("phemex", "Phemex", "UNVERIFIED", "CATALOG_ONLY"),
    FuturesVenue("kcex", "KCEX", "UNVERIFIED", "CATALOG_ONLY"),
    FuturesVenue("coinex", "CoinEx", "EXPLICIT_RESTRICTION", "CATALOG_ONLY"),
    FuturesVenue("btcc", "BTCC", "UNVERIFIED", "CATALOG_ONLY"),
)
VENUE_BY_KEY = {v.key: v for v in FUTURES_VENUES}
assert len(FUTURES_VENUES) == 20 and len(VENUE_BY_KEY) == 20

# Sources are documentation and operator verification context, never license
# to circumvent exchange country/KYC rules.
PROVENANCE = {
    "derivatives_market_list": "https://coinmarketcap.com/rankings/exchanges/derivatives/",
    "kraken_iran_restriction":
        "https://support.kraken.com/articles/360023786632-kraken-derivatives-eligibility",
    "weex_iran_restriction":
        "https://www.weex.com/help/articles/4417379529241",
    "coinex_iran_geofencing":
        "https://www.coinex.com/en/blog/14875-coinex-official-statement-regarding-the-wall-street-journal-report",
    "bitunix_iran_service_restriction":
        "https://www.bitunix.com/fr-fr/hub/helpcenter/article/bitunix-restricted-regions-and-user-eligibility-notice?id=146",
    "kraken_timeframes":
        "https://docs.kraken.com/api/docs/futures-api/charts/candles",
}


def get_venue(key: str) -> FuturesVenue:
    if type(key) is not str or key not in VENUE_BY_KEY:
        raise ValueError("BROOKS_FUTURES_EXCHANGE_UNKNOWN")
    return VENUE_BY_KEY[key]


def paper_feed_verified(key: str) -> bool:
    return get_venue(key).feed_status == "VERIFIED_PUBLIC_PAPER"


IRAN_LABELS = {
    "EXPLICIT_RESTRICTION": "⛔ محدودیت رسمی برای ایران",
    "UNVERIFIED": "⚪ وضعیت دسترسی ایران تأیید نشده",
}
FEED_LABELS = {
    "VERIFIED_PUBLIC_PAPER": "🧪 داده عمومی PAPER آزمایش‌شده",
    "HTTP_BLOCKED": "⛔ API فیوچرز در آزمون شبکه مسدود",
    "CATALOG_ONLY": "⚪ فقط در فهرست؛ اتصال تحلیل آماده نیست",
}


def iran_status_text(key: str) -> str:
    return IRAN_LABELS[get_venue(key).iran_access]


def feed_status_text(key: str) -> str:
    return FEED_LABELS[get_venue(key).feed_status]
