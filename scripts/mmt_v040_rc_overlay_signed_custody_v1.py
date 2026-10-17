"""Read-only v0.4.0 stable Wheel custody against a pinned clean RC checkout.

A publisher's signed stable-wheel manifest names the *original* RC Git commit;
the only allowed metadata change is the exact reviewed, read-only version overlay.
This proof does not make an RC commit a stable Git commit or grant publication.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import zipfile
from pathlib import Path

from scripts import mmt_v040_offline_stable_staging_v1 as staging
from scripts import mmt_v040_public_source_snapshot_audit_v1 as snapshot
from scripts import mmt_v040_signed_artifact_preflight_v1 as stable

HEX64 = re.compile(r"[0-9a-f]{64}\Z")


class OverlayCustodyRefused(ValueError):
    """Bounded, non-secret admission refusal code."""


def audit(*, repository: Path, manifest: Path, signature: Path, wheel: Path,
          trusted_public_key: Path, trusted_public_key_spki_sha256: str,
          policy: Path, expected_policy_sha256: str,
          expected_manifest_sha256: str, expected_source_commit: str,
          expected_public_tree_sha1: str, expected_lock_sha256: str,
          expected_overlay_sha256: str) -> dict:
    """Prove signed stable Wheel contents match verified RC bytes + one overlay.

    Signature/trust are independently pinned; all audit operations are read-only.
    Requires current package source to remain RC. No stage directory is made.
    """
    if os.environ.get("MMT_NONPRODUCTION") != "1" or "MMT_PRODUCTION" in os.environ:
        raise OverlayCustodyRefused("V040_OVERLAY_NONPRODUCTION_REQUIRED")
    if (type(expected_overlay_sha256) is not str
            or not HEX64.fullmatch(expected_overlay_sha256)):
        raise OverlayCustodyRefused("V040_OVERLAY_EXTERNAL_PIN_REQUIRED")
    signature_evidence = stable.verify(
        manifest=manifest, signature=signature, wheel=wheel,
        trusted_public_key=trusted_public_key,
        trusted_public_key_spki_sha256=trusted_public_key_spki_sha256,
        policy=policy, expected_policy_sha256=expected_policy_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_source_commit=expected_source_commit,
    )
    source_evidence = snapshot.audit(
        repository=repository, expected_source_commit=expected_source_commit,
        expected_public_tree_sha1=expected_public_tree_sha1,
        expected_lock_sha256=expected_lock_sha256,
    )
    metadata, _ = staging._metadata(repository)
    overlay_hash = hashlib.sha256(metadata).hexdigest()
    if overlay_hash != expected_overlay_sha256:
        raise OverlayCustodyRefused("V040_OVERLAY_METADATA_PIN_MISMATCH")
    lock = snapshot._read_snapshot(repository / snapshot.SNAPSHOT_PATH,
                                   expected_lock_sha256)
    raw = stable._read(wheel, stable.MAX_WHEEL)
    if hashlib.sha256(raw).hexdigest() != signature_evidence["wheel_sha256"]:
        raise OverlayCustodyRefused("V040_SIGNED_WHEEL_CHANGED")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            module_names = {name for name in archive.namelist()
                            if name.startswith("naseri_markets/")}
            expected_names = {m["path"] for m in lock["modules"]}
            if module_names != expected_names:
                raise OverlayCustodyRefused("V040_OVERLAY_MODULE_SET_MISMATCH")
            for module in lock["modules"]:
                path = module["path"]
                source = repository / path
                if source.is_symlink():
                    raise OverlayCustodyRefused("V040_OVERLAY_MODULE_UNSAFE")
                original = source.read_bytes()
                if (len(original) != module["size"]
                        or hashlib.sha1(b"blob " + str(len(original)).encode()
                                        + b"\0" + original).hexdigest()
                        != module["git_blob_sha1"]):
                    raise OverlayCustodyRefused("V040_OVERLAY_SOURCE_CHANGED")
                staging._check_source_module(original, path)
                if archive.read(path) != original:
                    raise OverlayCustodyRefused("V040_OVERLAY_MODULE_BYTES_MISMATCH")
    except OverlayCustodyRefused:
        raise
    except (OSError, KeyError, RuntimeError, ValueError, zipfile.BadZipFile) as exc:
        raise OverlayCustodyRefused("V040_OVERLAY_WHEEL_READ_REFUSED") from exc
    if snapshot._git(repository, "status", "--porcelain=v1",
                     "--untracked-files=all"):
        raise OverlayCustodyRefused("V040_OVERLAY_CHECKOUT_CHANGED")
    return {
        "verdict": "V040_RC_OVERLAY_SIGNED_SOURCE_CUSTODY_PASS_RELEASE_DENIED",
        "original_rc_source_commit": expected_source_commit,
        "public_source_tree_sha1": expected_public_tree_sha1,
        "public_snapshot_sha256": expected_lock_sha256,
        "approved_overlay_metadata_sha256": overlay_hash,
        "signed_stable_wheel_sha256": signature_evidence["wheel_sha256"],
        "public_modules_verified": source_evidence["public_modules_verified"],
        "signed_wheel_record_verified": signature_evidence["record_verified"],
        "signer_spki_sha256": signature_evidence["signer_spki_sha256"],
        "rc_git_commit_is_a_stable_release_commit": False,
        "writes_performed": False,
        "install_authorized": False,
        "public_release_authorized": False,
        "live_trading_authorized": False,
        "telegram_publication_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repository", "manifest", "signature", "wheel",
                 "trusted-public-key", "policy"):
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ("trusted-public-key-spki-sha256", "expected-policy-sha256",
                 "expected-manifest-sha256", "expected-source-commit",
                 "expected-public-tree-sha1", "expected-lock-sha256",
                 "expected-overlay-sha256"):
        parser.add_argument("--" + name, required=True)
    args = vars(parser.parse_args(argv))
    args = {key.replace("-", "_"): value for key, value in args.items()}
    try:
        output = audit(**args)
    except (OverlayCustodyRefused, staging.StableStageRefused,
            snapshot.PublicSnapshotRefused, stable.StableArtifactRefused,
            OSError) as exc:
        reason = (str(exc) if isinstance(exc, ValueError)
                  else "V040_OVERLAY_IO_REFUSED")
        print(json.dumps({
            "verdict": "V040_RC_OVERLAY_CUSTODY_REFUSED", "reason": reason,
            "install_authorized": False, "public_release_authorized": False,
            "live_trading_authorized": False,
        }, sort_keys=True))
        return 2
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
