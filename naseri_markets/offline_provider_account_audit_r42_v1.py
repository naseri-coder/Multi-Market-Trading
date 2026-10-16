"""R42 bounded offline evidence checks; never authenticates providers or accounts.

All four independently pinned blobs are treated as inert SYNTHETIC research
snapshots. Cryptographic hashes prove only byte consistency, NOT publisher
identity, venue session eligibility, available funds, or trading permission.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal

_MAX = 16_384
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{2,63}\Z")
_SYMBOL = re.compile(r"[A-Z0-9]{3,24}\Z")
_AMOUNT = re.compile(r"(?:0|[1-9][0-9]{0,11})(?:\.[0-9]{1,8})?\Z")
_POLICY_KEYS = frozenset({
    "schema", "provider", "market", "symbol", "account_id", "currency",
    "residency", "eligible_residencies", "max_feed_age_seconds",
    "max_account_age_seconds", "max_spread_fraction",
})
_FEED_KEYS = frozenset({
    "schema", "provider", "market", "symbol", "origin", "sequence",
    "source_ref", "observed_at", "received_at", "bid", "ask",
})
_ACCOUNT_KEYS = frozenset({
    "schema", "account_id", "currency", "observed_at", "equity",
    "available", "positions", "open_orders",
})
_POSITION_KEYS = frozenset({"symbol", "quantity"})
_ORDER_KEYS = frozenset({"order_id", "symbol", "side", "quantity"})


class R42Refused(ValueError):
    """Fixed denial reason codes; never echo account data or credentials."""


def _pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise R42Refused("R42_DUPLICATE_EVIDENCE_FIELD")
        result[key] = value
    return result


def _parse(raw: bytes, expected_sha: str, fields: frozenset) -> dict:
    if (type(expected_sha) is not str or not _SHA.fullmatch(expected_sha)
            or type(raw) is not bytes or not 1 <= len(raw) <= _MAX):
        raise R42Refused("R42_EXPLICIT_BOUNDED_EVIDENCE_PIN_REQUIRED")
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise R42Refused("R42_EVIDENCE_SHA256_MISMATCH")
    try:
        obj = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                         parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except R42Refused:
        raise
    except (ValueError, UnicodeError, TypeError, RecursionError) as exc:
        raise R42Refused("R42_INVALID_EVIDENCE_JSON") from exc
    if type(obj) is not dict or set(obj) != fields:
        raise R42Refused("R42_UNEXPECTED_EVIDENCE_SCHEMA")
    if (json.dumps(obj, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=True, allow_nan=False).encode() + b"\n" != raw):
        raise R42Refused("R42_NONCANONICAL_EVIDENCE")
    return obj


def _stamp(value: object) -> datetime:
    if type(value) is not str or not 20 <= len(value) <= 32:
        raise R42Refused("R42_INVALID_UTC_TIMESTAMP")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise R42Refused("R42_INVALID_UTC_TIMESTAMP") from exc
    if (parsed.tzinfo is None or parsed.utcoffset() != timedelta(0)
            or parsed.isoformat(timespec="seconds") != value):
        raise R42Refused("R42_CANONICAL_UTC_TIMESTAMP_REQUIRED")
    return parsed.astimezone(UTC)


def _number(value: object, *, zero_ok: bool = True) -> Decimal:
    if type(value) is not str or not _AMOUNT.fullmatch(value):
        raise R42Refused("R42_CANONICAL_FINITE_DECIMAL_REQUIRED")
    number = Decimal(value)
    if not zero_ok and number <= 0:
        raise R42Refused("R42_POSITIVE_DECIMAL_REQUIRED")
    return number


def _name(value: object, pattern: re.Pattern) -> None:
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise R42Refused("R42_INVALID_EVIDENCE_IDENTITY")


def _account(obj: dict, policy: dict, now: datetime) -> dict:
    if (type(obj["schema"]) is not int or obj["schema"] != 1
            or obj["account_id"] != policy["account_id"]
            or obj["currency"] != policy["currency"]):
        raise R42Refused("R42_ACCOUNT_IDENTITY_MISMATCH")
    when = _stamp(obj["observed_at"])
    if not timedelta(0) <= now - when <= timedelta(
        seconds=policy["max_account_age_seconds"]
    ):
        raise R42Refused("R42_STALE_OR_FUTURE_ACCOUNT_SNAPSHOT")
    equity = _number(obj["equity"], zero_ok=False)
    available = _number(obj["available"])
    if available > equity:
        raise R42Refused("R42_IMPOSSIBLE_ACCOUNT_BALANCE")
    positions = obj["positions"]
    orders = obj["open_orders"]
    if (type(positions) is not list or type(orders) is not list
            or len(positions) > 32 or len(orders) > 32):
        raise R42Refused("R42_UNBOUNDED_ACCOUNT_EXPOSURE")
    seen_pos, seen_orders = set(), set()
    for item in positions:
        if type(item) is not dict or set(item) != _POSITION_KEYS:
            raise R42Refused("R42_POSITION_SCHEMA_INVALID")
        _name(item["symbol"], _SYMBOL)
        _number(item["quantity"], zero_ok=False)
        if item["symbol"] in seen_pos:
            raise R42Refused("R42_DUPLICATE_POSITION")
        seen_pos.add(item["symbol"])
    for item in orders:
        if type(item) is not dict or set(item) != _ORDER_KEYS:
            raise R42Refused("R42_ORDER_SCHEMA_INVALID")
        _name(item["order_id"], _NAME)
        _name(item["symbol"], _SYMBOL)
        if item["side"] not in ("buy", "sell"):
            raise R42Refused("R42_UNKNOWN_ORDER_SIDE")
        _number(item["quantity"], zero_ok=False)
        if item["order_id"] in seen_orders:
            raise R42Refused("R42_DUPLICATE_OPEN_ORDER")
        seen_orders.add(item["order_id"])
    # The returned canonical representation is locally constructed; the
    # caller never receives a supposedly 'authenticated' venue balance.
    return {"equity": equity, "available": available,
            "positions": positions, "orders": orders}


def evaluate(*, policy_bytes: bytes, feed_bytes: bytes,
             local_account_bytes: bytes, provider_account_bytes: bytes,
             expected_policy_sha256: str, expected_feed_sha256: str,
             expected_local_sha256: str, expected_provider_account_sha256: str,
             expected_previous_sequence: int, as_of: datetime,
             operator_ack: bool = False) -> dict:
    """No side effects; accept snapshot consistency only, never LIVE rights."""
    if (operator_ack is not True or os.environ.get("MMT_NONPRODUCTION") != "1"
            or "MMT_PRODUCTION" in os.environ):
        raise R42Refused("R42_NONPRODUCTION_EXPLICIT_ACK_REQUIRED")
    if (type(as_of) is not datetime or as_of.tzinfo is None
            or as_of.utcoffset() != timedelta(0)
            or type(expected_previous_sequence) is not int
            or not 0 <= expected_previous_sequence < 2**63 - 1):
        raise R42Refused("R42_EXTERNAL_CLOCK_SEQUENCE_REQUIRED")
    now = as_of.astimezone(UTC)
    policy = _parse(policy_bytes, expected_policy_sha256, _POLICY_KEYS)
    feed = _parse(feed_bytes, expected_feed_sha256, _FEED_KEYS)
    local = _parse(local_account_bytes, expected_local_sha256, _ACCOUNT_KEYS)
    remote = _parse(provider_account_bytes, expected_provider_account_sha256,
                    _ACCOUNT_KEYS)
    if (type(policy["schema"]) is not int or policy["schema"] != 1
            or policy["market"] not in ("crypto", "forex")
            or type(policy["market"]) is not str):
        raise R42Refused("R42_POLICY_SCHEMA_INVALID")
    for key in ("provider", "account_id", "residency"):
        _name(policy[key], _NAME)
    for key in ("symbol", "currency"):
        _name(policy[key], _SYMBOL)
    eligible = policy["eligible_residencies"]
    if (type(eligible) is not list or not 1 <= len(eligible) <= 16
            or not all(type(x) is str and _NAME.fullmatch(x) for x in eligible)
            or len(set(eligible)) != len(eligible)
            or policy["residency"] not in eligible):
        raise R42Refused("R42_RESIDENCY_NOT_APPROVED_BY_LOCAL_POLICY")
    for name in ("max_feed_age_seconds", "max_account_age_seconds"):
        v = policy[name]
        if type(v) is not int or not 1 <= v <= 3600:
            raise R42Refused("R42_UNSAFE_FRESHNESS_POLICY")
    spread_limit = _number(policy["max_spread_fraction"])
    if not Decimal(0) <= spread_limit <= Decimal("0.1"):
        raise R42Refused("R42_UNSAFE_SPREAD_POLICY")
    if (type(feed["schema"]) is not int or feed["schema"] != 1
            or feed["origin"] != "synthetic"
            or any(feed[field] != policy[field]
                   for field in ("provider", "market", "symbol"))):
        raise R42Refused("R42_FEED_IDENTITY_OR_ORIGIN_MISMATCH")
    _name(feed["source_ref"], _NAME)
    if (type(feed["sequence"]) is not int
            or feed["sequence"] != expected_previous_sequence + 1):
        raise R42Refused("R42_FEED_SEQUENCE_GAP_OR_REPLAY")
    observed = _stamp(feed["observed_at"])
    received = _stamp(feed["received_at"])
    if not (observed <= received <= now
            and now - observed <= timedelta(seconds=policy["max_feed_age_seconds"])):
        raise R42Refused("R42_FEED_STALE_FUTURE_OR_OUT_OF_ORDER")
    bid = _number(feed["bid"], zero_ok=False)
    ask = _number(feed["ask"], zero_ok=False)
    if bid > ask or (ask - bid) / ask > spread_limit:
        raise R42Refused("R42_CROSSED_OR_EXCESSIVE_SPREAD")
    a = _account(local, policy, now)
    b = _account(remote, policy, now)
    if (a["equity"] != b["equity"] or a["available"] != b["available"]
            or a["positions"] != b["positions"]
            or a["orders"] != b["orders"]):
        raise R42Refused("R42_UNKNOWN_EXTERNAL_EXPOSURE_OR_ACCOUNT_DRIFT")
    return {
        "verdict": "R42_OFFLINE_SNAPSHOT_CONSISTENT_AUTHENTICATION_UNVERIFIED",
        "policy_sha256": expected_policy_sha256,
        "feed_sha256": expected_feed_sha256,
        "local_account_sha256": expected_local_sha256,
        "provider_account_sha256": expected_provider_account_sha256,
        "sequence": feed["sequence"],
        "matched_open_positions": len(a["positions"]),
        "matched_open_orders": len(a["orders"]),
        "data_provider_authenticated": False,
        "external_account_authenticated": False,
        "residency_and_venue_eligibility_verified": False,
        "provider_account_trading_authorized": False,
        "paper_connected_authorized": False,
        "telegram_authorized": False,
        "live_authorized": False,
        "public_release_authorized": False,
        "files_written": False,
    }


__all__ = ["R42Refused", "evaluate"]
