"""Stage 15: pinned historical candles -> ACTUAL frozen Brooks V5 worker.

This module only evaluates a bounded chronology in read-only research mode.
It never uses the PAPER signal ledger, sends a broker order or fits a rule.
The Stage-12 archive receipt is operator asserted, not externally attested.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .brooks_replay import (
    LEGACY_MANIFEST_SHA256, MAX_WORKER_BYTES, _run_worker,
    canonical_snapshot_identity, parse_candle_replay, verify_legacy_source,
)
from .historical_data_loader_a1 import HistoricalFileSpec
from .historical_pit_quality_stage12_v1 import inspect_historical_pit_archive

_MAX_ROWS = 512
_MAX_CUTS = 3
_MAX_REPLAY_BARS = 256
_REPLAY_MIN = 60
_BROOKS_VERSION = "brooks-trilogy-full-core-v5-context-structural"
_IDENT = re.compile(r"[A-Za-z0-9_.:-]{1,80}\Z")
_HEX = re.compile(r"[0-9a-f]{64}\Z")


class Stage15Refused(ValueError):
    """Fixed refusal codes; no user-provided price, path or secret disclosure."""


def _wire(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")


def _price(value: object) -> Decimal:
    if type(value) is not str or not 1 <= len(value) <= 60:
        raise Stage15Refused("BROOKS_WORKER_PRICE_NOT_DECIMAL")
    try:
        price = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise Stage15Refused("BROOKS_WORKER_PRICE_NOT_DECIMAL") from exc
    if not price.is_finite() or price <= 0:
        raise Stage15Refused("BROOKS_WORKER_PRICE_NOT_POSITIVE")
    return price


def _worker(root: Path, payload: bytes, timeout_seconds: int) -> dict:
    """Use the existing frozen-source worker; never open a state database."""
    # Avoid importing the old production package into this long-lived process.
    # The subprocess has no IPC path to any live order or Telegram service.
    with tempfile.TemporaryDirectory(prefix="mmt-stage15-offline-") as home:
        try:
            proc = subprocess.run(
                [
                    sys.executable, "-I", "-c",
                    "import sys; from pathlib import Path; "
                    "sys.path.insert(0, sys.argv[1]); "
                    "from naseri_markets.brooks_replay import _run_worker; "
                    "raise SystemExit(_run_worker(Path(sys.argv[2])))",
                    str(Path(__file__).resolve().parent.parent),
                    str(root),
                ],
                input=payload, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                check=False, timeout=timeout_seconds, cwd=home,
                env={
                    "HOME": home, "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONNOUSERSITE": "1", "MMT_NONPRODUCTION": "1",
                    "MMT_PRODUCTION": "0",
                },
            )
        except (subprocess.TimeoutExpired, OSError) as exc:
            raise Stage15Refused("BROOKS_FROZEN_WORKER_UNAVAILABLE") from exc
    if proc.returncode != 0 or not 0 < len(proc.stdout) <= MAX_WORKER_BYTES:
        raise Stage15Refused("BROOKS_FROZEN_WORKER_REJECTED")
    try:
        decoded = json.loads(proc.stdout)
    except (ValueError, UnicodeError) as exc:
        raise Stage15Refused("BROOKS_WORKER_OUTPUT_INVALID") from exc
    if type(decoded) is not dict:
        raise Stage15Refused("BROOKS_WORKER_OUTPUT_INVALID")
    return decoded


def _review(raw: dict, trace: dict, source_digest: str) -> dict:
    """Cross-check worker snapshot and any emitted price geometry."""
    parsed, _, candles = parse_candle_replay(_wire(raw))
    expected_id, expected_sha = canonical_snapshot_identity(parsed, candles)
    if (trace.get("snapshot_id") != expected_id
            or trace.get("snapshot_hash") != expected_sha
            or trace.get("engine_version") != _BROOKS_VERSION):
        raise Stage15Refused("BROOKS_REAL_ENGINE_OR_SNAPSHOT_IDENTITY_DRIFT")
    kind = trace.get("decision")
    if kind not in ("NO_SIGNAL", "LONG", "SHORT"):
        raise Stage15Refused("BROOKS_REAL_ENGINE_DECISION_INVALID")
    rules = trace.get("rule_ids")
    if (type(rules) is not list or len(rules) > 80
            or any(type(x) is not str or not 1 <= len(x) <= 100 for x in rules)):
        raise Stage15Refused("BROOKS_RULE_EVIDENCE_INVALID")
    for name in ("rule_set_version", "configuration_version"):
        if (type(trace.get(name)) is not str
                or not _IDENT.fullmatch(trace[name])):
            raise Stage15Refused("BROOKS_CONFIG_EVIDENCE_INVALID")
    targets = trace.get("targets")
    if type(targets) is not list:
        raise Stage15Refused("BROOKS_WORKER_TARGETS_INVALID")
    if kind == "NO_SIGNAL":
        if (trace.get("entry") is not None or trace.get("stop") is not None
                or targets or trace.get("setup_type") is not None):
            raise Stage15Refused("BROOKS_NO_SIGNAL_GEOMETRY_CONFLICT")
    else:
        entry, stop = _price(trace.get("entry")), _price(trace.get("stop"))
        if (not 1 <= len(targets) <= 10
                or type(trace.get("setup_type")) is not str
                or not 1 <= len(trace["setup_type"]) <= 160):
            raise Stage15Refused("BROOKS_ENTRY_GEOMETRY_INVALID")
        take = tuple(_price(value) for value in targets)
        if ((kind == "LONG" and not (stop < entry < min(take)))
                or (kind == "SHORT" and not (stop > entry > max(take)))):
            raise Stage15Refused("BROOKS_ENTRY_GEOMETRY_INVALID")
    return {
        "decision": kind,
        "snapshot_id": expected_id,
        "snapshot_sha256": expected_sha,
        "source_manifest_sha256": source_digest,
        "engine_version": _BROOKS_VERSION,
        "rule_set_version": trace["rule_set_version"],
        "configuration_version": trace["configuration_version"],
        "rule_count": len(rules),
        "rule_ids_sha256": hashlib.sha256(_wire(rules)).hexdigest(),
        "decision_evidence_sha256": hashlib.sha256(_wire(trace)).hexdigest(),
        "market_order_sent": False,
        "telegram_sent": False,
    }


def review_real_brooks_history(
    archive: Path,
    spec: HistoricalFileSpec,
    *,
    receipt_bytes: bytes,
    trusted_receipt_sha256: str,
    archive_as_of_utc: datetime,
    legacy_source: Path,
    evaluation_cutoffs_utc: tuple[datetime, ...],
    timeout_seconds: int = 30,
    operator_ack: bool = False,
) -> dict:
    """Explicit finite close-time snapshots; no PAPER journal or PnL booking."""
    if (operator_ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        raise Stage15Refused("EXPLICIT_NONPRODUCTION_OPERATOR_APPROVAL_REQUIRED")
    if (type(spec) is not HistoricalFileSpec
            or not isinstance(archive, Path) or not archive.is_absolute()
            or not isinstance(legacy_source, Path) or not legacy_source.is_absolute()
            or legacy_source.is_symlink() or type(timeout_seconds) is not int
            or not 1 <= timeout_seconds <= 60):
        raise Stage15Refused("EXPLICIT_PINNED_LOCAL_INPUTS_REQUIRED")
    cuts = evaluation_cutoffs_utc
    if (type(cuts) is not tuple or not 1 <= len(cuts) <= _MAX_CUTS
            or any(type(x) is not datetime or x.tzinfo is None
                   or x.utcoffset() != timedelta(0) for x in cuts)
            or tuple(sorted(set(cuts))) != cuts):
        raise Stage15Refused("UNIQUE_ORDERED_UTC_CUTOFFS_REQUIRED")
    feed = spec.feed
    identity = feed.instrument
    # The current real V5 replay contract has an explicit, checked Binance
    # futures identity, not a generic exchange/currency or spot backtest.
    if (identity.provider != "binance_replay" or identity.symbol != "BTCUSDT"
            or identity.quote_currency != "USDT" or feed.timeframe != "15m"):
        raise Stage15Refused("BROOKS_REVIEWED_INSTRUMENT_FENCE")
    pit = inspect_historical_pit_archive(
        archive, spec, receipt_bytes=receipt_bytes,
        trusted_receipt_sha256=trusted_receipt_sha256,
        as_of_utc=archive_as_of_utc, operator_ack=True,
    )
    if pit.contract_kind_claim != "linear_perpetual":
        raise Stage15Refused("BROOKS_LINEAR_FUTURES_CONTRACT_CLAIM_REQUIRED")
    # This function verifies 359 SHA-frozen historical files plus extras.
    source_digest = verify_legacy_source(legacy_source)
    if source_digest != LEGACY_MANIFEST_SHA256:
        raise Stage15Refused("BROOKS_SOURCE_PIN_DRIFT")
    from .historical_data_loader_a1 import validate_historical_file
    validated = validate_historical_file(archive, spec)
    if validated.report.sha256 != pit.dataset_sha256:
        raise Stage15Refused("PINNED_HISTORICAL_BYTES_DRIFT")
    if not _REPLAY_MIN <= validated.report.rows_validated <= _MAX_ROWS:
        raise Stage15Refused("BROOKS_HISTORY_BOUNDS_OR_WARMUP")
    rows = tuple(validated.packets())
    by_close = {p.candle.close_at: i + 1 for i, p in enumerate(rows)}
    if any(cut not in by_close or by_close[cut] < _REPLAY_MIN
           for cut in cuts):
        raise Stage15Refused("BROOKS_PREDECLARED_CUTOFF_NOT_CLOSED_OR_WARM")
    receipts = []
    for cut in cuts:
        last_index = by_close[cut]
        source_rows = rows[max(0, last_index - _MAX_REPLAY_BARS):last_index]
        bars = [{
            "open_time": packet.candle.open_at.isoformat(),
            "close_time": packet.candle.close_at.isoformat(),
            "open": str(packet.candle.open),
            "high": str(packet.candle.high),
            "low": str(packet.candle.low),
            "close": str(packet.candle.close),
            "volume": str(packet.candle.volume),
        } for packet in source_rows]
        context = {
            "schema_version": 1, "origin": "replay", "market": "crypto",
            "provider": "binance_replay", "exchange": "binance",
            "market_type": "futures", "symbol": "BTCUSDT",
            "quote_currency": "USDT", "timezone": "UTC",
            "timeframe": "15m", "candles": bars,
        }
        payload = _wire(context)
        parse_candle_replay(payload)
        output = _worker(legacy_source, payload, timeout_seconds)
        approved = _review(context, output, source_digest)
        receipts.append({
            "closed_bar_cutoff_utc": cut.astimezone(UTC).isoformat(),
            "visible_history_bar_count": len(bars),
            **approved,
        })
    report = {
        "mode": "STAGE15_REAL_PINNED_BROOKS_V5_OFFLINE_TRACE_ONLY",
        "source_manifest_sha256": source_digest,
        "dataset_sha256": pit.dataset_sha256,
        "historical_quality_evidence_sha256": pit.evidence_sha256,
        "evaluation_count": len(receipts),
        "evaluation_cutoffs_utc": [c.isoformat() for c in cuts],
        "evaluations": receipts,
        "actual_brooks_engine_evaluated": True,
        "actual_exchange_data_authenticated": False,
        "independent_archival_time_attested": False,
        "venue_contract_economics_verified": False,
        "actual_live_strategy_signal_parity_certified": False,
        "parametric_strategy_variants_evaluated": False,
        "walk_forward_backtest_run": False,
        "economic_pnl_calculated": False,
        "trading_edge_proven": False,
        "research_release_authorized": False,
        "broker_orders_authorized": False,
        "telegram_sent": False,
        "production_modified": False,
        "verdict": "REAL_CORE_EXECUTED_SOURCE_AND_ECONOMICS_UNVERIFIED",
    }
    report["report_sha256"] = hashlib.sha256(_wire(report)).hexdigest()
    return report


__all__ = ["Stage15Refused", "review_real_brooks_history"]
