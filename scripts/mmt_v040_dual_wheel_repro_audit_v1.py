"""Read-only two-artifact equality after signed RC-overlay source custody.

Separate files are not proof of separate builders. This gate never builds,
installs, signs, publishes, or authorizes production, Telegram, or trading.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from pathlib import Path

from scripts import mmt_v040_rc_overlay_signed_custody_v1 as overlay
from scripts import mmt_v040_signed_artifact_preflight_v1 as stable

SHA256 = re.compile(r"[0-9a-f]{64}\\Z")


class DualWheelRefused(ValueError):
    """Constant failure codes, not user-supplied paths or secrets."""


def audit(*, second_wheel: Path, expected_second_wheel_sha256: str,
          repository: Path, manifest: Path, signature: Path, wheel: Path,
          trusted_public_key: Path, trusted_public_key_spki_sha256: str,
          policy: Path, expected_policy_sha256: str,
          expected_manifest_sha256: str, expected_source_commit: str,
          expected_public_tree_sha1: str, expected_lock_sha256: str,
          expected_overlay_sha256: str) -> dict:
    if os.environ.get("MMT_NONPRODUCTION") != "1" or "MMT_PRODUCTION" in os.environ:
        raise DualWheelRefused("V040_DUAL_NONPRODUCTION_REQUIRED")
    if (type(expected_second_wheel_sha256) is not str
            or not SHA256.fullmatch(expected_second_wheel_sha256)):
        raise DualWheelRefused("V040_DUAL_EXTERNAL_SECOND_PIN_REQUIRED")
    if (not isinstance(second_wheel, Path) or not isinstance(wheel, Path)
            or not second_wheel.is_absolute() or not wheel.is_absolute()
            or second_wheel.name != stable.WHEEL_NAME
            or wheel.name != stable.WHEEL_NAME
            or second_wheel.is_symlink() or wheel.is_symlink()
            or second_wheel.parent.is_symlink() or wheel.parent.is_symlink()
            or second_wheel == wheel or second_wheel.parent == wheel.parent):
        raise DualWheelRefused("V040_DUAL_DISTINCT_ARTIFACT_PATHS_REQUIRED")
    try:
        first_stat, second_stat = wheel.stat(), second_wheel.stat()
        if (not stat.S_ISREG(first_stat.st_mode) or not stat.S_ISREG(second_stat.st_mode)
                or first_stat.st_nlink != 1 or second_stat.st_nlink != 1
                or (first_stat.st_dev, first_stat.st_ino)
                == (second_stat.st_dev, second_stat.st_ino)
                or wheel.parent.resolve(strict=True)
                == second_wheel.parent.resolve(strict=True)):
            raise DualWheelRefused("V040_DUAL_DISTINCT_REGULAR_FILES_REQUIRED")
    except OSError as exc:
        raise DualWheelRefused("V040_DUAL_ARTIFACT_UNREADABLE") from exc
    # Full positive signature, trust policy, pinned clean RC Git tree, exact
    # stable overlay and ALL 226 module source bytes are checked first.
    evidence = overlay.audit(
        repository=repository, manifest=manifest, signature=signature,
        wheel=wheel, trusted_public_key=trusted_public_key,
        trusted_public_key_spki_sha256=trusted_public_key_spki_sha256,
        policy=policy, expected_policy_sha256=expected_policy_sha256,
        expected_manifest_sha256=expected_manifest_sha256,
        expected_source_commit=expected_source_commit,
        expected_public_tree_sha1=expected_public_tree_sha1,
        expected_lock_sha256=expected_lock_sha256,
        expected_overlay_sha256=expected_overlay_sha256,
    )
    if (evidence.get("public_modules_verified") != 226
            or evidence.get("signed_wheel_record_verified") is not True
            or evidence.get("rc_git_commit_is_a_stable_release_commit") is not False
            or evidence.get("install_authorized") is not False
            or evidence.get("live_trading_authorized") is not False):
        raise DualWheelRefused("V040_DUAL_UNSAFE_CUSTODY_EVIDENCE")
    original = stable._read(wheel, stable.MAX_WHEEL)
    second = stable._read(second_wheel, stable.MAX_WHEEL)
    a = hashlib.sha256(original).hexdigest()
    b = hashlib.sha256(second).hexdigest()
    if a != evidence["signed_stable_wheel_sha256"]:
        raise DualWheelRefused("V040_DUAL_FIRST_ARTIFACT_CHANGED")
    if b != expected_second_wheel_sha256:
        raise DualWheelRefused("V040_DUAL_SECOND_EXTERNAL_PIN_MISMATCH")
    if original != second:
        raise DualWheelRefused("V040_DUAL_WHEELS_NOT_BYTE_IDENTICAL")
    return {
        "verdict": "V040_TWO_DISTINCT_SIGNED_WHEEL_FILES_IDENTICAL_RELEASE_DENIED",
        "first_wheel_sha256": a,
        "second_wheel_sha256": b,
        "matching_byte_count": len(original),
        "source_commit": evidence["original_rc_source_commit"],
        "public_modules_verified": evidence["public_modules_verified"],
        "second_file_has_independent_external_sha256_pin": True,
        "distinct_wheel_files": True,
        "byte_identical": True,
        "independent_build_proven": False,
        "fresh_build_on_python312_proven": False,
        "source_package_version_promoted": False,
        "writes_performed": False,
        "install_authorized": False,
        "public_release_authorized": False,
        "live_trading_authorized": False,
        "telegram_publication_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("repository", "manifest", "signature", "wheel", "second-wheel",
                 "trusted-public-key", "policy"):
        parser.add_argument("--" + name, required=True, type=Path)
    for name in ("expected-second-wheel-sha256", "trusted-public-key-spki-sha256",
                 "expected-policy-sha256", "expected-manifest-sha256",
                 "expected-source-commit", "expected-public-tree-sha1",
                 "expected-lock-sha256", "expected-overlay-sha256"):
        parser.add_argument("--" + name, required=True)
    args = {key.replace("-", "_"): value
            for key, value in vars(parser.parse_args(argv)).items()}
    try:
        result = audit(**args)
    except (DualWheelRefused, overlay.OverlayCustodyRefused,
            stable.StableArtifactRefused, OSError, ValueError) as exc:
        message = str(exc) if isinstance(exc, (DualWheelRefused,
                              overlay.OverlayCustodyRefused,
                              stable.StableArtifactRefused)) else "V040_DUAL_AUDIT_REFUSED"
        print(json.dumps({
            "verdict": "V040_DUAL_WHEEL_REFUSED", "reason": message,
            "install_authorized": False, "public_release_authorized": False,
            "live_trading_authorized": False,
        }, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
