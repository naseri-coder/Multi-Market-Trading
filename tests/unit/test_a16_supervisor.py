"""A16 real independent fixture process, signed release and recovery security tests."""
from __future__ import annotations

import hashlib

import pytest

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from naseri_markets.a14_packages import MockPackageDeploymentManager
from naseri_markets.a15_releases import SignedReleaseAuthority, SignedMockDeploymentManager
from naseri_markets.a16_supervisor import OfflineFixtureSupervisor, ServiceRefused
from test_a14_packages import FakeProvisioner, ENGINE, INSTALL, bundle
from test_a15_releases import KEY1, public, sign

NOW = 42


@pytest.fixture
def env(tmp_path):
    guard = FakeProvisioner()
    private = Ed25519PrivateKey.generate()
    pub = public(private)
    authority = SignedReleaseAuthority(
        tmp_path / "trusted-witness.db", engine_id=ENGINE,
        installation_id=INSTALL, publisher_key_id=KEY1,
        publisher_public_key=pub, approved_key_sha256=hashlib.sha256(pub).hexdigest(),
    )
    mock = MockPackageDeploymentManager(
        tmp_path / "a14-releases", provisioner=guard,
        engine_id=ENGINE, installation_id=INSTALL,
    )
    signed = SignedMockDeploymentManager(mock, authority)
    raw, _ = bundle("1.0.0")
    installed = signed.install(raw, sign(private, raw, sequence=1),
                               expected_revision=0, admission=guard, now=NOW)
    assert installed.state == "STOPPED"
    supervisor = OfflineFixtureSupervisor(
        tmp_path / "a16-service", signed=signed,
        engine_id=ENGINE, installation_id=INSTALL,
    )
    yield supervisor, signed, guard, authority, mock, private, tmp_path
    supervisor.close()
    mock.close()
    authority.close()


def start(supervisor, guard):
    return supervisor.start(expected_revision=supervisor.status().revision,
                            admission=guard, now=NOW)


def stop(supervisor):
    return supervisor.stop(expected_revision=supervisor.status().revision)


def test_real_two_process_start_heartbeat_stop_and_no_private_code(env):
    supervisor, signed, guard, _, mock, _, _ = env
    assert supervisor.status().state == "STOPPED"
    up = start(supervisor, guard)
    assert up.state == "RUNNING"
    assert up.revision == 1
    assert up.owned_process_alive
    assert up.signed_and_admitted_now
    assert not up.real_private_engine_running
    assert not up.live_trading_permitted
    assert supervisor.status().signed_and_admitted_now is False
    assert mock.status().state == "STOPPED"  # A14 worker never started
    ok = supervisor.health(admission=guard, now=NOW)
    assert ok.state == "RUNNING"
    assert ok.signed_and_admitted_now
    assert stop(supervisor).state == "STOPPED"
    assert not supervisor.status().owned_process_alive
    assert supervisor.history() == ("START_FIXTURE", "STOP_FIXTURE")


def test_crash_no_auto_restart_requires_reconciliation(env):
    supervisor, signed, guard, _, _, _, _ = env
    running = start(supervisor, guard)
    crashed = supervisor.crash_fixture_for_test(expected_revision=running.revision)
    assert crashed.state == "RECOVERY_REQUIRED"
    assert not crashed.owned_process_alive
    with pytest.raises(ServiceRefused, match="EXPLICIT_RECOVERY"):
        start(supervisor, guard)
    assert supervisor.health(admission=guard, now=NOW).state == "QUARANTINED"
    with pytest.raises(ServiceRefused, match="STALE_REVISION"):
        supervisor.reconcile(expected_revision=running.revision)
    assert supervisor.reconcile(expected_revision=2).state == "STOPPED"
    assert start(supervisor, guard).state == "RUNNING"
    assert stop(supervisor).state == "STOPPED"
    assert supervisor.history() == (
        "START_FIXTURE", "FAIL_CLOSED_HEALTH", "MANUAL_RECONCILE",
        "START_FIXTURE", "STOP_FIXTURE",
    )


def test_new_manager_cannot_adopt_or_kill_other_worker(env):
    owner, signed, guard, _, _, _, tmp_path = env
    started = start(owner, guard)
    observer = OfflineFixtureSupervisor(
        tmp_path / "a16-service", signed=signed,
        engine_id=ENGINE, installation_id=INSTALL,
    )
    assert observer.status().state == "RECOVERY_REQUIRED"
    with pytest.raises(ServiceRefused, match="WORKER_OWNED"):
        observer.reconcile(expected_revision=started.revision)  # no adoption
    with pytest.raises(ServiceRefused, match="EXPLICIT_RECOVERY"):
        observer.start(expected_revision=started.revision, admission=guard, now=NOW)
    observer.close()
    assert owner.health(admission=guard, now=NOW).owned_process_alive
    stop(owner)


def test_missing_admission_revocation_quarantines_owned_worker(env):
    supervisor, signed, guard, _, _, _, _ = env
    start(supervisor, guard)
    guard.enabled = False
    state = supervisor.health(admission=guard, now=NOW)
    assert state.state == "QUARANTINED"
    assert not state.owned_process_alive
    with pytest.raises(ServiceRefused, match="EXPLICIT_RECOVERY"):
        start(supervisor, guard)
    assert supervisor.reconcile(expected_revision=state.revision).state == "STOPPED"
    with pytest.raises(ValueError, match="A13_FRESH_ADMISSION"):
        start(supervisor, guard)
    guard.enabled = True
    start(supervisor, guard)
    stop(supervisor)


def test_publisher_revocation_fails_closed_even_midrun(env):
    supervisor, signed, guard, auth, _, _, _ = env
    start(supervisor, guard)
    auth.revoke_publisher(expected_generation=1)
    result = supervisor.health(admission=guard, now=NOW)
    assert result.state == "QUARANTINED"
    assert not result.owned_process_alive
    supervisor.reconcile(expected_revision=result.revision)
    with pytest.raises(ValueError, match="PUBLISHER_REVOKED"):
        start(supervisor, guard)


def test_operator_stop_after_grant_revocation(env):
    supervisor, signed, guard, auth, _, _, _ = env
    start(supervisor, guard)
    guard.enabled = False
    auth.revoke_publisher(expected_generation=1)
    assert stop(supervisor).state == "STOPPED"


def test_changed_underlying_release_quarantines_not_adopts(env):
    supervisor, signed, guard, authority, mock, issuer, _ = env
    start(supervisor, guard)
    newer, _ = bundle("1.0.1")
    staged = signed.install(newer, sign(issuer, newer, sequence=2, release="1.0.1"),
                            expected_revision=1, admission=guard, now=NOW)
    assert staged.active != supervisor.status().artifact_sha256
    report = supervisor.health(admission=guard, now=NOW)
    assert report.state == "QUARANTINED"
    supervisor.reconcile(expected_revision=report.revision)
    restarted = start(supervisor, guard)
    assert restarted.artifact_sha256 == staged.active
    stop(supervisor)


def test_archive_bytes_tamper_causes_shutdown(env):
    supervisor, signed, guard, _, mock, _, _ = env
    start(supervisor, guard)
    archive = mock._releases / mock.status().active / "package.zip"
    archive.write_bytes(archive.read_bytes() + b"forged")
    failed = supervisor.health(admission=guard, now=NOW)
    assert failed.state == "QUARANTINED"
    assert not failed.owned_process_alive


def test_worker_parent_pipe_eof_is_crash_not_liveness(env):
    supervisor, signed, guard, _, _, _, _ = env
    start(supervisor, guard)
    supervisor._child.stdin.close()  # simulate loss of command pipe
    supervisor._child.wait(timeout=2)
    assert supervisor.status().state == "RECOVERY_REQUIRED"
    assert supervisor.health(admission=guard, now=NOW).state == "QUARANTINED"
    supervisor.reconcile(expected_revision=2)
    assert start(supervisor, guard).state == "RUNNING"
    stop(supervisor)


def test_stale_revision_and_corrupt_state_fail_closed(env):
    supervisor, signed, guard, _, _, _, _ = env
    start(supervisor, guard)
    with pytest.raises(ServiceRefused, match="STALE_REVISION"):
        supervisor.stop(expected_revision=0)
    assert supervisor.health(admission=guard, now=NOW).state == "RUNNING"
    stop(supervisor)
    supervisor._state_path.write_bytes(b'{"schema":1,"schema":1}')
    with pytest.raises(ValueError, match="CORRUPT_STATE|DUPLICATE"):
        supervisor.status()


def test_no_external_paths_symlinks_or_wrong_engine(env, tmp_path):
    supervisor, signed, guard, _, mock, _, _ = env
    with pytest.raises(ServiceRefused, match="DISPOSABLE"):
        OfflineFixtureSupervisor("/opt/a16-service", signed=signed,
                                 engine_id=ENGINE, installation_id=INSTALL)
    link = tmp_path / "symlink"
    link.symlink_to(supervisor._root, target_is_directory=True)
    with pytest.raises(ServiceRefused, match="DISPOSABLE"):
        OfflineFixtureSupervisor(link, signed=signed,
                                 engine_id=ENGINE, installation_id=INSTALL)
    with pytest.raises(ServiceRefused, match="IDENTITY_MISMATCH"):
        OfflineFixtureSupervisor(tmp_path / "foreign",
                                 signed=signed, engine_id="foreign_engine",
                                 installation_id=INSTALL)
    with pytest.raises(ServiceRefused, match="DISPOSABLE"):
        OfflineFixtureSupervisor(mock._root / "embedded", signed=signed,
                                 engine_id=ENGINE, installation_id=INSTALL)


def test_unresponsive_worker_start_times_out_without_claiming_running(
    env, monkeypatch,
):
    import naseri_markets.a16_supervisor as a16
    supervisor, signed, guard, _, _, _, _ = env
    monkeypatch.setattr(a16, "_FIXED_WORKER", "import time; time.sleep(10)")
    with pytest.raises(ServiceRefused, match="HEALTH_TIMEOUT"):
        start(supervisor, guard)
    assert supervisor.status().state == "STOPPED"
    assert not supervisor.status().owned_process_alive


def test_expired_lease_heartbeat_halts_fixture(env):
    supervisor, signed, guard, _, _, _, _ = env
    start(supervisor, guard)
    # The signed envelope was valid at NOW=42, not at a far-future clock.
    failed = supervisor.health(admission=guard, now=100000)
    assert failed.state == "QUARANTINED"
    assert not failed.owned_process_alive


def test_full_real_a12_a13_a15_and_a16_process_revoke(tmp_path):
    from test_a13_provisioning import (
        fixture as a13_fixture, plan, admission, digest, NOW as real_now,
        ENGINE as real_engine, INSTALL as real_install,
    )

    plugins, trust, license_issuer, _, policy, provisioner = a13_fixture(tmp_path)
    plan_bytes = plan(policy)
    ready = provisioner.prepare(plan_bytes, approved_sha256=digest(plan_bytes))
    grant = admission(trust, license_issuer, policy)
    provisioner.verify(real_engine, expected_revision=ready.revision,
                       admission=grant, now=real_now)
    publisher = Ed25519PrivateKey.generate()
    pub = public(publisher)
    authority = SignedReleaseAuthority(
        tmp_path / "witness.db", engine_id=real_engine,
        installation_id=real_install, publisher_key_id=KEY1,
        publisher_public_key=pub, approved_key_sha256=hashlib.sha256(pub).hexdigest(),
    )
    mock = MockPackageDeploymentManager(
        tmp_path / "archives", provisioner=provisioner,
        engine_id=real_engine, installation_id=real_install,
    )
    signed = SignedMockDeploymentManager(mock, authority)
    archive, _ = bundle("1.0.0", engine=real_engine,
                        installation=real_install,
                        digest=policy["manifest_sha256"], generation=policy["generation"])
    proof = sign(publisher, archive, sequence=1,
                 installation_id=real_install,
                 manifest_sha256=policy["manifest_sha256"],
                 trust_generation=policy["generation"],
                 issued_at=real_now - 10, expires_at=real_now + 300)
    signed.install(archive, proof, expected_revision=0,
                   admission=grant, now=real_now)
    service = OfflineFixtureSupervisor(
        tmp_path / "a16-worker", signed=signed,
        engine_id=real_engine, installation_id=real_install,
    )
    running = service.start(expected_revision=0, admission=grant, now=real_now)
    assert running.signed_and_admitted_now
    assert service.health(admission=grant, now=real_now).state == "RUNNING"
    trust.revoke_serial("a" * 32)
    assert service.health(admission=grant, now=real_now).state == "QUARANTINED"
    assert service.reconcile(expected_revision=2).state == "STOPPED"
    service.close()
    mock.close()
    authority.close()
    provisioner.close()
    plugins.close()
    trust.close()
