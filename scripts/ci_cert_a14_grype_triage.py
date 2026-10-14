"""CERT-A14: offline-only read-only Critical/High Grype evidence triage.

No automatic false-positive disposition, package update, Worker permission,
network calls, production writes, trusted-host claim or release gates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from collections import Counter
from pathlib import Path

_SCAN_LIMIT = 40 * 1024 * 1024
_EVIDENCE_LIMIT = 64 * 1024
_TOTAL_LIMIT = 100_000
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_IMAGE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_PRIORITIES = {"Critical": "P0", "High": "P1"}
_SEVERITIES = ("Critical", "High", "Medium", "Low", "Negligible", "Unknown")
_FALSE_FIELDS = (
    "worker_execution_authorized", "production_authorized",
    "broker_authorized", "telegram_authorized",
    "rootless_gvisor_certified", "independent_publisher_verified",
    "vulnerability_free_certified", "sbom_coverage_complete_certified",
)
_DOMAIN = b"MMT-CERT-A14-OFFLINE-CRITICAL-HIGH-EVIDENCE-V1\x00"


class A14Refused(ValueError):
    """Error codes never embed scanner-controlled input."""


def _pairs_unique(pairs: list[tuple[str, object]]) -> dict:
    obj: dict = {}
    for key, value in pairs:
        if key in obj:
            raise A14Refused("A14_DUPLICATE_JSON_FIELD")
        obj[key] = value
    return obj


def _read(path: Path, limit: int) -> tuple[dict, str]:
    try:
        if path.is_symlink():
            raise A14Refused("A14_SYMLINK_INPUT_REFUSED")
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or not 0 < info.st_size <= limit):
            raise A14Refused("A14_MISSING_OR_OVERSIZED_EVIDENCE")
        data = path.read_bytes()
        obj = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs_unique)
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, A14Refused):
            raise
        raise A14Refused("A14_INVALID_EVIDENCE_JSON") from exc
    if type(obj) is not dict:
        raise A14Refused("A14_JSON_ROOT_NOT_OBJECT")
    return obj, hashlib.sha256(data).hexdigest()


def _text(value: object, *, limit: int = 512) -> str:
    if type(value) is not str or not 0 < len(value) <= limit:
        raise A14Refused("A14_INVALID_VULNERABILITY_FIELD")
    return value


def _fix(fix: object) -> tuple[str, list[str]]:
    if type(fix) is not dict:
        raise A14Refused("A14_FIX_STATE_NOT_REPORTED")
    state = _text(fix.get("state"), limit=48)
    versions = fix.get("versions", [])
    if type(versions) is not list or len(versions) > 32:
        raise A14Refused("A14_FIX_VERSIONS_MALFORMED")
    return state, [_text(version, limit=192) for version in versions]


def _row(match: object) -> dict:
    if type(match) is not dict:
        raise A14Refused("A14_VULNERABILITY_MATCH_INVALID")
    vuln, artifact = match.get("vulnerability"), match.get("artifact")
    if type(vuln) is not dict or type(artifact) is not dict:
        raise A14Refused("A14_MISSING_ADVISORY_OR_PACKAGE")
    severity = _text(vuln.get("severity"), limit=32)
    if severity not in _SEVERITIES:
        raise A14Refused("A14_UNKNOWN_SEVERITY")
    if severity not in _PRIORITIES:
        return {}
    package_type = _text(artifact.get("type"), limit=48)
    advisory = _text(vuln.get("id"), limit=128)
    name = _text(artifact.get("name"), limit=256)
    version = _text(artifact.get("version"), limit=192)
    state, fixed = _fix(vuln.get("fix"))
    purl = artifact.get("purl", "")
    if type(purl) is not str or len(purl) > 2048:
        raise A14Refused("A14_PACKAGE_REFERENCE_INVALID")
    locations = artifact.get("locations", [])
    if type(locations) is not list or len(locations) > 2048:
        raise A14Refused("A14_PACKAGE_LOCATIONS_MALFORMED")
    one_path = ""
    if locations:
        if type(locations[0]) is not dict:
            raise A14Refused("A14_PACKAGE_LOCATION_INVALID")
        raw = locations[0].get("path", "")
        if type(raw) is not str or len(raw) > 4096:
            raise A14Refused("A14_PACKAGE_LOCATION_INVALID")
        one_path = raw
    return {
        "priority": _PRIORITIES[severity],
        "severity": severity,
        "advisory_id": advisory,
        "artifact_type": package_type,
        "package": name,
        "installed_version": version,
        "purl": purl,
        "observed_package_path": one_path,
        "fix_state_as_reported": state,
        "fixed_versions_as_reported": fixed,
        "reachability_confirmed": False,
        "false_positive_confirmed": False,
        "debian_backport_assessed": False,
        "remediation_authorized": False,
        "review_state": "OPEN_REVIEW_REQUIRED",
        "next_review": (
            "VERIFY_DEBIAN_ADVISORY_AND_BACKPORT_AND_RUNTIME_REACHABILITY"
            if package_type == "deb" else
            "VERIFY_UPSTREAM_FIX_AND_WHY_PACKAGE_IS_IN_RUNTIME_IMAGE"
            if package_type == "npm" else
            "VERIFY_ECOSYSTEM_ADVISORY_AND_RUNTIME_REACHABILITY"
        ),
    }


def triage(scan: dict, scan_sha: str, evidence: dict) -> dict:
    """Cross-check A13 authoritative counts/bytes; never silently drop High."""
    if (type(evidence) is not dict or evidence.get("schema") != 1
            or evidence.get("audience") != "MMT-CERT-A13-EPHEMERAL-IMAGE-EVIDENCE"
            or evidence.get("grype_json_sha256") != scan_sha
            or _SHA.fullmatch(str(evidence.get("sbom_cyclonedx_sha256"))) is None
            or _IMAGE.fullmatch(str(evidence.get("candidate_image_id"))) is None
            or any(evidence.get(key) is not False for key in _FALSE_FIELDS)):
        raise A14Refused("A14_A13_EVIDENCE_UNTRUSTED_OR_HASH_CHANGED")
    matches = scan.get("matches")
    if (type(matches) is not list or len(matches) > _TOTAL_LIMIT
            or evidence.get("vulnerability_matches") != len(matches)):
        raise A14Refused("A14_RAW_MATCH_COUNT_DIFFERS_FROM_A13")
    observed: Counter = Counter()
    selected = []
    for match in matches:
        if (type(match) is not dict
                or type(match.get("vulnerability")) is not dict):
            raise A14Refused("A14_RAW_MATCH_MALFORMED")
        severity = match["vulnerability"].get("severity")
        if type(severity) is not str or severity not in _SEVERITIES:
            raise A14Refused("A14_RAW_SEVERITY_UNKNOWN")
        observed[severity] += 1
        if severity in _PRIORITIES:
            selected.append(_row(match))
    reported = evidence.get("by_severity")
    if (type(reported) is not dict or set(reported) != set(_SEVERITIES)
            or any(type(reported[key]) is not int
                   or reported[key] != observed[key] for key in _SEVERITIES)):
        raise A14Refused("A14_A13_SEVERITY_COUNTS_DO_NOT_RECONCILE")
    selected.sort(key=lambda x: (
        x["priority"], x["artifact_type"], x["package"],
        x["advisory_id"], x["installed_version"],
    ))
    by_fix = Counter(x["fix_state_as_reported"] for x in selected)
    by_type = Counter(x["artifact_type"] for x in selected)
    result = {
        "schema": 1,
        "status": "CERT_A14_EVIDENCE_ONLY_ALL_FINDINGS_PENDING_REVIEW",
        "source_a13_image_id": evidence["candidate_image_id"],
        "source_scan_sha256": scan_sha,
        "source_sbom_sha256": evidence["sbom_cyclonedx_sha256"],
        "source_db_built": evidence.get("vulnerability_database_built"),
        "all_severity_matches": len(matches),
        "critical_matches": observed["Critical"],
        "high_matches": observed["High"],
        "critical_high_matches": len(selected),
        "critical_high_unique_advisory_ids": len(
            {item["advisory_id"] for item in selected}
        ),
        "unique_critical_advisory_ids": len({
            item["advisory_id"] for item in selected
            if item["severity"] == "Critical"
        }),
        "by_artifact_type": dict(sorted(by_type.items())),
        "by_scanner_fix_state": dict(sorted(by_fix.items())),
        "no_automatic_false_positive_classification": True,
        "no_automatic_fix_application": True,
        "gvisor_host_certified": False,
        "worker_execution_authorized": False,
        "production_authorized": False,
        "findings": selected,
    }
    result["fingerprint_sha256"] = hashlib.sha256(
        _DOMAIN + json.dumps(
            result, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8"),
    ).hexdigest()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="A14 offline evidence triage")
    parser.add_argument("--scan", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if os.environ.get("MMT_PRODUCTION") == "1":
            raise A14Refused("A14_PRODUCTION_INVOCATION_REFUSED")
        raw_scan, scan_sha = _read(args.scan, _SCAN_LIMIT)
        a13, _ = _read(args.evidence, _EVIDENCE_LIMIT)
        report = triage(raw_scan, scan_sha, a13)
        if args.output.is_symlink():
            raise A14Refused("A14_OUTPUT_SYMLINK_REFUSED")
        args.output.write_text(
            json.dumps(report, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        print("A14_CRITICAL=" + str(report["critical_matches"]))
        print("A14_HIGH=" + str(report["high_matches"]))
        print("A14_UNIQUE_ADVISORIES=" + str(report["critical_high_unique_advisory_ids"]))
        print("A14_OPEN_REVIEW=" + str(len(report["findings"])))
        print("A14_ALL_FINDINGS_UNRELEASED__A6_DENY")
    except (A14Refused, OSError) as exc:
        print(str(exc) if isinstance(exc, A14Refused)
              else "A14_EVIDENCE_FILE_NOT_ACCESSIBLE", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
