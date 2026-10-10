"""Explicit derivatives pair selection; no implied unverified listing or Iran eligibility.

Only Kraken PF_XBTUSD/PF_ETHUSD/PF_SOLUSD are backed by documented
linear USD perpetual contracts and public instrument metadata. All other
venue options are exploratory, non-executable pair candidates.
"""
from __future__ import annotations

from .futures_venues import VENUE_BY_KEY

KRAKEN_PAIRS = ("PF_XBTUSD", "PF_ETHUSD", "PF_SOLUSD")
CATALOG_CANDIDATES = (
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT",
)
PAIR_SOURCES = {
    "kraken": "https://support.kraken.com/articles/4844359082772-linear-multi-collateral-derivatives-contract-specifications",
    "catalog": "https://coinmarketcap.com/rankings/exchanges/derivatives/",
}


def pair_choices(exchange: str) -> tuple[str, ...]:
    if type(exchange) is not str or exchange not in VENUE_BY_KEY:
        raise ValueError("BROOKS_PAIR_EXCHANGE_UNKNOWN")
    return KRAKEN_PAIRS if exchange == "kraken" else CATALOG_CANDIDATES


def initial_pair(exchange: str) -> str:
    return pair_choices(exchange)[0]


def pair_is_verified_paper(exchange: str, symbol: str) -> bool:
    return (exchange == "kraken" and type(symbol) is str
            and symbol in KRAKEN_PAIRS)


def require_pair(exchange: str, symbol: str) -> str:
    if type(symbol) is not str or symbol not in pair_choices(exchange):
        raise ValueError("BROOKS_PAIR_EXCHANGE_IDENTITY_MISMATCH")
    return symbol
