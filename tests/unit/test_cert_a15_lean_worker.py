"""CERT-A15 strictly mock-only regression; no real Docker or host mutation."""
from __future__ import annotations

import copy
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from deploy.runtime_a2 import a15_export_runtime as exporter
from scripts import ci_cert_a15_image_compare as a15

_ROOT = Path(__file__).resolve().parents[2]
_BASE_IMAGE = "sha256:" + "a" * 64
_LEAN_IMAGE = "sha256:" + "b" * 64
_NOW = datetime(2026, 10, 14, 15, tzinfo=UTC)


def _scan(severity="High"):
    return {
        "descriptor": {
            "name": "grype",
            "db": {"status": {"built": "2026-10-14T10:00:00Z"}},
        },
        "matches": [{
            "vulnerability": {"id": "CVE-TEST-123", "severity": severity},
            "artifact": {"name": "libnode108", "version": "18.20.4"},
        }],
    }


def _sbom():
    return {
        "bomFormat": "CycloneDX",
        "components": [{"name": "libnode108", "version": "18.20.4"}],
    }


def _files(root, *, scan=None, sbom=None):
    root.mkdir()
    src = root / "s.json"
    vulnerabilities = root / "v.json"
    src.write_text(json.dumps(_sbom() if sbom is None else sbom))
    vulnerabilities.write_text(json.dumps(_scan() if scan is None else scan))
    return src, vulnerabilities


def test_real_candidate_contract_requires_prior_local_image_and_same_digest():
    recipe = (
        _ROOT / "deploy/runtime_a2/Dockerfile.a15-lean"
    ).read_text()
    lines = [s.strip() for s in recipe.splitlines() if s.startswith("FROM ")]
    assert lines == [
        "FROM mmt/runtime-a2-candidate:pr AS pinned-a2-fixture-source",
        "FROM python:3.12-slim-bookworm@sha256:"
        "34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258",
    ]
    assert "COPY --from=pinned-a2-fixture-source /opt/mmt/a15-rootfs/ /" in recipe
    assert "USER 65534:65534" in recipe
    assert 'ENTRYPOINT ["/opt/mmt/bin/runtime-a1-worker"]' in recipe
    assert not any(needle in recipe for needle in (
        "apt-get", "npm install", "pip install", "COPY scripts/",
        "--privileged", "ENV MMT_PRODUCTION=1",
    ))
    ignore = (_ROOT / "deploy/runtime_a2/Dockerfile.a15-lean.dockerignore")
    assert ignore.read_text().splitlines() == [
        "# CERT-A15 narrow candidate-specific context. No repo/source/secrets copied.",
        "**", "!deploy/", "!deploy/runtime_a2/",
        "!deploy/runtime_a2/a15_export_runtime.py",
    ]


def test_benign_comparison_reports_observations_not_fixed_vulnerabilities(tmp_path):
    bsbom, bscan = _files(tmp_path / "base")
    lsbom, lscan = _files(tmp_path / "lean", scan={
        "descriptor": _scan()["descriptor"], "matches": [],
    })
    result = a15.compare(
        bsbom, bscan, lsbom, lscan, _BASE_IMAGE, _LEAN_IMAGE,
        950_000_000, 280_000_000, now=_NOW,
    )
    assert result["image_bytes_saved"] == 670_000_000
    assert result["image_size_reduced"] is True
    assert result["observed_match_delta_lean_minus_baseline"]["High"] == -1
    assert result["observed_total_match_delta"] == -1
    assert result["dpkg_metadata_removed_can_hide_vulnerable_library_inventory"] is True
    assert result["reduced_grype_matches_do_not_establish_cve_remediation"] is True
    assert result["original_apt_372_lock_untouched"] is True
    assert len(result["fingerprint_sha256"]) == 64
    for name, val in a15._NON_RELEASE.items():
        assert val is False
        assert result[name] is False


def test_no_size_gain_is_not_forged_into_a_success(tmp_path):
    base = _files(tmp_path / "base")
    lean = _files(tmp_path / "lean")
    result = a15.compare(
        *base, *lean, _BASE_IMAGE, _LEAN_IMAGE, 100, 120, now=_NOW,
    )
    assert result["image_bytes_saved"] == -20
    assert result["image_size_reduced"] is False
    assert result["observed_total_match_delta"] == 0


@pytest.mark.parametrize("change", [
    lambda scan: scan["descriptor"]["db"]["status"].update(
        built="2026-10-10T10:00:00Z"
    ),
    lambda scan: scan["descriptor"].update(name="unapproved-tool"),
    lambda scan: scan.update(matches=None),
    lambda scan: scan["matches"][0]["vulnerability"].update(severity="Whatever"),
])
def test_invalid_or_changed_advisory_source_fails_closed(tmp_path, change):
    base = _files(tmp_path / "base")
    lean_scan = copy.deepcopy(_scan())
    change(lean_scan)
    lean = _files(tmp_path / "lean", scan=lean_scan)
    with pytest.raises((a15.A15Refused, ValueError)):
        a15.compare(*base, *lean, _BASE_IMAGE, _LEAN_IMAGE, 100, 80, now=_NOW)


def test_missing_or_forged_image_ids_refused(tmp_path):
    base = _files(tmp_path / "base")
    lean = _files(tmp_path / "lean")
    for first, second in (
        ("image:latest", _LEAN_IMAGE),
        (_BASE_IMAGE, _BASE_IMAGE),
        (_BASE_IMAGE, "sha256:bad"),
    ):
        with pytest.raises(a15.A15Refused, match="A15_IMAGE_ID_OR_BYTE_SIZE_INVALID"):
            a15.compare(*base, *lean, first, second, 100, 80, now=_NOW)


def test_missing_or_forged_sbom_refused(tmp_path):
    base = _files(tmp_path / "base")
    lean = _files(tmp_path / "lean", sbom={"bomFormat": "SPDX", "components": []})
    with pytest.raises(a15.A15Refused, match="A15_SBOM_MISSING_OR_INVALID"):
        a15.compare(*base, *lean, _BASE_IMAGE, _LEAN_IMAGE, 100, 80, now=_NOW)


def test_elf_soname_symlink_filename_is_preserved(tmp_path):
    real = tmp_path / "libuv.so.1.0.0"
    real.write_bytes(b"fixed-public-runtime-elf-bytes")
    alias = tmp_path / "libuv.so.1"
    alias.symlink_to(real)
    root = tmp_path / "stage-root"
    root.mkdir()
    exported = exporter._copy_file(alias, root)
    assert exported["path"].endswith("/libuv.so.1")
    expected = root / alias.relative_to("/")
    assert expected.read_bytes() == real.read_bytes()
    assert not (root / real.relative_to("/")).exists()


def test_nested_node_dependencies_require_fixed_elf_libraries(monkeypatch):
    response = subprocess.CompletedProcess(
        (), 0, stdout=(
            b"linux-vdso.so.1 (0x1)\n"
            b"libnode.so.108 => /lib/x86_64-linux-gnu/libnode.so.108 (0x1)\n"
            b"libc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x1)\n"
            b"/lib64/ld-linux-x86-64.so.2 (0x1)\n"
        ), stderr=b"",
    )
    monkeypatch.setattr(exporter.subprocess, "run", lambda *a, **k: response)
    monkeypatch.setattr(exporter.Path, "is_file", lambda self: True)
    deps = exporter._node_dependencies()
    assert len(deps) == 3
    assert any("libnode" in x.name for x in deps)


def test_transitive_libnode_dependency_libuv_is_not_omitted(monkeypatch):
    calls = []

    def ldd(argv, **kwargs):
        target = argv[1]
        calls.append(target)
        if target == "/usr/bin/node":
            output = (
                b"libnode.so.108 => /lib/x86_64-linux-gnu/libnode.so.108 (0x1)\n"
                b"libc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x1)\n"
                b"/lib64/ld-linux-x86-64.so.2 (0x1)\n"
            )
        elif target.endswith("libnode.so.108"):
            output = (
                b"libuv.so.1 => /lib/x86_64-linux-gnu/libuv.so.1 (0x1)\n"
                b"libc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x1)\n"
            )
        else:
            output = b"linux-vdso.so.1 (0x1)\n"
        return subprocess.CompletedProcess(argv, 0, stdout=output, stderr=b"")

    monkeypatch.setattr(exporter.subprocess, "run", ldd)
    monkeypatch.setattr(exporter.Path, "is_file", lambda self: True)
    deps = exporter._node_dependencies()
    assert any(p.name == "libuv.so.1" for p in deps)
    assert any(p.name == "libnode.so.108" for p in deps)
    assert any(path.endswith("libnode.so.108") for path in calls)
    assert len(deps) == 4


@pytest.mark.parametrize("ldd", [
    b"libnode.so.108 => not found\n",
    b"libnode.so.108 => /tmp/external.so (0x1)\n",
    b"",
    b"libc.so.6 => /lib/x86_64-linux-gnu/libc.so.6 (0x1)\n",
])
def test_missing_or_unknown_runtime_native_libraries_refused(monkeypatch, ldd):
    response = subprocess.CompletedProcess((), 0, stdout=ldd, stderr=b"")
    monkeypatch.setattr(exporter.subprocess, "run", lambda *a, **k: response)
    monkeypatch.setattr(exporter.Path, "is_file", lambda self: True)
    with pytest.raises(exporter.A15ExportRefused):
        exporter._node_dependencies()


@pytest.mark.parametrize("missing", [
    "GITHUB_ACTIONS", "RUNNER_ENVIRONMENT", "MMT_NONPRODUCTION",
    "MMT_CERT_A15_COMPARE_ONLY",
])
def test_missing_ci_scope_fails_closed(monkeypatch, missing):
    for key, val in {
        "GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted",
        "MMT_NONPRODUCTION": "1", "MMT_CERT_A15_COMPARE_ONLY": "1",
    }.items():
        monkeypatch.setenv(key, val)
    monkeypatch.delenv(missing)
    monkeypatch.setattr(a15.os, "geteuid", lambda: 1001)
    with pytest.raises(a15.A15Refused):
        a15._check_scope()


def test_production_refused_even_under_mock_hosted_ci(monkeypatch):
    for key, val in {
        "GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted",
        "MMT_NONPRODUCTION": "1", "MMT_CERT_A15_COMPARE_ONLY": "1",
    }.items():
        monkeypatch.setenv(key, val)
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    monkeypatch.setattr(a15.os, "geteuid", lambda: 1001)
    with pytest.raises(a15.A15Refused):
        a15._check_scope()
