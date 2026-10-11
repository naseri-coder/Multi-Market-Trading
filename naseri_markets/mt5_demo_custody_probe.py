"""Opt-in one-shot MT5 DEMO history custody on the operator's own terminal.

Requires an explicitly selected DEMO login/server, read-only history scope and
dedicated SQLite path. No order_send, account login, risk action or deployment.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from .mt5_demo_evidence_custody_v1 import (
    DemoHistoryEvidenceCustodyV1,
    EvidenceCustodyRefused,
)
from .mt5_demo_history_readonly_v1 import MT5HistoryRefused
from .mt5_demo_readonly_adapter_v1 import DemoAccountExpectation, MT5ReadRefused


def run_once(args: argparse.Namespace, provider: Any) -> dict[str, Any]:
    if not args.connect_existing_demo_terminal:
        raise EvidenceCustodyRefused("EXPLICIT_DEMO_TERMINAL_OPT_IN_REQUIRED")
    if not isinstance(args.custody_db, str) or not args.custody_db.strip():
        raise EvidenceCustodyRefused("DEDICATED_CUSTODY_FILE_REQUIRED")
    expected = DemoAccountExpectation(
        account_id=args.account_id, login=args.expected_login,
        server=args.expected_server,
    )
    start, end = datetime.fromisoformat(args.start_utc), datetime.fromisoformat(
        args.end_utc
    )
    # This optional SDK may start a terminal, so CLI requires an explicit flag.
    if not provider.initialize():
        raise EvidenceCustodyRefused("DEMO_TERMINAL_NOT_AVAILABLE")
    try:
        with DemoHistoryEvidenceCustodyV1(Path(args.custody_db)) as custody:
            session = custody.open_read_session(provider, expected)
            receipt = custody.capture_and_append(
                provider, expected, start, end,
                session=session, action_id=args.action_id,
            )
            verified = custody.verify(expected.account_id)
            accounting = custody.accounting(expected.account_id)
            return {
                "receipt": receipt, "local_integrity": verified,
                "position_diagnostics": accounting,
                "may_send_order": False,
                "may_release_paper_risk": False,
                "may_unlock_stage4": False,
            }
    finally:
        provider.shutdown()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--connect-existing-demo-terminal", action="store_true")
    parser.add_argument("--account-id", required=True)
    parser.add_argument("--expected-login", type=int, required=True)
    parser.add_argument("--expected-server", required=True)
    parser.add_argument("--start-utc", required=True)
    parser.add_argument("--end-utc", required=True)
    parser.add_argument("--custody-db", required=True)
    parser.add_argument("--action-id", required=True)
    args = parser.parse_args(argv)
    if not args.connect_existing_demo_terminal:
        parser.error("explicit DEMO opt-in is required")
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("OPTIONAL_MT5_PACKAGE_NOT_INSTALLED", file=sys.stderr)
        return 2
    try:
        result = run_once(args, mt5)
    except (MT5ReadRefused, MT5HistoryRefused, EvidenceCustodyRefused, ValueError) as exc:
        print(f"MT5_DEMO_CUSTODY_REFUSED: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
