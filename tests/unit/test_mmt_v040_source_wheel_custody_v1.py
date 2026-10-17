"""Fail-closed source vs signed wheel custody on an ephemeral local Git repo."""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import os
import subprocess
import zipfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from scripts import mmt_v040_signed_artifact_preflight_v1 as stable
from scripts import mmt_v040_source_wheel_custody_v1 as custody


def _json(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True).encode() + b"\n"


def _git(repository: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(repository), *args],
                            check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _wheel_from_modules(modules: dict[str, bytes], *, mutate=None) -> tuple[bytes, bytes]:
    source = dict(modules)
    if mutate is not None:
        source.update(mutate)
    metadata = (
        "Metadata-Version: 2.4\nName: multi-market-trading\n"
        "Version: 0.4.0\nRequires-Python: <3.13,>=3.12\n"
        + "".join(
            f'Requires-Dist: {req}; extra == "{extra}"\n'
            for extra, values in stable._ALLOWED_REQUIREMENTS.items()
            for req in sorted(values)
        )
    ).encode()
    scripts = ("[console_scripts]\n" + "".join(
        f"{k} = {v}\n" for k, v in stable._ALLOWED_COMMANDS.items()
    )).encode()
    members = {**source, stable.DIST+"METADATA":metadata,
               stable.DIST+"WHEEL":b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
               stable.DIST+"entry_points.txt":scripts,
               stable.DIST+"top_level.txt":b"naseri_markets\n"}
    rows = []
    for name, data in members.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        rows.append((name, "sha256="+digest, str(len(data))))
    rows.append((stable.DIST+"RECORD", "", ""))
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\n").writerows(rows)
    record = buf.getvalue().encode()
    members[stable.DIST+"RECORD"] = record
    dst = io.BytesIO()
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return dst.getvalue(), record


@pytest.fixture
def signed_checkout(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    checkout = tmp_path / "project"
    (checkout / "platform_release").mkdir(parents=True)
    (checkout / "naseri_markets").mkdir()
    modules = {
        "naseri_markets/__init__.py":b'"""Synthetic package."""\n',
        "naseri_markets/platform_cli.py":b'"""Synthetic inert command."""\n',
        "naseri_markets/platform_version_policy_v1.py":b'"""Synthetic version check."""\n',
    }
    for rel, data in modules.items():
        (checkout / rel).write_bytes(data)
    build_toml = (
        '[build-system]\nrequires = ["setuptools==80.9.0", "wheel==0.45.1"]\n'
        'build-backend = "setuptools.build_meta"\n'
        '[project]\nname = "multi-market-trading"\nversion = "0.4.0"\n'
        'requires-python = ">=3.12,<3.13"\ndependencies = []\n'
        '[project.optional-dependencies]\n'
        + "".join(
            extra + " = [" + ", ".join(json.dumps(r) for r in sorted(reqs)) + "]\n"
            for extra, reqs in stable._ALLOWED_REQUIREMENTS.items()
        )
        + '[project.scripts]\n'
        + "".join(json.dumps(k) + " = " + json.dumps(v) + "\n"
                    for k, v in stable._ALLOWED_COMMANDS.items())
    )
    (checkout / "platform_release/pyproject.toml").write_text(build_toml)
    (checkout / "platform_release/README.md").write_text("Inert test fixture\n")
    _git(checkout, "init", "-q")
    _git(checkout, "-c", "user.email=test@example.invalid", "-c", "user.name=Audit Test", "add", ".")
    _git(checkout, "-c", "user.email=test@example.invalid", "-c", "user.name=Audit Test", "commit", "-qm", "Fixture")
    commit = _git(checkout, "rev-parse", "HEAD")
    witness = tmp_path / "private"
    witness.mkdir(mode=0o700)
    signer = Ed25519PrivateKey.generate()
    public = signer.public_key()
    key = public.public_bytes(serialization.Encoding.PEM,
                              serialization.PublicFormat.SubjectPublicKeyInfo)
    spki = public.public_bytes(serialization.Encoding.DER,
                               serialization.PublicFormat.SubjectPublicKeyInfo)
    fingerprint = hashlib.sha256(spki).hexdigest()
    (witness / "signer.pem").write_bytes(key)
    manifest = {
        "schema":1, "distribution":stable.DIST_NAME, "version":"0.4.0",
        "purpose":"offline-paper-release-only", "source_commit":commit,
        "source_date_epoch":1792100000, "wheel_filename":stable.WHEEL_NAME,
        "wheel_sha256":"", "wheel_size":0, "wheel_record_sha256":"",
    }
    policy = {
        "schema":1, "revision":1, "active_signers":[fingerprint],
        "revoked_signers":[], "min_source_date_epoch":1792000000,
    }
    (witness / "policy.json").write_bytes(_json(policy))

    def signs(*, mutate=None, skip=None):
        source = {name:data for name,data in modules.items() if name != skip}
        wheel, record = _wheel_from_modules(source, mutate=mutate)
        (witness / stable.WHEEL_NAME).write_bytes(wheel)
        manifest.update(wheel_sha256=hashlib.sha256(wheel).hexdigest(),
                        wheel_size=len(wheel),
                        wheel_record_sha256=hashlib.sha256(record).hexdigest())
        payload = _json(manifest)
        (witness / "manifest.json").write_bytes(payload)
        (witness / "signature.bin").write_bytes(signer.sign(stable.DOMAIN+payload))
        return dict(
            repository=checkout, manifest=witness/"manifest.json",
            signature=witness/"signature.bin", wheel=witness/stable.WHEEL_NAME,
            trusted_public_key=witness/"signer.pem",
            trusted_public_key_spki_sha256=fingerprint,
            policy=witness/"policy.json",
            expected_policy_sha256=hashlib.sha256(_json(policy)).hexdigest(),
            expected_manifest_sha256=hashlib.sha256(payload).hexdigest(),
            expected_source_commit=commit,
        )
    return checkout, modules, signs


def test_positive_real_git_checkout_plus_signed_wheel_byte_equality(signed_checkout):
    checkout, _, signs = signed_checkout
    evidence = custody.audit(**signs())
    assert evidence["public_modules_byte_verified"] == 3
    assert evidence["wheel_record_verified"] is True
    assert evidence["source_commit"] == _git(checkout, "rev-parse", "HEAD")
    for field in ("writes_performed", "install_authorized",
                  "public_release_authorized", "live_trading_authorized",
                  "telegram_publication_authorized"):
        assert evidence[field] is False


def test_signed_wheel_with_different_public_source_bytes_refused(signed_checkout):
    _, _, signs = signed_checkout
    params = signs(mutate={"naseri_markets/platform_cli.py":b'"""Forged module."""\n'})
    with pytest.raises(custody.SourceCustodyRefused,
                       match="V040_SOURCE_WHEEL_MODULE_BYTES_MISMATCH"):
        custody.audit(**params)


def test_signed_wheel_omitted_a_public_module_refused(signed_checkout):
    _, _, signs = signed_checkout
    with pytest.raises(custody.SourceCustodyRefused,
                       match="V040_SOURCE_WHEEL_MODULE_SET_MISMATCH"):
        custody.audit(**signs(skip="naseri_markets/__init__.py"))


def test_untracked_public_source_refused_before_wheel_bytes(signed_checkout):
    checkout, _, signs = signed_checkout
    params = signs()
    (checkout / "naseri_markets/new.py").write_text("# untracked\n")
    with pytest.raises(custody.SourceCustodyRefused,
                       match="V040_SOURCE_CHECKOUT_NOT_CLEAN"):
        custody.audit(**params)


def test_dirty_public_source_refused(signed_checkout):
    checkout, _, signs = signed_checkout
    params = signs()
    (checkout / "naseri_markets/platform_cli.py").write_text("# dirty\n")
    with pytest.raises(custody.SourceCustodyRefused,
                       match="V040_SOURCE_CHECKOUT_NOT_CLEAN"):
        custody.audit(**params)


def test_wrong_external_source_commit_refused(signed_checkout):
    _, _, signs = signed_checkout
    params = signs()
    params["expected_source_commit"] = "a"*40
    with pytest.raises(stable.StableArtifactRefused,
                       match="V040_SOURCE_COMMIT_MISMATCH"):
        custody.audit(**params)


def test_source_release_metadata_mismatch_refused(signed_checkout):
    checkout, _, signs = signed_checkout
    params = signs()
    p = checkout / "platform_release/pyproject.toml"
    content = p.read_text().replace('version = "0.4.0"', 'version = "0.4.0rc1"')
    p.write_text(content)
    _git(checkout,"add",".")
    _git(checkout,"-c","user.email=test@example.invalid","-c","user.name=Audit Test","commit","-qm","Wrong metadata")
    with pytest.raises(custody.SourceCustodyRefused,
                       match="V040_SOURCE_METADATA_DRIFT"):
        custody._source_inventory(checkout, _git(checkout, "rev-parse", "HEAD"))


def test_any_production_environment_setting_denied(signed_checkout, monkeypatch):
    _, _, signs = signed_checkout
    params=signs()
    monkeypatch.setenv("MMT_PRODUCTION", "0")
    with pytest.raises(custody.SourceCustodyRefused, match="V040_NONPRODUCTION_REQUIRED"):
        custody.audit(**params)


def test_changed_build_backend_even_clean_git_is_refused(signed_checkout):
    checkout, _, _ = signed_checkout
    p = checkout / "platform_release/pyproject.toml"
    p.write_text(p.read_text().replace(
        'build-backend = "setuptools.build_meta"',
        'build-backend = "unreviewed.backend"',
    ))
    _git(checkout, "add", ".")
    _git(checkout, "-c", "user.email=test@example.invalid",
         "-c", "user.name=Audit Test", "commit", "-qm", "bad builder")
    with pytest.raises(custody.SourceCustodyRefused,
                       match="V040_SOURCE_METADATA_DRIFT"):
        custody._source_inventory(checkout, _git(checkout, "rev-parse", "HEAD"))
