"""Operator-requested futures research PRIORITY, not 24h-volume ranking.

This read-only catalog does not grant Iranian-resident account eligibility,
enable PAPER analysis, list validated runtime adapters or accept credentials.
A venue is shown even if prohibited, precisely to explain its status.
"""
from __future__ import annotations

from dataclasses import dataclass

from .iran_futures_eligibility import iran_futures_approved, review_status

RESEARCHED_AT = "2026-10-11"
RANKING_BASIS = "OPERATOR_PRIORITY_NOT_VERIFIED_VOLUME_RANK"


@dataclass(frozen=True, slots=True)
class ResearchVenue:
    priority: int
    key: str
    name: str
    futures_api_docs: str
    api_evidence: str


PRIORITY_FUTURES_RESEARCH: tuple[ResearchVenue, ...] = (
    ResearchVenue(1, "binance", "Binance Futures",
                  "https://developers.binance.com/docs/derivatives/usds-margined-futures/general-info",
                  "OFFICIAL_FUTURES_API_DOCUMENTED"),
    ResearchVenue(2, "bybit", "Bybit",
                  "https://bybit-exchange.github.io/docs/v5/intro",
                  "OFFICIAL_FUTURES_API_DOCUMENTED"),
    ResearchVenue(3, "mexc", "MEXC",
                  "https://www.mexc.io/api-docs/futures/integration-guide",
                  "OFFICIAL_FUTURES_API_DOCUMENTED"),
    ResearchVenue(4, "lbank", "LBank",
                  "https://www.lbank.com/en-US/docs/contract.html",
                  "OFFICIAL_FUTURES_API_DOCUMENTED"),
    ResearchVenue(5, "xt", "XT.COM",
                  "https://doc.xt.com/docs/futures/Access%20Description/BasicInformationOfTheInterface",
                  "OFFICIAL_FUTURES_API_DOCUMENTED"),
    ResearchVenue(6, "toobit", "Toobit",
                  "https://api-docs.toobit.com/api/usdt-m-market-data",
                  "OFFICIAL_FUTURES_API_DOCUMENTED"),
    ResearchVenue(7, "bitunix", "Bitunix",
                  "https://www.bitunix.com/api-docs/futures/common/introduction.html",
                  "OFFICIAL_FUTURES_API_DOCUMENTED"),
    ResearchVenue(8, "bigone", "BigONE",
                  "https://open.big.one/docs/contract/introduction/",
                  "OFFICIAL_FUTURES_API_DOCUMENTED"),
    ResearchVenue(9, "kcex", "KCEX",
                  "https://www.kcex.com/en-us/support/articles/30088664472729",
                  "FUTURES_MARKET_CONFIRMED_API_DOCUMENTATION_UNVERIFIED"),
)
assert tuple(x.priority for x in PRIORITY_FUTURES_RESEARCH) == tuple(range(1, 10))
assert len({x.key for x in PRIORITY_FUTURES_RESEARCH}) == 9


def operator_futures_research() -> tuple[dict, ...]:
    """Unchanging operator priority for display, NEVER an eligible list."""
    return tuple({
        "priority": venue.priority,
        "exchange": venue.key,
        "name": venue.name,
        "official_futures_reference": venue.futures_api_docs,
        "futures_api_evidence": venue.api_evidence,
        "iran_resident_eligibility": (
            "UNVERIFIED" if venue.key == "bigone"
            else review_status(venue.key)),
        "iran_resident_futures_approved": iran_futures_approved(venue.key),
        "paper_signal_authorized": False,
        "live_order_authorized": False,
        "operator_priority_not_volume_rank": True,
    } for venue in PRIORITY_FUTURES_RESEARCH)
