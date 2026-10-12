"""Stage32 offline host preparation: signed claims never become host proof."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import time

import pytest

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from naseri_markets.a24_publisher_admission import canonical
from naseri_markets.disposable_host_preflight_stage32_v1 import (
    HostPreparationDossier, Stage32Refused, _DOMAIN,
    review_proposed_host_policy, verify_local_test_certificate_pair,
)
from test_tls_boundary_stage31_v1 import (
    HOSTNAME, tls_material,  # noqa: F401
)


@pytest.fixture(autouse=True)
def research_only(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


@pytest.fixture
def fixture_and_policy(tls_material):  # noqa: F811
    cert, key, _pem, digest = tls_material
    timestamp = int(time.time())
    fixture = verify_local_test_certificate_pair(
        certificate_path=cert, private_key_path=key,
        expected_hostname=HOSTNAME, expected_certificate_sha256=digest,
        now=timestamp, operator_ack=True)
    raw = {
        "schema": 1, "environment": "isolated_disposable_nonproduction",
        "authority": HOSTNAME, "ingress_bind": "127.0.0.1",
        "ingress_port": 443, "tls_minimum": "TLSv1.3",
        "accept_forwarded_headers": False, "public_ingress_enabled": False,
        "outbound_internet_enabled": False, "broker_credentials_present": False,
        "docker_socket_mounted": False,
        "untrusted_plugin_execution_enabled": False,
        "max_http_body_bytes": 132000,
    }
    review = review_proposed_host_policy(
        raw, expected_hostname=HOSTNAME, operator_ack=True)
    return (cert, key, digest, timestamp), raw, fixture, review


@pytest.fixture
def dossier(tmp_path):
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    signer = Ed25519PrivateKey.generate()
    public = signer.public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw)
    path = private / "stage32_evidence.sqlite"
    with HostPreparationDossier(
            path, reviewer_public_key=public,
            pinned_reviewer_public_key_sha256=hashlib.sha256(public).hexdigest(),
            operator_ack=True) as store:
        yield store, signer, path


def signed_review(signer, fixture, review, now, **changes):
    claim = {
        "version": 1, "kind": "disposable_host_preparation_only",
        "host_alias": "disposable_staging_one", "sequence": 1,
        "observed_at": now-15, "expires_at": now+600,
        "certificate_sha256": fixture.certificate_sha256,
        "proposed_policy_sha256": review.policy_sha256,
        "review_scope": "static_local_fixture_and_proposal",
        "actual_host_independently_verified": False,
        "internet_service_deployed": False,
        "untrusted_code_executed": False,
        "public_installer_authorized": False,
        "telegram_send_authorized": False,
        "broker_orders_authorized": False,
    }
    claim.update(changes)
    sig = base64.b64encode(signer.sign(_DOMAIN + canonical(claim))).decode()
    return canonical({"claim": claim, "reviewer_signature_b64": sig})


def test_valid_fixture_inspection_is_not_a_real_host_audit(fixture_and_policy):
    (_cert, _key, digest, _now), raw, fixture, proposed = fixture_and_policy
    assert fixture.certificate_sha256 == digest
    assert fixture.local_key_permissions_checked
    assert fixture.local_certificate_key_correspondence_checked
    assert not fixture.real_tls_server_checked
    assert not fixture.live_certificate_chain_verified
    assert not fixture.public_deployment_authorized
    assert proposed.authority == HOSTNAME
    assert proposed.policy_sha256 == hashlib.sha256(canonical(raw)).hexdigest()
    assert not proposed.host_firewall_independently_checked
    assert not proposed.real_reverse_proxy_config_verified
    assert not proposed.public_ingress_authorized


def test_private_key_symlink_weak_permissions_and_pins_rejected(
        fixture_and_policy, tmp_path):
    (cert, key, digest, now), _, _, _ = fixture_and_policy
    bad = key.parent / "private-copy.key"
    bad.symlink_to(key)
    with pytest.raises(Stage32Refused, match="NO_SYMLINKED"):
        verify_local_test_certificate_pair(
            certificate_path=cert, private_key_path=bad,
            expected_hostname=HOSTNAME,
            expected_certificate_sha256=digest, now=now, operator_ack=True)
    key.chmod(0o644)
    with pytest.raises(Stage32Refused, match="EXACT_OWNER_ONLY"):
        verify_local_test_certificate_pair(
            certificate_path=cert, private_key_path=key,
            expected_hostname=HOSTNAME,
            expected_certificate_sha256=digest, now=now, operator_ack=True)
    key.chmod(0o600)
    with pytest.raises(Stage32Refused, match="PIN_MISMATCH"):
        verify_local_test_certificate_pair(
            certificate_path=cert, private_key_path=key,
            expected_hostname=HOSTNAME,
            expected_certificate_sha256="0"*64, now=now, operator_ack=True)
    with pytest.raises(Stage32Refused):
        verify_local_test_certificate_pair(
            certificate_path=cert, private_key_path=key,
            expected_hostname="public.example.com",
            expected_certificate_sha256=digest, now=now, operator_ack=True)


def test_local_certificate_key_mismatch_is_fatal(fixture_and_policy, tmp_path):
    (cert, key, digest, now), *_ = fixture_and_policy
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    another = rsa.generate_private_key(public_exponent=65537,key_size=2048)
    otherkey = key.parent / "unrelated.key"
    otherkey.write_bytes(another.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()))
    otherkey.chmod(0o600)
    with pytest.raises(Stage32Refused, match="INVALID_PRIVATE_TEST_TLS"):
        verify_local_test_certificate_pair(
            certificate_path=cert, private_key_path=otherkey,
            expected_hostname=HOSTNAME,
            expected_certificate_sha256=digest, now=now, operator_ack=True)


@pytest.mark.parametrize("change", [
    {"ingress_bind": "0.0.0.0"},
    {"ingress_bind": "::"},
    {"ingress_port": 80},
    {"ingress_port": True},
    {"tls_minimum": "TLSv1.2"},
    {"accept_forwarded_headers": True},
    {"public_ingress_enabled": True},
    {"outbound_internet_enabled": True},
    {"broker_credentials_present": True},
    {"docker_socket_mounted": True},
    {"untrusted_plugin_execution_enabled": True},
    {"max_http_body_bytes": 5000000},
    {"max_http_body_bytes": True},
    {"environment": "production"},
    {"authority": "attacker.invalid"},
    {"extra": "backdoor"},
])
def test_unsafe_ingress_or_network_policy_refused(fixture_and_policy, change):
    _, raw, *_ = fixture_and_policy
    with pytest.raises(Stage32Refused, match="NOT_RESTRICTIVE"):
        review_proposed_host_policy(
            {**raw, **change}, expected_hostname=HOSTNAME,
            operator_ack=True)


def test_signed_review_is_append_only_and_never_certifies_real_host(
        fixture_and_policy, dossier):
    (_cert,_key,_digest,now), _proposal, fixture, policy = fixture_and_policy
    store, signer, _path = dossier
    packet = signed_review(signer,fixture,policy,now)
    receipt = store.record(
        packet, fixture=fixture, proposed_policy=policy,
        now=now, operator_ack=True)
    assert receipt.sequence == 1
    assert receipt.statement_sha256 == hashlib.sha256(packet).hexdigest()
    assert receipt.state == "SIGNED_LOCAL_HOST_PREPARATION_NOT_LIVE_ATTESTED"
    assert not receipt.actual_host_security_verified
    assert not receipt.actual_public_https_service_checked
    assert not receipt.public_port_opening_authorized
    assert not receipt.public_install_authorized
    assert not receipt.broker_orders_authorized
    assert store.summary("disposable_staging_one") == {
        "host_alias": "disposable_staging_one",
        "local_statements": 1, "latest_sequence": 1,
        "actual_host_audited": False,
        "internet_deployment_authorized": False,
        "broker_order_authorized": False,
    }
    with pytest.raises(Stage32Refused, match="SEQUENCE"):
        store.record(packet, fixture=fixture, proposed_policy=policy,
                     now=now,operator_ack=True)
    second = signed_review(signer,fixture,policy,now,sequence=2)
    assert store.record(
        second, fixture=fixture, proposed_policy=policy,
        now=now,operator_ack=True).sequence == 2
    with pytest.raises(sqlite3.IntegrityError, match="STAGE32_APPEND_ONLY"):
        store.db.execute(
            "UPDATE stage32_signed_preparation SET policy_sha256=?",
            ("0"*64,))
    with pytest.raises(sqlite3.IntegrityError, match="STAGE32_APPEND_ONLY"):
        store.db.execute("DELETE FROM stage32_signed_preparation")


@pytest.mark.parametrize("changes", [
    {"kind": "production_host_ready"},
    {"review_scope": "independent_real_host_test"},
    {"actual_host_independently_verified": True},
    {"internet_service_deployed": True},
    {"untrusted_code_executed": True},
    {"public_installer_authorized": True},
    {"telegram_send_authorized": True},
    {"broker_orders_authorized": True},
    {"certificate_sha256": "0"*64},
    {"proposed_policy_sha256": "0"*64},
    {"sequence": 0},
    {"sequence": True},
    {"expires_at": 2**63},
    {"host_alias": "wrong!"}
])
def test_claims_cannot_promote_signed_preparation_to_execution(
        fixture_and_policy,dossier,changes):
    (_,_,_,now),_,fixture,policy=fixture_and_policy
    store,signer,_=dossier
    signed=signed_review(signer,fixture,policy,now,**changes)
    with pytest.raises(Stage32Refused):
        store.record(signed,fixture=fixture,proposed_policy=policy,
                     now=now,operator_ack=True)
    assert store.summary("disposable_staging_one")["local_statements"]==0


def test_wrong_signer_tamper_reordered_json_and_unknown_key_refused(
        fixture_and_policy,dossier):
    (_,_,_,now),_,fixture,policy=fixture_and_policy
    store, signer,_=dossier
    foreign=Ed25519PrivateKey.generate()
    forged=signed_review(foreign,fixture,policy,now)
    with pytest.raises(Stage32Refused,match="UNTRUSTED"):
        store.record(forged,fixture=fixture,proposed_policy=policy,
                     now=now,operator_ack=True)
    good=signed_review(signer,fixture,policy,now)
    with pytest.raises(Stage32Refused,match="CANONICAL"):
        store.record(json.dumps(json.loads(good),indent=2).encode(),
                     fixture=fixture,proposed_policy=policy,
                     now=now,operator_ack=True)
    malformed = good.replace(b'{"claim":',b'{"claim":{},"claim":',1)
    with pytest.raises(Stage32Refused,match="DUPLICATE"):
        store.record(malformed,fixture=fixture,proposed_policy=policy,
                     now=now,operator_ack=True)
    assert store.summary("disposable_staging_one")["local_statements"] == 0


def test_key_anchor_mismatch_and_persistent_sequence_floor(
        fixture_and_policy,dossier):
    (_,_,_,now),_,fixture,policy=fixture_and_policy
    store,signer,path=dossier
    first=signed_review(signer,fixture,policy,now)
    store.record(first,fixture=fixture,proposed_policy=policy,
                 now=now,operator_ack=True)
    wrong=Ed25519PrivateKey.generate()
    pub=wrong.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
    with pytest.raises(Stage32Refused,match="ANCHOR_CHANGED"):
        HostPreparationDossier(
            path,reviewer_public_key=pub,
            pinned_reviewer_public_key_sha256=hashlib.sha256(pub).hexdigest(),
            operator_ack=True)
    other = signer.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
    with HostPreparationDossier(
        path,reviewer_public_key=other,
        pinned_reviewer_public_key_sha256=hashlib.sha256(other).hexdigest(),
        operator_ack=True,
    ) as reopened:
        with pytest.raises(Stage32Refused,match="SEQUENCE"):
            reopened.record(first,fixture=fixture,proposed_policy=policy,
                            now=now,operator_ack=True)
        next_one=signed_review(signer,fixture,policy,now,sequence=2)
        assert reopened.record(
            next_one,fixture=fixture,proposed_policy=policy,
            now=now,operator_ack=True).sequence==2


def test_no_operator_ack_or_production_cannot_open_or_record(
        fixture_and_policy, tmp_path, monkeypatch):
    (cert,key,digest,now),raw,*_ = fixture_and_policy
    monkeypatch.setenv("MMT_PRODUCTION","1")
    with pytest.raises(Stage32Refused,match="EXPLICIT_NONPRODUCTION"):
        verify_local_test_certificate_pair(
            certificate_path=cert,private_key_path=key,
            expected_hostname=HOSTNAME,
            expected_certificate_sha256=digest,now=now,operator_ack=True)
    with pytest.raises(Stage32Refused,match="EXPLICIT_NONPRODUCTION"):
        review_proposed_host_policy(
            raw,expected_hostname=HOSTNAME,operator_ack=True)
    dirname=tmp_path/"private"
    dirname.mkdir(mode=0o700)
    pub=Ed25519PrivateKey.generate().public_key().public_bytes(
        Encoding.Raw,PublicFormat.Raw)
    with pytest.raises(Stage32Refused,match="EXPLICIT_NONPRODUCTION"):
        HostPreparationDossier(
            dirname/"deny.sqlite",reviewer_public_key=pub,
            pinned_reviewer_public_key_sha256=hashlib.sha256(pub).hexdigest(),
            operator_ack=True)
    assert not (dirname/"deny.sqlite").exists()


def test_insecure_parent_or_symlinked_db_refused(tmp_path):
    dirname=tmp_path/"vault"
    dirname.mkdir(mode=0o755)
    signer=Ed25519PrivateKey.generate()
    pub=signer.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)
    kwargs=dict(
        reviewer_public_key=pub,
        pinned_reviewer_public_key_sha256=hashlib.sha256(pub).hexdigest(),
        operator_ack=True)
    with pytest.raises(Stage32Refused,match="OWNER_PRIVATE"):
        HostPreparationDossier(dirname/"db.sqlite",**kwargs)
    dirname.chmod(0o700)
    (dirname/"db.sqlite").symlink_to(tmp_path/"does-not-exist")
    with pytest.raises(Stage32Refused,match="PRIVATE_DOSSIER"):
        HostPreparationDossier(dirname/"db.sqlite",**kwargs)
