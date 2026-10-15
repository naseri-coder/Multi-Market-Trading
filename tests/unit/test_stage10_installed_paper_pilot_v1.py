"""Stage-10 installed-vs-source boundaries and restart-safe PAPER inspection tests."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from naseri_markets.installed_paper_pilot_stage10_v1 import (
    InstalledPilotRefused,
    inspect_installed_paper,
    main,
)
from naseri_markets.unified_paper_pilot_stage20_v1 import run_paper_pilot


@pytest.fixture(autouse=True)
def offline_environment(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


@pytest.fixture()
def paper_fixture(tmp_path):
    state = tmp_path / "new_pilot"
    result = run_paper_pilot(
        state, first_symbol="BTCUSD", second_symbol="ETHUSD",
        first_timeframe="5m", second_timeframe="1h",
    )
    assert result["completed_jobs"] == result["closed_paper_trades"] == 2
    assert result["exact_effects"] == 6
    return state


def inspect(state: Path, *, signal=True):
    return inspect_installed_paper(
        state, expected_dry_signals=signal,
        operator_ack=True, all_writers_stopped=True,
    )


def test_independent_inspection_is_readonly_repeatable(paper_fixture):
    state = paper_fixture
    paths = tuple(sorted(state.glob("*.sqlite")))
    before = [p.read_bytes() for p in paths]
    first = inspect(state)
    second = inspect(state)
    assert first == second
    assert [p.read_bytes() for p in paths] == before
    assert first["mode"] == "INSTALLED_TWO_BINDING_SYNTHETIC_PAPER_REOPEN_ONLY"
    assert first["runtime_jobs_done"] == first["paper_orders"] == 2
    assert first["paper_plans"] == 2
    assert first["dry_signal_commands"] == 2
    assert first["exact_initial_effects"] == 6
    assert first["paper_exits"] >= 2
    assert len(first["reliability_sha256"]) == 64
    assert len(first["recovery_decision_sha256"]) == 64
    assert first["integrity_verdict"] == "PASS"
    assert first["release_verdict"] == "BLOCKED_NONPRODUCTION_UNATTESTED"
    for gate in (
        "source_authenticated", "real_feed_used", "profitability_proven",
        "live_trading_enabled", "broker_order_sent", "telegram_sent",
        "public_release_authorized", "automatic_recovery_authorized",
        "exactly_once_guaranteed",
    ):
        assert first[gate] is False


def test_no_dry_signal_option_is_independently_bound(tmp_path):
    state = tmp_path / "no_signal"
    outcome = run_paper_pilot(state, dry_run_signals=False)
    assert outcome["exact_effects"] == 4
    assert inspect(state, signal=False)["exact_initial_effects"] == 4
    with pytest.raises(InstalledPilotRefused, match="RECONCILIATION|INCOMPLETE"):
        inspect(state, signal=True)


def test_no_auto_resume_or_overwrite_of_existing_paper(paper_fixture):
    existing = paper_fixture
    original = (existing / "effects.sqlite").read_bytes()
    with pytest.raises(ValueError, match="NEW_OWNER_PRIVATE_DIRECTORY_REQUIRED"):
        run_paper_pilot(existing)
    assert original == (existing / "effects.sqlite").read_bytes()


@pytest.mark.parametrize(("ack", "stopped"), [
    (False, True), (True, False), (False, False),
])
def test_inspection_requires_explicit_operator_stop(paper_fixture, ack, stopped):
    with pytest.raises(InstalledPilotRefused):
        inspect_installed_paper(
            paper_fixture, expected_dry_signals=True,
            operator_ack=ack, all_writers_stopped=stopped,
        )


def test_production_and_missing_nonproduction_denied(paper_fixture, monkeypatch):
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(InstalledPilotRefused, match="NONPRODUCTION"):
        inspect(paper_fixture)
    monkeypatch.delenv("MMT_PRODUCTION")
    monkeypatch.delenv("MMT_NONPRODUCTION")
    with pytest.raises(InstalledPilotRefused, match="NONPRODUCTION"):
        inspect(paper_fixture)


def test_symlink_and_world_access_and_missing_file_refused(paper_fixture, tmp_path):
    target = paper_fixture
    alias = tmp_path / "symlink_to_pilot"
    alias.symlink_to(target, target_is_directory=True)
    with pytest.raises(InstalledPilotRefused):
        inspect(alias)
    file = target / "effects.sqlite"
    file.chmod(0o644)
    with pytest.raises(InstalledPilotRefused, match="UNSAFE_STATE_FILE"):
        inspect(target)
    file.chmod(0o600)
    file.rename(target / "renamed.sqlite")
    with pytest.raises(InstalledPilotRefused, match="COMPLETE_PRIVATE_STATE"):
        inspect(target)


def test_crashed_runtime_job_blocked_without_record_replay(paper_fixture):
    state = paper_fixture
    runtime = state / "runtime.sqlite"
    with sqlite3.connect(runtime) as connection:
        job_id = connection.execute(
            "SELECT job_id FROM runtime17_jobs ORDER BY job_id LIMIT 1"
        ).fetchone()[0]
        connection.execute(
            "UPDATE runtime17_jobs SET status='QUARANTINED' WHERE job_id=?",
            (job_id,),
        )
    evidence_before = (state / "effects.sqlite").read_bytes()
    with pytest.raises(InstalledPilotRefused, match="JOB_NOT_DONE"):
        inspect(state)
    assert (state / "effects.sqlite").read_bytes() == evidence_before


def test_missing_effect_does_not_silently_certify_done_state(paper_fixture):
    state = paper_fixture
    effects = state / "effects.sqlite"
    with sqlite3.connect(effects) as connection:
        connection.execute(
            "UPDATE effect19_intents SET state='PREPARED',receipt_sha256=NULL "
            "WHERE intent_id=(SELECT intent_id FROM effect19_intents LIMIT 1)"
        )
    with pytest.raises(ValueError):
        inspect(state)


def test_cli_installed_version_and_fail_closed_approval(tmp_path, capsys, monkeypatch):
    import naseri_markets.installed_paper_pilot_stage10_v1 as module

    state = tmp_path / "cli_pilot"
    arguments = ["--state-dir", str(state), "--run", "--ack-synthetic-offline"]
    assert main(arguments[:-1]) == 2
    assert not state.exists()
    assert "STAGE10_INSTALLED_PAPER_REFUSED" in capsys.readouterr().err
    monkeypatch.setattr(module, "version", lambda _name: "wrong-version")
    assert main(arguments) == 2
    assert not state.exists()
    monkeypatch.setattr(module, "version", lambda _name: "0.4.0rc1")
    assert main(arguments) == 0
    first = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert first["mode"] == "STAGE20_SYNTHETIC_PAPER_ONLY"
    assert main(arguments) == 2
    assert "STAGE10_INSTALLED_PAPER_REFUSED" in capsys.readouterr().err
    inspect_args = [
        "--state-dir", str(state), "--inspect", "--ack-synthetic-offline",
        "--ack-writers-stopped",
    ]
    assert main(inspect_args) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["exact_initial_effects"] == 6
    assert not report["broker_order_sent"] and not report["telegram_sent"]


def test_inspect_cannot_be_called_without_ack_or_as_run_mode(paper_fixture, capsys,
                                                             monkeypatch):
    import naseri_markets.installed_paper_pilot_stage10_v1 as module
    monkeypatch.setattr(module, "version", lambda _name: "0.4.0rc1")
    args = ["--state-dir", str(paper_fixture), "--inspect",
            "--ack-synthetic-offline"]
    assert main(args) == 2
    assert "STAGE10_INSTALLED_PAPER_REFUSED" in capsys.readouterr().err
    assert main(["--state-dir", str(paper_fixture), "--run",
                 "--ack-synthetic-offline", "--ack-writers-stopped"]) == 2
    assert "STAGE10_INSTALLED_PAPER_REFUSED" in capsys.readouterr().err


def test_a6_release_exact_entrypoint_allowlist_still_refuses_unknown_commands(
    tmp_path, monkeypatch,
):
    import scripts.a6_release_preflight as preflight
    source = Path(preflight.ROOT)
    safe = tmp_path / "fake_checked_release"
    (safe / "platform_release").mkdir(parents=True)
    (safe / "production_source").mkdir()
    (safe / "pyproject.toml").write_bytes((source / "pyproject.toml").read_bytes())
    metadata = (source / "platform_release/pyproject.toml").read_text()
    assert 'naseri-paper-pilot = "naseri_markets.installed_paper_pilot_stage10_v1:main"' in metadata
    (safe / "platform_release/pyproject.toml").write_text(metadata)
    (safe / "compose.yaml").write_text(
        "name: crypto-price-action\npostgres_data:/var/lib/postgresql/data\n"
    )
    (safe / "compose.platform.yaml").write_text(
        'name: multi-market-trading\nprofiles: ["validation"]\n'
        'network_mode: none\nread_only: true\n'
    )
    (safe / "Dockerfile.platform").write_text("USER 10001:10001\n")
    (safe / "production_source/SHA256SUMS").write_text("test-sentinel\n")
    monkeypatch.setattr(preflight, "ROOT", safe)
    accepted = preflight.check()
    assert accepted["verdict"] == "A6_SEPARATE_RELEASE_PREVIEW_PASS"
    assert accepted["preview_runtime_enabled"] is False
    assert accepted["database_migration_executed"] is False
    metadata = metadata.replace(
        "[tool.setuptools.packages.find]",
        'naseri-hidden-executor = "unknown.operator:main"\n\n'
        "[tool.setuptools.packages.find]",
    )
    # An unauthorized executable must still fail the exact-script inventory
    # rather than being accepted by a wildcard or a relaxed subset policy.
    (safe / "platform_release/pyproject.toml").write_text(metadata)
    with pytest.raises(ValueError, match="A6_CLI_INVALID"):
        preflight.check()
