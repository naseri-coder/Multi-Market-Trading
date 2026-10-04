"""Framework-independent contracts for the future FM core."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from app.modules.signal_strategies.publisher import TelegramStrategyVipPublisher


@dataclass(frozen=True, slots=True)
class FMRuntimeContext:
    """Resources granted to an attached FM engine.

    The context intentionally exposes no Brooks-specific services. The FM core
    receives only the shared database boundary and its own strategy publisher.
    """

    database: Any
    publisher: TelegramStrategyVipPublisher
    private_channel_id: int


@runtime_checkable
class FMEngine(Protocol):
    """Minimal lifecycle port implemented by the future FM engine."""

    engine_id: str
    engine_version: str

    async def start(self, context: FMRuntimeContext) -> None:
        """Start the FM engine using only the supplied isolated context."""
        ...

    async def shutdown(self) -> None:
        """Stop all FM-owned background work and release FM-owned resources."""
        ...
