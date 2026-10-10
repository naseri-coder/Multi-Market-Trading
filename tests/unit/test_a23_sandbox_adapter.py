"""A23 actual disposable kernel-scoped Custom data relay / lifecycle E2E."""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time

import pytest

from naseri_markets.a21_custom_contract import CustomContractCatalog
from naseri_markets.a22_custom_bridge import CustomPaperRuntimeBridge
from naseri_markets.a23_sandbox_adapter import (
    FIXED_RELAY, FixedCustomSandbox, SandboxRefused,
)
from naseri_markets.paper_journal import PaperJournal
from naseri_markets.quotes import QuoteOrigin, QuoteTick
from test_a22_custom_bridge import metadata, pinned, sample
from test_a7_replay_pipeline import INST, quote, session


@pytest.fixture
def rig(tmp_path):
    catalog = CustomContractCatalog()
    raw = metadata()
    contract = catalog.register(raw, approved_sha256=pinned(raw))
    journal = PaperJournal(tmp_path / "paper.db")
    bridge = CustomPaperRuntimeBridge(catalog, journal, paper_enabled=True)
    state = bridge.attach(raw, approved_sha256=pinned(raw),
                          instruments=frozenset({INST}),
                          session_policy=session())
    sandbox = FixedCustomSandbox(tmp_path / "a23", catalog=catalog, contract=contract)
    yield catalog, bridge, journal, sandbox, state, contract
    sandbox.close()
    journal.close()


def enable(bridge, state):
    return bridge.enable_paper("custom_demo",
                               approved_sha256=state.descriptor_sha256,
                               expected_revision=state.revision)


def start(sandbox, contract):
    return sandbox.launch(approved_sha256=contract.approved_descriptor_sha256)


@pytest.mark.asyncio
async def test_a23_real_kernel_default_deny_separate_uid_cgroup_and_a22_journal(rig):
    _, bridge, journal, sandbox, state, contract = rig
    assert sandbox.status().state == "NEW"
    assert not state.enabled
    assert start(sandbox, contract).scope_verified
    status = sandbox.status()
    assert status.state == "RUNNING"
    assert status.worker_uid > 0 and status.worker_uid != os.geteuid()
    assert status.fixed_fixture_only and not status.custom_code_executed
    assert not status.private_engine_loaded and not status.live_trading_permitted
    rev = enable(bridge, state).revision
    tick = quote()
    result = await sandbox.dispatch(
        bridge, sample(), tick=tick, expected_revision=rev,
        now=tick.occurred_at)
    assert result.status == "PAPER_RECORDED"
    assert result.stored == 1
    assert journal.count() == 1
    assert sandbox.heartbeat().scope_verified
    assert sandbox.stop().state == "STOPPED"
    assert not sandbox.status().scope_verified
    with pytest.raises(SandboxRefused, match="NOT_RUNNING"):
        sandbox.relay(sample(), tick=tick)


def test_a23_closed_by_default_no_non_ci_fallback(tmp_path, monkeypatch):
    catalog = CustomContractCatalog()
    raw = metadata()
    contract = catalog.register(raw, approved_sha256=pinned(raw))
    sandbox = FixedCustomSandbox(tmp_path / "owner", catalog=catalog, contract=contract)
    try:
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        with pytest.raises(SandboxRefused, match="DISPOSABLE_NONROOT_GITHUB_LINUX_ONLY"):
            start(sandbox, contract)
        assert sandbox.status().state == "NEW"
    finally:
        sandbox.close()


@pytest.mark.parametrize("policy,family,name", [
    ("owner_only", "ny_first_reversal", "ny_first_reversal"),
    ("owner_only", "generic_custom", "private_study"),
    ("commercial_candidate", "generic_custom", "marketplace_candidate"),
])
def test_a23_never_accepts_nyfr_private_or_commercial_context(tmp_path, policy, family, name):
    catalog = CustomContractCatalog()
    raw = metadata(name, access_policy=policy, family=family)
    contract = catalog.register(raw, approved_sha256=pinned(raw))
    with pytest.raises(SandboxRefused, match="PUBLIC_GENERIC_PINNED_CONTRACT_REQUIRED"):
        FixedCustomSandbox(tmp_path / "out", catalog=catalog, contract=contract)
    assert not (tmp_path / "out").exists()


def test_a23_scope_unique_owner_lock_and_no_adoption(rig, tmp_path):
    catalog, _, _, sandbox, _, contract = rig
    with pytest.raises(SandboxRefused, match="EXISTING_SANDBOX_OWNER"):
        FixedCustomSandbox(tmp_path / "a23", catalog=catalog, contract=contract)
    start(sandbox, contract)
    sandbox.stop()
    with pytest.raises(SandboxRefused, match="EXPLICIT_RECOVERY"):
        start(sandbox, contract)
    assert sandbox.reconcile(approved_sha256=contract.approved_descriptor_sha256).state == "NEW"
    assert start(sandbox, contract).state == "RUNNING"
    sandbox.stop()


def test_a23_fail_closed_when_previous_ownership_state_exists(rig, tmp_path):
    catalog, _, _, sandbox, _, contract = rig
    sandbox.close()
    fresh = FixedCustomSandbox(tmp_path / "a23", catalog=catalog, contract=contract)
    try:
        with pytest.raises(SandboxRefused, match="EXPLICIT_RECOVERY"):
            start(fresh, contract)
        with pytest.raises(SandboxRefused, match="RECONCILIATION_DENIED"):
            fresh.reconcile(approved_sha256=contract.approved_descriptor_sha256)
    finally:
        fresh.close()


@pytest.mark.asyncio
async def test_a23_disabled_permission_fails_before_sandbox_exchange(rig):
    _, bridge, journal, sandbox, state, contract = rig
    start(sandbox, contract)
    tick = quote()
    with pytest.raises(SandboxRefused, match="A22_PERMISSION_OR_PIN_DENIED"):
        await sandbox.dispatch(bridge, sample(), tick=tick,
                               expected_revision=1, now=tick.occurred_at)
    assert journal.count() == 0
    enable(bridge, state)
    bridge.disable("custom_demo")
    with pytest.raises(SandboxRefused, match="A22_PERMISSION_OR_PIN_DENIED"):
        await sandbox.dispatch(bridge, sample(), tick=tick,
                               expected_revision=2, now=tick.occurred_at)
    assert journal.count() == 0


@pytest.mark.asyncio
async def test_a23_public_paper_envelope_identity_market_and_live_quote_denied(rig):
    _, bridge, journal, sandbox, state, contract = rig
    start(sandbox, contract)
    enable(bridge, state)
    tick = quote()
    with pytest.raises(ValueError):
        await sandbox.dispatch(bridge, sample(engine_id="ny_first_reversal"),
                               tick=tick, expected_revision=2,
                               now=tick.occurred_at)
    live = QuoteTick(INST, tick.occurred_at, tick.bid, tick.ask, QuoteOrigin.LIVE)
    with pytest.raises(SandboxRefused, match="PRECOMPUTED_PAPER_BYTES"):
        sandbox.relay(sample(), tick=live)
    with pytest.raises(SandboxRefused, match="PRECOMPUTED_PAPER_BYTES"):
        sandbox.relay(b"x" * 8193, tick=tick)
    assert journal.count() == 0


@pytest.mark.asyncio
async def test_a23_revocation_while_sandbox_is_awaited_blocks_journal(rig):
    _, bridge, journal, sandbox, state, contract = rig
    start(sandbox, contract)
    enable(bridge, state)
    entered, go = threading.Event(), threading.Event()
    real = sandbox.relay

    def deferred(packet, *, tick):
        entered.set()
        if not go.wait(2):
            raise SandboxRefused("A23_RACE_TEST_TIMEOUT")
        return real(packet, tick=tick)

    sandbox.relay = deferred
    tick = quote()
    pending = asyncio.create_task(
        sandbox.dispatch(bridge, sample(), tick=tick,
                         expected_revision=2, now=tick.occurred_at))
    await asyncio.wait_for(asyncio.to_thread(entered.wait, 2), 3)
    bridge.disable("custom_demo")
    go.set()
    with pytest.raises(SandboxRefused, match="PERMISSION_CHANGED_DURING_SANDBOX"):
        await asyncio.wait_for(pending, 4)
    assert journal.count() == 0


def test_a23_real_worker_crash_no_restart_then_manual_reconcile(rig):
    _, _, _, sandbox, _, contract = rig
    start(sandbox, contract)
    stopped = sandbox.crash_for_test()
    assert stopped.state == "QUARANTINED"
    with pytest.raises(SandboxRefused, match="EXPLICIT_RECOVERY"):
        start(sandbox, contract)
    # Owned systemd-run wrapper must exit before explicit reconciliation.
    sandbox._stop_process()
    with pytest.raises(SandboxRefused, match="RECONCILIATION_DENIED"):
        sandbox.reconcile(approved_sha256="0" * 64)
    assert sandbox.reconcile(
        approved_sha256=contract.approved_descriptor_sha256).state == "NEW"
    assert start(sandbox, contract).state == "RUNNING"
    sandbox.stop()


def test_a23_actual_child_monotonic_lease_expiry_without_heartbeat(rig):
    _, _, _, sandbox, _, contract = rig
    start(sandbox, contract)
    time.sleep(3.5)
    with pytest.raises(SandboxRefused):
        sandbox.heartbeat()
    assert sandbox.status().state == "QUARANTINED"
    sandbox._stop_process()


def test_a23_real_nonroot_kernel_attestation_required_and_wrong_pin_denied(rig):
    _, _, _, sandbox, _, contract = rig
    with pytest.raises(SandboxRefused, match="FRESH_PUBLIC_PIN"):
        sandbox.launch(approved_sha256="0" * 64)
    assert sandbox.status().state == "NEW"
    start(sandbox, contract)
    original = sandbox._uid
    sandbox._uid = os.geteuid()
    with pytest.raises(SandboxRefused, match="KERNEL_ATTESTATION"):
        sandbox.heartbeat()
    sandbox._uid = original
    sandbox.stop()


def test_a23_fixed_worker_prohibits_unknown_code_and_enforces_real_seccomp():
    import ast

    ast.parse(FIXED_RELAY)
    assert "sc.seccomp_init(0x00050000 | errno.EPERM)" in FIXED_RELAY
    assert "socket.socket(socket.AF_INET" in FIXED_RELAY
    assert "os.open('/etc/passwd', os.O_RDONLY)" in FIXED_RELAY
    assert "os.fork()" in FIXED_RELAY
    assert "select.select" in FIXED_RELAY
    assert "eval(" not in FIXED_RELAY
    assert "exec(" not in FIXED_RELAY
    assert "importlib" not in FIXED_RELAY
    assert "MetaTrader5" not in FIXED_RELAY
    assert "private_nyfr_core" not in FIXED_RELAY


def test_a23_state_file_contains_only_safe_terminal_fixture_metadata(rig, tmp_path):
    _, _, _, sandbox, _, contract = rig
    start(sandbox, contract)
    sandbox.stop()
    state = json.loads((tmp_path / "a23" / "a23.json").read_text())
    assert state["fixed_fixture_only"] is True
    assert state["custom_code_executed"] is False
    assert state["live_trading_permitted"] is False
    assert state["pid_observed_only"] is None
    assert state["descriptor_sha256"] == contract.approved_descriptor_sha256
