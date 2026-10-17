"""R38 cryptographically valid test-only keys, revocation and install denials.

Tests never launch pip, create a real venv, connect network or trade.
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from scripts import mmt_r35_offline_preview_install_v1 as r35
from scripts import mmt_r37_offline_signed_manifest_verify_v1 as r37
from scripts import mmt_r38_signed_offline_preview_install_v1 as r38


def canonical(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode() + b"\n"


@pytest.fixture
def example(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    monkeypatch.setattr(r37.sys, "version_info", (3, 12, 3))
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    private_key = Ed25519PrivateKey.generate()  # ephemeral, local TEST only
    public = private_key.public_key()
    (private / "public.pem").write_bytes(public.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    spki = public.public_bytes(serialization.Encoding.DER,
                               serialization.PublicFormat.SubjectPublicKeyInfo)
    fingerprint = hashlib.sha256(spki).hexdigest()
    package = private / r35.FILE_NAME
    meta = ("Metadata-Version: 2.4\nName: multi-market-trading\n"
            "Version: 0.4.0rc1\n")
    scripts = ("[console_scripts]\n"
               "naseri-markets = naseri_markets.platform_cli:main\n"
               "naseri-paper-demo = naseri_markets.paper_demo_cli_v1:main\n")
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("naseri_markets/platform_cli.py", "# safe test only\n")
        archive.writestr(r35.DIST + "METADATA", meta)
        archive.writestr(r35.DIST + "entry_points.txt", scripts)
    wheel_bytes = package.read_bytes()
    manifest_obj = {
        "schema": 1,
        "distribution": "multi-market-trading",
        "version": "0.4.0rc1",
        "purpose": "offline-preview-only",
        "source_commit": "1" * 40,
        "source_date_epoch": 1704067200,
        "wheel_filename": r35.FILE_NAME,
        "wheel_sha256": hashlib.sha256(wheel_bytes).hexdigest(),
        "wheel_size": len(wheel_bytes),
    }
    policy_obj = {
        "schema": 1,
        "revision": 3,
        "active_keys": [fingerprint],
        "revoked_keys": [],
        "min_source_date_epoch": 1700000000,
    }

    def write_manifest():
        raw = canonical(manifest_obj)
        (private / "manifest.json").write_bytes(raw)
        (private / "manifest.sig").write_bytes(private_key.sign(r37.DOMAIN + raw))
        return hashlib.sha256(raw).hexdigest()

    def write_policy():
        raw = canonical(policy_obj)
        (private / "policy.json").write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    kwargs = {
        "manifest": private / "manifest.json",
        "signature": private / "manifest.sig",
        "wheel": package,
        "trusted_public_key": private / "public.pem",
        "trusted_public_key_spki_sha256": fingerprint,
        "expected_source_commit": manifest_obj["source_commit"],
        "expected_manifest_sha256": write_manifest(),
        "policy": private / "policy.json",
        "expected_policy_sha256": write_policy(),
        "destination": private / "fresh-preview",
    }
    return kwargs, manifest_obj, policy_obj, write_manifest, write_policy


def test_signed_policy_preflight_readonly(example):
    params, _, _, _, _ = example
    report = r38.preflight(**params)
    assert report["signed_preview_verified"] is True
    assert report["verdict"] == "R38_SIGNED_OFFLINE_PREFLIGHT_PASS_RELEASE_DENIED"
    assert report["writes_performed"] is False
    assert report["install_authorized"] is False
    assert report["live_authorized"] is False
    assert not params["destination"].exists()


def test_missing_signature_denied_before_writes(example):
    params, _, _, _, _ = example
    params["signature"].unlink()
    with pytest.raises(r37.R37Refused, match="FILE_UNREADABLE"):
        r38.preflight(**params)
    assert not params["destination"].exists()


def test_bad_signature_denied(example):
    params, _, _, _, _ = example
    params["signature"].write_bytes(b"Q" * 64)
    with pytest.raises(r37.R37Refused, match="INVALID_ED25519_SIGNATURE"):
        r38.preflight(**params)


def test_unpinned_manifest_denied(example):
    params, _, _, _, _ = example
    params["expected_manifest_sha256"] = "0" * 64
    with pytest.raises(r38.R38Refused, match="MANIFEST_PIN_MISMATCH"):
        r38.preflight(**params)


def test_unpinned_policy_denied(example):
    params, _, _, _, _ = example
    params["expected_policy_sha256"] = "0" * 64
    with pytest.raises(r38.R38Refused, match="POLICY_HASH_MISMATCH"):
        r38.preflight(**params)


def test_revoked_signer_denied_even_with_valid_signature(example):
    params, _, policy, _, rewrite = example
    policy["active_keys"] = []
    policy["revoked_keys"] = [params["trusted_public_key_spki_sha256"]]
    params["expected_policy_sha256"] = rewrite()
    with pytest.raises(r38.R38Refused, match="SIGNING_KEY_REVOKED"):
        r38.preflight(**params)
    assert not params["destination"].exists()


def test_signer_omitted_from_allowlist_denied(example):
    params, _, policy, _, rewrite = example
    policy["active_keys"] = ["f" * 64]
    params["expected_policy_sha256"] = rewrite()
    with pytest.raises(r38.R38Refused, match="SIGNING_KEY_NOT_ACTIVE"):
        r38.preflight(**params)


def test_signed_stale_manifest_denied(example):
    params, manifest, policy, _, rewrite_policy = example
    policy["min_source_date_epoch"] = 1704067201
    params["expected_policy_sha256"] = rewrite_policy()
    with pytest.raises(r38.R38Refused, match="OLD_MANIFEST_REPLAY_DENIED"):
        r38.preflight(**params)
    assert manifest["source_date_epoch"] == 1704067200


def test_signed_replay_other_source_commit_denied(example):
    params, _, _, _, _ = example
    params["expected_source_commit"] = "2" * 40
    with pytest.raises(r37.R37Refused, match="SOURCE_PIN_MISMATCH"):
        r38.preflight(**params)


def test_signed_wheel_modified_denied(example):
    params, _, _, _, _ = example
    params["wheel"].write_bytes(b"x" * params["wheel"].stat().st_size)
    with pytest.raises(r37.R37Refused, match="SIGNED_WHEEL_HASH_MISMATCH"):
        r38.preflight(**params)


def test_wrong_public_key_denied(example):
    params, _, _, _, _ = example
    other = Ed25519PrivateKey.generate().public_key()
    params["trusted_public_key"].write_bytes(other.public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))
    with pytest.raises(r37.R37Refused, match="TRUSTED_KEY_PIN_MISMATCH"):
        r38.preflight(**params)


def test_corrupt_duplicate_policy_denied(example):
    params, _, _, _, _ = example
    raw = params["policy"].read_bytes().strip()
    raw = raw[:-1] + b',"revision":3}\n'
    params["policy"].write_bytes(raw)
    params["expected_policy_sha256"] = hashlib.sha256(raw).hexdigest()
    with pytest.raises(r38.R38Refused, match="POLICY_DUPLICATE_KEY"):
        r38.preflight(**params)


def test_explicit_production_environment_denied(example, monkeypatch):
    params, _, _, _, _ = example
    monkeypatch.setenv("MMT_PRODUCTION", "0")
    with pytest.raises(r38.R38Refused, match="NONPRODUCTION_REQUIRED"):
        r38.preflight(**params)


def test_existing_destination_denied(example):
    params, _, _, _, _ = example
    params["destination"].mkdir()
    with pytest.raises(r35.R35Refused, match="NEW_ABSOLUTE"):
        r38.preflight(**params)


def test_nonroot_gate_denies_root_before_signature_read(example, monkeypatch):
    params, _, _, _, _ = example
    monkeypatch.setattr(r35.os, "geteuid", lambda: 0)
    with pytest.raises(r35.R35Refused, match="NONROOT_INSTALL_REQUIRED"):
        r38.install(ack=True, **params)
    assert not params["destination"].exists()


def test_install_missing_ack_denied(example):
    params, _, _, _, _ = example
    with pytest.raises(r35.R35Refused, match="ACK_REQUIRED"):
        r38.install(ack=False, **params)
    assert not params["destination"].exists()


def test_installer_is_not_invoked_before_signature(example, monkeypatch):
    params, _, _, _, _ = example
    params["signature"].write_bytes(b"0" * 64)
    called = []
    monkeypatch.setattr(r35, "install", lambda **kwargs: called.append(kwargs))
    monkeypatch.setattr(r35, "_gate", lambda **kwargs: None)
    with pytest.raises(r37.R37Refused, match="INVALID_ED25519_SIGNATURE"):
        r38.install(ack=True, **params)
    assert not called
    assert not params["destination"].exists()


def test_signed_install_mock_only_saves_audit_proof(example, monkeypatch):
    params, _, _, _, _ = example
    calls = []
    monkeypatch.setattr(r35, "_gate", lambda **kwargs: None)

    def fake_install(*, wheel, sha256, destination, ack):
        calls.append((wheel, sha256, destination, ack))
        destination.mkdir(mode=0o700)
        return {
            "verdict": "R35_INSTALLED_OFFLINE_PREVIEW_PASS_RELEASE_DENIED",
            "wheel_sha256": sha256,
            "installation_isolated": True,
            "live_authorized": False,
        }

    monkeypatch.setattr(r35, "install", fake_install)
    output = r38.install(ack=True, **params)
    assert len(calls) == 1
    assert calls[0][1] == hashlib.sha256(params["wheel"].read_bytes()).hexdigest()
    assert calls[0][3] is True
    assert output["verdict"] == "R38_SIGNED_OFFLINE_INSTALLED_PREVIEW_PASS_RELEASE_DENIED"
    assert output["live_authorized"] is False
    evidence = params["destination"] / r38.EVIDENCE_NAME
    assert json.loads(evidence.read_text()) == output
    assert evidence.stat().st_mode & 0o077 == 0


def test_denied_r35_install_result_does_not_create_evidence(example, monkeypatch):
    params, _, _, _, _ = example
    monkeypatch.setattr(r35, "_gate", lambda **kwargs: None)

    def fake_install(*, wheel, sha256, destination, ack):
        destination.mkdir(mode=0o700)
        return {"verdict": "R35_INSTALLED_OFFLINE_PREVIEW_PASS_RELEASE_DENIED",
                "wheel_sha256": sha256, "installation_isolated": True,
                "live_authorized": True}

    monkeypatch.setattr(r35, "install", fake_install)
    with pytest.raises(r38.R38Refused, match="R35_INSTALL_RESULT_UNSAFE"):
        r38.install(ack=True, **params)
    assert params["destination"].is_dir()  # preserve failure evidence
    assert not (params["destination"] / r38.EVIDENCE_NAME).exists()


def test_invalid_cli_refused_and_no_writes(example, capsys):
    params, _, _, _, _ = example
    params["expected_manifest_sha256"] = "0" * 64
    flags = ["manifest", "signature", "wheel", "trusted_public_key",
             "trusted_public_key_spki_sha256", "expected_source_commit",
             "expected_manifest_sha256", "policy", "expected_policy_sha256",
             "destination"]
    args = ["--check-only"]
    for field in flags:
        args += ["--" + field.replace("_", "-"), str(params[field])]
    assert r38.main(args) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["verdict"] == "R38_SIGNED_PREVIEW_REFUSED"
    assert result["live_authorized"] is False
    assert not params["destination"].exists()
