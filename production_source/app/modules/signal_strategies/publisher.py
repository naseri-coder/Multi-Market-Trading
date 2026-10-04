"""Shared VIP publisher preserving the existing signal output format."""

from __future__ import annotations

from app.modules.live_vip_runtime.publisher import TelegramLiveVipPublisher
from app.modules.paper_runtime.protocols import TelegramBotLike


class TelegramStrategyVipPublisher(TelegramLiveVipPublisher):
    """Publish any strategy through the exact existing VIP signal template."""

    def __init__(self, *, bot: TelegramBotLike, private_channel_id: int) -> None:
        super().__init__(bot=bot, vip_channel_id=private_channel_id)
