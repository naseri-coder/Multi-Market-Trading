"""R38 signed-only offline preview gateway: R37 trust gate before R35.

Read-only preflight or explicitly acknowledged nonroot offline install into a
new isolated destination. No signing key, market data, Telegram, deployment or
production authorization; this does not replace the separate R36 source audit.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
from pathlib import Path

from scripts import mmt_r35_offline_preview_install_v1 as r35
from scripts import mmt_r37_offline_signed_manifest_verify_v1 as r37

POLICY_FIELDS = frozenset({
    "schema", "purpose", "approved_source_commit", "approved_wheel_sha256",
    "trusted_key_spki_sha256", "minimum_source_date_epoch",
    "revoked_key_spki_sha256",
})


class R38Refused(ValueError):
    """Constant fail-closed operator reason codes, without private paths."""


def _policy(path: Path, independently_pinned_sha256: str) -> dict:
    if (type(independently_pinned_sha256) is not str
            or r37.SHA256.fullmatch(independently_pinned_sha256) is None):
        raise R38Refused("R38_EXTERNAL_POLICY_PIN_REQUIRED")
    raw = r37._read(path, 8192)
    if hashlib.sha256(raw).hexdigest() != independently_pinned_sha256:
        raise R38Refused("R38_POLICY_PIN_MISMATCH")
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=r37._unique_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeError, ValueError, TypeError) as exc:
        if isinstance(exc, r37.R37Refused):
            raise R38Refused("R38_POLICY_DUPLICATE_KEY") from exc
        raise R38Refused("R38_POLICY_INVALID_JSON") from exc
    if type(value) is not dict or set(value) != POLICY_FIELDS:
        raise R38Refused("R38_POLICY_FIELDS_INVALID")
    canonical = (json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8") + b"\n")
    if canonical != raw:
        raise R38Refused("R38_POLICY_NOT_CANONICAL")
    revoked = value["revoked_key_spki_sha256"]
    if (type(value["schema"]) is not int or value["schema"] != 1
            or value["purpose"] != "offline-preview-only"
            or type(value["approved_source_commit"]) is not str
            or r37.COMMIT.fullmatch(value["approved_source_commit"]) is None
            or type(value["approved_wheel_sha256"]) is not str
            or r37.SHA256.fullmatch(value["approved_wheel_sha256"]) is None
            or type(value["trusted_key_spki_sha256"]) is not str
            or r37.SHA256.fullmatch(value["trusted_key_spki_sha256"]) is None
            or type(value["minimum_source_date_epoch"]) is not int
            or not 315532800 <= value["minimum_source_date_epoch"] <= 4102444800
            or type(revoked) is not list or len(revoked) > 128
            or any(type(item) is not str or r37.SHA256.fullmatch(item) is None
                   for item in revoked)
            or revoked != sorted(set(revoked))):
        raise R38Refused("R38_POLICY_VALUES_INVALID")
    if value["trusted_key_spki_sha256"] in revoked:
        raise R38Refused("R38_TRUSTED_KEY_REVOKED")
    return value


def gate(*, manifest: Path, signature: Path, wheel: Path,
         trusted_public_key: Path, policy: Path, policy_sha256: str,
         destination: Path, install: bool, ack: bool) -> dict:
    if (os.environ.get("MMT_NONPRODUCTION") != "1"
            or "MMT_PRODUCTION" in os.environ
            or sys.version_info[:2] != (3, 12)):
        raise R38Refused("R38_NONPRODUCTION_PY312_REQUIRED")
    if install and not ack:
        raise R38Refused("R38_EXPLICIT_SIGNED_INSTALL_ACK_REQUIRED")
    if not install and ack:
        raise R38Refused("R38_CHECK_ONLY_CANNOT_INSTALL")
    record = _policy(policy, policy_sha256)
    signed_bytes = r37._read(manifest, 4096)
    signed = r37._manifest(signed_bytes)
    if (signed["source_date_epoch"] < record["minimum_source_date_epoch"]
            or signed["source_commit"] != record["approved_source_commit"]
            or signed["wheel_sha256"] != record["approved_wheel_sha256"]):
        raise R38Refused("R38_SIGNED_PREVIEW_NOT_APPROVED_BY_POLICY")
    result = r37.verify(
        manifest=manifest, signature=signature, wheel=wheel,
        trusted_public_key=trusted_public_key,
        trusted_public_key_spki_sha256=record["trusted_key_spki_sha256"],
        expected_source_commit=record["approved_source_commit"],
    )
    if (not result.get("manifest_signature_valid")
            or result.get("wheel_sha256") != record["approved_wheel_sha256"]
            or not hmac.compare_digest(r37._read(manifest, 4096), signed_bytes)):
        raise R38Refused("R38_SIGNED_MANIFEST_CHANGED_OR_UNVERIFIED")
    # This independent second hash/ZIP review guards against a Wheel changing
    # between the signature check and R35's check or attempted installation.
    preflight = r35.check(
        wheel=wheel, sha256=record["approved_wheel_sha256"],
        destination=destination,
    )
    if preflight.get("verdict") != "R35_OFFLINE_WHEEL_PREFLIGHT_PASS":
        raise R38Refused("R38_R35_PREFLIGHT_NOT_ACCEPTED")
    response = {
        "verdict": "R38_SIGNED_OFFLINE_PREFLIGHT_PASS_RELEASE_DENIED",
        "wheel_sha256": record["approved_wheel_sha256"],
        "source_commit": record["approved_source_commit"],
        "manifest_signature_valid": True,
        "trusted_key_not_revoked_in_pinned_policy": True,
        "writes_performed": False,
        "install_authorized": False,
        "production_release_authorized": False,
        "public_signal_authorized": False,
        "telegram_enabled": False,
        "broker_orders_enabled": False,
        "live_authorized": False,
    }
    if not install:
        return response
    # R35 enforces non-root, exclusive path ownership, explicit ack,
    # offline pip --no-index --no-deps and inert installed --check.
    # Do not mock or relax the R35 guards in live operation.
    installed = r35.install(
        wheel=wheel, sha256=record["approved_wheel_sha256"],
        destination=destination, ack=ack,
    )
    if installed.get("verdict") != "R35_INSTALLED_OFFLINE_PREVIEW_PASS_RELEASE_DENIED":
        raise R38Refused("R38_INSTALL_RESULT_UNSAFE")
    response["verdict"] = "R38_SIGNED_OFFLINE_PREVIEW_INSTALLED_RELEASE_DENIED"
    response["writes_performed"] = True
    response["installation_isolated"] = True
    return response


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for item in ("manifest", "signature", "wheel", "trusted-public-key",
                 "policy", "destination"):
        parser.add_argument("--" + item, required=True, type=Path)
    parser.add_argument("--policy-sha256", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-only", action="store_true")
    mode.add_argument("--install", action="store_true")
    parser.add_argument("--ack-offline-preview-install", action="store_true")
    args = parser.parse_args(argv)
    try:
        answer = gate(
            manifest=args.manifest, signature=args.signature,
            wheel=args.wheel, trusted_public_key=args.trusted_public_key,
            policy=args.policy, policy_sha256=args.policy_sha256,
            destination=args.destination, install=args.install,
            ack=args.ack_offline_preview_install,
        )
    except (R38Refused, r37.R37Refused, r35.R35Refused, OSError,
            ValueError, RuntimeError, TypeError) as exc:
        reason = (
            str(exc) if isinstance(exc, (R38Refused, r37.R37Refused, r35.R35Refused))
            else "R38_PREVIEW_GATE_FAILED"
        )
        print(json.dumps({
            "verdict": "R38_SIGNED_PREVIEW_GATE_REFUSED",
            "reason": reason, "writes_performed": False,
            "install_authorized": False, "production_release_authorized": False,
            "live_authorized": False,
        }, sort_keys=True))
        return 2
    print(json.dumps(answer, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
