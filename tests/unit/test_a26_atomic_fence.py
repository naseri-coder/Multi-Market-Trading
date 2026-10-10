"""A26 transactional PAPER commit fence: revocation races and rollback tests."""
from __future__ import annotations

import sqlite3
import threading
from dataclasses import replace

import pytest

from naseri_markets.a21_custom_contract import inspect_custom_paper_fixture
from naseri_markets.a22_custom_bridge import CustomPaperRuntimeBridge, CustomRuntimeRefused
from naseri_markets.a24_publisher_admission import PublisherAdmissionRefused
from naseri_markets.a25_bundle_admission import (
    A25GuardedFixedFixture, BundleAdmissionRefused,
)
from naseri_markets.a26_atomic_fence import (
    AtomicFenceRefused, AtomicGuardedFixedSession, AtomicPaperCommitFence,
)
from naseri_markets.delivery_ledger import IdentityConflict
from naseri_markets.paper_journal import PaperJournal
from test_a22_custom_bridge import metadata, pinned, sample
from test_a23_sandbox_adapter import enable
from test_a24_publisher_admission import INSTALL, NOW, ctx as a24_ctx, service
from test_a25_bundle_admission import case as a25_case, args, pack, release
from test_a7_replay_pipeline import INST, quote, session


@pytest.fixture
def rig(request, tmp_path):
    assert callable(a25_case) and callable(a24_ctx)
    case = request.getfixturevalue("a25_case")
    ctx, gate, bundle, a24_envelope = case
    original = ctx[6]
    assert not original._require_atomic_fence
    journal = PaperJournal(tmp_path / "a26-paper.db")
    catalog = ctx[0]
    bridge = CustomPaperRuntimeBridge(
        catalog, journal, paper_enabled=True, require_atomic_fence=True)
    descriptor = metadata()
    state = bridge.attach(descriptor, approved_sha256=pinned(descriptor),
                          instruments=frozenset({INST}), session_policy=session())
    assert not state.enabled
    signed_bundle = release(ctx, a24=a24_envelope, package=bundle)
    receipt = gate.admit(**args(case, signed=signed_bundle))
    assert receipt.state == "SIGNED_INERT_BUNDLE_ADMITTED_NO_INSTALL"
    fixture = A25GuardedFixedFixture(
        service(ctx, a24_envelope), gate=gate, package=bundle,
        release=signed_bundle, a24_envelope=a24_envelope)
    guarded = AtomicGuardedFixedSession(fixture, bridge)
    yield ctx, gate, bundle, a24_envelope, journal, bridge, guarded
    ctx[7].close()
    journal.close()


def start(rig):
    ctx, _, _, _, _, bridge, guarded = rig
    assert guarded.launch(now=NOW).scope_verified
    state = enable(bridge, bridge.status("custom_demo"))
    assert state.revision == 2
    return guarded


@pytest.mark.asyncio
async def test_a26_full_dual_signed_inert_fixture_atomic_paper_commit_and_duplicate(rig):
    ctx, gate, _, _, journal, bridge, guarded = rig
    assert not guarded.fence.evidence.power_failure_cross_database_atomicity_guaranteed
    assert guarded.fence.evidence.sqlite_cross_database_concurrency_fenced
    assert guarded.fence.evidence.journal_writes_protected
    assert not guarded.fence.evidence.private_engine_installed
    start(rig)
    tick = quote()
    first = await guarded.dispatch(sample(), tick=tick, now=NOW,
                                   expected_revision=2)
    assert first.status == "PAPER_RECORDED"
    assert first.stored == 1 and first.duplicate == 0
    assert journal.count() == 1
    second = await guarded.dispatch(sample(), tick=tick, now=NOW,
                                    expected_revision=2)
    assert second.stored == 0 and second.duplicate == 1
    assert journal.count() == 1
    assert journal.get("custom_demo", "example-paper-1") is not None


@pytest.mark.asyncio
async def test_a26_hard_fence_cannot_use_previous_ungated_a22_record_batch(rig):
    ctx, gate, _, _, journal, bridge, guarded = rig
    start(rig)
    tick = quote()
    with pytest.raises(CustomRuntimeRefused, match="A26_ATOMIC_FENCE_REQUIRED"):
        await bridge.dispatch(tick, packets={"custom_demo": sample()},
                              expected_revisions={"custom_demo": 2},
                              now=tick.occurred_at)
    with pytest.raises(CustomRuntimeRefused, match="A26_EXACT_FENCE_AND_CLOCK"):
        await bridge.dispatch(tick, packets={"custom_demo": sample()},
                              expected_revisions={"custom_demo": 2},
                              now=tick.occurred_at, atomic_fence=object(),
                              authorization_now=NOW)
    assert journal.count() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("revocation", ["publisher", "installation", "bundle"])
async def test_a26_revoked_before_commit_no_paper_records(rig, revocation):
    ctx, gate, _, _, journal, _, guarded = rig
    start(rig)
    if revocation == "publisher":
        ctx[2].revoke_publisher(ctx[1].publisher)
    elif revocation == "installation":
        ctx[2].revoke_installation(INSTALL, "custom_demo")
    else:
        gate.revoke(INSTALL, "custom_demo")
    tick = quote()
    with pytest.raises(PublisherAdmissionRefused):
        await guarded.dispatch(sample(), tick=tick, now=NOW,
                               expected_revision=2)
    assert journal.count() == 0
    assert ctx[7].status().state == "STOPPED"


@pytest.mark.asyncio
async def test_a26_bundle_supersession_blocks_old_release(rig):
    ctx, gate, _, _, journal, _, guarded = rig
    start(rig)
    from test_a25_bundle_admission import release as make_release
    new_release = make_release(ctx, package=rig[2], a24=rig[3], sequence=2)
    gate.admit(**args((ctx,gate,rig[2],rig[3]), signed=new_release))
    tick = quote()
    with pytest.raises(BundleAdmissionRefused, match="UNADMITTED"):
        await guarded.dispatch(sample(), tick=tick, now=NOW,
                               expected_revision=2)
    assert journal.count() == 0


@pytest.mark.asyncio
async def test_a26_expiration_blocks_commit_even_if_worker_was_running(rig):
    _, _, _, _, journal, _, guarded = rig
    start(rig)
    tick = quote()
    with pytest.raises(PublisherAdmissionRefused):
        await guarded.dispatch(sample(), tick=tick, now=NOW + 301,
                               expected_revision=2)
    assert journal.count() == 0


@pytest.mark.asyncio
async def test_a26_revocation_after_a25_preflight_but_before_sqlite_begin(rig):
    ctx, gate, _, _, journal, _, guarded = rig
    start(rig)
    previous = guarded.fence.commit

    def race(signals, *, now):
        gate.revoke(INSTALL, "custom_demo")
        return previous(signals, now=now)

    guarded.fence.commit = race
    tick = quote()
    with pytest.raises(BundleAdmissionRefused, match="UNADMITTED"):
        await guarded.dispatch(sample(), tick=tick, now=NOW,
                               expected_revision=2)
    assert journal.count() == 0


@pytest.mark.asyncio
async def test_a26_auth_db_revoker_waits_for_locked_commit_linearization(rig):
    ctx, gate, _, _, journal, _, guarded = rig
    start(rig)
    path = ctx[2]._db.execute("PRAGMA database_list").fetchone()[2]
    orig = guarded.fence._verify_locked
    revoker_started = threading.Event()
    revoked = threading.Event()
    results = []
    workers = []

    def revoke():
        db = sqlite3.connect(path, isolation_level=None, timeout=5)
        try:
            revoker_started.set()
            db.execute(
                "UPDATE a24_publishers SET revoked=1 WHERE publisher=?",
                (ctx[1].publisher,))
            revoked.set()
            results.append("revoked")
        finally:
            db.close()

    def locked(**kwargs):
        orig(**kwargs)
        worker = threading.Thread(target=revoke, daemon=True)
        workers.append(worker)
        worker.start()
        assert revoker_started.wait(timeout=2)
        # The true SQLite writer lock is HELD until the PAPER commit.
        assert not revoked.wait(timeout=0.12)

    guarded.fence._verify_locked = locked
    tick = quote()
    result = await guarded.dispatch(sample(), tick=tick, now=NOW,
                                    expected_revision=2)
    for worker in workers:
        worker.join(timeout=5)
        assert not worker.is_alive()
    assert results == ["revoked"]
    # Commit linearized before the revocation. No retroactive erase.
    assert result.stored == 1 and journal.count() == 1
    with pytest.raises(PublisherAdmissionRefused):
        guarded.fence.fixture._check(NOW)


@pytest.mark.asyncio
async def test_a26_bundle_db_revoker_waits_for_locked_commit_linearization(rig):
    ctx, gate, _, _, journal, _, guarded = rig
    start(rig)
    dbpath = gate._db.execute("PRAGMA database_list").fetchone()[2]
    verified = guarded.fence._verify_locked
    entered = threading.Event()
    committed_revoke = threading.Event()
    workers = []

    def revoke():
        db = sqlite3.connect(dbpath, isolation_level=None, timeout=5)
        try:
            entered.set()
            db.execute(
                "UPDATE a25_floors SET revoked=1 WHERE installation_id=? AND engine_id=?",
                (INSTALL, "custom_demo"))
            committed_revoke.set()
        finally:
            db.close()

    def probe(**kwargs):
        verified(**kwargs)
        worker = threading.Thread(target=revoke, daemon=True)
        workers.append(worker)
        worker.start()
        assert entered.wait(timeout=2)
        assert not committed_revoke.wait(timeout=0.12)

    guarded.fence._verify_locked = probe
    tick = quote()
    result = await guarded.dispatch(sample(), tick=tick,
                                    expected_revision=2, now=NOW)
    for w in workers:
        w.join(timeout=5)
        assert not w.is_alive()
    assert committed_revoke.is_set() and result.stored == 1
    with pytest.raises(BundleAdmissionRefused):
        gate.current(**args((ctx, gate, rig[2], rig[3]),
                            signed=rig[6].protected.release))


def test_a26_atomic_partial_journal_batch_rolls_back_on_duplicate_conflict(rig):
    ctx, gate, _, _, journal, bridge, guarded = rig
    tick = quote()
    intent = inspect_custom_paper_fixture(ctx[1], sample(), tick)
    assert intent.engine_id == "custom_demo"
    # Direct fence is not allowed while the A22 toggle is disabled.
    with pytest.raises(AtomicFenceRefused, match="PAPER_PERMISSION_REVOKED"):
        guarded.fence.commit([intent], now=NOW)
    state = enable(bridge, bridge.status("custom_demo"))
    assert state.enabled
    first = guarded.fence.commit([intent], now=NOW)
    assert first.inserted == 1
    modified = replace(intent, entry=intent.entry + 1)
    with pytest.raises(IdentityConflict, match="PAPER_IDENTITY_CONFLICT"):
        guarded.fence.commit([modified], now=NOW)
    assert journal.count() == 1
    fresh = replace(intent, signal_id="example-paper-2")
    with pytest.raises(IdentityConflict):
        guarded.fence.commit([fresh, modified], now=NOW)
    assert journal.count() == 1
    assert journal.get("custom_demo", "example-paper-2") is None


def test_a26_refuses_wrong_bridge_or_unbound_claim_and_cross_engine(rig,tmp_path):
    ctx, gate, _, _, journal, bridge, guarded = rig
    wrong = CustomPaperRuntimeBridge(ctx[0], journal, paper_enabled=True)
    with pytest.raises(AtomicFenceRefused, match="EXACT_GUARDED"):
        AtomicPaperCommitFence(guarded.protected, wrong)
    other = PaperJournal(tmp_path / "other.db")
    try:
        wrong_bridge = CustomPaperRuntimeBridge(
            ctx[0], other, paper_enabled=True, require_atomic_fence=True)
        with pytest.raises(AtomicFenceRefused):
            AtomicPaperCommitFence(guarded.protected, wrong_bridge)
    finally:
        other.close()
    enable(bridge, bridge.status("custom_demo"))
    tick = quote()
    valid = inspect_custom_paper_fixture(ctx[1], sample(), tick)
    with pytest.raises(AtomicFenceRefused, match="EXACT_PUBLIC_PAPER"):
        guarded.fence.commit([replace(valid, engine_id="ny_first_reversal")],
                             now=NOW)
    assert journal.count() == 0


def test_a26_scope_is_readable_true_and_power_loss_not_claimed(rig):
    _, _, _, _, journal, bridge, guarded = rig
    proof = guarded.fence.evidence
    assert proof.journal_writes_protected
    assert proof.sqlite_cross_database_concurrency_fenced
    assert not proof.power_failure_cross_database_atomicity_guaranteed
    assert not proof.private_engine_installed
    assert not proof.live_trading_permitted
    assert journal.count() == 0
    assert bridge._require_atomic_fence


def test_a26_no_arbitrary_code_exec_or_private_nyfr_imports():
    import ast
    from pathlib import Path
    code = (Path(__file__).resolve().parents[2] /
            "naseri_markets/a26_atomic_fence.py").read_text()
    tree = ast.parse(code)
    restricted = {"subprocess", "socket", "importlib", "runpy", "requests",
                  "httpx", "aiohttp", "ctypes", "pickle", "zipfile"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(x.name.split(".")[0] not in restricted for x in node.names)
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in restricted
    assert "Ed25519PrivateKey" not in code
    assert "private_nyfr_core" not in code
    assert "r0_engine" not in code
    assert "shell=True" not in code
