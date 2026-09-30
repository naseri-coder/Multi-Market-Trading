"""Telegram delivery adapter for analytics-only Performance Intelligence reports."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
import logging
from typing import Any, Protocol

from telegram.error import RetryAfter, TelegramError

logger = logging.getLogger(__name__)


class TelegramReportBotLike(Protocol):
    async def send_message(self, **kwargs: Any) -> Any: ...
    async def get_me(self) -> Any: ...
    async def get_chat(self, chat_id: int) -> Any: ...
    async def get_chat_member(self, chat_id: int, user_id: int) -> Any: ...


@dataclass(frozen=True)
class PerformancePublishResult:
    success: bool
    attempts: int
    message_id: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class PerformanceChannelValidation:
    valid: bool
    bot_is_admin: bool
    can_post_messages: bool
    chat_type: str | None
    errors: tuple[str, ...] = ()


class PerformanceTelegramPublisher:
    """Publish reports without propagating Telegram delivery failures into runtime."""

    def __init__(
        self,
        *,
        bot: TelegramReportBotLike,
        channel_id: int,
        parse_mode: str = "HTML",
        max_retry: int = 3,
    ) -> None:
        if channel_id == 0:
            raise ValueError("channel_id must be non-zero")
        if parse_mode != "HTML":
            raise ValueError("only HTML parse mode is supported")
        if max_retry < 0:
            raise ValueError("max_retry must be non-negative")
        self.bot = bot
        self.channel_id = channel_id
        self.parse_mode = parse_mode
        self.max_retry = max_retry

    async def validate_channel(self) -> PerformanceChannelValidation:
        """Verify channel identity, administrator membership, and post permission without sending."""
        errors: list[str] = []
        try:
            bot_user = await self.bot.get_me()
            chat = await self.bot.get_chat(self.channel_id)
            member = await self.bot.get_chat_member(self.channel_id, bot_user.id)
        except TelegramError as exc:
            logger.error(
                "Performance report channel validation failed",
                extra={"event": "performance_report_channel_validation_failed"},
            )
            return PerformanceChannelValidation(
                valid=False, bot_is_admin=False, can_post_messages=False,
                chat_type=None, errors=(exc.__class__.__name__,),
            )

        chat_type = str(getattr(chat, "type", "") or "").lower() or None
        if chat_type != "channel":
            errors.append("configured chat is not a Telegram channel")

        status = str(getattr(member, "status", "") or "").lower()
        bot_is_admin = status in {"administrator", "creator", "owner"}
        if not bot_is_admin:
            errors.append("bot is not a channel administrator")

        permission = getattr(member, "can_post_messages", None)
        can_post_messages = bot_is_admin and (status in {"creator", "owner"} or permission is True)
        if not can_post_messages:
            errors.append("bot does not have permission to post messages")

        return PerformanceChannelValidation(
            valid=not errors,
            bot_is_admin=bot_is_admin,
            can_post_messages=can_post_messages,
            chat_type=chat_type,
            errors=tuple(errors),
        )

    async def publish(self, text: str) -> PerformancePublishResult:
        """Send with bounded retries; never raise Telegram delivery errors to analytics runtime."""
        total_attempts = self.max_retry + 1
        for attempt in range(1, total_attempts + 1):
            try:
                message = await self.bot.send_message(
                    chat_id=self.channel_id,
                    text=text,
                    parse_mode=self.parse_mode,
                    disable_web_page_preview=True,
                )
                return PerformancePublishResult(
                    success=True, attempts=attempt, message_id=str(message.message_id)
                )
            except RetryAfter as exc:
                if attempt >= total_attempts:
                    return self._failed(attempt, exc)
                retry_after = exc.retry_after
                seconds = (
                    retry_after.total_seconds()
                    if isinstance(retry_after, timedelta)
                    else float(retry_after)
                )
                await asyncio.sleep(max(seconds, 0.0))
            except TelegramError as exc:
                if attempt >= total_attempts:
                    return self._failed(attempt, exc)
                logger.warning(
                    "Performance report Telegram delivery retry",
                    extra={
                        "event": "performance_report_retry",
                        "attempt": attempt,
                        "max_retry": self.max_retry,
                    },
                )

        return PerformancePublishResult(False, total_attempts, error="UNREACHABLE")

    @staticmethod
    def _failed(attempts: int, exc: TelegramError) -> PerformancePublishResult:
        logger.error(
            "Performance report Telegram delivery failed",
            extra={
                "event": "performance_report_delivery_failed",
                "attempts": attempts,
                "error_type": exc.__class__.__name__,
            },
        )
        return PerformancePublishResult(
            success=False, attempts=attempts, error=exc.__class__.__name__
        )
