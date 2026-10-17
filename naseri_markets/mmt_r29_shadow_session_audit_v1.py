"""R29: read-only multi-day audit of manual original-source shadow checkpoints.

A local hash-chain and repeated R24 source replay are not independent exchange
authentication, independent time attestations, account fills or realized PnL.
No worker scheduling, trades, network, journal writes or auto repair.
"""
from __future__ import annotations

import json
import os
import stat
from collections import Counter
from pathlib import Path

from .brooks_forward_source_custody_stage21g_v1 import _read_original_evidence
from .brooks_future_shadow_paper_mmt_r29_v1 import (
    MAX_TOTAL_BARS,
    PLAN_SHA,
    PROTOCOL,
    R29ShadowRefused,
    _canonical,
    _gate,
    _hash,
    _unique,
    _validated_tape,
)
from .brooks_sequential_forward_custody_mmt_r24_v1 import (
    stage24_replay_all_previous_batches,
)

_REQUIRED = frozenset({
    "protocol", "canonical_plan_sha256", "frozen_brooks_manifest_sha256",
    "decision_bar_index", "decision_cutoff_utc", "source_prefix_sha256",
    "window_input_sha256", "previous_r29_receipt_sha256",
    "r24_last_outer_receipt_sha256", "r24_latest_batch_fingerprint",
    "decision", "snapshot_sha256", "rule_ids_sha256",
    "decision_evidence_sha256", "shadow_ledger_only", "modeling_result",
    "network_used", "broker_orders_sent", "telegram_sent",
    "connected_paper_enabled", "live_trading_enabled",
    "market_source_issuer_authenticity_proven",
    "receive_time_independently_attested", "actual_fills_verified",
    "net_profit_verified", "prospective_edge_certified", "status",
    "receipt_sha256",
})
_FALSE = (
    "network_used", "broker_orders_sent", "telegram_sent",
    "connected_paper_enabled", "live_trading_enabled",
    "market_source_issuer_authenticity_proven",
    "receive_time_independently_attested", "actual_fills_verified",
    "net_profit_verified", "prospective_edge_certified",
)
_SHA_FIELDS = (
    "frozen_brooks_manifest_sha256", "source_prefix_sha256",
    "window_input_sha256", "r24_last_outer_receipt_sha256",
    "r24_latest_batch_fingerprint", "snapshot_sha256",
    "rule_ids_sha256", "decision_evidence_sha256",
)


def _secure_receipt(path: Path) -> dict:
    if not isinstance(path, Path) or not path.is_absolute() or path.is_symlink():
        raise R29ShadowRefused("R29_AUDIT_ABSOLUTE_PRIVATE_RECEIPT_REQUIRED")
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise R29ShadowRefused("R29_AUDIT_PRIVATE_PARENT_REQUIRED")
    parent = path.parent.stat()
    if (parent.st_uid != os.geteuid()
            or stat.S_IMODE(parent.st_mode) & 0o077):
        raise R29ShadowRefused("R29_AUDIT_PRIVATE_PARENT_REQUIRED")
    flags = os.O_RDONLY | os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                    or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o077
                    or not 10 <= info.st_size <= 16384):
                raise R29ShadowRefused("R29_AUDIT_PRIVATE_RECEIPT_REQUIRED")
            with os.fdopen(fd, "rb", closefd=False) as f:
                raw = f.read(16385)
        finally:
            os.close(fd)
    except OSError as exc:
        raise R29ShadowRefused("R29_AUDIT_RECEIPT_IO_REFUSED") from exc
    try:
        obj = json.loads(raw.decode("ascii"), object_pairs_hook=_unique)
        if type(obj) is not dict or frozenset(obj) != _REQUIRED:
            raise ValueError("shape")
        digest = obj["receipt_sha256"]
        if (type(digest) is not str or not _shahex(digest)
                or _canonical(obj) != raw
                or digest != _hash(_canonical({
                    k: v for k, v in obj.items() if k != "receipt_sha256"
                }))):
            raise ValueError("digest")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise R29ShadowRefused("R29_AUDIT_NONCANONICAL_RECEIPT") from exc
    return obj


def _shahex(value: object) -> bool:
    return (type(value) is str and len(value) == 64
            and all(c in "0123456789abcdef" for c in value))


def audit_r29_original_source_shadow_session(
    *, witness_directory: Path,
    previous_directories: tuple[Path, ...],
    shadow_receipts: tuple[Path, ...],
    operator_ack: bool = False,
) -> dict:
    """Validate all sequential decisions from index 60 with no gaps or rewrites.

    Does not re-run the frozen worker for every event; therefore source and
    local receipt consistency do not make an execution/performance certificate.
    """
    _gate(operator_ack)
    if (type(shadow_receipts) is not tuple
            or len(shadow_receipts) > MAX_TOTAL_BARS - 59):
        raise R29ShadowRefused("R29_AUDIT_BOUNDED_COMPLETE_RECEIPTS_REQUIRED")
    witness = _read_original_evidence(witness_directory)
    source = stage24_replay_all_previous_batches(
        previous_directories=previous_directories, witness=witness,
        operator_ack=True,
    )
    tape = _validated_tape(previous_directories, source)
    if len(tape) < 60 and shadow_receipts:
        raise R29ShadowRefused("R29_AUDIT_UNCLOSED_OR_MISSING_SOURCE")
    counters: Counter[str] = Counter()
    per_day: Counter[str] = Counter()
    previous_digest = PLAN_SHA
    seen_paths: set[tuple[int, int]] = set()
    for i, path in enumerate(shadow_receipts, start=60):
        try:
            info = (path.stat() if isinstance(path, Path)
                    and not path.is_symlink() else None)
        except OSError as exc:
            raise R29ShadowRefused("R29_AUDIT_RECEIPT_STAT_REFUSED") from exc
        if info is None or (info.st_dev, info.st_ino) in seen_paths:
            raise R29ShadowRefused("R29_AUDIT_DUPLICATE_OR_LINKED_RECEIPT")
        seen_paths.add((info.st_dev, info.st_ino))
        obj = _secure_receipt(path)
        if (i > len(tape)
                or type(obj.get("decision_bar_index")) is not int
                or obj["decision_bar_index"] != i
                or obj["protocol"] != PROTOCOL
                or obj["canonical_plan_sha256"] != PLAN_SHA
                or obj["previous_r29_receipt_sha256"] != previous_digest
                or obj["source_prefix_sha256"] != _hash(_canonical(tape[:i]))
                or obj["decision_cutoff_utc"] != tape[i - 1]["close_time"]
                or obj["decision"] not in ("LONG", "SHORT", "NO_SIGNAL")
                or obj["shadow_ledger_only"] is not True
                or obj["modeling_result"] != "NO_BROKER_FILL_OR_ACTUAL_PNL_MODELED"
                or obj["status"] != "FROZEN_BROOKS_REAL_WORKER_SHADOW_RESEARCH_ONLY"
                or any(obj[key] is not False for key in _FALSE)
                or any(not _shahex(obj[field]) for field in _SHA_FIELDS)):
            raise R29ShadowRefused("R29_AUDIT_DECISION_SOURCE_OR_SAFETY_DRIFT")
        previous_digest = obj["receipt_sha256"]
        counters[obj["decision"]] += 1
        per_day[obj["decision_cutoff_utc"][:10]] += 1
    return {
        "protocol": "MMT_R29_ORIGINAL_SOURCE_SHADOW_SESSION_AUDIT_V1",
        "state": ("NO_VALID_FUTURE_DECISIONS_YET" if not shadow_receipts
                  else "LOCAL_CONSISTENT_SEQUENCE_NOT_INDEPENDENT_OOS"),
        "original_closed_bars_preserved": len(tape),
        "consecutive_decision_receipts": len(shadow_receipts),
        "first_eligible_decision_utc": "2026-10-20T15:00:00Z",
        "last_decision_close_utc": (
            tape[58 + len(shadow_receipts)]["close_time"]
            if shadow_receipts else None
        ),
        "decision_counts": {x: counters[x] for x in ("LONG", "SHORT", "NO_SIGNAL")},
        "utc_dates_with_decisions": dict(sorted(per_day.items())),
        "last_local_receipt_sha256": previous_digest,
        "source_chain_last_digest": source.previous_batch_digest,
        "complete_study_coverage": (
            len(tape) == MAX_TOTAL_BARS
            and len(shadow_receipts) == MAX_TOTAL_BARS - 59
        ),
        "independent_market_data_authentication": False,
        "independent_candle_receive_clock": False,
        "actual_fills_or_profits_certified": False,
        "background_runner_started": False,
        "broker_orders_sent": False,
        "telegram_sent": False,
        "connected_paper_enabled": False,
        "live_trading_enabled": False,
        "production_modified": False,
    }


__all__ = ["audit_r29_original_source_shadow_session"]
