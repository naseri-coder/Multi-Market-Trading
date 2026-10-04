"""In-process registry for the optional FM engine implementation."""

from __future__ import annotations

from app.modules.fm_runtime.contracts import FMEngine


class FMEngineRegistry:
    """Hold at most one explicitly connected FM engine."""

    def __init__(self) -> None:
        self._engine: FMEngine | None = None

    @property
    def ready(self) -> bool:
        return self._engine is not None

    def get(self) -> FMEngine | None:
        return self._engine

    def register(self, engine: FMEngine) -> None:
        if not isinstance(engine, FMEngine):
            raise TypeError("engine must implement the FMEngine protocol")
        if self._engine is not None and self._engine is not engine:
            raise RuntimeError("an FM engine is already registered")
        if not engine.engine_id.strip() or not engine.engine_version.strip():
            raise ValueError("FM engine identity and version are required")
        self._engine = engine

    def clear(self) -> None:
        self._engine = None


default_fm_engine_registry = FMEngineRegistry()
