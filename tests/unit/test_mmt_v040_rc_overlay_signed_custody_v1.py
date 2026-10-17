"""Real local Git (226-module) + test-only Ed25519 RC-overlay custody tests."""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import subprocess
import tomllib
import zipfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from scripts import mmt_v040_rc_overlay_signed_custody_v1 as custody
from scripts import mmt_v040_offline_stable_staging_v1 as staging
from scripts import mmt_v040_public_source_snapshot_audit_v1 as snap
from scripts import mmt_v040_signed_artifact_preflight_v1 as stable

META = Path(__file__).resolve().parents[2] / "platform_release/pyproject.toml"


def canonical(payload: dict) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True).encode() + b"\n")


def git(root: Path, *args: str) -> str:
    output = subprocess.run(["git", "-C", str(root), *args],
                            capture_output=True, text=True, check=True)
    return output.stdout.strip()


def make_wheel(modules: dict[str, bytes], *, metadata_override: bytes | None = None) -> tuple[bytes, bytes]:
    project = tomllib.loads(META.read_text(encoding="utf-8"))["project"]
    info = ("Metadata-Version: 2.4\nName: multi-market-trading\n"
            "Version: 0.4.0\n"
            f"Summary: {project['description']}\n"
            "Description-Content-Type: text/markdown\n"
            "Requires-Python: <3.13,>=3.12\n"
            + "".join(
                f'Requires-Dist: {req}; extra == "{extra}"\n'
                for extra, deps in stable._ALLOWED_REQUIREMENTS.items()
                for req in sorted(deps)
            ) + "\nSynthetic, not published\n").encode()
    if metadata_override is not None:
        info = metadata_override
    cli = ("[console_scripts]\n" + "".join(
        f"{name} = {entry}\n" for name, entry in stable._ALLOWED_COMMANDS.items()
    )).encode()
    members = {**modules,
               stable.DIST + "METADATA": info,
               stable.DIST + "WHEEL": b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
               stable.DIST + "entry_points.txt": cli,
               stable.DIST + "top_level.txt": b"naseri_markets\n"}
    record = io.StringIO()
    writer = csv.writer(record, lineterminator="\n")
    for name, data in members.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        writer.writerow((name, "sha256=" + digest, str(len(data))))
    writer.writerow((stable.DIST + "RECORD", "", ""))
    record_bytes = record.getvalue().encode()
    members[stable.DIST + "RECORD"] = record_bytes
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return result.getvalue(), record_bytes


@pytest.fixture
def example(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    root = tmp_path / "clean-rc"
    (root / "naseri_markets").mkdir(parents=True)
    (root / "platform_release").mkdir()
    (root / "platform_release/pyproject.toml").write_bytes(META.read_bytes())
    (root / "platform_release/README.md").write_text("Synthetic, not published\n")
    names = ["__init__.py", "platform_cli.py", "platform_version_policy_v1.py"] + [
        f"test_module_{i:03d}.py" for i in range(223)
    ]
    modules = {}
    for name in names:
        data = (f'"""Synthetic {name}; no execution permitted."""\n').encode()
        path = "naseri_markets/" + name
        (root / path).write_bytes(data)
        modules[path] = data
    git(root, "init", "-q")
    git(root, "add", ".")
    git(root, "-c", "user.email=fixture@example.invalid", "-c", "user.name=Test",
        "commit", "-qm", "source")
    tree = git(root, "rev-parse", "HEAD:naseri_markets")
    source_commit = git(root, "rev-parse", "HEAD")
    lock = {
        "schema_version": 1, "distribution": "multi-market-trading",
        "release_candidate": "v0.4.0",
        "provenance": "GITHUB_TREE_SNAPSHOT__NOT_RELEASE_APPROVAL",
        "github_repository": "naseri-coder/Multi-Market-Trading",
        "snapshot_commit": source_commit,
        "public_subtree_sha1": tree, "expected_module_count": 226,
        "source_bytes": sum(map(len, modules.values())),
        "modules": [{
            "path": name,
            "git_blob_sha1": hashlib.sha1(b"blob " + str(len(raw)).encode()
                                    + b"\0" + raw).hexdigest(),
            "size": len(raw),
        } for name, raw in sorted(modules.items())],
    }
    (root / "docs").mkdir()
    lock_path = root / snap.SNAPSHOT_PATH
    lock_path.write_text(json.dumps(lock, indent=2) + "\n")
    git(root, "add", "docs")
    git(root, "-c", "user.email=fixture@example.invalid", "-c", "user.name=Test",
        "commit", "-qm", "locked")
    commit = git(root, "rev-parse", "HEAD")
    key = Ed25519PrivateKey.generate()
    pub = key.public_key()
    pem = pub.public_bytes(serialization.Encoding.PEM,
                           serialization.PublicFormat.SubjectPublicKeyInfo)
    fingerprint = hashlib.sha256(pub.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo)).hexdigest()
    safe = tmp_path / "signed"
    safe.mkdir(mode=0o700)
    (safe / "pub.pem").write_bytes(pem)
    policy = {
        "schema": 1, "revision": 1, "active_signers": [fingerprint],
        "revoked_signers": [], "min_source_date_epoch": 1792000000,
    }
    (safe / "policy.json").write_bytes(canonical(policy))
    wheel, record = make_wheel(modules)
    manifest = {
        "schema": 1, "distribution": stable.DIST_NAME, "version": stable.VERSION,
        "purpose": "offline-paper-release-only", "source_commit": commit,
        "source_date_epoch": 1792100000,
        "wheel_filename": stable.WHEEL_NAME,
        "wheel_sha256": "", "wheel_size": 0, "wheel_record_sha256": "",
    }

    def sign(*, mutate=None, omit=None, domain=stable.DOMAIN,
             metadata_override: bytes | None = None):
        sources = dict(modules)
        if omit is not None:
            del sources[omit]
        if mutate is not None:
            sources.update(mutate)
        raw, rec = make_wheel(sources, metadata_override=metadata_override)
        (safe / stable.WHEEL_NAME).write_bytes(raw)
        manifest.update(wheel_sha256=hashlib.sha256(raw).hexdigest(),
                        wheel_size=len(raw),
                        wheel_record_sha256=hashlib.sha256(rec).hexdigest())
        msg = canonical(manifest)
        (safe / "manifest.json").write_bytes(msg)
        (safe / "sig.bin").write_bytes(key.sign(domain + msg))
        overlay_metadata, _ = staging._metadata(root)
        return {
            "repository": root, "manifest": safe / "manifest.json",
            "signature": safe / "sig.bin", "wheel": safe / stable.WHEEL_NAME,
            "trusted_public_key": safe / "pub.pem",
            "trusted_public_key_spki_sha256": fingerprint,
            "policy": safe / "policy.json",
            "expected_policy_sha256": hashlib.sha256(canonical(policy)).hexdigest(),
            "expected_manifest_sha256": hashlib.sha256(msg).hexdigest(),
            "expected_source_commit": commit,
            "expected_public_tree_sha1": tree,
            "expected_lock_sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
            "expected_overlay_sha256": hashlib.sha256(overlay_metadata).hexdigest(),
        }
    return root, modules, sign, safe


def test_valid_signed_stable_wheel_attests_exact_rc_overlay_readonly(example):
    root, modules, sign, _ = example
    options = sign()
    result = custody.audit(**options)
    assert result["public_modules_verified"] == 226
    assert result["signed_wheel_record_verified"] is True
    assert result["original_rc_source_commit"] == git(root, "rev-parse", "HEAD")
    assert set(result.items()) >= {
        ("rc_git_commit_is_a_stable_release_commit", False),
        ("writes_performed", False), ("install_authorized", False),
        ("public_release_authorized", False),
        ("live_trading_authorized", False),
        ("telegram_publication_authorized", False),
    }
    assert (root / "platform_release/pyproject.toml").read_bytes() == META.read_bytes()
    assert len(modules) == 226


def test_wrong_independent_overlay_metadata_hash_refused(example):
    _, _, sign, _ = example
    params = sign()
    params["expected_overlay_sha256"] = "0" * 64
    with pytest.raises(custody.OverlayCustodyRefused, match="V040_OVERLAY_METADATA_PIN_MISMATCH"):
        custody.audit(**params)


def test_invalid_external_overlay_pin_denied(example):
    _, _, sign, _ = example
    params = sign()
    params["expected_overlay_sha256"] = "0"
    with pytest.raises(custody.OverlayCustodyRefused, match="V040_OVERLAY_EXTERNAL_PIN_REQUIRED"):
        custody.audit(**params)


def test_externally_signed_modified_module_not_claimed_as_git_source(example):
    _, _, sign, _ = example
    params = sign(mutate={"naseri_markets/test_module_102.py": b'"""Changed."""\n'})
    with pytest.raises(custody.OverlayCustodyRefused, match="V040_OVERLAY_MODULE_BYTES_MISMATCH"):
        custody.audit(**params)


def test_wheel_missing_one_module_even_if_signature_recreated_is_denied(example):
    _, _, sign, _ = example
    params = sign(omit="naseri_markets/test_module_105.py")
    with pytest.raises(custody.OverlayCustodyRefused, match="V040_OVERLAY_MODULE_SET_MISMATCH"):
        custody.audit(**params)


def test_dirty_checkout_denied_even_when_wheel_is_valid(example):
    root, _, sign, _ = example
    params = sign()
    (root / "naseri_markets/test_module_101.py").write_text("# changed after signing\n")
    with pytest.raises(snap.PublicSnapshotRefused, match="V040_GIT_NOT_CLEAN"):
        custody.audit(**params)


def test_wrong_external_tree_denied(example):
    _, _, sign, _ = example
    params = sign()
    params["expected_public_tree_sha1"] = "0" * 40
    with pytest.raises(snap.PublicSnapshotRefused, match="V040_PUBLIC_TREE_PIN_MISMATCH"):
        custody.audit(**params)


def test_forged_signature_denied(example):
    _, _, sign, safe = example
    params = sign()
    (safe / "sig.bin").write_bytes(b"0" * 64)
    with pytest.raises(stable.StableArtifactRefused, match="V040_SIGNATURE_VERIFICATION_FAILED"):
        custody.audit(**params)


def test_historical_rc_domain_signature_cannot_validate_stable_overlay(example):
    _, _, sign, _ = example
    params = sign(domain=b"MMT-R37-OFFLINE-PREVIEW-MANIFEST-V1\n")
    with pytest.raises(stable.StableArtifactRefused, match="V040_SIGNATURE_VERIFICATION_FAILED"):
        custody.audit(**params)


def test_any_defined_production_setting_denied(example, monkeypatch):
    _, _, sign, _ = example
    params = sign()
    monkeypatch.setenv("MMT_PRODUCTION", "0")
    with pytest.raises(custody.OverlayCustodyRefused, match="V040_OVERLAY_NONPRODUCTION_REQUIRED"):
        custody.audit(**params)


def test_signed_manifest_wrong_commit_pin_denied(example):
    _, _, sign, _ = example
    params = sign()
    params["expected_source_commit"] = "a" * 40
    with pytest.raises(stable.StableArtifactRefused, match="V040_SOURCE_COMMIT_MISMATCH"):
        custody.audit(**params)


def test_installed_parser_never_offers_publish_or_install_flags():
    source = (Path(__file__).resolve().parents[2]
              / "scripts/mmt_v040_rc_overlay_signed_custody_v1.py").read_text()
    assert "--install" not in source
    assert "--publish" not in source
    assert '"rc_git_commit_is_a_stable_release_commit": False' in source


def _wheel_metadata(raw: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(raw)) as wheel:
        return wheel.read(stable.DIST + "METADATA")


def test_even_validly_resigned_changed_summary_fails_source_attestation(example):
    root, modules, sign, _ = example
    normal = _wheel_metadata(make_wheel(modules)[0])
    source_summary = tomllib.loads(META.read_text())["project"]["description"]
    assert normal.count(f"Summary: {source_summary}".encode()) == 1
    spoofed = normal.replace(f"Summary: {source_summary}".encode(),
                             b"Summary: Inaccurate externally signed market promise")
    params = sign(metadata_override=spoofed)  # genuine fixture signer signs malicious metadata
    assert stable.verify(**{k: params[k] for k in (
        "manifest", "signature", "wheel", "trusted_public_key",
        "trusted_public_key_spki_sha256", "policy", "expected_policy_sha256",
        "expected_manifest_sha256", "expected_source_commit",
    )})["record_verified"] is True
    with pytest.raises(custody.OverlayCustodyRefused,
                       match="V040_WHEEL_SUMMARY_SOURCE_MISMATCH"):
        custody.audit(**params)


def test_even_validly_resigned_changed_readme_fails_source_attestation(example):
    _, modules, sign, _ = example
    normal = _wheel_metadata(make_wheel(modules)[0])
    assert normal.endswith(b"Synthetic, not published\n")
    forged = normal[:-len(b"Synthetic, not published\n")] + b"Misleading published README\n"
    params = sign(metadata_override=forged)
    with pytest.raises(custody.OverlayCustodyRefused,
                       match="V040_WHEEL_README_SOURCE_MISMATCH"):
        custody.audit(**params)


def test_even_validly_resigned_duplicate_summary_fails_source_attestation(example):
    _, modules, sign, _ = example
    normal = _wheel_metadata(make_wheel(modules)[0])
    forged = normal.replace(b"Description-Content-Type: text/markdown\n",
                            b"Summary: Hidden second summary\nDescription-Content-Type: text/markdown\n")
    params = sign(metadata_override=forged)
    with pytest.raises(custody.OverlayCustodyRefused,
                       match="V040_WHEEL_SUMMARY_SOURCE_MISMATCH"):
        custody.audit(**params)
