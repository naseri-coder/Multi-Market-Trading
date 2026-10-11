"""Explicit one-shot MT5 DEMO history probe, no order/send/trading methods.

The operator selects an exact timezone-aware start/end. Any failure exits
without publishing a partial window or changing a PAPER risk ledger.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import Any

from .mt5_demo_history_audit_v1 import audit_demo_history
from .mt5_demo_history_readonly_v1 import MT5DemoHistoryReaderV1, MT5HistoryRefused
from .mt5_demo_readonly_adapter_v1 import DemoAccountExpectation, MT5ReadRefused


def run_once(args: argparse.Namespace, provider: Any) -> dict[str, Any]:
    if not args.connect_existing_demo_terminal:
        raise MT5HistoryRefused("EXPLICIT_MT5_DEMO_OPT_IN_REQUIRED")
    # No login, password, server, path or "portable" trading parameters.
    if not provider.initialize():
        raise MT5HistoryRefused("MT5_TERMINAL_CONNECTION_UNAVAILABLE")
    try:
        expected = DemoAccountExpectation(
            account_id=args.account_id, login=args.expected_login,
            server=args.expected_server,
        )
        reader = MT5DemoHistoryReaderV1(provider, expected)
        snapshot = reader.capture(
            datetime.fromisoformat(args.start_utc),
            datetime.fromisoformat(args.end_utc),
        )
        report = audit_demo_history(
            snapshot, paper_ledger=args.paper_ledger,
            account_id=args.account_id,
        )
        return {
            "history": snapshot.wire(),
            "history_audit": report,
            "reconciliation_authority": False,
            "account_unhalt_authority": False,
            "order_execution_authority": False,
        }
    finally:
        provider.shutdown()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connect-existing-demo-terminal", action="store_true")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--expected-login", type=int, required=True)
    parser.add_argument("--expected-server", required=True)
    parser.add_argument("--start-utc", required=True,
                        help="ISO-8601 with offset, e.g. 2026-10-01T00:00:00+00:00")
    parser.add_argument("--end-utc", required=True,
                        help="ISO-8601 with offset, e.g. 2026-10-08T00:00:00+00:00")
    parser.add_argument("--paper-ledger", default=None,
                        help="Optional disposable Stage-3 PAPER DB opened READ ONLY")
    args = parser.parse_args(argv)
    if not args.connect_existing_demo_terminal:
        parser.error("explicit --connect-existing-demo-terminal is required")
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("OPTIONAL_MT5_PACKAGE_NOT_INSTALLED", file=sys.stderr)
        return 2
    try:
        output = run_once(args, mt5)
    except (MT5ReadRefused, MT5HistoryRefused, ValueError) as exc:
        print(f"MT5_DEMO_HISTORY_READ_ONLY_REFUSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(output, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
