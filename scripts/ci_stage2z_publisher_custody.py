"""Stage 2Z: real-source, disposable TEST-key wheel custody rehearsal.

NOT publisher approval: ephemeral Ed25519 key generated in memory. This file
contains no key upload, signing service, installation, publication or LIVE path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from scripts import mmt_v040_offline_stable_staging_v1 as stage
from scripts import mmt_v040_public_source_snapshot_audit_v1 as snapshot
from scripts import mmt_v040_rc_overlay_signed_custody_v1 as overlay
from scripts import mmt_v040_signed_artifact_preflight_v1 as stable

PUBLIC_TREE_SHA1 = "511e9346d88280f3be7c80367f8822a8eaa24dd7"
SOURCE_SNAPSHOT_SHA256 = "c2554a8a1c3a46d1675e8e44429c017f6981758df012d5b5feecab353bcf9b9c"
APPROVED_OVERLAY_SHA256 = "11d87431c863a20514541d8c2eaf70e47555d0ca2e2dbd8d1ded11c994ac01d7"
RECORD_NAME = "multi_market_trading-0.4.0.dist-info/RECORD"
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")


def canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


def command(*argv: str, cwd: Path | None = None, env: dict | None = None) -> str:
    run = subprocess.run(argv, cwd=cwd, env=env, check=True,
                         capture_output=True, text=True, timeout=240)
    return run.stdout.strip()


def rehearsal(repository: Path, expected_source_commit: str) -> dict:
    if ("MMT_PRODUCTION" in os.environ or os.getenv("MMT_NONPRODUCTION") != "1"
            or os.getenv("APP_ENV") != "test"):
        raise ValueError("STAGE2Z_NONPRODUCTION_ONLY")
    if (not repository.is_absolute() or repository.is_symlink()
            or not repository.is_dir() or not COMMIT_RE.fullmatch(expected_source_commit)):
        raise ValueError("STAGE2Z_EXPLICIT_REPO_AND_SHA_REQUIRED")
    if command("git", "rev-parse", "HEAD", cwd=repository) != expected_source_commit:
        raise ValueError("STAGE2Z_GITHUB_EXACT_SHA_MISMATCH")
    if command("git", "status", "--porcelain=v1", "--untracked-files=all",
               cwd=repository):
        raise ValueError("STAGE2Z_DIRTY_REPOSITORY")
    epoch = int(command("git", "show", "-s", "--format=%ct", "HEAD", cwd=repository))
    environment = {**os.environ, "SOURCE_DATE_EPOCH": str(epoch),
                   "PYTHONDONTWRITEBYTECODE": "1", "MMT_NONPRODUCTION": "1"}
    evidence = snapshot.audit(
        repository=repository, expected_source_commit=expected_source_commit,
        expected_public_tree_sha1=PUBLIC_TREE_SHA1,
        expected_lock_sha256=SOURCE_SNAPSHOT_SHA256,
    )
    assert evidence["public_modules_verified"] == 226

    with tempfile.TemporaryDirectory(prefix="mmt-stage2z-") as scratch:
        private = Path(scratch)
        os.chmod(private, 0o700)
        first = private / "source-a"
        second = private / "source-b"
        for dest in (first, second):
            result = stage.stage(
                repository=repository, destination=dest,
                expected_source_commit=expected_source_commit,
                expected_public_tree_sha1=PUBLIC_TREE_SHA1,
                expected_lock_sha256=SOURCE_SNAPSHOT_SHA256,
            )
            assert result["staged_module_count"] == 226
            assert result["staged_metadata_sha256"] == APPROVED_OVERLAY_SHA256
        build_paths = []
        for index, staged in enumerate((first, second)):
            wheels = private / f"wheels-{index}"
            wheels.mkdir(mode=0o700)
            command(sys.executable, "-m", "pip", "wheel", "--no-index",
                    "--no-build-isolation", "--no-deps", "--wheel-dir",
                    str(wheels), str(staged), env=environment)
            artifact = wheels / stable.WHEEL_NAME
            if not artifact.is_file():
                raise ValueError("STAGE2Z_STABLE_WHEEL_MISSING")
            build_paths.append(artifact)

        wheel = build_paths[0].read_bytes()
        if wheel != build_paths[1].read_bytes():
            raise ValueError("STAGE2Z_INDEPENDENT_WHEEL_BUILD_MISMATCH")
        if not 128 <= len(wheel) <= stable.MAX_WHEEL:
            raise ValueError("STAGE2Z_WHEEL_SIZE_REFUSED")
        with zipfile.ZipFile(build_paths[0]) as archive:
            record = archive.read(RECORD_NAME)

        # A throwaway key demonstrates the cryptographic verifier. It is NOT
        # an authorized publisher key, and is never written to disk.
        test_key = Ed25519PrivateKey.generate()
        public_key = test_key.public_key()
        pem = public_key.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        spki = public_key.public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        fingerprint = hashlib.sha256(spki).hexdigest()
        manifest = {
            "schema": 1,
            "distribution": stable.DIST_NAME,
            "version": "0.4.0",
            "purpose": "offline-paper-release-only",
            "source_commit": expected_source_commit,
            "source_date_epoch": epoch,
            "wheel_filename": stable.WHEEL_NAME,
            "wheel_sha256": hashlib.sha256(wheel).hexdigest(),
            "wheel_size": len(wheel),
            "wheel_record_sha256": hashlib.sha256(record).hexdigest(),
        }
        policy = {
            "schema": 1, "revision": 1, "active_signers": [fingerprint],
            "revoked_signers": [], "min_source_date_epoch": epoch,
        }
        signed = canonical(manifest)
        policy_bytes = canonical(policy)
        manifest_path = private / "manifest.test-only.json"
        signature_path = private / "signature.test-only.ed25519"
        key_path = private / "public-test-only.pem"
        policy_path = private / "policy.test-only.json"
        manifest_path.write_bytes(signed)
        signature_path.write_bytes(test_key.sign(stable.DOMAIN + signed))
        key_path.write_bytes(pem)
        policy_path.write_bytes(policy_bytes)
        verification_args = {
            "manifest": manifest_path, "signature": signature_path,
            "wheel": build_paths[0], "trusted_public_key": key_path,
            "trusted_public_key_spki_sha256": fingerprint,
            "policy": policy_path,
            "expected_policy_sha256": hashlib.sha256(policy_bytes).hexdigest(),
            "expected_manifest_sha256": hashlib.sha256(signed).hexdigest(),
            "expected_source_commit": expected_source_commit,
        }
        verified = stable.verify(**verification_args)
        assert verified["record_verified"] is True
        custody = overlay.audit(
            repository=repository, expected_public_tree_sha1=PUBLIC_TREE_SHA1,
            expected_lock_sha256=SOURCE_SNAPSHOT_SHA256,
            expected_overlay_sha256=APPROVED_OVERLAY_SHA256,
            **verification_args,
        )
        assert custody["public_modules_verified"] == 226
        assert custody["wheel_readme_matches_reviewed_source"] is True
        assert custody["wheel_summary_matches_reviewed_source"] is True

        # Explicit negative: signed bytes altered after creation.
        signature_path.write_bytes(b"\x00" * 64)
        try:
            stable.verify(**verification_args)
        except stable.StableArtifactRefused as exc:
            if str(exc) != "V040_SIGNATURE_VERIFICATION_FAILED":
                raise
        else:
            raise ValueError("STAGE2Z_FORGED_SIGNATURE_WAS_ACCEPTED")

        # Explicit negative: key not in independently pinned signer policy.
        signature_path.write_bytes(test_key.sign(stable.DOMAIN + signed))
        revoked = {**policy, "active_signers": [],
                   "revoked_signers": [fingerprint]}
        revoked_bytes = canonical(revoked)
        policy_path.write_bytes(revoked_bytes)
        revoked_args = {**verification_args,
                        "expected_policy_sha256": hashlib.sha256(revoked_bytes).hexdigest()}
        try:
            stable.verify(**revoked_args)
        except stable.StableArtifactRefused as exc:
            if str(exc) != "V040_SIGNER_REVOKED":
                raise
        else:
            raise ValueError("STAGE2Z_REVOKED_SIGNER_WAS_ACCEPTED")

    if command("git", "status", "--porcelain=v1", "--untracked-files=all",
               cwd=repository):
        raise ValueError("STAGE2Z_SOURCE_MODIFIED")
    return {
        "verdict": "STAGE2Z_REAL_SOURCE_TEST_SIGNER_REHEARSAL_PASS_RELEASE_BLOCKED",
        "source_commit": expected_source_commit,
        "verified_source_modules": 226,
        "dual_wheels_identical": True,
        "wheel_sha256": hashlib.sha256(wheel).hexdigest(),
        "signed_record_verified": True,
        "forged_signature_rejected": True,
        "revoked_signer_rejected": True,
        "test_key_only": True,
        "independent_approved_publisher_verified": False,
        "publication_authorized": False,
        "main_merge_authorized": False,
        "live_trading_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--expected-source-commit", required=True)
    args = parser.parse_args()
    try:
        report = rehearsal(args.repository, args.expected_source_commit)
    except Exception as exc:
        # Avoid exposing credentials or raw exception messages in CI output.
        print(json.dumps({"verdict": "STAGE2Z_REHEARSAL_FAILED",
                          "exception_type": type(exc).__name__,
                          "publication_authorized": False}))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
