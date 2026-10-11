"""Read-only Stage-12 Brooks cohort assessment; no runtime mutations."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

from .brooks_stage12_research_audit import (
    MAX_MANIFEST_BYTES, Stage12ResearchRefused, evaluate_brooks_stage12,
)


def run_once(args: argparse.Namespace, *, environment: dict[str, str]) -> dict:
    if (
        environment.get("MMT_NONPRODUCTION") != "1"
        or environment.get("MMT_PRODUCTION") == "1"
        or args.ack_offline_research_only is not True
    ):
        raise Stage12ResearchRefused("STAGE12_NONPRODUCTION_OPTIN_REQUIRED")
    manifest = args.manifest
    if manifest.is_symlink() or not manifest.is_file() or manifest.stat().st_size > MAX_MANIFEST_BYTES:
        raise Stage12ResearchRefused("STAGE12_MANIFEST_FILE_UNSAFE")
    return evaluate_brooks_stage12(args.state_dir, manifest.read_bytes())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--ack-offline-research-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = run_once(args, environment=dict(os.environ))
    except (Stage12ResearchRefused, OSError, ValueError, KeyError, sqlite3.Error):
        print("STAGE12_READONLY_COHORT_AUDIT_REFUSED", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
