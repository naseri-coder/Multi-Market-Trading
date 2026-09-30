"""User statistics repository port and SQLAlchemy aggregate query."""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import and_, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

# Register string-based relationship targets before ORM statements compile.
from app.db import models as _models  # noqa: F401
from app.modules.users.entities import UserStatisticsBoundaries, UserStatisticsCounts
from app.modules.users.errors import UserStatisticsRepositoryError
from app.modules.users.models import User, UserStatus


class UserStatisticsRepository(Protocol):
    """Persistence contract consumed by UserStatisticsService."""

    async def fetch_counts(
        self,
        boundaries: UserStatisticsBoundaries,
    ) -> UserStatisticsCounts:
        """Load all dashboard counts in one database round trip."""
        ...


class SQLAlchemyUserStatisticsRepository:
    """PostgreSQL aggregate implementation for user dashboard counts."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def fetch_counts(
        self,
        boundaries: UserStatisticsBoundaries,
    ) -> UserStatisticsCounts:
        active_condition = and_(
            User.status == UserStatus.ACTIVE.value,
            User.last_activity >= boundaries.active_since,
        )
        statement = select(
            func.count(User.id).label("total_users"),
            func.count(User.id).filter(active_condition).label("active_users"),
            func.count(User.id)
            .filter(
                and_(
                    User.created_at >= boundaries.today_start,
                    User.created_at <= boundaries.as_of,
                )
            )
            .label("new_users_today"),
            func.count(User.id)
            .filter(
                and_(
                    User.created_at >= boundaries.week_start,
                    User.created_at <= boundaries.as_of,
                )
            )
            .label("new_users_this_week"),
            func.count(User.id)
            .filter(
                and_(
                    User.created_at >= boundaries.month_start,
                    User.created_at <= boundaries.as_of,
                )
            )
            .label("new_users_this_month"),
        )

        try:
            row = (await self.session.execute(statement)).one()
        except SQLAlchemyError as exc:
            raise UserStatisticsRepositoryError("Unable to load user statistics") from exc

        return UserStatisticsCounts(
            total_users=int(row.total_users),
            active_users=int(row.active_users),
            new_users_today=int(row.new_users_today),
            new_users_this_week=int(row.new_users_this_week),
            new_users_this_month=int(row.new_users_this_month),
        )
