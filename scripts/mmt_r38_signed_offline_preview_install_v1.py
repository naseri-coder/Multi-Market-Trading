"""R38: signed+revocation-pinned offline preview installer facade.

New strict pathway; does not alter the legacy unsigned R35 *preview* CLI.
No release grant, no publisher private key, no broker or Telegram service.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from pathlib import Path

from scripts import mmt_r35_offline_preview_install_v1 as r35
from scripts import mmt_r37_offline_signed_manifest_verify_v1 as r37

POLICY_FIELDS = frozenset({
    "schema", "revision", "active_keys", "revoked_keys",
    "min_source_date_epoch",
})
EVIDENCE_NAME = "signed-preview-install-evidence.json"


class R38Refused(ValueError):
    """Constant failure reason; no release authorization can be inferred."""


def _policy(path: Path, expected_hash: str, key_fingerprint: str) -> dict:
    """Only a separately pinned local trust snapshot may authorize a key."""
    if type(expected_hash) is not str or not r37.SHA256.fullmatch(expected_hash):
        raise R38Refused("R38_EXTERNAL_POLICY_HASH_REQUIRED")
    raw = r37._read(path, 8192)
    if hashlib.sha256(raw).hexdigest() != expected_hash:
        raise R38Refused("R38_POLICY_HASH_MISMATCH")
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=r37._unique_pairs)
    except (UnicodeError, ValueError, TypeError) as exc:
        if isinstance(exc, r37.R37Refused):
            raise R38Refused("R38_POLICY_DUPLICATE_KEY") from exc
        raise R38Refused("R38_POLICY_JSON_INVALID") from exc
    if type(data) is not dict or set(data) != POLICY_FIELDS:
        raise R38Refused("R38_POLICY_SCHEMA_INVALID")
    if (json.dumps(data, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=True).encode("utf-8") + b"\n" != raw):
        raise R38Refused("R38_POLICY_NONCANONICAL")
    active = data["active_keys"]
    revoked = data["revoked_keys"]
    if (type(data["schema"]) is not int or data["schema"] != 1
            or type(data["revision"]) is not int or data["revision"] < 1
            or type(data["min_source_date_epoch"]) is not int
            or not 315532800 <= data["min_source_date_epoch"] <= 4102444800
            or type(active) is not list or type(revoked) is not list
            or len(active) > 32 or len(revoked) > 128
            or not all(type(x) is str and r37.SHA256.fullmatch(x)
                       for x in [*active, *revoked])
            or len(active) != len(set(active))
            or len(revoked) != len(set(revoked))
            or set(active) & set(revoked)):
        raise R38Refused("R38_POLICY_VALUES_INVALID")
    if key_fingerprint in revoked:
        raise R38Refused("R38_SIGNING_KEY_REVOKED")
    if key_fingerprint not in active:
        raise R38Refused("R38_SIGNING_KEY_NOT_ACTIVE")
    return data


def preflight(*, manifest: Path, signature: Path, wheel: Path,
              trusted_public_key: Path, trusted_public_key_spki_sha256: str,
              expected_source_commit: str, expected_manifest_sha256: str,
              policy: Path, expected_policy_sha256: str,
              destination: Path) -> dict:
    """Read-only: exact trust pins -> key policy -> signature -> R35 archive."""
    if (os.environ.get("MMT_NONPRODUCTION") != "1"
            or "MMT_PRODUCTION" in os.environ):
        raise R38Refused("R38_NONPRODUCTION_REQUIRED")
    if (type(expected_manifest_sha256) is not str
            or not r37.SHA256.fullmatch(expected_manifest_sha256)
            or type(trusted_public_key_spki_sha256) is not str
            or not r37.SHA256.fullmatch(trusted_public_key_spki_sha256)):
        raise R38Refused("R38_EXTERNAL_TRUST_PINS_REQUIRED")
    trust = _policy(policy, expected_policy_sha256,
                    trusted_public_key_spki_sha256)
    raw = r37._read(manifest, 4096)
    if hashlib.sha256(raw).hexdigest() != expected_manifest_sha256:
        raise R38Refused("R38_MANIFEST_PIN_MISMATCH")
    description = r37._manifest(raw)
    if description["source_date_epoch"] < trust["min_source_date_epoch"]:
        raise R38Refused("R38_OLD_MANIFEST_REPLAY_DENIED")
    proof = r37.verify(
        manifest=manifest, signature=signature, wheel=wheel,
        trusted_public_key=trusted_public_key,
        trusted_public_key_spki_sha256=trusted_public_key_spki_sha256,
        expected_source_commit=expected_source_commit,
    )
    if (proof["manifest_signature_valid"] is not True
            or proof["wheel_sha256"] != description["wheel_sha256"]
            or proof["install_authorized"] is not False
            or proof["live_authorized"] is not False):
        raise R38Refused("R38_SIGNED_PROOF_UNSAFE")
    checked = r35.check(
        wheel=wheel, sha256=proof["wheel_sha256"], destination=destination,
    )
    if (checked["verdict"] != "R35_OFFLINE_WHEEL_PREFLIGHT_PASS"
            or checked["wheel_sha256"] != proof["wheel_sha256"]
            or checked["writes_performed"] is not False
            or checked["live_authorized"] is not False):
        raise R38Refused("R38_R35_PREFLIGHT_UNSAFE")
    return {
        "verdict": "R38_SIGNED_OFFLINE_PREFLIGHT_PASS_RELEASE_DENIED",
        "wheel_sha256": proof["wheel_sha256"],
        "manifest_sha256": expected_manifest_sha256,
        "trusted_key_spki_sha256": trusted_public_key_spki_sha256,
        "policy_sha256": expected_policy_sha256,
        "policy_revision": trust["revision"],
        "source_commit": expected_source_commit,
        "signed_preview_verified": True,
        "writes_performed": False,
        "install_authorized": False,
        "public_release_authorized": False,
        "live_authorized": False,
        "broker_orders_enabled": False,
        "telegram_enabled": False,
    }


def install(*, ack: bool, **options) -> dict:
    """Only explicit nonroot opt-in can create one new private R35 preview."""
    r35._gate(install=True, ack=ack)
    proof = preflight(**options)
    destination = options["destination"]
    verified_wheel = proof["wheel_sha256"]  # Never take pin from user Wheel itself.
    installed = r35.install(
        wheel=options["wheel"], sha256=verified_wheel,
        destination=destination, ack=ack,
    )
    if (installed["verdict"]
            != "R35_INSTALLED_OFFLINE_PREVIEW_PASS_RELEASE_DENIED"
            or installed["wheel_sha256"] != verified_wheel
            or installed["installation_isolated"] is not True
            or installed["live_authorized"] is not False):
        raise R38Refused("R38_R35_INSTALL_RESULT_UNSAFE")
    evidence = dict(proof)
    evidence.update(
        verdict="R38_SIGNED_OFFLINE_INSTALLED_PREVIEW_PASS_RELEASE_DENIED",
        writes_performed=True, installation_isolated=True,
    )
    # Save the external signed trust pins *after* R35 has verified & installed
    # this exact digest. Failure leaves the private target for investigation;
    # no automatic rollback, merging, connected services, or cleanup.
    path = destination / EVIDENCE_NAME
    fd = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600,
    )
    with os.fdopen(fd, "w", encoding="utf-8") as file:
        json.dump(evidence, file, sort_keys=True)
        file.write("\n")
        file.flush()
        os.fsync(file.fileno())
    return evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "manifest", "signature", "wheel", "trusted-public-key",
        "policy", "destination",
    ):
        parser.add_argument("--" + name, required=True, type=Path)
    for name in (
        "trusted-public-key-spki-sha256", "expected-source-commit",
        "expected-manifest-sha256", "expected-policy-sha256",
    ):
        parser.add_argument("--" + name, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-only", action="store_true")
    mode.add_argument("--install", action="store_true")
    parser.add_argument("--ack-offline-preview-install", action="store_true")
    args = parser.parse_args(argv)
    params = {
        "manifest": args.manifest,
        "signature": args.signature,
        "wheel": args.wheel,
        "trusted_public_key": args.trusted_public_key,
        "trusted_public_key_spki_sha256":
            args.trusted_public_key_spki_sha256,
        "expected_source_commit": args.expected_source_commit,
        "expected_manifest_sha256": args.expected_manifest_sha256,
        "policy": args.policy,
        "expected_policy_sha256": args.expected_policy_sha256,
        "destination": args.destination,
    }
    try:
        result = (
            install(ack=args.ack_offline_preview_install, **params)
            if args.install else preflight(**params)
        )
    except (R38Refused, r37.R37Refused, r35.R35Refused,
            OSError, ValueError, RuntimeError, KeyError) as exc:
        reason = (str(exc) if isinstance(
            exc, (R38Refused, r37.R37Refused, r35.R35Refused)
        ) else "R38_SIGNED_PREVIEW_INSTALL_REFUSED")
        print(json.dumps({
            "verdict": "R38_SIGNED_PREVIEW_REFUSED", "reason": reason,
            "writes_authorized": False,
            "public_release_authorized": False,
            "live_authorized": False,
        }, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
