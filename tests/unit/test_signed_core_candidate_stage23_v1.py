"""Stage23 dual-issuer source candidate acceptance; never source execution."""
from __future__ import annotations

import base64
import hashlib
import json
import os

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from naseri_markets.a24_publisher_admission import canonical
from naseri_markets.core_api_v1 import content_digest
from naseri_markets.signed_core_candidate_stage23_v1 import (
    SignedCandidateRefused, SignedCandidateWitness,
    _PUB_DOMAIN, _OP_DOMAIN,
)
from test_secure_plugin_runtime_v1 import CORE, IMAGE, SOURCE, event

TENANT = "tenant_alpha"
PUB = "community.vendor"
KEY_ID = "pub_key_one"
NOW = 1000


@pytest.fixture(autouse=True)
def nonproduction(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def key_bytes(private):
    return private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def sha(value):
    return hashlib.sha256(value).hexdigest()


@pytest.fixture
def trusted(tmp_path):
    publisher = Ed25519PrivateKey.generate()
    operator = Ed25519PrivateKey.generate()
    pub = key_bytes(publisher)
    op = key_bytes(operator)
    folder = tmp_path / "candidate"
    folder.mkdir(mode=0o700)
    p = folder / "witness.sqlite"
    witness = SignedCandidateWitness(
        p, publisher_public_key=pub, publisher_key_sha256=sha(pub),
        operator_public_key=op, operator_key_sha256=sha(op),
        operator_ack=True)
    yield witness, publisher, operator, p
    witness.close()


def signed(trusted, *, pub_signer=None, op_signer=None, **overrides):
    _, publisher, operator, _path = trusted
    c = {
        "schema": 1,
        "kind": "public_generic_source_candidate",
        "visibility": "public",
        "tenant_id": TENANT,
        "binding_id": event().binding.binding_id,
        "core_id": CORE.manifest.core_id,
        "core_version": CORE.manifest.core_version,
        "publisher": PUB,
        "publisher_key_id": KEY_ID,
        "manifest_sha256": content_digest(CORE.manifest),
        "binding_sha256": content_digest(event().binding),
        "source_sha256": sha(SOURCE),
        "image": IMAGE,
        "sequence": 1,
        "issued_at": NOW - 30,
        "expires_at": NOW + 1000,
        "capabilities": ["offline_core_decision_only"],
        "execution_mode": "untrusted_gvisor_only_pending_proof",
    }
    c.update(overrides)
    ps = base64.b64encode((pub_signer or publisher).sign(
        _PUB_DOMAIN + canonical(c))).decode("ascii")
    sig = base64.b64encode((op_signer or operator).sign(
        _OP_DOMAIN + canonical({
            "claim": c, "publisher_signature_b64": ps}))).decode("ascii")
    return canonical({
        "claim": c, "publisher_signature_b64": ps,
        "operator_signature_b64": sig,
    })


def admit(trusted, payload, **opts):
    witness, _pub, _op, _path = trusted
    args = dict(source=SOURCE, manifest=CORE.manifest, binding=event().binding,
                tenant_id=TENANT, publisher=PUB,
                publisher_key_id=KEY_ID, image=IMAGE, now=NOW,
                operator_ack=True)
    args.update(opts)
    return witness.admit(payload, **args)


def test_two_real_distinct_ed25519_signatures_pin_executable_candidate(trusted):
    payload = signed(trusted)
    receipt = admit(trusted, payload)
    assert receipt.state == "SIGNED_EXECUTABLE_CANDIDATE_REVIEWED_NO_INSTALL"
    assert receipt.source_sha256 == sha(SOURCE)
    assert not receipt.executable_installed
    assert not receipt.executable_run_authorized
    assert not receipt.public_marketplace_authorized
    assert not receipt.trading_authorized
    witness = trusted[0]
    assert witness.current(
        payload, source=SOURCE, manifest=CORE.manifest,
        binding=event().binding, tenant_id=TENANT, publisher=PUB,
        publisher_key_id=KEY_ID, image=IMAGE, now=NOW) == receipt
    with pytest.raises(SignedCandidateRefused, match="REVOKED_OR_ROLLBACK"):
        admit(trusted, payload)


@pytest.mark.parametrize("change", [
    {"visibility": "private"}, {"kind": "private_nyfr_core"},
    {"capabilities": ["live_trading"]},
    {"execution_mode": "run_python_in_host"},
    {"source_sha256": "0" * 64},
    {"manifest_sha256": "0" * 64},
    {"binding_sha256": "0" * 64},
    {"tenant_id": "tenant_beta"},
    {"image": "python:3.12"},
    {"sequence": 0},
    {"schema": True},
    {"issued_at": 0},
    {"expires_at": 1000000},
    {"binding_id": "ny_first_reversal"},
    {"publisher_key_id": "NYFR"},
])
def test_bad_signed_scope_or_identity_does_not_admit(trusted, change):
    with pytest.raises(SignedCandidateRefused):
        admit(trusted, signed(trusted, **change))


def test_tampered_source_wrong_signer_wrong_tenant_and_image_rejected(trusted):
    payload = signed(trusted)
    with pytest.raises(SignedCandidateRefused, match="CANDIDATE_BINDING"):
        admit(trusted, payload, source=b"unexpected python")
    with pytest.raises(SignedCandidateRefused, match="CANDIDATE_BINDING"):
        admit(trusted, payload, tenant_id="tenant_beta")
    with pytest.raises(SignedCandidateRefused, match="CANDIDATE_BINDING"):
        admit(trusted, payload, image=IMAGE.replace("a" * 64, "b" * 64))
    with pytest.raises(SignedCandidateRefused, match="INVALID_DUAL_ISSUER"):
        admit(trusted, signed(trusted, pub_signer=Ed25519PrivateKey.generate()))
    with pytest.raises(SignedCandidateRefused, match="INVALID_DUAL_ISSUER"):
        admit(trusted, signed(trusted, op_signer=Ed25519PrivateKey.generate()))


def test_canonical_unknown_duplicate_and_hidden_fields_refused(trusted):
    payload = signed(trusted)
    with pytest.raises(SignedCandidateRefused, match="CANONICAL"):
        admit(trusted, json.dumps(json.loads(payload), indent=2).encode())
    with pytest.raises(SignedCandidateRefused, match="DUPLICATE"):
        admit(trusted, payload.replace(b'{"claim":', b'{"claim":{},"claim":', 1))
    with pytest.raises(SignedCandidateRefused):
        admit(trusted, payload + b'\x00')
    with pytest.raises(SignedCandidateRefused, match="UNKNOWN_OR_MISSING"):
        admit(trusted, signed(trusted, api_key="secret"))


def test_monotonic_sequences_persist_and_revocation_is_permanent(trusted):
    witness, publisher, operator, path = trusted
    assert admit(trusted, signed(trusted)).sequence == 1
    with pytest.raises(SignedCandidateRefused, match="REVOKED_OR_ROLLBACK"):
        admit(trusted, signed(trusted))
    assert admit(trusted, signed(trusted, sequence=2)).sequence == 2
    witness.close()
    reopened = SignedCandidateWitness(
        path, publisher_public_key=key_bytes(publisher),
        publisher_key_sha256=sha(key_bytes(publisher)),
        operator_public_key=key_bytes(operator),
        operator_key_sha256=sha(key_bytes(operator)), operator_ack=True)
    try:
        with pytest.raises(SignedCandidateRefused, match="REVOKED_OR_ROLLBACK"):
            reopened.admit(
                signed(trusted, sequence=1), source=SOURCE,
                manifest=CORE.manifest, binding=event().binding,
                tenant_id=TENANT, publisher=PUB, publisher_key_id=KEY_ID,
                image=IMAGE, now=NOW, operator_ack=True)
        reopened.revoke(TENANT, event().binding.binding_id, operator_ack=True)
        with pytest.raises(SignedCandidateRefused, match="REVOKED_OR_ROLLBACK"):
            reopened.admit(
                signed(trusted, sequence=3), source=SOURCE,
                manifest=CORE.manifest, binding=event().binding,
                tenant_id=TENANT, publisher=PUB, publisher_key_id=KEY_ID,
                image=IMAGE, now=NOW, operator_ack=True)
    finally:
        reopened.close()


def test_owner_private_trust_and_explicit_nonproduction_required(tmp_path, monkeypatch):
    publisher, operator = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
    pub, op = key_bytes(publisher), key_bytes(operator)
    parent = tmp_path / "private"
    parent.mkdir(mode=0o700)
    args = dict(publisher_public_key=pub, publisher_key_sha256=sha(pub),
                operator_public_key=op, operator_key_sha256=sha(op),
                operator_ack=True)
    with pytest.raises(SignedCandidateRefused, match="TWO_DISTINCT"):
        SignedCandidateWitness(parent / "equal.db", publisher_public_key=pub,
                               publisher_key_sha256=sha(pub),
                               operator_public_key=pub, operator_key_sha256=sha(pub),
                               operator_ack=True)
    with pytest.raises(SignedCandidateRefused, match="INDEPENDENT_ED25519"):
        SignedCandidateWitness(parent / "bad.db", **{
            **args, "operator_key_sha256": "0" * 64})
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(SignedCandidateRefused, match="NONPRODUCTION"):
        SignedCandidateWitness(parent / "production.db", **args)
    assert not (parent / "production.db").exists()
    monkeypatch.delenv("MMT_PRODUCTION")
    folder = tmp_path / "public"
    folder.mkdir(mode=0o755)
    with pytest.raises(SignedCandidateRefused, match="OWNER_PRIVATE"):
        SignedCandidateWitness(folder / "public.db", **args)


def test_reopen_with_different_key_pair_does_not_reanchor_issuer(trusted):
    witness, _publisher, operator, path = trusted
    impostor = Ed25519PrivateKey.generate()
    witness.close()
    with pytest.raises(SignedCandidateRefused, match="ISSUER_KEYS_CHANGED_ON_REOPEN"):
        SignedCandidateWitness(
            path, publisher_public_key=key_bytes(impostor),
            publisher_key_sha256=sha(key_bytes(impostor)),
            operator_public_key=key_bytes(operator),
            operator_key_sha256=sha(key_bytes(operator)), operator_ack=True)


def test_signed_source_upgrade_same_binding_denied_even_with_valid_signatures(trusted):
    witness, _pub, _op, _path = trusted
    original = signed(trusted)
    admit(trusted, original)
    with pytest.raises(SignedCandidateRefused, match="SOURCE_CHANGE_REQUIRES_NEW_BINDING"):
        admit(trusted, signed(trusted, sequence=2, source_sha256=sha(b"other source")),
              source=b"other source")
    assert witness.current(
        original, source=SOURCE, manifest=CORE.manifest,
        binding=event().binding, tenant_id=TENANT, publisher=PUB,
        publisher_key_id=KEY_ID, image=IMAGE, now=NOW).sequence == 1
