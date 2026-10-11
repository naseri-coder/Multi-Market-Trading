"""PUBLIC metadata research; NEVER a residency permission or PAPER signal feed.

Only two audited official, fixed, unauthenticated futures instrument-list
URLs are supported. This module has no access to engine settings, SQLite,
Telegram, API keys, trading endpoints or order-placement functions.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from typing import Callable

from .iran_futures_eligibility import iran_futures_approved, review_status

PUBLIC_INSTRUMENT_ENDPOINTS = {
    "kraken": "https://futures.kraken.com/derivatives/api/v3/instruments",
    "kucoin": "https://api-futures.kucoin.com/api/v1/contracts/active",
}
MAX_METADATA_BYTES = 2 * 1024 * 1024
MAX_INSTRUMENTS = 4000
_SYMBOL = re.compile(r"[A-Z0-9_\-]{3,45}\Z")


class PublicContractsRefused(ValueError):
    """Fail closed if public metadata is malformed or unavailable."""


@dataclass(frozen=True, slots=True)
class FuturesContract:
    venue: str
    symbol: str
    quote_currency: str
    tick_size: str
    exchange_tradeable: bool
    contract_kind: str


def _positive_tick(value: object) -> str:
    if type(value) is bool or type(value) not in (str, int, float, Decimal):
        raise PublicContractsRefused("PUBLIC_CONTRACT_TICK_TYPE")
    try:
        decimal = Decimal(str(value))
    except InvalidOperation as exc:
        raise PublicContractsRefused("PUBLIC_CONTRACT_TICK_INVALID") from exc
    if (not decimal.is_finite() or decimal <= 0 or decimal > 100000
            or decimal.as_tuple().exponent < -12):
        raise PublicContractsRefused("PUBLIC_CONTRACT_TICK_INVALID")
    return str(decimal)


def _download(venue: str) -> bytes:
    if venue not in PUBLIC_INSTRUMENT_ENDPOINTS:
        raise PublicContractsRefused("PUBLIC_CONTRACT_VENUE_NOT_SUPPORTED")
    url = PUBLIC_INSTRUMENT_ENDPOINTS[venue]

    class RejectRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise PublicContractsRefused("PUBLIC_CONTRACT_REDIRECT_DENIED")

    # No proxy-based country circumvention, credentials, POST or redirects.
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}), RejectRedirect())
    request = urllib.request.Request(
        url, method="GET",
        headers={"Accept": "application/json",
                 "User-Agent": "MMT-public-metadata-research/0.1"})
    try:
        with opener.open(request, timeout=10) as response:
            if (response.status != 200 or response.geturl() != url
                    or not response.headers.get(
                        "Content-Type", "").lower().startswith("application/json")):
                raise PublicContractsRefused("PUBLIC_CONTRACT_HTTP_RESPONSE")
            data = response.read(MAX_METADATA_BYTES + 1)
    except PublicContractsRefused:
        raise
    except urllib.error.HTTPError as exc:
        raise PublicContractsRefused("PUBLIC_CONTRACT_HTTP_REFUSED") from exc
    except (OSError, ValueError) as exc:
        raise PublicContractsRefused("PUBLIC_CONTRACT_NETWORK_FAILED") from exc
    if not 0 < len(data) <= MAX_METADATA_BYTES:
        raise PublicContractsRefused("PUBLIC_CONTRACT_RESPONSE_BOUNDS")
    return data


def _json(raw: bytes) -> dict:
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_METADATA_BYTES:
        raise PublicContractsRefused("PUBLIC_CONTRACT_RESPONSE_BOUNDS")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise PublicContractsRefused("PUBLIC_CONTRACT_DUPLICATE_KEY")
            result[key] = value
        return result

    try:
        item = json.loads(raw, object_pairs_hook=unique,
                          parse_float=Decimal,
                          parse_constant=lambda x: (_ for _ in ()).throw(
                              ValueError("nonfinite")))
    except (ValueError, UnicodeError) as exc:
        raise PublicContractsRefused("PUBLIC_CONTRACT_JSON_INVALID") from exc
    if type(item) is not dict:
        raise PublicContractsRefused("PUBLIC_CONTRACT_JSON_SCHEMA")
    return item


def parse_public_contracts(venue: str, raw: bytes) -> tuple[FuturesContract, ...]:
    """Exchange-native symbol mapping, never infer from BTCUSDT candidates."""
    if venue not in PUBLIC_INSTRUMENT_ENDPOINTS:
        raise PublicContractsRefused("PUBLIC_CONTRACT_VENUE_NOT_SUPPORTED")
    payload = _json(raw)
    if venue == "kraken":
        if payload.get("result") != "success":
            raise PublicContractsRefused("PUBLIC_CONTRACT_RESULT_NOT_SUCCESS")
        rows = payload.get("instruments")
    else:
        if payload.get("code") != "200000":
            raise PublicContractsRefused("PUBLIC_CONTRACT_RESULT_NOT_SUCCESS")
        rows = payload.get("data")
    if type(rows) is not list or not 0 < len(rows) <= MAX_INSTRUMENTS:
        raise PublicContractsRefused("PUBLIC_CONTRACT_INSTRUMENTS_BOUNDS")
    contracts = []
    symbols = set()
    for row in rows:
        if type(row) is not dict:
            raise PublicContractsRefused("PUBLIC_CONTRACT_ITEM_SCHEMA")
        raw_symbol = row.get("symbol")
        if type(raw_symbol) is not str:
            raise PublicContractsRefused("PUBLIC_CONTRACT_SYMBOL_INVALID")
        symbol = raw_symbol.upper()
        if not _SYMBOL.fullmatch(symbol):
            raise PublicContractsRefused("PUBLIC_CONTRACT_SYMBOL_INVALID")
        if symbol in symbols:
            raise PublicContractsRefused("PUBLIC_CONTRACT_SYMBOL_DUPLICATE")
        symbols.add(symbol)
        if venue == "kraken":
            kind = row.get("type")
            if type(kind) is not str or len(kind) > 64:
                raise PublicContractsRefused("PUBLIC_CONTRACT_KIND_INVALID")
            # Official Kraken instruments endpoint includes other products;
            # explicitly select listed USD vanilla perpetual instruments.
            if not (symbol.startswith("PF_")
                    and symbol.endswith("USD")
                    and "futures" in kind.lower()):
                continue
            if type(row.get("tradeable")) is not bool:
                raise PublicContractsRefused("PUBLIC_CONTRACT_STATUS_INVALID")
            tradeable = row["tradeable"]
            tick = row.get("tickSize")
            quote = "USD"
            contract_kind = "USD_PERPETUAL"
        else:
            kind = row.get("type")
            if type(kind) is not str or not 0 < len(kind) <= 64:
                raise PublicContractsRefused("PUBLIC_CONTRACT_KIND_INVALID")
            quote = row.get("quoteCurrency")
            if (type(quote) is not str or not _SYMBOL.fullmatch(quote)
                    or len(quote) > 12):
                raise PublicContractsRefused("PUBLIC_CONTRACT_QUOTE_INVALID")
            if type(row.get("status")) is not str:
                raise PublicContractsRefused("PUBLIC_CONTRACT_STATUS_INVALID")
            tradeable = row["status"] == "Open"
            tick = row.get("tickSize")
            # KuCoin response contains BOTH dated and perpetual futures.
            # Absence of expiry metadata is not proof of a perpetual.
            if "expireDate" not in row:
                raise PublicContractsRefused("PUBLIC_CONTRACT_EXPIRY_UNKNOWN")
            if row["expireDate"] is not None:
                continue
            contract_kind = "PERPETUAL"
        contracts.append(FuturesContract(
            venue=venue, symbol=symbol, quote_currency=quote,
            tick_size=_positive_tick(tick), exchange_tradeable=tradeable,
            contract_kind=contract_kind))
    return tuple(sorted(contracts, key=lambda c: c.symbol))


def discover_public_contracts(
    venue: str, *, max_results: int = 100,
    transport: Callable[[str], bytes] | None = None,
) -> dict:
    """Research-only contract snapshot. No HTTP without explicit caller action."""
    if (type(venue) is not str or venue not in PUBLIC_INSTRUMENT_ENDPOINTS
            or type(max_results) is not int or not 1 <= max_results <= 500):
        raise PublicContractsRefused("PUBLIC_CONTRACT_REQUEST_INVALID")
    raw = (_download(venue) if transport is None else transport(venue))
    contracts = parse_public_contracts(venue, raw)
    # Kept separate: 'tradeable' in remote API means exchange product is open;
    # it does not mean the operator is allowed to open a futures account.
    eligible = iran_futures_approved(venue)
    return {
        "mode": "PUBLIC_FUTURES_METADATA_RESEARCH_ONLY",
        "venue": venue,
        "api_source": PUBLIC_INSTRUMENT_ENDPOINTS[venue],
        "policy": review_status(venue),
        "iran_resident_futures_approved": eligible,
        "account_trading_authorized": False,
        "paper_signal_generation_authorized": False,
        "telegram_publication_authorized": False,
        "market_orders_authorized": False,
        "contract_count": len(contracts),
        "truncated": len(contracts) > max_results,
        "contracts": [asdict(c) for c in contracts[:max_results]],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--venue", choices=sorted(PUBLIC_INSTRUMENT_ENDPOINTS),
                        required=True)
    parser.add_argument("--max-results", type=int, default=100)
    parser.add_argument("--ack-public-metadata-research", action="store_true")
    args = parser.parse_args(argv)
    if (not args.ack_public_metadata_research
            or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        print("PUBLIC_CONTRACTS_REFUSED:NONPRODUCTION_ACK_REQUIRED", file=sys.stderr)
        return 2
    try:
        result = discover_public_contracts(
            args.venue, max_results=args.max_results)
    except (PublicContractsRefused, ValueError, OSError):
        print("PUBLIC_CONTRACTS_REFUSED:FAIL_CLOSED", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
