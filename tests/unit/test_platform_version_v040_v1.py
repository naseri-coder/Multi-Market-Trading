"""Offline v0.4.0 release-identity transition regressions; no release grant."""
from __future__ import annotations

import json

import pytest

from naseri_markets.platform_version_policy_v1 import require_offline_platform_version


@pytest.mark.parametrize("release", ("0.4.0rc1", "0.4.0"))
def test_exact_rc_or_final_identity(release):
    assert require_offline_platform_version(release) == release


@pytest.mark.parametrize("release", (
    None, True, False, 4, b"0.4.0", "", " 0.4.0", "0.4.0 ",
    "0.4.0RC1", "0.4.0.dev1", "0.4.0.post1", "0.4.1", "0.3.2",
    "4.0.0", "0.4.0+unsigned", "v0.4.0",
))
def test_unknown_identity_refused_without_coercion(release):
    with pytest.raises(ValueError, match="^UNEXPECTED_RELEASE_VERSION$"):
        require_offline_platform_version(release)


@pytest.mark.parametrize("release", ("0.4.0rc1", "0.4.0"))
def test_inert_platform_cli_uses_installed_identity(release, monkeypatch, capsys):
    from naseri_markets import platform_cli

    monkeypatch.setattr(platform_cli, "_installed_version", lambda: release)
    assert platform_cli.main(["--check"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["version"] == release
    assert report["network_enabled"] is False
    assert report["orders_enabled"] is False
    assert report["telegram_enabled"] is False
    assert report["legacy_database_attached"] is False


@pytest.mark.parametrize("release", ("0.3.2", "0.4.1", "0.4.0rc2"))
def test_inert_platform_cli_denies_other_versions(release, monkeypatch, capsys):
    from naseri_markets import platform_cli

    monkeypatch.setattr(platform_cli, "_installed_version", lambda: release)
    assert platform_cli.main(["--check"]) == 2
    assert "A6_PREVIEW_REFUSED" in capsys.readouterr().err


@pytest.mark.parametrize("release", ("0.4.0rc1", "0.4.0"))
def test_paper_pilot_installed_identity_nonproduction_only(release, monkeypatch):
    import naseri_markets.installed_paper_pilot_stage10_v1 as pilot

    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    monkeypatch.setattr(pilot, "version", lambda _: release)
    pilot._gate(ack=True, installed=True)

    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(pilot.InstalledPilotRefused,
                       match="EXPLICIT_NONPRODUCTION_ACK_REQUIRED"):
        pilot._gate(ack=True, installed=True)


@pytest.mark.parametrize("release", ("0.3.2", "0.4.1", "4.0.0"))
def test_paper_pilot_unknown_installed_version_denied(release, monkeypatch):
    import naseri_markets.installed_paper_pilot_stage10_v1 as pilot

    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)
    monkeypatch.setattr(pilot, "version", lambda _: release)
    with pytest.raises(pilot.InstalledPilotRefused, match="PREVIEW_VERSION_MISMATCH"):
        pilot._gate(ack=True, installed=True)
