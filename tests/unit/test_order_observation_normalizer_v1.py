"""Deterministic, offline-only tests for order observation state normalization."""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from naseri_markets.execution_contract_v1 import OrderStatus
from naseri_markets.order_observation_normalizer_v1 import (
    ObservationReason,
    ObservationRefused,
    ObservationVerdict,
    OrderObservation,
    OrderProgress,
    assess_order_observation,
    normalize_native_order_status,
)

T0 = datetime(2026, 10, 15, 10, 0, tzinfo=UTC)
ONE = Decimal("1")


def initial(**changes) -> OrderProgress:
    defaults = {"venue": "binance", "order_id": "order-1", "requested_quantity": ONE}
    defaults.update(changes)
    return OrderProgress(**defaults)


def seen(status="NEW", *, quantity="0", event_id="event-1", at=T0,
         venue="binance", order_id="order-1") -> OrderObservation:
    return OrderObservation(
        venue=venue, order_id=order_id, event_id=event_id,
        native_status=status, cumulative_filled=Decimal(quantity), occurred_at=at,
    )


@pytest.mark.parametrize(("venue", "native", "expected"), [
    ("binance", "NEW", OrderStatus.ACKNOWLEDGED),
    ("binance", "PARTIALLY_FILLED", OrderStatus.PARTIALLY_FILLED),
    ("binance", "FILLED", OrderStatus.FILLED),
    ("binance", "CANCELED", OrderStatus.CANCELED),
    ("binance", "EXPIRED", OrderStatus.CANCELED),
    ("binance", "EXPIRED_IN_MATCH", OrderStatus.CANCELED),
    ("binance", "REJECTED", OrderStatus.REJECTED),
    ("okx", "live", OrderStatus.ACKNOWLEDGED),
    ("okx", "partially_filled", OrderStatus.PARTIALLY_FILLED),
    ("okx", "filled", OrderStatus.FILLED),
    ("okx", "canceled", OrderStatus.CANCELED),
    ("okx", "mmp_canceled", OrderStatus.CANCELED),
    ("bybit", "New", OrderStatus.ACKNOWLEDGED),
    ("bybit", "PartiallyFilled", OrderStatus.PARTIALLY_FILLED),
    ("bybit", "Filled", OrderStatus.FILLED),
    ("bybit", "Cancelled", OrderStatus.CANCELED),
    ("bybit", "PartiallyFilledCanceled", OrderStatus.CANCELED),
    ("bybit", "Rejected", OrderStatus.REJECTED),
    ("bitget", "live", OrderStatus.ACKNOWLEDGED),
    ("bitget", "partially_filled", OrderStatus.PARTIALLY_FILLED),
    ("bitget", "filled", OrderStatus.FILLED),
    ("bitget", "canceled", OrderStatus.CANCELED),
])
def test_supported_statuses_use_the_internal_order_contract(venue, native, expected):
    assert normalize_native_order_status(venue, native) is expected


@pytest.mark.parametrize(("venue", "native"), [
    ("binance", "PENDING_CANCEL"),
    ("binance", "PENDING_NEW"),
    ("okx", "triggered"),
    ("bybit", "Untriggered"),
    ("bybit", "Deactivated"),
    ("bybit", "Triggered"),
    ("bitget", "pending"),
    ("binance", "COMPLETE"),
    ("okx", "NEW"),
])
def test_unproven_provider_states_remain_unknown(venue, native):
    assert normalize_native_order_status(venue, native) is None


def test_event_only_advances_explicit_checkpoint_and_does_not_mutate_input():
    before = initial()
    receipt = assess_order_observation(before, seen())
    assert receipt.verdict is ObservationVerdict.APPLIED
    assert receipt.reason is ObservationReason.ACCEPTED
    assert receipt.progress.status is OrderStatus.ACKNOWLEDGED
    assert receipt.progress.cumulative_filled == 0
    assert receipt.progress is not before
    assert before.status is OrderStatus.CREATED
    assert len(receipt.progress.receipts) == 1


def test_partial_then_full_cumulative_fill_progression():
    ack = assess_order_observation(initial(), seen()).progress
    partial = assess_order_observation(
        ack, seen("PARTIALLY_FILLED", quantity="0.375", event_id="event-2",
                  at=T0 + timedelta(seconds=1)),
    )
    assert partial.verdict is ObservationVerdict.APPLIED
    assert partial.progress.status is OrderStatus.PARTIALLY_FILLED
    assert partial.progress.cumulative_filled == Decimal("0.375")
    full = assess_order_observation(
        partial.progress, seen("FILLED", quantity="1", event_id="event-3",
                               at=T0 + timedelta(seconds=2)),
    )
    assert full.verdict is ObservationVerdict.APPLIED
    assert full.progress.status is OrderStatus.FILLED
    assert full.progress.cumulative_filled == ONE
    assert len(full.progress.receipts) == 3


def test_direct_new_to_filled_without_intermediate_message():
    receipt = assess_order_observation(initial(), seen("FILLED", quantity="1"))
    assert receipt.verdict is ObservationVerdict.APPLIED
    assert receipt.progress.status is OrderStatus.FILLED


@pytest.mark.parametrize(("venue", "native"), [
    ("binance", "EXPIRED"), ("okx", "canceled"),
    ("bybit", "PartiallyFilledCanceled"),
])
def test_terminal_cancellation_keeps_partial_fill_without_claiming_fully_filled(venue, native):
    first = initial(venue=venue)
    message = seen(native, venue=venue, quantity="0.2")
    out = assess_order_observation(first, message)
    assert out.verdict is ObservationVerdict.APPLIED
    assert out.progress.status is OrderStatus.CANCELED
    assert out.progress.cumulative_filled == Decimal("0.2")


def test_exact_same_event_id_and_evidence_are_idempotent():
    event = seen()
    progressed = assess_order_observation(initial(), event).progress
    outcome = assess_order_observation(progressed, event)
    assert outcome.verdict is ObservationVerdict.DUPLICATE
    assert outcome.reason is ObservationReason.REPLAY
    assert outcome.progress is progressed
    assert len(outcome.progress.receipts) == 1


@pytest.mark.parametrize("new_event", [
    seen("FILLED", quantity="1"),
    seen("NEW", at=T0 + timedelta(seconds=1)),
    seen("NEW", quantity="0.1"),
])
def test_same_event_id_with_changed_semantics_is_quarantined(new_event):
    prior = assess_order_observation(initial(), seen()).progress
    result = assess_order_observation(prior, new_event)
    assert result.verdict is ObservationVerdict.QUARANTINED
    assert result.reason is ObservationReason.EVENT_ID_CONFLICT
    assert result.progress is prior


def test_decimal_scale_change_with_same_semantics_is_duplicate():
    prior = assess_order_observation(initial(), seen(quantity="0.00")).progress
    result = assess_order_observation(prior, seen(quantity="0.0000"))
    assert result.verdict is ObservationVerdict.DUPLICATE


@pytest.mark.parametrize("reason, event", [
    (ObservationReason.OUT_OF_ORDER, seen("FILLED", quantity="1",
                                          event_id="event-2", at=T0)),
    (ObservationReason.OUT_OF_ORDER, seen("FILLED", quantity="1",
                                          event_id="event-2", at=T0 - timedelta(seconds=1))),
    (ObservationReason.STATUS_QUANTITY_CONFLICT,
     seen("NEW", quantity="0.25", event_id="event-2",
          at=T0 + timedelta(seconds=1))),
    (ObservationReason.STATUS_QUANTITY_CONFLICT,
     seen("PARTIALLY_FILLED", quantity="0", event_id="event-2",
          at=T0 + timedelta(seconds=1))),
    (ObservationReason.STATUS_QUANTITY_CONFLICT,
     seen("FILLED", quantity="0.999", event_id="event-2",
          at=T0 + timedelta(seconds=1))),
    (ObservationReason.FILLED_EXCEEDS_ORDER,
     seen("FILLED", quantity="1.01", event_id="event-2",
          at=T0 + timedelta(seconds=1))),
])
def test_invalid_progress_never_changes_the_checkpoint(reason, event):
    prior = assess_order_observation(initial(), seen()).progress
    result = assess_order_observation(prior, event)
    assert result.verdict is ObservationVerdict.QUARANTINED
    assert result.reason is reason
    assert result.progress is prior


def test_quantity_regression_and_status_regression_quarantine():
    prior = assess_order_observation(
        initial(), seen("PARTIALLY_FILLED", quantity="0.5")
    ).progress
    reverted_amount = assess_order_observation(
        prior, seen("PARTIALLY_FILLED", quantity="0.25", event_id="event-2",
                    at=T0 + timedelta(seconds=1)),
    )
    reverted_state = assess_order_observation(
        prior, seen("NEW", quantity="0.5", event_id="event-2",
                    at=T0 + timedelta(seconds=1)),
    )
    assert reverted_amount.reason is ObservationReason.FILLED_REGRESSION
    assert reverted_state.reason is ObservationReason.STATUS_REGRESSION
    assert reverted_amount.progress is prior
    assert reverted_state.progress is prior


def test_partial_status_cannot_drop_to_acknowledged_even_with_zero_fill():
    prior = initial(status=OrderStatus.PARTIALLY_FILLED,
                    cumulative_filled=Decimal("0.4"), last_event_at=T0)
    event = seen("NEW", quantity="0", event_id="later", at=T0 + timedelta(seconds=1))
    result = assess_order_observation(prior, event)
    assert result.reason is ObservationReason.STATUS_REGRESSION


@pytest.mark.parametrize(("status", "quantity"), [
    ("FILLED", "1"), ("CANCELED", "0.2"), ("REJECTED", "0"),
])
def test_terminal_reopening_and_late_messages_require_review(status, quantity):
    prior = assess_order_observation(initial(), seen(status, quantity=quantity)).progress
    next_event = seen(status, quantity=quantity, event_id="different",
                      at=T0 + timedelta(seconds=1))
    result = assess_order_observation(prior, next_event)
    assert result.reason is ObservationReason.TERMINAL_REOPEN
    assert result.progress is prior


def test_identity_confusion_never_crosses_order_or_venue():
    prior = initial()
    for event in (seen(order_id="another"), seen(venue="okx", status="live")):
        result = assess_order_observation(prior, event)
        assert result.reason is ObservationReason.WRONG_ORDER
        assert result.progress is prior


def test_unknown_native_status_never_auto_cancels():
    before = initial()
    result = assess_order_observation(before, seen("impossible cancel pending"))
    assert result.reason is ObservationReason.UNKNOWN_NATIVE_STATUS
    assert result.progress is before


def test_receipt_capacity_requires_external_checkpoint_strategy():
    checkpoint = initial(
        last_event_at=T0,
        receipts=tuple((f"id-{i}", "a" * 64) for i in range(256)),
    )
    result = assess_order_observation(
        checkpoint, seen(event_id="event-new", at=T0 + timedelta(seconds=1)),
    )
    assert result.reason is ObservationReason.RECEIPT_CAPACITY
    assert result.progress is checkpoint


def test_normalized_timezones_share_identical_event_fingerprints():
    event = seen(at=T0)
    checkpoint = assess_order_observation(initial(), event).progress
    plus_two = timezone(timedelta(hours=2))
    equivalent = seen(at=T0.astimezone(plus_two))
    duplicate = assess_order_observation(checkpoint, equivalent)
    assert duplicate.verdict is ObservationVerdict.DUPLICATE


@pytest.mark.parametrize("bad", [
    Decimal("-1"), Decimal("NaN"), Decimal("Infinity"), "0", 0, True,
])
def test_invalid_decimal_input_fails_closed(bad):
    with pytest.raises(ObservationRefused):
        OrderObservation("binance", "order-1", "event-1", "FILLED", bad, T0)


@pytest.mark.parametrize("bad", [
    datetime(2026, 10, 15), "2026-10-15T10:00:00Z",
    datetime(1900, 1, 1, tzinfo=UTC),
])
def test_invalid_time_is_refused(bad):
    with pytest.raises(ObservationRefused):
        seen(at=bad)


@pytest.mark.parametrize("kwargs", [
    {"venue": "unknown"},
    {"venue": "BINANCE"},
    {"order_id": "order id"},
    {"event_id": ""},
    {"native_status": "X" * 49},
])
def test_untrusted_strings_cannot_change_contract(kwargs):
    with pytest.raises(ObservationRefused):
        seen(**kwargs)


def test_checkpoint_must_have_coherent_state_and_bounded_receipts():
    invalid = [
        {"status": OrderStatus.FILLED},
        {"status": OrderStatus.PARTIALLY_FILLED, "cumulative_filled": Decimal("0")},
        {"status": OrderStatus.REJECTED, "cumulative_filled": Decimal("0.1")},
        {"requested_quantity": Decimal("0")},
        {"receipts": (("event-1", "a" * 64),)},
        {"last_event_at": T0, "receipts": (("event-1", "a" * 64),) * 2},
        {"last_event_at": T0, "receipts": (("event-1", "x" * 64),)},
    ]
    for args in invalid:
        with pytest.raises(ObservationRefused):
            initial(**args)


def test_no_execution_authority_and_frozen_result():
    out = assess_order_observation(initial(), seen())
    assert not hasattr(out, "retry")
    assert not hasattr(out, "execute")
    assert not hasattr(out.progress, "post_fill")
    with pytest.raises(FrozenInstanceError):
        out.progress.cumulative_filled = Decimal("0.2")


def test_malicious_native_status_not_retained_in_result():
    secret = "CREDENTIAL_MARKER_SENSITIVE"
    event = seen(secret)
    result = assess_order_observation(initial(), event)
    assert result.verdict is ObservationVerdict.QUARANTINED
    assert secret not in repr(result)
    assert result.reason is ObservationReason.UNKNOWN_NATIVE_STATUS
