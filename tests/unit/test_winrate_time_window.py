"""Half-open trading-performance time-window regression tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import DateTime, create_engine, literal, select
from sqlalchemy.dialects import postgresql

from app.modules.analytics.repository import _closed_at_in_window
from app.modules.signals.models import Signal

T0 = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
T1 = T0 + timedelta(days=1)
T2 = T1 + timedelta(days=1)
PRECISION = timedelta(microseconds=1)


def included(timestamp: datetime, *, start: datetime, end: datetime) -> bool:
    """Evaluate the production SQLAlchemy predicate without persistent storage."""
    timestamp_value = literal(timestamp, type_=DateTime(timezone=True))
    statement = select(literal(1)).where(
        _closed_at_in_window(timestamp_value, started_at=start, ended_at=end)
    )
    with create_engine("sqlite://").connect() as connection:
        return connection.scalar(statement) == 1


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    (
        (T0, True),
        (T1, False),
        (T1 - PRECISION, True),
        (T0 + PRECISION, True),
        (T0 - PRECISION, False),
        (T1 + PRECISION, False),
    ),
)
def test_half_open_window_exact_boundaries(
    timestamp: datetime,
    expected: bool,
) -> None:
    assert included(timestamp, start=T0, end=T1) is expected


def test_adjacent_windows_count_boundary_trade_exactly_once() -> None:
    count_in_window_a = int(included(T1, start=T0, end=T1))
    count_in_window_b = int(included(T1, start=T1, end=T2))

    assert count_in_window_a == 0
    assert count_in_window_b == 1
    assert count_in_window_a + count_in_window_b == 1


def test_multiple_trade_membership_across_adjacent_windows() -> None:
    timestamps = {
        "t0": T0,
        "middle_1": T0 + (T1 - T0) / 2,
        "t1": T1,
        "middle_2": T1 + (T2 - T1) / 2,
        "t2": T2,
    }

    window_1 = {
        key
        for key, timestamp in timestamps.items()
        if included(timestamp, start=T0, end=T1)
    }
    window_2 = {
        key
        for key, timestamp in timestamps.items()
        if included(timestamp, start=T1, end=T2)
    }

    assert window_1 == {"t0", "middle_1"}
    assert window_2 == {"t1", "middle_2"}
    assert window_1.isdisjoint(window_2)


def test_postgresql_predicate_uses_comparators_not_timestamp_epsilon() -> None:
    expression = _closed_at_in_window(
        Signal.closed_at,
        started_at=T0,
        ended_at=T1,
    )
    sql = str(
        expression.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "signals.closed_at >= " in sql
    assert "signals.closed_at < " in sql
    assert "signals.closed_at <= " not in sql
