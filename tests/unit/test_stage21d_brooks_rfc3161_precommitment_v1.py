"""Actual RFC3161 OpenSSL signature/PKCS7 chain fixture with an UNTRUSTED test CA.

A self-generated signer does NOT count as an independently vetted TSA.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from naseri_markets.brooks_prospective_forward_custody_stage21c_v1 import (
    BrooksProspectivePlan, freeze_brooks_prospective_plan,
)
from naseri_markets.brooks_rfc3161_precommitment_stage21d_v1 import (
    Stage21WitnessRefused, verify_brooks_rfc3161_precommitment,
)
from naseri_markets.brooks_replay import LEGACY_MANIFEST_SHA256

pytestmark = pytest.mark.skipif(shutil.which("openssl") is None, reason="OpenSSL executable unavailable")


@pytest.fixture(autouse=True)
def research(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def check(*args, cwd):
    p = subprocess.run(
        ["openssl", *args], cwd=cwd, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=20, check=False,
    )
    assert p.returncode == 0, (args, p.stderr.decode()[:800])


@pytest.fixture(scope="module")
def tsa(tmp_path_factory):
    directory = tmp_path_factory.mktemp("rfc3161")
    def put(name, text):
        (directory/name).write_text(text)
    put("root.cnf", "[req]\ndistinguished_name=dn\nx509_extensions=root_ext\nprompt=no\n[dn]\nCN=Test Local Root\n[root_ext]\nbasicConstraints=critical,CA:TRUE\nkeyUsage=critical,keyCertSign,cRLSign\nsubjectKeyIdentifier=hash\n")
    put("signer.cnf", "[req]\ndistinguished_name=dn\nprompt=no\n[dn]\nCN=Test Local Signer\n")
    put("ext.cnf", "basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature\nextendedKeyUsage=critical,timeStamping\n")
    put("ts.cnf", "[tsa]\ndefault_tsa=tsa1\n[tsa1]\nserial=serial.txt\nsigner_cert=signer.pem\ncerts=root.pem\nsigner_key=signer.key\nsigner_digest=sha256\ndefault_policy=1.2.3.4.5\ndigests=sha256\naccuracy=secs:1\nordering=yes\ntsa_name=yes\ness_cert_id_chain=yes\n")
    put("serial.txt", "01\n")
    check("req", "-new", "-newkey", "rsa:2048", "-nodes", "-x509",
          "-days", "2", "-config", "root.cnf", "-keyout", "root.key",
          "-out", "root.pem", cwd=directory)
    check("req", "-new", "-newkey", "rsa:2048", "-nodes",
          "-config", "signer.cnf", "-keyout", "signer.key",
          "-out", "signer.csr", cwd=directory)
    check("x509", "-req", "-days", "2", "-in", "signer.csr",
          "-CA", "root.pem", "-CAkey", "root.key", "-CAcreateserial",
          "-extfile", "ext.cnf", "-out", "signer.pem", cwd=directory)
    return directory


def freeze_plan(now):
    created = now.replace(second=0, microsecond=0)
    start = (created + timedelta(days=2)).replace(minute=0)
    stop = start + timedelta(days=8)
    plan = BrooksProspectivePlan(
        protocol="STAGE21C_BROOKS_PROSPECTIVE_PRECOMMIT_PROTOCOL_V1",
        strategy_manifest_sha256=LEGACY_MANIFEST_SHA256,
        bridge_source_sha256="a"*64,
        economics_assumptions_sha256="b"*64,
        study_start_utc=iso(start), study_end_utc=iso(stop),
        operator_created_utc=iso(created),
    )
    return freeze_brooks_prospective_plan(
        plan, operator_recorded_at_utc=created + timedelta(minutes=1),
        operator_ack=True,
    )


def timestamp(directory, data):
    (directory/"precommit.json").write_bytes(data)
    check("ts", "-query", "-data", "precommit.json", "-sha256",
          "-cert", "-out", "request.tsq", cwd=directory)
    check("ts", "-reply", "-config", "ts.cnf", "-queryfile", "request.tsq",
          "-out", "response.tsr", cwd=directory)
    return (directory/"response.tsr").read_bytes()


def inputs(tsa):
    now = datetime.now(UTC)
    plan, digest = freeze_plan(now)
    answer = timestamp(tsa, plan)
    root = (tsa/"root.pem").read_bytes()
    signer = (tsa/"signer.pem").read_bytes()
    return dict(
        plan_bytes=plan, plan_sha256=digest,
        timestamp_response_der=answer,
        timestamp_response_sha256=hashlib.sha256(answer).hexdigest(),
        trusted_ca_pem=root, trusted_ca_sha256=hashlib.sha256(root).hexdigest(),
        tsa_signer_certificate_pem=signer,
        tsa_signer_certificate_sha256=hashlib.sha256(signer).hexdigest(),
        operator_ack=True,
    )


def test_genuine_crypto_tsa_signature_and_message_imprint_pass_without_independence_claim(tsa):
    kw = inputs(tsa)
    report = verify_brooks_rfc3161_precommitment(**kw)
    assert report["plan_sha256"] == kw["plan_sha256"]
    assert report["cryptographic_tsa_signature_and_imprint_valid"] is True
    assert report["signer_chain_matched_operator_pinned_ca"] is True
    assert report["independent_tsa_provider_assessed"] is False
    assert report["independent_custody_policy_approved"] is False
    assert report["true_prospective_oos_run"] is False
    assert report["paper_mode_authorized"] is False
    assert report["live_trading_authorized"] is False
    assert report["production_modified"] is False
    assert verify_brooks_rfc3161_precommitment(**kw) == report


def test_tampered_plan_content_cannot_reuse_original_signed_token(tsa):
    kw = inputs(tsa)
    p = json.loads(kw["plan_bytes"])
    p["economics_assumptions_sha256"] = "c"*64
    new = json.dumps(p, sort_keys=True, separators=(",", ":")).encode()
    kw["plan_bytes"] = new
    kw["plan_sha256"] = hashlib.sha256(new).hexdigest()
    with pytest.raises(Stage21WitnessRefused, match="CRYPTOGRAPHIC"):
        verify_brooks_rfc3161_precommitment(**kw)


def test_modified_token_or_wrong_pinned_ca_refused(tsa):
    kw = inputs(tsa)
    raw = bytearray(kw["timestamp_response_der"])
    raw[-12] ^= 0x01
    kw["timestamp_response_der"] = bytes(raw)
    kw["timestamp_response_sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(Stage21WitnessRefused, match="CRYPTOGRAPHIC"):
        verify_brooks_rfc3161_precommitment(**kw)
    kw = inputs(tsa)
    kw["trusted_ca_sha256"] = "0"*64
    with pytest.raises(Stage21WitnessRefused, match="TRUST_ROOT"):
        verify_brooks_rfc3161_precommitment(**kw)


def test_different_signer_ca_chain_refused_even_when_hashes_match(tsa, tmp_path):
    kw = inputs(tsa)
    other = tmp_path/"other.pem"
    check("req", "-new", "-newkey", "rsa:2048", "-nodes", "-x509",
          "-days", "2", "-subj", "/CN=Fake CA",
          "-keyout", str(tmp_path/"other.key"), "-out", str(other), cwd=tmp_path)
    kw["trusted_ca_pem"] = other.read_bytes()
    kw["trusted_ca_sha256"] = hashlib.sha256(other.read_bytes()).hexdigest()
    with pytest.raises(Stage21WitnessRefused, match="CRYPTOGRAPHIC"):
        verify_brooks_rfc3161_precommitment(**kw)


def test_timestamp_before_operator_claimed_creation_is_refused(tsa):
    kw = inputs(tsa)
    plan = json.loads(kw["plan_bytes"])
    tomorrow = datetime.now(UTC)+timedelta(days=1)
    later = tomorrow.replace(second=0, microsecond=0)
    start = (later+timedelta(days=2)).replace(minute=0)
    plan["operator_created_utc"] = iso(later)
    plan["study_start_utc"] = iso(start)
    plan["study_end_utc"] = iso(start+timedelta(days=8))
    new = json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
    # Even if freshly signed now, future-dated operator registration must fail.
    signed = timestamp(tsa, new)
    kw.update(plan_bytes=new, plan_sha256=hashlib.sha256(new).hexdigest(),
              timestamp_response_der=signed,
              timestamp_response_sha256=hashlib.sha256(signed).hexdigest())
    with pytest.raises(Stage21WitnessRefused, match="NOT_A_PROSPECTIVE"):
        verify_brooks_rfc3161_precommitment(**kw)


def test_production_and_missing_ack_refused_prior_to_openssl(tsa, monkeypatch):
    kw = inputs(tsa)
    kw["operator_ack"] = False
    with pytest.raises(ValueError, match="NONPRODUCTION"):
        verify_brooks_rfc3161_precommitment(**kw)
    kw["operator_ack"] = True
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(ValueError, match="NONPRODUCTION"):
        verify_brooks_rfc3161_precommitment(**kw)
