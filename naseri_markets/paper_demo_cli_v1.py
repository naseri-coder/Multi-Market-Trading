"""One installed, restartable, trusted PUBLIC toy PAPER journey (NO live I/O).

Uses the pre-existing TrustedLocalCustomHost and its atomic SQLite journal.
Never executes a third-party candidate, places orders, or contacts Telegram.
The toy code is shipped in this public wheel; execution still needs an explicit
operator acknowledgement. This is not the Stage 3-12 unified runtime.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

from .custom_cli import _export_demo
from .trusted_custom import (
    MAX_QUOTE,
    TRUST_ACK,
    LocalCustomRefused,
    TrustedLocalCustomHost,
    _read_file,
)

DEMO_ENGINE = "public_toy_demo"


class PaperDemoRefused(ValueError):
    """A required isolation, identity or explicit-consent fence failed."""


def _scope(root: Path, *, new: bool) -> Path:
    if not root.is_absolute() or root.is_symlink() or not root.parent.is_dir():
        raise PaperDemoRefused("ABSOLUTE_SAFE_STATE_DIRECTORY_REQUIRED")
    if root.parent.is_symlink() or (new and root.exists()):
        raise PaperDemoRefused("NEW_PRIVATE_STATE_DIRECTORY_REQUIRED")
    if not new and (not root.is_dir() or not (root / "custom_paper.db").is_file()
                    or (root / "custom_paper.db").is_symlink()):
        raise PaperDemoRefused("INITIALIZED_PAPER_STATE_REQUIRED")
    return root


def _require_nonproduction() -> None:
    if os.environ.get("MMT_NONPRODUCTION") != "1" or os.environ.get("MMT_PRODUCTION") == "1":
        raise PaperDemoRefused("EXPLICIT_NONPRODUCTION_ENV_REQUIRED")


def _safe_state(host: TrustedLocalCustomHost):
    state = host.get(DEMO_ENGINE)
    if state is None or state.engine_version != "1.0.0":
        raise PaperDemoRefused("PUBLIC_TOY_IDENTITY_MISSING")
    return state


def _inspect(host: TrustedLocalCustomHost) -> dict:
    state = _safe_state(host)
    signals = host.signals(DEMO_ENGINE)
    return {
        "phase": "TRUSTED_PUBLIC_TOY_OFFLINE_PAPER",
        "engine_id": DEMO_ENGINE,
        "enabled": state.enabled,
        "revision": state.revision,
        "descriptor_sha256": state.descriptor_sha256,
        "code_sha256": state.code_sha256,
        "paper_signal_count": len(signals),
        "paper_signal_ids": [s["signal_id"] for s in signals],
        "journal_sha256": hashlib.sha256(
            json.dumps(signals, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "telegram_sent": False,
        "broker_order_sent": False,
        "untrusted_plugin_sandboxed": False,
        "release_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True,
                        help="New absolute private directory outside production")
    actions = parser.add_subparsers(dest="action", required=True)
    initialize = actions.add_parser("init", help="Pin bundled public toy; stays disabled")
    initialize.add_argument("--ack-reviewed-public-toy", action="store_true")
    enable = actions.add_parser("enable", help="CAS enable exact reviewed toy")
    enable.add_argument("--revision", type=int, required=True)
    enable.add_argument("--descriptor-sha256", required=True)
    replay = actions.add_parser("replay", help="One offline synthetic/replay Bid/Ask quote")
    replay.add_argument("--quote", type=Path, help="Default: state/sample/quote.json")
    replay.add_argument("--ack-offline-replay", action="store_true")
    actions.add_parser("inspect", help="Inspect durable PAPER evidence after restart")
    disable = actions.add_parser("disable", help="CAS disable; keep immutable PAPER history")
    disable.add_argument("--revision", type=int, required=True)
    args = parser.parse_args(argv)
    try:
        _require_nonproduction()
        if args.action == "init":
            if args.ack_reviewed_public_toy is not True:
                raise PaperDemoRefused("EXPLICIT_REVIEW_OF_BUNDLED_TOY_REQUIRED")
            root = _scope(args.state_dir, new=True)
            root.mkdir(mode=0o700)
            with TrustedLocalCustomHost(root) as host:
                fixture = _export_demo(root / "sample")
                created = host.register(
                    root / "sample" / "descriptor.json",
                    root / "sample" / "public_toy_demo.py",
                    descriptor_sha256=fixture["descriptor_sha256"],
                    code_sha256=fixture["code_sha256"], trust_ack=TRUST_ACK,
                )
                if created.enabled or created.revision != 1:
                    raise PaperDemoRefused("DEMO_MUST_START_DISABLED")
                result = _inspect(host)
                result["action"] = "INITIALIZED_DISABLED"
        else:
            root = _scope(args.state_dir, new=False)
            with TrustedLocalCustomHost(root) as host:
                state = _safe_state(host)
                if args.action == "enable":
                    if args.revision != state.revision:
                        raise PaperDemoRefused("STALE_REVISION")
                    host.toggle(DEMO_ENGINE, enabled=True, expected_revision=args.revision,
                                descriptor_sha256=args.descriptor_sha256)
                    result = _inspect(host)
                    result["action"] = "EXPLICITLY_ENABLED_PAPER_ONLY"
                elif args.action == "replay":
                    if args.ack_offline_replay is not True:
                        raise PaperDemoRefused("EXPLICIT_REPLAY_ACK_REQUIRED")
                    quote = args.quote or root / "sample" / "quote.json"
                    # Existing host enforces replay/synthetic provenance, CAS,
                    # publisher snapshot bytes and an atomic PAPER journal.
                    receipt = host.paper(DEMO_ENGINE, _read_file(quote, MAX_QUOTE))
                    result = _inspect(host)
                    result["action"] = "OFFLINE_REPLAY"
                    result["receipt"] = receipt
                elif args.action == "disable":
                    if args.revision != state.revision:
                        raise PaperDemoRefused("STALE_REVISION")
                    host.toggle(DEMO_ENGINE, enabled=False, expected_revision=args.revision)
                    result = _inspect(host)
                    result["action"] = "DISABLED_HISTORY_PRESERVED"
                else:
                    result = _inspect(host)
                    result["action"] = "READ_PAPER_HISTORY"
        print(json.dumps(result, sort_keys=True, ensure_ascii=True))
        return 0
    except (PaperDemoRefused, LocalCustomRefused, OSError, ValueError, sqlite3.Error) as exc:
        # No source bytes, full filesystem path, token or quote content in errors.
        print("PAPER_DEMO_REFUSED:" + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
