"""A17 non-production continuous process watchdog, SQLite ownership and RLIMIT."""
from __future__ import annotations

import hashlib
import threading
import time

import pytest

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from naseri_markets.a14_packages import MockPackageDeploymentManager
from naseri_markets.a15_releases import SignedReleaseAuthority, SignedMockDeploymentManager
from naseri_markets.a16_supervisor import (
    FixtureProcessLimits, OfflineFixtureSupervisor,
)
from naseri_markets.a17_watchdog import (
    ContinuousFixtureWatchdog, FixtureSession, WatchdogRefused,
)
from test_a14_packages import FakeProvisioner, ENGINE, INSTALL, bundle
from test_a15_releases import KEY1, public, sign


def until(predicate, seconds=3.5):
    limit = time.monotonic() + seconds
    while time.monotonic() < limit:
        x = predicate()
        if x:
            return x
        time.sleep(0.035)
    pytest.fail("A17_WATCHDOG_DID_NOT_REACT_WITHIN_DEADLINE")


@pytest.fixture
def ctx(tmp_path):
    guard = FakeProvisioner()
    publisher = Ed25519PrivateKey.generate()
    pub = public(publisher)
    approved = hashlib.sha256(pub).hexdigest()
    # Operator preinstalls a *signed*, synthetic release. The ongoing
    # watchdog will reopen all SQLite connections on its own thread.
    authority = SignedReleaseAuthority(
        tmp_path / "publisher-witness.db", engine_id=ENGINE,
        installation_id=INSTALL, publisher_key_id=KEY1,
        publisher_public_key=pub, approved_key_sha256=approved,
    )
    mock = MockPackageDeploymentManager(
        tmp_path / "a14", provisioner=guard, engine_id=ENGINE,
        installation_id=INSTALL,
    )
    signed = SignedMockDeploymentManager(mock, authority)
    artifact, _ = bundle("1.0.0")
    signed.install(artifact, sign(publisher, artifact, sequence=1),
                   expected_revision=0, admission=guard, now=42)

    made_on = []
    def factory():
        made_on.append(threading.get_ident())
        auth = SignedReleaseAuthority(
            tmp_path / "publisher-witness.db", engine_id=ENGINE,
            installation_id=INSTALL, publisher_key_id=KEY1,
            publisher_public_key=pub, approved_key_sha256=approved,
        )
        worker_mock = MockPackageDeploymentManager(
            tmp_path / "a14", provisioner=guard, engine_id=ENGINE,
            installation_id=INSTALL,
        )
        supervisor = OfflineFixtureSupervisor(
            tmp_path / "a16", signed=SignedMockDeploymentManager(worker_mock, auth),
            engine_id=ENGINE, installation_id=INSTALL,
            process_limits=FixtureProcessLimits(),
        )
        return FixtureSession(supervisor, guard, (worker_mock.close, auth.close))

    clock = [42]
    watcher = ContinuousFixtureWatchdog(
        tmp_path / "watchdog", session_factory=factory,
        trusted_clock=lambda: clock[0], interval_seconds=0.06,
    )
    yield watcher, guard, clock, auth if False else authority, mock, made_on, tmp_path
    watcher.close()
    mock.close()
    authority.close()


def test_watchdog_real_periodic_health_and_resource_limits(ctx):
    watcher, guard, clock, _, _, made_on, _ = ctx
    assert made_on == [watcher._thread.ident]
    assert watcher._thread.ident != threading.get_ident()
    started = watcher.start()
    assert started.monitoring and started.last_probe_admitted
    assert started.owned_child_alive
    assert started.service_state == "RUNNING"
    until(lambda: watcher.status().completed_health_probes >= 3)
    actual = watcher.observed_limits()
    cap = FixtureProcessLimits()
    assert actual["memory_bytes"] == (cap.memory_bytes, cap.memory_bytes)
    assert actual["cpu_seconds"] == (cap.cpu_seconds, cap.cpu_seconds)
    assert actual["open_files"] == (cap.open_files, cap.open_files)
    assert actual["core_bytes"] == (0, 0)
    assert watcher.stop().service_state == "STOPPED"
    assert not watcher.status().monitoring
    assert not watcher.status().owned_child_alive


def test_revoke_a13_during_running_quarantines_without_manual_probe(ctx):
    watcher, guard, _, _, _, _, _ = ctx
    watcher.start()
    guard.enabled = False
    state = until(lambda: (s if (s := watcher.status()).service_state
                           == "QUARANTINED" else None))
    assert not state.monitoring and not state.owned_child_alive
    assert not state.last_probe_admitted
    assert state.fault == "A17_FAIL_CLOSED_HEALTH"
    assert watcher.reconcile().service_state == "STOPPED"
    with pytest.raises(ValueError, match="A14_A13_FRESH_ADMISSION"):
        watcher.start()
    guard.enabled = True
    assert watcher.start().monitoring
    assert watcher.stop().service_state == "STOPPED"


def test_a15_publisher_revocation_quarantines_next_background_tick(ctx):
    watcher, guard, _, authority, _, _, _ = ctx
    watcher.start()
    authority.revoke_publisher(expected_generation=1)
    status = until(lambda: (s if (s := watcher.status()).service_state
                            == "QUARANTINED" else None))
    assert not status.owned_child_alive
    watcher.reconcile()
    with pytest.raises(ValueError, match="PUBLISHER_REVOKED"):
        watcher.start()


def test_expired_lease_quarantines_on_next_tick(ctx):
    watcher, guard, clock, _, _, _, _ = ctx
    watcher.start()
    clock[0] = 100000
    state = until(lambda: (s if (s := watcher.status()).service_state
                           == "QUARANTINED" else None))
    assert not state.owned_child_alive
    watcher.reconcile()
    with pytest.raises(ValueError, match="EXPIRED"):
        watcher.start()


def test_crash_injection_requires_explicit_operator_reconcile(ctx):
    watcher, _, _, _, _, _, _ = ctx
    started = watcher.start()
    watchdog_before = started.completed_health_probes
    watcher.crash_fixture_for_test()
    failed = until(lambda: (s if (s := watcher.status()).service_state
                            == "QUARANTINED" else None))
    assert failed.completed_health_probes > watchdog_before
    assert not failed.monitoring
    with pytest.raises(ValueError, match="EXPLICIT_RECOVERY"):
        watcher.start()
    assert watcher.reconcile().service_state == "STOPPED"
    assert watcher.start().monitoring
    watcher.stop()


def test_no_auto_restart_after_crash_and_quarantine(ctx):
    watcher, _, _, _, _, _, _ = ctx
    watcher.start()
    watcher.crash_fixture_for_test()
    failed = until(lambda: (s if (s := watcher.status()).service_state
                            == "QUARANTINED" else None))
    old_rev = failed.service_revision
    old_probes = failed.completed_health_probes
    time.sleep(0.2)
    next_state = watcher.status()
    assert next_state.service_revision == old_rev
    assert next_state.completed_health_probes == old_probes
    assert not next_state.owned_child_alive


def test_two_owner_watchdogs_cannot_control_same_root(ctx):
    watcher, guard, clock, _, _, _, tmp_path = ctx
    with pytest.raises(WatchdogRefused, match="OWNER_ALREADY_ACTIVE"):
        ContinuousFixtureWatchdog(
            tmp_path / "watchdog", session_factory=lambda: None,
            trusted_clock=lambda: clock[0],
        )
    assert watcher.start().monitoring
    watcher.stop()


def test_tampered_archive_quarantines_without_restart(ctx):
    watcher, guard, _, _, mock, _, _ = ctx
    watcher.start()
    target = mock._releases / mock.status().active / "package.zip"
    target.write_bytes(target.read_bytes() + b"A17_TAMPER")
    failed = until(lambda: (s if (s := watcher.status()).service_state
                            == "QUARANTINED" else None))
    assert not failed.owned_child_alive


def test_stop_remains_available_after_grant_revocation(ctx):
    watcher, guard, _, authority, _, _, _ = ctx
    watcher.start()
    guard.enabled = False
    authority.revoke_publisher(expected_generation=1)
    # Command queued before/after first background heartbeat is always
    # safe; STOP must not require a fresh valid grant.
    stopped = watcher.stop()
    assert not stopped.owned_child_alive
    assert stopped.service_state in ("STOPPED", "QUARANTINED")


def test_worker_session_factory_refusal_no_unbounded_worker(tmp_path):
    with pytest.raises(WatchdogRefused, match="SESSION_CREATION_FAILED"):
        ContinuousFixtureWatchdog(
            tmp_path / "broken-watchdog", session_factory=lambda: None,
            trusted_clock=lambda: 42,
        )


@pytest.mark.parametrize("kwargs", [
    {"memory_bytes": 8 * 1024 * 1024},
    {"cpu_seconds": 0},
    {"open_files": 999999},
    {"open_files": True},
])
def test_resource_limits_fail_closed_on_invalid_configuration(kwargs):
    with pytest.raises(ValueError, match="LIMITS_OUT_OF_BOUNDS"):
        FixtureProcessLimits(**kwargs)


def test_thread_exception_in_trusted_clock_kills_owned_worker(ctx):
    watcher, guard, clock, _, _, _, _ = ctx
    watcher.start()
    # Emulate a malformed clock in the next asynchronous monitor tick.
    watcher._clock = lambda: (_ for _ in ()).throw(RuntimeError("clock source lost"))
    failed = until(lambda: (s if (s := watcher.status()).service_state
                            == "QUARANTINED" else None))
    assert failed.fault == "A17_MONITOR_EXCEPTION"
    assert not failed.owned_child_alive


def test_full_real_a12_a13_a15_a16_a17_thread_owned_grant_revocation(tmp_path):
    """REAL signed A12 issuer + separately signed A15 publisher across threads."""
    from naseri_markets.a12_trust import OfflineAdmission, TrustStore
    from naseri_markets.a13_provisioning import OfflineProvisioner
    from naseri_markets.plugin_manager import PluginManager
    from test_a13_provisioning import (
        fixture as a13_fixture, plan, admission, digest,
        NOW, ENGINE as engine, INSTALL as installation,
    )

    plugins, trust, issuer, _, policy, provisioner = a13_fixture(tmp_path)
    plan_bytes = plan(policy)
    prepared = provisioner.prepare(
        plan_bytes, approved_sha256=digest(plan_bytes))
    grant = admission(trust, issuer, policy)
    provisioner.verify(engine, expected_revision=prepared.revision,
                       admission=grant, now=NOW)
    pubkey = Ed25519PrivateKey.generate()
    public_bytes = public(pubkey)
    public_pin = hashlib.sha256(public_bytes).hexdigest()
    auth = SignedReleaseAuthority(
        tmp_path / "a15.db", engine_id=engine, installation_id=installation,
        publisher_key_id=KEY1, publisher_public_key=public_bytes,
        approved_key_sha256=public_pin,
    )
    staged_mock = MockPackageDeploymentManager(
        tmp_path / "stage", provisioner=provisioner,
        engine_id=engine, installation_id=installation,
    )
    signed = SignedMockDeploymentManager(staged_mock, auth)
    raw, _ = bundle("1.0.0", engine=engine, installation=installation,
                    digest=policy["manifest_sha256"], generation=1)
    proof = sign(pubkey, raw, sequence=1, installation_id=installation,
                 manifest_sha256=policy["manifest_sha256"],
                 issued_at=NOW-10, expires_at=NOW+300)
    signed.install(raw, proof, expected_revision=0, admission=grant, now=NOW)
    def factory():
        p = PluginManager(tmp_path / "plugin-settings.db")
        t = TrustStore(tmp_path / "owner-trust.db")
        v = OfflineProvisioner(tmp_path / "provision.db", plugins=p,
                               trust=t, installation_id=installation)
        a = OfflineAdmission(t, engine_id=engine, installation_id=installation,
                             signed_grant=grant._grant, ca_pem=grant._ca,
                             owner_cert_der=grant._leaf)
        release = SignedReleaseAuthority(
            tmp_path / "a15.db", engine_id=engine, installation_id=installation,
            publisher_key_id=KEY1, publisher_public_key=public_bytes,
            approved_key_sha256=public_pin,
        )
        mocked = MockPackageDeploymentManager(
            tmp_path / "stage", provisioner=v,
            engine_id=engine, installation_id=installation)
        supervisor = OfflineFixtureSupervisor(
            tmp_path / "a16", signed=SignedMockDeploymentManager(mocked, release),
            engine_id=engine, installation_id=installation,
            process_limits=FixtureProcessLimits(),
        )
        return FixtureSession(supervisor, a,
                              (mocked.close, release.close, v.close, t.close, p.close))
    watcher = ContinuousFixtureWatchdog(
        tmp_path / "a17", session_factory=factory,
        trusted_clock=lambda: NOW, interval_seconds=0.07,
    )
    try:
        assert watcher.start().last_probe_admitted
        until(lambda: watcher.status().completed_health_probes >= 2)
        trust.revoke_serial("a" * 32)
        status = until(lambda: (s if (s := watcher.status()).service_state
                                == "QUARANTINED" else None))
        assert not status.owned_child_alive and not status.monitoring
        assert watcher.reconcile().service_state == "STOPPED"
        with pytest.raises(ValueError, match="FRESH_ADMISSION"):
            watcher.start()
    finally:
        watcher.close()
        staged_mock.close()
        auth.close()
        provisioner.close()
        plugins.close()
        trust.close()
