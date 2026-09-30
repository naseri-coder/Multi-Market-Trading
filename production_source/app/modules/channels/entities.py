"""Framework-independent channel management and membership data types."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ChannelRecord:
    """Stable read model for a required Telegram channel."""

    id: int
    telegram_chat_id: int
    username: str | None
    title: str
    invite_link: str | None
    is_active: bool
    sort_order: int
    created_at: datetime
    updated_at: datetime

    @property
    def join_url(self) -> str | None:
        if self.username:
            return f"https://t.me/{self.username}"
        return self.invite_link


@dataclass(frozen=True, slots=True)
class CreateChannel:
    """Validated channel creation input."""

    telegram_chat_id: int
    username: str | None
    title: str
    invite_link: str | None
    sort_order: int = 0


@dataclass(frozen=True, slots=True)
class UpdateChannel:
    """Editable channel metadata."""

    title: str
    username: str | None
    invite_link: str | None
    sort_order: int


@dataclass(frozen=True, slots=True)
class ResolvedTelegramChannel:
    """Channel metadata resolved and authorized through Telegram."""

    telegram_chat_id: int
    username: str | None
    title: str
    invite_link: str | None


@dataclass(frozen=True, slots=True)
class ChannelMembershipResult:
    """Result of checking one user against every active channel."""

    allowed: bool
    checked_channels: int
    missing_channels: tuple[ChannelRecord, ...]
