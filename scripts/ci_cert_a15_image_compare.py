"""CERT-A15 non-authorizing pairwise A2 vs lean Worker SBOM/CVE comparison.

Comparisons of Grype match counts on stripped ELF files are NOT evidence
of actual CVE fixes. No remote execution, installs or production authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from scripts.ci_cert_a13_sbom_review import _db_timestamp, _read, _scan_check

_IMAGE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_DOMAIN = b"MMT-CERT-A15-UNTRUSTED-RUNTIME-INVENTORY-COMPARISON-V1\x00"
_NON_RELEASE = {
    "independent_publisher_verified": False,
    "rootless_gvisor_host_certified": False,
    "worker_execution_authorized": False,
    "broker_authorized": False,
    "telegram_authorized": False,
    "production_authorized": False,
    "vulnerabilities_remediated_certified": False,
    "sbom_completeness_certified": False,
}


class A15Refused(ValueError):
    """Fail closed with fixed error codes."""


def _check_scope() -> None:
    must = {
        "GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted",
        "MMT_NONPRODUCTION": "1", "MMT_CERT_A15_COMPARE_ONLY": "1",
    }
    if (os.geteuid() == 0 or os.environ.get("MMT_PRODUCTION") == "1"
            or any(os.environ.get(k) != v for k, v in must.items())):
        raise A15Refused("A15_ONLY_GITHUB_NONPRODUCTION_FIXTURES")


def _inventory(sbom_path: Path, scan_path: Path, now: datetime) -> dict:
    sbom, sbom_sha = _read(sbom_path, 40 * 1024 * 1024)
    scan, scan_sha = _read(scan_path, 80 * 1024 * 1024)
    components = sbom.get("components")
    if (sbom.get("bomFormat") != "CycloneDX"
            or type(components) is not list
            or not 1 <= len(components) <= 50_000):
        raise A15Refused("A15_SBOM_MISSING_OR_INVALID")
    descriptor = scan.get("descriptor")
    if type(descriptor) is not dict or descriptor.get("name") != "grype":
        raise A15Refused("A15_SCANNER_NOT_GRYPE")
    db_time, age = _db_timestamp(scan, now=now)
    counts, total = _scan_check(scan)
    return {
        "sbom_sha256": sbom_sha, "scan_sha256": scan_sha,
        "components_observed": len(components),
        "vulnerability_db_built": db_time,
        "db_age_days": age, "matched_advisories": total,
        "by_severity": {
            name: counts.get(name, 0)
            for name in ("Critical", "High", "Medium", "Low", "Negligible", "Unknown")
        },
    }


def compare(
    base_sbom: Path, base_scan: Path, lean_sbom: Path, lean_scan: Path,
    base_id: str, lean_id: str, base_size: int, lean_size: int,
    *, now: datetime | None = None,
) -> dict:
    if (not _IMAGE.fullmatch(base_id) or not _IMAGE.fullmatch(lean_id)
            or base_id == lean_id
            or type(base_size) is not int or type(lean_size) is not int
            or not 0 < base_size < 2**32
            or not 0 < lean_size < 2**32):
        raise A15Refused("A15_IMAGE_ID_OR_BYTE_SIZE_INVALID")
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        raise A15Refused("A15_AWARE_TIME_REQUIRED")
    before = _inventory(base_sbom, base_scan, current)
    after = _inventory(lean_sbom, lean_scan, current)
    if before["vulnerability_db_built"] != after["vulnerability_db_built"]:
        raise A15Refused("A15_DIFFERENT_ADVISORY_DB_SNAPSHOT")
    severities = before["by_severity"]
    delta = {
        key: after["by_severity"][key] - value
        for key, value in severities.items()
    }
    report = {
        "schema": 1,
        "status": "CERT_A15_COMPARISON_ONLY_NO_CVE_REMEDIATION_ASSERTED",
        "baseline": {"image_id": base_id, "image_size_bytes": base_size, **before},
        "lean": {"image_id": lean_id, "image_size_bytes": lean_size, **after},
        "image_bytes_saved": base_size - lean_size,
        "image_size_reduced": lean_size < base_size,
        "observed_match_delta_lean_minus_baseline": delta,
        "observed_total_match_delta": (
            after["matched_advisories"] - before["matched_advisories"]
        ),
        "runtime_functional_equivalence_verified_only_on_benign_fixtures": True,
        "dpkg_metadata_removed_can_hide_vulnerable_library_inventory": True,
        "reduced_grype_matches_do_not_establish_cve_remediation": True,
        "original_apt_372_lock_untouched": True,
        **_NON_RELEASE,
    }
    report["fingerprint_sha256"] = hashlib.sha256(
        _DOMAIN + json.dumps(
            report, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8"),
    ).hexdigest()
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="A15 scan inventory, NO release authority")
    for item in ("base-sbom", "base-scan", "lean-sbom", "lean-scan"):
        parser.add_argument("--" + item, required=True, type=Path)
    for item in ("base-id", "lean-id"):
        parser.add_argument("--" + item, required=True)
    for item in ("base-size", "lean-size"):
        parser.add_argument("--" + item, required=True, type=int)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        _check_scope()
        temp = Path(os.environ.get("RUNNER_TEMP", "/nonexistent")).resolve()
        out = args.output.resolve()
        if (out.parent != temp or out.name != "cert-a15-comparison.json"
                or args.output.is_symlink()):
            raise A15Refused("A15_ONLY_RUNNER_TEMP_OUTPUT")
        report = compare(
            args.base_sbom, args.base_scan, args.lean_sbom, args.lean_scan,
            args.base_id, args.lean_id, args.base_size, args.lean_size,
        )
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print("A15_BASE_SIZE_BYTES=" + str(args.base_size))
        print("A15_LEAN_SIZE_BYTES=" + str(args.lean_size))
        print("A15_IMAGE_BYTES_SAVED=" + str(report["image_bytes_saved"]))
        print("A15_BASE_GRYPE_MATCHES=" + str(report["baseline"]["matched_advisories"]))
        print("A15_LEAN_GRYPE_MATCHES=" + str(report["lean"]["matched_advisories"]))
        for name, value in report["observed_match_delta_lean_minus_baseline"].items():
            print("A15_DELTA_" + name.upper() + "=" + str(value))
        print("A15_STATUS=" + report["status"])
    except (A15Refused, OSError, ValueError) as exc:
        print(str(exc) if isinstance(exc, A15Refused) else
              "A15_EVIDENCE_INVALID_OR_MISSING", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
