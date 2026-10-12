"""Stage 21B manual CLI: private local official-format captures -> PAPER only.

No fetching, polling, brokerage, Telegram, credential reads or third-party
strategy imports. Requires two real-format Kline JSON files and one official
Stage-6 public-contract JSON file prepared by the trusted operator.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from datetime import UTC, datetime
from pathlib import Path

from .captured_paper_pilot_stage21b_v1 import (
    CapturedPaperRefused, run_captured_paper_pilot,
)
from .kucoin_futures_replay_stage21_v1 import (
    FuturesKlineRequest, MAX_BYTES,
)
from .public_futures_contracts import MAX_METADATA_BYTES
from .read_only_provider_adapters_v1 import futures_snapshot


def _timestamp(raw: str) -> datetime:
    try:
        result = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("ISO_UTC_TIMESTAMP_REQUIRED") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise argparse.ArgumentTypeError("UTC_OFFSET_REQUIRED")
    return result.astimezone(UTC)


def _private_data(path: Path, *, limit: int) -> bytes:
    path = Path(path)
    if (not path.is_absolute() or path.is_symlink() or not path.is_file()
            or path.parent.is_symlink() or not path.parent.is_dir()
            or path.parent.stat().st_uid != os.geteuid()
            or stat.S_IMODE(path.parent.stat().st_mode) & 0o077):
        raise CapturedPaperRefused("OWNER_PRIVATE_CAPTURE_REQUIRED")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as source:
        info = os.fstat(source.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) & 0o077
                or not 1 <= info.st_size <= limit):
            raise CapturedPaperRefused("PRIVATE_BOUNDED_CAPTURE_REQUIRED")
        data = source.read(limit + 1)
    if len(data) > limit:
        raise CapturedPaperRefused("OVERSIZED_CAPTURE")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--metadata-json", type=Path, required=True)
    parser.add_argument("--metadata-asof", type=_timestamp, required=True)
    parser.add_argument("--capture-observed-at", type=_timestamp, required=True)
    for prefix in ("first", "second"):
        parser.add_argument("--" + prefix + "-symbol", required=True)
        parser.add_argument("--" + prefix + "-timeframe", required=True,
                            choices=("1m","5m","15m","30m","1h","4h","12h","1d"))
        parser.add_argument("--" + prefix + "-start", type=_timestamp, required=True)
        parser.add_argument("--" + prefix + "-end", type=_timestamp, required=True)
        parser.add_argument("--" + prefix + "-json", type=Path, required=True)
    parser.add_argument("--no-dry-run-signals", action="store_true")
    parser.add_argument("--ack-offline-captured-paper", action="store_true")
    opts = parser.parse_args(argv)
    try:
        if (not opts.ack_offline_captured_paper
                or os.environ.get("MMT_NONPRODUCTION") != "1"
                or os.environ.get("MMT_PRODUCTION") == "1"):
            raise CapturedPaperRefused("EXPLICIT_NONPRODUCTION_ACK_REQUIRED")
        metadata = futures_snapshot(
            "kucoin", _private_data(opts.metadata_json, limit=MAX_METADATA_BYTES),
            observed_at=opts.metadata_asof)
        datasets = []
        for prefix in ("first", "second"):
            query = FuturesKlineRequest(
                getattr(opts, prefix + "_symbol"), getattr(opts, prefix + "_timeframe"),
                getattr(opts, prefix + "_start"), getattr(opts, prefix + "_end"))
            raw = _private_data(getattr(opts, prefix + "_json"), limit=MAX_BYTES)
            datasets.append((query, raw))
        report = run_captured_paper_pilot(
            opts.state_dir, datasets=tuple(datasets),
            provider_snapshot=metadata,
            observed_at=opts.capture_observed_at, operator_ack=True,
            dry_run_signals=not opts.no_dry_run_signals)
    except (ValueError, RuntimeError, OSError):
        print("STAGE21B_CAPTURED_PAPER_REFUSED", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
