"""No-network, no-order, fixed-fixture evidence tests for four futures adapters."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from naseri_markets.offline_fill_evidence_stage3_v1 import (
    FeeDirection,
    FeeState,
    FillRefused,
    FillRelation,
    QuantityUnit,
    compare_fill_evidence,
    fill_evidence_digest,
    parse_offline_execution_fixtures,
)

STAMP = 1750000000123


def binance():
    return {
        "e": "ORDER_TRADE_UPDATE",
        "o": {
            "x": "TRADE", "s": "BTCUSDT", "i": 123, "t": 9001,
            "S": "BUY", "l": "0.25", "L": "100.125", "z": "0.25",
            "q": "2", "T": STAMP, "n": "0.0015", "N": "USDT", "m": False,
        },
    }


def okx():
    return {"arg": {"channel": "orders"}, "data": [{
        "instType": "SWAP", "instId": "BTC-USDT-SWAP", "ordId": "123",
        "tradeId": "9001", "side": "buy", "fillSz": "2",
        "fillPx": "100.125", "fillTime": str(STAMP),
        "fillFee": "-0.0125", "fillFeeCcy": "USDT",
    }]}


def bybit():
    return {"topic": "execution.linear", "data": [{
        "category": "linear", "execType": "Trade", "symbol": "BTCUSDT",
        "orderId": "123", "execId": "9001", "side": "Buy",
        "execQty": "0.25", "execPrice": "100.125",
        "execTime": str(STAMP), "execFee": "0.0125",
        "feeCurrency": "USDT", "isMaker": False,
    }]}


def bitget():
    return {"arg": {"instType": "UTA", "topic": "fill"},
            "action": "snapshot", "data": [{
                "category": "usdt-futures", "symbol": "BTCUSDT",
                "orderId": "123", "execId": "9001", "side": "buy",
                "execQty": "0.25", "execPrice": "100.125",
                "execTime": str(STAMP), "tradeScope": "maker",
                "feeDetail": [{"feeCoin": "USDT", "fee": "0.0125"}],
            }]}


FIXTURES = (
    ("binance", binance, "BTCUSDT"),
    ("okx", okx, "BTC-USDT-SWAP"),
    ("bybit", bybit, "BTCUSDT"),
    ("bitget", bitget, "BTCUSDT"),
)


def inspect(venue, data, symbol, *, order="123", account="paper-account"):
    return parse_offline_execution_fixtures(
        venue, data, account_scope=account,
        expected_symbol=symbol, expected_order_id=order,
    )


@pytest.mark.parametrize(("venue", "factory", "symbol"), FIXTURES)
def test_four_market_data_contracts_are_explicit(venue, factory, symbol):
    result = inspect(venue, factory(), symbol)
    assert len(result) == 1
    fill = result[0]
    assert fill.venue == venue
    assert fill.symbol == symbol
    assert fill.order_id == "123"
    assert fill.fill_id == "9001"
    assert fill.account_scope == "paper-account"
    assert fill.side == "buy"
    assert fill.fee_state is FeeState.OBSERVED
    assert fill.occurred_at == datetime(2025, 6, 15, 15, 6, 40, 123000, tzinfo=UTC)
    assert fill.market != ""
    assert len(fill.fees) == 1
    assert not hasattr(fill, "execute")
    assert not hasattr(fill, "post_fill")
    assert not hasattr(fill, "retry")


@pytest.mark.parametrize(("venue", "factory", "symbol"), FIXTURES)
def test_no_cross_order_or_cross_account_inference(venue, factory, symbol):
    for order, account in (("other", "paper-account"), ("123", "")):
        with pytest.raises(FillRefused):
            inspect(venue, factory(), symbol, order=order, account=account)


def test_okx_uses_contracts_and_negative_fee_as_a_charge():
    result = inspect("okx", okx(), "BTC-USDT-SWAP")[0]
    assert result.quantity_unit is QuantityUnit.CONTRACTS
    assert result.quantity == Decimal("2")
    assert result.fees[0].amount == Decimal("0.0125")
    assert result.fees[0].direction is FeeDirection.CHARGE


def test_okx_positive_fee_is_rebate_not_a_negative_cost():
    data = okx()
    data["data"][0]["fillFee"] = "0.005"
    result = inspect("okx", data, "BTC-USDT-SWAP")[0]
    assert result.fees[0].direction is FeeDirection.REBATE
    assert result.fees[0].amount == Decimal("0.005")


@pytest.mark.parametrize(("venue", "factory", "symbol"), (
    FIXTURES[0], FIXTURES[2], FIXTURES[3],
))
def test_other_venue_quantities_are_base_units(venue, factory, symbol):
    assert inspect(venue, factory(), symbol)[0].quantity_unit is QuantityUnit.BASE


def test_bybit_extra_fee_components_keep_their_currencies():
    data = bybit()
    data["data"][0]["extraFees"] = [
        {"feeCoin": "INR", "fee": "0.11"},
        {"feeCoin": "USDT", "fee": "0.01"},
    ]
    result = inspect("bybit", data, "BTCUSDT")[0]
    assert [(f.currency, f.amount, f.direction) for f in result.fees] == [
        ("USDT", Decimal("0.0125"), FeeDirection.CHARGE),
        ("INR", Decimal("0.11"), FeeDirection.CHARGE),
        ("USDT", Decimal("0.01"), FeeDirection.CHARGE),
    ]


def test_bitget_multiple_fee_currencies_are_never_summed():
    data = bitget()
    data["data"][0]["feeDetail"] = [
        {"feeCoin": "USDT", "fee": "0.012"},
        {"feeCoin": "BGB", "fee": "0.03"},
    ]
    result = inspect("bitget", data, "BTCUSDT")[0]
    assert len(result.fees) == 2
    assert {x.currency for x in result.fees} == {"USDT", "BGB"}


@pytest.mark.parametrize(("venue", "factory", "symbol", "alter"), [
    ("binance", binance, "BTCUSDT", lambda x: x["o"].update({"n": "0", "N": None})),
    ("okx", okx, "BTC-USDT-SWAP",
     lambda x: x["data"][0].update({"fillFee": "", "fillFeeCcy": ""})),
    ("bybit", bybit, "BTCUSDT",
     lambda x: x["data"][0].update({"execFee": None, "feeCurrency": None})),
    ("bitget", bitget, "BTCUSDT",
     lambda x: x["data"][0].update({"feeDetail": []})),
])
def test_missing_fees_remain_pending_not_zero(venue, factory, symbol, alter):
    value = factory()
    alter(value)
    result = inspect(venue, value, symbol)[0]
    assert result.fee_state is FeeState.PENDING
    assert result.fees == ()


@pytest.mark.parametrize(("venue", "factory", "symbol", "alter"), [
    ("binance", binance, "BTCUSDT", lambda x: x["o"].update({"n": "0.1", "N": None})),
    ("okx", okx, "BTC-USDT-SWAP",
     lambda x: x["data"][0].update({"fillFee": "-0.01", "fillFeeCcy": ""})),
    ("bybit", bybit, "BTCUSDT",
     lambda x: x["data"][0].update({"execFee": "0.01", "feeCurrency": None})),
    ("bitget", bitget, "BTCUSDT",
     lambda x: x["data"][0].update({"feeDetail": [{"feeCoin": "", "fee": "1"}]})),
])
def test_incomplete_fee_components_refuse_entire_event(venue, factory, symbol, alter):
    value = factory()
    alter(value)
    with pytest.raises(FillRefused):
        inspect(venue, value, symbol)


@pytest.mark.parametrize("raw", [
    "NaN", "Infinity", "-Infinity", "1e5", "1E5", "000.2", "",
    "-1", "1234567890123456789012345", "0.1234567890123456789",
    0.25, None, True,
])
def test_invalid_execution_quantity_never_coerced(raw):
    payload = bybit()
    payload["data"][0]["execQty"] = raw
    with pytest.raises(FillRefused):
        inspect("bybit", payload, "BTCUSDT")


@pytest.mark.parametrize("raw", ["NaN", "inf", "1e3", "-0.01", 1.0, None])
def test_invalid_execution_price_refused(raw):
    payload = bitget()
    payload["data"][0]["execPrice"] = raw
    with pytest.raises(FillRefused):
        inspect("bitget", payload, "BTCUSDT")


@pytest.mark.parametrize("bad_time", [None, True, 1750000000, "1750000000",
                                      "NaN", 0, 5000000000000, 1750000000123.5])
def test_invalid_timestamp_must_not_fall_back_to_now(bad_time):
    payload = bybit()
    payload["data"][0]["execTime"] = bad_time
    with pytest.raises(FillRefused):
        inspect("bybit", payload, "BTCUSDT")


@pytest.mark.parametrize("field,value", [
    ("x", "NEW"), ("x", "AMENDMENT"), ("t", 0), ("z", "0.20"),
    ("z", "3"), ("q", "0.1"), ("S", "HOLD"),
])
def test_binance_nontrade_and_bad_fill_geometry_refused(field, value):
    data = binance()
    data["o"][field] = value
    with pytest.raises(FillRefused):
        inspect("binance", data, "BTCUSDT")


def test_unknown_venue_and_channel_refuse_before_parsing():
    with pytest.raises(FillRefused):
        inspect("unknown", binance(), "BTCUSDT")
    data = binance()
    data["e"] = "TRADE_LITE"
    with pytest.raises(FillRefused):
        inspect("binance", data, "BTCUSDT")


@pytest.mark.parametrize(("venue", "factory", "symbol", "path", "value"), [
    ("okx", okx, "BTC-USDT-SWAP", "channel", "fills"),
    ("bybit", bybit, "BTCUSDT", "topic", "execution.spot"),
    ("bitget", bitget, "BTCUSDT", "topic", "orders"),
])
def test_unsupported_channel_never_guessed(venue, factory, symbol, path, value):
    data = factory()
    if venue == "okx":
        data["arg"]["channel"] = value
    elif venue == "bybit":
        data["topic"] = value
    else:
        data["arg"]["topic"] = value
    with pytest.raises(FillRefused):
        inspect(venue, data, symbol)


@pytest.mark.parametrize(("venue", "factory", "symbol", "field", "value"), [
    ("okx", okx, "BTC-USDT-SWAP", "instType", "SPOT"),
    ("bybit", bybit, "BTCUSDT", "category", "spot"),
    ("bybit", bybit, "BTCUSDT", "execType", "Funding"),
    ("bitget", bitget, "BTCUSDT", "category", "coin-futures"),
])
def test_market_unit_changes_are_not_silently_converted(
    venue, factory, symbol, field, value,
):
    data = factory()
    data["data"][0][field] = value
    with pytest.raises(FillRefused):
        inspect(venue, data, symbol)


@pytest.mark.parametrize(("venue", "factory", "symbol"), FIXTURES[1:])
def test_duplicate_fill_id_in_same_batch_refuses_all(venue, factory, symbol):
    data = factory()
    data["data"].append(dict(data["data"][0]))
    with pytest.raises(FillRefused, match="DUPLICATE_FILL_IN_BATCH"):
        inspect(venue, data, symbol)


@pytest.mark.parametrize(("venue", "factory", "symbol"), FIXTURES[1:])
def test_oversized_batch_and_mixed_order_refuse_all(venue, factory, symbol):
    data = factory()
    data["data"] *= 17
    with pytest.raises(FillRefused):
        inspect(venue, data, symbol)
    data = factory()
    different = dict(data["data"][0])
    different["execId" if venue != "okx" else "tradeId"] = "9002"
    different["orderId" if venue != "okx" else "ordId"] = "different-order"
    data["data"].append(different)
    with pytest.raises(FillRefused, match="EXECUTION_SCOPE_MISMATCH"):
        inspect(venue, data, symbol)


def test_fee_differences_are_conflicts_for_same_fill_identity():
    p = bybit()
    original = inspect("bybit", p, "BTCUSDT")[0]
    replay = inspect("bybit", bybit(), "BTCUSDT")[0]
    assert compare_fill_evidence(original, replay) is FillRelation.DUPLICATE
    p["data"][0]["execFee"] = "0.0126"
    changed = inspect("bybit", p, "BTCUSDT")[0]
    assert compare_fill_evidence(original, changed) is FillRelation.CONFLICT
    assert fill_evidence_digest(original) != fill_evidence_digest(changed)


def test_same_fill_different_account_is_a_distinct_identity():
    one = inspect("binance", binance(), "BTCUSDT", account="account-a")[0]
    two = inspect("binance", binance(), "BTCUSDT", account="account-b")[0]
    assert compare_fill_evidence(one, two) is FillRelation.DISTINCT


def test_decimal_scale_is_not_a_false_conflict():
    a = inspect("binance", binance(), "BTCUSDT")[0]
    raw = binance()
    raw["o"]["l"], raw["o"]["L"] = "0.2500", "100.12500"
    raw["o"]["n"] = "0.001500"
    b = inspect("binance", raw, "BTCUSDT")[0]
    assert compare_fill_evidence(a, b) is FillRelation.DUPLICATE


def test_maker_flag_must_be_real_boolean():
    p = bybit()
    p["data"][0]["isMaker"] = "false"
    with pytest.raises(FillRefused):
        inspect("bybit", p, "BTCUSDT")
    p = binance()
    p["o"]["m"] = 0
    with pytest.raises(FillRefused):
        inspect("binance", p, "BTCUSDT")


def test_no_raw_payload_secrets_returned_or_in_errors():
    raw = bybit()
    secret = "VERY_PRIVATE_PROVIDER_ACCESS_TOKEN"
    raw["data"][0]["secretField"] = secret
    fill = inspect("bybit", raw, "BTCUSDT")[0]
    assert secret not in repr(fill)
    raw["data"][0]["execQty"] = secret
    with pytest.raises(FillRefused) as caught:
        inspect("bybit", raw, "BTCUSDT")
    assert secret not in str(caught.value)


def test_immutable_fill_and_fee_does_not_prove_booking():
    fill = inspect("bitget", bitget(), "BTCUSDT")[0]
    with pytest.raises(FrozenInstanceError):
        fill.quantity = Decimal("100")
    with pytest.raises(FrozenInstanceError):
        fill.fees[0].amount = Decimal("0")
    assert not hasattr(fill, "booked")
    assert not hasattr(fill, "order_state")
    assert not hasattr(fill, "send_order")
