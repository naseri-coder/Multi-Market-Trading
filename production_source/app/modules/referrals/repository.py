"""Referral repository port and async PostgreSQL implementation."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from sqlalchemy import case, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as _models  # noqa: F401
from app.modules.referrals.entities import (
    InvitedUserRecord,
    ReferralStatistics,
    ReferralUserRecord,
)
from app.modules.referrals.errors import ReferralRepositoryError
from app.modules.referrals.models import Referral
from app.modules.users.models import User, UserStatus


class ReferralRepository(Protocol):
    """Persistence contract consumed by ReferralService."""

    async def get_user(
        self,
        user_id: int,
        *,
        for_update: bool = False,
    ) -> ReferralUserRecord | None: ...

    async def find_user_by_code(
        self,
        referral_code: str,
    ) -> ReferralUserRecord | None: ...

    async def assign_code_if_missing(
        self,
        user_id: int,
        referral_code: str,
    ) -> bool: ...

    async def create_referral(
        self,
        *,
        referrer_user_id: int,
        referred_user_id: int,
        referral_code: str,
        created_at: datetime,
    ) -> bool: ...

    async def statistics_for_user(
        self,
        referrer_user_id: int,
    ) -> ReferralStatistics: ...

    async def list_invited_users(
        self,
        referrer_user_id: int,
        *,
        limit: int,
        offset: int,
    ) -> tuple[InvitedUserRecord, ...]: ...


def _to_user(model: User) -> ReferralUserRecord:
    return ReferralUserRecord(
        id=model.id,
        telegram_user_id=model.telegram_user_id,
        username=model.username,
        first_name=model.first_name,
        last_name=model.last_name,
        status=model.status,
        referral_code=model.referral_code,
    )


class SQLAlchemyReferralRepository:
    """PostgreSQL referral repository bound to a caller-owned transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_user(
        self,
        user_id: int,
        *,
        for_update: bool = False,
    ) -> ReferralUserRecord | None:
        statement = select(User).where(User.id == user_id)
        if for_update:
            statement = statement.with_for_update()
        try:
            model = await self.session.scalar(statement)
        except SQLAlchemyError as exc:
            raise ReferralRepositoryError("Unable to load referral user") from exc
        return _to_user(model) if model is not None else None

    async def find_user_by_code(
        self,
        referral_code: str,
    ) -> ReferralUserRecord | None:
        statement = select(User).where(User.referral_code == referral_code)
        try:
            model = await self.session.scalar(statement)
        except SQLAlchemyError as exc:
            raise ReferralRepositoryError("Unable to resolve referral code") from exc
        return _to_user(model) if model is not None else None

    async def assign_code_if_missing(
        self,
        user_id: int,
        referral_code: str,
    ) -> bool:
        statement = (
            update(User)
            .where(User.id == user_id, User.referral_code.is_(None))
            .values(referral_code=referral_code)
            .returning(User.id)
        )
        try:
            async with self.session.begin_nested():
                assigned_id = await self.session.scalar(statement)
        except IntegrityError:
            return False
        except SQLAlchemyError as exc:
            raise ReferralRepositoryError("Unable to assign referral code") from exc
        return assigned_id is not None

    async def create_referral(
        self,
        *,
        referrer_user_id: int,
        referred_user_id: int,
        referral_code: str,
        created_at: datetime,
    ) -> bool:
        statement = (
            insert(Referral)
            .values(
                referrer_user_id=referrer_user_id,
                referred_user_id=referred_user_id,
                referral_code=referral_code,
                reward_granted=False,
                created_at=created_at,
            )
            .on_conflict_do_nothing(
                constraint="uq_referrals_referred_user_id"
            )
            .returning(Referral.id)
        )
        try:
            created_id = await self.session.scalar(statement)
        except SQLAlchemyError as exc:
            raise ReferralRepositoryError("Unable to create referral") from exc
        return created_id is not None

    async def statistics_for_user(
        self,
        referrer_user_id: int,
    ) -> ReferralStatistics:
        statement = (
            select(
                func.count(Referral.id),
                func.coalesce(
                    func.sum(
                        case(
                            (User.status == UserStatus.ACTIVE.value, 1),
                            else_=0,
                        )
                    ),
                    0,
                ),
            )
            .select_from(Referral)
            .join(User, User.id == Referral.referred_user_id)
            .where(Referral.referrer_user_id == referrer_user_id)
        )
        try:
            total, active = (await self.session.execute(statement)).one()
        except SQLAlchemyError as exc:
            raise ReferralRepositoryError("Unable to load referral statistics") from exc
        total_count = int(total or 0)
        active_count = int(active or 0)
        return ReferralStatistics(
            total_invited=total_count,
            active_invited=active_count,
            inactive_invited=total_count - active_count,
        )

    async def list_invited_users(
        self,
        referrer_user_id: int,
        *,
        limit: int,
        offset: int,
    ) -> tuple[InvitedUserRecord, ...]:
        statement = (
            select(User, Referral.created_at)
            .join(Referral, Referral.referred_user_id == User.id)
            .where(Referral.referrer_user_id == referrer_user_id)
            .order_by(Referral.created_at.desc(), Referral.id.desc())
            .limit(limit)
            .offset(offset)
        )
        try:
            rows = (await self.session.execute(statement)).all()
        except SQLAlchemyError as exc:
            raise ReferralRepositoryError("Unable to list invited users") from exc
        return tuple(
            InvitedUserRecord(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                status=user.status,
                invited_at=created_at,
            )
            for user, created_at in rows
        )
