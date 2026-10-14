"""CERT-A17 offline-only remediation ledger and A6 denial regressions."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from naseri_markets import cert_a17_remediation_review as a17

_ROOT = Path(__file__).resolve().parents[2]


def _samples():
    ledger = json.loads(
        (_ROOT / "deploy/runtime_a2/a17_remediation_review.json").read_text()
    )
    archive = json.loads(
        (_ROOT / "deploy/runtime_a2/a11_apt_closure.json").read_text()
    )
    packages = {item["package"]: item["version"] for item in archive["packages"]}
    return ledger, packages


def test_exact_immutable_repository_snapshot_and_original_a6_denial():
    result = a17.validate_repository(_ROOT)
    assert result["status"] == "CERT_A17_REMEDIATION_SOURCE_RESEARCH_FROZEN_NO_MUTATION"
    assert result["critical_open"] == 18
    assert result["high_open"] == 181
    assert result["debian_official_spot_checked_rows"] == 8
    assert result["apt_archive_pinned_critical_rows"] == 6
    assert result["image_patch_applied"] is False
    assert result["worker_execution_authorized"] is False


def test_18_exact_critical_rows_are_all_open_without_spurious_upgrades():
    ledger, packages = _samples()
    a17.validate_ledger(ledger, packages)
    assert len(ledger["critical_findings"]) == 18
    assert len({item["advisory_id"] for item in ledger["critical_findings"]}) == 17
    assert all(row["review_status"] == "OPEN_REVIEW_REQUIRED"
               for row in ledger["critical_findings"])
    assert all(row["vulnerability_fixed_certified"] is False
               for row in ledger["critical_findings"])
    assert ledger["source_a16_critical_high_total"] == 199
    assert ledger["source_a16_high_total"] == 181


def test_bookworm_5_undici_upstream_7_8_version_mismatch_preserved():
    ledger, _ = _samples()
    rows = [item for item in ledger["critical_findings"]
            if item["advisory_id"] in {"CVE-2026-13697", "CVE-2026-84961"}]
    assert len(rows) == 2
    assert all(
        item["upstream_scope_reconciliation"]
        == "VERSION_RANGES_7_8_VS_BOOKWORM_5_REQUIRE_SOURCE_AUDIT"
        for item in rows
    )
    assert all(item["vulnerability_fixed_certified"] is False for item in rows)


@pytest.mark.parametrize("change", [
    lambda x: x["critical_findings"].pop(),
    lambda x: x["critical_findings"].append(copy.deepcopy(x["critical_findings"][-1])),
    lambda x: x["critical_findings"][0].update(advisory_id="CVE-REWRITTEN"),
    lambda x: x["critical_findings"][0].update(priority="P3"),
    lambda x: x["critical_findings"][0].update(review_status="REMEDIATED"),
    lambda x: x["critical_findings"][0].update(vulnerability_fixed_certified=True),
    lambda x: x["critical_findings"][0].update(false_positive_certified=True),
    lambda x: x["critical_findings"][0].update(reachability_established=True),
    lambda x: x["critical_findings"][0].update(removed_from_runtime_certified=True),
    lambda x: x["critical_findings"][0].update(
        scanner_versions_not_approved_upgrade=False,
    ),
    lambda x: x["critical_findings"][0].update(
        scanner_suggested_upstream_versions=["999.0.0"],
    ),
    lambda x: x["critical_findings"][3].update(
        official_source_url="https://example.invalid/forged",
    ),
    lambda x: x["critical_findings"][10].update(
        upstream_scope_reconciliation="FIXED_UNAFFECTED",
    ),
    lambda x: x["critical_findings"][6].update(apt_372_archive_pinned=False),
    lambda x: x.update(worker_execution_authorized=True),
    lambda x: x.update(host_rootless_gvisor_certified=True),
    lambda x: x.update(production_authorized=True),
    lambda x: x.update(vulnerabilities_remediated_certified=True),
    lambda x: x.update(source_a16_high_total=0),
    lambda x: x.update(source_a16_evidence_fingerprint_sha256="0" * 64),
    lambda x: x["required_independent_evidence"].pop(),
    lambda x: x["required_independent_evidence"].__setitem__(
        0, "UNTRUSTED_SHORTCUT"
    ),
    lambda x: x.update(unrecognized_release_override=True),
])
def test_forged_research_finding_package_or_authority_refused(change):
    original, packages = _samples()
    modified = copy.deepcopy(original)
    change(modified)
    with pytest.raises(a17.A17Refused):
        a17.validate_ledger(modified, packages)


def test_glibc_and_sqlite_are_not_inferred_as_372_archives():
    ledger, packages = _samples()
    for pkg in ("libc6", "libc-bin", "libsqlite3-0"):
        assert pkg not in packages
        assert all(
            row["apt_372_archive_pinned"] is False
            for row in ledger["critical_findings"]
            if row["package"] == pkg
        )
    a17.validate_ledger(ledger, packages)


def test_duplicate_json_key_and_symlink_never_accepted(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text('{"schema":1,"schema":2}')
    with pytest.raises(a17.A17Refused, match="A17_DUPLICATE_JSON_KEY"):
        a17._load(f)
    g = tmp_path / "clean.json"
    g.write_text('{"schema":1}')
    f.unlink()
    f.symlink_to(g)
    with pytest.raises(a17.A17Refused, match="A17_SYMLINK_OR_MISSING_SOURCE"):
        a17._load(f)


def test_no_network_subprocess_docker_or_dependency_mutation_in_review_script():
    script = (_ROOT / "naseri_markets/cert_a17_remediation_review.py").read_text()
    for disallowed in (
        "subprocess.run(", "urllib.request", "requests.get(",
        "docker build", "docker run", "apt-get install", "pip install",
        "npm install", "RuntimeA6Denied =",
    ):
        assert disallowed not in script
