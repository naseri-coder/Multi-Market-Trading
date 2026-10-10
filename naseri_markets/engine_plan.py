"""Offline, fail-closed module installation PLAN; never loads a strategy.

A public installation manifest is intentionally metadata-only. Private engines
can be DECLARED but cannot be installed, enabled, fetched or executed by it.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

MARKETS = frozenset({"crypto", "forex", "index", "metal"})
SOURCES = frozenset({"bundled_legacy", "private_external"})
IDENTITY = re.compile(r"[a-z][a-z0-9_]{2,39}\Z")
VERSION = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")


@dataclass(frozen=True, slots=True)
class PlannedEngine:
    engine_id: str
    version: str
    market: str
    source: str
    enabled: bool
    status: str


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DUPLICATE_MANIFEST_KEY")
        result[key] = value
    return result


def plan(path: str | Path) -> tuple[PlannedEngine, ...]:
    candidate = Path(path)
    if not candidate.is_file() or candidate.is_symlink() or candidate.stat().st_size > 65536:
        raise ValueError("MANIFEST_MUST_BE_SMALL_REGULAR_FILE")
    obj = json.loads(candidate.read_text(encoding="utf-8"), object_pairs_hook=_unique)
    if not isinstance(obj, dict) or set(obj) != {"schema_version", "engines"}:
        raise ValueError("UNSUPPORTED_PLAN_SCHEMA")
    if type(obj["schema_version"]) is not int or obj["schema_version"] != 1:
        raise ValueError("UNSUPPORTED_PLAN_VERSION")
    rows = obj["engines"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 32:
        raise ValueError("INVALID_PLAN_ENGINE_COUNT")
    seen: set[str] = set()
    result: list[PlannedEngine] = []
    for item in rows:
        if not isinstance(item, dict) or set(item) != {
            "engine_id", "version", "market", "source", "enabled"
        }:
            raise ValueError("INVALID_ENGINE_METADATA")
        ident = item["engine_id"]
        version = item["version"]
        market = item["market"]
        source = item["source"]
        enabled = item["enabled"]
        if not isinstance(ident, str) or not IDENTITY.fullmatch(ident) or ident in seen:
            raise ValueError("INVALID_OR_DUPLICATE_ENGINE_ID")
        if not isinstance(version, str) or not VERSION.fullmatch(version):
            raise ValueError("INVALID_ENGINE_VERSION")
        if not isinstance(market, str) or market not in MARKETS:
            raise ValueError("INVALID_ENGINE_MARKET")
        if not isinstance(source, str) or source not in SOURCES:
            raise ValueError("INVALID_ENGINE_SOURCE")
        if enabled is not False:
            raise ValueError("A5_CANNOT_ENABLE_OR_RUN_ENGINES")
        seen.add(ident)
        result.append(
            PlannedEngine(
                ident, version, market, source, False,
                "LEGACY_RELEASE_ONLY" if source == "bundled_legacy"
                else "PRIVATE_PROVISIONING_REQUIRED",
            )
        )
    return tuple(result)
