"""Metadata registry; does not import, start, or trust a private strategy engine."""

from __future__ import annotations

from .contracts import EngineDescriptor, Market, SignalIntent


class EngineRegistry:
    def __init__(self) -> None:
        self._descriptors: dict[str, EngineDescriptor] = {}

    def register(self, descriptor: EngineDescriptor) -> None:
        if descriptor.engine_id in self._descriptors:
            raise ValueError("duplicate engine identity")
        self._descriptors[descriptor.engine_id] = descriptor

    def get(self, engine_id: str) -> EngineDescriptor | None:
        return self._descriptors.get(engine_id)

    def validate_intent(self, signal: SignalIntent) -> None:
        descriptor = self.get(signal.engine_id)
        if descriptor is None:
            raise ValueError("unregistered engine")
        if descriptor.version != signal.engine_version:
            raise ValueError("engine version mismatch")
        if signal.instrument.market not in descriptor.supported_markets:
            raise ValueError("engine market mismatch")

    def engines_for(self, market: Market) -> tuple[EngineDescriptor, ...]:
        return tuple(
            descriptor for descriptor in self._descriptors.values()
            if market in descriptor.supported_markets
        )
