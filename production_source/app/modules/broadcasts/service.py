"""Broadcast validation, state transitions, rate limiting, and delivery orchestration."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Protocol

from app.db.session import DatabaseManager
from app.modules.broadcasts.entities import (
    BroadcastRecipientRecord,
    BroadcastRecord,
    BroadcastReport,
    CreateBroadcast,
)
from app.modules.broadcasts.errors import (
    BroadcastBlockedError,
    BroadcastDeliveryError,
    BroadcastError,
    BroadcastRetryAfterError,
    InvalidBroadcastError,
)
from app.modules.broadcasts.models import (
    BroadcastContentType,
    BroadcastMediaType,
    BroadcastRecipientStatus,
    BroadcastStatus,
)
from app.modules.broadcasts.repository import (
    BroadcastRepository,
    SQLAlchemyBroadcastRepository,
)

logger = logging.getLogger(__name__)

Sleep = Callable[[float], Awaitable[None]]
Monotonic = Callable[[], float]


class BroadcastGateway(Protocol):
    """Telegram delivery port consumed by BroadcastDeliveryService."""

    async def send(self, telegram_user_id: int, broadcast: BroadcastRecord) -> None: ...


class BroadcastService:
    """Validate drafts and own administrator-triggered state transitions."""

    def __init__(self, repository: BroadcastRepository) -> None:
        self.repository = repository

    async def create_draft(self, draft: CreateBroadcast) -> BroadcastRecord:
        return await self.repository.create_draft(self._validate_draft(draft))

    async def get_preview(
        self,
        broadcast_id: int,
        admin_telegram_id: int,
    ) -> BroadcastRecord:
        self._validate_ids(broadcast_id, admin_telegram_id)
        broadcast = await self.repository.get_owned(broadcast_id, admin_telegram_id)
        if broadcast.status != BroadcastStatus.DRAFT.value:
            raise InvalidBroadcastError("Only draft broadcasts can be previewed")
        return broadcast

    async def cancel(
        self,
        broadcast_id: int,
        admin_telegram_id: int,
    ) -> BroadcastRecord:
        self._validate_ids(broadcast_id, admin_telegram_id)
        return await self.repository.cancel_draft(broadcast_id, admin_telegram_id)

    async def confirm(
        self,
        broadcast_id: int,
        admin_telegram_id: int,
        *,
        confirmed_at: datetime | None = None,
    ) -> BroadcastRecord:
        self._validate_ids(broadcast_id, admin_telegram_id)
        timestamp = confirmed_at or datetime.now(UTC)
        return await self.repository.claim_and_snapshot(
            broadcast_id,
            admin_telegram_id,
            confirmed_at=timestamp,
        )

    @staticmethod
    def report(broadcast: BroadcastRecord) -> BroadcastReport:
        return BroadcastReport(
            broadcast_id=broadcast.id,
            status=broadcast.status,
            total_recipients=broadcast.total_recipients,
            sent_count=broadcast.sent_count,
            failed_count=broadcast.failed_count,
            blocked_count=broadcast.blocked_count,
        )

    @staticmethod
    def _validate_ids(broadcast_id: int, admin_telegram_id: int) -> None:
        if broadcast_id <= 0 or admin_telegram_id <= 0:
            raise InvalidBroadcastError("Broadcast and administrator ids must be positive")

    @staticmethod
    def _validate_draft(draft: CreateBroadcast) -> CreateBroadcast:
        if draft.created_by_telegram_user_id <= 0:
            raise InvalidBroadcastError("Administrator Telegram id must be positive")

        if draft.content_type == BroadcastContentType.TEXT.value:
            text = draft.text.strip() if draft.text is not None else ""
            if not text or len(text) > 4096:
                raise InvalidBroadcastError("Text broadcast must contain 1 to 4096 characters")
            if any(
                value is not None
                for value in (
                    draft.media_type,
                    draft.media_file_id,
                    draft.caption,
                    draft.source_chat_id,
                    draft.source_message_id,
                )
            ):
                raise InvalidBroadcastError("Text broadcast cannot contain media fields")
            return CreateBroadcast(
                created_by_telegram_user_id=draft.created_by_telegram_user_id,
                content_type=BroadcastContentType.TEXT.value,
                text=text,
            )

        if draft.content_type == BroadcastContentType.FORWARD.value:
            if any(
                value is not None
                for value in (
                    draft.text,
                    draft.media_type,
                    draft.media_file_id,
                    draft.caption,
                )
            ):
                raise InvalidBroadcastError("Forward broadcast cannot contain copied content")
            if (
                not isinstance(draft.source_chat_id, int)
                or isinstance(draft.source_chat_id, bool)
                or draft.source_chat_id == 0
                or not isinstance(draft.source_message_id, int)
                or isinstance(draft.source_message_id, bool)
                or draft.source_message_id <= 0
            ):
                raise InvalidBroadcastError("Forward source identifiers are invalid")
            return CreateBroadcast(
                created_by_telegram_user_id=draft.created_by_telegram_user_id,
                content_type=BroadcastContentType.FORWARD.value,
                source_chat_id=draft.source_chat_id,
                source_message_id=draft.source_message_id,
            )

        if draft.content_type != BroadcastContentType.MEDIA.value:
            raise InvalidBroadcastError("Unsupported broadcast content type")
        if any(
            value is not None
            for value in (draft.text, draft.source_chat_id, draft.source_message_id)
        ):
            raise InvalidBroadcastError("Media broadcast contains incompatible fields")
        if draft.media_type not in {item.value for item in BroadcastMediaType}:
            raise InvalidBroadcastError("Unsupported broadcast media type")
        file_id = draft.media_file_id.strip() if draft.media_file_id is not None else ""
        if not file_id or len(file_id) > 512:
            raise InvalidBroadcastError("Telegram media file id is invalid")
        caption = draft.caption.strip() if draft.caption is not None else None
        caption = caption or None
        if caption is not None and len(caption) > 1024:
            raise InvalidBroadcastError("Media caption must not exceed 1024 characters")
        return CreateBroadcast(
            created_by_telegram_user_id=draft.created_by_telegram_user_id,
            content_type=BroadcastContentType.MEDIA.value,
            media_type=draft.media_type,
            media_file_id=file_id,
            caption=caption,
        )


class BroadcastRateLimiter:
    """Monotonic fixed-interval limiter kept below Telegram's free bulk limit."""

    def __init__(
        self,
        rate_per_second: float,
        *,
        sleep: Sleep = asyncio.sleep,
        monotonic: Monotonic = time.monotonic,
    ) -> None:
        if rate_per_second <= 0:
            raise ValueError("rate_per_second must be positive")
        self.interval = 1.0 / rate_per_second
        self.sleep = sleep
        self.monotonic = monotonic
        self.next_allowed_at = 0.0
        self.lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self.lock:
            now = self.monotonic()
            delay = max(0.0, self.next_allowed_at - now)
            self.next_allowed_at = max(now, self.next_allowed_at) + self.interval
        if delay:
            await self.sleep(delay)


class BroadcastDeliveryService:
    """Deliver a claimed broadcast and persist every recipient outcome."""

    def __init__(
        self,
        database: DatabaseManager,
        gateway: BroadcastGateway,
        *,
        rate_per_second: float,
        batch_size: int,
        max_retries: int,
        retry_after_cap_seconds: int,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        if batch_size <= 0 or max_retries < 0 or retry_after_cap_seconds <= 0:
            raise ValueError("Invalid broadcast delivery configuration")
        self.database = database
        self.gateway = gateway
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.retry_after_cap_seconds = retry_after_cap_seconds
        self.sleep = sleep
        self.rate_limiter = BroadcastRateLimiter(rate_per_second, sleep=sleep)

    async def run(self, broadcast_id: int) -> BroadcastReport:
        try:
            broadcast = await self._load_broadcast(broadcast_id)
            if broadcast.status != BroadcastStatus.PROCESSING.value:
                raise InvalidBroadcastError("Broadcast is not ready for delivery")

            while True:
                recipients = await self._load_pending(broadcast_id)
                if not recipients:
                    break
                for recipient in recipients:
                    status, attempts, error_code, sent_at = await self._deliver_one(
                        recipient,
                        broadcast,
                    )
                    await self._mark_recipient(
                        recipient.id,
                        status=status,
                        attempts=attempts,
                        error_code=error_code,
                        sent_at=sent_at,
                    )

            completed = await self._finalize(broadcast_id)
            return BroadcastService.report(completed)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Broadcast delivery run failed",
                extra={"event": "broadcast_delivery_failed", "broadcast_id": broadcast_id},
            )
            await self._mark_failed(broadcast_id)
            raise

    async def _deliver_one(
        self,
        recipient: BroadcastRecipientRecord,
        broadcast: BroadcastRecord,
    ) -> tuple[str, int, str | None, datetime | None]:
        attempts = 0
        while True:
            attempts += 1
            await self.rate_limiter.wait()
            try:
                await self.gateway.send(recipient.telegram_user_id, broadcast)
            except BroadcastBlockedError as exc:
                return (
                    BroadcastRecipientStatus.BLOCKED.value,
                    attempts,
                    exc.error_code,
                    None,
                )
            except BroadcastRetryAfterError as exc:
                if attempts <= self.max_retries:
                    await self.sleep(min(exc.retry_after_seconds, self.retry_after_cap_seconds))
                    continue
                return (
                    BroadcastRecipientStatus.FAILED.value,
                    attempts,
                    exc.error_code,
                    None,
                )
            except BroadcastDeliveryError as exc:
                return (
                    BroadcastRecipientStatus.FAILED.value,
                    attempts,
                    exc.error_code,
                    None,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "Unexpected recipient delivery failure",
                    extra={
                        "event": "broadcast_recipient_unexpected_error",
                        "broadcast_id": broadcast.id,
                        "recipient_id": recipient.id,
                    },
                )
                return (
                    BroadcastRecipientStatus.FAILED.value,
                    attempts,
                    "UNEXPECTED_ERROR",
                    None,
                )
            return (
                BroadcastRecipientStatus.SENT.value,
                attempts,
                None,
                datetime.now(UTC),
            )

    async def _load_broadcast(self, broadcast_id: int) -> BroadcastRecord:
        async with self.database.session() as session:
            return await SQLAlchemyBroadcastRepository(session).get_by_id(broadcast_id)

    async def _load_pending(
        self,
        broadcast_id: int,
    ) -> tuple[BroadcastRecipientRecord, ...]:
        async with self.database.session() as session:
            return await SQLAlchemyBroadcastRepository(session).list_pending(
                broadcast_id,
                limit=self.batch_size,
            )

    async def _mark_recipient(
        self,
        recipient_id: int,
        *,
        status: str,
        attempts: int,
        error_code: str | None,
        sent_at: datetime | None,
    ) -> None:
        async with self.database.session() as session, session.begin():
            await SQLAlchemyBroadcastRepository(session).mark_recipient(
                recipient_id,
                status=status,
                attempts=attempts,
                error_code=error_code,
                sent_at=sent_at,
            )

    async def _finalize(self, broadcast_id: int) -> BroadcastRecord:
        async with self.database.session() as session, session.begin():
            return await SQLAlchemyBroadcastRepository(session).finalize(
                broadcast_id,
                completed_at=datetime.now(UTC),
            )

    async def _mark_failed(self, broadcast_id: int) -> None:
        try:
            async with self.database.session() as session, session.begin():
                await SQLAlchemyBroadcastRepository(session).fail(
                    broadcast_id,
                    completed_at=datetime.now(UTC),
                )
        except BroadcastError:
            logger.exception(
                "Unable to persist failed broadcast status",
                extra={"event": "broadcast_fail_status_failed", "broadcast_id": broadcast_id},
            )
