"""Stage 6: operator-driven public futures and MT5 DEMO metadata adapters.

No background polling, strategy source, order_send, Telegram, secrets, live
CoreInput emission or admin-setting writes. Reuses vetted public metadata API.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Callable

from .contracts import Market
from .core_api_v1 import BidAskTick
from .instrument_registry_v1 import (
    CatalogRefused, InstrumentMetadata, ListingStatus, MetadataOrigin,
    ProviderSnapshot, _time,
)

VENUES = frozenset(("kraken", "kucoin"))


def _decimal(raw: object, field: str) -> Decimal:
    if type(raw) not in (str, int, float, Decimal) or type(raw) is bool:
        raise CatalogRefused(f"INVALID_{field}")
    if type(raw) is str and len(raw) > 64:
        raise CatalogRefused(f"INVALID_{field}")
    try:
        n = Decimal(str(raw))
    except InvalidOperation as exc:
        raise CatalogRefused(f"INVALID_{field}") from exc
    if not n.is_finite() or n <= 0:
        raise CatalogRefused(f"INVALID_{field}")
    return n


def futures_snapshot(venue: str, raw: bytes, *, observed_at: datetime) -> ProviderSnapshot:
    """Pure bytes-to-snapshot mapping via existing vetted futures parser."""
    if type(venue) is not str or venue not in VENUES:
        raise CatalogRefused("UNSUPPORTED_FUTURES_PROVIDER")
    from .public_futures_contracts import PublicContractsRefused, parse_public_contracts
    try:
        contracts = parse_public_contracts(venue, raw)
    except PublicContractsRefused as exc:
        raise CatalogRefused("INVALID_PUBLIC_CONTRACT_RESPONSE") from exc
    when = _time(observed_at)
    if not contracts:
        raise CatalogRefused("NO_PERPETUAL_CONTRACTS")
    entries = tuple(InstrumentMetadata(
        provider=f"{venue}_futures", market=Market.CRYPTO,
        symbol=c.symbol, timezone="UTC", quote_currency=c.quote_currency,
        price_tick_size=_decimal(c.tick_size, "PRICE_TICK"),
        origin=MetadataOrigin.PUBLIC_CONTRACT_RESEARCH,
        listing_status=ListingStatus.OPEN if c.exchange_tradeable else ListingStatus.HALTED,
        observed_at=when, contract_kind=c.contract_kind,
        # Existing parser has no independently verified contract size or lot step.
        quantity_step=None, contract_multiplier=None,
    ) for c in contracts)
    return ProviderSnapshot(f"{venue}_futures", MetadataOrigin.PUBLIC_CONTRACT_RESEARCH,
                            when, entries, hashlib.sha256(raw).hexdigest())


def discover_public_futures(
    venue: str, *, observed_at: datetime, acknowledge_research: bool = False,
    transport: Callable[[str], bytes] | None = None,
) -> ProviderSnapshot:
    """Opt-in PUBLIC read-only research via existing fixed official GET URLs."""
    if (acknowledge_research is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        raise CatalogRefused("EXPLICIT_NONPRODUCTION_RESEARCH_REQUIRED")
    if type(venue) is not str or venue not in VENUES:
        raise CatalogRefused("UNSUPPORTED_FUTURES_PROVIDER")
    from .public_futures_contracts import MAX_METADATA_BYTES, PublicContractsRefused, _download
    try:
        raw = _download(venue) if transport is None else transport(venue)
    except (PublicContractsRefused, OSError, ValueError) as exc:
        raise CatalogRefused("PUBLIC_PROVIDER_UNAVAILABLE") from exc
    if type(raw) is not bytes or not 0 < len(raw) <= MAX_METADATA_BYTES:
        raise CatalogRefused("PUBLIC_PROVIDER_RESPONSE_BOUNDS")
    return futures_snapshot(venue, raw, observed_at=observed_at)


def _info(info: object, name: str) -> object:
    if isinstance(info, dict):
        return info.get(name)
    return getattr(info, name, None)


@dataclass(frozen=True, slots=True)
class DemoMarketObservation:
    metadata: InstrumentMetadata
    quote: BidAskTick
    account_mode: str = "DEMO_OBSERVATION_ONLY"
    authorized_to_trade: bool = False
    verified_live_feed: bool = False


def mt5_demo_observation(
    sdk: object, *, broker: str, symbol: str, now: datetime,
    operator_ack: bool = False, max_quote_age_seconds: int = 10,
) -> DemoMarketObservation:
    """Read-only calls on preconnected DEMO MT5; never initialize or order."""
    if (operator_ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        raise CatalogRefused("EXPLICIT_NONPRODUCTION_DEMO_REQUIRED")
    if type(broker) is not str or type(symbol) is not str:
        raise CatalogRefused("INVALID_BROKER_OR_SYMBOL")
    if type(max_quote_age_seconds) is not int or not 1 <= max_quote_age_seconds <= 120:
        raise CatalogRefused("INVALID_MAX_QUOTE_AGE")
    for method in ("account_info", "terminal_info", "symbol_info", "symbol_info_tick"):
        if not callable(getattr(sdk, method, None)):
            raise CatalogRefused("READONLY_SDK_INTERFACE_REQUIRED")
    demo_constant = getattr(sdk, "ACCOUNT_TRADE_MODE_DEMO", None)
    if type(demo_constant) is not int:
        raise CatalogRefused("MT5_DEMO_CONSTANT_UNAVAILABLE")
    try:
        account = sdk.account_info()
        terminal = sdk.terminal_info()
        if (account is None or type(_info(account, "trade_mode")) is not int
                or _info(account, "trade_mode") != demo_constant
                or terminal is None or _info(terminal, "connected") is not True):
            raise CatalogRefused("CONNECTED_DEMO_ACCOUNT_REQUIRED")
        details = sdk.symbol_info(symbol)
        tick = sdk.symbol_info_tick(symbol)
    except CatalogRefused:
        raise
    except Exception as exc:
        raise CatalogRefused("MT5_READONLY_PROVIDER_FAILURE") from exc
    if details is None or tick is None or _info(details, "name") != symbol:
        raise CatalogRefused("MT5_SYMBOL_UNAVAILABLE")
    stamp = _info(tick, "time_msc")
    if type(stamp) is not int or stamp <= 0:
        raise CatalogRefused("MT5_QUOTE_TIMESTAMP_INVALID")
    from datetime import UTC
    quote_time = datetime.fromtimestamp(stamp / 1000, tz=UTC)
    current = _time(now)
    if not timedelta(0) <= current - quote_time <= timedelta(seconds=max_quote_age_seconds):
        raise CatalogRefused("MT5_QUOTE_STALE_OR_FUTURE")
    bid = _decimal(_info(tick, "bid"), "BID")
    ask = _decimal(_info(tick, "ask"), "ASK")
    if bid > ask:
        raise CatalogRefused("MT5_CROSSED_QUOTE")
    q = BidAskTick(quote_time, bid, ask)
    point = _decimal(_info(details, "trade_tick_size"), "TICK_SIZE")
    step = _decimal(_info(details, "volume_step"), "VOLUME_STEP")
    multiplier = _decimal(_info(details, "trade_contract_size"), "CONTRACT_SIZE")
    quote_currency = _info(details, "currency_profit")
    base_currency = _info(details, "currency_base")
    if (type(quote_currency) is not str or type(base_currency) is not str
            or len(quote_currency) != 3 or len(base_currency) != 3
            or not quote_currency.isupper() or not base_currency.isupper()
            or not quote_currency.isalpha() or not base_currency.isalpha()
            or not symbol.upper().startswith(base_currency + quote_currency)):
        raise CatalogRefused("MT5_FOREX_IDENTITY_NOT_VERIFIED")
    status = ListingStatus.OPEN if _info(details, "visible") is True else ListingStatus.UNKNOWN
    record = InstrumentMetadata(
        provider=broker, market=Market.FOREX, symbol=symbol, timezone="UTC",
        quote_currency=quote_currency, price_tick_size=point,
        origin=MetadataOrigin.MT5_DEMO_OBSERVATION, listing_status=status,
        observed_at=current, contract_kind="BROKER_FX_SYMBOL", quantity_step=step,
        contract_multiplier=multiplier)
    return DemoMarketObservation(record, q)


__all__ = ["DemoMarketObservation", "discover_public_futures",
           "futures_snapshot", "mt5_demo_observation"]
