"""Framework-independent contracts for the future MARC core."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from app.modules.signal_strategies.publisher import TelegramStrategyVipPublisher


@dataclass(frozen=True, slots=True)
class MARCRuntimeContext:
    """Resources granted to an attached MARC engine.

    The context intentionally exposes no Brooks-specific services. The MARC core
    receives only the shared database boundary and its own strategy publisher.
    """

    database: Any
    publisher: TelegramStrategyVipPublisher
    private_channel_id: int


@runtime_checkable
class MARCEngine(Protocol):
    """Minimal lifecycle port implemented by the validated MARC runtime adapter."""

    engine_id: str
    engine_version: str

    async def start(self, context: MARCRuntimeContext) -> None:
        """Start the MARC engine using only the supplied isolated context."""
        ...

    async def shutdown(self) -> None:
        """Stop all MARC-owned background work and release MARC-owned resources."""
        ...
