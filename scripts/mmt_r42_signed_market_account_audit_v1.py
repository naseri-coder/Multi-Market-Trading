"""R42: offline, read-only signed-capture consistency gate. Never routes orders.

A valid Ed25519 signature proves only that the pinned key signed bytes;
not that a market venue supplied them or the account has been reconciled live.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

_HEX = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[a-zA-Z0-9_.-]{3,64}\Z")
_DATE = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ\Z")
_NUMBER = re.compile(r"(?:0|[1-9][0-9]*)(?:\.[0-9]{1,12})?\Z")
_PERIODS = {"1m": 60, "5m": 300, "15m": 900, "30m": 1800,
            "1h": 3600, "4h": 14400, "12h": 43200, "1d": 86400}
_POLICY = frozenset("schema purpose venue market instrument_id symbol timeframe account_id currency region_status session_status price_tick max_feed_age_seconds max_account_age_seconds max_pair_skew_seconds max_spread_bps max_equity_diff max_exposure_diff min_feed_sequence min_account_sequence valid_from valid_until".split())
_FEED = frozenset("schema origin venue market instrument_id symbol timeframe sequence bar_open_at bar_close_at captured_at open high low close volume bid ask price_basis volume_semantics".split())
_ACCOUNT = frozenset("schema origin venue account_id currency observed_at equity gross_exposure open_order_ids position_ids sequence".split())
_ROLES = ("FEED", "ACCOUNT_PRIMARY", "ACCOUNT_REVIEW")


class R42Refused(ValueError):
    """Fixed failure codes; never echo market/account information."""


def _file(path: Path, limit: int) -> bytes:
    if not isinstance(path, Path) or not path.is_absolute() or any(
        x.is_symlink() for x in (path, *path.parents)
    ):
        raise R42Refused("R42_REGULAR_ABSOLUTE_UNLINKED_FILE_REQUIRED")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as exc:
        raise R42Refused("R42_FILE_UNREADABLE") from exc
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 1 <= before.st_size <= limit:
            raise R42Refused("R42_FILE_BOUNDS_INVALID")
        result = bytearray()
        while len(result) < before.st_size:
            block = os.read(fd, min(65536, before.st_size - len(result)))
            if not block:
                raise R42Refused("R42_FILE_CHANGED")
            result.extend(block)
        after = os.fstat(fd)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns
        ):
            raise R42Refused("R42_FILE_CHANGED")
        return bytes(result)
    finally:
        os.close(fd)


def _pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise R42Refused("R42_DUPLICATE_JSON_FIELD")
        result[key] = value
    return result


def _parse(raw: bytes, fields: frozenset[str]) -> dict:
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (UnicodeError, ValueError, TypeError) as exc:
        if isinstance(exc, R42Refused):
            raise
        raise R42Refused("R42_INVALID_JSON") from exc
    if type(data) is not dict or set(data) != fields:
        raise R42Refused("R42_UNEXPECTED_JSON_FIELDS")
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True, allow_nan=False).encode() + b"\n"
    if raw != canonical or type(data["schema"]) is not int or data["schema"] != 1:
        raise R42Refused("R42_NONCANONICAL_JSON_OR_SCHEMA")
    return data


def _stamp(value: object) -> datetime:
    if type(value) is not str or not _DATE.fullmatch(value):
        raise R42Refused("R42_UTC_TIMESTAMP_REQUIRED")
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise R42Refused("R42_INVALID_TIMESTAMP") from exc
    return moment.astimezone(UTC)


def _num(value: object, *, positive: bool = False) -> Decimal:
    if type(value) is not str or len(value) > 48 or not _NUMBER.fullmatch(value):
        raise R42Refused("R42_DECIMAL_FORMAT_INVALID")
    try:
        number = Decimal(value)
    except InvalidOperation as exc:
        raise R42Refused("R42_DECIMAL_INVALID") from exc
    if not number.is_finite() or number < 0 or positive and number == 0:
        raise R42Refused("R42_DECIMAL_OUT_OF_BOUNDS")
    return number


def _integer(value: object, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise R42Refused("R42_INTEGER_OUT_OF_BOUNDS")
    return value


def _pin(value: str) -> str:
    if type(value) is not str or not _HEX.fullmatch(value):
        raise R42Refused("R42_EXTERNAL_SHA256_PIN_REQUIRED")
    return value


def _signed(role: str, data_path: Path, sig_path: Path, key_path: Path,
            pin: str, key_pin: str, fields: frozenset[str]) -> dict:
    data = _file(data_path, 8192)
    if hashlib.sha256(data).hexdigest() != _pin(pin):
        raise R42Refused("R42_SIGNED_PAYLOAD_PIN_MISMATCH")
    parsed = _parse(data, fields)
    signature = _file(sig_path, 64)
    if len(signature) != 64:
        raise R42Refused("R42_SIGNATURE_LENGTH_INVALID")
    pem = _file(key_path, 4096)
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        key = serialization.load_pem_public_key(pem)
        if not isinstance(key, Ed25519PublicKey):
            raise R42Refused("R42_ED25519_KEY_REQUIRED")
        der = key.public_bytes(serialization.Encoding.DER,
                               serialization.PublicFormat.SubjectPublicKeyInfo)
        if hashlib.sha256(der).hexdigest() != _pin(key_pin):
            raise R42Refused("R42_TRUSTED_KEY_MISMATCH")
        key.verify(signature, ("MMT-R42-" + role + "-V1\n").encode() + data)
    except ImportError as exc:
        raise R42Refused("R42_CRYPTO_AUDITOR_NOT_INSTALLED") from exc
    except (InvalidSignature, ValueError, TypeError) as exc:
        if isinstance(exc, R42Refused):
            raise
        raise R42Refused("R42_INVALID_SIGNATURE_OR_KEY") from exc
    return parsed


def _ids(values: object) -> tuple[str, ...]:
    if type(values) is not list or len(values) > 64 or any(
        type(v) is not str or not _ID.fullmatch(v) for v in values
    ) or len(set(values)) != len(values) or values != sorted(values):
        raise R42Refused("R42_ORDER_IDS_INVALID")
    return tuple(values)


def audit(*, policy_path: Path, policy_sha256: str, feed_path: Path,
          feed_signature: Path, feed_public_key: Path, feed_sha256: str,
          feed_key_spki_sha256: str, primary_path: Path,
          primary_signature: Path, primary_public_key: Path,
          primary_sha256: str, primary_key_spki_sha256: str,
          review_path: Path, review_signature: Path, review_public_key: Path,
          review_sha256: str, review_key_spki_sha256: str,
          now: datetime) -> dict:
    """Verify only signed offline snapshots and independently pinned policy."""
    if os.environ.get("MMT_NONPRODUCTION") != "1" or "MMT_PRODUCTION" in os.environ:
        raise R42Refused("R42_NONPRODUCTION_REQUIRED")
    if type(now) is not datetime or now.tzinfo is None or now.utcoffset() is None:
        raise R42Refused("R42_TRUSTED_AWARE_TIME_REQUIRED")
    now = now.astimezone(UTC)
    pins = (feed_key_spki_sha256, primary_key_spki_sha256, review_key_spki_sha256)
    if len({_pin(x) for x in pins}) != 3:
        raise R42Refused("R42_INDEPENDENT_SIGNERS_REQUIRED")
    raw = _file(policy_path, 8192)
    if hashlib.sha256(raw).hexdigest() != _pin(policy_sha256):
        raise R42Refused("R42_POLICY_PIN_MISMATCH")
    policy = _parse(raw, _POLICY)
    if (policy["purpose"] != "OFFLINE_RESEARCH_ONLY"
            or policy["region_status"] != "UNVERIFIED_FOR_TRADING"
            or policy["session_status"] != "UNVERIFIED_FOR_TRADING"):
        raise R42Refused("R42_TRADING_ELIGIBILITY_NOT_ALLOWED")
    for name in ("venue", "market", "instrument_id", "symbol", "account_id", "currency"):
        if type(policy[name]) is not str or not _ID.fullmatch(policy[name]):
            raise R42Refused("R42_POLICY_IDENTITY_INVALID")
    if type(policy["timeframe"]) is not str or policy["timeframe"] not in _PERIODS:
        raise R42Refused("R42_POLICY_TIMEFRAME_INVALID")
    tick = _num(policy["price_tick"], positive=True)
    spread_max = _integer(policy["max_spread_bps"], 0, 10000)
    feed_age = _integer(policy["max_feed_age_seconds"], 1, 86400)
    account_age = _integer(policy["max_account_age_seconds"], 1, 86400)
    max_gap = _integer(policy["max_pair_skew_seconds"], 0, 3600)
    min_feed_seq = _integer(policy["min_feed_sequence"], 1, 10**12)
    min_account_seq = _integer(policy["min_account_sequence"], 1, 10**12)
    equity_diff = _num(policy["max_equity_diff"])
    exposure_diff = _num(policy["max_exposure_diff"])
    if not _stamp(policy["valid_from"]) <= now <= _stamp(policy["valid_until"]):
        raise R42Refused("R42_OPERATOR_POLICY_EXPIRED_OR_EARLY")
    feed = _signed("FEED", feed_path, feed_signature, feed_public_key,
                   feed_sha256, feed_key_spki_sha256, _FEED)
    primary = _signed("ACCOUNT_PRIMARY", primary_path, primary_signature,
                      primary_public_key, primary_sha256,
                      primary_key_spki_sha256, _ACCOUNT)
    review = _signed("ACCOUNT_REVIEW", review_path, review_signature,
                     review_public_key, review_sha256,
                     review_key_spki_sha256, _ACCOUNT)
    if (feed["origin"] != "OFFLINE_UNVERIFIED_CAPTURE"
            or feed["price_basis"] != "TRADE"
            or feed["volume_semantics"] != "TRADED"):
        raise R42Refused("R42_FEED_ORIGIN_OR_SEMANTICS_INVALID")
    for name in ("venue", "market", "instrument_id", "symbol", "timeframe"):
        if feed[name] != policy[name]:
            raise R42Refused("R42_FEED_IDENTITY_MISMATCH")
    if _integer(feed["sequence"], 1, 10**12) < min_feed_seq:
        raise R42Refused("R42_FEED_SEQUENCE_REPLAY")
    opened, closed, captured = (_stamp(feed[n]) for n in
                                ("bar_open_at", "bar_close_at", "captured_at"))
    if (closed - opened != timedelta(seconds=_PERIODS[policy["timeframe"]])
            or opened >= closed or closed > captured or captured > now
            or (now - captured).total_seconds() > feed_age):
        raise R42Refused("R42_STALE_OR_CAUSALLY_INVALID_FEED")
    prices = {name: _num(feed[name], positive=name != "volume")
              for name in ("open", "high", "low", "close", "volume", "bid", "ask")}
    try:
        invalid_price = (
            prices["low"] > min(prices["open"], prices["close"])
            or prices["high"] < max(prices["open"], prices["close"])
            or prices["low"] > prices["high"]
            or prices["bid"] > prices["ask"]
            or (prices["ask"] - prices["bid"]) * 10000 > prices["close"] * spread_max
            or any(prices[k] % tick for k in ("open", "high", "low", "close", "bid", "ask"))
        )
    except InvalidOperation as exc:
        raise R42Refused("R42_DECIMAL_PRECISION_UNSAFE") from exc
    if invalid_price:
        raise R42Refused("R42_INVALID_OHLC_SPREAD_OR_TICK")
    for item, origin in ((primary, "OFFLINE_PRIMARY_CAPTURE"),
                         (review, "OFFLINE_INDEPENDENT_REVIEW")):
        if item["origin"] != origin or any(
            item[name] != policy[name] for name in ("venue", "account_id", "currency")
        ):
            raise R42Refused("R42_ACCOUNT_IDENTITY_OR_ORIGIN_MISMATCH")
        if _integer(item["sequence"], 1, 10**12) < min_account_seq:
            raise R42Refused("R42_ACCOUNT_SEQUENCE_REPLAY")
        age = (now - _stamp(item["observed_at"])).total_seconds()
        if not 0 <= age <= account_age:
            raise R42Refused("R42_ACCOUNT_CAPTURE_STALE_OR_FUTURE")
        _ids(item["open_order_ids"])
        _ids(item["position_ids"])
        _num(item["equity"])
        _num(item["gross_exposure"])
    if (abs((_stamp(primary["observed_at"]) - _stamp(review["observed_at"])).total_seconds()) > max_gap
            or any(abs((_stamp(item["observed_at"]) - captured).total_seconds()) > max_gap
                   for item in (primary, review))):
        raise R42Refused("R42_ACCOUNT_CAPTURES_TIME_SKEW")
    if (abs(_num(primary["equity"]) - _num(review["equity"])) > equity_diff
            or abs(_num(primary["gross_exposure"]) - _num(review["gross_exposure"])) > exposure_diff
            or primary["open_order_ids"] != review["open_order_ids"]
            or primary["position_ids"] != review["position_ids"]
            or primary["sequence"] != review["sequence"]):
        raise R42Refused("R42_ACCOUNT_EQUITY_EXPOSURE_OR_ORDERS_DISAGREE")
    return {
        "verdict": "R42_SIGNED_OFFLINE_CAPTURES_CONSISTENT_RELEASE_DENIED",
        "policy_sha256": _pin(policy_sha256),
        "feed_sha256": _pin(feed_sha256),
        "primary_account_sha256": _pin(primary_sha256),
        "review_account_sha256": _pin(review_sha256),
        "three_distinct_pinned_signers_verified": True,
        "offline_feed_quality_checked": True,
        "offline_account_capture_consistency_checked": True,
        "real_provider_provenance_verified": False,
        "real_account_reconciliation_verified": False,
        "venue_session_and_region_eligible": False,
        "broker_order_authorized": False,
        "telegram_authorized": False,
        "live_authorized": False,
        "public_release_authorized": False,
        "files_written": False,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--policy-path", type=Path, required=True)
    ap.add_argument("--policy-sha256", required=True)
    for role in ("feed", "primary", "review"):
        for suffix, kind in (("path", Path), ("signature", Path),
                             ("public-key", Path), ("sha256", str),
                             ("key-spki-sha256", str)):
            ap.add_argument("--" + role + "-" + suffix, type=kind, required=True)
    ap.add_argument("--now-utc", required=True)
    args = ap.parse_args(argv)
    try:
        outcome = audit(
            policy_path=args.policy_path, policy_sha256=args.policy_sha256,
            feed_path=args.feed_path, feed_signature=args.feed_signature,
            feed_public_key=args.feed_public_key, feed_sha256=args.feed_sha256,
            feed_key_spki_sha256=args.feed_key_spki_sha256,
            primary_path=args.primary_path, primary_signature=args.primary_signature,
            primary_public_key=args.primary_public_key, primary_sha256=args.primary_sha256,
            primary_key_spki_sha256=args.primary_key_spki_sha256,
            review_path=args.review_path, review_signature=args.review_signature,
            review_public_key=args.review_public_key, review_sha256=args.review_sha256,
            review_key_spki_sha256=args.review_key_spki_sha256,
            now=_stamp(args.now_utc),
        )
    except (R42Refused, OSError, ValueError) as exc:
        print(json.dumps({"verdict": "R42_OFFLINE_EVIDENCE_REFUSED",
                          "reason": str(exc) if isinstance(exc, R42Refused) else "R42_INPUT_REFUSED",
                          "live_authorized": False, "files_written": False}, sort_keys=True))
        return 2
    print(json.dumps(outcome, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
