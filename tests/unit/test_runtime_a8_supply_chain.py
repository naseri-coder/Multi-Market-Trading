"""A8 offline-only source and OCI digest validation. No Docker execution."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

import naseri_markets.runtime_a8_supply_chain as a8


def _source_fixture(tmp_path):
    root = tmp_path / "repo"
    for relative in a8._ALLOWED_FILES:
        file = root / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(("fixed:" + relative).encode())
    lock_path = root / "deploy/runtime_a2/a8_source_lock.json"
    doc = {
        "schema": 1,
        "audience": a8._AUDIENCE,
        "baseline_commit": "a" * 40,
        "lock_state": "SOURCE_ONLY_EXTERNAL_UNVERIFIED",
        "source_files": [
            {
                "path": name,
                "sha256": hashlib.sha256(("fixed:" + name).encode()).hexdigest(),
            }
            for name in a8._ALLOWED_FILES
        ],
        "oci_manifest_digest": None,
        "independent_publisher_attestation": None,
        "host_isolation_certified": False,
        "execution_authorized": False,
    }
    lock_path.write_text(json.dumps(doc))
    return root, lock_path, doc


def _oci_fixture(tmp_path):
    root = tmp_path / "oci"
    blob = root / "blobs" / "sha256"
    blob.mkdir(parents=True)
    (root / "oci-layout").write_text('{"imageLayoutVersion":"1.0.0"}')
    content = [
        (b'{"architecture":"amd64","os":"linux"}', a8._OCI_CONFIG),
        (b"fixed harmless test-only layer", "application/vnd.oci.image.layer.v1.tar"),
    ]
    descriptors = []
    for value, media in content:
        digest = hashlib.sha256(value).hexdigest()
        (blob / digest).write_bytes(value)
        descriptors.append({
            "mediaType": media, "digest": f"sha256:{digest}", "size": len(value),
        })
    manifest = {
        "schemaVersion": 2,
        "mediaType": a8._OCI_MANIFEST,
        "config": descriptors[0],
        "layers": [descriptors[1]],
    }
    raw = json.dumps(manifest, sort_keys=True).encode()
    digest = hashlib.sha256(raw).hexdigest()
    (blob / digest).write_bytes(raw)
    index = {
        "schemaVersion": 2,
        "manifests": [{
            "mediaType": a8._OCI_MANIFEST,
            "digest": f"sha256:{digest}",
            "size": len(raw),
        }],
    }
    (root / "index.json").write_text(json.dumps(index))
    return root, digest, descriptors


def test_real_committed_source_pins():
    root = Path(__file__).resolve().parents[2]
    lock = root / "deploy/runtime_a2/a8_source_lock.json"
    verdict = a8.verify_source_lock(root, lock)
    assert verdict.checked_files == 3
    assert verdict.status == "A8_SOURCE_SHA256_MATCH_EXTERNAL_MATERIALS_UNVERIFIED"
    assert not verdict.verified_worker_image_available
    assert not verdict.external_dependency_provenance_verified
    assert not verdict.worker_execution_authorized
    assert not verdict.telegram_authorized


def test_synthetic_source_mutation_detected(tmp_path):
    root, lock, _ = _source_fixture(tmp_path)
    assert a8.verify_source_lock(root, lock).checked_files == 3
    (root / a8._ALLOWED_FILES[0]).write_text("modified recipe")
    with pytest.raises(a8.A8Refused, match="A8_SOURCE_DIGEST_MISMATCH"):
        a8.verify_source_lock(root, lock)


@pytest.mark.parametrize("field,value", [
    ("schema", True),
    ("lock_state", "APPROVED"),
    ("oci_manifest_digest", "a" * 64),
    ("independent_publisher_attestation", "self-signed claim"),
    ("execution_authorized", True),
    ("host_isolation_certified", True),
])
def test_untrusted_release_claims_rejected(tmp_path, field, value):
    root, lock, obj = _source_fixture(tmp_path)
    obj[field] = value
    lock.write_text(json.dumps(obj))
    with pytest.raises(a8.A8Refused):
        a8.verify_source_lock(root, lock)


def test_extra_keys_duplicate_json_and_path_tricks_refused(tmp_path):
    root, lock, obj = _source_fixture(tmp_path)
    obj["bypass"] = True
    lock.write_text(json.dumps(obj))
    with pytest.raises(a8.A8Refused, match="A8_LOCK_SCHEMA_INVALID"):
        a8.verify_source_lock(root, lock)
    lock.write_bytes(b'{"schema":1,"schema":2}')
    with pytest.raises(a8.A8Refused, match="A8_DUPLICATE_JSON_KEY"):
        a8.verify_source_lock(root, lock)
    lock.write_text(json.dumps(_source_fixture(tmp_path)[2]))
    link = root / a8._ALLOWED_FILES[0]
    link.unlink()
    link.symlink_to(root / a8._ALLOWED_FILES[1])
    with pytest.raises(a8.A8Refused, match="A8_SYMLINK_REFUSED"):
        a8.verify_source_lock(root, lock)


def test_valid_offline_oci_integrity_is_not_authorization(tmp_path):
    root, sha, _ = _oci_fixture(tmp_path)
    outcome = a8.verify_local_oci_layout(root, sha)
    assert outcome.verified_blobs == 3
    assert outcome.manifest_digest == sha
    assert outcome.publisher_signature_verified is False
    assert outcome.independently_attested is False
    assert outcome.runnable_worker_approved is False
    assert outcome.production_authorized is False


def test_wrong_manifest_pin_denied(tmp_path):
    root, _, _ = _oci_fixture(tmp_path)
    with pytest.raises(a8.A8Refused, match="A8_OCI_INDEX_PIN_INVALID"):
        a8.verify_local_oci_layout(root, "f" * 64)


def test_corrupted_layer_or_missing_blob_refused(tmp_path):
    root, sha, descriptors = _oci_fixture(tmp_path)
    layer_hash = descriptors[1]["digest"][7:]
    layer = root / "blobs/sha256" / layer_hash
    layer.write_bytes(b"tampered bytes changed")
    with pytest.raises(a8.A8Refused):
        a8.verify_local_oci_layout(root, sha)
    layer.unlink()
    with pytest.raises(a8.A8Refused):
        a8.verify_local_oci_layout(root, sha)


def test_symlinked_oci_layer_refused(tmp_path):
    root, sha, descriptors = _oci_fixture(tmp_path)
    layer = root / "blobs/sha256" / descriptors[1]["digest"][7:]
    other = root / "payload"
    shutil.copy(layer, other)
    layer.unlink()
    layer.symlink_to(other)
    with pytest.raises(a8.A8Refused, match="A8_SYMLINK_REFUSED"):
        a8.verify_local_oci_layout(root, sha)


def test_oci_index_duplicate_manifest_fails_closed(tmp_path):
    root, sha, _ = _oci_fixture(tmp_path)
    index = root / "index.json"
    doc = json.loads(index.read_text())
    doc["manifests"].append(doc["manifests"][0])
    index.write_text(json.dumps(doc))
    with pytest.raises(a8.A8Refused, match="A8_OCI_INDEX_INVALID"):
        a8.verify_local_oci_layout(root, sha)


def test_oci_invalid_descriptor_no_external_urls(tmp_path):
    root, sha, _ = _oci_fixture(tmp_path)
    data = (root / "blobs/sha256" / sha).read_bytes()
    manifest = json.loads(data)
    manifest["layers"][0]["urls"] = ["https://malicious.invalid/layer"]
    raw = json.dumps(manifest).encode()
    new_sha = hashlib.sha256(raw).hexdigest()
    (root / "blobs/sha256" / new_sha).write_bytes(raw)
    index = json.loads((root / "index.json").read_text())
    index["manifests"][0]["digest"] = "sha256:" + new_sha
    index["manifests"][0]["size"] = len(raw)
    (root / "index.json").write_text(json.dumps(index))
    with pytest.raises(a8.A8Refused, match="A8_OCI_DESCRIPTOR_INVALID"):
        a8.verify_local_oci_layout(root, new_sha)


def test_never_invokes_processes_or_changes_a6(tmp_path, monkeypatch):
    import subprocess
    from naseri_markets.runtime_a6_dispatch_fence import require_worker_launch

    def forbidden(*args, **kwargs):
        raise AssertionError("NO_DOCKER_OR_PROCESS_ALLOWED")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    root, lock, _ = _source_fixture(tmp_path)
    assert not a8.verify_source_lock(root, lock).worker_execution_authorized
    oci_root, digest, _ = _oci_fixture(tmp_path)
    assert not a8.verify_local_oci_layout(oci_root, digest).runnable_worker_approved
    assert "require_worker_launch" == require_worker_launch.__name__


def test_forged_unsupported_media_type_refused(tmp_path):
    root, sha, _ = _oci_fixture(tmp_path)
    manifest = json.loads((root / "blobs/sha256" / sha).read_text())
    manifest["mediaType"] = "application/vnd.docker.distribution.manifest.v2+json"
    raw = json.dumps(manifest).encode()
    new_sha = hashlib.sha256(raw).hexdigest()
    (root / "blobs/sha256" / new_sha).write_bytes(raw)
    index = json.loads((root / "index.json").read_text())
    index["manifests"][0]["digest"] = f"sha256:{new_sha}"
    index["manifests"][0]["size"] = len(raw)
    (root / "index.json").write_text(json.dumps(index))
    with pytest.raises(a8.A8Refused, match="A8_OCI_MANIFEST_SCHEMA_INVALID"):
        a8.verify_local_oci_layout(root, new_sha)
