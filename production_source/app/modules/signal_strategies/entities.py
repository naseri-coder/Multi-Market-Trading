"""Framework-independent signal-strategy configuration contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

BROOKS_STRATEGY_CODE = "BROOKS"
FM_STRATEGY_CODE = "FM"
SUPPORTED_STRATEGY_CODES = frozenset({BROOKS_STRATEGY_CODE, FM_STRATEGY_CODE})


@dataclass(frozen=True, slots=True)
class SignalStrategyRecord:
    id: int
    strategy_code: str
    display_name: str
    enabled: bool
    engine_ready: bool
    private_channel_id: int | None
    private_channel_title: str | None
    private_channel_username: str | None
    updated_by_telegram_user_id: int | None
    created_at: datetime
    updated_at: datetime

    @property
    def effective_enabled(self) -> bool:
        return bool(self.enabled and self.engine_ready and self.private_channel_id is not None)
