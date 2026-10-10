"""Local-only A9 plugin metadata manager. NOT a production bot UI.

Operating-system file permissions are the security boundary for this CLI.
--allow-metadata-writes is confirmation, NOT authentication or entitlement.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict
from pathlib import Path

from .plugin_manager import PluginManager
from .plugin_settings import _panel_item


def _read_descriptor(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= 8192:
        raise ValueError("A9_DESCRIPTOR_FILE_UNSAFE")
    return path.read_bytes()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", type=Path, required=True, help="Existing parent, local SQLite")
    p.add_argument("--allow-metadata-writes", action="store_true")
    cmds = p.add_subparsers(dest="command", required=True)
    cmds.add_parser("inventory")
    cmds.add_parser("health")
    register = cmds.add_parser("register")
    register.add_argument("descriptor", type=Path)
    register.add_argument("--sha256", required=True)
    upgrade = cmds.add_parser("upgrade")
    upgrade.add_argument("descriptor", type=Path)
    upgrade.add_argument("--sha256", required=True)
    upgrade.add_argument("--revision", type=int, required=True)
    for name in ("enable", "disable", "unregister"):
        action = cmds.add_parser(name)
        action.add_argument("engine_id")
        action.add_argument("--revision", type=int, required=True)
    audit = cmds.add_parser("audit")
    audit.add_argument("engine_id")
    args = p.parse_args(argv)
    changed = args.command not in {"inventory", "health", "audit"}
    if changed and not args.allow_metadata_writes:
        print("A9_CONFIRM_OFFLINE_METADATA_WRITE_REQUIRED", file=sys.stderr)
        return 2
    manager = None
    try:
        manager = PluginManager(args.db)
        if args.command == "inventory":
            result = [asdict(_panel_item(x)) for x in manager.list()]
        elif args.command == "health":
            result = {
                "scope": "OFFLINE_METADATA_ONLY",
                "operator_auth_source": "LOCAL_OS_FILE_PERMISSIONS",
                "private_engine_attested": False,
                "live_feed_verified": False,
                "telegram_publication_enabled": False,
                "broker_order_execution_enabled": False,
                "plugins": [asdict(_panel_item(x)) for x in manager.list()],
            }
        elif args.command == "audit":
            result = manager.audit_history(args.engine_id)
        elif args.command == "register":
            result = asdict(_panel_item(manager.register(
                _read_descriptor(args.descriptor),
                approved_sha256=args.sha256,
            )))
        elif args.command == "upgrade":
            result = asdict(_panel_item(manager.replace(
                _read_descriptor(args.descriptor),
                approved_sha256=args.sha256, expected_revision=args.revision,
            )))
        elif args.command == "unregister":
            revision = manager.unregister(
                args.engine_id, expected_revision=args.revision,
            )
            result = {"engine_id": args.engine_id, "removed_revision": revision,
                      "code_deleted": False}
        else:
            result = asdict(_panel_item(manager.set_enabled(
                args.engine_id, enabled=args.command == "enable",
                expected_revision=args.revision,
            )))
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, sqlite3.Error, UnicodeError) as exc:
        print(f"A9_OFFLINE_COMMAND_REFUSED:{type(exc).__name__}", file=sys.stderr)
        return 2
    finally:
        if manager is not None:
            manager.close()


if __name__ == "__main__":
    raise SystemExit(main())
