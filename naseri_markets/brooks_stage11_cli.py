"""Stage 11 offline-only manual operator replay and read-only diagnostics."""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .brooks_stage11_candle_replay import (
    BrooksStage11CandleReplay,
    BrooksStage11Refused,
    stage11_panel_summary,
)


def run_once(args: argparse.Namespace, *, environment: dict[str, str]) -> dict:
    if args.status:
        return stage11_panel_summary(args.state_dir)
    if (
        not args.ack_offline_paper_only
        or environment.get("MMT_NONPRODUCTION") != "1"
        or "MMT_PRODUCTION" in environment
        or args.account_id is None or args.signal_id is None
        or args.candles_file is None
    ):
        raise BrooksStage11Refused("EXPLICIT_NONPRODUCTION_FILE_REPLAY_REQUIRED")
    p = args.candles_file
    if p.is_symlink() or not p.is_file() or p.stat().st_size > 524288:
        raise BrooksStage11Refused("OFFLINE_REPLAY_FILE_INVALID")
    content = p.read_bytes()
    return BrooksStage11CandleReplay(args.state_dir).replay(
        account_id=args.account_id, signal_id=args.signal_id,
        candles_json=content, ack_offline_only=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--status", action="store_true")
    choice.add_argument("--replay-file", action="store_true")
    parser.add_argument("--account-id")
    parser.add_argument("--signal-id")
    parser.add_argument("--candles-file", type=Path)
    parser.add_argument("--ack-offline-paper-only", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run_once(args, environment=dict(os.environ))
    except (BrooksStage11Refused, OSError, ValueError):
        # The report/error never prints private candle data or account details.
        print("STAGE11_OFFLINE_PAPER_REPLAY_REFUSED", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
