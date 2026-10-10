"""Explicit operator CLI for locally trusted public Custom PAPER engines.

Nothing executes on import. No public plugin marketplace, live trading,
credentials, Telegram posting or source installation from the network.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
from dataclasses import asdict
from pathlib import Path

from .trusted_custom import LocalCustomRefused, TRUST_ACK, TrustedLocalCustomHost


def _export_demo(directory: str | Path) -> dict:
    output = Path(directory).absolute()
    if (output.exists() or output.is_symlink() or not output.parent.is_dir()
            or output.parent.is_symlink()):
        raise LocalCustomRefused("CUSTOM_DEMO_NEW_DIRECTORY_REQUIRED")
    output.mkdir(mode=0o700)
    worker = Path(__file__).with_name("public_demo_custom_worker.py").read_bytes()
    # A21 registration remains NON-EXECUTABLE metadata. Local code trust is
    # separately and explicitly granted by the operator at register time.
    manifest = {
        "schema_version": 1,
        "engine_id": "public_toy_demo", "engine_version": "1.0.0",
        "publisher": "mmt.demo", "markets": ["crypto","forex","index","metal"],
        "access_policy": "public_custom", "strategy_family": "generic_custom",
        "adapter": "external_contract", "abi_version": 1,
        "distribution": "metadata_only",
        "artifact_policy": "no_executable_or_ciphertext",
        "permissions": ["paper_analysis"],
        "runtime_mode": "replay_or_synthetic", "execution_authorized": False,
    }
    descriptor = json.dumps(manifest, sort_keys=True,
                            separators=(",", ":")).encode()
    quote = {
        "market": "index", "provider": "mt5:synthetic", "symbol": "US30",
        "timezone": "America/New_York", "quote_currency": "USD",
        "occurred_at": "2026-10-09T13:30:00+00:00",
        "bid": "43000", "ask": "43001", "origin": "synthetic",
    }
    samples = {
        "descriptor.json": descriptor,
        "public_toy_demo.py": worker,
        "quote.json": json.dumps(quote, sort_keys=True,
                                 separators=(",", ":")).encode(),
    }
    for name, payload in samples.items():
        dest = output / name
        fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as file:
            file.write(payload)
    return {
        "status": "TOY_PUBLIC_SAMPLE_EXPORTED_NO_EXECUTION",
        "directory": str(output),
        "descriptor_sha256": hashlib.sha256(descriptor).hexdigest(),
        "code_sha256": hashlib.sha256(worker).hexdigest(),
        "nonproduction": True, "trust_required": True,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--state-dir", type=Path,
                   help="Explicit private 0700 directory outside the public repo")
    commands = p.add_subparsers(dest="command", required=True)
    sample = commands.add_parser("sample", help="Export public toy plugin and replay quote")
    sample.add_argument("--output-dir", type=Path, required=True)
    register = commands.add_parser("register", help="Snapshot operator-trusted public code")
    register.add_argument("--descriptor", type=Path, required=True)
    register.add_argument("--code", type=Path, required=True)
    register.add_argument("--descriptor-sha256", required=True)
    register.add_argument("--code-sha256", required=True)
    register.add_argument("--trust-local-code", action="store_true")
    commands.add_parser("list")
    for name in ("enable", "disable"):
        action = commands.add_parser(name)
        action.add_argument("engine_id")
        action.add_argument("--revision", required=True, type=int)
        if name == "enable":
            action.add_argument("--descriptor-sha256", required=True)
    paper = commands.add_parser("paper", help="Run trusted engine on one offline quote")
    paper.add_argument("engine_id")
    paper.add_argument("--quote", type=Path, required=True)
    paper.add_argument("--timeout", type=float, default=2.0)
    show = commands.add_parser("signals")
    show.add_argument("--engine-id")
    args = p.parse_args(argv)
    try:
        if args.command == "sample":
            answer = _export_demo(args.output_dir)
        else:
            if args.state_dir is None:
                raise LocalCustomRefused("CUSTOM_EXPLICIT_STATE_DIR_REQUIRED")
            host = TrustedLocalCustomHost(args.state_dir)
            try:
                if args.command == "register":
                    answer = asdict(host.register(
                        args.descriptor, args.code,
                        descriptor_sha256=args.descriptor_sha256,
                        code_sha256=args.code_sha256,
                        trust_ack=TRUST_ACK if args.trust_local_code else ""))
                elif args.command == "list":
                    answer = [asdict(item) for item in host.list()]
                elif args.command in ("enable", "disable"):
                    answer = asdict(host.toggle(
                        args.engine_id, enabled=args.command == "enable",
                        expected_revision=args.revision,
                        descriptor_sha256=getattr(args, "descriptor_sha256", None)))
                elif args.command == "paper":
                    from .trusted_custom import _read_file, MAX_QUOTE
                    answer = host.paper(
                        args.engine_id, _read_file(args.quote, MAX_QUOTE),
                        timeout_seconds=args.timeout)
                else:
                    answer = host.signals(engine_id=args.engine_id)
            finally:
                host.close()
        print(json.dumps(answer, sort_keys=True, ensure_ascii=True))
        return 0
    except (LocalCustomRefused, OSError, ValueError, sqlite3.Error) as exc:
        # Do not echo code, user-provided paths, secrets or child traceback.
        print(f"CUSTOM_PAPER_REFUSED:{type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
