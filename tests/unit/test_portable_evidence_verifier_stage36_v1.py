"""Stage36 standalone cryptographic verification from exported canonical bytes.

No database is needed by the verifier. Synthetic Stage34 data is NEVER proof
of a real physical disposable host.
"""
from __future__ import annotations

import base64
import hashlib
import json

import pytest

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from naseri_markets.a24_publisher_admission import canonical
from naseri_markets.portable_evidence_verifier_stage36_v1 import (
    OfflineBundleVerdict, Stage36Refused,
    export_signed_offline_bundle, verify_signed_offline_bundle,
)
from test_self_observation_evidence_chain_stage35_v1 import (
    chain, signed_binding,  # noqa: F401
)
from test_disconnected_host_evidence_stage33_v1 import (
    claim, prepared, research_only,  # noqa: F401
)
from test_disposable_host_preflight_stage32_v1 import (
    fixture_and_policy, dossier,  # noqa: F401
)
from test_tls_boundary_stage31_v1 import tls_material  # noqa: F401

HOST = "disposable_staging_one"
NODE = "pinned-disposable-node"


@pytest.fixture
def exported(chain):  # noqa: F811
    worker, prior_stage, auditor, _prep, now, receipt = chain
    stage35_signature = signed_binding(chain)
    worker.record(
        stage34_probe=receipt.evidence_json(),
        signed_binding=stage35_signature, expected_nodename=NODE,
        now=now, operator_ack=True)
    archive = export_signed_offline_bundle(
        worker, host_alias=HOST, sequence=1, operator_ack=True)
    reviewer_public = prior_stage[-1].reviewer_public_key
    auditor_public = auditor.public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw)
    kwargs = {
        "reviewer_public_key": reviewer_public,
        "reviewer_key_sha256": hashlib.sha256(reviewer_public).hexdigest(),
        "auditor_public_key": auditor_public,
        "auditor_key_sha256": hashlib.sha256(auditor_public).hexdigest(),
        "expected_host_alias": HOST, "expected_nodename": NODE,
        "pinned_stage35_sha256": hashlib.sha256(stage35_signature).hexdigest(),
        "pinned_stage35_sequence": 1,
        "now": now, "operator_ack": True,
    }
    return worker, archive, kwargs


def test_offline_verification_without_database_or_real_host(exported):
    worker, archive, keys = exported
    # Destroy the *connection* after exporting, not the private ledger.
    # Off-machine verifier needs only bytes and independent external pins.
    worker.db.close()
    verdict = verify_signed_offline_bundle(archive, **keys)
    assert isinstance(verdict, OfflineBundleVerdict)
    assert verdict.sequence == 1
    assert verdict.pinned_stage35_sha256 == keys["pinned_stage35_sha256"]
    assert verdict.state == "INDEPENDENT_SIGNATURE_AND_HASH_CUSTODY_VERIFIED_ONLY"
    for field in (
        "original_probe_origin_authenticated",
        "actual_host_independently_attested", "live_firewall_verified",
        "gvisor_isolation_certified", "public_api_deployment_authorized",
        "third_party_plugin_execution_authorized",
        "telegram_send_authorized", "broker_order_authorized",
    ):
        assert getattr(verdict, field) is False
    parts = json.loads(archive)
    assert parts["schema"] == 1
    assert set(parts) == {
        "schema", "kind", "host_alias", "stage35_sequence",
        "stage32_signed_b64", "stage33_signed_b64",
        "stage34_probe_b64", "stage35_signed_b64",
    }


@pytest.mark.parametrize("mutation", [
    {"expected_host_alias":"different_host"},
    {"expected_nodename":"another-disposable"},
    {"pinned_stage35_sequence":2},
    {"pinned_stage35_sha256":"0"*64},
    {"reviewer_key_sha256":"0"*64},
    {"auditor_key_sha256":"0"*64},
    {"now":True},
    {"operator_ack":False},
])
def test_external_anchor_host_time_and_operator_mismatch_denied(exported, mutation):
    _, archive, keys = exported
    with pytest.raises(Stage36Refused):
        verify_signed_offline_bundle(archive, **{**keys, **mutation})


def test_independent_wrong_reviewer_auditor_and_same_key_denied(exported):
    _, archive, keys = exported
    outsider = Ed25519PrivateKey.generate().public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw)
    with pytest.raises(Stage36Refused):
        verify_signed_offline_bundle(archive, **{
            **keys,"reviewer_public_key":outsider,
            "reviewer_key_sha256":hashlib.sha256(outsider).hexdigest(),
        })
    with pytest.raises(Stage36Refused):
        verify_signed_offline_bundle(archive, **{
            **keys,"auditor_public_key":outsider,
            "auditor_key_sha256":hashlib.sha256(outsider).hexdigest(),
        })
    with pytest.raises(Stage36Refused, match="SEPARATE"):
        verify_signed_offline_bundle(archive, **{
            **keys,"auditor_public_key":keys["reviewer_public_key"],
            "auditor_key_sha256":keys["reviewer_key_sha256"],
        })


@pytest.mark.parametrize("member", [
    "stage32_signed_b64", "stage33_signed_b64",
    "stage34_probe_b64", "stage35_signed_b64",
])
def test_each_hashed_signed_member_is_verified(exported, member):
    _, archive, keys = exported
    obj = json.loads(archive)
    raw = base64.b64decode(obj[member])
    corrupted = bytearray(raw)
    corrupted[len(raw)//2] ^= 1
    obj[member] = base64.b64encode(corrupted).decode("ascii")
    with pytest.raises(Stage36Refused):
        verify_signed_offline_bundle(canonical(obj), **keys)


@pytest.mark.parametrize("field", [
    "stage32_signed_b64", "stage33_signed_b64",
    "stage34_probe_b64", "stage35_signed_b64",
])
def test_missing_or_invalid_canonical_base64_rejected(exported, field):
    _, archive, keys = exported
    obj = json.loads(archive)
    obj.pop(field)
    with pytest.raises(Stage36Refused):
        verify_signed_offline_bundle(canonical(obj), **keys)
    obj = json.loads(archive)
    obj[field] = "!!!"
    with pytest.raises(Stage36Refused):
        verify_signed_offline_bundle(canonical(obj), **keys)


def test_untrusted_json_outer_schema_duplicates_noncanonical_and_oversize(exported):
    _, archive, keys = exported
    wrong = {**json.loads(archive), "allow_public_trading":True}
    for bad in (
        canonical(wrong),
        archive+b" ",
        json.dumps(json.loads(archive), indent=2).encode("ascii"),
        archive.replace(b'{"host_alias":',
                        b'{"host_alias":"x","host_alias":',1),
        b"\xff", b"[]" , b"{" + b"x"*40000 + b"}",
    ):
        with pytest.raises(Stage36Refused):
            verify_signed_offline_bundle(bad, **keys)


def test_exporter_requires_existing_signed_row_and_restricted_env(chain,monkeypatch):  # noqa: F811
    worker, *_ = chain
    with pytest.raises(Stage36Refused, match="NOT_FOUND"):
        export_signed_offline_bundle(
            worker,host_alias=HOST,sequence=1,operator_ack=True)
    with pytest.raises(Stage36Refused):
        export_signed_offline_bundle(
            worker,host_alias=HOST,sequence=True,operator_ack=True)
    monkeypatch.setenv("MMT_PRODUCTION","1")
    with pytest.raises(Stage36Refused, match="NONPRODUCTION"):
        export_signed_offline_bundle(
            worker,host_alias=HOST,sequence=1,operator_ack=True)


def test_archive_member_size_and_stored_db_tamper_fail_closed(exported):
    worker, archive, keys = exported
    obj = json.loads(archive)
    obj["stage34_probe_b64"] = base64.b64encode(b"x"*4097).decode()
    with pytest.raises(Stage36Refused):
        verify_signed_offline_bundle(canonical(obj), **keys)
    worker.db.execute("DROP TRIGGER stage35_no_update")
    worker.db.execute(
        "UPDATE stage35_self_observation_bindings SET probe_bytes=?",
        (b'{"forged":true}',))
    with pytest.raises(Stage36Refused, match="ALTERED"):
        export_signed_offline_bundle(
            worker,host_alias=HOST,sequence=1,operator_ack=True)


def test_time_windows_and_strong_independent_checkpoint_reject_old_export(exported):
    worker, archive, keys = exported
    with pytest.raises(Stage36Refused):
        verify_signed_offline_bundle(archive, **{
            **keys, "now":keys["now"]+1200})
    with pytest.raises(Stage36Refused):
        verify_signed_offline_bundle(archive, **{
            **keys, "now":keys["now"]-1000})
    # "A previous signed record" is indistinguishable from latest
    # without an independently maintained digest+sequence checkpoint.
    with pytest.raises(Stage36Refused):
        verify_signed_offline_bundle(archive, **{
            **keys, "pinned_stage35_sequence":3,
            "pinned_stage35_sha256":"f"*64})


def test_exporter_never_contains_certificate_private_key_or_local_file_paths(exported):
    _, archive, keys = exported
    assert b"PRIVATE KEY" not in archive
    assert b"/proc" not in archive
    assert b"test-ca.pem" not in archive
    assert b"/operator-private/" not in archive
    valid = verify_signed_offline_bundle(archive, **keys)
    assert not valid.original_probe_origin_authenticated
