"""MARC strategy runtime connection boundary.

The MARC trading core is intentionally not implemented here. This package only
provides the isolated runtime port that a validated MARC runtime adapter must implement.
"""

from app.modules.marc_runtime.contracts import MARCEngine, MARCRuntimeContext
from app.modules.marc_runtime.coordinator import MARCRuntimeCoordinator
from app.modules.marc_runtime.registry import (
    MARCEngineRegistry,
    default_marc_engine_registry,
)

__all__ = [
    "MARCEngine",
    "MARCEngineRegistry",
    "MARCRuntimeContext",
    "MARCRuntimeCoordinator",
    "default_marc_engine_registry",
]
