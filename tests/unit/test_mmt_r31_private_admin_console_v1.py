"""R31 REAL Stage12/10 fixture tests; NO Telegram connection or real orders."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from naseri_markets.contracts import Direction, Instrument, Market
from naseri_markets.core_api_v1 import (
    ClosedCandle, CoreBinding, CoreDecision, CoreEventType, CoreInput,
    CoreManifest, CoreResult, DataOrigin, DecisionKind, SetupSpec,
)
from naseri_markets.instrument_registry_v1 import (
    InstrumentMetadata, ListingStatus, MetadataOrigin, ProviderSnapshot,
    ResearchInstrumentCatalog,
)
from naseri_markets.market_data_engine_v1 import PriceBasis, VolumeSemantics
from naseri_markets.offline_signal_lifecycle_v1 import OfflineSignalLifecycle
from naseri_markets.trading_control_center_v1 import (
    ControlRefused, CoreListing, OfflineTradingControlCenter,
)
from naseri_markets.mmt_r31_private_admin_console_v1 import (
    R31AdminRefused, R31OfflineAdminConsole, R31PrivateTelegramAdminPanel,
)

NOW = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
CORE = CoreManifest(
    "example.public", "1.0.0", (SetupSpec("breakout", "Example", True),),
    frozenset({Market.CRYPTO}),
    frozenset({CoreEventType.CLOSED_CANDLE, CoreEventType.POSITION_UPDATE}), 1,
)
INSTRUMENT = Instrument(Market.CRYPTO, "research_data", "ALPHAUSD", "UTC", "USD")


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setenv("MMT_NONPRODUCTION", "1")
    monkeypatch.delenv("MMT_PRODUCTION", raising=False)


@pytest.fixture
def center(tmp_path):
    catalog = ResearchInstrumentCatalog(max_age_seconds=86400)
    metadata = InstrumentMetadata(
        "research_data", Market.CRYPTO, "ALPHAUSD", "UTC", "USD",
        D(".01"), MetadataOrigin.PUBLIC_CONTRACT_RESEARCH,
        ListingStatus.OPEN, NOW, "SYNTHETIC_FIXTURE",
    )
    catalog.replace(ProviderSnapshot(
        "research_data", MetadataOrigin.PUBLIC_CONTRACT_RESEARCH,
        NOW, (metadata,), "c" * 64,
    ))
    with OfflineTradingControlCenter(
        tmp_path / "r31_panel.sqlite",
        admin_ids={1001, 1002},
        catalog=catalog,
        listings=(
            CoreListing(CORE.core_id, "Example Public Core", CORE.core_version,
                        manifest=CORE),
        ),
        enabled=True,
    ) as center:
        yield center


def setup(center, *, instance_id="demo_one", actor=1001):
    view = center.create_instance(
        actor, core_id=CORE.core_id, instance_id=instance_id,
        account_id="paper_account", portfolio_id="paper_portfolio",
    )
    view = center.add_binding(
        actor, instance_id, provider="research_data",
        symbol="ALPHAUSD", timeframe="15m",
        now=NOW, expected_revision=view.revision,
    )
    binding = center.preview_bindings(actor, instance_id, now=NOW)[0]
    return view, binding


def build_signal(store, view, binding):
    candle = ClosedCandle(
        NOW - timedelta(minutes=15), NOW,
        D("100"), D("106"), D("92"), D("100"), D("5"),
    )
    core_binding = CoreBinding(
        view.instance_id, binding.binding_id, INSTRUMENT, "15m",
    )
    event = CoreInput(
        CORE.core_id, CORE.core_version, core_binding,
        CoreEventType.CLOSED_CANDLE, NOW, DataOrigin.REPLAY, "fixture_r31",
        (candle,),
    )
    decision = CoreDecision(
        "decision_r31", DecisionKind.ENTRY_INTENT, "breakout",
        direction=Direction.LONG, entry=D("100"), stop=D("90"),
        targets=(D("110"),),
    )
    result = CoreResult(
        CORE.core_id, CORE.core_version, view.instance_id, binding.binding_id,
        NOW, event.input_digest, (decision,),
    )
    return store.register(
        CORE, event, result, decision, channel_id=-10099,
        price_basis=PriceBasis.TRADE,
        volume_semantics=VolumeSemantics.TRADED,
        expires_at=NOW + timedelta(hours=1), operator_ack=True,
    )


def test_r31_scoped_overview_owner_isolation(center):
    setup(center)
    console = R31OfflineAdminConsole(center, operator_ack=True)
    assert console.overview(1001)["accessible_instances"] == ("demo_one",)
    assert console.overview(1002)["accessible_instances"] == ()
    with pytest.raises(ControlRefused):
        console.detail(1002, "demo_one")
    with pytest.raises(ControlRefused):
        console.overview(9999)
    report = console.detail(1001, "demo_one")
    assert report["bindings"][0]["symbol"] == "ALPHAUSD"
    assert report["bindings"][0]["timeframe"] == "15m"
    assert report["telegram_signal_publication_enabled"] is False
    assert report["trade_reporting"] == "REALIZED_PNL_NOT_INDEPENDENTLY_ATTESTED"
    assert report["manual_reconciliation_required_or_unavailable"] is True


def test_r31_disable_atomic_cas_all_requests_and_audit(center):
    view, _ = setup(center)
    for field in ("analysis", "signals", "paper"):
        view = center.set_request(
            1001, view.instance_id, field=field, requested=True,
            expected_revision=view.revision,
        )
    before = len(center.audit(1001, view.instance_id))
    console = R31OfflineAdminConsole(center, operator_ack=True)
    result = console.disable_requests(
        1001, "demo_one", expected_revision=view.revision,
        operator_ack=True,
    )
    assert result["revision"] == view.revision + 1
    updated = center.inspect(1001, "demo_one")
    assert not any((
        updated.analysis_requested, updated.telegram_signals_requested,
        updated.paper_orders_requested,
    ))
    history = center.audit(1001, "demo_one")
    assert len(history) == before + 1
    assert history[-1]["action"] == "R31_DISABLE_ALL_REQUESTS"
    with pytest.raises(ControlRefused, match="STALE_INSTANCE_REVISION"):
        console.disable_requests(
            1001, "demo_one", expected_revision=view.revision,
            operator_ack=True,
        )
    with pytest.raises(ControlRefused):
        console.disable_requests(
            1002, "demo_one", expected_revision=updated.revision,
            operator_ack=True,
        )
    assert len(center.audit(1001, "demo_one")) == before + 1


def test_r31_no_ack_and_production_env_refuse_before_write(center, monkeypatch):
    view, _ = setup(center)
    console = R31OfflineAdminConsole(center, operator_ack=True)
    with pytest.raises(R31AdminRefused, match="EXPLICIT_DISABLE"):
        console.disable_requests(
            1001, "demo_one", expected_revision=view.revision,
        )
    monkeypatch.setenv("MMT_PRODUCTION", "1")
    with pytest.raises(R31AdminRefused, match="NONPRODUCTION"):
        console.disable_requests(
            1001, "demo_one", expected_revision=view.revision,
            operator_ack=True,
        )
    assert center.inspect(1001, "demo_one").revision == view.revision


def test_r31_private_signal_preview_unknown_never_resends(center, tmp_path):
    view, binding = setup(center)
    with OfflineSignalLifecycle(
        tmp_path / "r31_signals.sqlite", enabled=True,
    ) as signals:
        signal = build_signal(signals, view, binding)
        console = R31OfflineAdminConsole(
            center, signals=signals, operator_ack=True,
        )
        overview = console.private_signal_preview(
            1001, "demo_one", signal_key=signal.key,
        )
        assert overview["outbox_state_counts"] == {"PENDING": 1}
        assert overview["exactly_once_telegram_delivery_proven"] is False
        assert overview["telegram_sent"] is False
        assert signals.claim_dry_run(signal.key, operator_ack=True)
        review = console.private_signal_preview(
            1001, "demo_one", signal_key=signal.key,
        )
        assert review["unresolved_outbox_effects"] is True
        assert signals.quarantine_inflight() == 1
        blocked = console.private_signal_preview(
            1001, "demo_one", signal_key=signal.key,
        )
        assert blocked["outbox_state_counts"]["UNKNOWN"] == 1
        assert blocked["real_telegram_delivery_verified"] is False
        with pytest.raises(ControlRefused):
            console.private_signal_preview(
                1002, "demo_one", signal_key=signal.key,
            )


class Message:
    def __init__(self, text):
        self.text = text
        self.replies = []

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)


def update(text, *, actor=1001, chat_id=None, chat_type="private"):
    chat_id = actor if chat_id is None else chat_id
    msg = Message(text)
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=actor),
        effective_chat=SimpleNamespace(id=chat_id, type=chat_type),
        effective_message=msg, callback_query=None,
    )


def test_r31_telegram_private_only_and_command_cas(center):
    view, _ = setup(center)
    panel = R31PrivateTelegramAdminPanel(
        R31OfflineAdminConsole(center, operator_ack=True),
    )
    u = update("/mmt31_view demo_one")
    asyncio.run(panel.command(u, None))
    assert "ALPHAUSD" in u.effective_message.replies[0]
    group = update("/mmt31_view demo_one", chat_id=-123, chat_type="group")
    asyncio.run(panel.command(group, None))
    assert "غیرمجاز" in group.effective_message.replies[0]
    attacker = update("/mmt31_view demo_one", actor=1002)
    asyncio.run(panel.command(attacker, None))
    assert "غیرمجاز" in attacker.effective_message.replies[0]
    malformed = update("/mmt31_off demo_one 0")
    asyncio.run(panel.command(malformed, None))
    assert center.inspect(1001, "demo_one").revision == view.revision
    valid = update(f"/mmt31_off demo_one {view.revision}")
    asyncio.run(panel.command(valid, None))
    assert "غیرفعال" in valid.effective_message.replies[0]
    assert center.inspect(1001, "demo_one").revision == view.revision + 1
    stale = update(f"/mmt31_off demo_one {view.revision}")
    asyncio.run(panel.command(stale, None))
    assert "غیرمجاز" in stale.effective_message.replies[0]


def test_r31_private_only_api_no_telegram_transport_or_live_methods(center):
    console = R31OfflineAdminConsole(center, operator_ack=True)
    assert not hasattr(console, "send_message")
    assert not hasattr(console, "send_order")
    assert not hasattr(console, "enable_live")
    assert not hasattr(console, "acknowledge_dry_run")
