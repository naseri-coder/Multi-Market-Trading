"""Mock-only CERT-A14 scanner-matching and fail-closed denial regressions."""
from __future__ import annotations

import copy
import hashlib
import json

import pytest

from scripts import ci_cert_a14_grype_triage as a14

IMAGE = "sha256:" + "d" * 64
SBOM_SHA = "f" * 64


def _match(severity="Critical", name="handlebars", artifact_type="deb",
           state="wont-fix"):
    return {
        "vulnerability": {
            "id": "CVE-2026-11111", "severity": severity,
            "fix": {"state": state, "versions": []},
        },
        "artifact": {
            "name": name, "version": "4.7.7", "type": artifact_type,
            "purl": "pkg:deb/debian/handlebars@4.7.7",
            "locations": [{"path": "/usr/share/nodejs/handlebars/package.json"}],
        },
    }


def _samples():
    scan = {"matches": [
        _match(),
        _match(severity="High", name="tar", artifact_type="npm", state="fixed"),
        _match(severity="Medium", name="other"),
    ]}
    evidence = {
        "schema": 1,
        "audience": "MMT-CERT-A13-EPHEMERAL-IMAGE-EVIDENCE",
        "candidate_image_id": IMAGE,
        "sbom_cyclonedx_sha256": SBOM_SHA,
        "vulnerability_matches": 3,
        "by_severity": {
            "Critical": 1, "High": 1, "Medium": 1,
            "Low": 0, "Negligible": 0, "Unknown": 0,
        },
        "vulnerability_database_built": "2026-10-14T06:30:34+00:00",
    }
    evidence.update(dict.fromkeys(a14._FALSE_FIELDS, False))
    digest = hashlib.sha256(json.dumps(scan).encode()).hexdigest()
    evidence["grype_json_sha256"] = digest
    return scan, evidence, digest


def test_full_report_reconciles_and_grants_no_authority():
    scan, a13, sha = _samples()
    report = a14.triage(scan, sha, a13)
    assert report["all_severity_matches"] == 3
    assert report["critical_high_matches"] == 2
    assert report["critical_high_unique_advisory_ids"] == 1
    assert report["critical_matches"] == 1
    assert report["high_matches"] == 1
    assert report["by_artifact_type"] == {"deb": 1, "npm": 1}
    assert report["by_scanner_fix_state"] == {"fixed": 1, "wont-fix": 1}
    assert report["no_automatic_false_positive_classification"] is True
    assert report["no_automatic_fix_application"] is True
    assert report["gvisor_host_certified"] is False
    assert report["production_authorized"] is False
    assert report["worker_execution_authorized"] is False
    assert len(report["fingerprint_sha256"]) == 64
    assert all(item["review_state"] == "OPEN_REVIEW_REQUIRED"
               for item in report["findings"])
    assert all(item["reachability_confirmed"] is False
               for item in report["findings"])
    assert all(item["false_positive_confirmed"] is False
               for item in report["findings"])


def test_duplicated_cvss_or_cve_is_not_silently_dropped():
    scan, a13, _ = _samples()
    scan["matches"].append(copy.deepcopy(scan["matches"][0]))
    a13["vulnerability_matches"] += 1
    a13["by_severity"]["Critical"] += 1
    sha = hashlib.sha256(json.dumps(scan).encode()).hexdigest()
    a13["grype_json_sha256"] = sha
    report = a14.triage(scan, sha, a13)
    assert report["critical_matches"] == 2
    assert report["critical_high_matches"] == 3
    assert report["critical_high_unique_advisory_ids"] == 1


@pytest.mark.parametrize("key", a14._FALSE_FIELDS)
def test_forged_security_release_or_host_grants_refused(key):
    scan, a13, sha = _samples()
    a13[key] = True
    with pytest.raises(a14.A14Refused, match="A14_A13_EVIDENCE_UNTRUSTED"):
        a14.triage(scan, sha, a13)


@pytest.mark.parametrize("change", [
    lambda a: a.update(grype_json_sha256="a" * 64),
    lambda a: a.update(candidate_image_id="runtime-worker:latest"),
    lambda a: a.update(sbom_cyclonedx_sha256="unknown"),
    lambda a: a.update(schema=2),
    lambda a: a.update(audience="EXTERNAL_RELEASE_AUTHORITY"),
])
def test_source_fingerprint_or_schema_changed_refused(change):
    scan, a13, sha = _samples()
    change(a13)
    with pytest.raises(a14.A14Refused):
        a14.triage(scan, sha, a13)


def test_drifted_match_counts_or_severity_is_denied():
    scan, a13, sha = _samples()
    a13["by_severity"]["High"] = 0
    with pytest.raises(a14.A14Refused, match="A14_A13_SEVERITY_COUNTS"):
        a14.triage(scan, sha, a13)
    scan, a13, sha = _samples()
    a13["vulnerability_matches"] = 2
    with pytest.raises(a14.A14Refused, match="A14_RAW_MATCH_COUNT"):
        a14.triage(scan, sha, a13)


@pytest.mark.parametrize("mutate", [
    lambda m: m["vulnerability"].update(severity="Impossible"),
    lambda m: m["artifact"].update(name=None),
    lambda m: m["artifact"].update(version=[]),
    lambda m: m["artifact"].update(type=""),
    lambda m: m["vulnerability"].pop("fix"),
    lambda m: m["vulnerability"]["fix"].update(versions=[""] * 33),
    lambda m: m["artifact"].update(locations=[{"path": 14}]),
])
def test_critical_high_unparseable_matches_not_silently_filtered(mutate):
    scan, a13, sha = _samples()
    mutate(scan["matches"][0])
    with pytest.raises(a14.A14Refused):
        a14.triage(scan, sha, a13)


def test_read_json_duplicate_keys_and_symlink_refused(tmp_path):
    payload = tmp_path / "scan.json"
    payload.write_text('{"matches":[],"matches":[]}')
    with pytest.raises(a14.A14Refused, match="A14_DUPLICATE_JSON_FIELD"):
        a14._read(payload, 2048)
    src = tmp_path / "source.json"
    src.write_text('{"matches":[]}')
    payload.unlink()
    payload.symlink_to(src)
    with pytest.raises(a14.A14Refused, match="A14_SYMLINK_INPUT_REFUSED"):
        a14._read(payload, 2048)


def test_valid_evidence_raw_file_digest(tmp_path):
    scan, a13, _ = _samples()
    scan_path = tmp_path / "scan.json"
    a13_path = tmp_path / "a13.json"
    scan_path.write_text(json.dumps(scan))
    a13_path.write_text(json.dumps(a13))
    result, sha = a14._read(scan_path, a14._SCAN_LIMIT)
    summary, _ = a14._read(a13_path, a14._EVIDENCE_LIMIT)
    assert a14.triage(result, sha, summary)["high_matches"] == 1


def test_vulnerability_wont_fix_remains_open_review():
    scan, a13, sha = _samples()
    report = a14.triage(scan, sha, a13)
    deb = next(x for x in report["findings"] if x["artifact_type"] == "deb")
    assert deb["fix_state_as_reported"] == "wont-fix"
    assert deb["debian_backport_assessed"] is False
    assert deb["remediation_authorized"] is False
    assert "VERIFY_DEBIAN_ADVISORY" in deb["next_review"]
