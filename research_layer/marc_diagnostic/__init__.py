"""MARC R2 research diagnostics.

This package describes why the frozen MARC R1 baseline behaved as observed.
It does not change MARC signal rules or authorize runtime use.
"""

from research_layer.marc_diagnostic.analysis import (
    MARCTradeDiagnostic,
    build_diagnostic_report,
    diagnose_trades,
)

__all__ = [
    "MARCTradeDiagnostic",
    "build_diagnostic_report",
    "diagnose_trades",
]
