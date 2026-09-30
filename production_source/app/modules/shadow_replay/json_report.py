"""Deterministic JSON serialization for Phase 8 reports."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json

from app.modules.shadow_replay.entities import ShadowReplayReport


def _default(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"unsupported report value: {type(value)!r}")


def report_to_json(report: ShadowReplayReport, *, pretty: bool = True) -> str:
    return json.dumps(
        asdict(report),
        default=_default,
        ensure_ascii=False,
        sort_keys=True,
        indent=2 if pretty else None,
        separators=None if pretty else (",", ":"),
    )
