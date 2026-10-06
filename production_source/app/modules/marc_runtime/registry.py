"""In-process registry for the optional MARC engine implementation."""

from __future__ import annotations

from app.modules.marc_runtime.contracts import MARCEngine


class MARCEngineRegistry:
    """Hold at most one explicitly connected MARC engine."""

    def __init__(self) -> None:
        self._engine: MARCEngine | None = None

    @property
    def ready(self) -> bool:
        return self._engine is not None

    def get(self) -> MARCEngine | None:
        return self._engine

    def register(self, engine: MARCEngine) -> None:
        if not isinstance(engine, MARCEngine):
            raise TypeError("engine must implement the MARCEngine protocol")
        if self._engine is not None and self._engine is not engine:
            raise RuntimeError("an MARC engine is already registered")
        if not engine.engine_id.strip() or not engine.engine_version.strip():
            raise ValueError("MARC engine identity and version are required")
        self._engine = engine

    def clear(self) -> None:
        self._engine = None


default_marc_engine_registry = MARCEngineRegistry()
