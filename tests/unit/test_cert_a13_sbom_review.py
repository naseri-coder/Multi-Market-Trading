"""CERT-A13 mock-only SBOM/Grype validation and non-authorization tests."""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from datetime import UTC, datetime, timedelta

import pytest

from scripts import ci_cert_a13_sbom_review as a13

NOW = datetime(2026, 10, 14, 15, tzinfo=UTC)
IMAGE = "sha256:" + "a" * 64
SBOM = {
    "bomFormat": "CycloneDX",
    "specVersion": "1.6",
    "components": [
        {"type": "library", "name": "nodejs", "version": "18.20.4"},
        {"type": "library", "name": "npm", "version": "9.2.0"},
        {"type": "library", "name": "wasmtime", "version": "49.0.0"},
    ],
}
SCAN = {
    "descriptor": {"name": "grype", "version": "0.120.1"},
    "db": {"built": "2026-10-13T10:00:00Z", "schemaVersion": 6},
    "matches": [{
        "vulnerability": {"id": "CVE-2026-1234", "severity": "High"},
        "artifact": {"name": "nodejs", "version": "18.20.4"},
    }],
}


def _files(tmp_path, *, sbom=None, scan=None):
    a = tmp_path / "image.sbom.json"
    b = tmp_path / "image.scan.json"
    a.write_text(json.dumps(SBOM if sbom is None else sbom))
    b.write_text(json.dumps(SCAN if scan is None else scan))
    return a, b


def test_complete_image_review_is_not_release_approval(tmp_path):
    a, b = _files(tmp_path)
    result = a13.review(a, b, IMAGE, now=NOW)
    assert result["components"] == 3
    assert result["vulnerability_matches"] == 1
    assert result["by_severity"]["High"] == 1
    assert sum(result["by_severity"].values()) == 1
    assert result["vulnerability_db_age_days"] == 1
    assert result["verdict"] == "CERT_A13_FINDINGS_REQUIRE_MANUAL_SECURITY_REVIEW"
    assert result["candidate_image_id"] == IMAGE
    assert result["sbom_cyclonedx_sha256"] == hashlib.sha256(a.read_bytes()).hexdigest()
    assert result["grype_json_sha256"] == hashlib.sha256(b.read_bytes()).hexdigest()
    assert len(result["evidence_fingerprint_sha256"]) == 64
    for forbidden in (
        "worker_execution_authorized", "production_authorized",
        "telegram_authorized", "broker_authorized",
        "rootless_gvisor_certified", "independent_publisher_verified",
        "vulnerability_free_certified", "sbom_coverage_complete_certified",
    ):
        assert result[forbidden] is False


def test_cyclonedx_may_omit_version_on_unrelated_packages(tmp_path):
    sbom = copy.deepcopy(SBOM)
    sbom["components"].append({"type": "file", "name": "generated-file"})
    a, b = _files(tmp_path, sbom=sbom)
    assert a13.review(a, b, IMAGE, now=NOW)["components"] == 4


def test_expected_nodejs_version_must_be_recorded(tmp_path):
    sbom = copy.deepcopy(SBOM)
    sbom["components"][0].pop("version")
    a, b = _files(tmp_path, sbom=sbom)
    with pytest.raises(a13.A13Refused, match="A13_EXPECTED_APT_VERSIONS_MISSING"):
        a13.review(a, b, IMAGE, now=NOW)


def test_modern_grype_descriptor_db_status_timestamp(tmp_path):
    scan = copy.deepcopy(SCAN)
    date = scan.pop("db")["built"]
    scan["descriptor"]["db"] = {"status": {"built": date, "schemaVersion": "v6"}}
    a, b = _files(tmp_path, scan=scan)
    result = a13.review(a, b, IMAGE, now=NOW)
    assert result["vulnerability_db_age_days"] == 1
    assert result["vulnerability_matches"] == 1


def test_modern_grype_missing_db_timestamp_is_not_valid_evidence(tmp_path):
    scan = copy.deepcopy(SCAN)
    scan.pop("db")
    scan["descriptor"]["db"] = {"status": {"built": None}}
    a, b = _files(tmp_path, scan=scan)
    with pytest.raises(
        a13.A13Refused, match="A13_VULNERABILITY_DATABASE_PROVENANCE_MISSING",
    ):
        a13.review(a, b, IMAGE, now=NOW)


def test_zero_matches_is_not_vulnerability_free_certificate(tmp_path):
    scan = copy.deepcopy(SCAN)
    scan["matches"] = []
    a, b = _files(tmp_path, scan=scan)
    result = a13.review(a, b, IMAGE, now=NOW)
    assert result["vulnerability_matches"] == 0
    assert result["verdict"] == "CERT_A13_NO_MATCHES_DETECTED_NOT_PROOF_OF_SAFETY"
    assert result["vulnerability_free_certified"] is False


@pytest.mark.parametrize("change", [
    lambda s: s.update(bomFormat="SPDX"),
    lambda s: s.pop("components"),
    lambda s: s["components"].clear(),
    lambda s: s["components"].pop(1),
    lambda s: s["components"][0].update(version=12),
])
def test_incomplete_sbom_refused(tmp_path, change):
    sbom = copy.deepcopy(SBOM)
    change(sbom)
    a, b = _files(tmp_path, sbom=sbom)
    with pytest.raises(a13.A13Refused):
        a13.review(a, b, IMAGE, now=NOW)


@pytest.mark.parametrize("change", [
    lambda s: s.pop("descriptor"),
    lambda s: s.pop("db"),
    lambda s: s["db"].update(built="not-a-date"),
    lambda s: s["db"].update(built="2026-06-01T01:00:00Z"),
    lambda s: s["db"].update(built="2026-10-20T01:00:00Z"),
    lambda s: s.update(matches=None),
    lambda s: s["matches"][0]["vulnerability"].update(severity="unmapped"),
    lambda s: s["matches"][0]["vulnerability"].update(id=""),
    lambda s: s["matches"][0]["artifact"].update(name=12),
])
def test_missing_db_invalid_severity_or_stale_feed_refused(tmp_path, change):
    scan = copy.deepcopy(SCAN)
    change(scan)
    a, b = _files(tmp_path, scan=scan)
    with pytest.raises(a13.A13Refused):
        a13.review(a, b, IMAGE, now=NOW)


def test_duplicate_scanner_fields_refused(tmp_path):
    a, b = _files(tmp_path)
    b.write_text('{"descriptor":{},"db":{"built":"2026-10-13T10:00:00Z"},'
                 '"matches":[],"matches":[]}')
    with pytest.raises(a13.A13Refused, match="A13_DUPLICATE_JSON_FIELD"):
        a13.review(a, b, IMAGE, now=NOW)


def test_guest_produced_symlink_or_forged_image_digest_refused(tmp_path):
    a, b = _files(tmp_path)
    alias = tmp_path / "scan-alias.json"
    alias.symlink_to(b)
    with pytest.raises(a13.A13Refused, match="A13_SYMLINK_REFUSED"):
        a13.review(a, alias, IMAGE, now=NOW)
    with pytest.raises(a13.A13Refused, match="A13_IMAGE_ID_NOT_CONTENT_ADDRESSED"):
        a13.review(a, b, "mmt/runtime-a2-candidate:pr", now=NOW)


@pytest.mark.parametrize("env", [
    "GITHUB_ACTIONS", "RUNNER_ENVIRONMENT", "MMT_NONPRODUCTION",
    "MMT_CERT_A13_AUDIT_ONLY",
])
def test_missing_hosted_ci_scope_refused_before_any_scan(monkeypatch, env):
    for k, v in {
        "GITHUB_ACTIONS": "true",
        "RUNNER_ENVIRONMENT": "github-hosted",
        "MMT_NONPRODUCTION": "1",
        "MMT_CERT_A13_AUDIT_ONLY": "1",
    }.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv(env)
    monkeypatch.setattr(a13.os, "geteuid", lambda: 1001)
    with pytest.raises(a13.A13Refused, match="A13_ONLY_GITHUB_HOSTED_NONPRODUCTION"):
        a13._guard()


def test_prod_host_or_root_refused(monkeypatch):
    for k, v in {
        "GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted",
        "MMT_NONPRODUCTION": "1", "MMT_CERT_A13_AUDIT_ONLY": "1",
    }.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(a13.os, "geteuid", lambda: 0)
    with pytest.raises(a13.A13Refused):
        a13._guard()
    monkeypatch.setattr(a13.os, "geteuid", lambda: 1001)
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(a13.A13Refused):
        a13._guard()


def test_offline_validator_never_executes_subprocess(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        pytest.fail("CERT_A13_PARSER_MUST_NOT_EXECUTE_TOOLS")
    monkeypatch.setattr(subprocess, "run", forbidden)
    a, b = _files(tmp_path)
    assert a13.review(a, b, IMAGE, now=NOW)["components"] == 3


def test_missing_evidence_is_not_empty_success(tmp_path):
    a, _ = _files(tmp_path)
    with pytest.raises(a13.A13Refused):
        a13.review(a, tmp_path / "missing.json", IMAGE, now=NOW)


def test_database_build_timestamp_exact_freshness_edge(tmp_path):
    a, _ = _files(tmp_path)
    scan = copy.deepcopy(SCAN)
    scan["db"]["built"] = (NOW - timedelta(days=30)).isoformat()
    _, b = _files(tmp_path, scan=scan)
    assert a13.review(a, b, IMAGE, now=NOW)["vulnerability_db_age_days"] == 30
    scan["db"]["built"] = (NOW - timedelta(days=30, seconds=1)).isoformat()
    _, b = _files(tmp_path, scan=scan)
    with pytest.raises(a13.A13Refused, match="A13_DB_STALE_OR_FUTURE"):
        a13.review(a, b, IMAGE, now=NOW)
