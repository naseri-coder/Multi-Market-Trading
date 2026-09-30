"""Broadcast persistence port and PostgreSQL implementation."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from sqlalchemy import func, literal, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as _models  # noqa: F401
from app.modules.broadcasts.entities import (
    BroadcastRecipientRecord,
    BroadcastRecord,
    CreateBroadcast,
)
from app.modules.broadcasts.errors import (
    BroadcastNotFoundError,
    BroadcastRepositoryError,
    BroadcastStateError,
)
from app.modules.broadcasts.models import (
    Broadcast,
    BroadcastRecipient,
    BroadcastRecipientStatus,
    BroadcastStatus,
)
from app.modules.users.models import User, UserStatus


class BroadcastRepository(Protocol):
    """Persistence operations consumed by Phase 8 services."""

    async def create_draft(self, draft: CreateBroadcast) -> BroadcastRecord: ...

    async def get_owned(self, broadcast_id: int, admin_telegram_id: int) -> BroadcastRecord: ...

    async def cancel_draft(self, broadcast_id: int, admin_telegram_id: int) -> BroadcastRecord: ...

    async def claim_and_snapshot(
        self,
        broadcast_id: int,
        admin_telegram_id: int,
        *,
        confirmed_at: datetime,
    ) -> BroadcastRecord: ...

    async def get_by_id(self, broadcast_id: int) -> BroadcastRecord: ...

    async def list_pending(
        self,
        broadcast_id: int,
        *,
        limit: int,
    ) -> tuple[BroadcastRecipientRecord, ...]: ...

    async def mark_recipient(
        self,
        recipient_id: int,
        *,
        status: str,
        attempts: int,
        error_code: str | None,
        sent_at: datetime | None,
    ) -> None: ...

    async def finalize(self, broadcast_id: int, *, completed_at: datetime) -> BroadcastRecord: ...

    async def fail(self, broadcast_id: int, *, completed_at: datetime) -> None: ...


def _to_broadcast_record(broadcast: Broadcast) -> BroadcastRecord:
    return BroadcastRecord(
        id=broadcast.id,
        created_by_telegram_user_id=broadcast.created_by_telegram_user_id,
        content_type=broadcast.content_type,
        text=broadcast.text,
        media_type=broadcast.media_type,
        media_file_id=broadcast.media_file_id,
        caption=broadcast.caption,
        status=broadcast.status,
        total_recipients=broadcast.total_recipients,
        sent_count=broadcast.sent_count,
        failed_count=broadcast.failed_count,
        blocked_count=broadcast.blocked_count,
        confirmed_at=broadcast.confirmed_at,
        completed_at=broadcast.completed_at,
        created_at=broadcast.created_at,
        updated_at=broadcast.updated_at,
        source_chat_id=broadcast.source_chat_id,
        source_message_id=broadcast.source_message_id,
    )


def _to_recipient_record(recipient: BroadcastRecipient) -> BroadcastRecipientRecord:
    return BroadcastRecipientRecord(
        id=recipient.id,
        broadcast_id=recipient.broadcast_id,
        user_id=recipient.user_id,
        telegram_user_id=recipient.telegram_user_id,
        status=recipient.status,
        attempts=recipient.attempts,
        last_error_code=recipient.last_error_code,
        sent_at=recipient.sent_at,
    )


class SQLAlchemyBroadcastRepository:
    """PostgreSQL repository bound to a caller-owned session and transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_draft(self, draft: CreateBroadcast) -> BroadcastRecord:
        statement = (
            insert(Broadcast)
            .values(
                created_by_telegram_user_id=draft.created_by_telegram_user_id,
                content_type=draft.content_type,
                text=draft.text,
                media_type=draft.media_type,
                media_file_id=draft.media_file_id,
                caption=draft.caption,
                source_chat_id=draft.source_chat_id,
                source_message_id=draft.source_message_id,
            )
            .returning(Broadcast)
        )
        try:
            created = (await self.session.execute(statement)).scalar_one()
        except SQLAlchemyError as exc:
            raise BroadcastRepositoryError("Unable to create broadcast draft") from exc
        return _to_broadcast_record(created)

    async def get_owned(self, broadcast_id: int, admin_telegram_id: int) -> BroadcastRecord:
        statement = select(Broadcast).where(
            Broadcast.id == broadcast_id,
            Broadcast.created_by_telegram_user_id == admin_telegram_id,
        )
        return await self._get(statement)

    async def get_by_id(self, broadcast_id: int) -> BroadcastRecord:
        return await self._get(select(Broadcast).where(Broadcast.id == broadcast_id))

    async def _get(self, statement: object) -> BroadcastRecord:
        try:
            broadcast = (await self.session.execute(statement)).scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise BroadcastRepositoryError("Unable to load broadcast") from exc
        if broadcast is None:
            raise BroadcastNotFoundError("Broadcast does not exist")
        return _to_broadcast_record(broadcast)

    async def cancel_draft(self, broadcast_id: int, admin_telegram_id: int) -> BroadcastRecord:
        statement = (
            update(Broadcast)
            .where(
                Broadcast.id == broadcast_id,
                Broadcast.created_by_telegram_user_id == admin_telegram_id,
                Broadcast.status == BroadcastStatus.DRAFT.value,
            )
            .values(status=BroadcastStatus.CANCELLED.value)
            .returning(Broadcast)
        )
        try:
            cancelled = (await self.session.execute(statement)).scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise BroadcastRepositoryError("Unable to cancel broadcast") from exc
        if cancelled is None:
            await self._raise_transition_error(broadcast_id, admin_telegram_id)
        return _to_broadcast_record(cancelled)

    async def claim_and_snapshot(
        self,
        broadcast_id: int,
        admin_telegram_id: int,
        *,
        confirmed_at: datetime,
    ) -> BroadcastRecord:
        claim = (
            update(Broadcast)
            .where(
                Broadcast.id == broadcast_id,
                Broadcast.created_by_telegram_user_id == admin_telegram_id,
                Broadcast.status == BroadcastStatus.DRAFT.value,
            )
            .values(
                status=BroadcastStatus.PROCESSING.value,
                confirmed_at=confirmed_at,
            )
            .returning(Broadcast.id)
        )
        try:
            claimed_id = (await self.session.execute(claim)).scalar_one_or_none()
            if claimed_id is None:
                await self._raise_transition_error(broadcast_id, admin_telegram_id)

            recipients = select(
                literal(broadcast_id),
                User.id,
                User.telegram_user_id,
                literal(BroadcastRecipientStatus.PENDING.value),
                literal(0),
            ).where(
                User.status == UserStatus.ACTIVE.value,
                User.is_bot.is_(False),
            )
            snapshot = (
                insert(BroadcastRecipient)
                .from_select(
                    [
                        BroadcastRecipient.broadcast_id,
                        BroadcastRecipient.user_id,
                        BroadcastRecipient.telegram_user_id,
                        BroadcastRecipient.status,
                        BroadcastRecipient.attempts,
                    ],
                    recipients,
                )
                .on_conflict_do_nothing(constraint="uq_broadcast_recipients_broadcast_user")
            )
            await self.session.execute(snapshot)
            total = await self.session.scalar(
                select(func.count(BroadcastRecipient.id)).where(
                    BroadcastRecipient.broadcast_id == broadcast_id
                )
            )
            updated = (
                await self.session.execute(
                    update(Broadcast)
                    .where(Broadcast.id == broadcast_id)
                    .values(total_recipients=int(total or 0))
                    .returning(Broadcast)
                )
            ).scalar_one()
        except (BroadcastNotFoundError, BroadcastStateError):
            raise
        except SQLAlchemyError as exc:
            raise BroadcastRepositoryError("Unable to prepare broadcast recipients") from exc
        return _to_broadcast_record(updated)

    async def _raise_transition_error(
        self,
        broadcast_id: int,
        admin_telegram_id: int,
    ) -> None:
        try:
            status = await self.session.scalar(
                select(Broadcast.status).where(
                    Broadcast.id == broadcast_id,
                    Broadcast.created_by_telegram_user_id == admin_telegram_id,
                )
            )
        except SQLAlchemyError as exc:
            raise BroadcastRepositoryError("Unable to validate broadcast state") from exc
        if status is None:
            raise BroadcastNotFoundError("Broadcast does not exist")
        raise BroadcastStateError(f"Broadcast cannot transition from {status}")

    async def list_pending(
        self,
        broadcast_id: int,
        *,
        limit: int,
    ) -> tuple[BroadcastRecipientRecord, ...]:
        statement = (
            select(BroadcastRecipient)
            .where(
                BroadcastRecipient.broadcast_id == broadcast_id,
                BroadcastRecipient.status == BroadcastRecipientStatus.PENDING.value,
            )
            .order_by(BroadcastRecipient.id)
            .limit(limit)
        )
        try:
            recipients = (await self.session.execute(statement)).scalars().all()
        except SQLAlchemyError as exc:
            raise BroadcastRepositoryError("Unable to load pending recipients") from exc
        return tuple(_to_recipient_record(recipient) for recipient in recipients)

    async def mark_recipient(
        self,
        recipient_id: int,
        *,
        status: str,
        attempts: int,
        error_code: str | None,
        sent_at: datetime | None,
    ) -> None:
        statement = (
            update(BroadcastRecipient)
            .where(
                BroadcastRecipient.id == recipient_id,
                BroadcastRecipient.status == BroadcastRecipientStatus.PENDING.value,
            )
            .values(
                status=status,
                attempts=attempts,
                last_error_code=error_code,
                sent_at=sent_at,
            )
            .returning(BroadcastRecipient.user_id)
        )
        try:
            user_id = (await self.session.execute(statement)).scalar_one_or_none()
            if user_id is None:
                raise BroadcastStateError("Recipient was already finalized")
            if status == BroadcastRecipientStatus.BLOCKED.value:
                await self.session.execute(
                    update(User).where(User.id == user_id).values(status=UserStatus.BLOCKED.value)
                )
        except BroadcastStateError:
            raise
        except SQLAlchemyError as exc:
            raise BroadcastRepositoryError("Unable to persist recipient outcome") from exc

    async def finalize(
        self,
        broadcast_id: int,
        *,
        completed_at: datetime,
    ) -> BroadcastRecord:
        try:
            rows = await self.session.execute(
                select(BroadcastRecipient.status, func.count(BroadcastRecipient.id))
                .where(BroadcastRecipient.broadcast_id == broadcast_id)
                .group_by(BroadcastRecipient.status)
            )
            counts = {status: int(count) for status, count in rows.all()}
            finalized = (
                await self.session.execute(
                    update(Broadcast)
                    .where(
                        Broadcast.id == broadcast_id,
                        Broadcast.status == BroadcastStatus.PROCESSING.value,
                    )
                    .values(
                        status=BroadcastStatus.COMPLETED.value,
                        sent_count=counts.get(BroadcastRecipientStatus.SENT.value, 0),
                        failed_count=counts.get(BroadcastRecipientStatus.FAILED.value, 0),
                        blocked_count=counts.get(BroadcastRecipientStatus.BLOCKED.value, 0),
                        completed_at=completed_at,
                    )
                    .returning(Broadcast)
                )
            ).scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise BroadcastRepositoryError("Unable to finalize broadcast") from exc
        if finalized is None:
            raise BroadcastStateError("Broadcast is not processing")
        return _to_broadcast_record(finalized)

    async def fail(self, broadcast_id: int, *, completed_at: datetime) -> None:
        try:
            await self.session.execute(
                update(Broadcast)
                .where(
                    Broadcast.id == broadcast_id,
                    Broadcast.status == BroadcastStatus.PROCESSING.value,
                )
                .values(
                    status=BroadcastStatus.FAILED.value,
                    completed_at=completed_at,
                )
            )
        except SQLAlchemyError as exc:
            raise BroadcastRepositoryError("Unable to mark broadcast failed") from exc
