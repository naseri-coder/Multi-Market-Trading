"""A5 persistent one-time A4 evidence review. No Docker or code execution."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from naseri_markets.durable_runtime_a3 import DurableRuntimeRefused
from naseri_markets.multilang_runtime_a1 import RuntimeKind, RuntimeProfile
from naseri_markets.runtime_a4_security_evidence import (
    RuntimeEvidenceRefused,
    policy_digest,
)
from naseri_markets.runtime_a5_nonce_custody import (
    RuntimeChallengeLedger,
    RuntimeChallengeRefused,
)
from naseri_markets.secure_plugin_runtime_v1 import SecurePluginPolicy

KEY = b"ci-only-no-real-custody-key-this-key-is-not-production"
ISSUER = "auditor.test-v1"
HOST = "sandbox.test-v1"
WORKER = "b" * 64
NOW = datetime(2026, 10, 14, 12, tzinfo=UTC)
OPERATORS = frozenset({101})


def _profile(monkeypatch, kind=RuntimeKind.PYTHON):
    """Build the synthetic rootless profile for a fixture Docker endpoint.

    The synthetic endpoint pretends to belong to uid 1001, so the policy object
    is validated while a fake effective uid is installed.  The patch is scoped
    with ``monkeypatch.context()`` - the same convention as
    ``test_durable_isolated_core_gate_stage22_v1.host`` - because the ledger
    files created by these tests must keep satisfying the *real* owner check in
    ``naseri_markets.durable_runtime_a3._approved_dir``.  Leaving the fake uid
    installed made the whole module pass only on hosts whose user id happens to
    be 1001 (the GitHub-hosted runner) and fail everywhere else.
    """
    with monkeypatch.context() as local:
        local.setattr(os, "geteuid", lambda: 1001)
        policy = SecurePluginPolicy(
            enabled=True,
            image="registry.invalid/fixture@sha256:" + "a" * 64,
            docker_binary="/usr/bin/docker",
            docker_socket="unix:///run/user/1001/docker.sock",
            timeout_seconds=3.0,
        )
    return RuntimeProfile(
        kind,
        policy,
        reviewed_image_sha256="a" * 64,
        worker_reviewed=True,
    )


def _issue(ledger, profile, **extra):
    kwargs = dict(
        worker_sha256=WORKER, host_id=HOST, issuer_id=ISSUER,
        at=NOW - timedelta(minutes=2), operator_id=101,
        authorized_operator_ids=OPERATORS, operator_ack=True,
    )
    kwargs.update(extra)
    return ledger.issue(profile, **kwargs)


def _receipt(profile, nonce, *, worker=WORKER, key=KEY):
    payload = {
        "schema_version": 1,
        "audience": "MMT-RUNTIME-A4-RESEARCH-ONLY",
        "issuer_id": ISSUER,
        "host_id": HOST,
        "runtime_kind": profile.kind.value,
        "image_digest": "a" * 64,
        "policy_digest": policy_digest(profile),
        "worker_digest": worker,
        "issued_at": "2026-10-14T11:59:00Z",
        "expires_at": "2026-10-14T12:04:00Z",
        "nonce": nonce,
        "checks": {name: True for name in (
            "rootless_daemon_verified", "runsc_runtime_verified",
            "network_denied_verified", "readonly_root_verified",
            "no_mounts_verified", "no_privileges_verified",
            "nonroot_uid_verified", "cpu_memory_pid_limits_verified",
            "no_credentials_verified", "oci_cleanup_verified",
            "fixed_fixture_abi_verified",
        )},
    }
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode()
    mac = hmac.new(key, canonical, hashlib.sha256).hexdigest()
    return json.dumps(
        {"payload": payload, "mac_sha256": mac},
        sort_keys=True, separators=(",", ":"),
    ).encode()


def _consume(ledger, receipt, nonce, profile, **extra):
    kwargs = dict(
        nonce=nonce, profile=profile, review_key=KEY,
        host_id=HOST, issuer_id=ISSUER, at=NOW,
        operator_id=101, authorized_operator_ids=OPERATORS,
        operator_ack=True,
    )
    kwargs.update(extra)
    return ledger.consume(receipt, **kwargs)


@pytest.mark.parametrize("kind", tuple(RuntimeKind))
def test_one_time_review_for_four_kinds_and_restart(tmp_path, monkeypatch, kind):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    profile = _profile(monkeypatch, kind)
    path = tmp_path / "a5.sqlite"
    ledger = RuntimeChallengeLedger(path)
    challenge = _issue(ledger, profile)
    assert challenge.status == "ISSUED_REVIEW_ONLY"
    assert challenge.execution_authorized is False
    assert len(challenge.nonce) == 48
    assert challenge.nonce not in path.read_bytes().decode("latin1")
    receipt = _receipt(profile, challenge.nonce)
    review = _consume(ledger, receipt, challenge.nonce, profile)
    assert review.status == "EVIDENCE_CONSUMED_REVIEW_ONLY"
    assert review.receipt_sha256 == hashlib.sha256(receipt).hexdigest()
    assert review.host_isolation_certified is False
    assert review.execution_authorized is False
    assert review.worker_installed is False
    assert review.retry_permitted is False
    assert review.broker_enabled is False
    assert review.telegram_enabled is False
    ledger.close()
    reopened = RuntimeChallengeLedger(path)
    try:
        with pytest.raises(RuntimeChallengeRefused, match="ALREADY_SPENT"):
            _consume(reopened, receipt, challenge.nonce, profile)
    finally:
        reopened.close()


def test_two_connections_cannot_spend_once_twice(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    profile = _profile(monkeypatch)
    path = tmp_path / "a5.sqlite"
    first, second = RuntimeChallengeLedger(path), RuntimeChallengeLedger(path)
    try:
        nonce = _issue(first, profile).nonce
        receipt = _receipt(profile, nonce)
        assert _consume(second, receipt, nonce, profile).execution_authorized is False
        with pytest.raises(RuntimeChallengeRefused, match="ALREADY_SPENT"):
            _consume(first, receipt, nonce, profile)
    finally:
        first.close()
        second.close()


def test_bad_mac_or_worker_does_not_burn_nonce(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    profile = _profile(monkeypatch)
    ledger = RuntimeChallengeLedger(tmp_path / "a5.sqlite")
    try:
        nonce = _issue(ledger, profile).nonce
        with pytest.raises(RuntimeEvidenceRefused, match="MAC_INVALID"):
            _consume(ledger, _receipt(profile, nonce, key=b"wrong" * 12), nonce, profile)
        with pytest.raises(RuntimeChallengeRefused, match="SCOPE_OR_TIME"):
            _consume(ledger, _receipt(profile, nonce, worker="c"*64), nonce, profile)
        good = _consume(ledger, _receipt(profile, nonce), nonce, profile)
        assert good.status == "EVIDENCE_CONSUMED_REVIEW_ONLY"
    finally:
        ledger.close()


def test_expired_challenge_even_if_signed_receipt_still_valid(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    profile = _profile(monkeypatch)
    ledger = RuntimeChallengeLedger(tmp_path / "a5.sqlite")
    try:
        challenge = _issue(ledger, profile, lifetime_seconds=30)
        with pytest.raises(RuntimeChallengeRefused, match="SCOPE_OR_TIME"):
            _consume(ledger, _receipt(profile, challenge.nonce), challenge.nonce, profile)
    finally:
        ledger.close()


def test_revoke_blocks_review_and_no_release(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    profile = _profile(monkeypatch)
    ledger = RuntimeChallengeLedger(tmp_path / "a5.sqlite")
    try:
        challenge = _issue(ledger, profile)
        ledger.revoke(
            challenge.challenge_digest, operator_id=101,
            authorized_operator_ids=OPERATORS, operator_ack=True,
        )
        with pytest.raises(RuntimeChallengeRefused, match="ALREADY_SPENT_OR_REVOKED"):
            _consume(ledger, _receipt(profile, challenge.nonce), challenge.nonce, profile)
        with pytest.raises(RuntimeChallengeRefused, match="UNKNOWN_OR_SPENT"):
            ledger.revoke(
                challenge.challenge_digest, operator_id=101,
                authorized_operator_ids=OPERATORS, operator_ack=True,
            )
    finally:
        ledger.close()


def test_ledger_directory_must_be_private_and_owned_by_effective_uid(tmp_path, monkeypatch):
    """The A3 private-directory fence must fail closed for unsafe parents.

    This keeps the owner/permission half of ``_approved_dir`` covered without
    faking the effective uid: an exposed parent directory is refused, while the
    owner-only directory owned by the real test user is accepted.
    """
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    exposed = tmp_path / "exposed"
    exposed.mkdir(mode=0o755)
    with pytest.raises(DurableRuntimeRefused,
                       match="PRIVATE_OWNER_ONLY_DIRECTORY_REQUIRED"):
        RuntimeChallengeLedger(exposed / "a5.sqlite")
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    ledger = RuntimeChallengeLedger(private / "a5.sqlite")
    try:
        assert _issue(ledger, _profile(monkeypatch)).execution_authorized is False
    finally:
        ledger.close()


def test_relative_or_symlinked_ledger_paths_are_refused(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    with pytest.raises(DurableRuntimeRefused,
                       match="PRIVATE_ABSOLUTE_LEDGER_PATH_REQUIRED"):
        RuntimeChallengeLedger(Path("relative.sqlite"))
    link = tmp_path / "symlinked"
    link.symlink_to(tmp_path)
    with pytest.raises(DurableRuntimeRefused,
                       match="PRIVATE_ABSOLUTE_LEDGER_PATH_REQUIRED"):
        RuntimeChallengeLedger(link / "a5.sqlite")


def test_operator_and_environment_gates(tmp_path, monkeypatch):
    profile = _profile(monkeypatch)
    ledger = RuntimeChallengeLedger(tmp_path / "a5.sqlite")
    try:
        monkeypatch.delenv("MMT_NONPRODUCTION", raising=False)
        with pytest.raises(RuntimeChallengeRefused, match="NONPRODUCTION_ONLY"):
            _issue(ledger, profile)
        monkeypatch.setenv("MMT_NONPRODUCTION", "1")
        monkeypatch.setenv("MMT_PRODUCTION", "1")
        with pytest.raises(RuntimeChallengeRefused, match="NONPRODUCTION_ONLY"):
            _issue(ledger, profile)
        monkeypatch.delenv("MMT_PRODUCTION", raising=False)
        with pytest.raises(RuntimeChallengeRefused, match="OPERATOR"):
            _issue(ledger, profile, operator_id=202)
        with pytest.raises(RuntimeChallengeRefused, match="OPERATOR"):
            _issue(ledger, profile, operator_ack=False)
        with pytest.raises(RuntimeChallengeRefused, match="INVALID_PINNED"):
            _issue(ledger, profile, worker_sha256="unknown")
        with pytest.raises(RuntimeChallengeRefused, match="INVALID_PINNED"):
            _issue(ledger, profile, lifetime_seconds=901)
    finally:
        ledger.close()


def test_unknown_nonce_cannot_be_signed_into_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    profile = _profile(monkeypatch)
    ledger = RuntimeChallengeLedger(tmp_path / "a5.sqlite")
    try:
        unknown = "a" * 48
        with pytest.raises(RuntimeChallengeRefused, match="UNISSUED_NONCE"):
            _consume(ledger, _receipt(profile, unknown), unknown, profile)
    finally:
        ledger.close()


def test_ledger_scope_tamper_detected(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    profile = _profile(monkeypatch)
    path = tmp_path / "a5.sqlite"
    ledger = RuntimeChallengeLedger(path)
    _issue(ledger, profile)
    ledger.close()
    with sqlite3.connect(path) as database:
        database.execute("UPDATE challenges SET worker_hash='invalid'")
    with pytest.raises(RuntimeChallengeRefused, match="CHALLENGE_LEDGER_DRIFT"):
        RuntimeChallengeLedger(path)


def test_symlink_and_world_readable_ledger_rejected(tmp_path):
    path = tmp_path / "ordinary.sqlite"
    path.write_bytes(b"not sqlite")
    path.chmod(0o600)
    link = tmp_path / "alias.sqlite"
    link.symlink_to(path)
    with pytest.raises(DurableRuntimeRefused, match="PRIVATE_ABSOLUTE_LEDGER_PATH_REQUIRED"):
        RuntimeChallengeLedger(link)
    path.chmod(0o644)
    with pytest.raises(DurableRuntimeRefused, match="PRIVATE_OWNER_ONLY"):
        RuntimeChallengeLedger(path)


def test_no_host_execution_or_automatic_release(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    import subprocess

    def forbidden(*args, **kwargs):
        raise AssertionError("HOST_CODE_EXECUTION_NOT_ALLOWED")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    profile = _profile(monkeypatch)
    ledger = RuntimeChallengeLedger(tmp_path / "a5.sqlite")
    try:
        nonce = _issue(ledger, profile).nonce
        assert not _consume(ledger, _receipt(profile, nonce), nonce, profile).execution_authorized
    finally:
        ledger.close()
