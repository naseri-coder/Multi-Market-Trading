"""Framework-independent notification preference read models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class NotificationPreference:
    """One persisted user preference for a supported notification type."""

    notification_type: str
    is_enabled: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class NotificationPreferenceMutation:
    """Idempotent result of explicitly enabling or disabling one type."""

    notification_type: str
    is_enabled: bool
    changed: bool
