"""R29 manual Brooks future-source shadow decisions; NO connected PAPER.

Consumes only the complete R24 locally replay-verified source chain; evaluates
one strictly sequential closed-bar cutoff with genuine SHA-frozen Brooks V5.
Does not compute fills/PnL without future ticks, account fees, funding/Mark,
or order-type semantics. No collector, timer, network, broker or Telegram.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .brooks_forward_source_custody_stage21g_v1 import _read_original_evidence
from .brooks_replay import (
    canonical_snapshot_identity, parse_candle_replay, verify_legacy_source,
)
from .brooks_sequential_forward_custody_mmt_r24_v1 import (
    _strict_read, stage24_replay_all_previous_batches,
)
from .real_brooks_historical_stage15_v1 import _review, _wire, _worker

PLAN_SHA = "c557e8792ff7f097ee483903e2e6702c622a20f3975af898ee9aca7e257ad94d"
FIRST_OPEN = datetime(2026, 10, 20, tzinfo=UTC)
LAST_CLOSE = datetime(2026, 11, 3, tzinfo=UTC)
BAR = timedelta(minutes=15)
HEADER = ["open_at", "close_at", "open", "high", "low", "close", "volume"]
MAX_TOTAL_BARS = 14 * 24 * 4
SHA = re.compile(r"[0-9a-f]{64}\Z")
PROTOCOL = "MMT_R29_ORIGINAL_SOURCE_SHADOW_DECISION_V1"


class R29ShadowRefused(ValueError):
    """Fail closed without echoing untrusted market-data text."""


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical(data: object) -> bytes:
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _unique(pairs: list[tuple[str, object]]) -> dict:
    out = {}
    for key, value in pairs:
        if key in out:
            raise R29ShadowRefused("R29_DUPLICATE_JSON_FIELD")
        out[key] = value
    return out


def _gate(operator_ack: bool) -> None:
    if (operator_ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        raise R29ShadowRefused("R29_EXPLICIT_DISCONNECTED_RESEARCH_ONLY")


def _validated_tape(directories: tuple[Path, ...], state) -> tuple[dict, ...]:
    all_rows: list[dict] = []
    next_open = FIRST_OPEN
    for folder in directories:
        raw = _strict_read(folder, "canonical-reviewed-closed-candles.csv")
        if len(raw) > 160000:
            raise R29ShadowRefused("R29_CAPTURED_CSV_OVERSIZE")
        try:
            parsed = list(csv.reader(
                io.StringIO(raw.decode("ascii"), newline=""), strict=True,
            ))
        except (UnicodeError, ValueError, csv.Error) as exc:
            raise R29ShadowRefused("R29_INVALID_CAPTURED_CSV") from exc
        if (not parsed or parsed[0] != HEADER
                or not 1 <= len(parsed) - 1 <= 96
                or any(len(row) != len(HEADER) for row in parsed[1:])):
            raise R29ShadowRefused("R29_CAPTURED_CSV_SCHEMA_DRIFT")
        for row in parsed[1:]:
            expected_open = next_open.strftime("%Y-%m-%dT%H:%M:%SZ")
            next_open += BAR
            expected_close = next_open.strftime("%Y-%m-%dT%H:%M:%SZ")
            if row[0] != expected_open or row[1] != expected_close:
                raise R29ShadowRefused("R29_CAPTURED_CANDLE_GAP_OR_ORDER")
            if next_open > LAST_CLOSE or len(all_rows) >= MAX_TOTAL_BARS:
                raise R29ShadowRefused("R29_CAPTURED_CANDLE_OUTSIDE_STUDY")
            all_rows.append({
                "open_time": row[0], "close_time": row[1],
                "open": row[2], "high": row[3], "low": row[4],
                "close": row[5], "volume": row[6],
            })
    if (not all_rows or state.accepted_batches != len(directories)
            or state.next_open_utc != next_open):
        raise R29ShadowRefused("R29_R24_SOURCE_CHAIN_COVERAGE_DRIFT")
    return tuple(all_rows)


def _previous(raw: bytes | None, *, index: int,
              tape: tuple[dict, ...]) -> str:
    if raw is None:
        if index != 60:
            raise R29ShadowRefused("R29_FIRST_DECISION_MUST_BE_BAR_60")
        return PLAN_SHA
    if type(raw) is not bytes or not 10 <= len(raw) <= 16384:
        raise R29ShadowRefused("R29_PREVIOUS_RECEIPT_BYTES_REQUIRED")
    try:
        obj = json.loads(raw.decode("ascii"), object_pairs_hook=_unique)
        if type(obj) is not dict:
            raise ValueError("object required")
        digest = obj.pop("receipt_sha256")
        if (type(digest) is not str or not SHA.fullmatch(digest)
                or _hash(_canonical(obj)) != digest
                or _canonical({**obj, "receipt_sha256": digest}) != raw
                or obj.get("protocol") != PROTOCOL
                or obj.get("canonical_plan_sha256") != PLAN_SHA
                or obj.get("decision_bar_index") != index - 1
                or obj.get("source_prefix_sha256") !=
                _hash(_canonical(tape[:index - 1]))
                or obj.get("network_used") is not False
                or obj.get("broker_orders_sent") is not False
                or obj.get("telegram_sent") is not False
                or obj.get("connected_paper_enabled") is not False
                or obj.get("live_trading_enabled") is not False
                or obj.get("actual_fills_verified") is not False
                or obj.get("net_profit_verified") is not False):
            raise ValueError("previous chain invalid")
        return digest
    except (ValueError, TypeError, KeyError, UnicodeError) as exc:
        raise R29ShadowRefused("R29_PREVIOUS_CHECKPOINT_CHAIN_REFUSED") from exc


def review_r29_one_closed_bar_shadow(
    *, witness_directory: Path,
    previous_directories: tuple[Path, ...],
    frozen_source: Path,
    decision_bar_index: int,
    previous_r29_receipt_bytes: bytes | None = None,
    operator_ack: bool = False,
) -> tuple[dict, bytes | None]:
    """Explicit one-bar review; index 60 is first, then 61, 62, ... in order.

    A returned decision is genuine pinned-engine shadow research over operator-
    acquired market bytes, NOT an independently authenticated venue feed.
    Before the first 60 forward bars, return a waiting *nonreceipt*.
    """
    _gate(operator_ack)
    if (not isinstance(witness_directory, Path)
            or not isinstance(frozen_source, Path)
            or type(previous_directories) is not tuple
            or type(decision_bar_index) is not int
            or not 60 <= decision_bar_index <= MAX_TOTAL_BARS):
        raise R29ShadowRefused("R29_EXACT_OPERATOR_PATHS_AND_INDEX_REQUIRED")
    witness = _read_original_evidence(witness_directory)
    state = stage24_replay_all_previous_batches(
        previous_directories=previous_directories,
        witness=witness, operator_ack=True,
    )
    tape = _validated_tape(previous_directories, state)
    if len(tape) < 60:
        if decision_bar_index != 60 or previous_r29_receipt_bytes is not None:
            raise R29ShadowRefused("R29_NOT_ENOUGH_REAL_CLOSED_BARS")
        return {
            "protocol": PROTOCOL,
            "status": "WAITING_FOR_60_FUTURE_CLOSED_BARS",
            "admitted_closed_bars": len(tape),
            "first_possible_decision_close_utc": "2026-10-20T15:00:00Z",
            "worker_executed": False,
            "connected_paper_enabled": False,
            "live_trading_enabled": False,
        }, None
    if decision_bar_index > len(tape):
        raise R29ShadowRefused("R29_CANNOT_EVALUATE_UNCAPTURED_FUTURE")
    previous_digest = _previous(
        previous_r29_receipt_bytes, index=decision_bar_index, tape=tape,
    )
    window = tape[max(0, decision_bar_index - 256):decision_bar_index]
    replay = {
        "schema_version": 1, "origin": "replay", "market": "crypto",
        "provider": "binance_usdm_public_source_unverified",
        "symbol": "BTCUSDT", "timezone": "UTC", "quote_currency": "USDT",
        "exchange": "binance", "market_type": "futures",
        "timeframe": "15m", "candles": list(window),
    }
    payload = _wire(replay)
    parse_candle_replay(payload)
    source_manifest_sha256 = verify_legacy_source(frozen_source)
    trace = _worker(frozen_source, payload, 30)
    reviewed = _review(replay, trace, source_manifest_sha256)
    _, _, normalized = parse_candle_replay(payload)
    identity, snapshot_sha = canonical_snapshot_identity(replay, normalized)
    if (reviewed["snapshot_id"] != identity
            or reviewed["snapshot_sha256"] != snapshot_sha
            or reviewed.get("market_order_sent") is not False
            or reviewed.get("telegram_sent") is not False):
        raise R29ShadowRefused("R29_FROZEN_WORKER_PROOF_MISMATCH")
    decision_cutoff = tape[decision_bar_index - 1]["close_time"]
    result = {
        "protocol": PROTOCOL,
        "canonical_plan_sha256": PLAN_SHA,
        "frozen_brooks_manifest_sha256": source_manifest_sha256,
        "decision_bar_index": decision_bar_index,
        "decision_cutoff_utc": decision_cutoff,
        "source_prefix_sha256": _hash(_canonical(tape[:decision_bar_index])),
        "window_input_sha256": _hash(payload),
        "previous_r29_receipt_sha256": previous_digest,
        "r24_last_outer_receipt_sha256": state.last_outer_receipt_sha256,
        "r24_latest_batch_fingerprint": state.previous_batch_digest,
        "decision": reviewed["decision"],
        "snapshot_sha256": snapshot_sha,
        "rule_ids_sha256": reviewed["rule_ids_sha256"],
        "decision_evidence_sha256": reviewed["decision_evidence_sha256"],
        "shadow_ledger_only": True,
        "modeling_result": "NO_BROKER_FILL_OR_ACTUAL_PNL_MODELED",
        "network_used": False,
        "broker_orders_sent": False,
        "telegram_sent": False,
        "connected_paper_enabled": False,
        "live_trading_enabled": False,
        "market_source_issuer_authenticity_proven": False,
        "receive_time_independently_attested": False,
        "actual_fills_verified": False,
        "net_profit_verified": False,
        "prospective_edge_certified": False,
        "status": "FROZEN_BROOKS_REAL_WORKER_SHADOW_RESEARCH_ONLY",
    }
    result["receipt_sha256"] = _hash(_canonical(result))
    return result, _canonical(result)


def save_r29_receipt_exclusive(
    *, directory: Path, receipt: bytes, operator_ack: bool = False,
) -> Path:
    """Persist only one already-produced canonical decision; never overwrite."""
    _gate(operator_ack)
    if (not isinstance(directory, Path) or not directory.is_absolute()
            or directory.is_symlink() or not directory.is_dir()
            or directory.stat().st_uid != os.geteuid()
            or stat.S_IMODE(directory.stat().st_mode) & 0o077):
        raise R29ShadowRefused("R29_PRIVATE_OUTPUT_DIRECTORY_REQUIRED")
    if type(receipt) is not bytes or not 10 <= len(receipt) <= 16384:
        raise R29ShadowRefused("R29_BOUNDED_RECEIPT_BYTES_REQUIRED")
    try:
        obj = json.loads(receipt.decode("ascii"), object_pairs_hook=_unique)
        digest = obj["receipt_sha256"]
        if (obj.get("protocol") != PROTOCOL or
                not isinstance(digest, str) or not SHA.fullmatch(digest)
                or _canonical(obj) != receipt
                or digest != _hash(_canonical({
                    k: v for k, v in obj.items() if k != "receipt_sha256"
                }))):
            raise ValueError("invalid receipt")
    except (KeyError, ValueError, TypeError, UnicodeError) as exc:
        raise R29ShadowRefused("R29_CHECKPOINT_RECEIPT_INVALID") from exc
    dest = directory / ("r29-shadow-bar-%04d.json" % obj["decision_bar_index"])
    try:
        fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    except OSError as exc:
        raise R29ShadowRefused("R29_NO_OVERWRITE_OR_SYMLINK_ALLOWED") from exc
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(receipt)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    return dest


__all__ = [
    "R29ShadowRefused", "review_r29_one_closed_bar_shadow",
    "save_r29_receipt_exclusive",
]
