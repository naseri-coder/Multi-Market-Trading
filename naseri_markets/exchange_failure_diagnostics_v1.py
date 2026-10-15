"""Inert, bounded diagnostics for explicitly supplied exchange error evidence.

No network access, credential handling, order placement, retries or persistence.
The outcome is advisory and MUST NOT be interpreted as execution permission.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class FailureKind(StrEnum):
    AUTHENTICATION = "authentication"
    CLOCK = "clock"
    RATE_LIMIT = "rate_limit"
    SYMBOL = "invalid_symbol"
    QUANTITY = "invalid_quantity"
    FUNDS = "insufficient_funds"
    POSITION = "position_conflict"
    PRICE_BAND = "price_band"
    VENUE_UNAVAILABLE = "venue_unavailable"
    TRANSPORT_UNKNOWN = "transport_unknown"
    UNCLASSIFIED = "unclassified"


class OperatorAction(StrEnum):
    STOP_AND_REVIEW = "stop_and_review"
    CHECK_CONFIGURATION = "check_configuration"
    WAIT_AND_INSPECT = "wait_and_inspect"
    RECONCILE_BEFORE_ANY_RETRY = "reconcile_before_any_retry"


@dataclass(frozen=True, slots=True)
class FailureDiagnosis:
    venue: str
    category: FailureKind
    action: OperatorAction
    evidence: str  # Stable reason tag; never the original message or code.


# Deliberately small exact-match, venue-scoped table; expand only with fixture evidence.
# Values are diagnostic categories, not an authorization to re-submit an order.
_EXACT_CODES: dict[tuple[str, str], FailureKind] = {
    ("binance", "-1021"): FailureKind.CLOCK,
    ("binance", "-1022"): FailureKind.AUTHENTICATION,
    ("binance", "-2015"): FailureKind.AUTHENTICATION,
    ("binance", "-1003"): FailureKind.RATE_LIMIT,
    ("binance", "-1121"): FailureKind.SYMBOL,
    ("binance", "-1013"): FailureKind.QUANTITY,
    ("binance", "-1111"): FailureKind.QUANTITY,
    ("binance", "-2019"): FailureKind.FUNDS,
    ("binance", "-2022"): FailureKind.POSITION,
    ("binance", "-4016"): FailureKind.PRICE_BAND,
    ("okx", "50102"): FailureKind.CLOCK,
    ("okx", "50105"): FailureKind.AUTHENTICATION,
    ("okx", "50011"): FailureKind.RATE_LIMIT,
    ("okx", "51008"): FailureKind.FUNDS,
    ("okx", "51010"): FailureKind.POSITION,
    ("bybit", "10002"): FailureKind.CLOCK,
    ("bybit", "10004"): FailureKind.AUTHENTICATION,
    ("bybit", "10006"): FailureKind.RATE_LIMIT,
    ("bybit", "110007"): FailureKind.FUNDS,
    ("bybit", "110017"): FailureKind.POSITION,
    ("bitget", "40009"): FailureKind.AUTHENTICATION,
    ("bitget", "40018"): FailureKind.AUTHENTICATION,
}

# Only short, high-signal phrases; message text is never exposed or logged.
_PHRASES: tuple[tuple[str, FailureKind], ...] = (
    ("invalid api key", FailureKind.AUTHENTICATION),
    ("invalid signature", FailureKind.AUTHENTICATION),
    ("timestamp outside recvwindow", FailureKind.CLOCK),
    ("too many requests", FailureKind.RATE_LIMIT),
    ("rate limit exceeded", FailureKind.RATE_LIMIT),
    ("insufficient margin", FailureKind.FUNDS),
    ("insufficient balance", FailureKind.FUNDS),
    ("invalid symbol", FailureKind.SYMBOL),
    ("filter failure: lot_size", FailureKind.QUANTITY),
    ("filter failure: min_notional", FailureKind.QUANTITY),
    ("reduce-only order is rejected", FailureKind.POSITION),
    ("outside the price band", FailureKind.PRICE_BAND),
)

_ACTIONS = {
    FailureKind.AUTHENTICATION: OperatorAction.CHECK_CONFIGURATION,
    FailureKind.CLOCK: OperatorAction.CHECK_CONFIGURATION,
    FailureKind.RATE_LIMIT: OperatorAction.WAIT_AND_INSPECT,
    FailureKind.SYMBOL: OperatorAction.CHECK_CONFIGURATION,
    FailureKind.QUANTITY: OperatorAction.CHECK_CONFIGURATION,
    FailureKind.FUNDS: OperatorAction.STOP_AND_REVIEW,
    FailureKind.POSITION: OperatorAction.STOP_AND_REVIEW,
    FailureKind.PRICE_BAND: OperatorAction.STOP_AND_REVIEW,
    FailureKind.VENUE_UNAVAILABLE: OperatorAction.WAIT_AND_INSPECT,
    FailureKind.TRANSPORT_UNKNOWN: OperatorAction.RECONCILE_BEFORE_ANY_RETRY,
    FailureKind.UNCLASSIFIED: OperatorAction.STOP_AND_REVIEW,
}

_ALLOWED_VENUES = frozenset({
    "binance", "okx", "bybit", "bitget", "gate", "htx", "kraken", "kucoin", "mt5"
})
_SAFE_CODE = re.compile(r"-?[0-9]{1,9}\Z", flags=re.ASCII)


def diagnose_exchange_failure(
    *,
    venue: str,
    http_status: int | None = None,
    exchange_code: str | int | None = None,
    message: str | None = None,
    request_submitted: bool = True,
) -> FailureDiagnosis:
    """Classify untrusted error evidence without making any operational decision.

    request_submitted defaults to True: failures may be ambiguous after a
    network attempt. A confirmed pre-dispatch failure may set it to False.
    """
    if not isinstance(venue, str) or not isinstance(request_submitted, bool):
        raise ValueError("INVALID_ERROR_EVIDENCE")
    if http_status is not None and (
        type(http_status) is not int or not 100 <= http_status <= 599
    ):
        raise ValueError("INVALID_HTTP_STATUS")
    if exchange_code is not None and type(exchange_code) not in (str, int):
        raise ValueError("INVALID_EXCHANGE_CODE")
    if message is not None and type(message) is not str:
        raise ValueError("INVALID_ERROR_MESSAGE")

    normalized_venue = venue.strip().lower() if len(venue) <= 32 else "unknown"
    if normalized_venue not in _ALLOWED_VENUES:
        normalized_venue = "unknown"
    raw_code = (
        str(exchange_code)
        if type(exchange_code) is int and abs(exchange_code) <= 999_999_999
        else exchange_code if type(exchange_code) is str and len(exchange_code) <= 10
        else ""
    )
    code = raw_code if _SAFE_CODE.fullmatch(raw_code) else ""
    # Excessively large messages are not inspected, keeping parsing bounded.
    summary = (
        " ".join(message.lower().split())
        if message is not None and len(message) <= 2048
        else ""
    )

    def result(kind: FailureKind, evidence: str) -> FailureDiagnosis:
        return FailureDiagnosis(normalized_venue, kind, _ACTIONS[kind], evidence)

    if http_status in (401, 403):
        return result(FailureKind.AUTHENTICATION, "HTTP_ACCESS_DENIED")
    if http_status == 429:
        return result(FailureKind.RATE_LIMIT, "HTTP_RATE_LIMIT")
    # A 5xx gateway result after dispatch does not prove non-execution.
    if http_status is not None and http_status >= 500:
        kind = (FailureKind.TRANSPORT_UNKNOWN if request_submitted
                else FailureKind.VENUE_UNAVAILABLE)
        return result(kind, "HTTP_SERVER_FAILURE")
    if code and (kind := _EXACT_CODES.get((normalized_venue, code))) is not None:
        return result(kind, "VENUE_STRUCTURED_CODE")
    if any(marker in summary for marker in (
        "connection reset", "connection timed out", "read timeout", "gateway timeout"
    )):
        kind = (FailureKind.TRANSPORT_UNKNOWN if request_submitted
                else FailureKind.VENUE_UNAVAILABLE)
        return result(kind, "TRANSPORT_UNCERTAIN")
    for marker, kind in _PHRASES:
        if marker in summary:
            return result(kind, "KNOWN_MESSAGE_PATTERN")
    return result(FailureKind.UNCLASSIFIED, "NO_TRUSTED_CLASSIFICATION")
