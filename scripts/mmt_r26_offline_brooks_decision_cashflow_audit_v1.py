#!/usr/bin/env python3
"""R26 offline signed-source Brooks V5 decision and two futures what-if audit.

All scenario inputs explicitly operator-provided; not an OOS performance
replay, not a trading client. Uses local genuine frozen source worker once.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from naseri_markets.brooks_frozen_decision_parity_mmt_r26_v1 import (
    R26CounterfactualPath,
    r26_audit_frozen_brooks_two_paths,
)
from naseri_markets.futures_economic_scenario_stage16_v1 import FundingMarkScenario

_MAX_FILE = 524288
_MAX_SCENARIOS = 2


def _read_bounded_file(path: Path) -> bytes:
    if (not path.is_absolute() or path.is_symlink() or not path.is_file()
            or path.stat().st_size < 1 or path.stat().st_size > _MAX_FILE):
        raise ValueError("R26_EXPLICIT_BOUNDED_LOCAL_FILE_REQUIRED")
    return path.read_bytes()


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for k, v in pairs:
        if k in result:
            raise ValueError("R26_DUPLICATE_SCENARIO_FIELD")
        result[k] = v
    return result


def _paths(raw: bytes) -> tuple[R26CounterfactualPath, R26CounterfactualPath]:
    try:
        doc = json.loads(
            raw.decode("ascii"), object_pairs_hook=_no_duplicate_keys,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
        if (type(doc) is not dict or set(doc) != {"protocol", "scenarios"}
                or doc["protocol"] != "MMT_R26_TWO_OPERATOR_HYPOTHETICAL_PATHS_V1"
                or type(doc["scenarios"]) is not list
                or len(doc["scenarios"]) != _MAX_SCENARIOS):
            raise ValueError()
        scenarios = []
        for entry in doc["scenarios"]:
            if (type(entry) is not dict or set(entry) != {
                    "label", "future_candles", "funding_events",
                    "expected_funding_instants"}):
                raise ValueError()
            events = tuple(FundingMarkScenario(
                at=datetime.fromisoformat(row["at"]),
                funding_rate=row["funding_rate"],
                referenced_mark_price=row["referenced_mark_price"],
            ) for row in entry["funding_events"])
            times = tuple(datetime.fromisoformat(t)
                          for t in entry["expected_funding_instants"])
            scenarios.append(R26CounterfactualPath(
                label=entry["label"],
                post_signal_closed_candles=tuple(entry["future_candles"]),
                expected_funding_instants=times,
                funding_mark_events=events,
            ))
    except (ValueError, TypeError, KeyError, UnicodeError) as exc:
        raise ValueError("R26_RESEARCH_SCENARIO_JSON_SCHEMA_REQUIRED") from exc
    return tuple(scenarios)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Brooks V5 source-frozen independent Decimal audit; offline",
    )
    parser.add_argument("--ack-research-only", action="store_true")
    parser.add_argument("--original-predecision-replay", required=True, type=Path)
    parser.add_argument("--two-futures-json", required=True, type=Path)
    parser.add_argument("--economic-metadata", required=True, type=Path)
    parser.add_argument("--economic-metadata-sha256", required=True)
    parser.add_argument("--quantity-contracts", required=True)
    parser.add_argument(
        "--frozen-source-dir", type=Path,
        default=Path(__file__).resolve().parents[1] / "production_source",
    )
    args = parser.parse_args(argv)
    if (args.ack_research_only is not True
            or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        raise SystemExit("R26_NONPRODUCTION_RESEARCH_ACK_REQUIRED")
    report = r26_audit_frozen_brooks_two_paths(
        original_replay_bytes=_read_bounded_file(args.original_predecision_replay),
        legacy_source=args.frozen_source_dir,
        counterfactuals=_paths(_read_bounded_file(args.two_futures_json)),
        economic_metadata_bytes=_read_bounded_file(args.economic_metadata),
        economic_metadata_sha256=args.economic_metadata_sha256,
        quantity_contracts=args.quantity_contracts,
        operator_ack=True,
    )
    print(json.dumps(report, sort_keys=True, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
