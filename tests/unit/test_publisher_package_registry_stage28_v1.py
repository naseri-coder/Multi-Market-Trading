"""Stage28 offline publisher identity, key lifecycle and bounded ZIP security."""
from __future__ import annotations

import hashlib
import io
import sqlite3
import stat
import zipfile

import pytest

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from naseri_markets.a24_publisher_admission import canonical
from naseri_markets.core_api_v1 import content_digest
from naseri_markets.durable_isolated_core_gate_stage22_v1 import (
    DurableIsolatedCoreGate, Stage22Refused,
)
from naseri_markets.publisher_package_registry_stage28_v1 import (
    PublisherPackageRegistry, Stage28Refused,
    _ENROLL_DOMAIN, _ROTATE_DOMAIN,
)
from test_durable_isolated_core_gate_stage22_v1 import host  # noqa: F401
from test_signed_core_candidate_stage23_v1 import (
    TENANT, PUB, KEY_ID, NOW, key_bytes, signed, trusted,  # noqa: F401
)
from test_secure_plugin_runtime_v1 import CORE, IMAGE, SOURCE, event

NONCE = "a"*32


def digest(data):
    return hashlib.sha256(data).hexdigest()


def enrollment_claim(pubkey, *, tenant=TENANT, pub=PUB, key=KEY_ID,
                     nonce=NONCE, at=NOW):
    return dict(tenant_id=tenant,publisher=pub,key_id=key,
                key_sha256=digest(pubkey),nonce=nonce,issued_at=at)


def zip_bytes(descriptor, source=SOURCE, *,
              compression=zipfile.ZIP_STORED, filenames=None):
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w") as stream:
        stream.writestr((filenames or ("source.py","descriptor.json"))[0],
                        source,compress_type=compression)
        stream.writestr((filenames or ("source.py","descriptor.json"))[1],
                        canonical(descriptor),compress_type=compression)
    return buf.getvalue()


def descriptor(payload, *, source=SOURCE, **changes):
    item=dict(schema=1,tenant_id=TENANT,publisher=PUB,
              publisher_key_id=KEY_ID,binding_id=event().binding.binding_id,
              source_sha256=digest(source),
              manifest_sha256=content_digest(CORE.manifest),
              binding_sha256=content_digest(event().binding),
              candidate_sha256=digest(payload),image=IMAGE)
    item.update(changes)
    return item


@pytest.fixture(autouse=True)
def safe_env(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


@pytest.fixture
def roster(tmp_path, host, trusted):  # noqa: F811
    witness,pub_signer,operator_signer,_=trusted
    signed_source=signed(trusted)
    assert witness.admit(signed_source,source=SOURCE,
                         manifest=CORE.manifest,binding=event().binding,
                         tenant_id=TENANT,publisher=PUB,
                         publisher_key_id=KEY_ID,image=IMAGE,now=NOW,
                         operator_ack=True).sequence == 1
    private=tmp_path/"quarantine"
    private.mkdir(mode=0o700)
    with DurableIsolatedCoreGate(
            tmp_path/"stage28.sqlite",host=host) as gate:
        registry=PublisherPackageRegistry(gate,private,operator_ack=True)
        pubkey=key_bytes(pub_signer)
        claim=enrollment_claim(pubkey)
        sig=pub_signer.sign(_ENROLL_DOMAIN+canonical(claim))
        assert registry.enroll(tenant_id=TENANT,publisher=PUB,key_id=KEY_ID,
                               public_key=pubkey,proof_signature=sig,
                               nonce=NONCE,issued_at=NOW,now=NOW,
                               operator_ack=True)["revision"] == 1
        yield registry,gate,witness,pub_signer,operator_signer,signed_source,private


def submit_args(roster):
    registry,gate,witness,_pub,_op,payload,_folder=roster
    archive=zip_bytes(descriptor(payload))
    return dict(tenant_id=TENANT,publisher=PUB,key_id=KEY_ID,
                stage23=witness,package=archive,signed_candidate=payload,
                manifest=CORE.manifest,binding=event().binding,
                expected_image=IMAGE,now=NOW,operator_ack=True)


def test_signed_source_submission_is_atomic_stage27_and_never_runs(roster,monkeypatch):
    registry,gate,*_=roster
    args=submit_args(roster)
    called=[]
    monkeypatch.setattr(gate.host,"evaluate",lambda *_a,**_k:called.append(True))
    receipt=registry.submit(**args)
    assert receipt.state=="QUARANTINED_PUBLIC_SOURCE_NOT_EXECUTABLE"
    assert not receipt.package_executed
    assert not receipt.public_install_authorized
    assert not receipt.telegram_publish_authorized
    assert not receipt.broker_order_authorized
    assert not receipt.developer_external_identity_verified
    assert len(receipt.package_sha256)==64
    assert gate.state(TENANT,"binding_a")["public_untrusted_intake_pending"]
    assert gate.state(TENANT,"binding_a")["state"]=="DISABLED"
    assert registry.inspect_submission(
        tenant_id=TENANT,binding_id="binding_a")["stage27_initial_lock"]
    assert len(registry.audit(tenant_id=TENANT,publisher=PUB))==2
    assert [x["action"] for x in registry.audit(tenant_id=TENANT,publisher=PUB)]==[
        "ENROLLED","SUBMITTED"]
    with pytest.raises(Stage22Refused,match="STAGE27_PUBLIC_UNTRUSTED"):
        gate.set_enabled(TENANT,"binding_a",enabled=True,
                         expected_revision=1,operator_ack=True)
    with pytest.raises(Stage22Refused,match="STAGE27_PUBLIC_UNTRUSTED"):
        gate.evaluate(TENANT,CORE.manifest,event(),source=SOURCE,operator_ack=True)
    assert not called
    with pytest.raises(sqlite3.IntegrityError,match="STAGE27_PUBLIC_ACTIVATION"):
        gate.db.execute("UPDATE secure22_bindings SET state='ENABLED' "
                        "WHERE binding_id='binding_a'")
    assert len(list(registry.quarantine_dir.iterdir()))==1
    archived=next(registry.quarantine_dir.iterdir())
    assert stat.S_IMODE(archived.stat().st_mode)==0o600
    assert archived.read_bytes()==args["package"]


def test_bad_descriptor_and_wrong_source_do_not_create_any_files(roster):
    registry,gate,*_=roster
    args=submit_args(roster)
    bad=[zip_bytes(descriptor(args["signed_candidate"],publisher="other.vendor")),
         zip_bytes(descriptor(args["signed_candidate"],source=b"modified"),b"modified"),
         zip_bytes(descriptor(args["signed_candidate"],unknown_field="x"))]
    for archive in bad:
        with pytest.raises(Stage28Refused):
            registry.submit(**{**args,"package":archive})
    assert not list(registry.quarantine_dir.iterdir())
    assert not gate.db.execute("SELECT 1 FROM secure22_bindings").fetchone()


@pytest.mark.parametrize("archive_factory",[
    lambda x: zip_bytes(x,filenames=("../evil.py","descriptor.json")),
    lambda x: zip_bytes(x,compression=zipfile.ZIP_DEFLATED),
    lambda x: zip_bytes(x)+b"TRAILER",
    lambda x: b"not a zip",
    lambda x: zip_bytes(x,source=b"x"*65537),
    lambda x: zip_bytes(x,source=b""),
])
def test_malicious_archives_are_rejected_without_extraction(roster,archive_factory):
    registry,gate,*_=roster
    args=submit_args(roster)
    with pytest.raises(Stage28Refused):
        registry.submit(**{**args,"package":archive_factory(descriptor(args["signed_candidate"]))})
    assert not gate.db.execute("SELECT 1 FROM secure22_bindings").fetchone()
    assert not list(registry.quarantine_dir.iterdir())


def test_symlink_member_and_duplicate_member_names_denied(roster):
    registry,gate,*_=roster
    args=submit_args(roster)
    meta=descriptor(args["signed_candidate"])
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w") as z:
        v=zipfile.ZipInfo("source.py")
        v.create_system=3
        v.external_attr=(stat.S_IFLNK|0o777)<<16
        z.writestr(v,b"../secrets")
        z.writestr("descriptor.json",canonical(meta))
    with pytest.raises(Stage28Refused,match="UNSUPPORTED_ARCHIVE_STRUCTURE"):
        registry.submit(**{**args,"package":buf.getvalue()})
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,"w") as z:
        z.writestr("source.py",SOURCE)
        z.writestr("source.py",SOURCE)
        z.writestr("descriptor.json",canonical(meta))
    with pytest.raises(Stage28Refused):
        registry.submit(**{**args,"package":buf.getvalue()})
    assert not gate.db.execute("SELECT 1 FROM secure22_bindings").fetchone()


def test_registry_onboarding_needs_cryptographic_key_ownership(
        tmp_path,host,monkeypatch):  # noqa: F811
    private=tmp_path/"private"
    private.mkdir(mode=0o700)
    with DurableIsolatedCoreGate(
            tmp_path/"stage28.sqlite",host=host) as gate:
        registry=PublisherPackageRegistry(gate,private,operator_ack=True)
        real=Ed25519PrivateKey.generate()
        forged=Ed25519PrivateKey.generate()
        pubkey=key_bytes(real)
        claim=enrollment_claim(pubkey)
        with pytest.raises(Stage28Refused,match="INVALID_PUBLISHER_PROOF"):
            registry.enroll(tenant_id=TENANT,publisher=PUB,key_id=KEY_ID,
                            public_key=pubkey,
                            proof_signature=forged.sign(_ENROLL_DOMAIN+canonical(claim)),
                            nonce=NONCE,issued_at=NOW,now=NOW,operator_ack=True)
        assert not gate.db.execute("SELECT 1 FROM secure28_publishers").fetchone()
        valid=real.sign(_ENROLL_DOMAIN+canonical(claim))
        with pytest.raises(Stage28Refused,match="SHORT_LIVED"):
            registry.enroll(tenant_id=TENANT,publisher=PUB,key_id=KEY_ID,
                            public_key=pubkey,proof_signature=valid,
                            nonce=NONCE,issued_at=NOW,now=NOW+301,operator_ack=True)
        with pytest.raises(Stage28Refused,match="EXPLICIT_NONPRODUCTION"):
            monkeypatch.setenv("MMT_PRODUCTION","1")
            registry.enroll(tenant_id=TENANT,publisher=PUB,key_id=KEY_ID,
                            public_key=pubkey,proof_signature=valid,
                            nonce=NONCE,issued_at=NOW,now=NOW,operator_ack=True)


def test_rotation_requires_old_and_new_key_signatures_and_cas(roster):
    registry,_gate,_witness,old,_op,_source,_folder=roster
    new=Ed25519PrivateKey.generate()
    pubkey=key_bytes(new)
    challenge=dict(tenant_id=TENANT,publisher=PUB,old_key_id=KEY_ID,
                   new_key_id="key_two",new_key_sha256=digest(pubkey),
                   revision=1,nonce=NONCE,issued_at=NOW)
    old_sig=old.sign(_ROTATE_DOMAIN+canonical(challenge))
    new_sig=new.sign(_ROTATE_DOMAIN+canonical(challenge))
    kwargs=dict(tenant_id=TENANT,publisher=PUB,old_key_id=KEY_ID,
                new_key_id="key_two",new_public_key=pubkey,
                old_signature=old_sig,new_signature=new_sig,
                expected_revision=1,nonce=NONCE,issued_at=NOW,now=NOW,
                operator_ack=True)
    with pytest.raises(Stage28Refused,match="INVALID_PUBLISHER_PROOF"):
        registry.rotate(**{**kwargs,"new_signature":old_sig})
    assert registry.status(TENANT,PUB)["revision"]==1
    updated=registry.rotate(**kwargs)
    assert updated["revision"]==2
    assert updated["active_key_id"]=="key_two"
    with pytest.raises(Stage28Refused,match="STALE_OR_REVOKED"):
        registry.rotate(**kwargs)
    # Stage23 still authenticates the *retired* key, but Stage28 refuses it.
    args=submit_args(roster)
    with pytest.raises(Stage28Refused,match="INACTIVE_OR_UNVERIFIED_PUBLISHER"):
        registry.submit(**args)
    assert len(list(registry.quarantine_dir.iterdir()))==0


def test_revoke_persists_and_disables_even_cryptographically_valid_source(roster):
    registry,gate,*_=roster
    assert registry.revoke(tenant_id=TENANT,publisher=PUB,key_id=KEY_ID,
                           expected_revision=1,now=NOW,operator_ack=True)[
                               "state"]=="BLOCKED"
    with pytest.raises(Stage28Refused,match="INACTIVE_OR_UNVERIFIED"):
        registry.submit(**submit_args(roster))
    assert not gate.db.execute("SELECT 1 FROM secure27_public_intake").fetchone()
    with pytest.raises(Stage28Refused,match="REVOKED_OR_STALE"):
        registry.revoke(tenant_id=TENANT,publisher=PUB,key_id=KEY_ID,
                        expected_revision=2,now=NOW,operator_ack=True)
    assert [v["action"] for v in registry.audit(tenant_id=TENANT,publisher=PUB)]==[
        "ENROLLED","REVOKED"]


def test_atomic_second_stage27_insert_failure_rolls_back_db_and_leaves_only_orphan(roster):
    registry,gate,*_=roster
    gate.db.execute("""CREATE TRIGGER reject_stage27 BEFORE INSERT ON secure27_public_intake
                 BEGIN SELECT RAISE(ABORT,'INTENTIONAL_TEST_INJECTED_FAILURE'); END""")
    with pytest.raises(Stage28Refused,match="QUARANTINED_INTAKE_REFUSED"):
        registry.submit(**submit_args(roster))
    assert not gate.db.execute("SELECT 1 FROM secure22_bindings").fetchone()
    assert not gate.db.execute("SELECT 1 FROM secure28_submissions").fetchone()
    assert len(registry.audit(tenant_id=TENANT,publisher=PUB))==1
    # Only a 0600 orphan may remain; no code path loads or executes it.
    artifacts=list(registry.quarantine_dir.iterdir())
    assert len(artifacts)==1
    assert stat.S_IMODE(artifacts[0].stat().st_mode)==0o600


def test_quarantine_tampering_is_detected_when_read_by_operator(roster):
    registry,_gate,*_=roster
    registry.submit(**submit_args(roster))
    saved=next(registry.quarantine_dir.iterdir())
    saved.write_bytes(saved.read_bytes()+b"x")
    with pytest.raises(Stage28Refused,match="QUARANTINE_HASH_MISMATCH"):
        registry.inspect_submission(tenant_id=TENANT,binding_id="binding_a")


def test_duplicate_submission_and_cross_tenant_inspection_refused(roster):
    registry,gate,*_=roster
    args=submit_args(roster)
    registry.submit(**args)
    with pytest.raises(Stage28Refused):
        registry.submit(**args)
    with pytest.raises(Stage22Refused,match="TENANT_BINDING_NOT_AUTHORIZED"):
        registry.inspect_submission(tenant_id="tenant_beta",binding_id="binding_a")
    with pytest.raises(sqlite3.IntegrityError,match="STAGE28_IMMUTABLE_SUBMISSION"):
        gate.db.execute("DELETE FROM secure28_submissions WHERE binding_id='binding_a'")


def test_owner_private_quarantine_directory_is_required(tmp_path,host):  # noqa: F811
    folder=tmp_path/"shared"
    folder.mkdir(mode=0o755)
    with DurableIsolatedCoreGate(tmp_path/"ledger.sqlite",host=host) as gate:
        with pytest.raises(Stage28Refused,match="OWNER_PRIVATE"):
            PublisherPackageRegistry(gate,folder,operator_ack=True)
    assert not (folder/"anything.zip").exists()


def test_signed_source_can_be_inert_malicious_python_but_never_executed(roster,monkeypatch):
    # Stage23's signed SHA pins source bytes. A forged payload cannot execute
    # arbitrary Python just because it is physically in a ZIP or SQLite.
    registry,gate,*_=roster
    calls=[]
    monkeypatch.setattr(gate.host,"evaluate",lambda *_a,**_k:calls.append(True))
    args=submit_args(roster)
    registry.submit(**args)
    assert not calls
    assert registry.status(TENANT,PUB)["externally_verified_identity"] is False
