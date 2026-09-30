"""Channel management and multi-channel membership business rules."""

from __future__ import annotations

import asyncio
import re
from typing import Protocol
from urllib.parse import urlsplit

from app.modules.channels.entities import (
    ChannelMembershipResult,
    ChannelRecord,
    CreateChannel,
    ResolvedTelegramChannel,
    UpdateChannel,
)
from app.modules.channels.errors import (
    ChannelConfigurationError,
    ChannelMembershipCheckError,
    InvalidChannelError,
)
from app.modules.channels.repository import ChannelRepository

_USERNAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")
_ALLOWED_INVITE_HOSTS = frozenset({"t.me", "telegram.me", "www.t.me", "www.telegram.me"})


class ChannelMembershipGateway(Protocol):
    """Telegram membership port consumed by ChannelService."""

    async def is_member(self, telegram_chat_id: int, telegram_user_id: int) -> bool: ...


class ChannelService:
    """Validate channel state and enforce membership across every active channel."""

    def __init__(self, repository: ChannelRepository) -> None:
        self.repository = repository

    async def create_channel(self, channel: CreateChannel) -> ChannelRecord:
        return await self.repository.create(self._validate_create(channel))

    async def update_channel(self, channel_id: int, channel: UpdateChannel) -> ChannelRecord:
        self._validate_internal_id(channel_id)
        return await self.repository.update(channel_id, self._validate_update(channel))

    async def delete_channel(self, channel_id: int) -> None:
        self._validate_internal_id(channel_id)
        await self.repository.delete(channel_id)

    async def toggle_channel(self, channel_id: int) -> ChannelRecord:
        self._validate_internal_id(channel_id)
        return await self.repository.toggle(channel_id)

    async def get_channel(self, channel_id: int) -> ChannelRecord:
        self._validate_internal_id(channel_id)
        return await self.repository.get_by_id(channel_id)

    async def refresh_channel(self, channel: ResolvedTelegramChannel) -> ChannelRecord:
        """Refresh stored Telegram metadata while preserving administrator ordering."""
        existing = await self.repository.get_by_telegram_chat_id(channel.telegram_chat_id)
        return await self.repository.update(
            existing.id,
            self._validate_update(
                UpdateChannel(
                    title=channel.title,
                    username=channel.username,
                    invite_link=channel.invite_link,
                    sort_order=existing.sort_order,
                )
            ),
        )

    async def list_channels(self) -> tuple[ChannelRecord, ...]:
        return await self.repository.list_all()

    async def check_membership(
        self,
        telegram_user_id: int,
        gateway: ChannelMembershipGateway,
    ) -> ChannelMembershipResult:
        if telegram_user_id <= 0:
            raise InvalidChannelError("Telegram user id must be positive")

        active_channels = await self.repository.list_active()
        if not active_channels:
            return ChannelMembershipResult(
                allowed=True,
                checked_channels=0,
                missing_channels=(),
            )

        checks = await asyncio.gather(
            *(
                gateway.is_member(channel.telegram_chat_id, telegram_user_id)
                for channel in active_channels
            ),
            return_exceptions=True,
        )
        for result in checks:
            if isinstance(result, asyncio.CancelledError):
                raise result
        if any(isinstance(result, Exception) for result in checks):
            raise ChannelMembershipCheckError(
                "Unable to verify membership for every active channel"
            )

        missing_channels = tuple(
            channel
            for channel, is_member in zip(active_channels, checks, strict=True)
            if is_member is not True
        )
        if any(channel.join_url is None for channel in missing_channels):
            raise ChannelConfigurationError("An active channel has no usable join URL")

        return ChannelMembershipResult(
            allowed=not missing_channels,
            checked_channels=len(active_channels),
            missing_channels=missing_channels,
        )

    @classmethod
    def _validate_create(cls, channel: CreateChannel) -> CreateChannel:
        if channel.telegram_chat_id >= 0:
            raise InvalidChannelError("Telegram channel id must be negative")
        title = cls._validate_title(channel.title)
        username = cls._normalize_username(channel.username)
        invite_link = cls._normalize_invite_link(channel.invite_link)
        sort_order = cls._validate_sort_order(channel.sort_order)
        cls._require_join_target(username, invite_link)
        return CreateChannel(
            telegram_chat_id=channel.telegram_chat_id,
            username=username,
            title=title,
            invite_link=invite_link,
            sort_order=sort_order,
        )

    @classmethod
    def _validate_update(cls, channel: UpdateChannel) -> UpdateChannel:
        title = cls._validate_title(channel.title)
        username = cls._normalize_username(channel.username)
        invite_link = cls._normalize_invite_link(channel.invite_link)
        sort_order = cls._validate_sort_order(channel.sort_order)
        cls._require_join_target(username, invite_link)
        return UpdateChannel(
            title=title,
            username=username,
            invite_link=invite_link,
            sort_order=sort_order,
        )

    @staticmethod
    def _validate_internal_id(channel_id: int) -> None:
        if channel_id <= 0:
            raise InvalidChannelError("Internal channel id must be positive")

    @staticmethod
    def _validate_title(title: str) -> str:
        normalized = title.strip()
        if not normalized or len(normalized) > 255:
            raise InvalidChannelError("Channel title must contain 1 to 255 characters")
        return normalized

    @staticmethod
    def _normalize_username(username: str | None) -> str | None:
        if username is None:
            return None
        normalized = username.strip().removeprefix("@")
        if not normalized:
            return None
        if not _USERNAME_PATTERN.fullmatch(normalized):
            raise InvalidChannelError("Channel username format is invalid")
        return normalized

    @staticmethod
    def _normalize_invite_link(invite_link: str | None) -> str | None:
        if invite_link is None:
            return None
        normalized = invite_link.strip()
        if not normalized:
            return None
        parsed = urlsplit(normalized)
        if parsed.scheme != "https" or parsed.hostname not in _ALLOWED_INVITE_HOSTS:
            raise InvalidChannelError("Invite link must be a Telegram HTTPS URL")
        if not parsed.path or parsed.path == "/" or len(normalized) > 2048:
            raise InvalidChannelError("Invite link path is invalid")
        return normalized

    @staticmethod
    def _validate_sort_order(sort_order: int) -> int:
        if (
            not isinstance(sort_order, int)
            or isinstance(sort_order, bool)
            or sort_order < 0
            or sort_order > 2**31 - 1
        ):
            raise InvalidChannelError("Sort order must be a non-negative integer")
        return sort_order

    @staticmethod
    def _require_join_target(username: str | None, invite_link: str | None) -> None:
        if username is None and invite_link is None:
            raise InvalidChannelError("A public username or private invite link is required")
