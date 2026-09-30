"""Unit contract tests for public signal publication isolation."""

from datetime import UTC, datetime

from sqlalchemy.dialects import postgresql

from app.modules.signals.entities import SignalListMode
from app.modules.signals.models import Signal
from app.modules.signals.repository import SQLAlchemySignalRepository


def _compiled_filters(mode: str, live_since=None) -> str:
    filters = SQLAlchemySignalRepository._public_signal_filters(mode, live_since)
    statement = Signal.__table__.select().where(*filters)
    return str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )


def test_open_public_filter_requires_public_or_public_vip_scope() -> None:
    sql = _compiled_filters(SignalListMode.OPEN.value)
    assert "publication_scope IN ('PUBLIC', 'PUBLIC_VIP')" in sql
    assert "status = 'OPEN'" in sql
    assert "PRIVATE_TEST" not in sql
    assert "INTERNAL" not in sql


def test_live_public_filter_keeps_scope_and_time_gate() -> None:
    cutoff = datetime(2026, 9, 2, 12, tzinfo=UTC)
    sql = _compiled_filters(SignalListMode.LIVE.value, cutoff)
    assert "publication_scope IN ('PUBLIC', 'PUBLIC_VIP')" in sql
    assert "status != 'DRAFT'" in sql
    assert "created_at >=" in sql


def test_history_public_filter_keeps_scope_and_terminal_statuses() -> None:
    sql = _compiled_filters(SignalListMode.HISTORY.value)
    assert "publication_scope IN ('PUBLIC', 'PUBLIC_VIP')" in sql
    assert "status IN ('CLOSED', 'CANCELLED')" in sql
