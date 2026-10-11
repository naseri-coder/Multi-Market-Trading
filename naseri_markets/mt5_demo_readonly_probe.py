"""Explicit opt-in MT5 DEMO-only active exposure snapshot CLI.

Only read: terminal_info, account_info, positions_get and orders_get.
No login/password arguments, trade, live account or runtime integration.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .mt5_demo_exposure_audit_v1 import compare_demo_to_paper
from .mt5_demo_readonly_adapter_v1 import (
    DemoAccountExpectation,
    MT5DemoReadOnlyAdapterV1,
    MT5ReadRefused,
)


def run_once(args: argparse.Namespace, provider: Any) -> dict:
    if not args.connect_existing_demo_terminal:
        raise MT5ReadRefused("EXPLICIT_DEMO_TERMINAL_OPT_IN_REQUIRED")
    if not provider.initialize():
        raise MT5ReadRefused("MT5_TERMINAL_NOT_AVAILABLE")
    try:
        expected = DemoAccountExpectation(
            account_id=args.account_id, login=args.expected_login,
            server=args.expected_server,
        )
        observed = MT5DemoReadOnlyAdapterV1(provider, expected).capture()
        # Always diagnostic only. MT5 open order/position calls do NOT
        # establish complete order/deal execution history.
        result = {"snapshot": observed.wire(), "reconciliation_authority": False}
        if args.paper_ledger is not None:
            result["paper_audit"] = compare_demo_to_paper(
                observed, ledger=args.paper_ledger, account_id=args.account_id
            )
        return result
    finally:
        provider.shutdown()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--connect-existing-demo-terminal", action="store_true",
        help="Explicit opt-in; MT5.initialize() may start the terminal",
    )
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--expected-login", required=True, type=int)
    parser.add_argument("--expected-server", required=True)
    parser.add_argument(
        "--paper-ledger", help="Optional existing Stage-3/4 SQLite ledger (READ ONLY)",
    )
    args = parser.parse_args(argv)
    if not args.connect_existing_demo_terminal:
        parser.error("explicit --connect-existing-demo-terminal is mandatory")
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("OPTIONAL_MT5_PACKAGE_NOT_INSTALLED", file=sys.stderr)
        return 2
    try:
        report = run_once(args, mt5)
    except (MT5ReadRefused, ValueError) as exc:
        print(f"MT5_DEMO_READ_ONLY_REFUSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
