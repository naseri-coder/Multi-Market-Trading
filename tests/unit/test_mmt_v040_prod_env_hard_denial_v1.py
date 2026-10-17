"""Explicit production-setting hard denials for all R35-R38 release gates.

All tests use ephemeral paths, never install packages, sign releases, or trade.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scripts import mmt_r35_offline_preview_install_v1 as r35
from scripts import mmt_r36_offline_release_provenance_v1 as r36
from scripts import mmt_r37_offline_signed_manifest_verify_v1 as r37
from scripts import mmt_r38_signed_offline_preview_install_v1 as r38


@pytest.mark.parametrize("setting", ("", "0", "1", "false", "FALSE", "no"))
def test_any_explicit_production_setting_denied_before_file_or_network_io(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, setting: str
) -> None:
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.setenv("MMT_PRODUCTION", setting)
    # Force the documented supported Python version in gate-only tests.
    # An actual nonroot 3.12 installer run is a SEPARATE release gate.
    monkeypatch.setattr(r35.sys, "version_info", (3, 12, 9))

    target = tmp_path / "must-not-exist"
    with pytest.raises(r35.R35Refused, match="R35_NONPRODUCTION_PY312_REQUIRED"):
        r35._gate(install=False, ack=False)

    with pytest.raises(r36.R36Refused, match="R36_OFFLINE_PY312_ONLY"):
        r36.audit(
            repository=tmp_path / "missing-checkout",
            wheel=tmp_path / "missing.whl",
            expected_wheel_sha256="0" * 64,
            expected_source_commit="a" * 40,
        )

    with pytest.raises(r37.R37Refused, match="R37_NONPRODUCTION_PY312_REQUIRED"):
        r37.verify(
            manifest=tmp_path / "missing-manifest.json",
            signature=tmp_path / "missing-signature",
            wheel=tmp_path / "missing.whl",
            trusted_public_key=tmp_path / "missing-key.pem",
            trusted_public_key_spki_sha256="0" * 64,
            expected_source_commit="a" * 40,
        )

    with pytest.raises(r38.R38Refused, match="R38_NONPRODUCTION_REQUIRED"):
        r38.preflight(
            manifest=tmp_path / "missing-manifest.json",
            signature=tmp_path / "missing-signature",
            wheel=tmp_path / "missing.whl",
            trusted_public_key=tmp_path / "missing-key.pem",
            trusted_public_key_spki_sha256="0" * 64,
            expected_source_commit="a" * 40,
            expected_manifest_sha256="0" * 64,
            policy=tmp_path / "missing-policy",
            expected_policy_sha256="0" * 64,
            destination=target,
        )
    assert not target.exists()
    assert not any(tmp_path.iterdir())


def test_r35_with_no_explicit_production_setting_keeps_check_only_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    monkeypatch.setattr(r35.sys, "version_info", (3, 12, 9))
    r35._gate(install=False, ack=False)

    with pytest.raises(r35.R35Refused, match="R35_EXPLICIT_OFFLINE_INSTALL_ACK_REQUIRED"):
        r35._gate(install=True, ack=False)


def test_development_installer_uses_presence_guard_not_value_check() -> None:
    source = (Path(__file__).resolve().parents[2]
              / "scripts/install_platform_dev.sh").read_text()
    assert '[[ "${MMT_NONPRODUCTION:-}" != 1 || -v MMT_PRODUCTION' in source
    assert '"${MMT_PRODUCTION:-}" == 1' not in source
    assert "--ack-isolated-dev-install" in source
