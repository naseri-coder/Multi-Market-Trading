"""Stage29 one-use Ed25519 publisher login and quarantined signed ZIP intake."""
from __future__ import annotations

import pytest

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from naseri_markets.a24_publisher_admission import canonical
from naseri_markets.authenticated_developer_intake_stage29_v1 import (
    AuthenticatedDeveloperIntake, Stage29Refused, _LOGIN_DOMAIN,
)
from naseri_markets.publisher_package_registry_stage28_v1 import (
    Stage28Refused, _ROTATE_DOMAIN,
)
from test_publisher_package_registry_stage28_v1 import (
    KEY_ID, NONCE, NOW, PUB, TENANT, digest, roster, submit_args,  # noqa: F401
)
from test_signed_core_candidate_stage23_v1 import key_bytes


@pytest.fixture
def intake(roster):  # noqa: F811
    registry, gate, _witness, signer, _operator, _signed, _folder = roster
    now = [NOW]
    authenticated = AuthenticatedDeveloperIntake(
        registry, operator_ack=True, clock=lambda: now[0])
    return authenticated, now, signer, roster


def login(intake):
    gateway, _now, signer, _roster = intake
    challenge = gateway.begin_login(
        tenant_id=TENANT, publisher=PUB, key_id=KEY_ID, operator_ack=True)
    signature = signer.sign(_LOGIN_DOMAIN + canonical(challenge))
    session = gateway.complete_login(
        challenge=challenge, signature=signature, operator_ack=True)
    return session, challenge


def test_login_real_signature_and_one_use_upload_is_atomic_with_stage27(intake, monkeypatch):
    gateway, now, _signer, original = intake
    registry, gate, witness, *_ = original
    session, challenge = login(intake)
    assert challenge["scope"] == "QUARANTINE_SUBMIT_ONCE"
    assert session.scope == "QUARANTINE_SUBMIT_ONCE"
    assert not session.public_plugin_install_authorized
    assert not session.broker_order_authorized
    assert len(session.token) == 43
    assert session.token.encode() not in gate.path.read_bytes()
    assert gateway.status(token=session.token)["tenant_id"] == TENANT
    with pytest.raises(Stage28Refused, match="STAGE29_AUTHENTICATED_INTAKE_REQUIRED"):
        registry.submit(**submit_args(original))
    called = []
    monkeypatch.setattr(gate.host, "evaluate",
                        lambda *_a, **_k: called.append(True))
    args = submit_args(original)
    receipt = gateway.submit_package(
        token=session.token, stage23=witness, package=args["package"],
        signed_candidate=args["signed_candidate"], manifest=args["manifest"],
        binding=args["binding"], expected_image=args["expected_image"],
        operator_ack=True)
    assert receipt.state == "QUARANTINED_PUBLIC_SOURCE_NOT_EXECUTABLE"
    assert gate.state(TENANT, "binding_a")["state"] == "DISABLED"
    assert gate.state(TENANT, "binding_a")["public_untrusted_intake_pending"]
    assert gate.db.execute(
        "SELECT state FROM secure29_sessions").fetchone()[0] == "CONSUMED"
    assert gate.db.execute(
        "SELECT COUNT(*) FROM secure28_submissions").fetchone()[0] == 1
    assert [r["action"] for r in registry.audit(
        tenant_id=TENANT, publisher=PUB)] == [
            "ENROLLED", "AUTHENTICATED", "SUBMITTED"]
    assert not called
    with pytest.raises(Stage29Refused, match="SESSION_INVALID_OR_CONSUMED"):
        gateway.submit_package(
            token=session.token, stage23=witness, package=args["package"],
            signed_candidate=args["signed_candidate"], manifest=args["manifest"],
            binding=args["binding"], expected_image=args["expected_image"],
            operator_ack=True)
    assert not called


def test_bad_signature_does_not_consume_challenge(intake):
    gateway, _now, signer, _ = intake
    challenge = gateway.begin_login(
        tenant_id=TENANT, publisher=PUB, key_id=KEY_ID, operator_ack=True)
    false = Ed25519PrivateKey.generate().sign(_LOGIN_DOMAIN + canonical(challenge))
    with pytest.raises(Stage29Refused, match="INVALID_LOGIN_SIGNATURE"):
        gateway.complete_login(
            challenge=challenge, signature=false, operator_ack=True)
    good = signer.sign(_LOGIN_DOMAIN + canonical(challenge))
    session = gateway.complete_login(
        challenge=challenge, signature=good, operator_ack=True)
    assert session.token
    with pytest.raises(Stage29Refused, match="EXPIRED_USED_OR_TAMPERED"):
        gateway.complete_login(
            challenge=challenge, signature=good, operator_ack=True)


@pytest.mark.parametrize("tamper", [
    {"tenant_id": "tenant_beta"},
    {"publisher": "impostor.vendor"},
    {"publisher_key_id": "other_key"},
    {"scope": "PUBLIC_PLUGIN_EXECUTE"},
    {"publisher_revision": 2},
    {"expires_at": NOW + 500},
    {"schema": True},
    {"admin": True},
])
def test_altered_domain_bound_challenge_fails(intake, tamper):
    gateway, _now, signer, _ = intake
    claim = gateway.begin_login(
        tenant_id=TENANT, publisher=PUB, key_id=KEY_ID, operator_ack=True)
    corrupted = {**claim, **tamper}
    with pytest.raises(Stage29Refused):
        gateway.complete_login(
            challenge=corrupted,
            signature=signer.sign(_LOGIN_DOMAIN+canonical(corrupted)),
            operator_ack=True)


def test_expired_challenge_and_expired_session_denied(intake):
    gateway, now, signer, _ = intake
    claim = gateway.begin_login(
        tenant_id=TENANT, publisher=PUB, key_id=KEY_ID, operator_ack=True)
    now[0] += 121
    with pytest.raises(Stage29Refused, match="EXPIRED_USED"):
        gateway.complete_login(
            challenge=claim,
            signature=signer.sign(_LOGIN_DOMAIN+canonical(claim)),
            operator_ack=True)
    now[0] = NOW
    session, _ = login(intake)
    now[0] += 301
    with pytest.raises(Stage29Refused, match="SESSION_EXPIRED"):
        gateway.status(token=session.token)


def test_revoked_key_invalidates_preauthorized_session(intake):
    gateway, now, _signer, original = intake
    registry, gate, _witness, *_ = original
    session, _ = login(intake)
    registry.revoke(
        tenant_id=TENANT, publisher=PUB, key_id=KEY_ID,
        expected_revision=1, now=NOW, operator_ack=True)
    with pytest.raises(Stage29Refused, match="PUBLISHER_NOT_AUTHORIZED"):
        gateway.status(token=session.token)
    assert gate.db.execute(
        "SELECT COUNT(*) FROM secure28_submissions").fetchone()[0] == 0


def test_key_rotation_revokes_session_and_old_login(intake):
    gateway, now, signer, original = intake
    registry, gate, witness, *_ = original
    session, _ = login(intake)
    newer = Ed25519PrivateKey.generate()
    new_key = key_bytes(newer)
    claim = dict(tenant_id=TENANT, publisher=PUB, old_key_id=KEY_ID,
                 new_key_id="key_two", new_key_sha256=digest(new_key),
                 revision=1, nonce=NONCE, issued_at=NOW)
    registry.rotate(
        tenant_id=TENANT, publisher=PUB, old_key_id=KEY_ID,
        new_key_id="key_two", new_public_key=new_key,
        old_signature=signer.sign(_ROTATE_DOMAIN+canonical(claim)),
        new_signature=newer.sign(_ROTATE_DOMAIN+canonical(claim)),
        expected_revision=1, nonce=NONCE, issued_at=NOW, now=NOW,
        operator_ack=True)
    with pytest.raises(Stage29Refused):
        gateway.status(token=session.token)
    with pytest.raises(Stage29Refused):
        gateway.begin_login(
            tenant_id=TENANT, publisher=PUB, key_id=KEY_ID, operator_ack=True)
    # The next new-key login is possible but Stage23 also needs a NEW
    # independently reviewed issuer witness: no old source promotion.
    fresh = gateway.begin_login(
        tenant_id=TENANT, publisher=PUB, key_id="key_two", operator_ack=True)
    assert fresh["publisher_revision"] == 2
    assert gate.db.execute(
        "SELECT COUNT(*) FROM secure28_submissions").fetchone()[0] == 0


def test_one_use_session_revoke_no_cross_tenant_logout(intake):
    gateway, _now, _signer, original = intake
    session, _ = login(intake)
    gateway.revoke_session(token=session.token, operator_ack=True)
    with pytest.raises(Stage29Refused, match="SESSION_INVALID"):
        gateway.status(token=session.token)
    assert original[0].audit(tenant_id=TENANT, publisher=PUB)[-1][
        "action"] == "SESSION_REVOKED"
    with pytest.raises(Stage29Refused):
        gateway.revoke_session(token=session.token, operator_ack=True)


def test_invalid_session_and_no_ack_never_create_archive(intake):
    gateway, now, signer, original = intake
    registry, gate, witness, *_ = original
    args = submit_args(original)
    with pytest.raises(Stage29Refused):
        gateway.submit_package(
            token="a"*43, stage23=witness, package=args["package"],
            signed_candidate=args["signed_candidate"], manifest=args["manifest"],
            binding=args["binding"], expected_image=args["expected_image"],
            operator_ack=True)
    assert not list(registry.quarantine_dir.iterdir())
    session, _ = login(intake)
    with pytest.raises(Stage28Refused, match="EXPLICIT_NONPRODUCTION"):
        registry.submit(**{**args, "operator_ack": False})
    with pytest.raises(Stage28Refused, match="STAGE29_AUTHENTICATED"):
        registry.submit(**args)
    assert not gate.db.execute("SELECT 1 FROM secure22_bindings").fetchone()


def test_rejected_second_sqlite_insert_keeps_session_unconsumed_and_no_binding(intake):
    gateway, _now, _signer, original = intake
    registry, gate, witness, *_ = original
    session, _ = login(intake)
    gate.db.execute("""CREATE TRIGGER sabotage29 BEFORE INSERT
       ON secure27_public_intake BEGIN
       SELECT RAISE(ABORT,'SIMULATED_ATOMIC_COMMIT_FAILURE'); END""")
    args = submit_args(original)
    with pytest.raises(Stage29Refused, match="AUTHENTICATED_QUARANTINE_REFUSED"):
        gateway.submit_package(
            token=session.token, stage23=witness, package=args["package"],
            signed_candidate=args["signed_candidate"], manifest=args["manifest"],
            binding=args["binding"], expected_image=args["expected_image"],
            operator_ack=True)
    assert gate.db.execute(
        "SELECT state FROM secure29_sessions").fetchone()[0] == "ACTIVE"
    assert gate.db.execute(
        "SELECT COUNT(*) FROM secure22_bindings").fetchone()[0] == 0
    assert gate.db.execute(
        "SELECT COUNT(*) FROM secure28_submissions").fetchone()[0] == 0
    assert len(list(registry.quarantine_dir.iterdir())) == 1


def test_challenge_rate_limit_and_session_quota(intake):
    gateway, _now, signer, _ = intake
    claims = [gateway.begin_login(
        tenant_id=TENANT, publisher=PUB, key_id=KEY_ID,
        operator_ack=True) for _ in range(4)]
    with pytest.raises(Stage29Refused, match="PUBLISHER_LOGIN_RATE_LIMIT"):
        gateway.begin_login(
            tenant_id=TENANT, publisher=PUB, key_id=KEY_ID,
            operator_ack=True)
    for c in claims:
        gateway.complete_login(challenge=c,
                               signature=signer.sign(_LOGIN_DOMAIN+canonical(c)),
                               operator_ack=True)
    with pytest.raises(Stage29Refused, match="PUBLISHER_SESSION_QUOTA"):
        c = gateway.begin_login(
            tenant_id=TENANT, publisher=PUB, key_id=KEY_ID,
            operator_ack=True)
        gateway.complete_login(challenge=c,
                               signature=signer.sign(_LOGIN_DOMAIN+canonical(c)),
                               operator_ack=True)


def test_production_flag_blocks_login_and_upload(intake, monkeypatch):
    gateway, _now, _signer, original = intake
    session, _ = login(intake)
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises((Stage28Refused, Stage29Refused), match="EXPLICIT_NONPRODUCTION"):
        gateway.begin_login(
            tenant_id=TENANT, publisher=PUB, key_id=KEY_ID,
            operator_ack=True)
    args = submit_args(original)
    with pytest.raises((Stage28Refused, Stage29Refused), match="EXPLICIT_NONPRODUCTION"):
        gateway.submit_package(
            token=session.token, stage23=original[2],
            package=args["package"], signed_candidate=args["signed_candidate"],
            manifest=args["manifest"], binding=args["binding"],
            expected_image=args["expected_image"], operator_ack=True)
