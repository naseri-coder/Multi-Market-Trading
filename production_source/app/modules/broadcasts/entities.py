"""Framework-independent broadcast inputs, records, and reports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class CreateBroadcast:
    """Administrator-authored content awaiting preview and confirmation."""

    created_by_telegram_user_id: int
    content_type: str
    text: str | None = None
    media_type: str | None = None
    media_file_id: str | None = None
    caption: str | None = None
    source_chat_id: int | None = None
    source_message_id: int | None = None


@dataclass(frozen=True, slots=True)
class BroadcastRecord:
    """Stable broadcast read model."""

    id: int
    created_by_telegram_user_id: int
    content_type: str
    text: str | None
    media_type: str | None
    media_file_id: str | None
    caption: str | None
    status: str
    total_recipients: int
    sent_count: int
    failed_count: int
    blocked_count: int
    confirmed_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    source_chat_id: int | None = None
    source_message_id: int | None = None


@dataclass(frozen=True, slots=True)
class BroadcastRecipientRecord:
    """One recipient snapshot waiting for delivery."""

    id: int
    broadcast_id: int
    user_id: int
    telegram_user_id: int
    status: str
    attempts: int
    last_error_code: str | None
    sent_at: datetime | None


@dataclass(frozen=True, slots=True)
class BroadcastReport:
    """Aggregate delivery result suitable for the administrator UI."""

    broadcast_id: int
    status: str
    total_recipients: int
    sent_count: int
    failed_count: int
    blocked_count: int
