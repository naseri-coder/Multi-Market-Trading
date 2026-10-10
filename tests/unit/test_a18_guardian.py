"""A18 real standalone Guardian, Linux syscall confinement and crash fencing."""
from __future__ import annotations

import hashlib
import json
import os
import signal
import socket
import time

import pytest

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from naseri_markets.a14_packages import MockPackageDeploymentManager
from naseri_markets.a15_releases import SignedReleaseAuthority, SignedMockDeploymentManager
from naseri_markets.a18_controller import GuardianRefused, SignedGuardianController
from test_a14_packages import FakeProvisioner, ENGINE, INSTALL, bundle
from test_a15_releases import KEY1, public, sign


def until(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.04)
    pytest.fail("A18_EXPECTED_GUARDIAN_TRANSITION_NOT_SEEN")


@pytest.fixture
def fixture(tmp_path):
    guard = FakeProvisioner()
    signer = Ed25519PrivateKey.generate()
    pub = public(signer)
    authority = SignedReleaseAuthority(
        tmp_path / "signed-publisher.db", engine_id=ENGINE,
        installation_id=INSTALL, publisher_key_id=KEY1,
        publisher_public_key=pub,
        approved_key_sha256=hashlib.sha256(pub).hexdigest(),
    )
    mock = MockPackageDeploymentManager(
        tmp_path / "a14", provisioner=guard,
        engine_id=ENGINE, installation_id=INSTALL,
    )
    signed = SignedMockDeploymentManager(mock, authority)
    raw, _ = bundle("1.0.0")
    signed.install(raw, sign(signer, raw, sequence=1),
                   expected_revision=0, admission=guard, now=42)
    ctrl = SignedGuardianController(
        tmp_path / "a18", signed=signed,
        engine_id=ENGINE, installation_id=INSTALL,
        lease_seconds=0.65, heartbeat_seconds=0.08,
    )
    yield ctrl, guard, authority, mock, signer, tmp_path
    ctrl.close()
    mock.close()
    authority.close()


def test_independent_process_kernel_no_new_privs_seccomp_network_and_rlimits(fixture):
    import resource
    ctrl, guard, _, _, _, _ = fixture
    launched = ctrl.launch(admission=guard, now=42)
    assert launched.guardian_alive
    assert launched.worker_alive
    assert launched.sandbox_verified
    assert launched.current_proof_checked
    assert not launched.real_private_engine_running
    assert not launched.live_trading_permitted
    persisted = ctrl._persisted()
    assert persisted["state"] == "RUNNING"
    assert persisted["worker_pid"] != persisted["guardian_pid"]
    assert persisted["guardian_pid"] == ctrl._child.pid
    # Both are real Linux processes. The worker startup proves an actual
    # socket() syscall is denied with EPERM by the installed seccomp filter.
    pid = persisted["worker_pid"]
    with open(f"/proc/{pid}/status") as source:
        status = source.read()
    assert "NoNewPrivs:\t1" in status
    assert "Seccomp:\t2" in status
    assert resource.prlimit(pid, resource.RLIMIT_AS) == (256*1024*1024, 256*1024*1024)
    assert resource.prlimit(pid, resource.RLIMIT_NOFILE) == (48, 48)
    assert resource.prlimit(pid, resource.RLIMIT_CPU) == (5, 5)
    assert resource.prlimit(pid, resource.RLIMIT_CORE) == (0, 0)
    renewed = ctrl.renew(admission=guard, now=42)
    assert renewed.current_proof_checked
    assert renewed.worker_alive
    stopped = ctrl.stop()
    assert stopped.state == "STOPPED"
    assert not stopped.worker_alive


def test_expiring_lease_quarantines_on_guardian_own_clock_without_renew(fixture):
    ctrl, guard, _, _, _, _ = fixture
    ctrl.launch(admission=guard, now=42)
    expired = until(lambda: (s if (s := ctrl.status()).state == "QUARANTINED" else None))
    assert not expired.worker_alive
    assert not expired.current_proof_checked
    with pytest.raises(GuardianRefused, match="NOT_RUNNING"):
        ctrl.renew(admission=guard, now=42)
    with pytest.raises(GuardianRefused, match="ALREADY_OWNED"):
        ctrl.launch(admission=guard, now=42)


def test_revoked_grant_immediately_stops_on_failed_renew(fixture):
    ctrl, guard, _, _, _, _ = fixture
    ctrl.launch(admission=guard, now=42)
    guard.enabled = False
    with pytest.raises(ValueError, match="A13_FRESH_ADMISSION"):
        ctrl.renew(admission=guard, now=42)
    assert ctrl.status().state == "STOPPED"
    assert not ctrl.status().worker_alive


def test_signed_publisher_revocation_immediately_stops_on_renew(fixture):
    ctrl, guard, authority, _, _, _ = fixture
    ctrl.launch(admission=guard, now=42)
    authority.revoke_publisher(expected_generation=1)
    with pytest.raises(ValueError, match="PUBLISHER_REVOKED"):
        ctrl.renew(admission=guard, now=42)
    assert ctrl.status().state == "STOPPED"


def test_tampered_package_forces_stop_on_renew(fixture):
    ctrl, guard, _, mock, _, _ = fixture
    ctrl.launch(admission=guard, now=42)
    archive = mock._releases / mock.status().active / "package.zip"
    archive.write_bytes(archive.read_bytes() + b"forged")
    with pytest.raises(ValueError):
        ctrl.renew(admission=guard, now=42)
    assert not ctrl.status().worker_alive


def test_worker_crash_detected_by_separate_guardian_no_manager_heartbeat(fixture):
    ctrl, guard, _, _, _, _ = fixture
    ctrl.launch(admission=guard, now=42)
    ctrl.crash_worker_for_test()
    failed = until(lambda: (s if (s := ctrl.status()).state == "QUARANTINED" else None))
    assert not failed.worker_alive
    with pytest.raises(GuardianRefused, match="NOT_RUNNING"):
        ctrl.renew(admission=guard, now=42)


def test_wrong_token_does_not_control_worker(fixture):
    ctrl, guard, _, _, _, tmp_path = fixture
    ctrl.launch(admission=guard, now=42)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.connect(str(tmp_path / "a18" / "guardian.sock"))
        connection.sendall((json.dumps({"token": "0" * 64, "cmd": "STOP"}) + "\n").encode())
        reply = connection.recv(512).decode()
    assert "A18_CONTROL_AUTH_FAILED" in reply
    assert ctrl.renew(admission=guard, now=42).worker_alive
    ctrl.stop()


def test_second_controller_cannot_adopt_live_or_stale_guardian(fixture):
    ctrl, guard, _, mock, _, tmp_path = fixture
    ctrl.launch(admission=guard, now=42)
    another = SignedGuardianController(
        tmp_path / "a18", signed=ctrl._signed,
        engine_id=ENGINE, installation_id=INSTALL,
    )
    with pytest.raises(GuardianRefused, match="EXPLICIT_RECONCILIATION"):
        another.launch(admission=guard, now=42)
    with pytest.raises(GuardianRefused, match="GUARDIAN_STILL_OWNS"):
        another.reconcile_after_owner_exit(admission=guard, now=42)
    ctrl.stop()


def test_unverified_signature_and_external_path_fail_closed(fixture):
    ctrl, guard, authority, mock, _, tmp_path = fixture
    with pytest.raises(GuardianRefused, match="TEMP_ISOLATED"):
        SignedGuardianController(
            "/var/run/not-allowed", signed=ctrl._signed,
            engine_id=ENGINE, installation_id=INSTALL,
        )
    symlink = tmp_path / "symlink"
    symlink.symlink_to(tmp_path / "a18", target_is_directory=True)
    with pytest.raises(GuardianRefused, match="TEMP_ISOLATED"):
        SignedGuardianController(symlink, signed=ctrl._signed,
                                 engine_id=ENGINE, installation_id=INSTALL)
    guard.enabled = False
    with pytest.raises(ValueError, match="A13_FRESH_ADMISSION"):
        ctrl.launch(admission=guard, now=42)
    assert ctrl._child is None


def test_foreign_release_active_change_causes_fail_closed_stop(fixture):
    ctrl, guard, _, mock, issuer, _ = fixture
    ctrl.launch(admission=guard, now=42)
    newer, _ = bundle("1.0.1")
    ctrl._signed.install(
        newer, sign(issuer, newer, sequence=2, release="1.0.1"),
        expected_revision=mock.status().revision, admission=guard, now=42,
    )
    with pytest.raises(GuardianRefused, match="RELEASE_CHANGED_WITHIN_LEASE"):
        ctrl.renew(admission=guard, now=42)
    assert ctrl.status().state == "STOPPED"


def test_manager_sigkill_guardian_persists_then_expiry_then_manual_reconcile(fixture):
    """A real manager process dies with SIGKILL; Guardian is a separate session."""
    ctrl, guard, authority, mock, signer, tmp_path = fixture
    readfd, writefd = os.pipe()
    owner_pid = os.fork()
    if owner_pid == 0:
        try:
            os.close(readfd)
            # Connections opened after fork in the manager, never reusing
            # inherited sqlite connection objects for trusted operations.
            pub = public(signer)
            owned_auth = SignedReleaseAuthority(
                tmp_path / "signed-publisher.db", engine_id=ENGINE,
                installation_id=INSTALL, publisher_key_id=KEY1,
                publisher_public_key=pub,
                approved_key_sha256=hashlib.sha256(pub).hexdigest(),
            )
            owned_mock = MockPackageDeploymentManager(
                tmp_path / "a14", provisioner=FakeProvisioner(),
                engine_id=ENGINE, installation_id=INSTALL,
            )
            owned = SignedGuardianController(
                tmp_path / "a18",
                signed=SignedMockDeploymentManager(owned_mock, owned_auth),
                engine_id=ENGINE, installation_id=INSTALL,
                lease_seconds=0.65, heartbeat_seconds=0.08,
            )
            started = owned.launch(admission=owned_mock._provisioner, now=42)
            os.write(writefd, b"started" if started.worker_alive else b"failed")
            # Caller kills this manager process, deliberately skipping close.
            time.sleep(30)
        except BaseException:
            os.write(writefd, b"failed")
        finally:
            os._exit(0)
    os.close(writefd)
    try:
        report = os.read(readfd, 16)
        assert report == b"started"
        guardian_record = json.loads((tmp_path / "a18" / "guardian.json").read_text())
        assert guardian_record["guardian_pid"] != owner_pid
        assert guardian_record["worker_pid"] != owner_pid
        os.kill(owner_pid, signal.SIGKILL)
        os.waitpid(owner_pid, 0)
        # Guardian is independent and must stop its own static child
        # after the lease, without any in-process renewer.
        expired = until(lambda: (
            s if (s := json.loads((tmp_path / "a18" / "guardian.json").read_text()))["state"]
            == "QUARANTINED" else None), timeout=3.0)
        assert expired["worker_pid"] is None  # Guardian owns cleanup
        assert expired["sandbox_verified"] is False
        with pytest.raises(GuardianRefused, match="GUARDIAN_STILL_OWNS"):
            ctrl.reconcile_after_owner_exit(admission=guard, now=42)
        # Guardian will release ownership after its bounded idle grace.
        until(lambda: not (tmp_path / "a18" / "guardian.sock").exists(), timeout=8.5)
        assert ctrl.reconcile_after_owner_exit(admission=guard, now=42) == "RECOVERED_STOPPED"
        assert ctrl._child is None  # no PID adoption and NO auto restart
        next_state = ctrl.launch(admission=guard, now=42)
        assert next_state.sandbox_verified
        ctrl.stop()
    finally:
        os.close(readfd)
        try:
            os.kill(owner_pid, signal.SIGKILL)
            os.waitpid(owner_pid, 0)
        except (ProcessLookupError, ChildProcessError):
            pass


def test_full_real_a12_a13_a15_guardian_integration(tmp_path):
    from test_a13_provisioning import (
        fixture as a13_fixture, plan, admission, digest,
        NOW, ENGINE as engine, INSTALL as installation,
    )
    plugins, trust, issuer, _, policy, provisioner = a13_fixture(tmp_path)
    planned = plan(policy)
    prepared = provisioner.prepare(planned, approved_sha256=digest(planned))
    grant = admission(trust, issuer, policy)
    provisioner.verify(engine, expected_revision=prepared.revision,
                       admission=grant, now=NOW)
    publisher = Ed25519PrivateKey.generate()
    pub = public(publisher)
    auth = SignedReleaseAuthority(
        tmp_path / "a15.db", engine_id=engine,
        installation_id=installation, publisher_key_id=KEY1,
        publisher_public_key=pub,
        approved_key_sha256=hashlib.sha256(pub).hexdigest(),
    )
    mock = MockPackageDeploymentManager(
        tmp_path / "a14", provisioner=provisioner,
        engine_id=engine, installation_id=installation)
    signed = SignedMockDeploymentManager(mock, auth)
    archive, _ = bundle("1.0.0", engine=engine,
                        installation=installation,
                        digest=policy["manifest_sha256"], generation=1)
    proof = sign(publisher, archive, sequence=1,
                 installation_id=installation,
                 manifest_sha256=policy["manifest_sha256"],
                 issued_at=NOW - 10, expires_at=NOW + 300)
    signed.install(archive, proof, expected_revision=0,
                   admission=grant, now=NOW)
    ctrl = SignedGuardianController(
        tmp_path / "guardian", signed=signed,
        engine_id=engine, installation_id=installation,
        lease_seconds=0.8,
    )
    try:
        assert ctrl.launch(admission=grant, now=NOW).sandbox_verified
        assert ctrl.renew(admission=grant, now=NOW).worker_alive
        trust.revoke_serial("a" * 32)
        with pytest.raises(ValueError, match="FRESH_ADMISSION"):
            ctrl.renew(admission=grant, now=NOW)
        assert ctrl.status().state == "STOPPED"
    finally:
        ctrl.close()
        mock.close()
        auth.close()
        provisioner.close()
        plugins.close()
        trust.close()
