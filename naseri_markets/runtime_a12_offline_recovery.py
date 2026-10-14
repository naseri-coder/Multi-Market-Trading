"""RUNTIME-A12: INERT two-key witness-recovery rehearsal, never a runtime grant.

A10/A11 anchors and key custody are operator-supplied claims. This module
cannot authenticate physical media, trusted time, key compromise or a latest
external monotonic floor. It makes no system, Docker, DB or network changes.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime

from .runtime_a10_evidence_anchor import (
    A10Refused,
    _canonical,
    _nonproduction,
    _operator,
    _second,
)
from .runtime_a11_offline_witness import (
    A11Refused,
    _anchor,
    _key,
    _parse_signed,
    _sha,
    compare_witness_receipt,
)

_AUDIENCE = "MMT-RUNTIME-A12-INERT-KEY-HANDOFF-V1"
_MODE = "NONPRODUCTION_CONTINUITY_EXERCISE_ONLY"
_FIELDS = frozenset({
    "schema", "audience", "mode", "old_witness_id", "new_witness_id",
    "a10_ledger_id", "old_a10_sequence", "old_a10_hash",
    "old_a10_anchor_sha256", "old_receipt_sha256",
    "previous_key_epoch", "new_key_epoch", "claimed_utc_epoch", "nonce",
})
_MAC_OLD = b"MMT-A12-OLD-REVIEW-KEY-V1\x00"
_MAC_NEW = b"MMT-A12-NEW-REVIEW-KEY-V1\x00"
_MAX_BYTES = 4096


class A12Refused(ValueError):
    """No custody secret, key material, or raw receipt is included in errors."""


@dataclass(frozen=True, slots=True)
class RotationProposal:
    envelope: bytes
    sha256: str
    new_key_epoch: int
    new_witness_id: str
    status: str = "A12_DUAL_MAC_PROPOSAL_NOT_INDEPENDENTLY_CUSTODIED"
    recovery_activated: bool = False
    media_independence_proven: bool = False
    prior_key_retired: bool = False
    worker_execution_authorized: bool = False
    quarantine_release_authorized: bool = False
    broker_authorized: bool = False
    telegram_authorized: bool = False


@dataclass(frozen=True, slots=True)
class RecoveryReview:
    proposal_sha256: str
    new_key_epoch: int
    old_a10_sequence: int
    new_a10_sequence: int
    new_witness_id: str
    status: str = "A12_REPLACEMENT_WITNESS_SIMULATION_ONLY"
    media_independence_proven: bool = False
    external_latest_floor_authenticated: bool = False
    trusted_key_rotation_proven: bool = False
    recovery_activated: bool = False
    worker_execution_authorized: bool = False
    quarantine_release_authorized: bool = False
    broker_authorized: bool = False
    telegram_authorized: bool = False


@dataclass(frozen=True, slots=True)
class MediaLossReview:
    status: str = "A12_MEDIA_LOSS_BLOCKED_INDEPENDENT_EVIDENCE_REQUIRED"
    automatic_recovery_permitted: bool = False
    witness_identity_renewed: bool = False
    key_rotation_performed: bool = False
    worker_execution_authorized: bool = False
    quarantine_release_authorized: bool = False
    broker_authorized: bool = False
    telegram_authorized: bool = False


def _gate() -> None:
    try:
        _nonproduction()
    except A10Refused as exc:
        raise A12Refused("A12_NONPRODUCTION_ONLY") from exc


def _approve(operator_id: int, allowed: frozenset[int], ack: bool) -> None:
    try:
        _operator(operator_id, allowed, ack)
    except A10Refused as exc:
        raise A12Refused("A12_OPERATOR_ACK_REQUIRED") from exc


def _key_pair(old_key: bytes, new_key: bytes) -> None:
    try:
        _key(old_key)
        _key(new_key)
    except A11Refused as exc:
        raise A12Refused("A12_EXACT_TWO_KEYS_REQUIRED") from exc
    if hmac.compare_digest(old_key, new_key):
        raise A12Refused("A12_KEY_REUSE_FORBIDDEN")


def _epoch(value: int) -> None:
    if type(value) is not int or not 1 <= value <= 2_147_483_646:
        raise A12Refused("A12_PINNED_KEY_EPOCH_REQUIRED")


def _parse_anchor(raw: bytes) -> dict:
    try:
        return _anchor(raw)
    except A11Refused as exc:
        raise A12Refused("A12_CANONICAL_A10_ANCHOR_REQUIRED") from exc


def _old_floor(raw: bytes, anchor: bytes, key: bytes) -> dict:
    """Only checks a caller-supplied floor. Its independent origin is unproven."""
    try:
        p = _parse_signed(raw, key)
        compare_witness_receipt(
            raw, anchor, key=key, expected_witness_id=p["witness_id"],
            trusted_floor_receipt=raw,
        )
        return p
    except (A11Refused, A10Refused) as exc:
        raise A12Refused("A12_OLD_FLOOR_NOT_VERIFIED") from exc


def _mac(payload: dict, key: bytes, domain: bytes) -> str:
    return hmac.new(key, domain + _canonical(payload), hashlib.sha256).hexdigest()


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for k, value in pairs:
        if k in result:
            raise A12Refused("A12_DUPLICATE_KEY")
        result[k] = value
    return result


def _reject_float(_: str) -> None:
    raise A12Refused("A12_NONINTEGER_NUMBER")


def _parse_proposal(raw: bytes, old_key: bytes, new_key: bytes) -> dict:
    _key_pair(old_key, new_key)
    if type(raw) is not bytes or not 0 < len(raw) <= _MAX_BYTES:
        raise A12Refused("A12_BOUNDED_PROPOSAL_REQUIRED")
    try:
        obj = json.loads(
            raw.decode("ascii"), object_pairs_hook=_unique,
            parse_float=_reject_float, parse_constant=_reject_float,
        )
    except A12Refused:
        raise
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise A12Refused("A12_PROPOSAL_JSON_INVALID") from exc
    if (type(obj) is not dict
            or set(obj) != {"payload", "old_mac_sha256", "new_mac_sha256"}
            or type(obj["payload"]) is not dict
            or set(obj["payload"]) != _FIELDS
            or not _sha(obj["old_mac_sha256"])
            or not _sha(obj["new_mac_sha256"])
            or _canonical(obj) != raw):
        raise A12Refused("A12_PROPOSAL_CANONICAL_SCHEMA_INVALID")
    p = obj["payload"]
    if (type(p["schema"]) is not int or p["schema"] != 1
            or p["audience"] != _AUDIENCE or p["mode"] != _MODE
            or not _sha(p["old_witness_id"], 32)
            or not _sha(p["new_witness_id"], 32)
            or p["new_witness_id"] == p["old_witness_id"]
            or not _sha(p["a10_ledger_id"], 32)
            or not _sha(p["old_a10_hash"])
            or not _sha(p["old_receipt_sha256"])
            or not _sha(p["old_a10_anchor_sha256"])
            or type(p["old_a10_sequence"]) is not int
            or p["old_a10_sequence"] <= 0
            or type(p["previous_key_epoch"]) is not int
            or not 1 <= p["previous_key_epoch"] <= 2_147_483_646
            or type(p["new_key_epoch"]) is not int
            or p["new_key_epoch"] != p["previous_key_epoch"] + 1
            or type(p["claimed_utc_epoch"]) is not int
            or p["claimed_utc_epoch"] <= 0
            or type(p["nonce"]) is not str
            or len(p["nonce"]) != 48
            or not all(c in "0123456789abcdef" for c in p["nonce"])):
        raise A12Refused("A12_HANDOFF_FIELDS_INVALID")
    if (not hmac.compare_digest(
            obj["old_mac_sha256"], _mac(p, old_key, _MAC_OLD),
        ) or not hmac.compare_digest(
            obj["new_mac_sha256"], _mac(p, new_key, _MAC_NEW),
        )):
        raise A12Refused("A12_DUAL_MAC_MISMATCH")
    return p


def block_lost_media(*, media_accessible: bool,
                     authentic_latest_floor_available: bool) -> MediaLossReview:
    """Fail closed if physical custody/floor is unavailable. Never restore.

    Even both inputs True do not confer custody or activation; they only
    describe operator claims. Recovery requires a separately reviewed bridge.
    """
    _gate()
    if type(media_accessible) is not bool or type(authentic_latest_floor_available) is not bool:
        raise A12Refused("A12_EXPLICIT_MEDIA_STATE_REQUIRED")
    return MediaLossReview()


def propose_key_rotation(
    *, old_receipt: bytes, old_anchor: bytes,
    retained_old_floor: bytes, old_key: bytes, new_key: bytes,
    new_witness_id: str, previous_key_epoch: int, at: datetime,
    operator_id: int, authorized_operators: frozenset[int],
    operator_ack: bool = False,
) -> RotationProposal:
    """Two-key continuity proposal; NOT activation or real key retirement."""
    _gate()
    _approve(operator_id, authorized_operators, operator_ack)
    _key_pair(old_key, new_key)
    _epoch(previous_key_epoch)
    if type(old_receipt) is not bytes or type(retained_old_floor) is not bytes:
        raise A12Refused("A12_EXPLICIT_OLD_FLOOR_REQUIRED")
    if not hmac.compare_digest(old_receipt, retained_old_floor):
        raise A12Refused("A12_STALE_OLD_RECEIPT_BELOW_SUPPLIED_FLOOR")
    old = _old_floor(retained_old_floor, old_anchor, old_key)
    a = _parse_anchor(old_anchor)
    if (not _sha(new_witness_id, 32)
            or new_witness_id == old["witness_id"]):
        raise A12Refused("A12_NEW_WITNESS_ID_REQUIRED")
    try:
        timestamp = _second(at)
    except A10Refused as exc:
        raise A12Refused("A12_EXACT_UTC_TIMESTAMP_REQUIRED") from exc
    payload = {
        "schema": 1, "audience": _AUDIENCE, "mode": _MODE,
        "old_witness_id": old["witness_id"],
        "new_witness_id": new_witness_id,
        "a10_ledger_id": a["ledger_id"],
        "old_a10_sequence": a["sequence"],
        "old_a10_hash": a["record_hash"],
        "old_a10_anchor_sha256": hashlib.sha256(old_anchor).hexdigest(),
        "old_receipt_sha256": hashlib.sha256(retained_old_floor).hexdigest(),
        "previous_key_epoch": previous_key_epoch,
        "new_key_epoch": previous_key_epoch + 1,
        "claimed_utc_epoch": timestamp, "nonce": secrets.token_hex(24),
    }
    body = _canonical({
        "payload": payload,
        "old_mac_sha256": _mac(payload, old_key, _MAC_OLD),
        "new_mac_sha256": _mac(payload, new_key, _MAC_NEW),
    })
    return RotationProposal(
        body, hashlib.sha256(body).hexdigest(),
        previous_key_epoch + 1, new_witness_id,
    )


def verify_key_rotation(
    proposal: bytes, *, old_receipt: bytes,
    retained_old_floor: bytes, old_anchor: bytes,
    old_key: bytes, new_key: bytes, expected_new_witness_id: str,
    pinned_previous_key_epoch: int,
) -> dict:
    """Verify dual-key claims against explicit caller-retained monotonic pins."""
    _gate()
    _epoch(pinned_previous_key_epoch)
    if (type(old_receipt) is not bytes or type(retained_old_floor) is not bytes
            or not hmac.compare_digest(old_receipt, retained_old_floor)):
        raise A12Refused("A12_STALE_OLD_RECEIPT_BELOW_SUPPLIED_FLOOR")
    p = _parse_proposal(proposal, old_key, new_key)
    old = _old_floor(retained_old_floor, old_anchor, old_key)
    a = _parse_anchor(old_anchor)
    if (not _sha(expected_new_witness_id, 32)
            or p["new_witness_id"] != expected_new_witness_id
            or p["old_witness_id"] != old["witness_id"]
            or p["a10_ledger_id"] != a["ledger_id"]
            or p["old_a10_sequence"] != a["sequence"]
            or p["old_a10_hash"] != a["record_hash"]
            or p["old_a10_anchor_sha256"]
            != hashlib.sha256(old_anchor).hexdigest()
            or p["old_receipt_sha256"]
            != hashlib.sha256(retained_old_floor).hexdigest()
            or p["previous_key_epoch"] != pinned_previous_key_epoch):
        raise A12Refused("A12_HANDOFF_OUT_OF_BAND_PIN_MISMATCH")
    return p


def verify_replacement_witness(
    proposal: bytes, *, old_receipt: bytes,
    retained_old_floor: bytes, old_anchor: bytes,
    old_key: bytes, new_key: bytes, expected_new_witness_id: str,
    pinned_previous_key_epoch: int,
    replacement_receipt: bytes, replacement_anchor: bytes,
) -> RecoveryReview:
    """Compare new witness genesis to dual-MAC handoff, without activating it."""
    p = verify_key_rotation(
        proposal, old_receipt=old_receipt, retained_old_floor=retained_old_floor,
        old_anchor=old_anchor, old_key=old_key, new_key=new_key,
        expected_new_witness_id=expected_new_witness_id,
        pinned_previous_key_epoch=pinned_previous_key_epoch,
    )
    next_anchor = _parse_anchor(replacement_anchor)
    if (next_anchor["ledger_id"] != p["a10_ledger_id"]
            or next_anchor["sequence"] <= p["old_a10_sequence"]):
        raise A12Refused("A12_RECOVERY_A10_ROLLBACK_OR_WRONG_LEDGER")
    try:
        signed = _parse_signed(replacement_receipt, new_key)
        compare_witness_receipt(
            replacement_receipt, replacement_anchor,
            key=new_key, expected_witness_id=expected_new_witness_id,
            trusted_floor_receipt=replacement_receipt,
        )
    except (A11Refused, A10Refused) as exc:
        raise A12Refused("A12_REPLACEMENT_RECEIPT_NOT_VALID") from exc
    if (signed["witness_sequence"] != 1
            or signed["previous_receipt_sha256"] != "0" * 64):
        raise A12Refused("A12_REPLACEMENT_NOT_FRESH_GENESIS")
    return RecoveryReview(
        hashlib.sha256(proposal).hexdigest(),
        p["new_key_epoch"], p["old_a10_sequence"],
        next_anchor["sequence"], expected_new_witness_id,
    )


__all__ = [
    "A12Refused", "RotationProposal", "RecoveryReview", "MediaLossReview",
    "block_lost_media", "propose_key_rotation", "verify_key_rotation",
    "verify_replacement_witness",
]
