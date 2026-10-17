"""Two distinct REAL setuptools wheel builds from synthetic 226-module RC Git.

Integration rehearsal only: 3.13's --ignore-requires-python never belongs in
shipping installer; no real project code, live orders, services or production.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from scripts import mmt_v040_dual_wheel_repro_audit_v1 as dual
from scripts import mmt_v040_offline_stable_staging_v1 as staging
from scripts import mmt_v040_signed_artifact_preflight_v1 as stable
from test_mmt_v040_rc_overlay_signed_custody_v1 import canonical, example


def test_two_independent_setuptools_invocations_match_signed_rc_overlay(
    example, tmp_path: Path
):
    root, modules, sign_fixture, private = example
    values = sign_fixture()
    env = dict(os.environ)
    env.update(SOURCE_DATE_EPOCH="1792100000", PYTHONHASHSEED="0",
               PIP_NO_INDEX="1", PIP_DISABLE_PIP_VERSION_CHECK="1",
               PYTHONDONTWRITEBYTECODE="1")
    outputs = []
    for attempt in (1, 2):
        staging_path = tmp_path / f"stage-{attempt}"
        evidence = staging.stage(
            repository=root, destination=staging_path,
            expected_source_commit=values["expected_source_commit"],
            expected_public_tree_sha1=values["expected_public_tree_sha1"],
            expected_lock_sha256=values["expected_lock_sha256"],
        )
        assert evidence["staged_module_count"] == 226
        wheel_dir = tmp_path / f"wheel-build-{attempt}"
        wheel_dir.mkdir(mode=0o700)
        command = [
            sys.executable, "-m", "pip", "wheel", "--no-index", "--no-deps",
            "--no-build-isolation",
        ]
        # Never bypass Python compatibility on an actual CPython 3.12 test host.
        if sys.version_info[:2] != (3, 12):
            command.append("--ignore-requires-python")
        command.extend(["--wheel-dir", str(wheel_dir), str(staging_path)])
        process = subprocess.run(command, env=env, capture_output=True,
                                 text=True, timeout=90, check=False)
        assert process.returncode == 0, process.stderr[-1000:]
        path = wheel_dir / stable.WHEEL_NAME
        assert path.is_file()
        with zipfile.ZipFile(path) as z:
            members = z.namelist()
            assert len(members) == 231  # 226 source + 5 dist-info
            assert len([m for m in members if m.startswith("naseri_markets/")]) == 226
            record = z.read(stable.DIST + "RECORD")
        assert stable._wheel(path.read_bytes(), hashlib.sha256(record).hexdigest())[
            "record_verified"
        ] is True
        outputs.append((path, record))
    first, first_record = outputs[0]
    second, second_record = outputs[1]
    first_bytes, second_bytes = first.read_bytes(), second.read_bytes()
    assert first_bytes == second_bytes  # real builds, NOT copied artifact files
    assert first_record == second_record
    key = Ed25519PrivateKey.generate()  # private test key; never saved to GitHub
    public = key.public_key()
    pem = public.public_bytes(serialization.Encoding.PEM,
                              serialization.PublicFormat.SubjectPublicKeyInfo)
    spki = public.public_bytes(serialization.Encoding.DER,
                               serialization.PublicFormat.SubjectPublicKeyInfo)
    key_fingerprint = hashlib.sha256(spki).hexdigest()
    manifest = {
        "schema": 1, "distribution": stable.DIST_NAME,
        "version": stable.VERSION, "purpose": "offline-paper-release-only",
        "source_commit": values["expected_source_commit"],
        "source_date_epoch": 1792100000,
        "wheel_filename": stable.WHEEL_NAME,
        "wheel_sha256": hashlib.sha256(first_bytes).hexdigest(),
        "wheel_size": len(first_bytes),
        "wheel_record_sha256": hashlib.sha256(first_record).hexdigest(),
    }
    manifest_bytes = canonical(manifest)
    policy = {"schema": 1, "revision": 1,
              "active_signers": [key_fingerprint],
              "revoked_signers": [], "min_source_date_epoch": 1792000000}
    policy_bytes = canonical(policy)
    (private / "manifest.json").write_bytes(manifest_bytes)
    (private / "sig.bin").write_bytes(key.sign(stable.DOMAIN + manifest_bytes))
    (private / "pub.pem").write_bytes(pem)
    (private / "policy.json").write_bytes(policy_bytes)
    values.update(
        wheel=first, signature=private / "sig.bin",
        trusted_public_key=private / "pub.pem",
        trusted_public_key_spki_sha256=key_fingerprint,
        expected_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        expected_policy_sha256=hashlib.sha256(policy_bytes).hexdigest(),
        second_wheel=second,
        expected_second_wheel_sha256=hashlib.sha256(second_bytes).hexdigest(),
    )
    checked = dual.audit(**values)
    assert checked["byte_identical"] is True
    assert checked["public_modules_verified"] == 226
    assert checked["independent_build_proven"] is False  # no external builder attestation
    assert checked["fresh_build_on_python312_proven"] is False
    assert checked["public_release_authorized"] is False
    assert checked["live_trading_authorized"] is False
    assert len(modules) == 226
    # Even a newly pinned, tampered SECOND artifact must be rejected.
    second.write_bytes(second_bytes + b"modified after build")
    values["expected_second_wheel_sha256"] = hashlib.sha256(second.read_bytes()).hexdigest()
    with pytest.raises(dual.DualWheelRefused,
                       match="V040_DUAL_WHEELS_NOT_BYTE_IDENTICAL"):
        dual.audit(**values)
