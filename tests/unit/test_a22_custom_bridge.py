"""A22 Custom engine PAPER data bridge security and A21 owner-only regressions."""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import timedelta
from decimal import Decimal

import pytest

from naseri_markets.a21_custom_contract import CustomContractCatalog
from naseri_markets.a22_custom_bridge import (
    CustomPaperRuntimeBridge, CustomRuntimeRefused,
)
from naseri_markets.paper_journal import PaperJournal
from naseri_markets.quotes import QuoteOrigin, QuoteTick, QuoteVerdict
from test_a7_replay_pipeline import INST, packet, quote, session


def metadata(engine_id="custom_demo", *, access_policy="public_custom",
             family="generic_custom", **extra):
    obj = {
        "schema_version": 1, "engine_id": engine_id,
        "engine_version": "1.2.3", "publisher": "community.vendor",
        "markets": ["index"], "access_policy": access_policy,
        "strategy_family": family, "adapter": "external_contract",
        "abi_version": 1, "distribution": "metadata_only",
        "artifact_policy": "no_executable_or_ciphertext",
        "permissions": ["paper_analysis"],
        "runtime_mode": "replay_or_synthetic",
        "execution_authorized": False,
    }
    obj.update(extra)
    return json.dumps(obj, sort_keys=True).encode()


def pinned(raw):
    return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def rig(tmp_path):
    catalog = CustomContractCatalog()
    journal = PaperJournal(tmp_path / "a22-paper.db")
    bridge = CustomPaperRuntimeBridge(catalog, journal, paper_enabled=True)
    yield catalog, journal, bridge
    journal.close()


def bind(catalog, bridge, name="custom_demo", **meta):
    raw = metadata(name, **meta)
    catalog.register(raw, approved_sha256=pinned(raw))
    return bridge.attach(raw, approved_sha256=pinned(raw),
                         instruments=frozenset({INST}), session_policy=session())


def enable(bridge, name="custom_demo"):
    state = bridge.status(name)
    return bridge.enable_paper(name, approved_sha256=state.descriptor_sha256,
                               expected_revision=state.revision)


def sample(name="custom_demo", *, tick=None, **extra):
    t = tick if tick is not None else quote()
    return packet(t, **{"engine_id": name, "engine_version": "1.2.3", **extra})


@pytest.mark.asyncio
async def test_a22_public_custom_end_to_end_real_journal_and_explicit_switch(rig):
    catalog, journal, bridge = rig
    status = bind(catalog, bridge)
    assert not status.enabled and status.revision == 1
    assert not status.executable_installed
    assert not status.private_code_loaded
    assert not status.live_trading_permitted
    assert not status.commercial_entitlement_issued
    item = quote()
    with pytest.raises(CustomRuntimeRefused, match="DISABLED_OR_STALE"):
        await bridge.dispatch(item, packets={"custom_demo": sample()},
                              expected_revisions={"custom_demo": 1},
                              now=item.occurred_at)
    assert journal.count() == 0
    enabled = enable(bridge)
    assert enabled.enabled and enabled.revision == 2
    result = await bridge.dispatch(
        item, packets={"custom_demo": sample()},
        expected_revisions={"custom_demo": 2}, now=item.occurred_at)
    assert result.status == "PAPER_RECORDED"
    assert result.quote_verdict is QuoteVerdict.ACCEPTED
    assert result.stored == 1 and result.duplicate == 0
    assert result.submitted_engines == ("custom_demo",)
    assert journal.count() == 1
    assert journal.get("custom_demo", "example-paper-1") is not None
    assert not result.live_trading_permitted
    assert not bridge.status("custom_demo").executable_installed


@pytest.mark.asyncio
async def test_two_independent_custom_public_engines_one_quote_one_dispatch(rig):
    catalog, journal, bridge = rig
    for name in ("custom_demo", "custom_second"):
        bind(catalog, bridge, name)
        enable(bridge, name)
    tick = quote()
    packets = {name: sample(name) for name in ("custom_demo", "custom_second")}
    result = await bridge.dispatch(
        tick, packets=packets, expected_revisions={key: 2 for key in packets},
        now=tick.occurred_at)
    assert result.stored == 2
    assert set(result.submitted_engines) == set(packets)
    assert journal.count() == 2
    assert journal.get("custom_second", "example-paper-1") is not None
    assert journal.get("custom_demo", "example-paper-1") is not None


@pytest.mark.asyncio
async def test_engine_disable_isolated_and_revision_cas_no_unwanted_callback(rig):
    catalog, journal, bridge = rig
    for name in ("custom_demo", "custom_second"):
        bind(catalog, bridge, name)
        enable(bridge, name)
    disabled = bridge.disable("custom_demo")
    assert not disabled.enabled and disabled.revision == 3
    with pytest.raises(CustomRuntimeRefused, match="DISABLED_OR_STALE"):
        await bridge.dispatch(quote(), packets={"custom_demo": sample()},
                              expected_revisions={"custom_demo": 2},
                              now=quote().occurred_at)
    assert journal.count() == 0
    other = await bridge.dispatch(quote(), packets={"custom_second": sample("custom_second")},
                                  expected_revisions={"custom_second": 2},
                                  now=quote().occurred_at)
    assert other.stored == 1 and journal.count() == 1
    with pytest.raises(CustomRuntimeRefused, match="OPERATOR_PIN_AND_CAS"):
        bridge.enable_paper("custom_demo", approved_sha256="0" * 64,
                            expected_revision=3)
    with pytest.raises(CustomRuntimeRefused, match="OPERATOR_PIN_AND_CAS"):
        bridge.enable_paper("custom_demo", approved_sha256=disabled.descriptor_sha256,
                            expected_revision=2)
    assert enable(bridge).revision == 4


@pytest.mark.parametrize("policy,family,engine_id", [
    ("owner_only", "ny_first_reversal", "ny_first_reversal"),
    ("owner_only", "generic_custom", "private_owner"),
    ("commercial_candidate", "generic_custom", "potential_sale"),
])
def test_owner_private_commercial_and_nyfr_never_attach_to_public_bridge(
        rig, policy, family, engine_id):
    catalog, journal, bridge = rig
    raw = metadata(engine_id, access_policy=policy, family=family)
    catalog.register(raw, approved_sha256=pinned(raw))
    with pytest.raises(CustomRuntimeRefused, match="OWNER_OR_COMMERCIAL"):
        bridge.attach(raw, approved_sha256=pinned(raw),
                      instruments=frozenset({INST}), session_policy=session())
    assert journal.count() == 0
    assert catalog.public_lookup(engine_id) is None


def test_unregistered_wrong_pin_unsafe_binding_and_callback_rejected(rig):
    catalog, _, bridge = rig
    raw = metadata()
    with pytest.raises(CustomRuntimeRefused, match="PUBLIC_PINNED_REGISTRATION"):
        bridge.attach(raw, approved_sha256=pinned(raw),
                      instruments=frozenset({INST}), session_policy=session())
    catalog.register(raw, approved_sha256=pinned(raw))
    with pytest.raises(ValueError, match="PIN_MISMATCH"):
        bridge.attach(raw, approved_sha256="0"*64,
                      instruments=frozenset({INST}), session_policy=session())
    with pytest.raises(CustomRuntimeRefused, match="VERIFIED_FIXED_PAPER"):
        bridge.attach(raw, approved_sha256=pinned(raw),
                      instruments=frozenset(), session_policy=session())
    with pytest.raises(CustomRuntimeRefused, match="VERIFIED_FIXED_PAPER"):
        bridge.attach(raw, approved_sha256=pinned(raw),
                      instruments=frozenset({INST}), session_policy=session(),
                      timeout_seconds=9)
    bind_status = bridge.attach(raw, approved_sha256=pinned(raw),
                                instruments=frozenset({INST}), session_policy=session())
    assert not bind_status.enabled
    with pytest.raises(CustomRuntimeRefused, match="DUPLICATE"):
        bridge.attach(raw, approved_sha256=pinned(raw),
                      instruments=frozenset({INST}), session_policy=session())


@pytest.mark.asyncio
async def test_broker_live_quote_blocked_before_any_provider_read(rig):
    catalog, journal, bridge = rig
    bind(catalog, bridge)
    enable(bridge)
    live = QuoteTick(INST, quote().occurred_at, Decimal("43000"),
                     Decimal("43001"), QuoteOrigin.LIVE)
    with pytest.raises(CustomRuntimeRefused, match="NO_LIVE"):
        await bridge.dispatch(live, packets={"custom_demo": sample()},
                              expected_revisions={"custom_demo": 2},
                              now=live.occurred_at)
    assert journal.count() == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("change", [
    {"direction": "short", "stop": "42970"},
    {"engine_id": "ny_first_reversal"},
    {"evidence_mode": "forward"},
    {"observed_at": "2020-01-01T00:00:00+00:00"},
    {"entry": "NaN"},
])
async def test_bad_price_identity_and_forward_evidence_no_persistence(rig, change):
    catalog, journal, bridge = rig
    bind(catalog, bridge)
    enable(bridge)
    tick = quote()
    with pytest.raises(ValueError):
        await bridge.dispatch(tick, packets={"custom_demo": sample(**change)},
                              expected_revisions={"custom_demo": 2},
                              now=tick.occurred_at)
    assert journal.count() == 0


@pytest.mark.asyncio
async def test_bad_packet_makes_entire_two_engine_batch_atomic(rig):
    catalog, journal, bridge = rig
    for name in ("custom_demo", "custom_second"):
        bind(catalog, bridge, name)
        enable(bridge, name)
    tick = quote()
    with pytest.raises(ValueError):
        await bridge.dispatch(tick, packets={
            "custom_demo": sample(),
            "custom_second": sample("custom_second", direction="short",
                                    stop="42970")},
            expected_revisions={"custom_demo": 2, "custom_second": 2},
            now=tick.occurred_at)
    assert journal.count() == 0


@pytest.mark.asyncio
async def test_invalid_bytes_and_revision_mapping_fail_closed(rig):
    catalog, journal, bridge = rig
    bind(catalog, bridge)
    enable(bridge)
    tick = quote()
    for bad in (b"", b"x" * 8193, "json", bytearray(b"{}")):
        with pytest.raises(CustomRuntimeRefused, match="BOUNDED_BYTES_ONLY"):
            await bridge.dispatch(tick, packets={"custom_demo": bad},
                                  expected_revisions={"custom_demo": 2},
                                  now=tick.occurred_at)
    for revisions in ({}, {"custom_demo": True}, {"custom_demo": 3}):
        with pytest.raises(CustomRuntimeRefused):
            await bridge.dispatch(tick, packets={"custom_demo": sample()},
                                  expected_revisions=revisions, now=tick.occurred_at)
    assert journal.count() == 0


@pytest.mark.asyncio
async def test_disable_during_await_discards_even_valid_output(rig):
    catalog, journal, bridge = rig
    bind(catalog, bridge)
    enable(bridge)
    slot = bridge._providers["custom_demo"]
    called, proceed = asyncio.Event(), asyncio.Event()
    original = slot.produce

    async def paused(tick):
        called.set()
        await proceed.wait()
        return await original(tick)

    slot.produce = paused  # test-only race injection, never public extension ABI
    tick = quote()
    task = asyncio.create_task(bridge.dispatch(
        tick, packets={"custom_demo": sample()},
        expected_revisions={"custom_demo": 2}, now=tick.occurred_at))
    await asyncio.wait_for(called.wait(), 2)
    bridge.disable("custom_demo")
    proceed.set()
    result = await asyncio.wait_for(task, 2)
    assert result.status == "PERMISSION_CHANGED_IN_FLIGHT"
    assert result.stored == 0 and journal.count() == 0
    assert not bridge.status("custom_demo").enabled


@pytest.mark.asyncio
async def test_disable_all_revokes_even_when_paper_engine_is_disabled(rig):
    catalog, journal, bridge = rig
    bind(catalog, bridge)
    enable(bridge)
    bridge.disable_all()
    assert bridge.status("custom_demo").revision == 3
    assert not bridge.status("custom_demo").enabled
    with pytest.raises(CustomRuntimeRefused, match="PLATFORM_PAPER_SWITCH_OFF"):
        bridge.enable_paper("custom_demo",
                            approved_sha256=bridge.status("custom_demo").descriptor_sha256,
                            expected_revision=3)
    tick = quote()
    result = await bridge.dispatch(tick, packets={"custom_demo": sample()},
                                   expected_revisions={"custom_demo": 3},
                                   now=tick.occurred_at)
    assert result.status == "PLATFORM_DISABLED"
    assert journal.count() == 0


@pytest.mark.asyncio
async def test_unverified_feed_rejects_without_written_signals(rig):
    catalog, journal, bridge = rig
    bind(catalog, bridge)
    enable(bridge)
    tick = quote()
    result = await bridge.dispatch(tick, packets={"custom_demo": sample()},
                                   expected_revisions={"custom_demo": 2},
                                   now=tick.occurred_at + timedelta(minutes=1))
    assert result.status == "QUOTE_REJECTED"
    assert result.quote_verdict == QuoteVerdict.STALE
    assert journal.count() == 0


@pytest.mark.asyncio
async def test_no_packet_does_not_fabricate_trading_signals(rig):
    catalog, journal, bridge = rig
    bind(catalog, bridge)
    enable(bridge)
    tick = quote()
    result = await bridge.dispatch(tick, packets={"custom_demo": None},
                                   expected_revisions={"custom_demo": 2},
                                   now=tick.occurred_at)
    assert result.status == "PAPER_RECORDED"
    assert result.stored == 0 and journal.count() == 0


def test_new_bridge_disabled_by_default_requires_operator_switch(tmp_path):
    catalog = CustomContractCatalog()
    journal = PaperJournal(tmp_path / "paper.db")
    bridge = CustomPaperRuntimeBridge(catalog, journal)
    bind(catalog, bridge)
    state = bridge.status("custom_demo")
    with pytest.raises(CustomRuntimeRefused, match="PLATFORM_PAPER_SWITCH_OFF"):
        bridge.enable_paper("custom_demo", approved_sha256=state.descriptor_sha256,
                            expected_revision=state.revision)
    journal.close()


def test_public_runtime_statically_never_imports_private_or_network_apis():
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / "naseri_markets"
    tree = ast.parse((root / "a22_custom_bridge.py").read_text())
    forbidden = {"socket", "subprocess", "ctypes", "importlib", "runpy",
                 "requests", "httpx", "aiohttp", "pickle", "base64",
                 "zipfile", "os"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(n.name.split(".")[0] not in forbidden for n in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] not in forbidden
