"""Stage-17 local read-only queue health CLI; no daemon, sockets or execution."""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import stat
import sys
from pathlib import Path
from urllib.parse import quote


class HealthRefused(ValueError):
    """Invalid private offline evidence file."""


def inspect_queue(path: Path) -> dict:
    if os.environ.get("MMT_NONPRODUCTION") != "1" or "MMT_PRODUCTION" in os.environ:
        raise HealthRefused("NONPRODUCTION_REQUIRED")
    path = Path(path)
    if (not path.is_absolute() or path.is_symlink() or not path.is_file()
            or path.stat().st_nlink != 1 or path.stat().st_uid != os.geteuid()
            or stat.S_IMODE(path.stat().st_mode) & 0o077):
        raise HealthRefused("PRIVATE_RUNTIME17_DATABASE_REQUIRED")
    uri = f"file:{quote(str(path))}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=2) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise HealthRefused("QUEUE_INTEGRITY_INVALID")
        try:
            counts = dict(db.execute(
                "SELECT status,COUNT(*) FROM runtime17_jobs GROUP BY status"))
        except sqlite3.Error as exc:
            raise HealthRefused("RUNTIME17_SCHEMA_REQUIRED") from exc
        db.execute("COMMIT")
    if set(counts) - {"PENDING", "CLAIMED", "DONE", "QUARANTINED"}:
        raise HealthRefused("UNKNOWN_WORK_STATUS")
    return {"mode": "READ_ONLY_OFFLINE_RUNTIME17",
            "counts": {name: counts.get(name, 0) for name in
                       ("PENDING", "CLAIMED", "DONE", "QUARANTINED")},
            "reconciliation_required": bool(counts.get("CLAIMED", 0)
                                            or counts.get("QUARANTINED", 0)),
            "telegram_sent": False, "broker_order_sent": False,
            "live_trading_enabled": False, "product_release_authorized": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-db", type=Path, required=True)
    parser.add_argument("--ack-nonproduction-readonly", action="store_true")
    args = parser.parse_args(argv)
    try:
        if not args.ack_nonproduction_readonly:
            raise HealthRefused("EXPLICIT_READONLY_ACK_REQUIRED")
        answer = inspect_queue(args.runtime_db)
    except (HealthRefused, sqlite3.Error, OSError) as exc:
        print("RUNTIME17_HEALTH_REFUSED:" + type(exc).__name__, file=sys.stderr)
        return 2
    print(json.dumps(answer, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
