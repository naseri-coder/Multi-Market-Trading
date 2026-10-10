"""A12 signed owner grants, key lifecycle, certificate pins and A10 binding."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import secrets
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from naseri_markets.a12_trust import (
    DOMAIN, AdmissionRefused, OfflineAdmission, TrustStore,
    canonical, parse_grant, parse_policy,
)
from naseri_markets.contracts import Instrument, Market
from naseri_markets.plugin_manager import PluginManager
from naseri_markets.private_connector import ConnectorKeys, PrivatePaperConnector
from naseri_markets.private_protocol import ReplayFence, sign_packet, verify_packet
from naseri_markets.quotes import QuoteOrigin, QuoteTick

NOW = 1791549000
CA = b"CI_ONLY_TRUST_FIXTURE_CA_CERT_BYTES"
LEAF = b"CI_ONLY_TRUST_FIXTURE_DER_BYTES"
INSTALL = "fixture_install_42"
ENGINE = "private_example"
MANIFEST_HASH = "1" * 64


@pytest.fixture()
def material(tmp_path):
    issuer = Ed25519PrivateKey.generate()
    pub = issuer.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    store = TrustStore(tmp_path / "trust.db")
    return {"issuer": issuer, "public": pub, "store": store, "root": tmp_path}


def policy(material, *, generation=1, ca=CA, leaf=LEAF, issuer_id="issuer_k1",
           publisher_key=None, **overrides):
    data = {
        "schema_version": 1, "generation": generation,
        "engine_id": ENGINE, "engine_version": "1.0.0",
        "manifest_sha256": MANIFEST_HASH,
        "owner_dns": "private-owner.fixture",
        "ca_sha256": hashlib.sha256(ca).hexdigest(),
        "owner_cert_sha256": hashlib.sha256(leaf).hexdigest(),
        "issuer_key_id": issuer_id,
        "issuer_public_key_b64": base64.b64encode(
            publisher_key or material["public"]
        ).decode(),
    }
    data.update(overrides)
    return data


def approved_policy(store, doc):
    raw = canonical(doc)
    store.stage(raw, approved_sha256=hashlib.sha256(raw).hexdigest())
    store.promote(doc["engine_id"], generation=doc["generation"],
                  expected_active=doc["generation"] - 1)


def grant(material, policy_data, *, issued=NOW - 1, expiry=NOW + 60,
          signer=None, **overrides):
    data = {
        "schema_version": 1, "serial": secrets.token_hex(16),
        "generation": policy_data["generation"],
        "engine_id": policy_data["engine_id"],
        "engine_version": policy_data["engine_version"],
        "manifest_sha256": policy_data["manifest_sha256"],
        "owner_dns": policy_data["owner_dns"],
        "installation_id": INSTALL,
        "issuer_key_id": policy_data["issuer_key_id"],
        "issued_at": issued, "expires_at": expiry,
        "permissions": ["paper_analysis"],
    }
    data.update(overrides)
    signed = (signer or material["issuer"]).sign(DOMAIN + canonical(data))
    return canonical({
        "grant": data,
        "signature_b64": base64.b64encode(signed).decode(),
    })


def gate(material, doc, *, signed=None, ca=CA, leaf=LEAF):
    return OfflineAdmission(
        material["store"], engine_id=ENGINE, installation_id=INSTALL,
        signed_grant=signed or grant(material, doc),
        ca_pem=ca, owner_cert_der=leaf,
    )


def test_first_grant_admitted_and_persists_restart(material):
    store = material["store"]
    doc = policy(material)
    approved_policy(store, doc)
    snapshot = gate(material, doc).snapshot(now=NOW)
    assert snapshot.engine_id == ENGINE and snapshot.generation == 1
    assert snapshot.license_expires_at == NOW + 60
    store.close()
    reopened = TrustStore(material["root"] / "trust.db")
    assert reopened.active(ENGINE) == doc
    reopened.close()


def test_no_policy_is_fail_closed(material):
    doc = policy(material)
    with pytest.raises(AdmissionRefused, match="NO_ACTIVE_TRUST"):
        gate(material, doc).snapshot(now=NOW)


@pytest.mark.parametrize("change", [
    {"schema_version": True}, {"schema_version": 2}, {"generation": 0},
    {"generation": True}, {"owner_dns": "owner.example.com"},
    {"owner_dns": "../private-owner.fixture"},
    {"issuer_key_id": ".."}, {"engine_version": "latest"},
    {"manifest_sha256": "not-a-sha"}, {"extra": "provision secret"},
    {"issuer_public_key_b64": "%%%"},
])
def test_policy_parser_rejects_invalid_manifest(material, change):
    raw = canonical(policy(material, **change))
    with pytest.raises(AdmissionRefused):
        parse_policy(raw, approved_sha256=hashlib.sha256(raw).hexdigest())


def test_policy_cannot_approve_itself(material):
    doc = policy(material)
    raw = canonical(doc)
    with pytest.raises(AdmissionRefused, match="PIN_MISMATCH"):
        parse_policy(raw, approved_sha256="a" * 64)


def test_policy_duplicate_json_keys_rejected(material):
    raw = b'{"schema_version":1,"schema_version":1}'
    with pytest.raises(AdmissionRefused, match="INVALID_JSON"):
        parse_policy(raw, approved_sha256=hashlib.sha256(raw).hexdigest())


@pytest.mark.parametrize("override", [
    {"engine_id": "other_owner"}, {"owner_dns": "other-owner.fixture"},
    {"engine_version": "9.0.0"}, {"manifest_sha256": "2" * 64},
    {"installation_id": "another_install"}, {"generation": 2},
    {"issuer_key_id": "issuer_k2"},
])
def test_license_binding_rejects_other_owner_or_installation(material, override):
    p = policy(material)
    approved_policy(material["store"], p)
    signed = grant(material, p, **override)
    with pytest.raises(AdmissionRefused, match="SCOPE_MISMATCH|WRONG_INSTALLATION"):
        gate(material, p, signed=signed).snapshot(now=NOW)


@pytest.mark.parametrize("override", [
    {"permissions": ["live_trading"]}, {"permissions": ["paper_analysis", "orders"]},
    {"permissions": []}, {"schema_version": True}, {"issued_at": True},
    {"expires_at": NOW + 86401}, {"serial": "not-hex"},
])
def test_license_must_have_bounded_paper_scope(material, override):
    p = policy(material)
    approved_policy(material["store"], p)
    signed = grant(material, p, **override)
    with pytest.raises(AdmissionRefused):
        gate(material, p, signed=signed).snapshot(now=NOW)


def test_license_tamper_and_wrong_signer_rejected(material):
    p = policy(material)
    approved_policy(material["store"], p)
    good = grant(material, p)
    invalid = json.loads(good)
    invalid["grant"]["expires_at"] += 1
    with pytest.raises(AdmissionRefused, match="SIGNATURE_INVALID"):
        gate(material, p, signed=canonical(invalid)).snapshot(now=NOW)
    with pytest.raises(AdmissionRefused, match="SIGNATURE_INVALID"):
        gate(material, p, signed=grant(
            material, p, signer=Ed25519PrivateKey.generate(),
        )).snapshot(now=NOW)


@pytest.mark.parametrize("issued,expiry", [
    (NOW + 6, NOW + 60), (NOW - 120, NOW - 10),
])
def test_future_or_expired_license_denied(material, issued, expiry):
    p = policy(material)
    approved_policy(material["store"], p)
    with pytest.raises(AdmissionRefused, match="EXPIRED_OR_FUTURE"):
        gate(material, p, signed=grant(
            material, p, issued=issued, expiry=expiry,
        )).snapshot(now=NOW)


def test_certificate_ca_and_leaf_are_pinned(material):
    p = policy(material)
    approved_policy(material["store"], p)
    for ca, leaf in ((b"rotated_ca", LEAF), (CA, b"other_cert")):
        with pytest.raises(AdmissionRefused, match="CERT_PIN_MISMATCH"):
            gate(material, p, ca=ca, leaf=leaf).snapshot(now=NOW)


def test_staged_policy_not_trusted_until_cas_promoted(material):
    s = material["store"]
    old = policy(material)
    approved_policy(s, old)
    next_policy = policy(material, generation=2, leaf=b"new_leaf")
    blob = canonical(next_policy)
    s.stage(blob, approved_sha256=hashlib.sha256(blob).hexdigest())
    assert s.active(ENGINE) == old
    with pytest.raises(AdmissionRefused, match="STALE_CAS"):
        s.promote(ENGINE, generation=2, expected_active=0)
    s.promote(ENGINE, generation=2, expected_active=1)
    with pytest.raises(AdmissionRefused, match="CERT_PIN_MISMATCH"):
        gate(material, old).snapshot(now=NOW)
    with pytest.raises(AdmissionRefused, match="ROLLBACK"):
        s.stage(canonical(old), approved_sha256=hashlib.sha256(
            canonical(old)
        ).hexdigest())


def test_rotation_refuses_old_license_even_when_leaf_same(material):
    s = material["store"]
    old = policy(material)
    approved_policy(s, old)
    old_signed = grant(material, old)
    next_policy = policy(material, generation=2)
    blob = canonical(next_policy)
    s.stage(blob, approved_sha256=hashlib.sha256(blob).hexdigest())
    s.promote(ENGINE, generation=2, expected_active=1)
    with pytest.raises(AdmissionRefused, match="SCOPE_MISMATCH"):
        gate(material, next_policy, signed=old_signed).snapshot(now=NOW)
    assert gate(material, next_policy).snapshot(now=NOW).generation == 2


def test_revoked_policy_serial_or_issuer_fails_closed(material):
    p = policy(material)
    approved_policy(material["store"], p)
    signed = grant(material, p)
    serial = parse_grant(signed)[0]["serial"]
    material["store"].revoke_serial(serial)
    with pytest.raises(AdmissionRefused, match="SERIAL_REVOKED"):
        gate(material, p, signed=signed).snapshot(now=NOW)
    material["store"].revoke_issuer("issuer_k1")
    with pytest.raises(AdmissionRefused, match="ISSUER_REVOKED"):
        gate(material, p).snapshot(now=NOW)
    material["store"].revoke_policy(ENGINE, expected_generation=1)
    with pytest.raises(AdmissionRefused, match="NO_ACTIVE_TRUST"):
        gate(material, p).snapshot(now=NOW)


def test_revocation_and_fencing_persist(material):
    p = policy(material)
    approved_policy(material["store"], p)
    material["store"].revoke_issuer("issuer_k1")
    material["store"].revoke_policy(ENGINE, expected_generation=1)
    material["store"].close()
    re = TrustStore(material["root"] / "trust.db")
    with pytest.raises(AdmissionRefused, match="NO_ACTIVE_TRUST"):
        re.active(ENGINE)
    with pytest.raises(AdmissionRefused, match="ISSUER_REVOKED"):
        re.check_revocations("a" * 32, "issuer_k1")
    re.close()


def test_partial_and_oversized_grant_fail(material):
    for raw in (b"", b"{}", b"x" * 8193,
                b'{"grant":{}, "grant":{}, "signature_b64":"x"}'):
        with pytest.raises(AdmissionRefused):
            parse_grant(raw)


def test_store_rejects_symlink(material):
    raw = material["root"] / "link.db"
    raw.symlink_to(material["root"] / "trust.db")
    with pytest.raises(AdmissionRefused, match="UNSAFE_STORE"):
        TrustStore(raw)


def test_unknown_grant_serial_requires_valid_signature(material):
    p = policy(material)
    approved_policy(material["store"], p)
    signed = grant(material, p)
    envelope = json.loads(signed)
    envelope["grant"]["serial"] = "b" * 32
    with pytest.raises(AdmissionRefused, match="SIGNATURE_INVALID"):
        gate(material, p, signed=canonical(envelope)).snapshot(now=NOW)


def _connector_fixture(material, *, custom_exchange=None):
    root = material["root"]
    mgr = PluginManager(root / "plugins.db")
    desc = canonical({
        "schema_version": 1, "engine_id": ENGINE, "engine_version": "1.0.0",
        "publisher": "owner.fixture", "visibility": "private",
        "adapter": "external_contract", "abi_version": 1,
        "markets": ["index"], "permissions": ["paper_analysis"],
    })
    digest = hashlib.sha256(desc).hexdigest()
    row = mgr.register(desc, approved_sha256=digest)
    mgr.set_enabled(ENGINE, enabled=True, expected_revision=row.revision)
    p = policy(material, manifest_sha256=digest)
    approved_policy(material["store"], p)
    admission = gate(material, p)
    replay = ReplayFence(root / "replay.db")
    ck, ok = b"c" * 32, b"o" * 32

    async def exchange(packet):
        request = verify_packet(
            packet, key=ck, key_id="client_k1", direction="to_owner",
            engine_id=ENGINE, engine_version="1.0.0", now=NOW,
        )
        tick = request["payload"]["tick"]
        envelope = canonical({
            "abi_version": 1, "signal_id": "a12-papercase",
            "engine_id": ENGINE, "engine_version": "1.0.0",
            "market": "index", "provider": tick["provider"],
            "symbol": tick["symbol"], "timezone": tick["timezone"],
            "quote_currency": tick["quote_currency"],
            "direction": "long", "observed_at": tick["occurred_at"],
            "entry": "43000", "stop": "42980", "targets": ["43070"],
            "evidence_mode": "paper",
        })
        answer = {
            "version": 1, "key_id": "owner_k1", "direction": "to_bot",
            "engine_id": ENGINE, "engine_version": "1.0.0",
            "nonce": secrets.token_hex(16),
            "request_nonce": request["nonce"],
            "issued_at": NOW, "expires_at": NOW + 20,
            "payload": {"operation": "paper_analysis",
                        "paper_envelope_b64": base64.b64encode(envelope).decode()},
        }
        return sign_packet(answer, key=ok)

    connector = PrivatePaperConnector(
        manager=mgr, fence=replay, engine_id=ENGINE,
        engine_version="1.0.0", approved_digest=digest,
        keys=ConnectorKeys("client_k1", ck, "owner_k1", ok),
        exchange=custom_exchange or exchange,
        now_seconds=lambda: NOW,
        offline_admission=admission,
    )
    return mgr, replay, connector, p, exchange


def _tick():
    return QuoteTick(
        Instrument(Market.INDEX, "fixture:quotes", "US30", "UTC", "USD"),
        datetime.fromtimestamp(NOW, tz=timezone.utc),
        Decimal("43000"), Decimal("43001"), QuoteOrigin.SYNTHETIC,
    )


@pytest.mark.asyncio
async def test_a10_connector_accepts_signed_a12_paper_grant(material):
    mgr, replay, connector, _, _ = _connector_fixture(material)
    assert await connector.produce(_tick())
    mgr.close()
    replay.close()


@pytest.mark.asyncio
async def test_license_revoked_during_owner_callback_is_dropped(material):
    entered = asyncio.Event()
    release = asyncio.Event()

    async def waiting(packet):
        entered.set()
        await release.wait()
        return await direct(packet)

    mgr, replay, connector, policy_doc, direct = _connector_fixture(
        material, custom_exchange=waiting,
    )
    pending = asyncio.create_task(connector.produce(_tick()))
    await asyncio.wait_for(entered.wait(), timeout=2)
    serial = parse_grant(connector._offline_admission._grant)[0]["serial"]
    material["store"].revoke_serial(serial)
    release.set()
    with pytest.raises(AdmissionRefused, match="SERIAL_REVOKED"):
        await asyncio.wait_for(pending, timeout=2)
    replay.close()
    mgr.close()


@pytest.mark.asyncio
async def test_grant_expiry_during_connection_is_rejected(material):
    mgr, replay, connector, p, _ = _connector_fixture(material)
    # The fake clock expires after request even if the owner replies promptly.
    values = iter([NOW, NOW, NOW + 200])
    connector._clock = lambda: next(values)
    with pytest.raises(AdmissionRefused, match="EXPIRED_OR_FUTURE"):
        await connector.produce(_tick())
    replay.close()
    mgr.close()
