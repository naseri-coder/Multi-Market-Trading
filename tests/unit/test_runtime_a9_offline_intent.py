"""A9 inert review tickets: 4 languages, replay, revoke, signature and bounds."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from naseri_markets.multilang_runtime_a1 import RuntimeKind, RuntimeProfile
from naseri_markets.runtime_a4_security_evidence import policy_digest
from naseri_markets.runtime_a5_nonce_custody import ConsumedReview
from naseri_markets.runtime_a9_offline_intent import A9Refused, OfflineIntentLedger
from naseri_markets.secure_plugin_runtime_v1 import SecurePluginPolicy

KEY = b"ci-only-a9-demo-key-not-from-any-real-independent-authority"
NOW = datetime(2026, 10, 14, 12, tzinfo=UTC)
OPS = frozenset({101})
WORKER = "b" * 64
SOURCE = "c" * 64
REQUEST = "d" * 64
HOST = "disposable.mock-host"
ISSUER = "research.operator-fixture"


def _profile(monkeypatch, kind):
    with monkeypatch.context() as m:
        m.setattr(os, "geteuid", lambda: 1001)
        policy = SecurePluginPolicy(
            enabled=True,
            image="registry.invalid/a9-fixture@sha256:" + "a" * 64,
            docker_binary="/usr/bin/docker",
            docker_socket="unix:///run/user/1001/docker.sock",
        )
        return RuntimeProfile(
            kind, policy, reviewed_image_sha256="a" * 64,
            worker_reviewed=True,
        )


def _a5(profile):
    return ConsumedReview("e" * 64, "f" * 64, policy_digest(profile))


def _scope(profile, review, **updates):
    kwargs = dict(
        profile=profile, a5=review, worker=WORKER, source=SOURCE,
        request=REQUEST, host=HOST, issuer=ISSUER, key=KEY,
        at=NOW, operator_id=101, allowed_operators=OPS,
        operator_ack=True,
    )
    kwargs.update(updates)
    return kwargs


def _ledger(tmp_path):
    return OfflineIntentLedger(tmp_path / "a9-intents.sqlite")


@pytest.mark.parametrize("kind", tuple(RuntimeKind))
def test_four_languages_one_spend_and_restart(tmp_path, monkeypatch, kind):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    profile = _profile(monkeypatch, kind)
    review = _a5(profile)
    ledger = _ledger(tmp_path)
    issued = ledger.issue(
        **_scope(profile, review, lifetime_seconds=90),
    )
    assert len(issued.ticket_sha256) == 64
    assert issued.status == "A9_SIMULATED_REVIEW_ONLY"
    assert not issued.worker_execution_authorized
    assert not issued.quarantine_release_authorized
    assert not issued.broker_authorized
    assert not issued.telegram_authorized
    assert issued.envelope not in (tmp_path / "a9-intents.sqlite").read_bytes()
    result = ledger.spend_review(
        issued.envelope, **_scope(profile, review, at=NOW + timedelta(seconds=1)),
    )
    assert result.status == "A9_ONE_TIME_REVIEW_SPENT_NO_EXECUTION"
    assert result.request_sha256 == REQUEST
    assert not result.host_isolation_certified
    assert not result.independent_custody_proved
    assert not result.worker_execution_authorized
    ledger.close()
    other = _ledger(tmp_path)
    try:
        with pytest.raises(A9Refused, match="REVOKED_SPENT_OR_DRIFT"):
            other.spend_review(
                issued.envelope,
                **_scope(profile, review, at=NOW + timedelta(seconds=2)),
            )
    finally:
        other.close()


def test_two_connections_atomic_single_spend(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    profile = _profile(monkeypatch, RuntimeKind.PYTHON)
    review = _a5(profile)
    first = _ledger(tmp_path)
    second = _ledger(tmp_path)
    try:
        ticket = first.issue(**_scope(profile, review))
        out = second.spend_review(
            ticket.envelope, **_scope(profile, review),
        )
        assert out.ticket_sha256 == ticket.ticket_sha256
        with pytest.raises(A9Refused, match="REVOKED_SPENT_OR_DRIFT"):
            first.spend_review(ticket.envelope, **_scope(profile, review))
    finally:
        first.close()
        second.close()


def test_revocation_persists_and_revoke_twice_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    profile = _profile(monkeypatch, RuntimeKind.WASM)
    review = _a5(profile)
    db = _ledger(tmp_path)
    ticket = db.issue(**_scope(profile, review))
    db.revoke(
        ticket.ticket_sha256, operator_id=101,
        allowed_operators=OPS, operator_ack=True,
    )
    with pytest.raises(A9Refused, match="UNKNOWN_OR_USED"):
        db.revoke(
            ticket.ticket_sha256, operator_id=101,
            allowed_operators=OPS, operator_ack=True,
        )
    db.close()
    other = _ledger(tmp_path)
    try:
        with pytest.raises(A9Refused, match="REVOKED_SPENT_OR_DRIFT"):
            other.spend_review(ticket.envelope, **_scope(profile, review))
    finally:
        other.close()


@pytest.mark.parametrize("changed", ["worker", "source", "request", "host", "issuer"])
def test_request_or_host_scope_drift_never_spends(tmp_path, monkeypatch, changed):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    profile = _profile(monkeypatch, RuntimeKind.JAVASCRIPT)
    review = _a5(profile)
    db = _ledger(tmp_path)
    try:
        ticket = db.issue(**_scope(profile, review))
        altered = "not.original-host" if changed in {"host", "issuer"} else "2" * 64
        with pytest.raises(A9Refused, match="SCOPE_OR_TIME_MISMATCH"):
            db.spend_review(
                ticket.envelope, **_scope(profile, review, **{changed: altered}),
            )
        assert db.spend_review(
            ticket.envelope, **_scope(profile, review),
        ).ticket_sha256 == ticket.ticket_sha256
    finally:
        db.close()


def test_forged_mac_wrong_key_and_duplicate_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    profile = _profile(monkeypatch, RuntimeKind.PYTHON)
    review = _a5(profile)
    db = _ledger(tmp_path)
    try:
        ticket = db.issue(**_scope(profile, review))
        body = json.loads(ticket.envelope)
        body["payload"]["request"] = "3" * 64
        forged = json.dumps(body).encode()
        with pytest.raises(A9Refused, match="A9_MAC_INVALID"):
            db.spend_review(forged, **_scope(profile, review))
        with pytest.raises(A9Refused, match="A9_MAC_INVALID"):
            db.spend_review(
                ticket.envelope,
                **_scope(profile, review, key=b"wrong-key-" * 5),
            )
        duplicate = ticket.envelope.replace(b'"payload":{', b'"payload":{},"payload":{')
        with pytest.raises(A9Refused, match="A9_DUPLICATE_FIELD"):
            db.spend_review(duplicate, **_scope(profile, review))
        assert db.spend_review(
            ticket.envelope, **_scope(profile, review),
        ).ticket_sha256 == ticket.ticket_sha256
    finally:
        db.close()


@pytest.mark.parametrize("age", [0, 301, True])
def test_short_lifetime_enforced(tmp_path, monkeypatch, age):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    profile = _profile(monkeypatch, RuntimeKind.TYPESCRIPT)
    db = _ledger(tmp_path)
    try:
        with pytest.raises(A9Refused, match="A9_LIFETIME_INVALID"):
            db.issue(**_scope(profile, _a5(profile), lifetime_seconds=age))
    finally:
        db.close()


def test_expired_ticket_cannot_spend(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    profile = _profile(monkeypatch, RuntimeKind.WASM)
    review = _a5(profile)
    db = _ledger(tmp_path)
    try:
        ticket = db.issue(**_scope(profile, review, lifetime_seconds=1))
        with pytest.raises(A9Refused, match="A9_SCOPE_OR_TIME_MISMATCH"):
            db.spend_review(
                ticket.envelope,
                **_scope(profile, review, at=NOW + timedelta(seconds=1)),
            )
    finally:
        db.close()


def test_malformed_a5_claims_never_issue(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    profile = _profile(monkeypatch, RuntimeKind.PYTHON)
    db = _ledger(tmp_path)
    try:
        review = _a5(profile)
        for forged in (
            replace(review, execution_authorized=True),
            replace(review, host_isolation_certified=True),
            replace(review, worker_installed=True),
            replace(review, profile_sha256="0" * 64),
        ):
            with pytest.raises(A9Refused, match="A9_EXACT_REVIEW_SCOPE_REQUIRED"):
                db.issue(**_scope(profile, forged))
    finally:
        db.close()


def test_environment_operator_and_key_fences(tmp_path, monkeypatch):
    monkeypatch.delenv("MMT_NONPRODUCTION", raising=False)
    profile = _profile(monkeypatch, RuntimeKind.PYTHON)
    review = _a5(profile)
    db = _ledger(tmp_path)
    try:
        with pytest.raises(A9Refused, match="A9_NONPRODUCTION_ONLY"):
            db.issue(**_scope(profile, review))
        monkeypatch.setenv("MMT_NONPRODUCTION", "1")
        with pytest.raises(A9Refused, match="A9_AUTHORIZED_OPERATOR_ACK_REQUIRED"):
            db.issue(**_scope(profile, review, operator_ack=False))
        with pytest.raises(A9Refused, match="A9_OUT_OF_BAND_KEY_REQUIRED"):
            db.issue(**_scope(profile, review, key=b"too-short"))
        monkeypatch.setenv("MMT_PRODUCTION", "1")
        with pytest.raises(A9Refused, match="A9_NONPRODUCTION_ONLY"):
            db.issue(**_scope(profile, review))
    finally:
        db.close()


def test_corrupt_sqlite_state_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    profile = _profile(monkeypatch, RuntimeKind.PYTHON)
    db = _ledger(tmp_path)
    ticket = db.issue(**_scope(profile, _a5(profile)))
    db.close()
    sql = sqlite3.connect(str(tmp_path / "a9-intents.sqlite"))
    sql.execute(
        "UPDATE tickets SET state='SPENT' WHERE ticket_sha=?",
        (ticket.ticket_sha256,),
    )
    sql.commit()
    sql.close()
    with pytest.raises(A9Refused, match="A9_LEDGER_STATE_INVALID"):
        _ledger(tmp_path)


def test_no_subprocess_or_a6_unlock(tmp_path, monkeypatch):
    from naseri_markets.runtime_a6_dispatch_fence import (
        RuntimeA6Denied,
        require_worker_launch,
    )

    monkeypatch.setenv("MMT_NONPRODUCTION", "1")

    def forbidden(*args, **kwargs):
        raise AssertionError("A9_MUST_NOT_LAUNCH_ANYTHING")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    profile = _profile(monkeypatch, RuntimeKind.JAVASCRIPT)
    review = _a5(profile)
    db = _ledger(tmp_path)
    try:
        ticket = db.issue(**_scope(profile, review))
        spent = db.spend_review(
            ticket.envelope, **_scope(profile, review),
        )
        assert spent.worker_execution_authorized is False
        framed = b"\x00\x00\x00\x01aX"
        with pytest.raises(RuntimeA6Denied, match="CERTIFICATION_REQUIRED"):
            require_worker_launch(profile, framed)
    finally:
        db.close()
