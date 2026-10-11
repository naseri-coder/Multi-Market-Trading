"""Explicitly opted-in one-shot read-only MT5 DEMO evidence requery.

Uses an EXISTING Stage-7 custody file in SQLite mode=ro. No database writes,
trade API calls, terminal login, secret arguments or actual broker operations.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import Any

from .mt5_demo_independent_reverify_v1 import (
    MT5DemoIndependentReverifierV1,
    MT5ReverificationRefused,
)
from .mt5_demo_readonly_adapter_v1 import DemoAccountExpectation, MT5ReadRefused


def run_once(args: argparse.Namespace, provider: Any) -> dict[str, Any]:
    if not args.connect_existing_demo_terminal:
        raise MT5ReverificationRefused("EXPLICIT_DEMO_TERMINAL_OPT_IN_REQUIRED")
    expected = DemoAccountExpectation(
        account_id=args.account_id,
        login=args.expected_login,
        server=args.expected_server,
    )
    start = datetime.fromisoformat(args.start_utc)
    end = datetime.fromisoformat(args.end_utc)
    if not provider.initialize():
        raise MT5ReverificationRefused("MT5_DEMO_TERMINAL_UNAVAILABLE")
    try:
        return MT5DemoIndependentReverifierV1(
            provider, expected, custody_path=args.custody_db,
        ).verify(start, end)
    finally:
        provider.shutdown()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connect-existing-demo-terminal", action="store_true")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--expected-login", required=True, type=int)
    parser.add_argument("--expected-server", required=True)
    parser.add_argument("--custody-db", required=True)
    parser.add_argument("--start-utc", required=True)
    parser.add_argument("--end-utc", required=True)
    args = parser.parse_args(argv)
    if not args.connect_existing_demo_terminal:
        parser.error("explicit --connect-existing-demo-terminal is required")
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("OPTIONAL_MT5_PACKAGE_NOT_INSTALLED", file=sys.stderr)
        return 2
    try:
        report = run_once(args, mt5)
    except (MT5ReadRefused, MT5ReverificationRefused, ValueError) as exc:
        print(f"MT5_DEMO_REQUERY_REFUSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
