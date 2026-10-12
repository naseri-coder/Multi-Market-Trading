"""Stage 21C: two explicit, forward-only public market research capture steps.

ARM records official public contract bytes *before* the candle window.
SEAL later downloads two fully closed kline responses and binds their hashes.
REPLAY consumes only the sealed bundle through the existing Stage-21B PAPER
journey. There is no daemon, retry loop, Telegram or broker order endpoint.

HTTP TLS and response integrity are NOT exchange signatures, residency grants,
or independently attested feed quality. Contract economic sizing is NOT wired
into the existing account-level Stage-8/9 risk engine.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable

from .captured_paper_pilot_stage21b_v1 import run_captured_paper_pilot
from .paper_contract_economics_stage21d_v1 import PaperContractEconomics
from .instrument_registry_v1 import MetadataOrigin
from .kucoin_futures_replay_stage21_v1 import (
    FuturesKlineRequest, MAX_BYTES, VenueReplayRefused, _public_get,
    parse_futures_klines,
)
from .public_futures_contracts import (
    MAX_METADATA_BYTES, PUBLIC_INSTRUMENT_ENDPOINTS, PublicContractsRefused, _download,
)
from .read_only_provider_adapters_v1 import futures_snapshot


class ForwardCaptureRefused(ValueError):
    """Explicitly refused data capture; never an order or publication grant."""


def _utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ForwardCaptureRefused("UTC_AWARE_CLOCK_REQUIRED")
    return value.astimezone(UTC)


def _gate(ack: bool) -> None:
    if (ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"):
        raise ForwardCaptureRefused("EXPLICIT_NONPRODUCTION_PUBLIC_RESEARCH_REQUIRED")


def _private_parent(path: Path, *, new: bool) -> Path:
    if not isinstance(path, Path) or not path.is_absolute() or path.is_symlink():
        raise ForwardCaptureRefused("ABSOLUTE_PRIVATE_PATH_REQUIRED")
    parent = path.parent
    if (parent.is_symlink() or not parent.is_dir()
            or parent.stat().st_uid != os.geteuid()
            or stat.S_IMODE(parent.stat().st_mode) & 0o077):
        raise ForwardCaptureRefused("OWNER_PRIVATE_PARENT_REQUIRED")
    if new:
        if path.exists():
            raise ForwardCaptureRefused("FRESH_CAPTURE_DIRECTORY_REQUIRED")
    elif (not path.is_dir() or path.stat().st_uid != os.geteuid()
          or stat.S_IMODE(path.stat().st_mode) & 0o077):
        raise ForwardCaptureRefused("EXISTING_OWNER_PRIVATE_BUNDLE_REQUIRED")
    return path


def _write_new(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def _read_private(path: Path, limit: int) -> bytes:
    if path.is_symlink():
        raise ForwardCaptureRefused("SYMLINK_CAPTURE_REFUSED")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as handle:
        info = os.fstat(handle.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) & 0o077
                or not 1 <= info.st_size <= limit):
            raise ForwardCaptureRefused("PRIVATE_BOUNDED_FILE_REQUIRED")
        result = handle.read(limit + 1)
    if len(result) > limit:
        raise ForwardCaptureRefused("PRIVATE_FILE_TOO_LARGE")
    return result


def _json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _unique(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ForwardCaptureRefused("DUPLICATE_CONTRACT_FIELD")
        result[key] = value
    return result


def _reject_const(_name: str) -> None:
    raise ForwardCaptureRefused("NONFINITE_CONTRACT_VALUE")


def _decimal(value: object, *, field: str, allow_zero: bool = False) -> Decimal:
    if type(value) not in (Decimal, int, str, float) or type(value) is bool:
        raise ForwardCaptureRefused("INVALID_CONTRACT_" + field)
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ForwardCaptureRefused("INVALID_CONTRACT_" + field) from exc
    if (not number.is_finite() or number < 0
            or (not allow_zero and number == 0)):
        raise ForwardCaptureRefused("INVALID_CONTRACT_" + field)
    return number


@dataclass(frozen=True)
class PublicContractGeometry:
    symbol: str
    price_tick: str
    lot_contracts: str
    base_units_per_contract: str
    settle_currency: str
    taker_fee_fraction: str
    maker_fee_fraction: str
    is_inverse: bool
    is_quanto: bool
    model_status: str = "PUBLIC_CONTRACT_SHAPE_ONLY_NOT_VERIFIED_ECONOMICS"

    def as_dict(self) -> dict:
        return asdict(self)


def inspect_public_contract_geometry(raw: bytes, symbols: tuple[str, str]
                                     ) -> tuple[PublicContractGeometry, ...]:
    """Decode exact public contract units without manufacturing missing values."""
    if (type(raw) is not bytes or not 1 <= len(raw) <= MAX_METADATA_BYTES
            or type(symbols) is not tuple or len(symbols) != 2
            or len(set(symbols)) != 2):
        raise ForwardCaptureRefused("BOUNDED_TWO_SYMBOL_CONTRACT_RESEARCH_REQUIRED")
    # Reuse the source-reviewed Stage-6 parser and match every reported field.
    catalog = futures_snapshot("kucoin", raw, observed_at=datetime(2026, 1, 1,
                                                                   tzinfo=UTC))
    by_name = {row.symbol: row for row in catalog.instruments}
    if not set(symbols).issubset(by_name):
        raise ForwardCaptureRefused("SYMBOL_NOT_IN_OFFICIAL_CONTRACT_LIST")
    try:
        body = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                          parse_float=Decimal, parse_constant=_reject_const)
    except (ValueError, UnicodeError, TypeError) as exc:
        raise ForwardCaptureRefused("INVALID_CONTRACT_JSON") from exc
    if (not isinstance(body, dict) or body.get("code") != "200000"
            or not isinstance(body.get("data"), list)):
        raise ForwardCaptureRefused("INVALID_CONTRACT_SCHEMA")
    found = {row["symbol"]: row for row in body["data"]
             if type(row) is dict and type(row.get("symbol")) is str}
    out = []
    for symbol in symbols:
        row = found[symbol]
        meta = by_name[symbol]
        if (meta.listing_status.value != "open" or meta.origin is not
                MetadataOrigin.PUBLIC_CONTRACT_RESEARCH
                or meta.quote_currency != "USDT" or row.get("settleCurrency") != "USDT"
                or row.get("quoteCurrency") != "USDT" or row.get("expireDate", 1) is not None
                or row.get("isInverse") is not False
                or type(row.get("isQuanto")) is not bool
                or row.get("status") != "Open"):
            raise ForwardCaptureRefused("UNSUPPORTED_CONTRACT_SETTLEMENT_OR_STATUS")
        tick = _decimal(row.get("tickSize"), field="TICK")
        lot = _decimal(row.get("lotSize"), field="LOT")
        mul = _decimal(row.get("multiplier"), field="MULTIPLIER")
        maker = _decimal(row.get("makerFeeRate"), field="MAKER_FEE", allow_zero=True)
        taker = _decimal(row.get("takerFeeRate"), field="TAKER_FEE", allow_zero=True)
        if (tick != meta.price_tick_size or lot != lot.to_integral_value()
                or lot < 1 or mul > 1000000 or maker >= 1 or taker >= 1):
            raise ForwardCaptureRefused("CONTRACT_UNIT_OR_FEE_UNSUPPORTED")
        out.append(PublicContractGeometry(
            symbol, str(tick), str(lot), str(mul), "USDT", str(taker),
            str(maker), False, row["isQuanto"]))
    return tuple(out)


def _arm_manifest(folder: Path) -> tuple[dict, bytes]:
    _private_parent(folder, new=False)
    record = json.loads(_read_private(folder / "armed.json", 4096))
    raw = _read_private(folder / "contracts.json", MAX_METADATA_BYTES)
    if (type(record) is not dict or record.get("version") != 1
            or _sha(raw) != record.get("contracts_sha256")
            or record.get("capture_mode") not in
                ("PUBLIC_HTTPS_UNATTESTED", "INJECTED_TEST_TRANSPORT")):
        raise ForwardCaptureRefused("ARMING_EVIDENCE_DRIFT")
    geometries = inspect_public_contract_geometry(raw, tuple(record["symbols"]))
    if [g.as_dict() for g in geometries] != record["contract_geometry"]:
        raise ForwardCaptureRefused("CONTRACT_GEOMETRY_DRIFT")
    return record, raw


def arm_forward_capture(
    folder: Path, *, symbols: tuple[str, str], operator_ack: bool = False,
    transport: Callable[[str], bytes] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> dict:
    """One explicit public metadata GET; no periodic work or operator secrets."""
    _gate(operator_ack)
    _private_parent(folder, new=True)
    if (type(symbols) is not tuple or len(symbols) != 2
            or any(type(v) is not str for v in symbols)
            or len(set(symbols)) != 2):
        raise ForwardCaptureRefused("TWO_EXACT_PUBLIC_SYMBOLS_REQUIRED")
    if transport is not None and not callable(transport):
        raise ForwardCaptureRefused("INVALID_TEST_TRANSPORT")
    if clock is None:
        clock = lambda: datetime.now(UTC)
    _utc(clock())
    try:
        raw = (_download("kucoin") if transport is None else
               transport(PUBLIC_INSTRUMENT_ENDPOINTS["kucoin"]))
    except (OSError, ValueError, PublicContractsRefused) as exc:
        raise ForwardCaptureRefused("PUBLIC_METADATA_UNAVAILABLE") from exc
    geometry = inspect_public_contract_geometry(raw, symbols)
    observed = _utc(clock())
    snapshot = futures_snapshot("kucoin", raw, observed_at=observed)
    if any(snapshot.provider != "kucoin_futures" or
           not any(x.symbol == g.symbol for x in snapshot.instruments)
           for g in geometry):
        raise ForwardCaptureRefused("CONTRACT_SNAPSHOT_MISMATCH")
    manifest = {
        "version": 1, "provider": "kucoin_futures", "symbols": list(symbols),
        "armed_at": observed.isoformat(), "contracts_sha256": _sha(raw),
        "contract_geometry": [g.as_dict() for g in geometry],
        "capture_mode": ("PUBLIC_HTTPS_UNATTESTED" if transport is None
                         else "INJECTED_TEST_TRANSPORT"),
        "paper_authorized": False, "broker_orders_authorized": False,
    }
    folder.mkdir(mode=0o700)
    _write_new(folder / "contracts.json", raw)
    _write_new(folder / "armed.json", _json(manifest))
    return {
        "status": "ARMED_METADATA_BEFORE_CANDLES",
        "contracts_sha256": manifest["contracts_sha256"],
        "armed_at": manifest["armed_at"],
        "contract_geometry": manifest["contract_geometry"],
        "capture_mode": manifest["capture_mode"],
        "paper_run_executed": False, "telegram_sent": False,
        "broker_order_sent": False, "profitability_proven": False,
    }


def seal_forward_capture(
    folder: Path, *, requests: tuple[FuturesKlineRequest, FuturesKlineRequest],
    operator_ack: bool = False,
    transport: Callable[[str], bytes] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> dict:
    """Later 2 explicit public Kline GETs, both strictly after metadata capture."""
    _gate(operator_ack)
    record, _raw = _arm_manifest(folder)
    if (type(requests) is not tuple or len(requests) != 2
            or any(not isinstance(x, FuturesKlineRequest) for x in requests)
            or tuple(x.symbol for x in requests) != tuple(record["symbols"])):
        raise ForwardCaptureRefused("EXACT_TWO_ARMED_SYMBOLS_REQUIRED")
    if (folder / "sealed.json").exists() or any(
            (folder / name).exists() for name in ("first.json", "second.json")):
        raise ForwardCaptureRefused("CAPTURE_ALREADY_SEALED_OR_INDETERMINATE")
    armed_at = _utc(datetime.fromisoformat(record["armed_at"]))
    if any(x.start < armed_at or x.end > armed_at + timedelta(hours=24)
           or x.expected_bars < 4 for x in requests):
        raise ForwardCaptureRefused("HISTORIC_LOOKBACK_OR_STALE_METADATA_REFUSED")
    if clock is None:
        clock = lambda: datetime.now(UTC)
    start_check = _utc(clock())
    if any(x.end > start_check for x in requests):
        raise ForwardCaptureRefused("FORWARD_BARS_NOT_CLOSED")
    if transport is not None and not callable(transport):
        raise ForwardCaptureRefused("INVALID_TEST_TRANSPORT")
    captured = []
    for query in requests:
        try:
            raw = (_public_get(query.url) if transport is None
                   else transport(query.url))
        except (OSError, ValueError, VenueReplayRefused) as exc:
            raise ForwardCaptureRefused("PUBLIC_CANDLES_UNAVAILABLE") from exc
        received_at = _utc(clock())
        if received_at < start_check:
            raise ForwardCaptureRefused("CLOCK_ROLLBACK_REFUSED")
        parsed = parse_futures_klines(
            raw, query, observed_at=received_at,
            origin=("PUBLIC_HTTPS_UNATTESTED" if transport is None
                    else "INJECTED_TEST_TRANSPORT"))
        captured.append((query, raw, parsed))
    # Commit only after BOTH HTTP bodies passed semantic validations. Failed
    # writes leave a non-reusable partial bundle; recovery is manual only.
    for name, (_query, raw, _parsed) in zip(("first.json", "second.json"), captured):
        _write_new(folder / name, raw)
    report = {
        "version": 1, "armed_sha256": _sha(_read_private(folder / "armed.json", 4096)),
        "metadata_sha256": record["contracts_sha256"],
        "sources": [
            {"symbol": q.symbol, "timeframe": q.timeframe,
             "start": q.start.isoformat(), "end": q.end.isoformat(),
             "raw_sha256": parsed.raw_sha256,
             "observed_at": parsed.observed_at.isoformat(),
             "input_origin": parsed.origin,
             "bar_count": len(parsed.candles)}
            for q, _raw, parsed in captured
        ],
        "exchange_signature_verified": False,
        "real_contract_pnl_calibrated": False,
        "telegram_sent": False, "broker_order_sent": False,
    }
    _write_new(folder / "sealed.json", _json(report))
    return {"status": "SEALED_COMPLETE_PUBLIC_RESPONSE_BUNDLE",
            "metadata_sha256": report["metadata_sha256"],
            "sources": report["sources"], "exchange_signature_verified": False,
            "real_contract_pnl_calibrated": False,
            "broker_order_sent": False, "telegram_sent": False}


def verify_capture_bundle(folder: Path) -> tuple[dict, tuple, object]:
    """Read-only verification; local SHA256 proves file identity, not publisher."""
    record, raw_meta = _arm_manifest(folder)
    sealed = json.loads(_read_private(folder / "sealed.json", 8192))
    if (type(sealed) is not dict or sealed.get("version") != 1
            or sealed.get("armed_sha256") != _sha(
                _read_private(folder / "armed.json", 4096))
            or sealed.get("metadata_sha256") != record["contracts_sha256"]
            or type(sealed.get("sources")) is not list
            or len(sealed["sources"]) != 2):
        raise ForwardCaptureRefused("SEALED_EVIDENCE_DRIFT")
    datasets = []
    for name, row in zip(("first.json", "second.json"), sealed["sources"]):
        query = FuturesKlineRequest(
            row["symbol"], row["timeframe"],
            datetime.fromisoformat(row["start"]), datetime.fromisoformat(row["end"]))
        data = _read_private(folder / name, MAX_BYTES)
        if _sha(data) != row["raw_sha256"]:
            raise ForwardCaptureRefused("CANDLE_EVIDENCE_DIGEST_CONFLICT")
        capture = parse_futures_klines(
            data, query, observed_at=datetime.fromisoformat(row["observed_at"]),
            origin=row["input_origin"])
        if (capture.raw_sha256 != row["raw_sha256"]
                or len(capture.candles) != row["bar_count"]
                or query.symbol != record["symbols"][len(datasets)]):
            raise ForwardCaptureRefused("CANDLE_IDENTITY_DRIFT")
        datasets.append((query, data))
    metadata = futures_snapshot(
        "kucoin", raw_meta, observed_at=datetime.fromisoformat(record["armed_at"]))
    return record, tuple(datasets), metadata


def replay_sealed_bundle(
    folder: Path, output_dir: Path, *, operator_ack: bool = False,
    dry_run_signals: bool = False,
    contract_quantity: Decimal = Decimal("1"),
) -> dict:
    """Explicit PAPER-only Stage21B replay, STILL TOY economics, not live trading."""
    _gate(operator_ack)
    record, datasets, metadata = verify_capture_bundle(folder)
    if record["capture_mode"] == "INJECTED_TEST_TRANSPORT":
        input_mode = "INJECTED_TEST_TRANSPORT"
    else:
        input_mode = "PUBLIC_HTTPS_UNATTESTED"
    # Freeze a separate Stage21D contract policy for each instrument. Stage3,
    # Stage8 and Stage9 now all use the order's immutable economics snapshot.
    if (type(contract_quantity) is not Decimal or not contract_quantity.is_finite()
            or contract_quantity <= 0):
        raise ForwardCaptureRefused("EXPLICIT_POSITIVE_INTEGER_CONTRACTS_REQUIRED")
    economics = tuple(PaperContractEconomics.from_public(
        PublicContractGeometry(**geometry),
        metadata_sha256=record["contracts_sha256"],
        origin=("INJECTED_TEST_CONTRACT_FIXTURE" if input_mode ==
                "INJECTED_TEST_TRANSPORT" else
                "PUBLIC_CONTRACT_SNAPSHOT_UNATTESTED"))
        for geometry in record["contract_geometry"])
    for policy in economics:
        if ((contract_quantity / policy.quantity_step) !=
                (contract_quantity / policy.quantity_step).to_integral_value()):
            raise ForwardCaptureRefused("CONTRACT_LOT_STEP_MISMATCH")
    result = run_captured_paper_pilot(
        output_dir, datasets=datasets, provider_snapshot=metadata,
        observed_at=max(datetime.fromisoformat(
            s["end"]) for s in json.loads(
                _read_private(folder / "sealed.json", 8192))["sources"]),
        operator_ack=True, dry_run_signals=dry_run_signals,
        quantity=contract_quantity, contract_economics=economics)
    result.update({
        "source_transport_origin": input_mode,
        "actual_network_fetch_at_replay": False,
        "contract_geometry": record["contract_geometry"],
        "contract_economics_gate": "MODELED_PER_INSTRUMENT_APPLIED_UNATTESTED",
        "per_instrument_economics_digests": {e.symbol: e.digest for e in economics},
        "contract_quantity_per_symbol": str(contract_quantity),
        "funding_fees_modeled": False, "liquidation_risk_modeled": False,
        "real_exchange_contract_pnl_verified": False,
        "exchange_signature_verified": False,
        "data_capture_before_candle_window": True,
        "profitability_proven": False, "broker_order_sent": False,
        "telegram_sent": False,
    })
    return result


__all__ = [
    "ForwardCaptureRefused", "PublicContractGeometry",
    "inspect_public_contract_geometry", "arm_forward_capture",
    "seal_forward_capture", "verify_capture_bundle", "replay_sealed_bundle",
]
