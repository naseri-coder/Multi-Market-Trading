"""Bounded, fixture-only execution-fill evidence with explicit fee provenance.

No authenticated feeds, SDK imports, network, databases, state mutation, broker
orders, cost aggregation, currency conversion, or live execution authorization.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}\Z", re.ASCII)
_SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9_-]{1,39}\Z", re.ASCII)
_CCY = re.compile(r"[A-Z][A-Z0-9]{1,19}\Z", re.ASCII)
_DECIMAL = re.compile(r"-?(?:0|[1-9][0-9]{0,19})(?:\.[0-9]{1,18})?\Z", re.ASCII)
_MS = re.compile(r"[0-9]{13}\Z", re.ASCII)
_MAX_ROWS = 16
_MAX_FEES = 8
_MARKETS = {
    "binance": "usd_m_linear",
    "okx": "swap_contracts",
    "bybit": "linear",
    "bitget": "uta_usdt_futures",
}


class FillRefused(ValueError):
    """A fixed error code; never interpolate untrusted payload values."""


class QuantityUnit(StrEnum):
    BASE = "base_units"
    CONTRACTS = "contracts"


class FeeState(StrEnum):
    OBSERVED = "observed"
    PENDING = "pending"


class FeeDirection(StrEnum):
    CHARGE = "charge"
    REBATE = "rebate"


class FillRelation(StrEnum):
    DISTINCT = "distinct"
    DUPLICATE = "duplicate"
    CONFLICT = "conflict"


def _id(value: object, *, numeric: bool = False) -> str:
    if numeric and type(value) is int and 0 < value <= 2**63 - 1:
        return str(value)
    if type(value) is not str or not _ID.fullmatch(value) or value == "0":
        raise FillRefused("INVALID_EXECUTION_ID")
    return value


def _symbol(value: object) -> str:
    if type(value) is not str or not _SYMBOL.fullmatch(value):
        raise FillRefused("INVALID_SYMBOL")
    return value


def _number(value: object, *, positive: bool = False, signed: bool = False) -> Decimal:
    if type(value) is not str or not _DECIMAL.fullmatch(value):
        raise FillRefused("INVALID_EXECUTION_DECIMAL")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise FillRefused("INVALID_EXECUTION_DECIMAL") from exc
    if not number.is_finite() or (positive and number <= 0) or (
        not signed and number < 0
    ):
        raise FillRefused("INVALID_EXECUTION_DECIMAL")
    return number


def _ms_time(value: object) -> datetime:
    if type(value) is int and 946684800000 <= value < 4102444800000:
        number = value
    elif type(value) is str and _MS.fullmatch(value):
        number = int(value)
        if not 946684800000 <= number < 4102444800000:
            raise FillRefused("INVALID_EXECUTION_TIME")
    else:
        raise FillRefused("INVALID_EXECUTION_TIME")
    return datetime.fromtimestamp(number // 1000, tz=UTC) + timedelta(
        milliseconds=number % 1000
    )


def _mapping(value: object) -> Mapping:
    if type(value) is not dict:
        raise FillRefused("INVALID_EXECUTION_SHAPE")
    return value


def _rows(payload: Mapping, *, limit: int = _MAX_ROWS) -> list[Mapping]:
    data = payload.get("data")
    if type(data) is not list or not 1 <= len(data) <= limit:
        raise FillRefused("INVALID_EXECUTION_BATCH")
    return [_mapping(item) for item in data]


def _side(value: object) -> str:
    if type(value) is not str or value.lower() not in ("buy", "sell"):
        raise FillRefused("INVALID_EXECUTION_SIDE")
    return value.lower()


def _currency(value: object) -> str:
    if type(value) is not str or not _CCY.fullmatch(value):
        raise FillRefused("INVALID_FEE_CURRENCY")
    return value


@dataclass(frozen=True, slots=True)
class FeeEvidence:
    currency: str
    amount: Decimal
    direction: FeeDirection

    def __post_init__(self) -> None:
        _currency(self.currency)
        if type(self.amount) is not Decimal or not self.amount.is_finite():
            raise FillRefused("INVALID_FEE_AMOUNT")
        if self.amount < 0 or type(self.direction) is not FeeDirection:
            raise FillRefused("INVALID_FEE_AMOUNT")


@dataclass(frozen=True, slots=True)
class FillEvidence:
    account_scope: str
    venue: str
    market: str
    symbol: str
    order_id: str
    fill_id: str
    side: str
    price: Decimal
    quantity: Decimal
    quantity_unit: QuantityUnit
    occurred_at: datetime
    fee_state: FeeState
    fees: tuple[FeeEvidence, ...]
    maker: bool | None

    def __post_init__(self) -> None:
        _id(self.account_scope)
        if self.venue not in _MARKETS or self.market != _MARKETS[self.venue]:
            raise FillRefused("INVALID_MARKET_SCOPE")
        _symbol(self.symbol)
        _id(self.order_id)
        _id(self.fill_id)
        _side(self.side)
        if not all(type(x) is Decimal and x.is_finite() and x > 0
                   for x in (self.price, self.quantity)):
            raise FillRefused("INVALID_EXECUTION_DECIMAL")
        if type(self.quantity_unit) is not QuantityUnit:
            raise FillRefused("INVALID_QUANTITY_UNIT")
        if (self.quantity_unit is QuantityUnit.CONTRACTS) != (self.venue == "okx"):
            raise FillRefused("INVALID_QUANTITY_UNIT")
        if type(self.occurred_at) is not datetime or self.occurred_at.tzinfo is None:
            raise FillRefused("INVALID_EXECUTION_TIME")
        if self.occurred_at.utcoffset() is None:
            raise FillRefused("INVALID_EXECUTION_TIME")
        if type(self.fee_state) is not FeeState or type(self.fees) is not tuple:
            raise FillRefused("INVALID_FEE_EVIDENCE")
        if len(self.fees) > _MAX_FEES or any(type(x) is not FeeEvidence for x in self.fees):
            raise FillRefused("INVALID_FEE_EVIDENCE")
        if self.fee_state is FeeState.PENDING and self.fees:
            raise FillRefused("INVALID_FEE_EVIDENCE")
        if self.fee_state is FeeState.OBSERVED and not self.fees:
            raise FillRefused("INVALID_FEE_EVIDENCE")
        if self.maker is not None and type(self.maker) is not bool:
            raise FillRefused("INVALID_MAKER_FLAG")

    @property
    def identity(self) -> tuple[str, str, str, str, str, str]:
        return (
            self.account_scope, self.venue, self.market,
            self.symbol, self.order_id, self.fill_id,
        )


def _fee_one(amount: object, currency: object, *, signed_credit: bool) -> FeeEvidence:
    n = _number(amount, signed=signed_credit)
    # OKX: negative native fillFee = charge, positive = rebate.
    direction = (
        FeeDirection.REBATE if signed_credit and n > 0 else FeeDirection.CHARGE
    )
    return FeeEvidence(_currency(currency), abs(n), direction)


def _single_fee(
    amount: object, currency: object, *, signed_credit: bool = False,
) -> tuple[FeeState, tuple[FeeEvidence, ...]]:
    if amount in (None, "") and currency in (None, ""):
        return FeeState.PENDING, ()
    # Binance can report zero commission before an asset is assigned.
    if type(amount) is str and currency is None and _DECIMAL.fullmatch(amount):
        if _number(amount, signed=True) == 0:
            return FeeState.PENDING, ()
    if amount in (None, "") or currency in (None, ""):
        raise FillRefused("INCOMPLETE_FEE_EVIDENCE")
    return FeeState.OBSERVED, (_fee_one(amount, currency, signed_credit=signed_credit),)


def _fees_list(value: object) -> tuple[FeeState, tuple[FeeEvidence, ...]]:
    if value is None:
        return FeeState.PENDING, ()
    if type(value) is not list or len(value) > _MAX_FEES:
        raise FillRefused("INVALID_FEE_LIST")
    if not value:
        return FeeState.PENDING, ()
    fees: list[FeeEvidence] = []
    for entry in value:
        item = _mapping(entry)
        fees.append(_fee_one(item.get("fee"), item.get("feeCoin"), signed_credit=False))
    return FeeState.OBSERVED, tuple(fees)


def _new(
    *, account: str, venue: str, symbol: object, order: object, fill: object,
    side: object, quantity: object, price: object, at: object,
    fee_state: FeeState, fees: tuple[FeeEvidence, ...],
    maker: object = None, numeric_ids: bool = False,
) -> FillEvidence:
    if maker is not None and type(maker) is not bool:
        raise FillRefused("INVALID_MAKER_FLAG")
    return FillEvidence(
        account_scope=account, venue=venue, market=_MARKETS[venue],
        symbol=_symbol(symbol), order_id=_id(order, numeric=numeric_ids),
        fill_id=_id(fill, numeric=numeric_ids), side=_side(side),
        quantity=_number(quantity, positive=True),
        price=_number(price, positive=True),
        quantity_unit=(
            QuantityUnit.CONTRACTS if venue == "okx" else QuantityUnit.BASE
        ),
        occurred_at=_ms_time(at), fee_state=fee_state, fees=fees, maker=maker,
    )


def _binance(data: Mapping, account: str) -> tuple[FillEvidence, ...]:
    if data.get("e") != "ORDER_TRADE_UPDATE":
        raise FillRefused("UNSUPPORTED_EXECUTION_CHANNEL")
    event = _mapping(data.get("o"))
    if event.get("x") != "TRADE":
        raise FillRefused("NOT_A_TRADE_EXECUTION")
    quantity = _number(event.get("l"), positive=True)
    total = _number(event.get("z"))
    original = _number(event.get("q"), positive=True)
    if total < quantity or total > original:
        raise FillRefused("INCONSISTENT_CUMULATIVE_FILL")
    fees = _single_fee(event.get("n"), event.get("N"))
    return (_new(
        account=account, venue="binance", symbol=event.get("s"),
        order=event.get("i"), fill=event.get("t"), side=event.get("S"),
        quantity=event.get("l"), price=event.get("L"), at=event.get("T"),
        fee_state=fees[0], fees=fees[1], maker=event.get("m"),
        numeric_ids=True,
    ),)


def _okx(data: Mapping, account: str) -> tuple[FillEvidence, ...]:
    args = _mapping(data.get("arg"))
    if args.get("channel") != "orders":
        raise FillRefused("UNSUPPORTED_EXECUTION_CHANNEL")
    result: list[FillEvidence] = []
    for item in _rows(data):
        if item.get("instType") != "SWAP":
            raise FillRefused("UNSUPPORTED_MARKET_UNIT")
        fees = _single_fee(item.get("fillFee"), item.get("fillFeeCcy"),
                           signed_credit=True)
        result.append(_new(
            account=account, venue="okx", symbol=item.get("instId"),
            order=item.get("ordId"), fill=item.get("tradeId"), side=item.get("side"),
            quantity=item.get("fillSz"), price=item.get("fillPx"),
            at=item.get("fillTime"), fee_state=fees[0], fees=fees[1],
        ))
    return tuple(result)


def _bybit(data: Mapping, account: str) -> tuple[FillEvidence, ...]:
    if data.get("topic") != "execution.linear":
        raise FillRefused("UNSUPPORTED_EXECUTION_CHANNEL")
    result: list[FillEvidence] = []
    for item in _rows(data):
        if item.get("category") != "linear" or item.get("execType") != "Trade":
            raise FillRefused("UNSUPPORTED_EXECUTION_EVENT")
        fees = _single_fee(item.get("execFee"), item.get("feeCurrency"))
        extra = item.get("extraFees")
        if extra not in (None, []):
            state, components = _fees_list(extra)
            if state is FeeState.OBSERVED:
                if fees[0] is FeeState.PENDING:
                    raise FillRefused("INCOMPLETE_FEE_EVIDENCE")
                if len(fees[1]) + len(components) > _MAX_FEES:
                    raise FillRefused("INVALID_FEE_LIST")
                fees = FeeState.OBSERVED, fees[1] + components
        result.append(_new(
            account=account, venue="bybit", symbol=item.get("symbol"),
            order=item.get("orderId"), fill=item.get("execId"), side=item.get("side"),
            quantity=item.get("execQty"), price=item.get("execPrice"),
            at=item.get("execTime"), fee_state=fees[0], fees=fees[1],
            maker=item.get("isMaker"),
        ))
    return tuple(result)


def _bitget(data: Mapping, account: str) -> tuple[FillEvidence, ...]:
    args = _mapping(data.get("arg"))
    if (args.get("instType"), args.get("topic"), data.get("action")) != (
        "UTA", "fill", "snapshot",
    ):
        raise FillRefused("UNSUPPORTED_EXECUTION_CHANNEL")
    result: list[FillEvidence] = []
    for item in _rows(data):
        if item.get("category") != "usdt-futures":
            raise FillRefused("UNSUPPORTED_MARKET_UNIT")
        scope = item.get("tradeScope")
        if scope not in ("maker", "taker", None):
            raise FillRefused("INVALID_MAKER_FLAG")
        fees = _fees_list(item.get("feeDetail"))
        result.append(_new(
            account=account, venue="bitget", symbol=item.get("symbol"),
            order=item.get("orderId"), fill=item.get("execId"), side=item.get("side"),
            quantity=item.get("execQty"), price=item.get("execPrice"),
            at=item.get("execTime"), fee_state=fees[0], fees=fees[1],
            maker=None if scope is None else scope == "maker",
        ))
    return tuple(result)


_PARSERS = {
    "binance": _binance,
    "okx": _okx,
    "bybit": _bybit,
    "bitget": _bitget,
}


def parse_offline_execution_fixtures(
    venue: str, payload: Mapping, *, account_scope: str,
    expected_symbol: str, expected_order_id: str,
) -> tuple[FillEvidence, ...]:
    """Parse only operator-provided fixture objects; refuse an entire bad batch."""
    if type(venue) is not str or venue not in _PARSERS:
        raise FillRefused("UNSUPPORTED_EXECUTION_VENUE")
    _id(account_scope)
    _symbol(expected_symbol)
    _id(expected_order_id)
    values = _PARSERS[venue](_mapping(payload), account_scope)
    if len(values) > _MAX_ROWS:
        raise FillRefused("INVALID_EXECUTION_BATCH")
    seen: set[str] = set()
    for item in values:
        if item.symbol != expected_symbol or item.order_id != expected_order_id:
            raise FillRefused("EXECUTION_SCOPE_MISMATCH")
        if item.fill_id in seen:
            raise FillRefused("DUPLICATE_FILL_IN_BATCH")
        seen.add(item.fill_id)
    return values


def _canonical_number(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def fill_evidence_digest(value: FillEvidence) -> str:
    if type(value) is not FillEvidence:
        raise FillRefused("TYPED_FILL_REQUIRED")
    basis = {
        "identity": value.identity,
        "side": value.side,
        "price": _canonical_number(value.price),
        "quantity": _canonical_number(value.quantity),
        "unit": value.quantity_unit.value,
        "time": value.occurred_at.astimezone(UTC).isoformat(),
        "fees": sorted((
            fee.currency, _canonical_number(fee.amount), fee.direction.value
            for fee in value.fees
        )),
        "fee_state": value.fee_state.value,
        "maker": value.maker,
    }
    raw = json.dumps(basis, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compare_fill_evidence(left: FillEvidence, right: FillEvidence) -> FillRelation:
    """No persistence: an external durable ledger must enforce uniqueness."""
    if type(left) is not FillEvidence or type(right) is not FillEvidence:
        raise FillRefused("TYPED_FILL_REQUIRED")
    if left.identity != right.identity:
        return FillRelation.DISTINCT
    if fill_evidence_digest(left) == fill_evidence_digest(right):
        return FillRelation.DUPLICATE
    return FillRelation.CONFLICT
