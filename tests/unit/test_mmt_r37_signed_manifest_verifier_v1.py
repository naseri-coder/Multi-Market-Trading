"""R37 standalone signature verifier tests with temporary ephemeral test-only keys."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from scripts import mmt_r37_offline_signed_manifest_verify_v1 as r


@pytest.fixture
def setup(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    monkeypatch.setattr(r.sys, "version_info", (3, 12, 3))
    private = Ed25519PrivateKey.generate()  # TEST ONLY; never stored or published
    public = private.public_key()
    pem = public.public_bytes(serialization.Encoding.PEM,
                              serialization.PublicFormat.SubjectPublicKeyInfo)
    spki = public.public_bytes(serialization.Encoding.DER,
                               serialization.PublicFormat.SubjectPublicKeyInfo)
    (tmp_path / "trusted.pem").write_bytes(pem)
    data = b"inert-preview-wheel-test-data" * 6
    assert len(data) > 128
    wheel = tmp_path / r.WHEEL_NAME
    wheel.write_bytes(data)
    commit = "1" * 40
    obj = {
        "schema": 1, "distribution": "multi-market-trading",
        "version": "0.4.0rc1", "purpose": "offline-preview-only",
        "source_commit": commit, "source_date_epoch": 1704067200,
        "wheel_filename": r.WHEEL_NAME, "wheel_sha256": hashlib.sha256(data).hexdigest(),
        "wheel_size": len(data),
    }

    def write(obj=obj):
        manifest = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode() + b"\n"
        (tmp_path / "manifest.json").write_bytes(manifest)
        (tmp_path / "manifest.sig").write_bytes(private.sign(r.DOMAIN + manifest))
    write()
    opts = {
        "manifest": tmp_path / "manifest.json", "signature": tmp_path / "manifest.sig",
        "wheel": wheel, "trusted_public_key": tmp_path / "trusted.pem",
        "trusted_public_key_spki_sha256": hashlib.sha256(spki).hexdigest(),
        "expected_source_commit": commit,
    }
    return opts, private, obj, write


def test_verified_detached_signature_no_release_grant(setup):
    opts, _, _, _ = setup
    out = r.verify(**opts)
    assert out["manifest_signature_valid"] is True
    assert out["public_release_authorized"] is False
    assert out["live_authorized"] is False
    assert out["files_written"] is False


def test_signature_forgery_denied(setup):
    opts, _, _, _ = setup
    opts["signature"].write_bytes(b"a" * 64)
    with pytest.raises(r.R37Refused, match="INVALID_ED25519_SIGNATURE"):
        r.verify(**opts)


def test_untrusted_public_key_denied(setup):
    opts, _, _, _ = setup
    other = Ed25519PrivateKey.generate().public_key()
    opts["trusted_public_key"].write_bytes(other.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    with pytest.raises(r.R37Refused, match="TRUSTED_KEY_PIN_MISMATCH"):
        r.verify(**opts)


def test_mismatched_independent_source_pin_denied(setup):
    opts, _, _, _ = setup
    opts["expected_source_commit"] = "2" * 40
    with pytest.raises(r.R37Refused, match="SOURCE_PIN_MISMATCH"):
        r.verify(**opts)


def test_signed_wheel_tampered_denied(setup):
    opts, _, _, _ = setup
    opts["wheel"].write_bytes(b"x" * opts["wheel"].stat().st_size)
    with pytest.raises(r.R37Refused, match="SIGNED_WHEEL_HASH_MISMATCH"):
        r.verify(**opts)


def test_manifest_key_duplicate_denied(setup):
    opts, _, _, _ = setup
    raw = opts["manifest"].read_bytes().strip()
    opts["manifest"].write_bytes(raw[:-1] + b',"schema":1}\n')
    with pytest.raises(r.R37Refused, match="DUPLICATE_JSON_KEY"):
        r.verify(**opts)


def test_signed_wrong_purpose_denied(setup):
    opts, _, obj, write = setup
    obj["purpose"] = "production"
    write(obj)
    with pytest.raises(r.R37Refused, match="MANIFEST_VALUES_INVALID"):
        r.verify(**opts)


def test_noncanonical_manifest_denied(setup):
    opts, private, obj, _ = setup
    raw = json.dumps(obj, indent=2).encode()
    opts["manifest"].write_bytes(raw)
    opts["signature"].write_bytes(private.sign(r.DOMAIN + raw))
    with pytest.raises(r.R37Refused, match="NONCANONICAL_MANIFEST"):
        r.verify(**opts)


def test_production_environment_denied(setup, monkeypatch):
    opts, _, _, _ = setup
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(r.R37Refused, match="NONPRODUCTION_PY312_REQUIRED"):
        r.verify(**opts)


def test_missing_crypto_pin_denied(setup):
    opts, _, _, _ = setup
    opts["trusted_public_key_spki_sha256"] = ""
    with pytest.raises(r.R37Refused, match="EXTERNAL_TRUST_PINS_REQUIRED"):
        r.verify(**opts)


def test_symlink_manifest_denied(setup):
    opts, _, _, _ = setup
    link = opts["manifest"].parent / "link.json"
    link.symlink_to(opts["manifest"])
    opts["manifest"] = link
    with pytest.raises(r.R37Refused, match="ABSOLUTE_REGULAR_FILE_REQUIRED"):
        r.verify(**opts)


def test_signature_domain_separation_denied(setup):
    opts, private, _, _ = setup
    opts["signature"].write_bytes(private.sign(opts["manifest"].read_bytes()))
    with pytest.raises(r.R37Refused, match="INVALID_ED25519_SIGNATURE"):
        r.verify(**opts)


def test_short_signature_denied(setup):
    opts, _, _, _ = setup
    opts["signature"].write_bytes(b"0" * 63)
    with pytest.raises(r.R37Refused, match="SIGNATURE_LENGTH_INVALID"):
        r.verify(**opts)


@pytest.mark.parametrize("setting", ["0", "true", "YES", ""])
def test_any_explicit_production_setting_denied(setup, monkeypatch, setting):
    opts, _, _, _ = setup
    monkeypatch.setenv("MMT_PRODUCTION", setting)
    with pytest.raises(r.R37Refused, match="NONPRODUCTION_PY312_REQUIRED"):
        r.verify(**opts)


def test_no_nonproduction_ack_denied(setup, monkeypatch):
    opts, _, _, _ = setup
    monkeypatch.delenv("MMT_NONPRODUCTION")
    with pytest.raises(r.R37Refused, match="NONPRODUCTION_PY312_REQUIRED"):
        r.verify(**opts)


def test_signed_boolean_epoch_denied(setup):
    opts, _, obj, write = setup
    obj["source_date_epoch"] = True
    write(obj)
    with pytest.raises(r.R37Refused, match="MANIFEST_VALUES_INVALID"):
        r.verify(**opts)


def test_local_wheel_symlink_denied(setup):
    opts, _, _, _ = setup
    path = opts["wheel"].parent / "source" / r.WHEEL_NAME
    path.parent.mkdir()
    path.symlink_to(opts["wheel"])
    opts["wheel"] = path
    with pytest.raises(r.R37Refused, match="ABSOLUTE_REGULAR_FILE_REQUIRED"):
        r.verify(**opts)


def test_hardlinked_manifest_denied(setup):
    import os
    opts, _, _, _ = setup
    os.link(opts["manifest"], opts["manifest"].parent / "extra-manifest.json")
    with pytest.raises(r.R37Refused, match="BOUNDED_SINGLE_LINK_FILE_REQUIRED"):
        r.verify(**opts)


def test_valid_cli_never_grants_install_or_live(setup, capsys):
    opts, _, _, _ = setup
    args = [
        "--manifest", str(opts["manifest"]),
        "--signature", str(opts["signature"]),
        "--wheel", str(opts["wheel"]),
        "--trusted-public-key", str(opts["trusted_public_key"]),
        "--trusted-public-key-spki-sha256", opts["trusted_public_key_spki_sha256"],
        "--expected-source-commit", opts["expected_source_commit"],
    ]
    assert r.main(args) == 0
    response = json.loads(capsys.readouterr().out)
    assert response["install_authorized"] is False
    assert response["public_release_authorized"] is False
    assert response["live_authorized"] is False
    assert response["manifest_signature_valid"] is True


def test_signature_invalid_cli_fails_closed(setup, capsys):
    opts, _, _, _ = setup
    opts["signature"].write_bytes(b"A" * 64)
    args = [
        "--manifest", str(opts["manifest"]),
        "--signature", str(opts["signature"]),
        "--wheel", str(opts["wheel"]),
        "--trusted-public-key", str(opts["trusted_public_key"]),
        "--trusted-public-key-spki-sha256", opts["trusted_public_key_spki_sha256"],
        "--expected-source-commit", opts["expected_source_commit"],
    ]
    assert r.main(args) == 2
    response = json.loads(capsys.readouterr().out)
    assert response["verdict"] == "R37_SIGNATURE_AUDIT_REFUSED"
    assert response["live_authorized"] is False
    assert response["public_release_authorized"] is False
