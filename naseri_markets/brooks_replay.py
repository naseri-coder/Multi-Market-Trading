"""Real Al Brooks V5 full-core OFFLINE candle replay into v0.4 PAPER journal.

The public historical algorithm lives in the separate SHA-frozen legacy
production_source tree. Import it only in an explicit isolated worker. The
new release wheel never bundles historical app code or private NYFR.
No market-data downloads, Telegram sending, broker trades or daemon process.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .contracts import Direction, EvidenceMode, Instrument, Market, SignalIntent
from .delivery_ledger import IdentityConflict, _wire_intent
from .engine_control_store import BROOKS_ENGINE_ID, EngineControlStore
from .trusted_custom import LocalCustomRefused

MAX_REPLAY_BYTES = 524288
MAX_WORKER_BYTES = 32768
MIN_BARS = 60
MAX_BARS = 256
SECONDS = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600,
           "4h": 14400, "1d": 86400}
SCHEMA_FIELDS = frozenset({
    "schema_version", "origin", "market", "provider", "symbol", "timezone",
    "quote_currency", "exchange", "market_type", "timeframe", "candles",
})
BAR_FIELDS = frozenset({
    "open_time", "close_time", "open", "high", "low", "close", "volume",
})
_IDENTITY = re.compile(r"[a-zA-Z0-9_.:-]{1,80}\Z")


class BrooksReplayRefused(LocalCustomRefused):
    """Reject unsupported, untrusted, stale or noncausal offline replay."""


def _unique(pairs):
    data = {}
    for k, v in pairs:
        if k in data:
            raise BrooksReplayRefused("BROOKS_DUPLICATE_JSON_FIELD")
        data[k] = v
    return data


def _decimal(value: object, *, strictly_positive: bool = True) -> Decimal:
    if not isinstance(value, str) or not 0 < len(value) <= 48:
        raise BrooksReplayRefused("BROOKS_DECIMAL_STRING_REQUIRED")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise BrooksReplayRefused("BROOKS_INVALID_DECIMAL") from exc
    if not number.is_finite() or number < 0 or (strictly_positive and number == 0):
        raise BrooksReplayRefused("BROOKS_INVALID_DECIMAL_RANGE")
    return number


def _time(value: object) -> datetime:
    if not isinstance(value, str) or len(value) > 48:
        raise BrooksReplayRefused("BROOKS_TIME_REQUIRED")
    try:
        instant = datetime.fromisoformat(value)
        if instant.tzinfo is None or instant.utcoffset() is None:
            raise ValueError("naive timestamp")
        return instant.astimezone(UTC)
    except ValueError as exc:
        raise BrooksReplayRefused("BROOKS_TIME_INVALID") from exc


def parse_candle_replay(payload: bytes) -> tuple[dict, Instrument, tuple[dict, ...]]:
    """Validate a strictly ordered, CLOSED, constant-timeframe OHLCV window."""
    if type(payload) is not bytes or not 0 < len(payload) <= MAX_REPLAY_BYTES:
        raise BrooksReplayRefused("BROOKS_REPLAY_BOUNDS")
    try:
        raw = json.loads(
            payload, object_pairs_hook=_unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                BrooksReplayRefused("BROOKS_NONFINITE_JSON")))
    except (UnicodeError, ValueError) as exc:
        raise BrooksReplayRefused("BROOKS_REPLAY_JSON_INVALID") from exc
    if not isinstance(raw, dict) or set(raw) != SCHEMA_FIELDS:
        raise BrooksReplayRefused("BROOKS_REPLAY_SCHEMA")
    if raw["schema_version"] != 1 or type(raw["schema_version"]) is not int:
        raise BrooksReplayRefused("BROOKS_SCHEMA_VERSION")
    if raw["origin"] != "replay" or raw["market"] != "crypto":
        raise BrooksReplayRefused("BROOKS_OFFLINE_CRYPTO_REPLAY_ONLY")
    if (raw["timeframe"] not in SECONDS or raw["market_type"] not in
            ("spot", "futures") or raw["timezone"] != "UTC"):
        raise BrooksReplayRefused("BROOKS_UNSUPPORTED_MARKET_CONTEXT")
    for field in ("provider", "symbol", "quote_currency", "exchange"):
        if (not isinstance(raw[field], str)
                or not _IDENTITY.fullmatch(raw[field])):
            raise BrooksReplayRefused("BROOKS_INSTRUMENT_IDENTITY_INVALID")
    instrument = Instrument(
        Market.CRYPTO, raw["provider"], raw["symbol"],
        raw["timezone"], raw["quote_currency"],
    )
    bars = raw["candles"]
    if type(bars) is not list or not MIN_BARS <= len(bars) <= MAX_BARS:
        raise BrooksReplayRefused("BROOKS_REPLAY_CANDLE_COUNT")
    step = timedelta(seconds=SECONDS[raw["timeframe"]])
    normalized = []
    prev_close = None
    for bar in bars:
        if not isinstance(bar, dict) or set(bar) != BAR_FIELDS:
            raise BrooksReplayRefused("BROOKS_CANDLE_SCHEMA")
        opened, closed = _time(bar["open_time"]), _time(bar["close_time"])
        if closed - opened != step or (prev_close and opened != prev_close):
            raise BrooksReplayRefused("BROOKS_CANDLE_GAP_OVERLAP_OR_OPEN")
        prices = {k: _decimal(bar[k], strictly_positive=(k != "volume"))
                  for k in ("open", "high", "low", "close", "volume")}
        if (prices["low"] > prices["high"]
                or not prices["low"] <= prices["open"] <= prices["high"]
                or not prices["low"] <= prices["close"] <= prices["high"]):
            raise BrooksReplayRefused("BROOKS_CANDLE_GEOMETRY")
        normalized.append({
            "open_time": opened, "close_time": closed, **prices,
        })
        prev_close = closed
    return raw, instrument, tuple(normalized)


def verify_legacy_source(source_root: Path) -> str:
    """Verify 362 checked-in frozen source entries; never fetch or repair."""
    root = Path(source_root).absolute()
    manifest = root / "SHA256SUMS"
    if (not root.is_dir() or root.is_symlink() or not manifest.is_file()
            or manifest.is_symlink()):
        raise BrooksReplayRefused("BROOKS_FROZEN_SOURCE_REQUIRED")
    data = manifest.read_bytes()
    lines = data.decode("utf-8").splitlines()
    if len(lines) != 362:
        raise BrooksReplayRefused("BROOKS_FROZEN_MANIFEST_COUNT")
    seen = set()
    for line in lines:
        try:
            digest, name = line.split("  ", 1)
        except ValueError as exc:
            raise BrooksReplayRefused("BROOKS_BAD_MANIFEST_ENTRY") from exc
        rel = Path(name)
        if (not re.fullmatch(r"[0-9a-f]{64}", digest)
                or rel.is_absolute() or ".." in rel.parts
                or name in seen):
            raise BrooksReplayRefused("BROOKS_BAD_MANIFEST_ENTRY")
        seen.add(name)
        file = root / rel
        if (not file.is_file() or file.is_symlink()
                or hashlib.sha256(file.read_bytes()).hexdigest() != digest):
            raise BrooksReplayRefused("BROOKS_FROZEN_SOURCE_DIGEST_CHANGED")
    for entry in root.rglob("*.py"):
        if "__pycache__" in entry.parts:
            continue
        if entry.is_symlink() or str(entry.relative_to(root)) not in seen:
            raise BrooksReplayRefused("BROOKS_UNTRACKED_PYTHON_SOURCE")
    if ("app/modules/brooks_core/books_full_engine.py" not in seen
            or "app/modules/market_data/entities.py" not in seen):
        raise BrooksReplayRefused("BROOKS_ACTUAL_LEGACY_ENGINE_MISSING")
    return hashlib.sha256(data).hexdigest()


def _evaluate_legacy(root: Path, payload: bytes) -> dict:
    """In a separate child interpreter, evaluate the ACTUAL frozen V5 engine."""
    raw, _instrument, rows = parse_candle_replay(payload)
    verify_legacy_source(root)
    sys.path.insert(0, str(root))
    from app.modules.brooks_core.books_full_engine import BrooksTrilogyFullCoreEngine
    from app.modules.brooks_core.books_full_policy import BrooksFullCorePolicy
    from app.modules.market_data.entities import Candle, MarketSnapshot

    snapshot = MarketSnapshot(
        exchange=raw["exchange"], market_type=raw["market_type"],
        symbol=raw["symbol"], timeframe=raw["timeframe"],
        candles=tuple(Candle(**row) for row in rows),
        captured_at=rows[-1]["close_time"], source="OFFLINE_REPLAY",
    )
    # This flag requests a geometry decision from the pure analyzer. It does
    # NOT place orders, open a broker, authorize Telegram or bypass risk gates.
    engine = BrooksTrilogyFullCoreEngine(
        policy=BrooksFullCorePolicy(enable_trade_decisions=True))
    result = asyncio.run(engine.evaluate(snapshot))
    return {
        "decision": result.decision,
        "entry": str(result.entry_price) if result.entry_price is not None else None,
        "stop": str(result.stop_loss) if result.stop_loss is not None else None,
        "targets": [str(x) for x in result.targets],
        "setup_type": result.setup_type,
        "engine_version": result.engine_version,
        "rule_set_version": result.rule_set_version,
        "configuration_version": result.configuration_version,
        "rule_ids": list(result.rule_ids[:80]),
        "snapshot_hash": snapshot.snapshot_hash,
        "snapshot_id": snapshot.snapshot_id,
    }


def _run_worker(root: Path) -> int:
    try:
        data = sys.stdin.buffer.read(MAX_REPLAY_BYTES + 1)
        report = _evaluate_legacy(root, data)
        result = json.dumps(report, sort_keys=True, separators=(",", ":"))
        if len(result.encode("utf-8")) > MAX_WORKER_BYTES:
            raise BrooksReplayRefused("BROOKS_WORKER_OUTPUT_BOUNDS")
    except Exception:
        # No secrets, file paths, raw candles or tracebacks on stdout/stderr.
        return 3
    print(result)
    return 0


def _check_requested(store: EngineControlStore, timeframe: str) -> tuple[int, int]:
    state = store.get(BROOKS_ENGINE_ID)
    preferences = store.preferences(BROOKS_ENGINE_ID)
    if (state is None or not state.requested_enabled
            or preferences["signal_environment"] != "PAPER"
            or preferences["timeframe"] != timeframe
            or preferences["market_scope"] not in ("all", "crypto")):
        raise BrooksReplayRefused("BROOKS_PAPER_NOT_ENABLED_OR_SCOPE_DENIED")
    return state.revision, preferences["revision"]


def replay_once(*, state_dir: str | Path, legacy_source: str | Path,
                replay_json: bytes, timeout_seconds: int = 30) -> dict:
    """Replay the last finalized candle only; PAPER storage is fenced atomically."""
    if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 60:
        raise BrooksReplayRefused("BROOKS_BOUNDED_TIMEOUT_REQUIRED")
    raw, instrument, bars = parse_candle_replay(replay_json)
    with EngineControlStore(state_dir) as store:
        engine_revision, preference_revision = _check_requested(
            store, raw["timeframe"])
    source_digest = verify_legacy_source(Path(legacy_source))
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-m", "naseri_markets.brooks_replay",
             "--worker", str(Path(legacy_source).absolute())],
            input=replay_json, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            check=False, timeout=timeout_seconds,
            env={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
                 "HOME": str(Path(state_dir).absolute())},
            cwd=Path(state_dir).absolute(),
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise BrooksReplayRefused("BROOKS_WORKER_TIMED_OUT_OR_FAILED") from exc
    if proc.returncode or len(proc.stdout) > MAX_WORKER_BYTES:
        raise BrooksReplayRefused("BROOKS_ACTUAL_ENGINE_FAILED_CLOSED")
    try:
        obj = json.loads(proc.stdout)
    except (ValueError, UnicodeError) as exc:
        raise BrooksReplayRefused("BROOKS_BAD_ENGINE_RESULT") from exc
    if (type(obj) is not dict or obj.get("decision") not in
            ("NO_SIGNAL", "LONG", "SHORT")
            or obj.get("engine_version") !=
            "brooks-trilogy-full-core-v5-context-structural"
            or not isinstance(obj.get("snapshot_hash"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", obj["snapshot_hash"])
            or obj.get("snapshot_id", "").split(":")[-1] !=
            str(int(bars[-1]["close_time"].timestamp() * 1000))):
        raise BrooksReplayRefused("BROOKS_ENGINE_RESULT_PROVENANCE_INVALID")
    if obj["decision"] == "NO_SIGNAL":
        if obj.get("entry") is not None or obj.get("targets"):
            raise BrooksReplayRefused("BROOKS_NO_SIGNAL_HAS_GEOMETRY")
        signal = None
    else:
        try:
            stamp = bars[-1]["close_time"]
            identity = json.dumps({
                "snapshot": obj["snapshot_hash"],
                "instrument": (instrument.market.value, instrument.provider,
                               instrument.symbol, instrument.timezone,
                               instrument.quote_currency),
                "engine": obj["engine_version"],
                "config": obj["configuration_version"],
                "setup": obj["setup_type"], "decision": obj["decision"],
                "source": source_digest,
            }, sort_keys=True)
            signal_id = "brooks-" + hashlib.sha256(identity.encode()).hexdigest()[:40]
            signal = SignalIntent(
                signal_id, BROOKS_ENGINE_ID, obj["engine_version"], instrument,
                Direction.LONG if obj["decision"] == "LONG" else Direction.SHORT,
                stamp, _decimal(obj["entry"]), _decimal(obj["stop"]),
                tuple(_decimal(target) for target in obj["targets"]),
                EvidenceMode.PAPER,
            )
        except (KeyError, ValueError, TypeError) as exc:
            raise BrooksReplayRefused("BROOKS_UNSAFE_DECISION_GEOMETRY") from exc
    scan_key = hashlib.sha256(json.dumps({
        "snapshot_hash": obj["snapshot_hash"], "source": source_digest,
        "market": instrument.market.value, "provider": instrument.provider,
        "symbol": instrument.symbol, "version": obj["engine_version"],
        "timeframe": raw["timeframe"], "decision": obj["decision"],
    }, sort_keys=True).encode()).hexdigest()
    report = {
        "engine_id": BROOKS_ENGINE_ID,
        "snapshot_hash": obj["snapshot_hash"],
        "scan_id": scan_key,
        "decision": obj["decision"],
        "setup_type": obj.get("setup_type"),
        "rule_ids": obj.get("rule_ids", []),
        "signal_id": signal.signal_id if signal else None,
        "mode": "OFFLINE_REPLAY_PAPER",
        "live_publication_enabled": False, "telegram_sent": False,
    }
    with EngineControlStore(state_dir) as store:
        db = store._db
        db.execute("BEGIN IMMEDIATE")
        try:
            current_engine_revision, current_preference_revision = _check_requested(
                store, raw["timeframe"])
            if (current_engine_revision != engine_revision
                    or current_preference_revision != preference_revision):
                raise BrooksReplayRefused("BROOKS_CONFIGURATION_CHANGED_DURING_SCAN")
            db.execute("""CREATE TABLE IF NOT EXISTS brooks_replay_scans(
                scan_id TEXT PRIMARY KEY, snapshot_hash TEXT NOT NULL,
                decision TEXT NOT NULL, setup_type TEXT,
                signal_id TEXT, source_sha256 TEXT NOT NULL)""")
            prior = db.execute(
                "SELECT decision,signal_id FROM brooks_replay_scans WHERE scan_id=?",
                (scan_key,)).fetchone()
            if prior is not None:
                if (prior["decision"] != obj["decision"]
                        or prior["signal_id"] != report["signal_id"]):
                    raise IdentityConflict("BROOKS_REPLAY_IDENTITY_CHANGED")
                recorded = duplicate = 0
                if signal is not None:
                    duplicate = 1
                outcome = "DUPLICATE_SCAN"
            else:
                recorded = duplicate = 0
                if signal:
                    encoded = _wire_intent(signal)
                    digest = hashlib.sha256(encoded.encode()).hexdigest()
                    existed = db.execute(
                        "SELECT digest FROM a7_paper_intents "
                        "WHERE engine_id=? AND signal_id=?",
                        (BROOKS_ENGINE_ID, signal.signal_id)).fetchone()
                    if existed is not None:
                        if existed["digest"] != digest:
                            raise IdentityConflict("BROOKS_SIGNAL_IDENTITY_CHANGED")
                        duplicate = 1
                    else:
                        db.execute(
                            "INSERT INTO a7_paper_intents VALUES(?,?,?,?)",
                            (BROOKS_ENGINE_ID, signal.signal_id, digest, encoded))
                        recorded = 1
                db.execute(
                    "INSERT INTO brooks_replay_scans VALUES(?,?,?,?,?,?)",
                    (scan_key, obj["snapshot_hash"], obj["decision"],
                     obj.get("setup_type"), report["signal_id"], source_digest))
                outcome = ("NO_SIGNAL" if signal is None else
                           "RECORDED" if recorded else "DUPLICATE_SIGNAL")
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
    return {**report, "outcome": outcome, "stored": recorded,
            "duplicate": duplicate, "source_manifest_sha256": source_digest}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    mode.add_argument("--replay", type=Path,
                      help="strict JSON closed-candle offline replay file")
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--legacy-source", type=Path)
    args = parser.parse_args(argv)
    if args.worker is not None:
        return _run_worker(args.worker)
    try:
        if args.state_dir is None or args.legacy_source is None:
            raise BrooksReplayRefused("BROOKS_EXPLICIT_LOCAL_PATHS_REQUIRED")
        path = args.replay.absolute()
        if not path.is_file() or path.is_symlink():
            raise BrooksReplayRefused("BROOKS_REPLAY_REGULAR_FILE_REQUIRED")
        result = replay_once(
            state_dir=args.state_dir, legacy_source=args.legacy_source,
            replay_json=path.read_bytes())
    except (ValueError, OSError, IdentityConflict) as exc:
        print(f"BROOKS_PAPER_REFUSED:{type(exc).__name__}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
