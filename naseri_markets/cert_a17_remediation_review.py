"""CERT-A17 read-only remediation decision gates, NEVER package mutation.

This audit freezes what is observed, what official Debian tracker states
for a *subset* of advisories, and which evidence still needs review.
No vulnerability is reclassified as fixed or unreachable. No new image
is built, no Docker code is executed, and no production authority exists.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_RELATIVE = "deploy/runtime_a2/a17_remediation_review.json"
_A11 = "deploy/runtime_a2/a11_apt_closure.json"
_A12 = "deploy/runtime_a2/a12_signed_snapshot.json"
_A6 = "naseri_markets/runtime_a6_dispatch_fence.py"

_ORIGINAL_SOURCE = "5567e106f4dc81d441ee8aff1db100df244134d6"
_A16_FINGERPRINT = "fe25ab67ef9252f2b4694f4f0ddd12d305958878e9fb42cfa98a0ee5d3198d30"
_A11_CLOSURE = "47bd698232b4f624d1aab35c6453e1f01641b1b6ebdd8d4d7dc38a4dd19ae872"
_EXPECTED_CRITICAL = (
    ("CVE-2026-106445", "deb", "handlebars", "3:4.7.7+~4.1.0-1"),
    ("CVE-2026-106446", "deb", "handlebars", "3:4.7.7+~4.1.0-1"),
    ("CVE-2026-33937", "deb", "handlebars", "3:4.7.7+~4.1.0-1"),
    ("CVE-2026-5450", "deb", "libc-bin", "2.36-9+deb12u14"),
    ("CVE-2026-5450", "deb", "libc6", "2.36-9+deb12u14"),
    ("CVE-2025-7458", "deb", "libsqlite3-0", "3.40.1-2+deb12u2"),
    ("CVE-2026-25547", "deb", "node-brace-expansion", "2.0.1-2"),
    ("CVE-2026-33228", "deb", "node-flatted", "3.2.7~ds-1+deb12u1"),
    ("CVE-2023-42282", "deb", "node-ip", "2.0.0+~1.1.0-1"),
    ("CVE-2026-45623", "deb", "node-postcss", "8.4.20+~cs8.0.23-1+deb12u1"),
    ("CVE-2026-13697", "deb", "node-undici",
     "5.15.0+dfsg1+~cs20.10.9.3-1+deb12u4"),
    ("CVE-2026-84961", "deb", "node-undici",
     "5.15.0+dfsg1+~cs20.10.9.3-1+deb12u4"),
    ("GHSA-67hx-6x53-jw92", "npm", "@babel/traverse", "7.20.13"),
    ("GHSA-2w6w-674q-4c4q", "npm", "handlebars", "4.7.7"),
    ("GHSA-8r5x-fm3f-whwj", "npm", "handlebars", "4.7.7"),
    ("GHSA-p8wg-vrv2-v86f", "npm", "handlebars", "4.7.7"),
    ("GHSA-23hp-3jrh-7fpw", "npm", "tar", "6.1.13"),
    ("GHSA-hc6q-2mpp-qw7j", "npm", "webpack", "5.75.0"),
)
_OFFICIALLY_SPOT_CHECKED = frozenset({
    "CVE-2026-5450", "CVE-2025-7458", "CVE-2026-33937",
    "CVE-2026-33228", "CVE-2026-25547", "CVE-2026-13697",
    "CVE-2026-84961",
})
_NPM_CANDIDATES = {
    "GHSA-67hx-6x53-jw92": ["7.23.2"],
    "GHSA-2w6w-674q-4c4q": ["4.7.9"],
    "GHSA-8r5x-fm3f-whwj": ["4.7.10"],
    "GHSA-p8wg-vrv2-v86f": ["4.7.10"],
    "GHSA-23hp-3jrh-7fpw": ["7.5.19"],
    "GHSA-hc6q-2mpp-qw7j": ["5.76.0"],
}
_EVIDENCE_GATES = (
    "DEBIAN_SOURCE_PACKAGE_OWNER_AND_EXACT_BYTES",
    "OFFICIAL_ADVISORY_VERSION_AND_BACKPORT_STATUS",
    "REACHABILITY_OR_PROVEN_ABSENCE",
    "FIXED_CANDIDATE_DIGEST_AND_LICENSE",
    "UNCHANGED_BASELINE_BENIGN_FOUR_LANGUAGE_EQUIVALENCE",
    "INDEPENDENT_HOST_ISOLATION_AND_ATTESTATION_FOR_ANY_EXECUTION_APPROVAL",
)
_CRITICAL_KEYS = frozenset({
    "advisory_id", "ecosystem", "package", "installed_version", "priority",
    "apt_372_archive_pinned", "debian_tracker", "official_source_url",
    "upstream_scope_reconciliation", "suggested_research_route",
    "scanner_suggested_upstream_versions",
    "scanner_versions_not_approved_upgrade", "review_status",
    "removed_from_runtime_certified", "vulnerability_fixed_certified",
    "false_positive_certified", "reachability_established",
})
_SIGNATURE = re.compile(r"[a-f0-9]{64}\Z")


class A17Refused(ValueError):
    """Fail-closed fixed error codes, not untrusted details."""


def _unique(pairs: list[tuple[str, object]]) -> dict:
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise A17Refused("A17_DUPLICATE_JSON_KEY")
        obj[key] = value
    return obj


def _load(path: Path, limit: int = 75_000) -> dict:
    try:
        if path.is_symlink() or not path.is_file():
            raise A17Refused("A17_SYMLINK_OR_MISSING_SOURCE")
        info = path.stat()
        if not 0 < info.st_size <= limit or info.st_nlink != 1:
            raise A17Refused("A17_SOURCE_SIZE_INVALID")
        parsed = json.loads(path.read_text(encoding="utf-8"),
                            object_pairs_hook=_unique)
    except (OSError, ValueError, UnicodeError, RecursionError) as exc:
        if isinstance(exc, A17Refused):
            raise
        raise A17Refused("A17_INVALID_JSON") from exc
    if type(parsed) is not dict:
        raise A17Refused("A17_ROOT_NOT_OBJECT")
    return parsed


def validate_ledger(ledger: dict, apt_packages: dict[str, str]) -> None:
    if type(ledger) is not dict:
        raise A17Refused("A17_LEDGER_NOT_OBJECT")
    base = {
        "schema": 1, "stage": "CERT-A17",
        "mode": "SOURCE_RESEARCH_REMEDIATION_FREEZE_ONLY",
        "as_of": "2026-10-14", "baseline_commit": _ORIGINAL_SOURCE,
        "source_a16_evidence_fingerprint_sha256": _A16_FINGERPRINT,
        "source_a16_run": 38602711151,
        "source_a16_critical_high_total": 199,
        "source_a16_critical_total": 18,
        "source_a16_high_total": 181,
        "source_a16_match_class_counts": {
            "SAME_ADVISORY_PACKAGE_VERSION_DETECTED_IN_LEAN": 70,
            "NOT_SCANNER_MATCHED_SAMPLED_PAYLOAD_BYTES_RETAINED": 14,
            "NOT_SCANNER_MATCHED_PAYLOAD_REMOVAL_UNPROVEN": 115,
        },
        "apt_372_lock_closure_sha256": _A11_CLOSURE,
        "debian_snapshot_timestamp": "20261014T000000Z",
        "high_findings_status": "ALL_181_OPEN_NOT_INDIVIDUALLY_ADJUDICATED",
        "files_modified_in_active_worker": [],
        "no_build_deploy_restart": True,
        "original_worker_and_debian_locks_untouched": True,
        "worker_execution_authorized": False,
        "host_rootless_gvisor_certified": False,
        "production_authorized": False,
        "broker_authorized": False,
        "telegram_authorized": False,
        "vulnerabilities_remediated_certified": False,
    }
    if any(
        type(ledger.get(k)) is not type(value) or ledger.get(k) != value
        for k, value in base.items()
    ):
        raise A17Refused("A17_BASELINE_OR_RELEASE_CLAIM_CHANGED")
    if set(ledger) != set(base) | {
        "critical_findings", "required_independent_evidence",
    }:
        raise A17Refused("A17_SCHEMA_OR_FORGED_FIELDS")
    requirements = ledger["required_independent_evidence"]
    if type(requirements) is not list or requirements != list(_EVIDENCE_GATES):
        raise A17Refused("A17_MISSING_REMEDIATION_EVIDENCE_GATES")
    if (type(ledger["critical_findings"]) is not list
            or len(ledger["critical_findings"]) != 18):
        raise A17Refused("A17_CRITICAL_FINDINGS_LOST")
    for expected, item in zip(_EXPECTED_CRITICAL, ledger["critical_findings"]):
        if type(item) is not dict or set(item) != _CRITICAL_KEYS:
            raise A17Refused("A17_CRITICAL_ROW_SCHEMA_CHANGED")
        identity = tuple(item.get(k) for k in (
            "advisory_id", "ecosystem", "package", "installed_version",
        ))
        if identity != expected:
            raise A17Refused("A17_ORIGINAL_CRITICAL_IDENTITY_CHANGED")
        advisory, ecosystem, package, version = expected
        hashed_apt = ecosystem == "deb" and apt_packages.get(package) == version
        if (item["priority"] != "P0"
                or item["apt_372_archive_pinned"] is not hashed_apt
                or item["review_status"] != "OPEN_REVIEW_REQUIRED"
                or item["scanner_versions_not_approved_upgrade"] is not True
                or any(item.get(x) is not False for x in (
                    "removed_from_runtime_certified", "vulnerability_fixed_certified",
                    "false_positive_certified", "reachability_established",
                ))):
            raise A17Refused("A17_FORGED_FIX_OR_APT_PIN_STATUS")
        if (type(item["suggested_research_route"]) is not str
                or not 10 <= len(item["suggested_research_route"]) <= 160):
            raise A17Refused("A17_REMEDIATION_ROUTE_MISSING")
        expected_url = (
            f"https://security-tracker.debian.org/tracker/{advisory}"
            if advisory in _OFFICIALLY_SPOT_CHECKED else None
        )
        expected_tracker = (
            "vulnerable" if advisory in _OFFICIALLY_SPOT_CHECKED
            else "NOT_INDEPENDENTLY_ADJUDICATED"
        )
        if (item["official_source_url"] != expected_url
                or item["debian_tracker"] != expected_tracker):
            raise A17Refused("A17_FORGED_TRACKER_EVIDENCE")
        if item["scanner_suggested_upstream_versions"] != _NPM_CANDIDATES.get(
            advisory, []
        ):
            raise A17Refused("A17_UNAPPROVED_VERSION_CANDIDATE")
        expected_scope = (
            "VERSION_RANGES_7_8_VS_BOOKWORM_5_REQUIRE_SOURCE_AUDIT"
            if advisory in {"CVE-2026-13697", "CVE-2026-84961"}
            else "REQUIRED"
        )
        if item["upstream_scope_reconciliation"] != expected_scope:
            raise A17Refused("A17_UPSTREAM_APPLICABILITY_NOT_PROVEN")


def validate_repository(root: Path) -> dict:
    doc = _load(root / _RELATIVE)
    apt = _load(root / _A11)
    snap = _load(root / _A12)
    if (apt.get("closure_sha256") != _A11_CLOSURE
            or type(apt.get("packages")) is not list
            or len(apt["packages"]) != 372
            or snap.get("snapshot_timestamp") != "20261014T000000Z"
            or snap.get("worker_execution_authorized") is not False):
        raise A17Refused("A17_PINNED_APT_SNAPSHOT_BASELINE_DRIFT")
    packages: dict[str, str] = {}
    for package in apt["packages"]:
        if (type(package) is not dict
                or type(package.get("package")) is not str
                or type(package.get("version")) is not str
                or not _SIGNATURE.fullmatch(str(package.get("sha256")))):
            raise A17Refused("A17_APT_ARCHIVE_IDENTITY_INVALID")
        if package["package"] in packages:
            raise A17Refused("A17_DUPLICATE_APT_PACKAGE")
        packages[package["package"]] = package["version"]
    validate_ledger(doc, packages)
    fence = (root / _A6).read_text(encoding="utf-8")
    if 'raise RuntimeA6Denied("A6_INDEPENDENT_HOST_CERTIFICATION_REQUIRED")' not in fence:
        raise A17Refused("A17_A6_UNCONDITIONAL_DENY_CHANGED")
    return {
        "status": "CERT_A17_REMEDIATION_SOURCE_RESEARCH_FROZEN_NO_MUTATION",
        "critical_open": len(doc["critical_findings"]),
        "high_open": doc["source_a16_high_total"],
        "debian_official_spot_checked_rows": sum(
            item["official_source_url"] is not None
            for item in doc["critical_findings"]
        ),
        "apt_archive_pinned_critical_rows": sum(
            item["apt_372_archive_pinned"]
            for item in doc["critical_findings"]
        ),
        "image_patch_applied": False,
        "worker_execution_authorized": False,
    }


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    report = validate_repository(root)
    print(json.dumps(report, sort_keys=True))
