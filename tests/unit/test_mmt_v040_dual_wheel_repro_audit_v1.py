"""Standalone dual Wheel equality requires signed RC-overlay source custody.

Tests inherit the audited ephemeral 226-module Git + Ed25519 fixture, but
never build or run code from packages, nor claim independent builders.
"""
from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

from scripts import mmt_v040_dual_wheel_repro_audit_v1 as dual
from scripts import mmt_v040_rc_overlay_signed_custody_v1 as overlay
from scripts import mmt_v040_signed_artifact_preflight_v1 as stable
from test_mmt_v040_rc_overlay_signed_custody_v1 import example  # shared real-Git test fixture


@pytest.fixture
def pair(example, tmp_path):
    _, _, sign, _ = example
    params = sign()
    second_parent = tmp_path / "second-build-artifact"
    second_parent.mkdir(mode=0o700)
    second = second_parent / stable.WHEEL_NAME
    shutil.copyfile(params["wheel"], second)
    params["second_wheel"] = second
    params["expected_second_wheel_sha256"] = hashlib.sha256(second.read_bytes()).hexdigest()
    return params


def test_two_signed_wheel_files_identical_with_complete_rc_source_custody(pair):
    result = dual.audit(**pair)
    assert result["public_modules_verified"] == 226
    assert result["byte_identical"] is True
    assert result["distinct_wheel_files"] is True
    assert result["first_wheel_sha256"] == result["second_wheel_sha256"]
    for key in (
        "independent_build_proven", "fresh_build_on_python312_proven",
        "source_package_version_promoted", "writes_performed", "install_authorized",
        "public_release_authorized", "live_trading_authorized",
        "telegram_publication_authorized",
    ):
        assert result[key] is False


def test_second_artifact_external_pin_mismatch_refused(pair):
    pair["expected_second_wheel_sha256"] = "0" * 64
    with pytest.raises(dual.DualWheelRefused, match="V040_DUAL_SECOND_EXTERNAL_PIN_MISMATCH"):
        dual.audit(**pair)


def test_distinct_artifact_with_correct_own_pin_but_different_bytes_refused(pair):
    raw = pair["second_wheel"].read_bytes()
    pair["second_wheel"].write_bytes(raw + b"differently-packaged")
    pair["expected_second_wheel_sha256"] = hashlib.sha256(
        pair["second_wheel"].read_bytes()
    ).hexdigest()
    with pytest.raises(dual.DualWheelRefused, match="V040_DUAL_WHEELS_NOT_BYTE_IDENTICAL"):
        dual.audit(**pair)


def test_cannot_compare_wheel_against_itself(pair):
    pair["second_wheel"] = pair["wheel"]
    with pytest.raises(dual.DualWheelRefused, match="V040_DUAL_DISTINCT_ARTIFACT_PATHS_REQUIRED"):
        dual.audit(**pair)


def test_second_artifact_symlink_is_denied(pair):
    link = pair["second_wheel"].parent / ("alias-" + stable.WHEEL_NAME)
    # Must have the exactly expected filename; place the link in a new parent.
    link_parent = pair["second_wheel"].parent.parent / "linked"
    link_parent.mkdir()
    link = link_parent / stable.WHEEL_NAME
    link.symlink_to(pair["second_wheel"])
    pair["second_wheel"] = link
    with pytest.raises(dual.DualWheelRefused, match="V040_DUAL_DISTINCT_ARTIFACT_PATHS_REQUIRED"):
        dual.audit(**pair)


def test_second_artifact_hardlink_of_first_denied(pair):
    pair["second_wheel"].unlink()
    pair["second_wheel"].hardlink_to(pair["wheel"])
    with pytest.raises(dual.DualWheelRefused, match="V040_DUAL_DISTINCT_REGULAR_FILES_REQUIRED"):
        dual.audit(**pair)


def test_second_artifact_wrong_filename_refused(pair):
    renamed = pair["second_wheel"].with_name("multi_market_trading-0.4.0rc1-py3-none-any.whl")
    pair["second_wheel"].rename(renamed)
    pair["second_wheel"] = renamed
    with pytest.raises(dual.DualWheelRefused, match="V040_DUAL_DISTINCT_ARTIFACT_PATHS_REQUIRED"):
        dual.audit(**pair)


@pytest.mark.parametrize("setting", ("", "0", "1", "false"))
def test_any_defined_production_env_denied(pair, monkeypatch, setting):
    monkeypatch.setenv("MMT_PRODUCTION", setting)
    with pytest.raises(dual.DualWheelRefused, match="V040_DUAL_NONPRODUCTION_REQUIRED"):
        dual.audit(**pair)


def test_unreviewed_secondary_pin_refused_before_signed_verification(pair):
    pair["expected_second_wheel_sha256"] = "not-a-hex-pin"
    with pytest.raises(dual.DualWheelRefused, match="V040_DUAL_EXTERNAL_SECOND_PIN_REQUIRED"):
        dual.audit(**pair)


def test_primary_wheel_mutation_denied_even_when_secondary_matches_old_signed_wheel(pair):
    pair["wheel"].write_bytes(pair["wheel"].read_bytes() + b"tampered")
    with pytest.raises(stable.StableArtifactRefused, match="V040_WHEEL_BYTES_MISMATCH"):
        dual.audit(**pair)


def test_bad_signed_manifest_refused_even_if_two_wheel_copies_identical(pair):
    pair["signature"].write_bytes(b"0" * 64)
    with pytest.raises(stable.StableArtifactRefused, match="V040_SIGNATURE_VERIFICATION_FAILED"):
        dual.audit(**pair)


def test_broken_overlay_pin_denied_even_for_byte_identical_artifacts(pair):
    pair["expected_overlay_sha256"] = "0" * 64
    with pytest.raises(overlay.OverlayCustodyRefused, match="V040_OVERLAY_METADATA_PIN_MISMATCH"):
        dual.audit(**pair)


def test_safe_cli_has_no_build_or_install_option():
    source = (Path(__file__).resolve().parents[2]
              / "scripts/mmt_v040_dual_wheel_repro_audit_v1.py").read_text()
    assert "--install" not in source
    assert "--publish" not in source
    assert "independent_build_proven\": False" in source
