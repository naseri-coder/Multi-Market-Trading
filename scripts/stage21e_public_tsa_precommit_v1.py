#!/usr/bin/env python3
"""One-shot, opt-in research preregistration with the public RFC3161 TSA.

Only official FreeTSA HTTPS and public certificate URLs. Never an exchange,
Telegram, background monitor, broker or independent provider-policy approval.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import urllib.request
from datetime import UTC, datetime, timedelta

from naseri_markets.brooks_prospective_forward_custody_stage21c_v1 import (
    BrooksProspectivePlan, freeze_brooks_prospective_plan,
)
from naseri_markets.brooks_replay import LEGACY_MANIFEST_SHA256
from naseri_markets.brooks_rfc3161_precommitment_stage21d_v1 import (
    verify_brooks_rfc3161_precommitment,
)

_CERT_ORIGIN = "https://freetsa.org/files/"
_STAMP_URL = "https://freetsa.org/tsr"
_ROOT_SHA256 = "2151b61137ffa86bf664691ba67e7da0b19f98c758e3d228d5d8ebf27e044438"
_SIGNER_SHA256 = "8bfb0305bb64e2571ca507552ef3245cb1c2fee8728e0ff8689225081ea13467"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise ValueError("ST21E_NONCANONICAL_REDIRECT_REFUSED")


def _hash(x: bytes) -> str:
    return hashlib.sha256(x).hexdigest()


def _fetch_cert(opener: urllib.request.OpenerDirector, name: str, pinned: str) -> bytes:
    url = _CERT_ORIGIN + name
    request = urllib.request.Request(url, headers={"Accept-Encoding": "identity"})
    with opener.open(request, timeout=20) as response:
        if response.status != 200 or response.geturl() != url:
            raise ValueError("ST21E_CERTIFICATE_ENDPOINT_REFUSED")
        content = response.read(16385)
    if (not 100 < len(content) <= 16384
            or _hash(content) != pinned
            or b"-----BEGIN CERTIFICATE-----" not in content):
        raise ValueError("ST21E_INDEPENDENTLY_REVIEWED_PUBLIC_CERTIFICATE_PIN_MISMATCH")
    return content


def _put(directory: pathlib.Path, name: str, raw: bytes) -> pathlib.Path:
    p = directory / name
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())
    return p


def _iso(value: datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> None:
    if (os.environ.get("MMT_NONPRODUCTION") != "1"
            or os.environ.get("MMT_PRODUCTION") == "1"
            or os.environ.get("ST21E_EXPLICIT_ONE_SHOT_APPROVAL") != "1"):
        raise ValueError("ST21E_NO_LIVE_AND_EXPLICIT_ONE_SHOT_ACK_REQUIRED")
    root = pathlib.Path(os.environ["RUNNER_TEMP"]).resolve()
    folder = root / "stage21e-brooks-future-research-precommit"
    folder.mkdir(mode=0o700, exist_ok=False)
    opener = urllib.request.build_opener(_NoRedirect())
    # Only these two public certificates are accepted; digest pins originate
    # from the separately reviewed HTTPS discovery run 38835711245.
    ca = _fetch_cert(opener, "cacert.pem", _ROOT_SHA256)
    signer = _fetch_cert(opener, "tsa.crt", _SIGNER_SHA256)
    bridge_source = pathlib.Path(
        "naseri_markets/brooks_primary_source_funding_join_stage21b_v1.py"
    ).read_bytes()

    # This document is a FIXED research economic-assumption commitment,
    # explicitly NOT a user-specific signed fee tier or venue execution model.
    assumptions = {
        "schema_version": 1,
        "market": "binance_usdm", "symbol": "BTCUSDT",
        "experiment_kind": "NO_LIVE_ORDERS_NO_CONNECTED_PAPER",
        "assumptions_origin": "operator_unverified_research_only",
        "base_units_per_contract": "1", "price_tick": "0.1",
        "quantity_step": "0.001", "taker_fee_fraction": "0.0004",
        "worst_slippage_fraction": "0.0007",
        "maintenance_margin_fraction": "0.005",
        "historical_fee_tier_verified": False,
        "precise_settlement_mark_verified": False,
        "broker_fill_parity_verified": False,
    }
    economics = (json.dumps(assumptions, sort_keys=True, separators=(",", ":"))
                 + "\n").encode("ascii")
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    start = (now + timedelta(days=4)).replace(hour=0, minute=0)
    end = start + timedelta(days=14)
    proposed = BrooksProspectivePlan(
        protocol="STAGE21C_BROOKS_PROSPECTIVE_PRECOMMIT_PROTOCOL_V1",
        strategy_manifest_sha256=LEGACY_MANIFEST_SHA256,
        bridge_source_sha256=_hash(bridge_source),
        economics_assumptions_sha256=_hash(economics),
        study_start_utc=_iso(start),
        study_end_utc=_iso(end),
        operator_created_utc=_iso(now),
    )
    plan, digest = freeze_brooks_prospective_plan(
        proposed, operator_recorded_at_utc=datetime.now(UTC),
        operator_ack=True,
    )
    _put(folder, "exact-frozen-brooks-plan.json", plan)
    _put(folder, "locked-unverified-economic-assumptions.json", economics)
    _put(folder, "tsa-root-public.pem", ca)
    _put(folder, "tsa-signer-public.pem", signer)
    request_path = folder / "plan-rfc3161-request.tsq"
    query = subprocess.run(
        ["openssl", "ts", "-query", "-data",
         str(folder / "exact-frozen-brooks-plan.json"),
         "-sha256", "-no_nonce", "-cert", "-out", str(request_path)],
        check=False, capture_output=True, timeout=15,
    )
    if query.returncode != 0:
        raise ValueError("ST21E_COULD_NOT_BUILD_CANONICAL_TIMESTAMP_REQUEST")
    request_bytes = request_path.read_bytes()
    if not 10 <= len(request_bytes) <= 2048:
        raise ValueError("ST21E_TIMESTAMP_REQUEST_SIZE_INVALID")
    remote = urllib.request.Request(
        _STAMP_URL, data=request_bytes,
        headers={"Content-Type": "application/timestamp-query",
                 "Accept": "application/timestamp-reply",
                 "Accept-Encoding": "identity"},
        method="POST",
    )
    with opener.open(remote, timeout=30) as response:
        if response.status != 200 or response.geturl() != _STAMP_URL:
            raise ValueError("ST21E_UNEXPECTED_TIMESTAMP_AUTHORITY_RESPONSE")
        token = response.read(32769)
    if not 100 < len(token) <= 32768:
        raise ValueError("ST21E_INVALID_BOUNDED_TIMESTAMP_RESPONSE")
    _put(folder, "original-external-timestamp-response.tsr", token)
    receipt = verify_brooks_rfc3161_precommitment(
        plan_bytes=plan, plan_sha256=digest,
        timestamp_response_der=token,
        timestamp_response_sha256=_hash(token),
        trusted_ca_pem=ca, trusted_ca_sha256=_ROOT_SHA256,
        tsa_signer_certificate_pem=signer,
        tsa_signer_certificate_sha256=_SIGNER_SHA256,
        operator_ack=True,
    )
    assert receipt["cryptographic_tsa_signature_and_imprint_valid"] is True
    assert receipt["independent_tsa_provider_assessed"] is False
    assert receipt["true_prospective_oos_run"] is False
    assert receipt["paper_mode_authorized"] is False
    audit = {
        "experiment": "STAGE21E_SINGLE_EXTERNAL_RFC3161_PRECOMMIT_ONLY",
        "service_url": _STAMP_URL,
        "certificate_source": _CERT_ORIGIN,
        "trust_root_sha256": _ROOT_SHA256,
        "trust_signer_sha256": _SIGNER_SHA256,
        "exact_frozen_plan_sha256": digest,
        "exact_bridge_code_sha256": _hash(bridge_source),
        "operator_unverified_economics_sha256": _hash(economics),
        "original_rfc3161_query_sha256": _hash(request_bytes),
        "original_rfc3161_response_sha256": _hash(token),
        "verified_timestamp_utc": receipt["signed_timestamp_utc"],
        "study_start_utc": proposed.study_start_utc,
        "study_end_utc": proposed.study_end_utc,
        "tsa_signature_and_chain_verified": True,
        "independence_and_accreditation_audited": False,
        "independent_witness_custody_approved": False,
        "source_feed_authenticated": False,
        "forward_candles_collected": False,
        "actual_paper_started": False,
        "production_modified": False,
    }
    _put(folder, "external-rfc3161-verification-receipt.json",
         (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode())
    _put(folder, "operator-admission-audit.json",
         (json.dumps(audit, indent=2, sort_keys=True) + "\n").encode())
    print("ST21E_EXTERNAL_PUBLIC_TSA_CRYPTOGRAPHIC_PASS")
    print("ST21E_FROZEN_PLAN_SHA256=" + digest)
    print("ST21E_EXTERNAL_TSR_SHA256=" + _hash(token))
    print("ST21E_SIGNED_TIME=" + receipt["signed_timestamp_utc"])
    print("ST21E_STUDY_START=" + proposed.study_start_utc)
    print("ST21E_STUDY_END=" + proposed.study_end_utc)
    print("ST21E_OPERATOR_TRUST_POLICY_REVIEW_STILL_REQUIRED")
    print("ST21E_NO_FORWARD_CANDLES_OR_CONNECTED_PAPER")


if __name__ == "__main__":
    main()
