"""R33 manually reviewed local LIVE blocker report; no exchange integration.

Input JSON is untrusted, and even a fully affirmative evidence file cannot
generate a LIVE token, enable a publisher, or transmit an order.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
from datetime import UTC, datetime
from pathlib import Path

from naseri_markets.mmt_r33_live_hard_deny_readiness_v1 import (
    R33Evidence, R33PRObservation, R33ReadinessRefused,
    _EVIDENCE_FLAG_FIELDS, review_r33_live_readiness,
)

_MAX_INPUT = 8192


def _reject_duplicates(pairs: list[tuple[str, object]]) -> dict:
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise R33ReadinessRefused("R33_DUPLICATE_EVIDENCE_FIELD")
        obj[key] = value
    return obj


def _reject_constant(_: str) -> None:
    raise R33ReadinessRefused("R33_NONFINITE_NUMBER_FORBIDDEN")


def _read_private(path: Path) -> bytes:
    if type(path) is not Path or not path.is_absolute() or path.is_symlink():
        raise R33ReadinessRefused("R33_PRIVATE_ABSOLUTE_INPUT_REQUIRED")
    if (path.parent.is_symlink() or not path.parent.is_dir()
            or path.parent.resolve(strict=True) != path.parent
            or path.parent.stat().st_uid != os.geteuid()
            or stat.S_IMODE(path.parent.stat().st_mode) & 0o077):
        raise R33ReadinessRefused("R33_PRIVATE_PARENT_REQUIRED")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            st = os.fstat(fd)
            if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
                    or st.st_uid != os.geteuid()
                    or stat.S_IMODE(st.st_mode) & 0o077
                    or not 2 <= st.st_size <= _MAX_INPUT):
                raise R33ReadinessRefused("R33_OWNER_PRIVATE_BOUNDED_FILE_REQUIRED")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                raw = stream.read(_MAX_INPUT + 1)
            if len(raw) != st.st_size:
                raise R33ReadinessRefused("R33_CHANGED_EVIDENCE_FILE")
            return raw
        finally:
            os.close(fd)
    except OSError as exc:
        raise R33ReadinessRefused("R33_PRIVATE_FILE_READ_FAILED") from exc


def decode_offline_operator_claims(raw: bytes) -> R33Evidence:
    """Strictly type-check claims, but NEVER pretend they are attested."""
    if type(raw) is not bytes or not 2 <= len(raw) <= _MAX_INPUT:
        raise R33ReadinessRefused("R33_BOUNDED_JSON_REQUIRED")
    try:
        data = json.loads(
            raw.decode("ascii"),
            object_pairs_hook=_reject_duplicates,
            parse_constant=_reject_constant,
        )
    except (ValueError, UnicodeError, TypeError) as exc:
        raise R33ReadinessRefused("R33_INVALID_INPUT_JSON") from exc
    if (type(data) is not dict or set(data) != {
        "prs", "review_time_utc", "flags",
    } or type(data["prs"]) is not list or len(data["prs"]) != 5
            or type(data["flags"]) is not dict
            or set(data["flags"]) != set(_EVIDENCE_FLAG_FIELDS)):
        raise R33ReadinessRefused("R33_EXACT_SCHEMA_REQUIRED")
    if type(data["review_time_utc"]) is not str:
        raise R33ReadinessRefused("R33_FIXED_UTC_TIME_REQUIRED")
    try:
        now = datetime.strptime(
            data["review_time_utc"], "%Y-%m-%dT%H:%M:%SZ",
        ).replace(tzinfo=UTC)
    except ValueError as exc:
        raise R33ReadinessRefused("R33_FIXED_UTC_TIME_REQUIRED") from exc
    prs = []
    for item in data["prs"]:
        if (type(item) is not dict
                or set(item) != {"number", "head_sha", "state", "draft", "merged"}):
            raise R33ReadinessRefused("R33_EXACT_PR_SCHEMA_REQUIRED")
        prs.append(R33PRObservation(**item))
    return R33Evidence(
        prs=tuple(prs), review_time_utc=now, **data["flags"],
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="R33 OFFLINE ONLY: inspect declared blockers, never LIVE"
    )
    parser.add_argument("--private-evidence-json", type=Path, required=True)
    parser.add_argument("--ack-deny-only-review", action="store_true")
    args = parser.parse_args(argv)
    try:
        claims = decode_offline_operator_claims(
            _read_private(args.private_evidence_json.absolute()),
        )
        result = review_r33_live_readiness(
            claims, operator_ack=args.ack_deny_only_review,
        )
    except (R33ReadinessRefused, ValueError, OSError):
        print(json.dumps({
            "protocol": "MMT_R33_OFFLINE_CLI_V1",
            "decision": "LIVE_HARD_DENY",
            "evidence_schema": "REFUSED_REVIEW_REQUIRED",
            "can_route_order": False,
            "can_enable_live": False,
        }, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
