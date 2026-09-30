"""Variant-scoped economic origin semantics for the isolated H1E candidate."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.modules.signal_automation.entities import BrooksRuleEvidence, BrooksSignalImport

FIRST = datetime(2026, 9, 28, 0, 0, tzinfo=UTC)
SECOND = FIRST + timedelta(minutes=15)


def command(
    *, snapshot: str = "a", setup: str = "II_PENDING_PAIR",
    view: str = "PENDING", first: datetime = FIRST,
    second: datetime = SECOND, symbol: str = "BTCUSDT",
) -> BrooksSignalImport:
    return BrooksSignalImport(
        source_signal_id=f"synthetic-{snapshot}-{setup}",
        symbol=symbol,
        direction="LONG",
        entry_price=Decimal("100"),
        stop_loss=Decimal("95"),
        targets=(Decimal("110"),),
        leverage=Decimal("1"),
        exchange="synthetic",
        market_type="spot",
        timeframe="15m",
        setup_type=setup,
        market_snapshot_id=f"snapshot-{snapshot}",
        market_snapshot_hash=f"hash-{snapshot}",
        engine_version="synthetic",
        rule_set_version="synthetic",
        configuration_version="synthetic",
        reasoning=("synthetic",),
        rule_ids=("BB-TRD-06-II-III",),
        failed_rules=(),
        rule_evidence=(BrooksRuleEvidence("BB-TRD-06-II-III", "PASS", (109,)),),
        generation_mode="PAPER",
        publication_scope="PRIVATE_TEST",
        opportunity_variant="CH6_II_PAIR_STOP_V1",
        ii_first_open_time=first,
        ii_second_open_time=second,
        opportunity_view=view,
    )


def test_same_pair_across_snapshot_and_confirmed_view() -> None:
    pending = command()
    confirmed = command(snapshot="b", setup="II_CONFIRMED_BREAKOUT", view="CONFIRMED")
    assert pending.opportunity_key == confirmed.opportunity_key
    assert pending.idempotency_key != confirmed.idempotency_key
    assert pending.market_snapshot_hash != confirmed.market_snapshot_hash


def test_utc_normalization_and_genuine_pair_separation() -> None:
    shifted = command(
        first=FIRST.astimezone(timezone(timedelta(hours=3))),
        second=SECOND.astimezone(timezone(timedelta(hours=3))),
    )
    assert shifted.opportunity_key == command().opportunity_key
    next_pair = command(first=SECOND, second=SECOND + timedelta(minutes=15))
    assert next_pair.opportunity_key != shifted.opportunity_key
    assert command(symbol="ETHUSDT").opportunity_key != shifted.opportunity_key


def test_unrelated_import_keeps_normal_key() -> None:
    legacy = replace(
        command(),
        opportunity_variant=None,
        ii_first_open_time=None,
        ii_second_open_time=None,
        opportunity_view=None,
    )
    assert legacy.opportunity_key is None
    assert legacy.idempotency_key == command().idempotency_key


@pytest.mark.parametrize(
    "first,second",
    [(SECOND, FIRST), (FIRST.replace(tzinfo=None), SECOND)],
)
def test_invalid_pair_origin_fails_closed(first: datetime, second: datetime) -> None:
    with pytest.raises(ValueError):
        command(first=first, second=second)
