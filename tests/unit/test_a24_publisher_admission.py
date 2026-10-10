"""A24 independently signed public Custom admission and real A23 fixture E2E."""
from __future__ import annotations

import asyncio
import base64
import json
import threading

import pytest

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from naseri_markets.a21_custom_contract import CustomContractCatalog
from naseri_markets.a22_custom_bridge import CustomPaperRuntimeBridge
from naseri_markets.a23_sandbox_adapter import FixedCustomSandbox
from naseri_markets.a24_publisher_admission import (
    AdmittedFixedCustomSession, PublisherAdmissionAuthority,
    PublisherAdmissionRefused, PUBLISHER_DOMAIN, OPERATOR_DOMAIN, canonical,
)
from naseri_markets.paper_journal import PaperJournal
from test_a22_custom_bridge import metadata, pinned, sample
from test_a7_replay_pipeline import INST, quote, session

NOW = 1000
INSTALL = "public_ci_fixture_one"
PUBLISHER_KEY_ID = "community_publisher_one"


def public(signer):
    return signer.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)


def signed(ctx, *, seq=1, publisher_signer=None, operator_signer=None, **override):
    _, contract, _, owner, pub, op, _, _, _ = ctx
    claim = {
        "schema_version": 1,
        "kind": "public_custom_paper_metadata",
        "engine_id": contract.engine_id,
        "engine_version": contract.engine_version,
        "publisher": contract.publisher,
        "publisher_key_id": PUBLISHER_KEY_ID,
        "installation_id": INSTALL,
        "descriptor_sha256": contract.approved_descriptor_sha256,
        "sequence": seq,
        "issued_at": NOW - 10,
        "expires_at": NOW + 300,
        "permissions": ["paper_analysis"],
        "execution_kind": "fixed_a23_data_relay_only",
        "artifact_policy": "no_executable_or_ciphertext",
        "runtime_mode": "ephemeral_ci_paper",
    }
    claim.update(override)
    publisher_signer = publisher_signer or pub
    operator_signer = operator_signer or op
    ps = base64.b64encode(publisher_signer.sign(
        PUBLISHER_DOMAIN + canonical(claim))).decode("ascii")
    osig = base64.b64encode(operator_signer.sign(
        OPERATOR_DOMAIN + canonical({
            "claim": claim, "publisher_signature_b64": ps}))).decode("ascii")
    return canonical({
        "claim": claim, "publisher_signature_b64": ps,
        "operator_signature_b64": osig,
    })


@pytest.fixture
def ctx(tmp_path):
    catalog = CustomContractCatalog()
    descriptor = metadata()
    contract = catalog.register(descriptor, approved_sha256=pinned(descriptor))
    pub = Ed25519PrivateKey.generate()
    op = Ed25519PrivateKey.generate()
    db = tmp_path / "authority" / "a24.db"
    db.parent.mkdir(mode=0o700)
    auth = PublisherAdmissionAuthority(
        db, operator_public_key=public(op),
        approved_operator_key_sha256=pinned(public(op)))
    auth.register_publisher("community.vendor", PUBLISHER_KEY_ID,
                            public(pub), approved_key_sha256=pinned(public(pub)))
    journal = PaperJournal(tmp_path / "journal.db")
    bridge = CustomPaperRuntimeBridge(catalog, journal, paper_enabled=True)
    bridge.attach(descriptor, approved_sha256=pinned(descriptor),
                          instruments=frozenset({INST}),
                          session_policy=session())
    sandbox = FixedCustomSandbox(tmp_path / "sandbox", catalog=catalog,
                                 contract=contract)
    yield catalog, contract, auth, auth, pub, op, bridge, sandbox, journal
    sandbox.close()
    journal.close()
    auth.close()


def admit(ctx, envelope, *, now=NOW):
    cat, contract, auth, _, _, _, _, _, _ = ctx
    return auth.admit(envelope, catalog=cat, contract=contract,
                      installation_id=INSTALL, now=now)


def current(ctx, envelope, *, now=NOW, installation_id=INSTALL):
    cat, contract, auth, _, _, _, _, _, _ = ctx
    return auth.current(envelope, catalog=cat, contract=contract,
                        installation_id=installation_id, now=now)


def service(ctx, envelope):
    cat, contract, auth, _, _, _, _, sandbox, _ = ctx
    return AdmittedFixedCustomSession(
        auth, catalog=cat, contract=contract,
        sandbox=sandbox, installation_id=INSTALL,
        signed_admission=envelope)


def test_a24_independent_double_signatures_metadata_admission_and_expiry(ctx):
    envelope = signed(ctx)
    with pytest.raises(PublisherAdmissionRefused, match="NOT_ADMITTED"):
        current(ctx, envelope)
    receipt = admit(ctx, envelope)
    assert receipt.state == "SIGNED_METADATA_ADMITTED_NO_INSTALL"
    assert receipt.sequence == 1 and receipt.revision == 1
    assert not receipt.executable_installed
    assert not receipt.private_engine_loaded
    assert not receipt.live_trading_permitted
    assert not receipt.commercial_license_issued
    assert current(ctx, envelope) == receipt
    with pytest.raises(PublisherAdmissionRefused, match="EXPIRED"):
        current(ctx, envelope, now=NOW+300)
    with pytest.raises(PublisherAdmissionRefused, match="EXPIRED"):
        current(ctx, envelope, now=NOW-11)


def test_a24_signatures_cannot_be_exchanged_or_self_approved(ctx):
    wrong_pub = signed(ctx, publisher_signer=Ed25519PrivateKey.generate())
    with pytest.raises(PublisherAdmissionRefused, match="INVALID_ED25519"):
        admit(ctx, wrong_pub)
    wrong_op = signed(ctx, operator_signer=Ed25519PrivateKey.generate())
    with pytest.raises(PublisherAdmissionRefused, match="INVALID_ED25519"):
        admit(ctx, wrong_op)
    with pytest.raises(PublisherAdmissionRefused, match="INVALID_ED25519"):
        admit(ctx, signed(ctx, publisher_signer=ctx[5], operator_signer=ctx[4]))


@pytest.mark.parametrize("changes", [
    {"engine_id": "another_demo"},
    {"engine_version": "2.0.0"},
    {"publisher": "other.vendor"},
    {"publisher_key_id": "other_publisher"},
    {"installation_id": "another_installation"},
    {"descriptor_sha256": "0" * 64},
])
def test_a24_signatures_correct_but_wrong_identity_or_installation_fail(ctx, changes):
    with pytest.raises(PublisherAdmissionRefused):
        admit(ctx, signed(ctx, **changes))


@pytest.mark.parametrize("changes", [
    {"permissions": ["live_trading"]},
    {"execution_kind": "arbitrary_python_code"},
    {"artifact_policy": "encrypted_plugin_download"},
    {"artifact_policy": "public_zip"},
    {"runtime_mode": "production"},
    {"kind": "private_nyfr_core"},
    {"sequence": 0},
    {"sequence": True},
    {"issued_at": 0},
    {"issued_at": NOW + 100},
    {"expires_at": NOW - 1},
    {"expires_at": NOW + 86410},
    {"schema_version": 2},
    {"schema_version": True},
])
def test_a24_forbidden_private_code_binary_live_or_bad_window(ctx, changes):
    with pytest.raises(PublisherAdmissionRefused):
        admit(ctx, signed(ctx, **changes))


@pytest.mark.parametrize("extra", [
    {"artifact_url": "https://example.invalid/nypayload.enc"},
    {"encrypted_payload_b64": "AAAA"},
    {"zip_path": "../../private.zip"},
    {"plugin_entrypoint": "python:private"},
    {"license_server": "https://lic.example"},
    {"signature_of_installer": "fake"},
])
def test_a24_no_new_artifact_fields_or_executable_download(ctx, extra):
    with pytest.raises(PublisherAdmissionRefused, match="EXACT_CLAIM_FIELDS"):
        admit(ctx, signed(ctx, **extra))


def test_a24_tampering_and_noncanonical_envelopes_fail(ctx):
    good = signed(ctx)
    altered = json.loads(good)
    altered["claim"]["sequence"] = 999
    with pytest.raises(PublisherAdmissionRefused, match="INVALID_ED25519"):
        admit(ctx, canonical(altered))
    with pytest.raises(PublisherAdmissionRefused, match="CANONICAL"):
        admit(ctx, json.dumps(json.loads(good), indent=1).encode())
    with pytest.raises(PublisherAdmissionRefused, match="DUPLICATE"):
        admit(ctx, b'{"claim":{},"claim":{},"operator_signature_b64":"","publisher_signature_b64":""}')
    with pytest.raises(PublisherAdmissionRefused):
        admit(ctx, b"PK\x03\x04" + b"\x00" * 40)
    with pytest.raises(PublisherAdmissionRefused):
        admit(ctx, good + b"padding")


def test_a24_monotonic_sequence_and_replay_cross_install_rejected(ctx):
    first = signed(ctx, seq=1)
    admit(ctx, first)
    with pytest.raises(PublisherAdmissionRefused, match="REPLAY_SEQUENCE"):
        admit(ctx, first)
    next_ = signed(ctx, seq=3)
    updated = admit(ctx, next_)
    assert updated.revision == 2 and updated.sequence == 3
    with pytest.raises(PublisherAdmissionRefused, match="STALE_PROOF"):
        current(ctx, first)
    with pytest.raises(PublisherAdmissionRefused, match="REPLAY_SEQUENCE"):
        admit(ctx, signed(ctx, seq=2))
    with pytest.raises(PublisherAdmissionRefused, match="INSTALLATION_OR_CONTRACT"):
        current(ctx, next_, installation_id="public_ci_fixture_two")
    assert current(ctx, next_).sequence == 3


def test_a24_independently_pinned_publisher_key_and_immutable_operator(ctx):
    cat, contract, auth, _, pub, op, _, _, _ = ctx
    with pytest.raises(PublisherAdmissionRefused, match="INDEPENDENT_PUBLISHER_KEY_PIN"):
        auth.register_publisher(contract.publisher, PUBLISHER_KEY_ID,
                                public(pub), approved_key_sha256="0" * 64)
    with pytest.raises(PublisherAdmissionRefused, match="INDEPENDENT_PUBLISHER_KEY_PIN"):
        auth.register_publisher(contract.publisher, PUBLISHER_KEY_ID,
                                public(op), approved_key_sha256=pinned(public(op)))
    with pytest.raises(PublisherAdmissionRefused, match="PUBLISHER_LOCKED"):
        newkey = Ed25519PrivateKey.generate()
        auth.register_publisher(contract.publisher, PUBLISHER_KEY_ID,
                                public(newkey), approved_key_sha256=pinned(public(newkey)))
    with pytest.raises(PublisherAdmissionRefused, match="INDEPENDENT_OPERATOR_KEY_PIN"):
        PublisherAdmissionAuthority(
            auth._db.execute("PRAGMA database_list").fetchone()[2],
            operator_public_key=public(op), approved_operator_key_sha256="0" * 64)


def test_a24_local_ledger_persists_independently_without_key_loss(ctx):
    cat, contract, auth, _, pub, op, _, _, _ = ctx
    envelope = signed(ctx)
    admit(ctx, envelope)
    db = auth._db.execute("PRAGMA database_list").fetchone()[2]
    recovered = PublisherAdmissionAuthority(
        db, operator_public_key=public(op),
        approved_operator_key_sha256=pinned(public(op)))
    try:
        assert recovered.current(envelope, catalog=cat, contract=contract,
                                 installation_id=INSTALL, now=NOW).sequence == 1
        with pytest.raises(PublisherAdmissionRefused, match="REPLAY_SEQUENCE"):
            recovered.admit(envelope, catalog=cat, contract=contract,
                            installation_id=INSTALL, now=NOW)
        with pytest.raises(PublisherAdmissionRefused, match="OPERATOR_PIN_CHANGED"):
            other = Ed25519PrivateKey.generate()
            PublisherAdmissionAuthority(
                db, operator_public_key=public(other),
                approved_operator_key_sha256=pinned(public(other)))
    finally:
        recovered.close()


def test_a24_revoking_publisher_or_installation_does_not_enable_any_plugin(ctx):
    envelope = signed(ctx)
    admit(ctx, envelope)
    ctx[2].revoke_installation(INSTALL, "custom_demo")
    with pytest.raises(PublisherAdmissionRefused, match="STALE_PROOF"):
        current(ctx, envelope)
    with pytest.raises(PublisherAdmissionRefused, match="REPLAY_SEQUENCE"):
        admit(ctx, signed(ctx, seq=2))
    assert ctx[7].status().state == "NEW"


def test_a24_publisher_revocation_does_not_recover_by_re_registration(ctx):
    envelope = signed(ctx)
    admit(ctx, envelope)
    ctx[2].revoke_publisher("community.vendor")
    with pytest.raises(PublisherAdmissionRefused, match="REVOKED_PUBLISHER"):
        current(ctx, envelope)
    with pytest.raises(PublisherAdmissionRefused, match="PUBLISHER_LOCKED"):
        ctx[2].register_publisher(
            "community.vendor", PUBLISHER_KEY_ID, public(ctx[4]),
            approved_key_sha256=pinned(public(ctx[4])))


def test_a24_nyfr_owner_and_private_commercial_claims_have_no_public_admission(ctx, tmp_path):
    cat, _, auth, _, pub, op, bridge, _, _ = ctx
    for ident, policy, family in (
        ("ny_first_reversal", "owner_only", "ny_first_reversal"),
        ("private_owner", "owner_only", "generic_custom"),
        ("commercial_candidate", "commercial_candidate", "generic_custom"),
    ):
        raw = metadata(ident, access_policy=policy, family=family)
        contract = cat.register(raw, approved_sha256=pinned(raw))
        claim = json.loads(signed(ctx))["claim"]
        claim.update({
            "engine_id": ident, "publisher": contract.publisher,
            "descriptor_sha256": contract.approved_descriptor_sha256})
        ps = base64.b64encode(pub.sign(PUBLISHER_DOMAIN + canonical(claim))).decode()
        sg = canonical({"claim": claim, "publisher_signature_b64": ps})
        envelope = canonical({"claim": claim, "publisher_signature_b64": ps,
                              "operator_signature_b64": base64.b64encode(
                                  op.sign(OPERATOR_DOMAIN + sg)).decode()})
        with pytest.raises(PublisherAdmissionRefused, match="OWNER_PRIVATE"):
            auth.admit(envelope, catalog=cat, contract=contract,
                       installation_id=INSTALL, now=NOW)
        assert cat.public_lookup(ident) is None


@pytest.mark.asyncio
async def test_a24_real_linux_a23_signed_admission_start_paper_dispatch_and_revocation(ctx):
    _, contract, auth, _, _, _, bridge, sandbox, journal = ctx
    envelope = signed(ctx)
    with pytest.raises(PublisherAdmissionRefused, match="NOT_ADMITTED"):
        service(ctx, envelope).launch(now=NOW)
    receipt = admit(ctx, envelope)
    assert receipt.state == "SIGNED_METADATA_ADMITTED_NO_INSTALL"
    guarded = service(ctx, envelope)
    assert guarded.launch(now=NOW).scope_verified
    revision = bridge.enable_paper(
        "custom_demo", approved_sha256=contract.approved_descriptor_sha256,
        expected_revision=1).revision
    tick = quote()
    result = await guarded.dispatch(bridge, sample(), tick=tick,
                                    expected_revision=revision, now=NOW)
    assert result.stored == 1
    assert journal.count() == 1
    assert guarded.heartbeat(now=NOW).scope_verified
    auth.revoke_publisher(contract.publisher)
    with pytest.raises(PublisherAdmissionRefused, match="REVOKED_PUBLISHER"):
        guarded.heartbeat(now=NOW)
    assert sandbox.status().state == "STOPPED"
    assert journal.count() == 1


@pytest.mark.asyncio
async def test_a24_revocation_while_relay_awaited_blocks_paper_journal(ctx):
    _, contract, auth, _, _, _, bridge, sandbox, journal = ctx
    envelope = signed(ctx)
    admit(ctx, envelope)
    guarded = service(ctx, envelope)
    guarded.launch(now=NOW)
    bridge.enable_paper("custom_demo", approved_sha256=contract.approved_descriptor_sha256,
                        expected_revision=1)
    entered, release = threading.Event(), threading.Event()
    real = sandbox.relay

    def pause(packet, *, tick):
        entered.set()
        if not release.wait(2):
            raise ValueError("A24_RACE_TIMEOUT")
        return real(packet, tick=tick)

    sandbox.relay = pause
    tick = quote()
    pending = asyncio.create_task(guarded.dispatch(
        bridge, sample(), tick=tick, expected_revision=2, now=NOW))
    assert await asyncio.wait_for(asyncio.to_thread(entered.wait, 2), 3)
    auth.revoke_installation(INSTALL, "custom_demo")
    release.set()
    with pytest.raises(PublisherAdmissionRefused, match="STALE_PROOF"):
        await asyncio.wait_for(pending, 4)
    assert journal.count() == 0
    assert sandbox.status().state == "STOPPED"


def test_a24_missing_signature_dependency_and_host_paths_are_fail_closed(tmp_path):
    operator = Ed25519PrivateKey.generate()
    with pytest.raises(PublisherAdmissionRefused, match="SEPARATE_DISPOSABLE"):
        PublisherAdmissionAuthority(
            "/etc/mmt-a24-trust.db", operator_public_key=public(operator),
            approved_operator_key_sha256=pinned(public(operator)))
    with pytest.raises(PublisherAdmissionRefused, match="SEPARATE_DISPOSABLE"):
        PublisherAdmissionAuthority(
            tmp_path / "missing" / "a24.db",
            operator_public_key=public(operator),
            approved_operator_key_sha256=pinned(public(operator)))


def test_a24_no_private_signing_key_or_runtime_installer_imported():
    import ast
    from pathlib import Path
    source = (Path(__file__).resolve().parents[2] /
              "naseri_markets/a24_publisher_admission.py").read_text()
    tree = ast.parse(source)
    forbidden = {"requests", "httpx", "aiohttp", "urllib", "socket",
                 "subprocess", "runpy", "importlib", "zipfile", "pickle"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(part.name.split(".")[0] not in forbidden for part in node.names)
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in forbidden
    assert "Ed25519PrivateKey" not in source
    assert "shell=True" not in source
    assert "production_source" not in source
    assert "private_nyfr_core" not in source
    assert "r0_engine" not in source
