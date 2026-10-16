"""MMT-R23: offline recovery and preflight of the ONLY canonical FreeTSA witness.

Portable to Python 3.11+ / Android Termux. This module never uses a
network connection, talks to a broker, runs PAPER, schedules work or modifies
the signed plan. The optional one-shot market fetch is in Stage21G, separately
guarded by a human-invoked CLI command and exact future-window gate.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .brooks_forward_source_custody_stage21g_v1 import (
    _EXPECTED_EVIDENCE,
    _read_original_evidence,
)
from .brooks_prospective_forward_custody_stage21c_v1 import _gate, _load_plan
from .brooks_rfc3161_precommitment_stage21d_v1 import (
    verify_brooks_rfc3161_precommitment,
)

_ORIGINAL_ZIP_SHA256 = "7e05a160c1f4dc0740ca18604456924df81e8254a3455dab76643f9106809868"
_ORIGINAL_ZIP_SIZE_LIMIT = 131072
_REQUIRED_FILES = frozenset(_EXPECTED_EVIDENCE)
_OPTIONAL_PINNED_FILES = {
    "external-rfc3161-verification-receipt.json":
        "39e17ba24739a02f7e02b4511ddf64357340a9578a9b5491aa85ae0fff653c45",
    "locked-unverified-economic-assumptions.json":
        "0512df973f0c3098d512d4606f4530f1d2c514618400eea2082ad5a37c5b32f5",
    "operator-admission-audit.json":
        "11f9a4ad2211d99503c21d02a3d2bbd13599885905ad433d0a4353c3c959a830",
    "plan-rfc3161-request.tsq":
        "e2319952ed7a3c7d827cf3c3c77bdfc6ef6757cb7d2dc8f546d3dee3c52970e7",
}
_ALL_PINS = {**_EXPECTED_EVIDENCE, **_OPTIONAL_PINNED_FILES}
_EXPECTED_NAMES = frozenset(_ALL_PINS)
_SHA_MANIFEST_NAME = "R23-original-artifact-manifest.json"
_MAX_ITEM_SIZE = 16_384


class R23ReadinessRefused(ValueError):
    """No untrusted path, data, exchange response, or secret in refusal codes."""


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical(data: dict) -> bytes:
    return (json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
            + "\n").encode("ascii")


def _research_only_ack(operator_ack: bool) -> None:
    _gate(operator_ack)
    if os.environ.get("MMT_PRODUCTION") == "1":
        raise R23ReadinessRefused("R23_PRODUCTION_ENVIRONMENT_REFUSED")


def verify_exact_original_rfc3161_zip(original_zip: Path) -> dict[str, bytes]:
    """Reject all ZIP substitution, symlinks, extra files, bombs and CRC faults."""
    if (not isinstance(original_zip, Path) or not original_zip.is_absolute()
            or original_zip.is_symlink() or not original_zip.is_file()):
        raise R23ReadinessRefused("R23_ABSOLUTE_NON_SYMLINK_ORIGINAL_ZIP_REQUIRED")
    with original_zip.open("rb") as stream:
        raw = stream.read(_ORIGINAL_ZIP_SIZE_LIMIT + 1)
    if not 100 <= len(raw) <= _ORIGINAL_ZIP_SIZE_LIMIT or _sha(raw) != _ORIGINAL_ZIP_SHA256:
        raise R23ReadinessRefused("R23_ORIGINAL_EXTERNAL_WITNESS_ZIP_SHA_MISMATCH")
    result: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(original_zip, "r") as archive:
            entries = archive.infolist()
            if (len(entries) != len(_EXPECTED_NAMES)
                    or frozenset(f.filename for f in entries) != _EXPECTED_NAMES):
                raise R23ReadinessRefused("R23_EXACT_ORIGINAL_ZIP_MEMBER_SET_REQUIRED")
            for item in entries:
                mode = (item.external_attr >> 16) & 0o170000
                if (item.is_dir() or mode == stat.S_IFLNK
                        or item.flag_bits & 0x1
                        or item.file_size < 1 or item.file_size > _MAX_ITEM_SIZE
                        or "/" in item.filename or "\\" in item.filename
                        or item.filename.startswith(".")
                        or item.filename not in _ALL_PINS):
                    raise R23ReadinessRefused("R23_UNSAFE_OR_OVERSIZED_ZIP_MEMBER")
                data = archive.read(item, pwd=None)
                if _sha(data) != _ALL_PINS[item.filename]:
                    raise R23ReadinessRefused("R23_PINNED_ORIGINAL_ZIP_MEMBER_MISMATCH")
                result[item.filename] = data
    except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as exc:
        if isinstance(exc, R23ReadinessRefused):
            raise
        raise R23ReadinessRefused("R23_MALFORMED_ORIGINAL_WITNESS_ZIP") from exc
    return result


def _original_signature_and_source(
    original_files: dict[str, bytes], *, operator_ack: bool,
) -> dict:
    _research_only_ack(operator_ack)
    for name in _REQUIRED_FILES:
        if name not in original_files or _sha(original_files[name]) != _ALL_PINS[name]:
            raise R23ReadinessRefused("R23_CANONICAL_WITNESS_FILE_PIN_MISMATCH")
    plan = original_files["exact-frozen-brooks-plan.json"]
    _load_plan(plan, _EXPECTED_EVIDENCE["exact-frozen-brooks-plan.json"])
    receipt = verify_brooks_rfc3161_precommitment(
        plan_bytes=plan,
        plan_sha256=_EXPECTED_EVIDENCE["exact-frozen-brooks-plan.json"],
        timestamp_response_der=original_files["original-external-timestamp-response.tsr"],
        timestamp_response_sha256=_EXPECTED_EVIDENCE[
            "original-external-timestamp-response.tsr"
        ],
        trusted_ca_pem=original_files["tsa-root-public.pem"],
        trusted_ca_sha256=_EXPECTED_EVIDENCE["tsa-root-public.pem"],
        tsa_signer_certificate_pem=original_files["tsa-signer-public.pem"],
        tsa_signer_certificate_sha256=_EXPECTED_EVIDENCE[
            "tsa-signer-public.pem"
        ],
        operator_ack=True,
    )
    if not (receipt["cryptographic_tsa_signature_and_imprint_valid"] is True
            and receipt["independent_tsa_provider_assessed"] is False
            and receipt["paper_mode_authorized"] is False):
        raise R23ReadinessRefused("R23_UNTRUSTED_TIMESTAMP_ATTESTATION_OR_SCOPE")
    return receipt


def stage23_prepare_witness_from_original_zip(
    *, original_zip: Path, destination: Path, operator_ack: bool = False,
) -> dict:
    """Verify cryptography BEFORE creating destination; preserve original bytes.

    Original ZIP is public certificate evidence only, never an account secret.
    Keep output inside Termux $HOME (not Android shared Downloads).
    """
    _research_only_ack(operator_ack)
    if (not isinstance(destination, Path) or not destination.is_absolute()
            or destination.is_symlink() or destination.exists()
            or not destination.parent.is_dir()
            or destination.parent.is_symlink()):
        raise R23ReadinessRefused("R23_FRESH_PRIVATE_ABSOLUTE_OUTPUT_REQUIRED")
    originals = verify_exact_original_rfc3161_zip(original_zip)
    witness = _original_signature_and_source(originals, operator_ack=True)
    destination.mkdir(mode=0o700)
    try:
        for name in sorted(_REQUIRED_FILES):
            path = destination / name
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(originals[name])
                stream.flush()
                os.fsync(stream.fileno())
        manifest = {
            "protocol": "MMT_R23_ORIGINAL_SIGNED_WITNESS_PREPARATION_V1",
            "source_original_zip_sha256": _ORIGINAL_ZIP_SHA256,
            "stage21g_evidence_sha256": dict(sorted(_EXPECTED_EVIDENCE.items())),
            "canonical_plan_sha256": _EXPECTED_EVIDENCE[
                "exact-frozen-brooks-plan.json"
            ],
            "externally_signed_timestamp_utc": witness["signed_timestamp_utc"],
            "independent_tsa_accreditation_approved": False,
            "binance_data_source_independently_signed": False,
            "connected_paper_active": False,
            "live_order_authorized": False,
            "production_modified": False,
        }
        fd = os.open(
            destination / _SHA_MANIFEST_NAME,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600,
        )
        with os.fdopen(fd, "wb") as stream:
            stream.write(_canonical(manifest))
            stream.flush()
            os.fsync(stream.fileno())
        return manifest
    except Exception:
        # Only the exclusive newly created destination is cleaned up.
        shutil.rmtree(destination)
        raise


def stage23_offline_witness_preflight(
    *, evidence_directory: Path, at_utc: datetime,
    operator_ack: bool = False,
) -> dict:
    """Genuine OpenSSL validation, no network; report future first-window gate."""
    _research_only_ack(operator_ack)
    evidence = _read_original_evidence(evidence_directory)
    receipt = _original_signature_and_source(evidence, operator_ack=True)
    plan, start, end = _load_plan(
        evidence["exact-frozen-brooks-plan.json"],
        _EXPECTED_EVIDENCE["exact-frozen-brooks-plan.json"],
    )
    if (type(at_utc) is not datetime or at_utc.tzinfo is None
            or at_utc.utcoffset() != timedelta(0)):
        raise R23ReadinessRefused("R23_UTC_AWARE_CLOCK_REQUIRED")
    now = at_utc.astimezone(UTC)
    first_ready = start + timedelta(minutes=15, seconds=5)
    first_expires = start + timedelta(minutes=75)
    if now < first_ready:
        status = "AWAITING_FIRST_CLOSED_CANDLE"
    elif now <= first_expires:
        status = "FIRST_SINGLE_BAR_CAPTURE_TIME_OPEN_MANUAL_ONLY"
    else:
        status = "FIRST_SINGLE_BAR_WINDOW_MISSED_DO_NOT_BACKDATE"
    return {
        "protocol": "MMT_R23_OFFLINE_TERMUX_READINESS_V1",
        "canonical_frozen_plan_sha256": _EXPECTED_EVIDENCE[
            "exact-frozen-brooks-plan.json"
        ],
        "actual_external_rfc3161_signature_verified": True,
        "externally_signed_timestamp_utc": receipt["signed_timestamp_utc"],
        "study_start_utc": plan.study_start_utc,
        "study_end_utc": plan.study_end_utc,
        "now_local_utc_unattested": now.isoformat(),
        "first_bar_earliest_manual_capture_utc": first_ready.isoformat(),
        "first_bar_latest_manual_receipt_utc": first_expires.isoformat(),
        "first_single_bar_window_status": status,
        "source_original_verified": False,
        "independent_receiver_clock_verified": False,
        "externally_accredited_tsa_policy_approved": False,
        "future_market_candles_received": False,
        "paper_mode_active": False,
        "live_orders_authorized": False,
        "production_modified": False,
    }


__all__ = [
    "R23ReadinessRefused",
    "verify_exact_original_rfc3161_zip",
    "stage23_prepare_witness_from_original_zip",
    "stage23_offline_witness_preflight",
]
