"""Manual R29 Termux entrypoint. OFFLINE archive input only; never downloads."""
from __future__ import annotations

import argparse
import json
import os
import stat
from pathlib import Path

from naseri_markets.brooks_future_shadow_paper_mmt_r29_v1 import (
    R29ShadowRefused, review_r29_one_closed_bar_shadow,
    save_r29_receipt_exclusive,
)


def _existing_receipt(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_nlink != 1:
        raise R29ShadowRefused("R29_PREVIOUS_RECEIPT_PATH_REFUSED")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise R29ShadowRefused("R29_PREVIOUS_RECEIPT_NOT_PRIVATE")
    with path.open("rb") as stream:
        data = stream.read(16385)
    if not 10 <= len(data) <= 16384:
        raise R29ShadowRefused("R29_PREVIOUS_RECEIPT_SIZE_REFUSED")
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="R29 offline, one original-source Brooks shadow cutoff"
    )
    parser.add_argument("--witness-dir", required=True, type=Path)
    parser.add_argument("--batch-dir", action="append", required=True, type=Path)
    parser.add_argument("--frozen-source", required=True, type=Path)
    parser.add_argument("--decision-bar-index", required=True, type=int)
    parser.add_argument("--previous-receipt", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--ack-nonproduction-no-order", action="store_true")
    args = parser.parse_args(argv)
    if (not args.ack_nonproduction_no_order
            or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        parser.error("R29_EXPLICIT_DISCONNECTED_RESEARCH_ONLY")
    try:
        previous = (_existing_receipt(args.previous_receipt)
                    if args.previous_receipt else None)
        report, raw = review_r29_one_closed_bar_shadow(
            witness_directory=args.witness_dir.resolve(),
            previous_directories=tuple(p.absolute() for p in args.batch_dir),
            frozen_source=args.frozen_source.resolve(),
            decision_bar_index=args.decision_bar_index,
            previous_r29_receipt_bytes=previous,
            operator_ack=True,
        )
        if raw is not None:
            saved = save_r29_receipt_exclusive(
                directory=args.output_dir.absolute(),
                receipt=raw,
                operator_ack=True,
            )
            # Do not claim independent market-source certification.
            report["saved_checkpoint_filename"] = saved.name
        print(json.dumps(report, sort_keys=True, ensure_ascii=True))
    except (R29ShadowRefused, ValueError, OSError):
        # No untrusted input or path is echoed to the operator.
        print(json.dumps({
            "protocol": "MMT_R29_CLI_OFFLINE",
            "status": "REFUSED_REVIEW_REQUIRED",
        }))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
