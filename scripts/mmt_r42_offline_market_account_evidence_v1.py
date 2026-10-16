"""R42: read-only, externally SHA-pinned synthetic market/account comparison.

Does not fetch feeds, authenticate a provider/account, grant venue access,
reconcile remote orders, execute a plugin, install, signal, or trade.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path


class R42Refused(ValueError):
    """Fail closed with fixed non-sensitive reason codes."""


_SHA = re.compile(r"[a-f0-9]{64}\Z")
_ID = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{2,63}\Z")
_AMOUNT = re.compile(r"(?:0|[1-9][0-9]{0,15})(?:\.[0-9]{1,12})?\Z")
_TIME = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z\Z")
_POLICY_FIELDS = frozenset({"schema", "scope", "provider_id", "market", "symbol",
                            "contract_id", "region", "eligible_regions", "price_basis",
                            "volume_semantics", "timeframe_seconds", "max_market_lag_seconds",
                            "max_account_lag_seconds", "account_alias", "currency"})
_MARKET_FIELDS = frozenset({"schema", "provider_id", "market", "symbol", "contract_id",
                            "price_basis", "volume_semantics", "timeframe_seconds",
                            "received_at", "bars"})
_BAR_FIELDS = frozenset({"sequence", "open_at", "close_at", "open", "high", "low", "close", "volume"})
_ACCOUNT_FIELDS = frozenset({"schema", "provider_id", "account_alias", "currency", "observed_at",
                             "equity", "available", "margin_used", "positions", "open_orders"})
_LEDGER_FIELDS = frozenset({"schema", "account_alias", "currency", "observed_at", "equity",
                            "available", "margin_used", "positions", "open_orders"})
_POSITION_FIELDS = frozenset({"position_id", "contract_id", "side", "quantity", "entry_price"})
_ORDER_FIELDS = frozenset({"order_id", "contract_id", "side", "quantity", "limit_price"})
_MAX_FILE = 65_536


def _pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise R42Refused("R42_DUPLICATE_JSON_FIELD")
        result[key] = value
    return result


def _read(path: Path, expected_sha256: str) -> dict:
    if type(expected_sha256) is not str or not _SHA.fullmatch(expected_sha256):
        raise R42Refused("R42_INDEPENDENT_HASH_PIN_REQUIRED")
    if not isinstance(path, Path) or not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise R42Refused("R42_ABSOLUTE_NON_SYMLINK_PATH_REQUIRED")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as exc:
        raise R42Refused("R42_EVIDENCE_UNREADABLE") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 2 <= before.st_size <= _MAX_FILE:
            raise R42Refused("R42_BOUNDED_REGULAR_EVIDENCE_REQUIRED")
        data = bytearray()
        while len(data) < before.st_size:
            block = os.read(fd, min(8192, before.st_size - len(data)))
            if not block:
                raise R42Refused("R42_EVIDENCE_TRUNCATED")
            data.extend(block)
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise R42Refused("R42_EVIDENCE_CHANGED_DURING_READ")
    finally:
        os.close(fd)
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise R42Refused("R42_EVIDENCE_PIN_MISMATCH")
    try:
        obj = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (UnicodeError, ValueError, TypeError) as exc:
        if isinstance(exc, R42Refused):
            raise
        raise R42Refused("R42_EVIDENCE_INVALID_JSON") from exc
    if (type(obj) is not dict or json.dumps(obj, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False).encode() + b"\n" != data):
        raise R42Refused("R42_EVIDENCE_NONCANONICAL")
    return obj


def _fields(obj: object, keys: frozenset[str]) -> dict:
    if type(obj) is not dict or set(obj) != keys:
        raise R42Refused("R42_EVIDENCE_SCHEMA_INVALID")
    return obj


def _id(v: object) -> str:
    if type(v) is not str or not _ID.fullmatch(v):
        raise R42Refused("R42_EVIDENCE_ID_INVALID")
    return v


def _amount(v: object, *, positive: bool = False) -> Decimal:
    if type(v) is not str or not _AMOUNT.fullmatch(v):
        raise R42Refused("R42_DECIMAL_STRING_REQUIRED")
    try:
        n = Decimal(v)
    except InvalidOperation as exc:
        raise R42Refused("R42_DECIMAL_INVALID") from exc
    if not n.is_finite() or (positive and n <= 0):
        raise R42Refused("R42_DECIMAL_RANGE_INVALID")
    return n


def _time(v: object) -> datetime:
    if type(v) is not str or not _TIME.fullmatch(v):
        raise R42Refused("R42_CANONICAL_UTC_TIME_REQUIRED")
    try:
        return datetime.strptime(v, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise R42Refused("R42_INVALID_UTC_TIME") from exc


def _entities(items: object, *, positions: bool, contract_id: str) -> dict:
    if type(items) is not list or len(items) > 128:
        raise R42Refused("R42_EXPOSURE_LIST_INVALID")
    fields = _POSITION_FIELDS if positions else _ORDER_FIELDS
    key = "position_id" if positions else "order_id"
    result = {}
    last = ""
    for entry in items:
        _fields(entry, fields)
        identity = _id(entry[key])
        if identity <= last:
            raise R42Refused("R42_EXPOSURE_ORDER_OR_DUPLICATE")
        last = identity
        if entry["contract_id"] != contract_id or entry["side"] not in ("BUY", "SELL"):
            raise R42Refused("R42_UNKNOWN_CONTRACT_OR_SIDE")
        result[identity] = (
            entry["contract_id"], entry["side"], _amount(entry["quantity"], positive=True),
            _amount(entry["entry_price"] if positions else entry["limit_price"], positive=True),
        )
    return result


def _account(obj: dict, *, provider: str | None, policy: dict, as_of: datetime) -> dict:
    _fields(obj, _ACCOUNT_FIELDS if provider is not None else _LEDGER_FIELDS)
    if type(obj["schema"]) is not int or obj["schema"] != 1:
        raise R42Refused("R42_EVIDENCE_SCHEMA_VERSION_INVALID")
    if (obj.get("provider_id", provider) != provider or obj["account_alias"] != policy["account_alias"]
            or obj["currency"] != policy["currency"]):
        raise R42Refused("R42_ACCOUNT_IDENTITY_MISMATCH")
    stamp = _time(obj["observed_at"])
    lag = as_of - stamp
    if not timedelta(0) <= lag <= timedelta(seconds=policy["max_account_lag_seconds"]):
        raise R42Refused("R42_ACCOUNT_STALE_OR_FUTURE")
    amounts = tuple(_amount(obj[k]) for k in ("equity", "available", "margin_used"))
    if amounts[1] + amounts[2] > amounts[0]:
        raise R42Refused("R42_ACCOUNT_BALANCE_INCONSISTENT")
    positions = _entities(obj["positions"], positions=True, contract_id=policy["contract_id"])
    orders = _entities(obj["open_orders"], positions=False, contract_id=policy["contract_id"])
    return {"balances": amounts, "positions": positions, "open_orders": orders, "observed_at": stamp}


def _market(obj: dict, *, policy: dict, as_of: datetime) -> int:
    _fields(obj, _MARKET_FIELDS)
    if type(obj["schema"]) is not int or obj["schema"] != 1:
        raise R42Refused("R42_EVIDENCE_SCHEMA_VERSION_INVALID")
    for field in ("provider_id", "market", "symbol", "contract_id", "price_basis",
                  "volume_semantics", "timeframe_seconds"):
        if type(obj[field]) is not type(policy[field]) or obj[field] != policy[field]:
            raise R42Refused("R42_MARKET_CONTRACT_OR_SOURCE_MISMATCH")
    arrival = _time(obj["received_at"])
    if arrival > as_of:
        raise R42Refused("R42_RECEIPT_IN_FUTURE")
    bars = obj["bars"]
    if type(bars) is not list or not 2 <= len(bars) <= 128:
        raise R42Refused("R42_MARKET_BAR_COUNT_INVALID")
    prev_sequence = None
    prev_close = None
    for bar in bars:
        _fields(bar, _BAR_FIELDS)
        seq = bar["sequence"]
        if type(seq) is not int or seq <= 0 or (prev_sequence is not None and seq != prev_sequence + 1):
            raise R42Refused("R42_MARKET_SEQUENCE_GAP_OR_REPLAY")
        opened, closed = _time(bar["open_at"]), _time(bar["close_at"])
        if (closed - opened != timedelta(seconds=policy["timeframe_seconds"])
                or (prev_close is not None and opened != prev_close)
                or closed > arrival):
            raise R42Refused("R42_MARKET_TIME_GAP_OR_FUTURE")
        op, hi, lo, cl = (_amount(bar[n], positive=True) for n in ("open", "high", "low", "close"))
        _amount(bar["volume"])
        if lo > min(op, cl) or hi < max(op, cl) or lo > hi:
            raise R42Refused("R42_MARKET_OHLC_INVALID")
        prev_sequence, prev_close = seq, closed
    if as_of - prev_close > timedelta(seconds=policy["max_market_lag_seconds"]):
        raise R42Refused("R42_MARKET_STALE")
    return len(bars)


def audit(*, policy_path: Path, market_path: Path, account_path: Path, ledger_path: Path,
          policy_sha256: str, market_sha256: str, account_sha256: str, ledger_sha256: str,
          region: str, as_of_utc: str, operator_ack: bool = False) -> dict:
    if operator_ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1" or "MMT_PRODUCTION" in os.environ:
        raise R42Refused("R42_NONPRODUCTION_ACK_REQUIRED")
    if not all(isinstance(x, Path) for x in (policy_path, market_path, account_path, ledger_path)):
        raise R42Refused("R42_PATH_TYPES_REQUIRED")
    if len({str(policy_path), str(market_path), str(account_path), str(ledger_path)}) != 4:
        raise R42Refused("R42_DISTINCT_EVIDENCE_FILES_REQUIRED")
    as_of = _time(as_of_utc)
    policy = _fields(_read(policy_path, policy_sha256), _POLICY_FIELDS)
    for name in ("provider_id", "market", "symbol", "contract_id", "region", "account_alias", "currency"):
        _id(policy[name])
    if (policy["schema"] != 1 or type(policy["schema"]) is not int
            or policy["scope"] != "offline-synthetic-review-only"
            or policy["market"] not in ("SPOT", "FUTURES", "FOREX")
            or policy["price_basis"] not in ("TRADE", "BID", "ASK", "MARK")
            or policy["volume_semantics"] not in ("TRADED", "TICK_COUNT", "UNKNOWN")
            or type(policy["eligible_regions"]) is not list
            or not 1 <= len(policy["eligible_regions"]) <= 12
            or any(type(x) is not str or not _ID.fullmatch(x) for x in policy["eligible_regions"])
            or policy["eligible_regions"] != sorted(set(policy["eligible_regions"]))
            or type(policy["timeframe_seconds"]) is not int
            or policy["timeframe_seconds"] not in (60, 300, 900, 1800, 3600, 14400, 43200, 86400)
            or type(policy["max_market_lag_seconds"]) is not int
            or not 0 <= policy["max_market_lag_seconds"] <= 86400
            or type(policy["max_account_lag_seconds"]) is not int
            or not 0 <= policy["max_account_lag_seconds"] <= 86400):
        raise R42Refused("R42_REVIEW_POLICY_INVALID")
    if type(region) is not str or region != policy["region"] or region not in policy["eligible_regions"]:
        raise R42Refused("R42_REGION_POLICY_REJECTED")
    bars = _market(_read(market_path, market_sha256), policy=policy, as_of=as_of)
    source = _account(_read(account_path, account_sha256), provider=policy["provider_id"],
                      policy=policy, as_of=as_of)
    baseline = _account(_read(ledger_path, ledger_sha256), provider=None,
                        policy=policy, as_of=as_of)
    if source["balances"] != baseline["balances"]:
        raise R42Refused("R42_ACCOUNT_EQUITY_OR_MARGIN_DRIFT")
    if source["positions"] != baseline["positions"]:
        raise R42Refused("R42_POSITION_SET_OR_SIZE_DRIFT")
    if source["open_orders"] != baseline["open_orders"]:
        raise R42Refused("R42_ORDER_SET_OR_SIZE_DRIFT")
    return {"verdict": "R42_SYNTHETIC_EVIDENCE_MATCH_RELEASE_DENIED",
            "bars_checked": bars, "positions_compared": len(source["positions"]),
            "orders_compared": len(source["open_orders"]), "policy_sha256": policy_sha256,
            "market_sha256": market_sha256, "account_sha256": account_sha256,
            "ledger_sha256": ledger_sha256,
            "provider_origin_authenticated": False, "account_owner_authenticated": False,
            "region_and_venue_legally_verified": False, "remote_account_reconciled": False,
            "public_signals_authorized": False, "paper_orders_authorized": False,
            "live_orders_authorized": False, "files_written": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("policy", "market", "account", "ledger"):
        parser.add_argument("--" + name, type=Path, required=True)
        parser.add_argument("--" + name + "-sha256", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--as-of-utc", required=True)
    parser.add_argument("--ack-synthetic-offline", action="store_true")
    args = parser.parse_args(argv)
    try:
        outcome = audit(**{
            "policy_path": args.policy, "market_path": args.market,
            "account_path": args.account, "ledger_path": args.ledger,
            "policy_sha256": args.policy_sha256, "market_sha256": args.market_sha256,
            "account_sha256": args.account_sha256, "ledger_sha256": args.ledger_sha256,
            "region": args.region, "as_of_utc": args.as_of_utc,
            "operator_ack": args.ack_synthetic_offline,
        })
    except (R42Refused, OSError, ValueError, TypeError, KeyError):
        print(json.dumps({"verdict": "R42_EVIDENCE_REFUSED",
                          "files_written": False, "live_orders_authorized": False}, sort_keys=True))
        return 2
    print(json.dumps(outcome, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
