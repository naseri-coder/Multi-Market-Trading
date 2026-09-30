"""Telegram Bot API adapter for text, media, and forward delivery."""

from __future__ import annotations

from datetime import timedelta

from telegram import Bot
from telegram.error import Forbidden, RetryAfter, TelegramError

from app.modules.broadcasts.entities import BroadcastRecord
from app.modules.broadcasts.errors import (
    BroadcastBlockedError,
    BroadcastDeliveryError,
    BroadcastRetryAfterError,
)
from app.modules.broadcasts.models import BroadcastContentType, BroadcastMediaType


class TelegramBroadcastGateway:
    """Send persisted content by Telegram file id without forwarding a message."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def send(self, telegram_user_id: int, broadcast: BroadcastRecord) -> None:
        try:
            if broadcast.content_type == BroadcastContentType.TEXT.value:
                await self.bot.send_message(
                    chat_id=telegram_user_id,
                    text=broadcast.text,
                )
                return

            if broadcast.content_type == BroadcastContentType.FORWARD.value:
                if broadcast.source_chat_id is None or broadcast.source_message_id is None:
                    raise BroadcastDeliveryError("INVALID_FORWARD_SOURCE")
                await self.bot.forward_message(
                    chat_id=telegram_user_id,
                    from_chat_id=broadcast.source_chat_id,
                    message_id=broadcast.source_message_id,
                )
                return

            if broadcast.content_type != BroadcastContentType.MEDIA.value:
                raise BroadcastDeliveryError("UNSUPPORTED_CONTENT")

            senders = {
                BroadcastMediaType.PHOTO.value: self.bot.send_photo,
                BroadcastMediaType.VIDEO.value: self.bot.send_video,
                BroadcastMediaType.DOCUMENT.value: self.bot.send_document,
                BroadcastMediaType.ANIMATION.value: self.bot.send_animation,
                BroadcastMediaType.AUDIO.value: self.bot.send_audio,
                BroadcastMediaType.VOICE.value: self.bot.send_voice,
            }
            sender = senders.get(broadcast.media_type)
            if sender is None or broadcast.media_file_id is None:
                raise BroadcastDeliveryError("UNSUPPORTED_MEDIA")

            media_parameter = broadcast.media_type.lower()
            await sender(
                chat_id=telegram_user_id,
                **{
                    media_parameter: broadcast.media_file_id,
                    "caption": broadcast.caption,
                },
            )
        except BroadcastDeliveryError:
            raise
        except Forbidden as exc:
            raise BroadcastBlockedError from exc
        except RetryAfter as exc:
            retry_after = exc.retry_after
            seconds = (
                retry_after.total_seconds()
                if isinstance(retry_after, timedelta)
                else float(retry_after)
            )
            raise BroadcastRetryAfterError(max(seconds, 0.0)) from exc
        except TelegramError as exc:
            raise BroadcastDeliveryError("TELEGRAM_ERROR") from exc
