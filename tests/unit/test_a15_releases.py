"""A15 real Ed25519 signed release and independent rollback-floor rehearsal."""
from __future__ import annotations

import base64
import hashlib
import json

import pytest

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from naseri_markets.a15_releases import (
    DOMAIN, ROTATION_DOMAIN, ReleaseRefused, SignedMockDeploymentManager,
    SignedReleaseAuthority, canonical, parse_signed_release,
)
from naseri_markets.a14_packages import MockPackageDeploymentManager
from test_a14_packages import (
    FakeProvisioner, bundle, ENGINE, INSTALL, DESCRIPTOR,
)

NOW = 42
KEY1 = "fixture_publisher_one"
KEY2 = "fixture_publisher_two"


def public(private):
    return private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def sign(private, archive: bytes, *, sequence: int, key_id: str = KEY1,
         generation: int = 1, release: str = "1.0.0", **changes) -> bytes:
    fields = {
        "schema_version": 1, "kind": "synthetic_private_data",
        "mode": "offline_paper_only", "engine_id": ENGINE,
        "engine_version": "1.0.0", "installation_id": INSTALL,
        "manifest_sha256": DESCRIPTOR, "trust_generation": 1,
        "release": release, "release_sequence": sequence,
        "artifact_sha256": sha(archive), "publisher_key_id": key_id,
        "publisher_generation": generation, "issued_at": NOW - 10,
        "expires_at": NOW + 300,
    }
    fields.update(changes)
    return canonical({
        "release": fields,
        "signature_b64": base64.b64encode(
            private.sign(DOMAIN + canonical(fields))
        ).decode("ascii"),
    })


@pytest.fixture
def ctx(tmp_path):
    guard = FakeProvisioner()
    private = Ed25519PrivateKey.generate()
    pub = public(private)
    auth = SignedReleaseAuthority(
        tmp_path / "independent-witness.db", engine_id=ENGINE,
        installation_id=INSTALL, publisher_key_id=KEY1,
        publisher_public_key=pub, approved_key_sha256=sha(pub),
    )
    worker = MockPackageDeploymentManager(
        tmp_path / "releases", provisioner=guard, engine_id=ENGINE,
        installation_id=INSTALL,
    )
    facade = SignedMockDeploymentManager(worker, auth)
    yield facade, auth, worker, guard, private
    worker.close()
    auth.close()


def promote(facade, guard, private, release, sequence, *, behavior="healthy",
            key_id=KEY1, generation=1):
    artifact, _ = bundle(release, behavior=behavior)
    envelope = sign(private, artifact, sequence=sequence, release=release,
                    key_id=key_id, generation=generation)
    status = facade.install(
        artifact, envelope, expected_revision=facade.status().revision,
        admission=guard, now=NOW)
    return status, artifact, envelope


def start(facade, guard):
    return facade.start(expected_revision=facade.status().revision,
                        admission=guard, now=NOW)


def stop(facade):
    return facade.stop(expected_revision=facade.status().revision)


def test_signed_install_start_stop_and_replay_protection(ctx):
    facade, auth, _, guard, private = ctx
    state, raw, proof = promote(facade, guard, private, "1.0.0", 100)
    assert state.revision == 1
    assert auth.floor().sequence == 100
    assert auth.floor().artifact_sha256 == sha(raw)
    assert start(facade, guard).state == "MOCK_RUNNING"
    assert stop(facade).state == "STOPPED"
    with pytest.raises(ReleaseRefused, match="A15_ROLLBACK"):
        facade.install(
            *([bundle("0.9.0")[0], sign(private, bundle("0.9.0")[0],
                                          sequence=99, release="0.9.0")]),
            expected_revision=facade.status().revision, admission=guard, now=NOW)
    assert auth.floor().sequence == 100


def test_signed_upgrade_fences_old_rollback(ctx):
    facade, auth, mock, guard, private = ctx
    state, _, _ = promote(facade, guard, private, "1.0.0", 1)
    saved_earlier_state = mock._state_path.read_bytes()
    newer, _, _ = promote(facade, guard, private, "1.0.1", 2)
    assert newer.previous == state.active
    assert auth.floor().sequence == 2
    with pytest.raises(ReleaseRefused, match="A15_EXTERNAL_FLOOR"):
        facade.rollback(expected_revision=newer.revision, admission=guard, now=NOW)
    # An A14 data snapshot restored independently from the A15 witness
    # cannot start its older package via the signed A15 facade.
    mock._state_path.write_bytes(saved_earlier_state)
    with pytest.raises(ReleaseRefused, match="A15_EXTERNAL_FLOOR"):
        facade.start(expected_revision=1, admission=guard, now=NOW)


def test_failed_worker_start_remains_fenced_not_old_release(ctx):
    facade, auth, _, guard, private = ctx
    first, _, _ = promote(facade, guard, private, "1.0.0", 1)
    newer, _, _ = promote(
        facade, guard, private, "1.0.1", 2, behavior="fail_start"
    )
    with pytest.raises(ValueError, match="A14_INJECTED_MOCK_START_FAILURE"):
        start(facade, guard)
    assert facade.status().active == first.active  # A14 did mock pointer rollback
    assert auth.floor().sequence == 2
    with pytest.raises(ReleaseRefused, match="A15_EXTERNAL_FLOOR"):
        start(facade, guard)


def test_unsigned_tampered_forged_and_foreign_release_rejected(ctx):
    facade, auth, _, guard, private = ctx
    raw, _ = bundle("1.0.0")
    proof = sign(private, raw, sequence=1)
    wrong = json.loads(proof)
    wrong["release"]["release_sequence"] = 999
    bad = canonical(wrong)
    with pytest.raises(ReleaseRefused, match="SIGNATURE_INVALID"):
        facade.install(raw, bad, expected_revision=0, admission=guard, now=NOW)
    with pytest.raises(ReleaseRefused):
        parse_signed_release(b'{"release": {}, "release": {}, "signature_b64": "x"}')
    outsider = Ed25519PrivateKey.generate()
    with pytest.raises(ReleaseRefused, match="SIGNATURE_INVALID"):
        facade.install(raw, sign(outsider, raw, sequence=1),
                       expected_revision=0, admission=guard, now=NOW)
    wrong_installation = sign(private, raw, sequence=1,
                              installation_id="another_instance")
    with pytest.raises(ReleaseRefused, match="SCOPE_MISMATCH"):
        facade.install(raw, wrong_installation,
                       expected_revision=0, admission=guard, now=NOW)
    expired = sign(private, raw, sequence=1, expires_at=NOW)
    with pytest.raises(ReleaseRefused, match="EXPIRED"):
        facade.install(raw, expired, expected_revision=0, admission=guard, now=NOW)
    future = sign(private, raw, sequence=1, issued_at=NOW + 10,
                  expires_at=NOW + 100)
    with pytest.raises(ReleaseRefused, match="FUTURE"):
        facade.install(raw, future, expected_revision=0, admission=guard, now=NOW)
    assert facade.status().active is None
    assert auth.floor() is None


def test_equal_sequence_other_artifact_and_stale_revision(ctx):
    facade, auth, _, guard, private = ctx
    promote(facade, guard, private, "1.0.0", 1)
    other, _ = bundle("1.0.1")
    with pytest.raises(ReleaseRefused, match="ROLLBACK_OR_EQUIVOCATION"):
        facade.install(other, sign(private, other, sequence=1, release="1.0.1"),
                       expected_revision=1, admission=guard, now=NOW)
    with pytest.raises(ReleaseRefused, match="STOP_AND_CAS"):
        facade.install(other, sign(private, other, sequence=2, release="1.0.1"),
                       expected_revision=0, admission=guard, now=NOW)
    assert auth.floor().sequence == 1


def test_independent_publisher_key_pin_survives_restart(ctx, tmp_path):
    facade, auth, _, guard, private = ctx
    promote(facade, guard, private, "1.0.0", 10)
    different = public(Ed25519PrivateKey.generate())
    with pytest.raises(ReleaseRefused, match="TRUST_PIN_CHANGE"):
        SignedReleaseAuthority(
            tmp_path / "independent-witness.db", engine_id=ENGINE,
            installation_id=INSTALL, publisher_key_id=KEY1,
            publisher_public_key=different, approved_key_sha256=sha(different),
        )
    same = public(private)
    restored = SignedReleaseAuthority(
        tmp_path / "independent-witness.db", engine_id=ENGINE,
        installation_id=INSTALL, publisher_key_id=KEY1,
        publisher_public_key=same, approved_key_sha256=sha(same),
    )
    assert restored.floor().sequence == 10
    restored.close()


def test_key_rotation_requires_old_signature_and_new_out_of_band_pin(ctx):
    facade, auth, _, guard, private = ctx
    promote(facade, guard, private, "1.0.0", 10)
    replacement = Ed25519PrivateKey.generate()
    pub = public(replacement)
    move = {
        "engine_id": ENGINE, "installation_id": INSTALL,
        "from_generation": 1, "to_generation": 2,
        "new_key_id": KEY2, "new_key_sha256": sha(pub),
    }
    signature = base64.b64encode(
        private.sign(ROTATION_DOMAIN + canonical(move))
    ).decode("ascii")
    with pytest.raises(ReleaseRefused, match="SIGNATURE_INVALID"):
        auth.rotate_publisher(
            new_key_id=KEY2, new_public_key=pub,
            approved_key_sha256=sha(pub), expected_generation=1,
            old_key_signature_b64=base64.b64encode(
                replacement.sign(ROTATION_DOMAIN + canonical(move))
            ).decode("ascii"),
        )
    auth.rotate_publisher(
        new_key_id=KEY2, new_public_key=pub,
        approved_key_sha256=sha(pub), expected_generation=1,
        old_key_signature_b64=signature,
    )
    assert auth.floor().sequence == 10
    with pytest.raises(ReleaseRefused, match="PUBLISHER_GENERATION"):
        start(facade, guard)
    new, _, _ = promote(facade, guard, replacement, "1.0.1", 11,
                        key_id=KEY2, generation=2)
    assert new.previous is not None
    assert start(facade, guard).state == "MOCK_RUNNING"
    stop(facade)
    with pytest.raises(ReleaseRefused, match="ROTATION_CAS"):
        auth.rotate_publisher(
            new_key_id=KEY2, new_public_key=pub,
            approved_key_sha256=sha(pub), expected_generation=1,
            old_key_signature_b64=signature,
        )


def test_revoke_blocks_start_but_allows_stop(ctx):
    facade, auth, _, guard, private = ctx
    promote(facade, guard, private, "1.0.0", 1)
    assert start(facade, guard).owned_mock_worker_running
    auth.revoke_publisher(expected_generation=1)
    assert stop(facade).state == "STOPPED"
    with pytest.raises(ReleaseRefused, match="PUBLISHER_REVOKED"):
        start(facade, guard)


def test_fresh_a13_guard_required_even_with_valid_publisher_signature(ctx):
    facade, auth, _, guard, private = ctx
    raw, _ = bundle("1.0.0")
    proof = sign(private, raw, sequence=1)
    guard.enabled = False
    with pytest.raises(ValueError, match="A14_A13_FRESH_ADMISSION"):
        facade.install(raw, proof, expected_revision=0,
                       admission=guard, now=NOW)
    assert auth.floor() is None


def test_external_witness_cannot_be_inside_mock_root(ctx):
    facade, auth, mock, guard, private = ctx
    inside = SignedReleaseAuthority(
        mock._root / "unsafe.db", engine_id=ENGINE,
        installation_id=INSTALL, publisher_key_id=KEY1,
        publisher_public_key=public(private), approved_key_sha256=sha(public(private))
    )
    with pytest.raises(ReleaseRefused, match="WITNESS_MUST_BE_INDEPENDENT"):
        SignedMockDeploymentManager(mock, inside)
    inside.close()


def test_a15_real_a12_a13_signed_grant_to_publisher_release_end_to_end(tmp_path):
    """Separate ephemeral A12 issuer and A15 publisher keys; no private service."""
    from test_a13_provisioning import (
        fixture as a13_fixture, plan, admission, digest as a13_sha,
        NOW as real_now, ENGINE as real_engine, INSTALL as real_install,
    )

    plugins, trust, license_issuer, _, policy, provisioner = a13_fixture(tmp_path)
    plan_bytes = plan(policy)
    pending = provisioner.prepare(plan_bytes, approved_sha256=a13_sha(plan_bytes))
    signed_grant = admission(trust, license_issuer, policy)
    assert provisioner.verify(
        real_engine, expected_revision=pending.revision,
        admission=signed_grant, now=real_now,
    ).status == "OFFLINE_VERIFIED"

    publisher = Ed25519PrivateKey.generate()
    publisher_pub = public(publisher)
    release_authority = SignedReleaseAuthority(
        tmp_path / "independent-a15-witness.db", engine_id=real_engine,
        installation_id=real_install, publisher_key_id=KEY1,
        publisher_public_key=publisher_pub,
        approved_key_sha256=sha(publisher_pub),
    )
    mock = MockPackageDeploymentManager(
        tmp_path / "a15-release-fixture", provisioner=provisioner,
        engine_id=real_engine, installation_id=real_install,
    )
    signed_manager = SignedMockDeploymentManager(mock, release_authority)
    archive, _ = bundle(
        "1.0.0", engine=real_engine, installation=real_install,
        digest=policy["manifest_sha256"], generation=policy["generation"],
    )
    envelope = sign(
        publisher, archive, sequence=1,
        installation_id=real_install,
        manifest_sha256=policy["manifest_sha256"],
        trust_generation=policy["generation"],
        issued_at=real_now - 10, expires_at=real_now + 300,
    )
    installed = signed_manager.install(
        archive, envelope, expected_revision=0,
        admission=signed_grant, now=real_now,
    )
    assert installed.state == "STOPPED"
    assert signed_manager.start(
        expected_revision=installed.revision,
        admission=signed_grant, now=real_now,
    ).state == "MOCK_RUNNING"
    trust.revoke_serial("a" * 32)
    stopped = signed_manager.stop(expected_revision=2)
    assert stopped.state == "STOPPED"
    with pytest.raises(ValueError, match="A14_A13_FRESH_ADMISSION"):
        signed_manager.start(
            expected_revision=stopped.revision,
            admission=signed_grant, now=real_now,
        )
    mock.close()
    release_authority.close()
    provisioner.close()
    plugins.close()
    trust.close()
