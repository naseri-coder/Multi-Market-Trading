"""A25 strict Custom inert package, publisher supply-chain and lifecycle tests."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import stat
import zipfile

import pytest

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from naseri_markets.a25_bundle_admission import (
    A25GuardedFixedFixture, BundleAdmissionRefused, InertBundleAdmissionGate,
    OPERATOR_DOMAIN, PUBLISHER_DOMAIN, canonical, inspect_inert_bundle,
)
from naseri_markets.a24_publisher_admission import PublisherAdmissionRefused
from test_a24_publisher_admission import (
    INSTALL, NOW, PUBLISHER_KEY_ID, admit as admit_a24, ctx as a24_ctx,
    service, signed as signed_a24,
)
from test_a22_custom_bridge import sample
from test_a7_replay_pipeline import quote


def pack(contract, *, manifest_changes=None, payload_changes=None,
         members=None, compression=zipfile.ZIP_STORED, mode=None,
         json_override=None):
    payload = {
        "schema_version": 1, "kind": "synthetic_no_signal_data",
        "engine_id": contract.engine_id, "engine_version": contract.engine_version,
        "behavior": "no_signal",
    }
    payload.update(payload_changes or {})
    payload_raw = canonical(payload)
    manifest = {
        "schema_version": 1, "kind": "public_custom_inert_bundle",
        "engine_id": contract.engine_id, "engine_version": contract.engine_version,
        "publisher": contract.publisher,
        "descriptor_sha256": contract.approved_descriptor_sha256,
        "package_version": contract.engine_version,
        "payload_sha256": hashlib.sha256(payload_raw).hexdigest(),
        "abi_version": 1,
        "artifact_policy": "data_only_no_executable_or_ciphertext",
        "distribution": "ephemeral_ci_rehearsal",
    }
    manifest.update(manifest_changes or {})
    payloads = members if members is not None else [
        ("manifest.json", json_override if json_override is not None else canonical(manifest)),
        ("payload.json", payload_raw),
    ]
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=compression) as z:
        for name, content in payloads:
            if mode is not None:
                entry = zipfile.ZipInfo(name)
                entry.external_attr = (mode << 16)
                entry.compress_type = compression
                z.writestr(entry, content)
            else:
                z.writestr(name, content)
    return stream.getvalue()


def release(ctx, *, a24=None, package=None, sequence=1, pub_key=None,
            op_key=None, **changes):
    cat, contract, _, _, pub, op, _, _, _ = ctx
    a24 = a24 if a24 is not None else signed_a24(ctx)
    package = package if package is not None else pack(contract)
    proof = inspect_inert_bundle(
        package, approved_sha256=hashlib.sha256(package).hexdigest(),
        contract=contract)
    claim = {
        "schema_version": 1, "kind": "public_custom_inert_bundle",
        "engine_id": contract.engine_id, "engine_version": contract.engine_version,
        "publisher": contract.publisher, "publisher_key_id": PUBLISHER_KEY_ID,
        "installation_id": INSTALL,
        "descriptor_sha256": contract.approved_descriptor_sha256,
        "admission_sha256": hashlib.sha256(a24).hexdigest(),
        "bundle_sha256": proof.bundle_sha256,
        "payload_sha256": proof.payload_sha256,
        "package_version": contract.engine_version, "bundle_sequence": sequence,
        "issued_at": NOW - 10, "expires_at": NOW + 300,
        "capabilities": ["inert_paper_data_only"],
        "artifact_policy": "no_executable_or_ciphertext",
    }
    claim.update(changes)
    publisher = pub_key or pub
    operator = op_key or op
    psig = base64.b64encode(publisher.sign(
        PUBLISHER_DOMAIN + canonical(claim))).decode("ascii")
    isig = base64.b64encode(operator.sign(
        OPERATOR_DOMAIN + canonical({"claim": claim,
                                     "publisher_signature_b64": psig}))).decode("ascii")
    return canonical({"claim": claim, "publisher_signature_b64": psig,
                      "operator_signature_b64": isig})


@pytest.fixture
def case(a24_ctx, tmp_path):
    ctx = a24_ctx
    package = pack(ctx[1])
    a24 = signed_a24(ctx)
    admission = admit_a24(ctx, a24)
    assert admission.state == "SIGNED_METADATA_ADMITTED_NO_INSTALL"
    gate = InertBundleAdmissionGate(tmp_path / "a25_floor.db", authority=ctx[2])
    yield ctx, gate, package, a24
    gate.close()


def args(case, *, signed=None, package=None, admission=None):
    ctx, _, default_package, a24 = case
    return {
        "catalog": ctx[0], "contract": ctx[1], "installation_id": INSTALL,
        "now": NOW,
        "package": package if package is not None else default_package,
        "release": signed if signed is not None else release(
            ctx, package=package if package is not None else default_package,
            a24=admission if admission is not None else a24),
        "a24_envelope": admission if admission is not None else a24,
    }


def signed_case(case, **changes):
    return release(case[0], package=case[2], a24=case[3], **changes)

def test_a25_two_stored_json_members_strict_bundle_without_install(case):
    ctx, gate, package, _ = case
    proof = inspect_inert_bundle(
        package, approved_sha256=hashlib.sha256(package).hexdigest(),
        contract=ctx[1])
    assert proof.safe_data_only and not proof.encrypted_payload
    assert not proof.executable_payload and not proof.private_nyfr_included
    assert proof.engine_id == "custom_demo"
    with pytest.raises(BundleAdmissionRefused, match="UNADMITTED"):
        gate.current(**args(case))
    result = gate.admit(**args(case))
    assert result.state == "SIGNED_INERT_BUNDLE_ADMITTED_NO_INSTALL"
    assert result.bundle_sequence == 1 and result.revision == 1
    assert not result.executable_installed and not result.strategy_code_executed
    assert not result.live_trading_permitted and not result.private_nyfr_included
    assert gate.current(**args(case)) == result


def test_a25_signature_composition_rejects_wrong_publisher_operator_and_swaps(case):
    ctx, gate, _, _ = case
    for pub_key, op_key in [
        (Ed25519PrivateKey.generate(), None),
        (None, Ed25519PrivateKey.generate()),
        (ctx[5], ctx[4]),
    ]:
        signed = signed_case(case, pub_key=pub_key, op_key=op_key)
        with pytest.raises(PublisherAdmissionRefused, match="INVALID_ED25519"):
            gate.admit(**args(case, signed=signed))


@pytest.mark.parametrize("changes", [
    {"engine_id": "another_demo"},
    {"engine_version": "9.0.0"},
    {"publisher": "forged.vendor"},
    {"publisher_key_id": "forged_key"},
    {"installation_id": "another_installation"},
    {"descriptor_sha256": "0" * 64},
    {"admission_sha256": "0" * 64},
    {"bundle_sha256": "0" * 64},
    {"payload_sha256": "0" * 64},
    {"package_version": "9.0.0"},
])
def test_a25_signed_supply_chain_identity_binding_cannot_be_changed(case, changes):
    ctx, gate, _, _ = case
    signed = signed_case(case, **changes)
    with pytest.raises(PublisherAdmissionRefused):
        gate.admit(**args(case, signed=signed))


@pytest.mark.parametrize("changes", [
    {"artifact_policy": "encrypted_plugin"},
    {"artifact_policy": "installable_binary"},
    {"capabilities": ["run_python"]},
    {"capabilities": ["live_trading"]},
    {"kind": "owner_ny_first_reversal"},
    {"bundle_sequence": 0},
    {"bundle_sequence": True},
    {"schema_version": 2},
    {"issued_at": NOW+100},
    {"expires_at": NOW-2},
    {"expires_at": NOW+86410},
    {"installer_url": "https://example.invalid/private.aged"},
    {"source_code": "danger"},
])
def test_a25_signed_envelope_cannot_authorize_executable_or_expired_release(case, changes):
    ctx, gate, _, _ = case
    signed = signed_case(case, **changes)
    with pytest.raises(PublisherAdmissionRefused):
        gate.admit(**args(case, signed=signed))


@pytest.mark.parametrize("members", [
    [("manifest.json", b"{}"), ("payload.bin", b"MZprogram")],
    [("../manifest.json", b"{}"), ("payload.json", b"{}")],
    [("manifest.json", b"{}"), ("manifest.json", b"{}")],
    [("manifest.json", b"{}"), ("payload.json", b"{}"), ("main.py", b"print(1)")],
    [("manifest.json", b"{}"), ("payload.enc", b"encrypted")],
    [("manifest.json", b"{}"), ("payload.json", b"{}"), ("nyfr.so", b"ELF")],
    [("manifest.json/", b"{}"), ("payload.json", b"{}")],
])
def test_a25_zip_slip_duplicate_symlink_or_unapproved_artifact_names_rejected(
        case, members):
    ctx, _, _, _ = case
    raw = pack(ctx[1], members=members)
    with pytest.raises(BundleAdmissionRefused):
        inspect_inert_bundle(raw, approved_sha256=hashlib.sha256(raw).hexdigest(),
                             contract=ctx[1])


@pytest.mark.parametrize("mode", [
    stat.S_IFLNK | 0o777,
    stat.S_IFREG | 0o755,
    stat.S_IFREG | 0o700,
])
def test_a25_executable_permissions_and_symlinks_rejected(case, mode):
    ctx, _, _, _ = case
    data = pack(ctx[1], mode=mode)
    with pytest.raises(BundleAdmissionRefused, match="UNSAFE_ZIP_ENTRY"):
        inspect_inert_bundle(data, approved_sha256=hashlib.sha256(data).hexdigest(),
                             contract=ctx[1])


def test_a25_compressed_payload_rejected_even_if_small(case):
    ctx, _, _, _ = case
    data = pack(ctx[1], compression=zipfile.ZIP_DEFLATED)
    with pytest.raises(BundleAdmissionRefused, match="UNSAFE_ZIP_ENTRY"):
        inspect_inert_bundle(data, approved_sha256=hashlib.sha256(data).hexdigest(),
                             contract=ctx[1])


@pytest.mark.parametrize("manifest_changes", [
    {"engine_id": "ny_first_reversal"},
    {"engine_version": "2.0.0"},
    {"publisher": "nyfr.private"},
    {"descriptor_sha256": "0"*64},
    {"package_version": "2.0.0"},
    {"abi_version": 2},
    {"abi_version": True},
    {"artifact_policy": "encrypted_payload"},
    {"distribution": "public_binary"},
    {"entrypoint": "python strategy.py"},
])
def test_a25_manifest_must_match_public_contract_and_fixed_runtime(
        case, manifest_changes):
    ctx, _, _, _ = case
    data = pack(ctx[1], manifest_changes=manifest_changes)
    with pytest.raises(BundleAdmissionRefused):
        inspect_inert_bundle(data, approved_sha256=hashlib.sha256(data).hexdigest(),
                             contract=ctx[1])


@pytest.mark.parametrize("payload_changes", [
    {"behavior": "place_orders"},
    {"behavior": "network_connect"},
    {"kind": "encrypted_custom_code"},
    {"engine_id": "private_nyfr_core"},
    {"schema_version": True},
    {"entrypoint": "py"},
    {"secret": "sensitive"},
])
def test_a25_payload_always_inert_and_never_an_installer(case, payload_changes):
    ctx, _, _, _ = case
    raw = pack(ctx[1], payload_changes=payload_changes)
    with pytest.raises(BundleAdmissionRefused):
        inspect_inert_bundle(raw, approved_sha256=hashlib.sha256(raw).hexdigest(),
                             contract=ctx[1])


def test_a25_sha256_is_not_publisher_signature_or_operator_entitlement(case):
    ctx, gate, package, _ = case
    with pytest.raises(BundleAdmissionRefused, match="INDEPENDENT_BUNDLE_PIN"):
        inspect_inert_bundle(package, approved_sha256="0"*64, contract=ctx[1])
    proof = inspect_inert_bundle(package,
                                approved_sha256=hashlib.sha256(package).hexdigest(),
                                contract=ctx[1])
    assert proof.safe_data_only
    with pytest.raises(BundleAdmissionRefused, match="UNADMITTED"):
        gate.current(**args(case))


def test_a25_tampered_release_and_bundle_rejected_even_when_metadata_signed(case):
    ctx, gate, package, _ = case
    true_release = release(ctx)
    forged = json.loads(true_release)
    forged["claim"]["bundle_sequence"] = 999
    with pytest.raises(PublisherAdmissionRefused, match="INVALID_ED25519"):
        gate.admit(**args(case, signed=canonical(forged)))
    with pytest.raises(BundleAdmissionRefused):
        gate.admit(**args(case, package=package+b"x", signed=true_release))


def test_a25_replay_floor_persists_and_monotonic_cross_restart(case, tmp_path):
    ctx, gate, _, _ = case
    first = gate.admit(**args(case))
    with pytest.raises(BundleAdmissionRefused, match="ROLLBACK"):
        gate.admit(**args(case))
    new_release = signed_case(case, sequence=2)
    second = gate.admit(**args(case, signed=new_release))
    assert second.revision == first.revision+1
    with pytest.raises(BundleAdmissionRefused, match="UNADMITTED"):
        gate.current(**args(case))
    with pytest.raises(BundleAdmissionRefused, match="ROLLBACK"):
        gate.admit(**args(case))
    independent = InertBundleAdmissionGate(tmp_path/"a25_floor.db", authority=ctx[2])
    try:
        assert independent.current(**args(case, signed=new_release)) == second
        with pytest.raises(BundleAdmissionRefused, match="ROLLBACK"):
            independent.admit(**args(case))
    finally:
        independent.close()


def test_a25_a24_revocation_cascades_and_a25_revocation_is_terminal(case):
    ctx, gate, _, _ = case
    gate.admit(**args(case))
    gate.revoke(INSTALL, "custom_demo")
    with pytest.raises(BundleAdmissionRefused, match="UNADMITTED"):
        gate.current(**args(case))
    with pytest.raises(BundleAdmissionRefused, match="ROLLBACK"):
        gate.admit(**args(case, signed=signed_case(case, sequence=2)))


def test_a25_revoked_publisher_and_expired_A24_proof_never_admitted(case):
    ctx, gate, _, _ = case
    gate.admit(**args(case))
    ctx[2].revoke_publisher(ctx[1].publisher)
    with pytest.raises(PublisherAdmissionRefused, match="REVOKED_PUBLISHER"):
        gate.current(**args(case))
    with pytest.raises(PublisherAdmissionRefused, match="REVOKED_PUBLISHER"):
        gate.admit(**args(case, signed=signed_case(case, sequence=2)))


def test_a25_rejects_all_owner_private_and_commercial_candidate_artifacts(case):
    ctx, _, _, _ = case
    from test_a22_custom_bridge import metadata, pinned
    for identity, policy, family in (
        ("ny_first_reversal", "owner_only", "ny_first_reversal"),
        ("owner_demo", "owner_only", "generic_custom"),
        ("commercial_demo", "commercial_candidate", "generic_custom"),
    ):
        blob = metadata(identity, access_policy=policy, family=family)
        private = ctx[0].register(blob, approved_sha256=pinned(blob))
        with pytest.raises(BundleAdmissionRefused, match="PRIVATE_AND_OWNER"):
            inspect_inert_bundle(b"PK\x03\x04", approved_sha256="0"*64,
                                 contract=private)


def test_a25_invalid_manifest_json_rejected_without_disk_extraction(case):
    ctx, _, _, _ = case
    for malformed in (
        b'{"schema_version":1,"schema_version":1}',
        b'{"value":NaN}', b'{"value":Infinity}', b'{"value":"\xff"}',
    ):
        bundle = pack(ctx[1], json_override=malformed)
        with pytest.raises(BundleAdmissionRefused):
            inspect_inert_bundle(bundle,
                                 approved_sha256=hashlib.sha256(bundle).hexdigest(),
                                 contract=ctx[1])


def test_a25_executable_package_never_entered_in_temp_directory(case, tmp_path):
    ctx, gate, _, _ = case
    before = {x.name for x in tmp_path.iterdir()}
    gate.admit(**args(case))
    after = {x.name for x in tmp_path.iterdir()}
    # The A24 authority fixture already owns a legitimate /authority
    # directory. A25 must introduce NO new directory or ZIP extraction.
    assert after == before
    assert not any(x.endswith((".so", ".pyc", ".zip", ".enc", ".bin"))
                   for x in after)


@pytest.mark.asyncio
async def test_a25_real_A23_fixed_paper_relay_requires_both_signatures_and_bundle(case):
    ctx, gate, _, a24 = case
    r = release(ctx)
    wrapper = A25GuardedFixedFixture(
        service(ctx, a24), gate=gate, package=pack(ctx[1]),
        release=r, a24_envelope=a24)
    with pytest.raises(BundleAdmissionRefused, match="UNADMITTED"):
        wrapper.launch(now=NOW)
    gate.admit(**args(case, signed=r))
    assert wrapper.launch(now=NOW).scope_verified
    bridge = ctx[6]
    revision = bridge.enable_paper(
        "custom_demo", approved_sha256=ctx[1].approved_descriptor_sha256,
        expected_revision=1).revision
    tick = quote()
    result = await wrapper.dispatch(bridge, sample(), tick=tick,
                                    expected_revision=revision, now=NOW)
    assert result.stored == 1 and ctx[8].count() == 1
    assert wrapper.heartbeat(now=NOW).scope_verified
    gate.revoke(INSTALL, "custom_demo")
    with pytest.raises(BundleAdmissionRefused, match="UNADMITTED"):
        wrapper.heartbeat(now=NOW)
    assert ctx[7].status().state == "STOPPED"


@pytest.mark.asyncio
async def test_a25_revocation_inflight_fixed_relay_fails_closed_before_journal(case):
    import asyncio
    import threading
    ctx, gate, _, a24 = case
    proof = release(ctx)
    gate.admit(**args(case, signed=proof))
    wrapped = A25GuardedFixedFixture(
        service(ctx, a24), gate=gate, package=pack(ctx[1]),
        release=proof, a24_envelope=a24)
    wrapped.launch(now=NOW)
    ctx[6].enable_paper(
        "custom_demo", approved_sha256=ctx[1].approved_descriptor_sha256,
        expected_revision=1)
    entered, proceed = threading.Event(), threading.Event()
    original = ctx[7].relay
    def paused(packet, *, tick):
        entered.set()
        if not proceed.wait(2):
            raise AssertionError("A25_RELAY_TIMED_OUT")
        return original(packet, tick=tick)
    ctx[7].relay = paused
    tick = quote()
    work = asyncio.create_task(wrapped.dispatch(
        ctx[6], sample(), tick=tick, expected_revision=2, now=NOW))
    assert await asyncio.wait_for(asyncio.to_thread(entered.wait, 2), 3)
    gate.revoke(INSTALL, "custom_demo")
    proceed.set()
    # Parent A24 accepts release before relay; final A25 recheck detects
    # revoked package, but downstream A22 could already have committed.
    with pytest.raises(BundleAdmissionRefused):
        await asyncio.wait_for(work, 4)
    assert ctx[7].status().state == "STOPPED"
