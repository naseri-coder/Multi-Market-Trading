"""Fixture-only contract tests: never contact a venue or submit an order."""
from __future__ import annotations

import pytest

from naseri_markets.exchange_failure_diagnostics_v1 import (
    FailureKind,
    OperatorAction,
    diagnose_exchange_failure,
)


@pytest.mark.parametrize(("venue", "code", "expected"), [
    ("binance", "-1021", FailureKind.CLOCK),
    ("binance", "-1022", FailureKind.AUTHENTICATION),
    ("binance", -1003, FailureKind.RATE_LIMIT),
    ("binance", "-1121", FailureKind.SYMBOL),
    ("binance", "-1013", FailureKind.QUANTITY),
    ("binance", "-2019", FailureKind.FUNDS),
    ("binance", "-2022", FailureKind.POSITION),
    ("binance", "-4016", FailureKind.PRICE_BAND),
    ("okx", "50102", FailureKind.CLOCK),
    ("okx", "50011", FailureKind.RATE_LIMIT),
    ("okx", "51008", FailureKind.FUNDS),
    ("bybit", "10004", FailureKind.AUTHENTICATION),
    ("bybit", "10006", FailureKind.RATE_LIMIT),
    ("bybit", "110007", FailureKind.FUNDS),
    ("bitget", "40009", FailureKind.AUTHENTICATION),
])
def test_exact_venue_code_mapping(venue, code, expected):
    diagnosis = diagnose_exchange_failure(venue=venue, exchange_code=code)
    assert diagnosis.category is expected
    assert diagnosis.evidence == "VENUE_STRUCTURED_CODE"


def test_same_code_never_implies_other_exchange():
    diagnosis = diagnose_exchange_failure(venue="okx", exchange_code="-1021")
    assert diagnosis.category is FailureKind.UNCLASSIFIED
    assert diagnosis.action is OperatorAction.STOP_AND_REVIEW


@pytest.mark.parametrize(("status", "category", "action"), [
    (401, FailureKind.AUTHENTICATION, OperatorAction.CHECK_CONFIGURATION),
    (403, FailureKind.AUTHENTICATION, OperatorAction.CHECK_CONFIGURATION),
    (429, FailureKind.RATE_LIMIT, OperatorAction.WAIT_AND_INSPECT),
    (500, FailureKind.TRANSPORT_UNKNOWN, OperatorAction.RECONCILE_BEFORE_ANY_RETRY),
    (502, FailureKind.TRANSPORT_UNKNOWN, OperatorAction.RECONCILE_BEFORE_ANY_RETRY),
    (503, FailureKind.TRANSPORT_UNKNOWN, OperatorAction.RECONCILE_BEFORE_ANY_RETRY),
])
def test_http_precedence(status, category, action):
    diagnosis = diagnose_exchange_failure(
        venue="binance", http_status=status, exchange_code="-1121"
    )
    assert (diagnosis.category, diagnosis.action) == (category, action)


def test_confirmed_pre_dispatch_server_failure_is_only_advisory_wait():
    result = diagnose_exchange_failure(venue="okx", http_status=503, request_submitted=False)
    assert result.category is FailureKind.VENUE_UNAVAILABLE
    assert result.action is OperatorAction.WAIT_AND_INSPECT


@pytest.mark.parametrize("text", ["connection reset by peer", "read timeout", "gateway timeout"])
def test_ambiguous_transport_must_reconcile(text):
    result = diagnose_exchange_failure(venue="bybit", message=text)
    assert result.action is OperatorAction.RECONCILE_BEFORE_ANY_RETRY


def test_secret_and_injected_fake_codes_never_escape_result():
    secret = "SECRET_API_KEY_ABCD_99999"
    msg = f"invalid signature key={secret} token={secret} code=50011"
    result = diagnose_exchange_failure(venue="okx", message=msg)
    assert result.category is FailureKind.AUTHENTICATION
    assert secret not in repr(result)
    assert secret not in str(result)
    assert "50011" not in repr(result)
    assert "invalid signature" not in repr(result)


def test_code_not_parsed_from_free_text():
    result = diagnose_exchange_failure(venue="okx", message="price 50011.42 in error log")
    assert result.category is FailureKind.UNCLASSIFIED


def test_unknown_and_malformed_codes_are_not_assumed_safe():
    for value in ("code=50011", "50011 extra", "۵۰۰۱۱", "99999999999"):
        result = diagnose_exchange_failure(venue="okx", exchange_code=value)
        assert result.category is FailureKind.UNCLASSIFIED
        assert result.action is OperatorAction.STOP_AND_REVIEW


def test_oversized_message_is_not_parsed_or_reflected():
    result = diagnose_exchange_failure(
        venue="unknown secret provider", message="invalid api key" * 2000
    )
    assert result.venue == "unknown"
    assert result.category is FailureKind.UNCLASSIFIED
    assert len(repr(result)) < 300


@pytest.mark.parametrize("payload", [
    {"http_status": True}, {"http_status": 0}, {"http_status": 600},
    {"exchange_code": True}, {"exchange_code": {}},
    {"message": ["invalid signature"]}, {"request_submitted": "False"},
    {"venue": None},
])
def test_malformed_input_fails_without_interpreting_as_failure(payload):
    with pytest.raises(ValueError):
        diagnose_exchange_failure(**{"venue": "binance", **payload})


def test_unknown_venue_not_echoed_into_logs_or_diagnostic():
    secret = "my_token_hidden"
    result = diagnose_exchange_failure(
        venue=secret, http_status=418, message="nonstandard response"
    )
    assert result.venue == "unknown"
    assert secret not in repr(result)
    assert result.action is OperatorAction.STOP_AND_REVIEW


def test_diagnostic_is_immutable_and_does_not_grant_retries():
    from dataclasses import FrozenInstanceError

    diagnosis = diagnose_exchange_failure(venue="binance", http_status=502)
    with pytest.raises(FrozenInstanceError):
        diagnosis.action = OperatorAction.WAIT_AND_INSPECT
    assert not hasattr(diagnosis, "retryable")
    assert not hasattr(diagnosis, "allowed")


def test_absurdly_large_integer_code_is_bounded():
    result = diagnose_exchange_failure(venue="bybit", exchange_code=10 ** 5000)
    assert result.category is FailureKind.UNCLASSIFIED


def test_large_venue_does_not_propagate():
    result = diagnose_exchange_failure(venue="secret" * 1000)
    assert result.venue == "unknown"
