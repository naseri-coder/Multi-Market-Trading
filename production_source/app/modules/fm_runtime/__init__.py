"""FM strategy runtime connection boundary.

The FM trading core is intentionally not implemented here. This package only
provides the isolated runtime port that a future FM engine must implement.
"""

from app.modules.fm_runtime.contracts import FMEngine, FMRuntimeContext
from app.modules.fm_runtime.coordinator import FMRuntimeCoordinator
from app.modules.fm_runtime.registry import (
    FMEngineRegistry,
    default_fm_engine_registry,
)

__all__ = [
    "FMEngine",
    "FMEngineRegistry",
    "FMRuntimeContext",
    "FMRuntimeCoordinator",
    "default_fm_engine_registry",
]
