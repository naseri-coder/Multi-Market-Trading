"""Stage 9 operator MT5 DEMO read-only smoke; sanitized output only.

SDK inspection mode does NOT initialize a terminal. DEMO observation
mode requires explicit opt-in *and* acknowledgement that mt5.initialize()
may start an installed terminal and reuse its last logged-in account.
Never log in, switch account, send an order, or write broker/PAPER data.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import Any

from .mt5_demo_operator_smoke_v1 import (
    MT5DemoSmokeRefused,
    observe_demo_smoke,
    preflight_window,
    sdk_contract_preflight,
)
from .mt5_demo_readonly_adapter_v1 import DemoAccountExpectation


def run_once(
    args: argparse.Namespace, provider: Any, *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Provider-injected entrypoint: no MT5 import/initialize before consent."""
    if args.sdk_preflight_only:
        return sdk_contract_preflight(provider)
    if (
        not args.connect_existing_demo_terminal
        or not args.ack_initialize_may_start_terminal
    ):
        raise MT5DemoSmokeRefused("EXPLICIT_DEMO_OPT_IN_AND_INITIALIZE_ACK_REQUIRED")
    expected = DemoAccountExpectation(
        account_id=args.account_id,
        login=args.expected_login, server=args.expected_server,
    )
    start = datetime.fromisoformat(args.start_utc)
    end = datetime.fromisoformat(args.end_utc)
    preflight_window(start, end, now=now)
    sdk_contract_preflight(provider)
    try:
        if provider.initialize() is not True:
            raise MT5DemoSmokeRefused("MT5_TERMINAL_INITIALIZE_FAILED")
        return observe_demo_smoke(provider, expected, start, end, now=now)
    finally:
        provider.shutdown()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sdk-preflight-only", action="store_true",
        help="Check optional SDK methods only; do not start or access MT5",
    )
    parser.add_argument("--connect-existing-demo-terminal", action="store_true")
    parser.add_argument("--ack-initialize-may-start-terminal", action="store_true")
    parser.add_argument("--account-id")
    parser.add_argument("--expected-login", type=int)
    parser.add_argument("--expected-server")
    parser.add_argument("--start-utc")
    parser.add_argument("--end-utc")
    args = parser.parse_args(argv)
    if not args.sdk_preflight_only:
        if (
            not args.connect_existing_demo_terminal
            or not args.ack_initialize_may_start_terminal
        ):
            parser.error("explicit DEMO connection and terminal-start acknowledgement required")
        if not (
            args.account_id and args.expected_login and args.expected_server
            and args.start_utc and args.end_utc
        ):
            parser.error("pinned DEMO login/server/account and exact UTC window are required")
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("BLOCKED_OPTIONAL_MT5_SDK_NOT_INSTALLED", file=sys.stderr)
        return 2
    try:
        report = run_once(args, mt5)
    except Exception as exc:
        # Do NOT echo arbitrary provider exceptions: some brokers' SDKs
        # include login/server/tickets in error details.
        if isinstance(exc, (MT5DemoSmokeRefused, ValueError)):
            # Only our own fixed error codes appear in stdout/stderr.
            status = "SMOKE_DEMO_READ_REFUSED"
        else:
            status = "SMOKE_PROVIDER_READ_EXCEPTION"
        print(status, file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, ensure_ascii=True))
    return 0 if report.get("status", "PREFLIGHT") == "PASS_DEMO_READONLY_API_OBSERVATION" or args.sdk_preflight_only else 3


if __name__ == "__main__":
    raise SystemExit(main())
