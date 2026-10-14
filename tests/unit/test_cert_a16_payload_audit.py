"""CERT-A16 no-Docker unit tests for strict evidence mapping and denial."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts import ci_cert_a16_payload_audit as a16


def _match(severity: str, name: str, advisory: str) -> dict:
    return {
        "artifact": {
            "type": "deb", "name": name, "version": "1.0",
        },
        "vulnerability": {
            "id": advisory, "severity": severity,
        },
    }


def _sbom() -> dict:
    return {
        "bomFormat": "CycloneDX",
        "components": [
            {
                "type": "file",
                "name": f"/usr/lib/fixed/file-{i}",
                "hashes": [{"alg": "SHA-256", "content": "a" * 64}],
            }
            for i in range(120)
        ],
    }


def _fixture():
    base = {"matches": [
        _match("Critical", "node-undici", "CVE-A"),
        _match("High", "handlebars", "CVE-B"),
        _match("High", "libc6", "CVE-C"),
        _match("Medium", "other", "CVE-D"),
    ]}
    lean = {"matches": [_match("High", "libc6", "CVE-C")]}
    comparison = {
        "schema": 1,
        "baseline": {
            "sbom_sha256": "1" * 64,
            "scan_sha256": "2" * 64,
            "image_id": "sha256:" + "a" * 64,
            "matched_advisories": 4,
            "vulnerability_db_built": "2026-10-14T06:30:34+00:00",
        },
        "lean": {
            "sbom_sha256": "3" * 64,
            "scan_sha256": "4" * 64,
            "image_id": "sha256:" + "b" * 64,
            "matched_advisories": 1,
            "vulnerability_db_built": "2026-10-14T06:30:34+00:00",
        },
        "worker_execution_authorized": False,
        "production_authorized": False,
        "reduced_grype_matches_do_not_establish_cve_remediation": True,
    }
    hashes = {
        "base_sbom": "1" * 64, "base_scan": "2" * 64,
        "lean_sbom": "3" * 64, "lean_scan": "4" * 64,
    }
    samples = {
        "schema": 1,
        "scope": "FIXED_LOCAL_IMAGE_CREATE_CP_NO_GUEST_PROCESS_STARTED",
        "baseline": {
            "id": comparison["baseline"]["image_id"],
            "files": dict.fromkeys(a16._PATHS, "c" * 64),
        },
        "lean": {
            "id": comparison["lean"]["image_id"],
            "files": dict.fromkeys(a16._PATHS, "c" * 64),
        },
        "no_worker_launch_authorization": True,
    }
    return (_sbom(), base, _sbom(), lean, comparison, samples, hashes)


def test_critical_high_never_auto_fixed_and_undici_byte_retention():
    report = a16.audit(*_fixture())
    assert report["critical_or_high_baseline_count"] == 3
    assert report["by_evidence_class"] == {
        "NOT_SCANNER_MATCHED_PAYLOAD_REMOVAL_UNPROVEN": 1,
        "NOT_SCANNER_MATCHED_SAMPLED_PAYLOAD_BYTES_RETAINED": 1,
        "SAME_ADVISORY_PACKAGE_VERSION_DETECTED_IN_LEAN": 1,
    }
    undici = next(row for row in report["findings"]
                  if row["package"] == "node-undici")
    assert undici["sampled_payload_equal_sha256"] is True
    assert undici["security_review_state"] == "OPEN"
    assert undici["cve_fixed"] is False
    assert undici["exploitable_or_reachable_proven"] is False
    assert report["all_original_findings_still_require_review"] is True
    assert report["worker_execution_authorized"] is False
    assert report["production_authorized"] is False
    assert report["broker_authorized"] is False
    assert report["telegram_authorized"] is False


def test_same_path_and_sha_still_present_even_when_scanner_misses():
    args = _fixture()
    result = a16.audit(*args)
    assert result["same_sbom_file_path_count"] == 120
    assert result["identical_shared_sbom_file_sha256_count"] == 120
    assert result["sampled_runtime_paths"][
        "/usr/share/nodejs/undici/undici-fetch.js"
    ]["bytes_identical"] is True


@pytest.mark.parametrize("mutation", [
    lambda x: x[4]["baseline"].update(scan_sha256="0" * 64),
    lambda x: x[4]["lean"].update(sbom_sha256="0" * 64),
    lambda x: x[4]["lean"].update(vulnerability_db_built="yesterday"),
    lambda x: x[4].update(worker_execution_authorized=True),
    lambda x: x[4].update(
        reduced_grype_matches_do_not_establish_cve_remediation=False,
    ),
    lambda x: x[5]["lean"].update(id="sha256:" + "f" * 64),
    lambda x: x[5].update(no_worker_launch_authorization=False),
    lambda x: x[5]["baseline"]["files"].pop(a16._PATHS[0]),
    lambda x: x[5]["lean"]["files"].update({
        a16._PATHS[0]: "z" * 64,
    }),
    lambda x: x[1]["matches"].pop(),
    lambda x: x[3]["matches"].append(_match("High", "unexpected", "CVE-F")),
])
def test_forged_or_missing_evidence_denied(mutation):
    args = list(copy.deepcopy(_fixture()))
    mutation(args)
    with pytest.raises(a16.A16Refused):
        a16.audit(*args)


def test_extra_scanner_duplicate_findings_not_hidden():
    args = list(_fixture())
    base = copy.deepcopy(args[1])
    base["matches"].append(copy.deepcopy(base["matches"][0]))
    args[1] = base
    args[4] = copy.deepcopy(args[4])
    args[4]["baseline"]["matched_advisories"] = 5
    report = a16.audit(*args)
    assert report["critical_or_high_baseline_count"] == 4
    assert sum(report["by_evidence_class"].values()) == 4


def test_production_or_unapproved_runner_rejected(monkeypatch):
    for name, value in {
        "GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted",
        "MMT_NONPRODUCTION": "1", "MMT_CERT_A16_READ_ONLY": "1",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(a16.os, "geteuid", lambda: 1001)
    a16._runner_guard()
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(a16.A16Refused):
        a16._runner_guard()
    monkeypatch.delenv("MMT_PRODUCTION")
    monkeypatch.setattr(a16.os, "geteuid", lambda: 0)
    with pytest.raises(a16.A16Refused):
        a16._runner_guard()


def test_capture_is_never_started_in_unit_suite(monkeypatch):
    monkeypatch.setattr(
        a16.subprocess, "run",
        lambda *a, **kw: pytest.fail("A16_NO_DOCKER_IN_MOCK_UNIT_TEST"),
    )
    report = a16.audit(*_fixture())
    assert report["status"] == "CERT_A16_BYTE_RETENTION_MEASURED_199_FINDINGS_UNRESOLVED"


def test_duplicate_json_field_and_symlink_denied(tmp_path):
    f = tmp_path / "duplicate.json"
    f.write_text('{"schema":1,"schema":2}')
    with pytest.raises(a16.A16Refused, match="A16_DUPLICATE_JSON_FIELD"):
        a16._read(f, 1024)
    other = tmp_path / "other.json"
    other.write_text(json.dumps({"schema": 1}))
    f.unlink()
    f.symlink_to(other)
    with pytest.raises(a16.A16Refused, match="A16_REQUIRED_REGULAR_FILE_MISSING"):
        a16._read(f, 1024)


def test_companion_scanner_payload_probe_is_read_only():
    script = Path(a16.__file__).read_text(encoding="utf-8")
    assert '"container", "create"' in script
    assert '"cp", "-L"' in script
    assert '"docker", "rm"' in script
    for forbidden in ('"docker", "start"', '"docker", "run"',
                      '"docker", "exec"'):
        assert forbidden not in script
