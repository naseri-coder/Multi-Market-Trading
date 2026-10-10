"""Evidence-only Iranian-resident futures venue selector.

No venue is marked eligible merely because it is ranked on CMC, offers a
futures REST API, serves a public price feed, or omits Iran from a partial
restricted-territories list. Positive official assurance of Iranian-resident
futures service availability is required *in addition* to real futures/API.
This 2026-10-11 assessment has ZERO such confirmed exchanges.

Legacy sources remain internal for historic nonproduction PAPER tests; the
new Iranian-resident selector cannot route or authorize any of them.
"""
from __future__ import annotations

from dataclasses import dataclass

from .futures_venues import FUTURES_VENUES, FuturesVenue

RESEARCH_DATE = "2026-10-11"
RANKING_SOURCE = "https://coinmarketcap.com/rankings/exchanges/derivatives/"
RANKING_METRIC = "reported_24h_derivatives_volume_usd"

# Proof: official exchange terms, not third-party lists or influencers.
# Restricted means explicitly prohibited by its operator's published terms,
# including a prohibition via FATF high-risk jurisdictions in Toobit terms.
RESTRICTED_SOURCES: dict[str, str] = {
    "kraken": "https://support.kraken.com/articles/360023786632-kraken-derivatives-eligibility",
    "binance": "https://www.binance.com/en/terms",
    "okx": "https://www.okx.com/en-us/help/risk-compliance-disclosure",
    "bybit": "https://www.bybit.com/en/promo/campaign/trader-house",
    "gate": "https://www.gate.com/docs/Gate-User-Agreement.html",
    "bitget": "https://www.bitget.com/en-CA/support/articles/360014944032-terms-of-use",
    "mexc": "https://www.mexc.com/terms",
    "bingx": "https://bingx.com/en/support/articles/360034028153-0",
    "htx": "https://www.htx.com/support/ru-ru/detail/360000112261",
    "lbank": "https://www.lbank.com/support/articles/21436496711705/",
    "toobit": "https://www.toobit.com/en-US/support/toobit-terms-of-use",
    "bitunix": "https://www.bitunix.com/fr-fr/hub/helpcenter/article/bitunix-restricted-regions-and-user-eligibility-notice?id=146",
    "weex": "https://www.weex.com/help/articles/4417379529241",
    "blofin": "https://v3.blofin.com/en/support/Terms/7296238795279-TERMS-OF-USE",
    "phemex": "https://phemex.com/help-center/phemex-terms-of-use",
    "kcex": "https://www.kcex.io/en-US/support/articles/23962442522649",
    "coinex": "https://www.coinex.com/en/blog/14875-coinex-official-statement-regarding-the-wall-street-journal-report",
}
# No affirmative confirmation of futures access for Iranian residents:
REVIEW_SOURCES: dict[str, str] = {
    "kucoin": "https://www.kucoin.com/legal/terms-of-use",
    "xt": "https://www.xt.com/app",
    "btcc": "https://coinmarketcap.com/rankings/exchanges/derivatives/",
}
FATF_SOURCE = (
    "https://www.fatf-gafi.org/en/publications/"
    "High-risk-and-other-monitored-jurisdictions/call-for-action-june-2026.html"
)
assert set(RESTRICTED_SOURCES).isdisjoint(REVIEW_SOURCES)
assert set(RESTRICTED_SOURCES) | set(REVIEW_SOURCES) == {
    venue.key for venue in FUTURES_VENUES
}


@dataclass(frozen=True, slots=True)
class ApprovedVenue:
    key: str
    name: str
    official_iran_futures_eligibility_url: str
    official_futures_api_url: str
    volume_24h_usd: int
    volume_utc_date: str


# Important: DO NOT add a venue without official Iranian-resident trading
# eligibility proof and an independently verified public futures API.
# Neither a CFD-only approval nor a public OHLCV endpoint is sufficient.
VERIFIED_IRAN_FUTURES_VENUES: tuple[ApprovedVenue, ...] = ()


def ranked_iran_futures_venues() -> tuple[ApprovedVenue, ...]:
    """Actual eligible venues only, descending by comparable 24h volume."""
    return tuple(sorted(
        VERIFIED_IRAN_FUTURES_VENUES,
        key=lambda item: (-item.volume_24h_usd, item.key)))


def iran_futures_approved(exchange: str) -> bool:
    return (type(exchange) is str and any(
        item.key == exchange for item in VERIFIED_IRAN_FUTURES_VENUES))


def review_status(exchange: str) -> str:
    if exchange in RESTRICTED_SOURCES:
        return "RESTRICTED_OR_POLICY_BLOCKED"
    if exchange in REVIEW_SOURCES:
        return "ELIGIBILITY_UNVERIFIED"
    return "UNKNOWN_EXCHANGE"


def available_futures_venues() -> tuple[FuturesVenue, ...]:
    """Visibility filter: exclude explicitly restricted AND unverified."""
    approved = {item.key for item in ranked_iran_futures_venues()}
    return tuple(venue for venue in FUTURES_VENUES if venue.key in approved)
