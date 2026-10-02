"""Reporting-only helpers for separating Cold Start admissions.

This module is not wired into production reporting in Phase 4.2.41.85.
"""
from __future__ import annotations
from typing import Any
from app.modules.signal_intelligence.cold_start_policy import COLD_START_LABEL

def include_in_calibrated_at_admission_reporting(analysis_metadata: dict[str, Any] | None) -> bool:
    metadata=dict(analysis_metadata or {})
    if metadata.get('admission_gate')==COLD_START_LABEL:
        return False
    if metadata.get('statistically_calibrated_at_admission') is False:
        return False
    return True
