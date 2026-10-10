"""A27 actual single SQLite crash consistency and explicit recovery tests."""
from __future__ import annotations

import asyncio
import sqlite3
import subprocess
import sys
import threading

import pytest

from naseri_markets.a21_custom_contract import CustomContractCatalog, inspect_custom_paper_fixture
from naseri_markets.a22_custom_bridge import CustomPaperRuntimeBridge, CustomRuntimeRefused
from naseri_markets.a25_bundle_admission import PublisherAdmissionRefused
from naseri_markets.a27_unified_ledger import (
    RecoveredFixedPaperSession, RecoveryFenceRefused, UnifiedAuthorizationLedger,
    UnifiedPaperCommitFence,
)
from naseri_markets.delivery_ledger import IdentityConflict
from naseri_markets.paper_journal import PaperJournal
from test_a22_custom_bridge import metadata, pinned, sample
from test_a24_publisher_admission import INSTALL, NOW, ctx as a24_ctx, service
from test_a25_bundle_admission import case as a25_case, args, release
from test_a7_replay_pipeline import INST, quote, session


@pytest.fixture
def rig(request, tmp_path):
    # Nested fixture definitions are imported, not part of global conftest.
    assert callable(a24_ctx) and callable(a25_case)
    case = request.getfixturevalue("a25_case")
    ctx, gate, package, a24 = case
    signed_release = release(ctx, package=package, a24=a24)
    gate.admit(**args(case, signed=signed_release))
    ledger_path = tmp_path / "a27-unified.db"

    def open_ledger(now=NOW):
        return UnifiedAuthorizationLedger(
            ledger_path, catalog=ctx[0], contract=ctx[1],
            installation_id=INSTALL, authority=ctx[2], gate=gate,
            a24_envelope=a24, release=signed_release, package=package, now=now)

    journal = PaperJournal(tmp_path / "legacy-a7-unused.db")
    bridge = CustomPaperRuntimeBridge(
        ctx[0], journal, paper_enabled=True,
        require_atomic_fence=True, atomic_fence_kind="a27")
    descriptor = metadata()
    state = bridge.attach(descriptor, approved_sha256=pinned(descriptor),
                          instruments=frozenset({INST}), session_policy=session())
    assert not state.enabled
    ledger = open_ledger()
    wrapper = RecoveredFixedPaperSession(ledger, ctx[7], bridge)
    yield ctx, gate, journal, bridge, ledger, wrapper, open_ledger, ledger_path
    try:
        wrapper.stop()
    except Exception:
        pass
    ledger.close()
    journal.close()


def recover(rig):
    ctx, _, _, bridge, ledger, _, _, _ = rig
    receipt = ledger.recover(
        now=NOW, approved_sha256=ctx[1].approved_descriptor_sha256,
        expected_generation=ledger.receipt().generation)
    if not bridge.status("custom_demo").enabled:
        bridge.enable_paper(
            "custom_demo", approved_sha256=ctx[1].approved_descriptor_sha256,
            expected_revision=1)
    return receipt


@pytest.mark.asyncio
async def test_a27_real_fixed_relay_and_single_transaction_journal(rig):
    ctx, gate, old, bridge, ledger, wrapper, _, path = rig
    assert ledger.receipt().state == "SEALED"
    assert not ledger.receipt().armed_this_process
    with pytest.raises(RecoveryFenceRefused, match="RECOVERY_REQUIRED"):
        wrapper.launch(now=NOW)
    proof = recover(rig)
    assert proof.state == "ACTIVE" and proof.generation == 2
    assert proof.armed_this_process
    assert not proof.off_host_rollback_protected and proof.single_file_commit
    assert wrapper.launch(now=NOW).scope_verified
    tick = quote()
    result = await wrapper.dispatch(sample(), tick=tick, now=NOW,
                                    expected_revision=2)
    assert result.status == "PAPER_RECORDED" and result.stored == 1
    assert ledger.count() == 1
    assert old.count() == 0  # no cross-file A7 insert in A27
    rows = ledger._db.execute("PRAGMA database_list").fetchall()
    assert len(rows) == 1 and rows[0][1] == "main"
    assert ledger._db.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    assert ledger._db.execute("PRAGMA synchronous").fetchone()[0] == 2
    assert path.stat().st_mode & 0o077 == 0
    assert not ledger.receipt().live_trading_permitted
    assert not ledger.receipt().private_engine_installed


def test_a27_crash_reopens_inactive_until_explicit_pinned_recovery(rig):
    ctx, gate, old, bridge, ledger, wrapper, open_ledger, path = rig
    recover(rig)
    paper = inspect_custom_paper_fixture(ctx[1], sample(), quote())
    assert wrapper.fence.commit([paper], now=NOW).inserted == 1
    ledger.close()
    # Simulate process restart: persisted ACTIVE is never implicit authority.
    recovered = open_ledger()
    try:
        assert recovered.receipt().state == "ACTIVE"
        assert not recovered.receipt().armed_this_process
        with pytest.raises(RecoveryFenceRefused, match="ARMED"):
            recovered.commit([paper], now=NOW, bridge=bridge,
                             expected_generation=2)
        with pytest.raises(RecoveryFenceRefused, match="CAS_REQUIRED"):
            recovered.recover(now=NOW, approved_sha256="0"*64,
                              expected_generation=2)
        with pytest.raises(RecoveryFenceRefused, match="STALE"):
            recovered.recover(now=NOW,
                              approved_sha256=ctx[1].approved_descriptor_sha256,
                              expected_generation=1)
        state = recovered.recover(
            now=NOW, approved_sha256=ctx[1].approved_descriptor_sha256,
            expected_generation=2)
        assert state.generation == 3 and state.armed_this_process
        assert recovered.count() == 1
        assert recovered.commit([paper], now=NOW, bridge=bridge,
                                expected_generation=3).duplicate == 1
    finally:
        recovered.close()


def test_a27_actual_sigkill_before_commit_rolls_back_grant_and_paper_together(rig):
    ctx, gate, old, bridge, ledger, wrapper, open_ledger, path = rig
    recover(rig)
    base = ledger.receipt()
    ledger.close()
    script = """
import sqlite3, sys
c = sqlite3.connect(sys.argv[1], isolation_level=None, timeout=8)
c.execute('PRAGMA journal_mode=DELETE')
c.execute('PRAGMA synchronous=FULL')
c.execute('BEGIN IMMEDIATE')
c.execute("UPDATE a27_grant SET state='REVOKED',generation=generation+1")
c.execute("INSERT INTO a27_paper_intents VALUES('custom_demo','crash-uncommitted','x','{}',?)", (int(sys.argv[2])+1,))
print('TRANSACTION_OPEN', flush=True)
sys.stdin.buffer.read(1)
"""
    child = subprocess.Popen(
        [sys.executable, "-I", "-c", script, str(path), str(base.generation)],
        stdout=subprocess.PIPE, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        assert child.stdout.readline() == b"TRANSACTION_OPEN\n"
        child.kill()
        assert child.wait(timeout=5) != 0
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)
        child.stdout.close()
        child.stdin.close()
        child.stderr.close()
    reopened = open_ledger()
    try:
        assert reopened.receipt().generation == base.generation
        assert reopened.receipt().state == "ACTIVE"
        assert not reopened.receipt().armed_this_process
        assert reopened.count() == 0
        assert reopened._db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        reopened.close()


def test_a27_durable_revocation_and_old_signed_proof_never_rearms(rig):
    ctx, _, _, bridge, ledger, wrapper, open_ledger, path = rig
    recover(rig)
    revocation = ledger.revoke()
    assert revocation.state == "REVOKED"
    assert not revocation.armed_this_process
    with pytest.raises(RecoveryFenceRefused, match="RECOVERY_REVOKED_OR_STALE"):
        ledger.recover(now=NOW,
                       approved_sha256=ctx[1].approved_descriptor_sha256,
                       expected_generation=revocation.generation)
    ledger.close()
    again = open_ledger()
    try:
        assert again.receipt().state == "REVOKED"
        with pytest.raises(RecoveryFenceRefused, match="RECOVERY_REVOKED_OR_STALE"):
            again.recover(now=NOW,
                          approved_sha256=ctx[1].approved_descriptor_sha256,
                          expected_generation=again.receipt().generation)
    finally:
        again.close()


def test_a27_full_batch_rollback_on_duplicate_identity_conflict(rig):
    ctx, _, old, bridge, ledger, wrapper, _, _ = rig
    recover(rig)
    valid = inspect_custom_paper_fixture(ctx[1], sample(), quote())
    assert wrapper.fence.commit([valid], now=NOW).inserted == 1
    from dataclasses import replace
    bad = replace(valid, entry=valid.entry + 1)
    fresh = replace(valid, signal_id="new-not-persisted")
    with pytest.raises(IdentityConflict, match="PAPER_IDENTITY_CONFLICT"):
        wrapper.fence.commit([fresh, bad], now=NOW)
    assert ledger.count() == 1
    assert ledger._db.execute(
        "SELECT count(*) FROM a27_paper_intents WHERE signal_id='new-not-persisted'"
    ).fetchone()[0] == 0
    assert old.count() == 0


def test_a27_sqlite_writer_revocation_serializes_with_paper_commit(rig):
    ctx, gate, old, bridge, ledger, wrapper, _, path = rig
    recover(rig)
    intent = inspect_custom_paper_fixture(ctx[1], sample(), quote())
    entered = threading.Event()
    revoked = threading.Event()
    worker = []

    def run_revoke():
        c = sqlite3.connect(path, timeout=5, isolation_level=None)
        try:
            entered.set()
            c.execute("UPDATE a27_grant SET state='REVOKED',generation=generation+1")
            revoked.set()
        finally:
            c.close()

    def trace(statement):
        if statement.startswith("INSERT INTO a27_paper_intents"):
            t = threading.Thread(target=run_revoke, daemon=True)
            worker.append(t)
            t.start()
            assert entered.wait(2)
            assert not revoked.wait(0.12)  # BEGIN IMMEDIATE holds writer lock
    ledger._db.set_trace_callback(trace)
    try:
        assert wrapper.fence.commit([intent], now=NOW).inserted == 1
    finally:
        ledger._db.set_trace_callback(None)
    for t in worker:
        t.join(5)
        assert not t.is_alive()
    assert revoked.is_set() and ledger.count() == 1
    with pytest.raises(RecoveryFenceRefused, match="REVOKED_STALE"):
        wrapper.fence.commit([intent], now=NOW)


def test_a27_revocation_first_wins_and_prevents_all_commits(rig):
    ctx, _, old, bridge, ledger, wrapper, _, path = rig
    recover(rig)
    intent = inspect_custom_paper_fixture(ctx[1], sample(), quote())
    ledger.revoke()
    with pytest.raises(RecoveryFenceRefused):
        wrapper.fence.commit([intent], now=NOW)
    assert ledger.count() == 0


def test_a27_clean_shutdown_seals_and_requires_fresh_recovery(rig):
    ctx, _, _, bridge, ledger, wrapper, open_ledger, _ = rig
    recover(rig)
    sealed = ledger.seal()
    assert sealed.state == "SEALED"
    assert not sealed.armed_this_process
    state = ledger.recover(
        now=NOW, approved_sha256=ctx[1].approved_descriptor_sha256,
        expected_generation=sealed.generation)
    assert state.state == "ACTIVE"
    assert state.generation == sealed.generation + 1


@pytest.mark.asyncio
async def test_a27_wrong_fence_or_no_fence_fails_closed(rig):
    ctx, _, old, bridge, ledger, wrapper, _, _ = rig
    recover(rig)
    tick = quote()
    with pytest.raises(CustomRuntimeRefused, match="A26_ATOMIC_FENCE_REQUIRED"):
        await bridge.dispatch(tick, packets={"custom_demo": sample()},
                              expected_revisions={"custom_demo": 2},
                              now=tick.occurred_at)
    with pytest.raises(CustomRuntimeRefused, match="A26_EXACT_FENCE_AND_CLOCK"):
        await bridge.dispatch(tick, packets={"custom_demo": sample()},
                              expected_revisions={"custom_demo": 2},
                              now=tick.occurred_at, authorization_now=NOW,
                              atomic_fence=object())
    assert ledger.count() == 0 and old.count() == 0


def test_a27_old_external_permission_revoked_before_recovery_blocks_reopen(rig):
    ctx, gate, _, _, ledger, _, open_ledger, _ = rig
    ledger.close()
    ctx[2].revoke_publisher(ctx[1].publisher)
    with pytest.raises(PublisherAdmissionRefused):
        open_ledger()


def test_a27_owner_private_and_no_custom_code_module_loader(tmp_path):
    import ast
    from pathlib import Path
    src = (Path(__file__).resolve().parents[2] /
           "naseri_markets/a27_unified_ledger.py").read_text()
    tree = ast.parse(src)
    banned = {"importlib", "runpy", "requests", "httpx", "aiohttp",
              "subprocess", "socket", "pickle", "ctypes"}
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            assert all(x.name.split(".")[0] not in banned for x in n.names)
        elif isinstance(n, ast.ImportFrom):
            assert (n.module or "").split(".")[0] not in banned
    assert "private_nyfr_core" not in src
    assert "r0_engine" not in src
    assert "Ed25519PrivateKey" not in src
    assert "shell=True" not in src
