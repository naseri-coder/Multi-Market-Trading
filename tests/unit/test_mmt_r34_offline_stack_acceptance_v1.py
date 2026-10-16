"""R34 isolated deterministic evidence and runner selection tests; no subprocess tests."""
from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from naseri_markets import mmt_r34_offline_stack_acceptance_v1 as a34
from scripts import mmt_r34_manual_stack_acceptance_v1 as runner


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


def digest():
    return hashlib.sha256(b"R34 synthetic source and empty output").hexdigest()


def fake_evidence(*, green=False):
    rows = [
        a34.R34ToolFinding(name, "PASS", 0, digest())
        if green else a34.R34ToolFinding(name, "NOT_RUN", None, None)
        for name in (
            "R27", "R28", "R29", "R30", "R31", "R32", "R33",
            "RUFF_R28_TO_R34", "FULL_UNIT_SUITE", "STATIC_SYNTAX",
        )
    ]
    return a34.R34OfflineEvidence(
        pinned_checkout_head="a" * 40,
        observed_checkout_head="a" * 40,
        checkout_clean_pre_and_post=True,
        local_test_runner_executed=green,
        results=tuple(rows),
    )


def test_r34_initial_empty_evidence_never_claims_success():
    review = a34.review_r34_local_stack_evidence(
        fake_evidence(), operator_ack=True,
    )
    assert review["decision"] == "REVIEW_ONLY_RELEASE_BLOCKED"
    assert review["blocker_count"] >= 12
    assert review["stage_test_statuses"]["R29"] == "NOT_RUN"
    assert review["live_orders_authorized"] is False
    assert review["connected_paper_authorized"] is False
    assert review["server_deployment_authorized"] is False
    assert review["telegram_send_authorized"] is False
    assert len(review["review_sha256"]) == 64


def test_r34_even_fake_all_green_tests_do_not_authorize_release():
    forged = replace(
        fake_evidence(green=True),
        independent_test_witness_attested=True,
        upstream_prs_reviewed_and_merged=True,
        r29_true_prospective_oos_accepted=True,
        venue_permission_verified=True,
        real_account_position_state_verified=True,
        real_production_rollback_rehearsed=True,
    )
    report = a34.review_r34_local_stack_evidence(
        forged, operator_ack=True,
    )
    assert report["blockers"] == [
        "R34_LOCAL_EVIDENCE_NOT_INDEPENDENT_RELEASE_AUTHORITY",
    ]
    assert report["decision"] == "REVIEW_ONLY_RELEASE_BLOCKED"
    assert report["live_orders_authorized"] is False


def test_r34_single_ruff_failure_must_be_reported():
    item = fake_evidence(green=True)
    rows = list(item.results)
    rows[7] = a34.R34ToolFinding("RUFF_R28_TO_R34", "FAIL", 1, digest())
    report = a34.review_r34_local_stack_evidence(
        replace(item, results=tuple(rows)), operator_ack=True,
    )
    assert "R34_RUFF_R28_TO_R34_FAIL" in report["blockers"]


def test_r34_git_head_and_dirty_checkout_denied():
    item = fake_evidence()
    data = replace(
        item, observed_checkout_head="b" * 40,
        checkout_clean_pre_and_post=False,
    )
    report = a34.review_r34_local_stack_evidence(
        data, operator_ack=True,
    )
    assert "R34_CHECKOUT_HEAD_NOT_PINNED" in report["blockers"]
    assert "R34_CHECKOUT_NOT_CLEAN" in report["blockers"]


def test_r34_reject_false_or_unspecified_test_success():
    with pytest.raises(a34.R34AcceptanceRefused, match="PASS_WITHOUT"):
        a34.R34ToolFinding("R28", "PASS", 0, None)
    with pytest.raises(a34.R34AcceptanceRefused, match="PASS_WITHOUT"):
        a34.R34ToolFinding("R28", "PASS", 1, digest())
    with pytest.raises(a34.R34AcceptanceRefused, match="NOT_RUN_MUST"):
        a34.R34ToolFinding("R28", "NOT_RUN", 0, None)
    with pytest.raises(a34.R34AcceptanceRefused, match="UNTRUSTED_TEST"):
        a34.R34ToolFinding("R28", "GUESSED_SUCCESS", None, None)


def test_r34_missing_or_reordered_stage_result_denied():
    item = fake_evidence()
    with pytest.raises(a34.R34AcceptanceRefused, match="EXACT_EVIDENCE"):
        replace(item, results=item.results[1:])
    with pytest.raises(a34.R34AcceptanceRefused, match="EXACT_EVIDENCE"):
        replace(item, results=item.results[::-1])
    with pytest.raises(a34.R34AcceptanceRefused, match="EXACT_EVIDENCE"):
        replace(item, pinned_checkout_head="not_a_sha")
    with pytest.raises(a34.R34AcceptanceRefused, match="TYPED_ATTEST"):
        replace(item, venue_permission_verified=1)


def test_r34_active_production_env_or_no_ack_refused(monkeypatch):
    with pytest.raises(a34.R34AcceptanceRefused, match="EXPLICIT_NONPRODUCTION"):
        a34.review_r34_local_stack_evidence(fake_evidence())
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(a34.R34AcceptanceRefused, match="EXPLICIT_NONPRODUCTION"):
        a34.review_r34_local_stack_evidence(
            fake_evidence(), operator_ack=True,
        )


def test_r34_fixed_stage_pr_inventory_covers_all_draft_dependencies():
    rows = a34.known_upstream_pr_snapshots()
    assert tuple(rows) == (
        "R27", "R28", "R29", "R30", "R31", "R32", "R33",
    )
    assert rows["R27"]["pr"] == 320
    assert rows["R33"]["pr"] == 326
    assert all(
        entry["status_as_of_2026_10_16"] == "OPEN_DRAFT_UNMERGED"
        for entry in rows.values()
    )


def test_r34_default_cli_collect_uses_only_static_parse(monkeypatch):
    root = Path("/path/to/review")
    seen = []
    monkeypatch.setattr(runner, "_head", lambda *_: seen.append("head"))
    monkeypatch.setattr(
        runner, "_git",
        lambda _, *args: (
            "a" * 40 if args == ("rev-parse", "HEAD") else ""
        ),
    )
    monkeypatch.setattr(
        runner, "_run", lambda *args, **kw: (
            seen.append("EXECUTED"),
            a34.R34ToolFinding("R28", "PASS", 0, digest()),
        )[1],
    )
    monkeypatch.setattr(
        runner, "_syntax",
        lambda root: a34.R34ToolFinding(
            "STATIC_SYNTAX", "PASS", 0, digest(),
        ),
    )
    evidence = runner.collect_r34_offline_evidence(
        root=root, expected_head="a" * 40, operator_ack=True,
    )
    assert "EXECUTED" not in seen
    assert evidence.results[0].status == "NOT_RUN"
    assert evidence.results[-1].status == "PASS"
    assert evidence.local_test_runner_executed is False


def test_r34_stage_runner_explicit_approved_commands_and_only_allowlist(monkeypatch):
    monkeypatch.setattr(runner, "_project_python_preflight", lambda *_: None)
    cmds = []

    def fake_run(root, name, argv, timeout):
        cmds.append((name, argv, timeout))
        return a34.R34ToolFinding(name, "PASS", 0, digest())

    monkeypatch.setattr(runner, "_head", lambda *_: None)
    monkeypatch.setattr(
        runner, "_git",
        lambda _, *args: (
            "a" * 40 if args == ("rev-parse", "HEAD") else ""
        ),
    )
    monkeypatch.setattr(runner, "_run", fake_run)
    monkeypatch.setattr(
        runner, "_syntax",
        lambda root: a34.R34ToolFinding(
            "STATIC_SYNTAX", "PASS", 0, digest(),
        ),
    )
    result = runner.collect_r34_offline_evidence(
        root=Path("/isolated/offline/git"),
        expected_head="a" * 40, run_stage_tests=True,
        run_ruff=True, run_full_suite=True,
        operator_ack=True,
    )
    assert len(cmds) == 9  # 7 stages, Ruff, full unit tests
    assert tuple(c[0] for c in cmds) == (
        "R27", "R28", "R29", "R30", "R31", "R32", "R33",
        "RUFF_R28_TO_R34", "FULL_UNIT_SUITE",
    )
    assert all(
        "-p" in c[1] and "pytest_asyncio.plugin" in c[1]
        for c in cmds if c[0] != "RUFF_R28_TO_R34"
    )
    assert result.results[-1].status == "PASS"
    assert result.local_test_runner_executed is True


def test_r34_environment_redacts_ambient_tokens(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "secret-one")
    monkeypatch.setenv("DATABASE_URL", "secret-two")
    monkeypatch.setenv("EXCHANGE_API_KEY", "secret-three")
    env = runner._child_environment()
    assert "TELEGRAM_BOT_TOKEN" not in env
    assert "DATABASE_URL" not in env
    assert "EXCHANGE_API_KEY" not in env
    assert env["PYTHONDONTWRITEBYTECODE"] == "1"
    assert env["MMT_NONPRODUCTION"] == "1"


def test_r34_private_receipt_is_exclusive_and_owner_only(tmp_path):
    parent = tmp_path / "private"
    parent.mkdir(mode=0o700)
    path = parent / "offline-review.json"
    runner._private_new_report(path, b'{"decision":"REVIEW_ONLY_RELEASE_BLOCKED"}')
    assert path.stat().st_mode & 0o077 == 0
    with pytest.raises(a34.R34AcceptanceRefused, match="EXCLUSIVE_REPORT"):
        runner._private_new_report(path, b"forged")
    assert path.read_bytes().startswith(b'{"decision"')


def test_r34_private_receipt_refuses_public_dir_and_symlink(tmp_path):
    public = tmp_path / "public"
    public.mkdir(mode=0o755)
    with pytest.raises(a34.R34AcceptanceRefused, match="PRIVATE_0700"):
        runner._private_new_report(public / "report", b"bad")
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    linked = private / "linked"
    linked.symlink_to(public)
    with pytest.raises(a34.R34AcceptanceRefused, match="PRIVATE_NEW_REPORT"):
        runner._private_new_report(linked / "report", b"bad")


def test_r34_no_live_actions_exposed():
    assert not hasattr(runner, "connect_exchange")
    assert not hasattr(runner, "send_message")
    assert not hasattr(runner, "submit_order")
    assert not hasattr(runner, "deploy")
    assert not hasattr(runner, "retry_unknown")


def test_r34_static_preflight_failure_prevents_test_execution(monkeypatch):
    executed = []
    monkeypatch.setattr(runner, "_head", lambda *_: None)
    monkeypatch.setattr(
        runner, "_syntax",
        lambda _: a34.R34ToolFinding("STATIC_SYNTAX", "FAIL", 1, digest()),
    )
    monkeypatch.setattr(
        runner, "_run", lambda *args, **kwargs: executed.append(args),
    )
    with pytest.raises(a34.R34AcceptanceRefused, match="STATIC_PREFLIGHT"):
        runner.collect_r34_offline_evidence(
            root=Path("/synthetic/isolated"), expected_head="a" * 40,
            run_stage_tests=True, operator_ack=True,
        )
    assert executed == []


def test_r34_posttest_source_digest_drift_is_denied(monkeypatch):
    monkeypatch.setattr(runner, "_project_python_preflight", lambda *_: None)
    visits = []
    monkeypatch.setattr(runner, "_head", lambda *_: None)
    def changed_syntax(_):
        visits.append("inspected")
        return a34.R34ToolFinding(
            "STATIC_SYNTAX", "PASS", 0,
            "0" * 64 if len(visits) == 1 else "1" * 64,
        )
    monkeypatch.setattr(runner, "_syntax", changed_syntax)
    monkeypatch.setattr(
        runner, "_run",
        lambda root, name, argv, timeout: a34.R34ToolFinding(
            name, "PASS", 0, digest(),
        ),
    )
    with pytest.raises(a34.R34AcceptanceRefused, match="SOURCE_CHANGED"):
        runner.collect_r34_offline_evidence(
            root=Path("/synthetic/isolated"), expected_head="a" * 40,
            run_stage_tests=True, operator_ack=True,
        )
    assert len(visits) == 2


def test_r34_pythonpath_is_fixed_to_disposable_checkout(monkeypatch, tmp_path):
    root = tmp_path / "new_test_checkout"
    root.mkdir()
    monkeypatch.setenv("PYTHONPATH", "/unsafe/custom/modules")
    monkeypatch.setenv("PYTHONHOME", "/unsafe/custom/python")
    env = runner._child_environment(root)
    assert env["PYTHONPATH"] == (
        str(root / "production_source") + ":" + str(root)
    )
    assert "PYTHONHOME" not in env
    assert "/unsafe" not in str(env)


def test_r34_empty_pythonpath_when_checkout_not_provided(monkeypatch):
    monkeypatch.setenv("PYTHONPATH", "/unsafe/custom/modules")
    env = runner._child_environment()
    assert "PYTHONPATH" not in env



def test_r34_untrusted_pytest_environment_cannot_override_fixed_commands(
    monkeypatch, tmp_path,
):
    for key in (
        "PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTEST_DEBUG",
        "PYTHONSTARTUP", "PYTHONUSERBASE", "PYTHONINSPECT",
        "PYTHONWARNINGS", "PYTHONBREAKPOINT",
    ):
        monkeypatch.setenv(key, "UNSAFE_INJECTION")
    env = runner._child_environment(tmp_path)
    for key in (
        "PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTEST_DEBUG",
        "PYTHONSTARTUP", "PYTHONUSERBASE", "PYTHONINSPECT",
        "PYTHONWARNINGS", "PYTHONBREAKPOINT",
    ):
        assert key not in env
    assert env["PYTHONNOUSERSITE"] == "1"
    assert env["PYTHONSAFEPATH"] == "1"


def test_r34_runner_refuses_unsupported_python_versions():
    runner._project_python_preflight(True, version=(3, 12))
    runner._project_python_preflight(False, version=(3, 13))
    with pytest.raises(a34.R34AcceptanceRefused, match="PYTHON_312_REQUIRED"):
        runner._project_python_preflight(True, version=(3, 13))
    with pytest.raises(a34.R34AcceptanceRefused, match="PYTHON_312_REQUIRED"):
        runner._project_python_preflight(True, version=(3, 11))



def test_r34_timeout_kills_own_process_group(monkeypatch, tmp_path):
    import subprocess

    launches = []
    killed = []

    class TimedOutProcess:
        pid = 432101

        def __init__(self, args, **kwargs):
            launches.append((args, kwargs))
            self.count = 0

        def wait(self, timeout=None):
            self.count += 1
            if self.count == 1:
                raise subprocess.TimeoutExpired("isolated-test", timeout)
            return -9

    monkeypatch.setattr(runner.subprocess, "Popen", TimedOutProcess)
    monkeypatch.setattr(
        runner.os, "killpg", lambda pid, sig: killed.append((pid, sig)),
    )
    finding = runner._run(
        tmp_path, "R28", ("python", "-m", "pytest", "-q"),
        2,
    )
    assert finding.status == "TIMEOUT"
    assert finding.returncode is None
    assert launches[0][1]["start_new_session"] is True
    assert launches[0][1]["stdin"] == subprocess.DEVNULL
    assert killed == [(432101, runner.signal.SIGKILL)]


def test_r34_no_implicit_subprocess_or_network_without_opt_in(monkeypatch):
    calls = []
    monkeypatch.setattr(runner, "_head", lambda *_: None)
    monkeypatch.setattr(
        runner, "_syntax",
        lambda _: a34.R34ToolFinding(
            "STATIC_SYNTAX", "PASS", 0, digest(),
        ),
    )
    monkeypatch.setattr(
        runner, "_git",
        lambda _, *args: (
            "a" * 40 if args == ("rev-parse", "HEAD") else ""
        ),
    )
    monkeypatch.setattr(
        runner.subprocess, "Popen",
        lambda *args, **kwargs: calls.append("EXECUTED"),
    )
    evidence = runner.collect_r34_offline_evidence(
        root=Path("/disposable/review"), expected_head="a" * 40,
        operator_ack=True,
    )
    assert evidence.local_test_runner_executed is False
    assert calls == []


def test_r34_current_stacked_python_inventory_is_complete_and_unique():
    # Frozen baseline for PRs #320 to #327; reconfirm via GitHub on updates.
    sources = a34._STATIC_SOURCES
    tests = tuple(a34._STAGE_UNIT_TARGETS.values()) + (
        "tests/unit/test_mmt_r34_offline_stack_acceptance_v1.py",
    )
    assert len(sources) == 16
    assert len(tests) == 8
    assert len(set((*sources, *tests))) == 24
    for expected in (
        "naseri_markets/brooks_independent_lifecycle_economics_mmt_r27_v1.py",
        "naseri_markets/offline_runtime_supervisor_v1.py",
        "scripts/mmt_r29_manual_future_shadow.py",
        "scripts/mmt_r29_manual_shadow_audit.py",
        "scripts/mmt_r32_offline_review_kit_v1.py",
        "scripts/mmt_r32_stopped_recovery_cli_v1.py",
        "scripts/mmt_r33_manual_live_denial_review_v1.py",
    ):
        assert expected in sources
