"""CERT-A13 fixed nonproduction Worker image SBOM/vulnerability evidence review.

Only accepts already-generated CycloneDX and Grype JSON from the disposable
GitHub-hosted Docker candidate. Scanner findings are observations, NEVER
a certificate that the image is safe or Worker dispatch is authorized.
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
from datetime import datetime, timedelta, timezone
from pathlib import Path

_HEX = re.compile(r"sha256:[a-f0-9]{64}\Z")
_SEVERITIES = ("Critical", "High", "Medium", "Low", "Negligible", "Unknown")
_ALLOWED_SEVERITIES = frozenset(_SEVERITIES)
_MAX_SBOM = 40 * 1024 * 1024
_MAX_SCAN = 80 * 1024 * 1024
_MAX_MATCHES = 100_000
_MAX_COMPONENTS = 50_000
_DOMAIN = b"MMT-CERT-A13-SBOM-VULN-REPORT-V1\x00"


class A13Refused(ValueError):
    """Never print raw scanner output or untrusted structured details."""


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise A13Refused("A13_DUPLICATE_JSON_FIELD")
        obj[key] = value
    return obj


def _read(path: Path, limit: int) -> tuple[dict, str]:
    try:
        if path.is_symlink():
            raise A13Refused("A13_SYMLINK_REFUSED")
        info = path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                or not 0 < info.st_size <= limit):
            raise A13Refused("A13_MISSING_OR_OVERSIZED_EVIDENCE")
        raw = path.read_bytes()
        parsed = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
    except (OSError, UnicodeError, ValueError, RecursionError) as exc:
        if isinstance(exc, A13Refused):
            raise
        raise A13Refused("A13_EVIDENCE_NOT_VALID_JSON") from exc
    if type(parsed) is not dict:
        raise A13Refused("A13_JSON_ROOT_NOT_OBJECT")
    return parsed, hashlib.sha256(raw).hexdigest()


def _sbom_check(data: dict) -> int:
    if data.get("bomFormat") != "CycloneDX":
        raise A13Refused("A13_NOT_CYCLONEDX")
    components = data.get("components")
    if type(components) is not list or not 2 <= len(components) <= _MAX_COMPONENTS:
        raise A13Refused("A13_MISSING_PACKAGE_INVENTORY")
    names = set()
    for item in components:
        if (type(item) is not dict
                or type(item.get("name")) is not str
                or not 0 < len(item["name"]) <= 256
                or type(item.get("version")) is not str
                or not 0 < len(item["version"]) <= 192):
            raise A13Refused("A13_MALFORMED_SBOM_PACKAGE")
        names.add(item["name"])
    if not {"nodejs", "npm"}.issubset(names):
        raise A13Refused("A13_EXPECTED_APT_PACKAGES_MISSING")
    return len(components)


def _db_timestamp(data: dict, *, now: datetime) -> tuple[str, int]:
    db = data.get("db")
    if type(db) is not dict or type(db.get("built")) is not str:
        raise A13Refused("A13_VULNERABILITY_DATABASE_PROVENANCE_MISSING")
    raw = db["built"]
    try:
        built = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise A13Refused("A13_DB_BUILD_DATE_MALFORMED") from exc
    if built.tzinfo is None:
        raise A13Refused("A13_DB_BUILD_DATE_WITHOUT_TIMEZONE")
    built = built.astimezone(timezone.utc)
    age = now - built
    if not (-timedelta(hours=24) <= age <= timedelta(days=30)):
        raise A13Refused("A13_DB_STALE_OR_FUTURE")
    return built.isoformat(), int(age.total_seconds() // 86400)


def _scan_check(data: dict) -> tuple[Counter, int]:
    if type(data.get("descriptor")) is not dict:
        raise A13Refused("A13_SCANNER_DESCRIPTOR_MISSING")
    matches = data.get("matches")
    if type(matches) is not list or len(matches) > _MAX_MATCHES:
        raise A13Refused("A13_VULNERABILITY_RESULT_INVALID")
    counts: Counter = Counter()
    for match in matches:
        if type(match) is not dict:
            raise A13Refused("A13_MALFORMED_VULNERABILITY_MATCH")
        vuln, artifact = match.get("vulnerability"), match.get("artifact")
        if (type(vuln) is not dict or type(artifact) is not dict
                or type(vuln.get("id")) is not str
                or not 0 < len(vuln["id"]) <= 128
                or type(artifact.get("name")) is not str
                or not 0 < len(artifact["name"]) <= 256
                or type(vuln.get("severity")) is not str):
            raise A13Refused("A13_MALFORMED_VULNERABILITY_FIELDS")
        severity = vuln["severity"].capitalize()
        if severity not in _ALLOWED_SEVERITIES:
            raise A13Refused("A13_UNKNOWN_SEVERITY_REFUSED")
        counts[severity] += 1
    return counts, len(matches)


def review(
    sbom_path: Path, scan_path: Path, image_id: str, *,
    now: datetime | None = None,
) -> dict:
    """Review scanner structure/freshness only; findings cannot grant launch."""
    if _HEX.fullmatch(image_id) is None:
        raise A13Refused("A13_IMAGE_ID_NOT_CONTENT_ADDRESSED")
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise A13Refused("A13_CLOCK_NOT_TIMEZONE_AWARE")
    sbom, sbom_sha = _read(sbom_path, _MAX_SBOM)
    scan, scan_sha = _read(scan_path, _MAX_SCAN)
    components = _sbom_check(sbom)
    db_built, db_age_days = _db_timestamp(scan, now=now.astimezone(timezone.utc))
    counts, matches = _scan_check(scan)
    statuses = {
        "worker_execution_authorized": False,
        "production_authorized": False,
        "telegram_authorized": False,
        "broker_authorized": False,
        "rootless_gvisor_certified": False,
        "independent_publisher_verified": False,
        "vulnerability_free_certified": False,
    }
    verdict = (
        "CERT_A13_FINDINGS_REQUIRE_MANUAL_SECURITY_REVIEW"
        if matches else "CERT_A13_NO_MATCHES_DETECTED_NOT_PROOF_OF_SAFETY"
    )
    data = {
        "schema": 1,
        "audience": "MMT-CERT-A13-EPHEMERAL-IMAGE-EVIDENCE",
        "candidate_image_id": image_id,
        "sbom_cyclonedx_sha256": sbom_sha,
        "grype_json_sha256": scan_sha,
        "components": components,
        "vulnerability_matches": matches,
        "by_severity": {key: counts.get(key, 0) for key in _SEVERITIES},
        "vulnerability_database_built": db_built,
        "vulnerability_db_age_days": db_age_days,
        "verdict": verdict,
        "sbom_coverage_complete_certified": False,
        **statuses,
    }
    data["evidence_fingerprint_sha256"] = hashlib.sha256(
        _DOMAIN + json.dumps(data, sort_keys=True, separators=(",", ":")).encode(),
    ).hexdigest()
    return data


def _guard() -> None:
    required = {
        "GITHUB_ACTIONS": "true",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "MMT_NONPRODUCTION": "1",
        "MMT_CERT_A13_AUDIT_ONLY": "1",
    }
    if (os.geteuid() == 0 or os.environ.get("MMT_PRODUCTION") == "1"
            or any(os.environ.get(k) != v for k, v in required.items())):
        raise A13Refused("A13_ONLY_GITHUB_HOSTED_NONPRODUCTION")


def main() -> int:
    parser = argparse.ArgumentParser(description="CERT-A13 evidence review, never release")
    parser.add_argument("--sbom", required=True, type=Path)
    parser.add_argument("--scan", required=True, type=Path)
    parser.add_argument("--image-id", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        _guard()
        result = review(args.sbom, args.scan, args.image_id)
        # The output location remains inside runner temp, never the repo.
        temp = Path(os.environ.get("RUNNER_TEMP", "/nonexistent")).resolve()
        output = args.output.resolve()
        if (output.parent != temp or output.name != "cert-a13-evidence.json"
                or args.output.is_symlink()):
            raise A13Refused("A13_OUTPUT_MUST_BE_EPHEMERAL")
        output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print("CERT_A13_IMAGE_ID=" + result["candidate_image_id"])
        print("CERT_A13_SBOM_COMPONENTS=" + str(result["components"]))
        print("CERT_A13_VULNERABILITY_MATCHES=" + str(result["vulnerability_matches"]))
        for severity, count in result["by_severity"].items():
            print("CERT_A13_" + severity.upper() + "=" + str(count))
        print("CERT_A13_DB_AGE_DAYS=" + str(result["vulnerability_db_age_days"]))
        print("CERT_A13_STATUS=" + result["verdict"])
    except (A13Refused, OSError) as exc:
        print(str(exc) if isinstance(exc, A13Refused) else
              "A13_REPORT_FILE_UNAVAILABLE", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
