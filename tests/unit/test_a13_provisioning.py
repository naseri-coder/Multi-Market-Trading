"""A13 real metadata-only private plugin preparation and readiness tests."""
from __future__ import annotations

import base64
import hashlib
import json

import pytest

pytest.importorskip("cryptography", reason="A13 Ed25519 tests run in dedicated CI")
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from naseri_markets.a12_trust import (
    DOMAIN, OfflineAdmission, TrustStore, canonical,
)
from naseri_markets.a13_provisioning import (
    OfflineProvisioner, ProvisioningRefused, parse_plan,
)
from naseri_markets.plugin_manager import PluginManager

NOW = 1791549000
ENGINE = "private_example"
CA = b"a13-ephemeral-fixture-ca"
LEAF = b"a13-ephemeral-fixture-owner-leaf"
INSTALL = "a13_fixture_install"


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def fixture(tmp_path, *, private=True):
    plugins = PluginManager(tmp_path / "plugin-settings.db")
    trust = TrustStore(tmp_path / "owner-trust.db")
    issuer = Ed25519PrivateKey.generate()
    public = issuer.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    descriptor = canonical({
        "schema_version": 1,
        "engine_id": ENGINE,
        "engine_version": "1.0.0",
        "publisher": "fixture.owner",
        "visibility": "private" if private else "public",
        "adapter": "external_contract" if private else "in_process",
        "abi_version": 1, "markets": ["index"],
        "permissions": ["paper_analysis"],
    })
    state = plugins.register(descriptor, approved_sha256=digest(descriptor))
    policy = {
        "schema_version": 1, "generation": 1,
        "engine_id": ENGINE, "engine_version": "1.0.0",
        "manifest_sha256": state.digest,
        "owner_dns": "private-owner.fixture",
        "owner_cert_sha256": digest(LEAF),
        "ca_sha256": digest(CA),
        "issuer_key_id": "issuer_k1",
        "issuer_public_key_b64": base64.b64encode(public).decode("ascii"),
    }
    raw_policy = canonical(policy)
    trust.stage(raw_policy, approved_sha256=digest(raw_policy))
    trust.promote(ENGINE, generation=1, expected_active=0)
    provision = OfflineProvisioner(
        tmp_path / "provision.db", plugins=plugins, trust=trust,
    )
    return plugins, trust, issuer, state, policy, provision


def plan(policy):
    return canonical({
        "schema_version": 1,
        "engine_id": policy["engine_id"],
        "engine_version": policy["engine_version"],
        "manifest_sha256": policy["manifest_sha256"],
        "trust_generation": policy["generation"],
        "owner_dns": policy["owner_dns"],
        "owner_cert_sha256": policy["owner_cert_sha256"],
        "ca_sha256": policy["ca_sha256"],
        "mode": "offline_paper_only",
    })


def admission(trust, issuer, policy, *, expires=NOW + 120, serial="a" * 32):
    license_fields = {
        "schema_version": 1,
        "serial": serial,
        "generation": policy["generation"],
        "engine_id": policy["engine_id"],
        "engine_version": policy["engine_version"],
        "manifest_sha256": policy["manifest_sha256"],
        "owner_dns": policy["owner_dns"],
        "installation_id": INSTALL,
        "issuer_key_id": policy["issuer_key_id"],
        "issued_at": NOW - 30,
        "expires_at": expires,
        "permissions": ["paper_analysis"],
    }
    signed = canonical({
        "grant": license_fields,
        "signature_b64": base64.b64encode(
            issuer.sign(DOMAIN + canonical(license_fields))
        ).decode("ascii"),
    })
    return OfflineAdmission(
        trust, engine_id=ENGINE, installation_id=INSTALL,
        signed_grant=signed, ca_pem=CA, owner_cert_der=LEAF,
    )


def test_full_prepare_verify_recheck_suspend_retire_and_restart(tmp_path):
    plugins, trust, issuer, _, policy, mgr = fixture(tmp_path)
    raw = plan(policy)
    stage = mgr.prepare(raw, approved_sha256=digest(raw))
    assert stage.status == "PREPARED"
    assert stage.revision == 1
    assert not plugins.get(ENGINE).enabled
    assert mgr.health(ENGINE).state == "PREPARED"
    attestation = admission(trust, issuer, policy)
    done = mgr.verify(ENGINE, expected_revision=1, admission=attestation, now=NOW)
    assert done.status == "OFFLINE_VERIFIED"
    assert done.revision == 2
    assert mgr.health(ENGINE).state == "RECHECK_REQUIRED"
    check = mgr.health(ENGINE, admission=attestation, now=NOW)
    assert check.state == "OFFLINE_VERIFIED"
    assert check.verified_offline
    assert not check.external_engine_connected
    assert not check.live_trading_permitted
    assert not check.telegram_enabled
    mgr.close()
    again = OfflineProvisioner(
        tmp_path / "provision.db", plugins=plugins, trust=trust,
    )
    assert again.health(ENGINE).state == "RECHECK_REQUIRED"
    assert again.health(ENGINE, admission=attestation, now=NOW).verified_offline
    suspended = again.suspend(ENGINE, expected_revision=2)
    assert suspended.status == "SUSPENDED"
    with pytest.raises(ProvisioningRefused, match="STALE|NOT_PREPARED"):
        again.verify(ENGINE, expected_revision=2, admission=attestation, now=NOW)
    retired = again.retire(ENGINE, expected_revision=3)
    assert retired.status == "RETIRED"
    with pytest.raises(ProvisioningRefused):
        again.prepare(raw, approved_sha256=digest(raw), expected_revision=4)
    assert [x["event"] for x in again.history(ENGINE)] == [
        "PREPARE", "VERIFY_LOCAL_ONLY", "SUSPEND", "RETIRE",
    ]
    assert plugins.get(ENGINE).enabled is False
    again.close()
    plugins.close()
    trust.close()


@pytest.mark.parametrize("changed", [
    {"schema_version": True}, {"schema_version": 3},
    {"trust_generation": 0}, {"trust_generation": True},
    {"mode": "live_trading"}, {"mode": "offline_paper_only", "command": "curl"},
    {"owner_dns": "private.example.com"}, {"owner_dns": "../owner.fixture"},
    {"engine_version": ""}, {"manifest_sha256": "123"},
])
def test_bounded_exact_no_executable_plan(tmp_path, changed):
    plugins, trust, issuer, _, policy, mgr = fixture(tmp_path)
    payload = json.loads(plan(policy))
    payload.update(changed)
    raw = canonical(payload)
    with pytest.raises(ProvisioningRefused):
        parse_plan(raw, approved_sha256=digest(raw))
    assert mgr.get(ENGINE) is None
    mgr.close()
    plugins.close()
    trust.close()


@pytest.mark.parametrize("bad", [b"", b"{}", b"x" * 8193,
                               b'{"schema_version":1,"schema_version":1}',
                               b'{"schema_version":NaN}'])
def test_untrusted_or_oversized_inputs_rejected(bad):
    with pytest.raises(ProvisioningRefused):
        parse_plan(bad, approved_sha256=digest(bad))


def test_plan_pin_is_not_self_approving(tmp_path):
    plugins, trust, issuer, _, policy, mgr = fixture(tmp_path)
    raw = plan(policy)
    with pytest.raises(ProvisioningRefused, match="PIN_MISMATCH"):
        mgr.prepare(raw, approved_sha256="0" * 64)
    with pytest.raises(ProvisioningRefused, match="INDEPENDENT"):
        mgr.prepare(raw, approved_sha256=digest(raw).upper())
    assert mgr.get(ENGINE) is None
    mgr.close()
    plugins.close()
    trust.close()


def test_public_and_enabled_private_not_provisionable(tmp_path):
    plugins, trust, issuer, row, policy, mgr = fixture(tmp_path)
    raw = plan(policy)
    plugins.set_enabled(ENGINE, enabled=True, expected_revision=row.revision)
    with pytest.raises(ProvisioningRefused, match="PRIVATE_DISABLED"):
        mgr.prepare(raw, approved_sha256=digest(raw))
    mgr.close()
    plugins.close()
    trust.close()
    other_dir = tmp_path / "public-sibling"
    other_dir.mkdir()
    plugins, trust, issuer, row, policy, mgr = fixture(
        other_dir, private=False,
    )
    raw = plan(policy)
    with pytest.raises(ProvisioningRefused, match="PRIVATE_DISABLED"):
        mgr.prepare(raw, approved_sha256=digest(raw))
    mgr.close()
    plugins.close()
    trust.close()


def test_grant_revocation_expiry_and_trust_rotation_invalidate_health(tmp_path):
    plugins, trust, issuer, row, policy, mgr = fixture(tmp_path)
    raw = plan(policy)
    mgr.prepare(raw, approved_sha256=digest(raw))
    evidence = admission(trust, issuer, policy)
    mgr.verify(ENGINE, expected_revision=1, admission=evidence, now=NOW)
    assert mgr.health(ENGINE, admission=evidence, now=NOW).verified_offline
    assert mgr.health(ENGINE, admission=evidence, now=NOW + 121).state == "ADMISSION_INVALID"
    trust.revoke_serial("a" * 32)
    assert mgr.health(ENGINE, admission=evidence, now=NOW).state == "ADMISSION_INVALID"
    next_policy = dict(policy, generation=2)
    new_raw = canonical(next_policy)
    trust.stage(new_raw, approved_sha256=digest(new_raw))
    trust.promote(ENGINE, generation=2, expected_active=1)
    assert mgr.health(ENGINE, admission=evidence, now=NOW).state == "ADMISSION_INVALID"
    mgr.close()
    trust.close()
    plugins.close()


def test_invalidation_after_plugin_activation_or_removal(tmp_path):
    plugins, trust, issuer, state, policy, mgr = fixture(tmp_path)
    raw = plan(policy)
    mgr.prepare(raw, approved_sha256=digest(raw))
    evidence = admission(trust, issuer, policy)
    mgr.verify(ENGINE, expected_revision=1, admission=evidence, now=NOW)
    toggled = plugins.set_enabled(ENGINE, enabled=True, expected_revision=1)
    assert mgr.health(ENGINE, admission=evidence, now=NOW).state == "ADMISSION_INVALID"
    plugins.set_enabled(ENGINE, enabled=False, expected_revision=toggled.revision)
    plugins.unregister(ENGINE, expected_revision=toggled.revision + 1)
    new_state = plugins.register(
        canonical({
            "schema_version": 1, "engine_id": ENGINE, "engine_version": "1.0.0",
            "publisher": "fixture.owner", "visibility": "private",
            "adapter": "external_contract", "abi_version": 1,
            "markets": ["index"], "permissions": ["paper_analysis"],
        }),
        approved_sha256=policy["manifest_sha256"],
    )
    assert new_state.enabled is False
    assert mgr.health(ENGINE, admission=evidence, now=NOW).state == "ADMISSION_INVALID"
    mgr.close()
    plugins.close()
    trust.close()


def test_reprepare_after_disable_and_approved_trust_rotation(tmp_path):
    plugins, trust, issuer, row, policy, mgr = fixture(tmp_path)
    first = plan(policy)
    mgr.prepare(first, approved_sha256=digest(first))
    evidence = admission(trust, issuer, policy)
    mgr.verify(ENGINE, expected_revision=1, admission=evidence, now=NOW)
    suspended = mgr.suspend(ENGINE, expected_revision=2)
    new_policy = dict(policy, generation=2)
    policy_bytes = canonical(new_policy)
    trust.stage(policy_bytes, approved_sha256=digest(policy_bytes))
    trust.promote(ENGINE, generation=2, expected_active=1)
    candidate = plan(new_policy)
    changed = mgr.prepare(
        candidate, approved_sha256=digest(candidate),
        expected_revision=suspended.revision,
    )
    assert changed.status == "PREPARED" and changed.revision == 4
    assert changed.generation == 2
    with pytest.raises(ProvisioningRefused, match="POLICY_MISMATCH"):
        mgr.prepare(first, approved_sha256=digest(first), expected_revision=4)
    new_evidence = admission(trust, issuer, new_policy, serial="b" * 32)
    assert mgr.verify(
        ENGINE, expected_revision=4, admission=new_evidence, now=NOW,
    ).revision == 5
    assert mgr.health(ENGINE, admission=new_evidence, now=NOW).verified_offline
    mgr.close()
    plugins.close()
    trust.close()


def test_stale_cas_and_unsafe_store_path(tmp_path):
    plugins, trust, issuer, row, policy, mgr = fixture(tmp_path)
    raw = plan(policy)
    mgr.prepare(raw, approved_sha256=digest(raw))
    with pytest.raises(ProvisioningRefused, match="STALE|NOT_PREPARED"):
        mgr.verify(ENGINE, expected_revision=99,
                   admission=admission(trust, issuer, policy), now=NOW)
    with pytest.raises(ProvisioningRefused, match="INVALID_TRANSITION"):
        mgr.retire(ENGINE, expected_revision=1)
    with pytest.raises(ProvisioningRefused, match="SUSPEND_AND_CAS"):
        mgr.prepare(raw, approved_sha256=digest(raw), expected_revision=1)
    link = tmp_path / "link"
    link.symlink_to(tmp_path / "provision.db")
    with pytest.raises(ProvisioningRefused, match="UNSAFE_STORE"):
        OfflineProvisioner(link, plugins=plugins, trust=trust)
    mgr.close()
    plugins.close()
    trust.close()
