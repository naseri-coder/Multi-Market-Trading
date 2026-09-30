"""Durable runtime heartbeat writes."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.operations.models import RuntimeHealth


def utc_now() -> datetime:
    return datetime.now(UTC)


async def record_health(
    session: AsyncSession,
    *,
    component: str,
    status: str,
    details: dict[str, object] | None = None,
    error: bool = False,
) -> None:
    now = utc_now()
    payload: dict[str, object] = {
        "status": status,
        "details": details or {},
        "updated_at": now,
    }
    if error:
        payload["last_error_at"] = now
    else:
        payload["last_success_at"] = now
    statement = insert(RuntimeHealth).values(
        component=component,
        status=status,
        last_success_at=None if error else now,
        last_error_at=now if error else None,
        details=details or {},
        updated_at=now,
    ).on_conflict_do_update(
        index_elements=[RuntimeHealth.component],
        set_=payload,
    )
    await session.execute(statement)
