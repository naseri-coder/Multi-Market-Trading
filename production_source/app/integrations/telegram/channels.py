"""Telegram Bot API adapter for channel resolution and membership checks."""

from __future__ import annotations

from telegram import Bot, Chat, ChatMember
from telegram.error import TelegramError

from app.modules.channels.entities import ResolvedTelegramChannel
from app.modules.channels.errors import TelegramChannelGatewayError

_SUPPORTED_CHAT_TYPES = frozenset({Chat.CHANNEL, Chat.SUPERGROUP})
_BOT_ADMIN_STATUSES = frozenset({ChatMember.OWNER, ChatMember.ADMINISTRATOR})
_MEMBER_STATUSES = frozenset({ChatMember.OWNER, ChatMember.ADMINISTRATOR, ChatMember.MEMBER})


def parse_chat_reference(value: str) -> int | str:
    """Return a numeric chat id or normalized public @username."""
    normalized = value.strip()
    if not normalized:
        raise TelegramChannelGatewayError("Channel reference is required")
    if normalized.lstrip("-").isdigit():
        chat_id = int(normalized)
        if chat_id >= 0:
            raise TelegramChannelGatewayError("Channel chat id must be negative")
        return chat_id
    if not normalized.startswith("@"):
        normalized = f"@{normalized}"
    return normalized


class TelegramChannelGateway:
    """Resolve channels and verify membership through an initialized PTB Bot."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def resolve_channel(
        self,
        reference: str,
        *,
        supplied_invite_link: str | None = None,
        ensure_invite_link: bool = True,
    ) -> ResolvedTelegramChannel:
        chat_reference = parse_chat_reference(reference)
        try:
            chat = await self.bot.get_chat(chat_reference)
            if chat.type not in _SUPPORTED_CHAT_TYPES:
                raise TelegramChannelGatewayError(
                    "Only Telegram channels and supergroups are supported"
                )

            bot_member = await self.bot.get_chat_member(chat.id, self.bot.id)
            if bot_member.status not in _BOT_ADMIN_STATUSES:
                raise TelegramChannelGatewayError("The bot must be an administrator in the channel")

            invite_link = supplied_invite_link or chat.invite_link
            if ensure_invite_link and chat.username is None and invite_link is None:
                created_invite = await self.bot.create_chat_invite_link(
                    chat.id,
                    name="Crypto Signal Bot",
                )
                invite_link = created_invite.invite_link
        except TelegramChannelGatewayError:
            raise
        except TelegramError as exc:
            raise TelegramChannelGatewayError("Unable to resolve Telegram channel") from exc

        title = chat.title or chat.username or str(chat.id)
        return ResolvedTelegramChannel(
            telegram_chat_id=chat.id,
            username=chat.username,
            title=title,
            invite_link=invite_link,
        )

    async def is_member(self, telegram_chat_id: int, telegram_user_id: int) -> bool:
        try:
            member = await self.bot.get_chat_member(telegram_chat_id, telegram_user_id)
        except TelegramError as exc:
            raise TelegramChannelGatewayError("Unable to verify Telegram membership") from exc

        if member.status in _MEMBER_STATUSES:
            return True
        if member.status == ChatMember.RESTRICTED:
            return bool(getattr(member, "is_member", False))
        return False
