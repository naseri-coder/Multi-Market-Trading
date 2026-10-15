"""Stage21D: verify RFC3161 TSA signed precommitment over exact Brooks plan.

No issuer independence claims; a pinned trust root might be operator-generated.
Uses OS OpenSSL to verify a real PKCS#7 timestamp signature and the message
imprint. Does not obtain tokens, open sockets, schedule, run a strategy or
authorize PAPER/Production. Tests create a local TEST CA, not genuine evidence.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .brooks_prospective_forward_custody_stage21c_v1 import (
    _gate, _load_plan,
)

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_STAMP = re.compile(
    r"^Time stamp: ([A-Z][a-z]{2} +\d{1,2} \d\d:\d\d:\d\d \d{4} GMT)$",
    re.MULTILINE,
)


class Stage21WitnessRefused(ValueError):
    """Static refusal codes without echoing untrusted identity or file data."""


def _check_bytes(raw: bytes, sha: str, *, max_bytes: int, name: str) -> None:
    if (type(raw) is not bytes or not 1 <= len(raw) <= max_bytes
            or type(sha) is not str or not _SHA.fullmatch(sha)
            or hashlib.sha256(raw).hexdigest() != sha):
        raise Stage21WitnessRefused("ST21D_PINNED_" + name + "_REQUIRED")


def _canonical(data: object) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=True).encode("ascii")


def _openssl(command: list[str], *, working_directory: Path) -> str:
    try:
        result = subprocess.run(
            command, cwd=working_directory,
            env={"PATH": "/usr/bin:/bin", "HOME": str(working_directory)},
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, check=False, timeout=12,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Stage21WitnessRefused("ST21D_OPENSSL_UNAVAILABLE") from exc
    if result.returncode != 0 or len(result.stdout) > 32768:
        raise Stage21WitnessRefused("ST21D_RFC3161_CRYPTOGRAPHIC_VERIFICATION_FAILED")
    try:
        return result.stdout.decode("ascii")
    except UnicodeError as exc:
        raise Stage21WitnessRefused("ST21D_INVALID_OPENSSL_OUTPUT") from exc


def verify_brooks_rfc3161_precommitment(
    *, plan_bytes: bytes, plan_sha256: str,
    timestamp_response_der: bytes, timestamp_response_sha256: str,
    trusted_ca_pem: bytes, trusted_ca_sha256: str,
    tsa_signer_certificate_pem: bytes, tsa_signer_certificate_sha256: str,
    operator_ack: bool = False,
) -> dict:
    """Verify RFC3161 timestamp over the exact PRECOMMITTED raw plan.

    Trust anchors must be independently vetted and pinned OUTSIDE this code.
    An issuer name printed inside an X.509 certificate proves no independence.
    """
    _gate(operator_ack)
    try:
        plan, start, _ = _load_plan(plan_bytes, plan_sha256)
    except ValueError as exc:
        raise Stage21WitnessRefused("ST21D_EXACT_STAGE21C_FROZEN_PLAN_REQUIRED") from exc
    _check_bytes(timestamp_response_der, timestamp_response_sha256,
                 max_bytes=32768, name="TIMESTAMP_RESPONSE")
    _check_bytes(trusted_ca_pem, trusted_ca_sha256,
                 max_bytes=16384, name="TRUST_ROOT")
    _check_bytes(tsa_signer_certificate_pem, tsa_signer_certificate_sha256,
                 max_bytes=16384, name="SIGNER_CERTIFICATE")
    if (b"-----BEGIN CERTIFICATE-----" not in trusted_ca_pem
            or b"-----BEGIN CERTIFICATE-----" not in tsa_signer_certificate_pem):
        raise Stage21WitnessRefused("ST21D_X509_CERTIFICATE_PEM_REQUIRED")
    executable = shutil.which("openssl")
    if executable is None:
        raise Stage21WitnessRefused("ST21D_OPENSSL_UNAVAILABLE")
    if not Path(executable).is_absolute():
        raise Stage21WitnessRefused("ST21D_OPENSSL_ABSOLUTE_BINARY_REQUIRED")
    with tempfile.TemporaryDirectory(prefix="mmt-stage21d-tsa-") as directory:
        folder = Path(directory)
        def write(name: str, raw: bytes) -> Path:
            p = folder / name
            fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
            return p
        plan_file = write("plan.json", plan_bytes)
        response_file = write("precommit.tsr", timestamp_response_der)
        root_file = write("approved-root.pem", trusted_ca_pem)
        signer_file = write("approved-signer.pem", tsa_signer_certificate_pem)
        # OpenSSL ts -verify verifies the RFC3161 message imprint from the
        # supplied plan and the TSA signer certificate chain/EKU.
        _openssl([
            executable, "ts", "-verify", "-data", str(plan_file),
            "-in", str(response_file), "-CAfile", str(root_file),
            "-untrusted", str(signer_file),
        ], working_directory=folder)
        rendering = _openssl([
            executable, "ts", "-reply", "-in", str(response_file), "-text",
        ], working_directory=folder)
    stamp_match = _STAMP.search(rendering)
    if stamp_match is None or len(_STAMP.findall(rendering)) != 1:
        raise Stage21WitnessRefused("ST21D_UNPARSEABLE_VERIFIED_TSA_TIME")
    try:
        time_signed = datetime.strptime(
            stamp_match.group(1), "%b %d %H:%M:%S %Y GMT",
        ).replace(tzinfo=UTC)
        local_created = datetime.strptime(
            plan.operator_created_utc, "%Y-%m-%dT%H:%M:%SZ",
        ).replace(tzinfo=UTC)
    except ValueError as exc:
        raise Stage21WitnessRefused("ST21D_TSA_DATE_PARSING_FAILED") from exc
    # The provider's signed UTC time must be in the short, predeclared
    # registration interval; this does not independently attest operator intent.
    if (not local_created <= time_signed <= local_created + timedelta(hours=1)
            or time_signed > start - timedelta(days=1)):
        raise Stage21WitnessRefused("ST21D_TIMESTAMP_NOT_A_PROSPECTIVE_PRECOMMIT")
    receipt = {
        "protocol": "STAGE21D_BROOKS_RFC3161_TIMESTAMP_VERIFICATION_V1",
        "plan_sha256": plan_sha256,
        "timestamp_response_sha256": timestamp_response_sha256,
        "trusted_root_sha256": trusted_ca_sha256,
        "tsa_signer_certificate_sha256": tsa_signer_certificate_sha256,
        "signed_timestamp_utc": time_signed.isoformat(),
        "study_start_utc": plan.study_start_utc,
        "cryptographic_tsa_signature_and_imprint_valid": True,
        "signer_chain_matched_operator_pinned_ca": True,
        "independent_tsa_provider_assessed": False,
        "independent_custody_policy_approved": False,
        "provider_market_data_signed": False,
        "true_prospective_oos_run": False,
        "brooks_live_fill_parity_verified": False,
        "account_specific_futures_economics_verified": False,
        "paper_mode_authorized": False,
        "live_trading_authorized": False,
        "production_modified": False,
        "verdict": "RFC3161_CRYPTO_VALID_OPERATOR_TRUST_ANCHOR_NOT_INDEPENDENTLY_APPROVED",
    }
    receipt["receipt_sha256"] = hashlib.sha256(_canonical(receipt)).hexdigest()
    return receipt


__all__ = ["Stage21WitnessRefused", "verify_brooks_rfc3161_precommitment"]
