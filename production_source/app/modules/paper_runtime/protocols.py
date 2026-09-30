"""External side-effect protocols for PAPER runtime."""

from __future__ import annotations

from typing import Protocol, Any

from app.modules.paper_runtime.entities import PaperPublishPayload


class PaperPublisher(Protocol):
    async def publish(self, payload: PaperPublishPayload) -> str: ...


class TelegramBotLike(Protocol):
    async def send_photo(self, **kwargs: Any) -> Any: ...
