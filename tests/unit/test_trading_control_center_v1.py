"""Stage-12 Telegram control center nonproduction and privacy acceptance."""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace
import asyncio
import hashlib
import sys
import types

import pytest

from naseri_markets.contracts import Market
from naseri_markets.core_api_v1 import CoreManifest
from naseri_markets._contract_acceptance_fixture_v1 import OfflineContractFixture
from naseri_markets.instrument_registry_v1 import (
    InstrumentMetadata, MetadataOrigin, ListingStatus, ProviderSnapshot,
    ResearchInstrumentCatalog,
)
from naseri_markets.trading_control_center_v1 import (
    CoreListing, ControlRefused, OfflineTradingControlCenter,
)
from naseri_markets.trading_control_telegram_v1 import TelegramControlPreviewPanel

NOW = datetime(2026,10,12,12,0,tzinfo=UTC)
BASE = OfflineContractFixture().manifest
PUBLIC = CoreListing(BASE.core_id, "Dual Example Core", BASE.core_version,manifest=BASE)
PRIVATE_MANIFEST = replace(BASE, core_id="private.alpha.core")
PRIVATE = CoreListing(PRIVATE_MANIFEST.core_id, "Owner Sample Reference",
                      PRIVATE_MANIFEST.core_version,"OWNER_ONLY",PRIVATE_MANIFEST)


def meta(provider, market, symbol, origin, at=NOW):
    return InstrumentMetadata(provider, market, symbol, "UTC", "USD", D("0.01"),
                              origin,ListingStatus.OPEN,at,"DEMO_PERPETUAL")


def catalog():
    c=ResearchInstrumentCatalog(max_age_seconds=3600)
    for provider,origin,items in (
        ("research_crypto", MetadataOrigin.PUBLIC_CONTRACT_RESEARCH,
         [(Market.CRYPTO,"ALPHAUSD"),(Market.CRYPTO,"BETAUSD")]),
        ("research_fx",MetadataOrigin.MT5_DEMO_OBSERVATION,
         [(Market.FOREX,"EURUSD")]),
    ):
        c.replace(ProviderSnapshot(provider,origin,NOW,
                                   tuple(meta(provider,m,s,origin) for m,s in items),"a"*64))
    return c


@pytest.fixture
def path(tmp_path): return tmp_path/"separate_preview.sqlite"


@pytest.fixture
def center(path):
    with OfflineTradingControlCenter(path,admin_ids={1001,1002},owner_ids={1001},
                                     catalog=catalog(),listings=(PUBLIC,PRIVATE),enabled=True) as store:
        yield store


def create(c, id="inst_one",core=PUBLIC.core_id,actor=1001,account="paper_acct"):
    return c.create_instance(actor,core_id=core,instance_id=id,account_id=account,
                             portfolio_id="research_portfolio")


def add(c,instance="inst_one",provider="research_crypto",symbol="ALPHAUSD",tf="15m",actor=1001):
    return c.add_binding(actor,instance,provider=provider,symbol=symbol,timeframe=tf,
                         now=NOW,expected_revision=c.inspect(actor,instance).revision)


def test_explicit_disabled_by_default(tmp_path):
    with OfflineTradingControlCenter(tmp_path/"state.sqlite",admin_ids={1001},listings=(PUBLIC,),
                                     catalog=catalog()) as c:
        with pytest.raises(ControlRefused,match="DISABLED"):
            create(c)
        assert [x.core_id for x in c.available_cores(1001)]==["brooks_price_action",PUBLIC.core_id]


def test_brooks_visible_but_unported_not_executable(center):
    assert "brooks_price_action" in [x.core_id for x in center.available_cores(1002)]
    r=create(center,core="brooks_price_action")
    with pytest.raises(ControlRefused,match="CORE_MARKET_NOT_SUPPORTED_OR_NOT_PORTED"):
        add(center)
    with pytest.raises(ControlRefused,match="CORE_ABI_NOT_READY"):
        center.set_request(1001,r.instance_id,field="analysis",requested=True,expected_revision=r.revision)
    assert not center.inspect(1001,r.instance_id).analysis_requested


def test_private_metadata_visible_only_to_owner_and_no_source(center):
    listed=center.available_cores(1002)
    assert PRIVATE.core_id not in [x.core_id for x in listed]
    with pytest.raises(ControlRefused,match="CORE_NOT_VISIBLE"):
        create(center,core=PRIVATE.core_id,actor=1002)
    s=create(center,"owner_instance",core=PRIVATE.core_id)
    assert s.core_id==PRIVATE.core_id
    assert all(PRIVATE.core_id not in repr(x) for x in center.instances(1002))
    with pytest.raises(ControlRefused):
        center.inspect(1002,"owner_instance")
    assert not hasattr(PRIVATE,"source")


def test_public_cross_admin_instance_invisible(center):
    create(center)
    assert center.instances(1002)==()
    with pytest.raises(ControlRefused,match="ACCESSIBLE"):
        center.inspect(1002,"inst_one")
    with pytest.raises(ControlRefused,match="ACCESSIBLE"):
        add(center,actor=1002)
    with pytest.raises(ControlRefused,match="NOT_AUTHORIZED"):
        center.available_cores(9999)


def test_multi_provider_symbol_timeframe_and_core_api_bindings(center):
    create(center)
    add(center)
    add(center,symbol="BETAUSD",tf="5m")
    add(center,provider="research_fx",symbol="EURUSD",tf="1h")
    assert center.inspect(1001,"inst_one").binding_count==3
    bindings=center.preview_bindings(1001,"inst_one",now=NOW)
    assert len(bindings)==3
    assert {v.instrument.market for v in bindings}=={Market.CRYPTO,Market.FOREX}
    assert {v.timeframe for v in bindings}=={"15m","5m","1h"}
    assert all(v.instance_id=="inst_one" for v in bindings)
    assert all(v.binding_id.startswith("bind_") for v in bindings)
    assert all(v.trading_authorized is False for v in center.bindings(1001,"inst_one"))


def test_disabled_target_environments_independent(center):
    create(center);add(center)
    s=center.inspect(1001,"inst_one")
    for field in ("analysis","signals","paper"):
        s=center.set_request(1001,"inst_one",field=field,requested=True,expected_revision=s.revision)
    assert (s.analysis_requested,s.telegram_signals_requested,s.paper_orders_requested)==(True,True,True)
    assert not s.telegram_publication_enabled and not s.broker_orders_enabled and not s.live_trading_enabled
    new=center.set_request(1001,"inst_one",field="paper",requested=False,expected_revision=s.revision)
    assert new.telegram_signals_requested and not new.paper_orders_requested
    assert not new.live_trading_enabled
    with pytest.raises(ControlRefused,match="REQUEST_FIELD"):
        center.set_request(1001,"inst_one",field="live",requested=True,expected_revision=new.revision)


def test_revision_cas_refuses_stale_without_audit_event(center):
    s=create(center);add(center)
    prior=len(center.audit(1001,"inst_one"))
    with pytest.raises(ControlRefused,match="STALE"):
        center.set_request(1001,"inst_one",field="signals",requested=True,expected_revision=s.revision)
    assert len(center.audit(1001,"inst_one"))==prior


@pytest.mark.parametrize("timeframe",["2m","2h","1w","",None,12,True])
def test_unsupported_timeframe_rejected(center,timeframe):
    create(center)
    with pytest.raises(ControlRefused,match="TIMEFRAME"):
        add(center,tf=timeframe)


def test_duplicate_unknown_missing_catalog_and_closed_listing(center):
    create(center);add(center)
    with pytest.raises(ControlRefused,match="DUPLICATE"):
        add(center)
    with pytest.raises(ControlRefused,match="UNVERIFIED"):
        add(center,symbol="FAKE")
    with pytest.raises(ControlRefused,match="UNVERIFIED"):
        center.add_binding(1001,"inst_one",provider="research_crypto",symbol="ALPHAUSD",
                           timeframe="4h",now=NOW+timedelta(hours=10),expected_revision=center.inspect(1001,"inst_one").revision)
    snapshot=ProviderSnapshot("research_fx",MetadataOrigin.MT5_DEMO_OBSERVATION,NOW+timedelta(seconds=1),
                (replace(meta("research_fx",Market.FOREX,"EURUSD",MetadataOrigin.MT5_DEMO_OBSERVATION,
                              NOW+timedelta(seconds=1)),listing_status=ListingStatus.HALTED),),"b"*64)
    center.catalog.replace(snapshot)
    with pytest.raises(ControlRefused,match="NOT_OPEN"):
        center.add_binding(1001,"inst_one",provider="research_fx",symbol="EURUSD",timeframe="15m",
                           now=NOW+timedelta(seconds=1),expected_revision=center.inspect(1001,"inst_one").revision)


def test_changed_catalog_snapshot_fails_preview(center):
    create(center);add(center)
    snapshot=ProviderSnapshot("research_crypto",MetadataOrigin.PUBLIC_CONTRACT_RESEARCH,NOW+timedelta(seconds=1),
        (meta("research_crypto",Market.CRYPTO,"ALPHAUSD",MetadataOrigin.PUBLIC_CONTRACT_RESEARCH,
              NOW+timedelta(seconds=1)),),"f"*64)
    center.catalog.replace(snapshot)
    with pytest.raises(ControlRefused,match="CATALOG_CHANGED"):
        center.preview_bindings(1001,"inst_one",now=NOW+timedelta(seconds=1))


def test_remove_final_binding_revokes_requests(center):
    create(center);add(center)
    s=center.set_request(1001,"inst_one",field="analysis",requested=True,
                         expected_revision=center.inspect(1001,"inst_one").revision)
    binding=center.bindings(1001,"inst_one")[0]
    s=center.remove_binding(1001,"inst_one",binding_id=binding.binding_id,expected_revision=s.revision)
    assert s.binding_count==0 and not s.analysis_requested
    with pytest.raises(ControlRefused,match="BINDING_REQUIRED"):
        center.set_request(1001,"inst_one",field="signals",requested=True,expected_revision=s.revision)


def test_allocation_cas_bounds_account_aggregate_and_preview(center):
    create(center);create(center,"inst_two",account="paper_acct")
    s=center.inspect(1001,"inst_one")
    s=center.set_allocation(1001,"inst_one",max_reserved=D("0.6"),max_notional=D("0.8"),
                            max_order=D("0.01"),max_orders=4,expected_revision=s.revision)
    assert center.preview_capital(1001,"inst_one")["stage8_activation"] is False
    with pytest.raises(ControlRefused,match="OVERBOOKED"):
        center.set_allocation(1001,"inst_two",max_reserved=D("0.5"),max_notional=D("0.8"),
                              max_order=D("0.01"),max_orders=4,expected_revision=1)
    assert center.inspect(1001,"inst_two").max_reserved_risk_fraction=="0.01"
    with pytest.raises(ControlRefused,match="CORE_ALLOCATION"):
        center.set_allocation(1001,"inst_one",max_reserved=D("0.2"),max_notional=D("0.8"),
                              max_order=D("0.25"),max_orders=4,expected_revision=s.revision)


def test_restart_preserves_requested_state_but_no_live_permission(path):
    with OfflineTradingControlCenter(path,admin_ids={1001},listings=(PUBLIC,),catalog=catalog(),enabled=True) as c:
        create(c);add(c)
        c.set_request(1001,"inst_one",field="paper",requested=True,
                      expected_revision=c.inspect(1001,"inst_one").revision)
        audit=c.audit(1001,"inst_one")
    with OfflineTradingControlCenter(path,admin_ids={1001},listings=(PUBLIC,),catalog=catalog(),enabled=True) as c:
        s=c.inspect(1001,"inst_one")
        assert s.paper_orders_requested and not s.broker_orders_enabled
        assert c.audit(1001,"inst_one")==audit
        assert len(c.preview_bindings(1001,"inst_one",now=NOW))==1


def test_default_generated_audit_hash_chain(center):
    create(center);add(center)
    audit=center.audit(1001,"inst_one")
    assert audit[0]["prev_hash"]=="0"*64
    assert audit[1]["prev_hash"]==audit[0]["entry_hash"]
    assert len(audit[0]["entry_hash"])==64


def test_venue_metadata_not_eligibility_or_signal_permission(center):
    create(center);add(center)
    assert all(v.trading_authorized is False and v.live_data_authorized is False
               for v in center.bindings(1001,"inst_one"))
    assert center.preview_capital(1001,"inst_one")["stage8_activation"] is False


def test_failed_path_and_operator_ids(tmp_path):
    with pytest.raises(ControlRefused):
        OfflineTradingControlCenter(tmp_path/"nope"/"db",admin_ids={1001})
    with pytest.raises(ControlRefused):
        OfflineTradingControlCenter(tmp_path/"db",admin_ids={True})
    with pytest.raises(ControlRefused):
        OfflineTradingControlCenter(tmp_path/"db",admin_ids={1001},owner_ids={42})


class FakeMessage:
    def __init__(self,text=""):
        self.text=text
        self.out=[]
    async def reply_text(self,text,reply_markup=None):
        self.out.append((text,reply_markup))


class FakeQuery:
    def __init__(self,data,user_id=1001):
        self.data=data
        self.from_user=SimpleNamespace(id=user_id)
        self.message=FakeMessage()
        self.answers=[]
    async def answer(self,*args,**kwargs):
        self.answers.append((args,kwargs))


def update(text="/mmt12",actor=1001,chat_type="private",chat_id=None,callback=None):
    return SimpleNamespace(effective_user=SimpleNamespace(id=actor),
                           effective_chat=SimpleNamespace(id=actor if chat_id is None else chat_id,type=chat_type),
                           effective_message=FakeMessage(text),callback_query=callback)


def test_telegram_private_admin_gate_and_no_leak(center,monkeypatch):
    panel=TelegramControlPreviewPanel(center)
    u=update(chat_type="group",chat_id=-500)
    asyncio.run(panel.command(u,None))
    assert "غیرمجاز" in u.effective_message.out[0][0]
    u=update(actor=9999)
    asyncio.run(panel.command(u,None))
    assert "غیرمجاز" in u.effective_message.out[0][0]
    create(center,actor=1001)
    u=update(actor=1002)
    # Buttons generated by _overview need stub telegram library.
    fake=types.ModuleType("telegram")
    fake.InlineKeyboardButton=lambda label,callback_data: SimpleNamespace(text=label,callback_data=callback_data)
    fake.InlineKeyboardMarkup=lambda rows: SimpleNamespace(inline_keyboard=rows)
    monkeypatch.setitem(sys.modules,"telegram",fake)
    asyncio.run(panel.command(u,None))
    assert "نمونه‌های شما: 0" in u.effective_message.out[0][0]
    assert "inst_one" not in u.effective_message.out[0][0]


def test_callback_cas_toggles_and_binds_to_private_owner(center,monkeypatch):
    create(center);add(center)
    fake=types.ModuleType("telegram")
    fake.InlineKeyboardButton=lambda label,callback_data: SimpleNamespace(text=label,callback_data=callback_data)
    fake.InlineKeyboardMarkup=lambda rows: SimpleNamespace(inline_keyboard=rows)
    monkeypatch.setitem(sys.modules,"telegram",fake)
    panel=TelegramControlPreviewPanel(center)
    rowid=center._db.execute("SELECT rowid FROM t12_instances WHERE instance_id='inst_one'").fetchone()[0]
    rev=center.inspect(1001,"inst_one").revision
    token=f"t12:toggle:sg:{rowid}:{rev}"
    q=FakeQuery(token)
    asyncio.run(panel.callback(update(callback=q),None))
    assert center.inspect(1001,"inst_one").telegram_signals_requested
    assert q.message.out
    old=FakeQuery(token)
    asyncio.run(panel.callback(update(callback=old),None))
    assert old.answers[0][1].get("show_alert") is True
    untrusted=FakeQuery(f"t12:open:{rowid}",user_id=1002)
    asyncio.run(panel.callback(update(actor=1002,callback=untrusted),None))
    assert untrusted.answers[0][1].get("show_alert") is True


def test_telegram_commands_create_add_alloc_and_visibility(center,monkeypatch):
    fake=types.ModuleType("telegram")
    fake.InlineKeyboardButton=lambda label,callback_data: SimpleNamespace(text=label,callback_data=callback_data)
    fake.InlineKeyboardMarkup=lambda rows: SimpleNamespace(inline_keyboard=rows)
    monkeypatch.setitem(sys.modules,"telegram",fake)
    panel=TelegramControlPreviewPanel(center)
    monkeypatch.setattr("naseri_markets.trading_control_telegram_v1.datetime",SimpleNamespace(now=lambda tz:NOW))
    u=update("/mmt12_new fixture.contract.check myinstance myacct myportfolio")
    asyncio.run(panel.command(u,None))
    assert "myinstance" in u.effective_message.out[0][0]
    u=update("/mmt12_add myinstance research_crypto ALPHAUSD 5m")
    asyncio.run(panel.command(u,None))
    assert "ALPHAUSD" in u.effective_message.out[0][0]
    u=update("/mmt12_risk myinstance 0.07 0.30 0.02 3")
    asyncio.run(panel.command(u,None))
    assert "0.07" in u.effective_message.out[0][0]
    assert not center.inspect(1001,"myinstance").broker_orders_enabled


def test_telegram_register_opt_in_not_poll(monkeypatch,center):
    panel=TelegramControlPreviewPanel(center)
    ext=types.ModuleType("telegram.ext")
    ext.CommandHandler=lambda name,callback:("command",name,callback)
    ext.CallbackQueryHandler=lambda callback,pattern:("callback",pattern,callback)
    monkeypatch.setitem(sys.modules,"telegram.ext",ext)
    app=SimpleNamespace(handlers=[],add_handler=lambda h:app.handlers.append(h))
    panel.register(app)
    assert len(app.handlers)==8
    assert {h[1] for h in app.handlers if h[0]=="command"} == {
        "mmt12", "mmt12_new", "mmt12_add", "mmt12_del", "mmt12_risk",
        "mmt12_params", "mmt12_param_set",
    }
    assert all(item[0] in ("callback","command") for item in app.handlers)
    assert not hasattr(app,"polling_called")


def test_telegram_callback_actor_mismatch(center):
    panel=TelegramControlPreviewPanel(center)
    q=FakeQuery("t12:list",user_id=1002)
    asyncio.run(panel.callback(update(actor=1001,callback=q),None))
    assert q.answers[0][1].get("show_alert") is True


def test_explicit_single_application_dev_mount(monkeypatch,tmp_path):
    from naseri_markets.trading_control_dev_mount_v1 import build_stage12_dev_application
    with pytest.raises(ControlRefused,match="EXPLICIT_NONPRODUCTION"):
        build_stage12_dev_application(token="fake",state_dir=tmp_path,admin_ids={1001})
    app=SimpleNamespace(handlers=[],add_handler=lambda h:app.handlers.append(h))
    fakeadmin=types.ModuleType("naseri_markets.bot_admin_app")
    seen=[]
    def builder(**kwargs):
        seen.append(kwargs)
        return app
    fakeadmin.build_admin_application=builder
    monkeypatch.setitem(sys.modules,"naseri_markets.bot_admin_app",fakeadmin)
    ext=types.ModuleType("telegram.ext")
    ext.CommandHandler=lambda name,callback:("command",name,callback)
    ext.CallbackQueryHandler=lambda callback,pattern:("callback",pattern,callback)
    monkeypatch.setitem(sys.modules,"telegram.ext",ext)
    handle=build_stage12_dev_application(token="fake-token",state_dir=tmp_path,
                                          admin_ids={1001},owner_ids={1001},
                                          listings=(PUBLIC,),catalog=catalog(),explicitly_enabled=True)
    assert handle.application is app and len(seen)==1
    assert len(app.handlers)==8
    assert {h[1] for h in app.handlers if h[0]=="command"} == {
        "mmt12", "mmt12_new", "mmt12_add", "mmt12_del", "mmt12_risk",
        "mmt12_params", "mmt12_param_set",
    }
    assert handle.center.available_cores(1001)[0].core_id=="brooks_price_action"
    handle.close()


def test_cannot_attach_to_existing_non_stage12_database(tmp_path):
    import sqlite3
    db=tmp_path/"existing.sqlite"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE paper_orders(id INTEGER)")
    with pytest.raises(ControlRefused,match="DEDICATED_STAGE12"):
        OfflineTradingControlCenter(db,admin_ids={1001},listings=(PUBLIC,),enabled=True)
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT count(*) FROM paper_orders").fetchone()[0]==0
