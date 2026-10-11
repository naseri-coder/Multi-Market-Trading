"""Stage 12: offline, nonproduction multi-core Telegram control plane.

This module only stores *requested* research settings. It NEVER enables a
strategy runner, Telegram publishing, broker orders or LIVE trading.
Stage-6 instrument metadata is NOT a venue/account eligibility grant.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Collection

from .contracts import Market
from .core_api_v1 import CoreBinding, CoreManifest, content_digest
from .instrument_registry_v1 import CatalogRefused, ListingStatus, MetadataOrigin, ResearchInstrumentCatalog

_ID = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{1,79}\Z")
_TIMEFRAMES = frozenset(("1m", "5m", "15m", "30m", "1h", "4h", "12h", "1d"))
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.,() /+:-]{1,70}\Z")


class ControlRefused(ValueError):
    """Non-sensitive, stable rejection for untrusted UI inputs."""


def _identity(value: object, kind: str) -> str:
    if type(value) is not str or not _ID.fullmatch(value):
        raise ControlRefused("INVALID_" + kind)
    return value


def _fraction(raw: object, name: str) -> Decimal:
    if type(raw) is not Decimal or not raw.is_finite() or not Decimal("0") < raw <= 1:
        raise ControlRefused("INVALID_" + name)
    return raw


def _canonical(data: object) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hash(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CoreListing:
    core_id: str
    name: str
    version: str
    visibility: str = "PUBLIC"
    manifest: CoreManifest | None = None

    def __post_init__(self) -> None:
        _identity(self.core_id, "CORE_ID")
        if type(self.name) is not str or not _NAME.fullmatch(self.name):
            raise ControlRefused("INVALID_CORE_NAME")
        if type(self.version) is not str or not 1 <= len(self.version) <= 50:
            raise ControlRefused("INVALID_CORE_VERSION")
        if self.visibility not in ("PUBLIC", "OWNER_ONLY"):
            raise ControlRefused("INVALID_VISIBILITY")
        if self.manifest is not None and (not isinstance(self.manifest, CoreManifest)
                                           or self.manifest.core_id != self.core_id
                                           or self.manifest.core_version != self.version):
            raise ControlRefused("MANIFEST_IDENTITY_MISMATCH")


@dataclass(frozen=True, slots=True)
class InstanceView:
    instance_id: str
    core_id: str
    core_name: str
    account_id: str
    portfolio_id: str
    revision: int
    created_by: int
    analysis_requested: bool
    telegram_signals_requested: bool
    paper_orders_requested: bool
    max_reserved_risk_fraction: str
    max_notional_fraction: str
    max_order_risk_fraction: str
    max_active_orders: int
    binding_count: int
    # Authorization outputs are intentionally permanently false.
    telegram_publication_enabled: bool = False
    broker_orders_enabled: bool = False
    live_trading_enabled: bool = False


@dataclass(frozen=True, slots=True)
class BindingView:
    instance_id: str
    binding_id: str
    market: str
    provider: str
    symbol: str
    timeframe: str
    timezone: str
    quote_currency: str
    source_digest: str
    # Stage-6 research metadata alone cannot grant market participation.
    trading_authorized: bool = False
    live_data_authorized: bool = False


class OfflineTradingControlCenter:
    """Explicit owner/admin scope, SQLite CAS and append-only audit for preview.

    Trusted application must attest actor_id from Telegram framework and run in
    private chat. Neither admin IDs nor owner IDs are obtained from strategies.
    This class is NOT an authorization service for untrusted remote clients.
    """

    def __init__(self, path: str | Path, *, admin_ids: Collection[int],
                 owner_ids: Collection[int] = (), catalog: ResearchInstrumentCatalog | None = None,
                 listings: Collection[CoreListing] = (), enabled: bool = False):
        self.admin_ids = frozenset(admin_ids)
        self.owner_ids = frozenset(owner_ids)
        if (not self.admin_ids or any(type(x) is not int or x <= 0 for x in self.admin_ids)
                or any(type(x) is not int for x in self.owner_ids)
                or not self.owner_ids.issubset(self.admin_ids)
                or type(enabled) is not bool):
            raise ControlRefused("INVALID_OPERATOR_SCOPE")
        self.enabled = enabled
        self.catalog = catalog
        if catalog is not None and not isinstance(catalog, ResearchInstrumentCatalog):
            raise ControlRefused("INVALID_INSTRUMENT_CATALOG")
        # Existing Brooks is a public configuration REFERENCE ONLY; no
        # undocumented Core API bridge or signal permission is claimed.
        builtin = CoreListing("brooks_price_action", "Al Brooks Price Action",
                              "REFERENCE_ONLY")
        entries = (builtin, *tuple(listings))
        if any(type(x) is not CoreListing for x in entries):
            raise ControlRefused("INVALID_LISTING")
        self._listings = {x.core_id: x for x in entries}
        if len(self._listings) != len(entries):
            raise ControlRefused("DUPLICATE_CORE_LISTING")
        target = Path(path)
        if str(path) == ":memory:" or target.is_symlink() or (target.exists() and not target.is_file()) or not target.parent.is_dir():
            raise ControlRefused("DEDICATED_EXISTING_STATE_DIRECTORY_REQUIRED")
        self._db = sqlite3.connect(str(target), isolation_level=None, timeout=5)
        self._db.row_factory = sqlite3.Row
        existing = {r[0] for r in self._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )}
        if existing - {"t12_instances", "t12_bindings", "t12_audit"}:
            self._db.close()
            raise ControlRefused("DEDICATED_STAGE12_DATABASE_ONLY")
        self._db.execute("PRAGMA foreign_keys=ON")
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=FULL")
        self._db.execute("PRAGMA busy_timeout=5000")
        self._db.executescript("""
          CREATE TABLE IF NOT EXISTS t12_instances(
            instance_id TEXT PRIMARY KEY, core_id TEXT NOT NULL,
            account_id TEXT NOT NULL, portfolio_id TEXT NOT NULL,
            created_by INTEGER NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
            analysis INTEGER NOT NULL DEFAULT 0 CHECK(analysis IN(0,1)),
            signals INTEGER NOT NULL DEFAULT 0 CHECK(signals IN(0,1)),
            paper INTEGER NOT NULL DEFAULT 0 CHECK(paper IN(0,1)),
            max_reserved TEXT NOT NULL DEFAULT '0.01',
            max_notional TEXT NOT NULL DEFAULT '0.1',
            max_order TEXT NOT NULL DEFAULT '0.005',
            max_orders INTEGER NOT NULL DEFAULT 1);
          CREATE TABLE IF NOT EXISTS t12_bindings(
            binding_id TEXT PRIMARY KEY, instance_id TEXT NOT NULL REFERENCES t12_instances(instance_id),
            market TEXT NOT NULL, provider TEXT NOT NULL, symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL, timezone TEXT NOT NULL, currency TEXT NOT NULL,
            source_digest TEXT NOT NULL, UNIQUE(instance_id,market,provider,symbol,timeframe));
          CREATE TABLE IF NOT EXISTS t12_audit(
            seq INTEGER PRIMARY KEY AUTOINCREMENT, instance_id TEXT NOT NULL,
            actor_id INTEGER NOT NULL, revision INTEGER NOT NULL,
            action TEXT NOT NULL, payload_hash TEXT NOT NULL,
            prev_hash TEXT NOT NULL, entry_hash TEXT NOT NULL);
        """)

    def close(self) -> None:
        self._db.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def _auth(self, actor_id: int) -> None:
        if type(actor_id) is not int or actor_id not in self.admin_ids:
            raise ControlRefused("OPERATOR_NOT_AUTHORIZED")

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise ControlRefused("CONTROL_CENTER_DISABLED")

    def _listing(self, actor_id: int, core_id: str) -> CoreListing:
        self._auth(actor_id)
        _identity(core_id, "CORE_ID")
        item = self._listings.get(core_id)
        if item is None or (item.visibility == "OWNER_ONLY" and actor_id not in self.owner_ids):
            raise ControlRefused("CORE_NOT_VISIBLE")
        return item

    def available_cores(self, actor_id: int) -> tuple[CoreListing, ...]:
        self._auth(actor_id)
        return tuple(sorted((x for x in self._listings.values()
                     if x.visibility == "PUBLIC" or actor_id in self.owner_ids),
                     key=lambda v: v.core_id))

    def _row(self, actor_id: int, instance_id: str) -> tuple[sqlite3.Row, CoreListing]:
        self._auth(actor_id)
        _identity(instance_id, "INSTANCE_ID")
        row = self._db.execute("SELECT * FROM t12_instances WHERE instance_id=?", (instance_id,)).fetchone()
        if row is None:
            raise ControlRefused("INSTANCE_NOT_ACCESSIBLE")
        listing = self._listing(actor_id, row["core_id"])
        if row["created_by"] != actor_id:
            raise ControlRefused("INSTANCE_NOT_ACCESSIBLE")
        return row, listing

    def _audit(self, row: sqlite3.Row, actor: int, action: str, payload: object, revision: int) -> None:
        last = self._db.execute("SELECT entry_hash FROM t12_audit ORDER BY seq DESC LIMIT 1").fetchone()
        prev = last["entry_hash"] if last is not None else "0" * 64
        digest = _hash(_canonical(payload))
        stamp = _canonical([prev, row["instance_id"], actor, revision, action, digest])
        self._db.execute("INSERT INTO t12_audit(instance_id,actor_id,revision,action,payload_hash,prev_hash,entry_hash) VALUES(?,?,?,?,?,?,?)",
                         (row["instance_id"], actor, revision, action, digest, prev, _hash(stamp)))

    def _tx(self, callback):
        self._db.execute("BEGIN IMMEDIATE")
        try:
            v = callback()
            self._db.execute("COMMIT")
            return v
        except BaseException:
            self._db.execute("ROLLBACK")
            raise

    def create_instance(self, actor_id: int, *, core_id: str, instance_id: str,
                        account_id: str, portfolio_id: str) -> InstanceView:
        self._require_enabled()
        self._listing(actor_id, core_id)
        for value, name in ((instance_id,"INSTANCE_ID"),(account_id,"ACCOUNT_ID"),(portfolio_id,"PORTFOLIO_ID")):
            _identity(value, name)
        def commit():
            if self._db.execute("SELECT 1 FROM t12_instances WHERE instance_id=?", (instance_id,)).fetchone():
                raise ControlRefused("INSTANCE_ALREADY_EXISTS")
            self._db.execute("INSERT INTO t12_instances(instance_id,core_id,account_id,portfolio_id,created_by) VALUES(?,?,?,?,?)",
                             (instance_id, core_id, account_id, portfolio_id, actor_id))
            row, _ = self._row(actor_id, instance_id)
            self._audit(row, actor_id, "CREATE", {"core_id":core_id,"account":account_id,"portfolio":portfolio_id}, 1)
        self._tx(commit)
        return self.inspect(actor_id, instance_id)

    def _mutate(self, actor_id: int, instance_id: str, expected_revision: int,
                action: str, payload: object, callback) -> InstanceView:
        self._require_enabled()
        if type(expected_revision) is not int or expected_revision <= 0:
            raise ControlRefused("INVALID_EXPECTED_REVISION")
        def commit():
            row, listing = self._row(actor_id, instance_id)
            if row["revision"] != expected_revision:
                raise ControlRefused("STALE_INSTANCE_REVISION")
            callback(row, listing)
            self._db.execute("UPDATE t12_instances SET revision=revision+1 WHERE instance_id=?", (instance_id,))
            self._audit(row, actor_id, action, payload, expected_revision + 1)
        self._tx(commit)
        return self.inspect(actor_id, instance_id)

    def set_request(self, actor_id: int, instance_id: str, *, field: str,
                    requested: bool, expected_revision: int) -> InstanceView:
        if field not in ("analysis", "signals", "paper") or type(requested) is not bool:
            raise ControlRefused("INVALID_REQUEST_FIELD")
        def apply(row, listing):
            if requested and listing.manifest is None:
                raise ControlRefused("CORE_ABI_NOT_READY")
            if requested and self._db.execute("SELECT 1 FROM t12_bindings WHERE instance_id=?",(instance_id,)).fetchone() is None:
                raise ControlRefused("BINDING_REQUIRED")
            self._db.execute(f"UPDATE t12_instances SET {field}=? WHERE instance_id=?",(int(requested),instance_id))
        return self._mutate(actor_id,instance_id,expected_revision,"REQUEST_"+field.upper(),{"requested":requested},apply)

    def set_allocation(self, actor_id: int, instance_id: str, *, max_reserved: Decimal,
                       max_notional: Decimal, max_order: Decimal,
                       max_orders: int, expected_revision: int) -> InstanceView:
        reserved = _fraction(max_reserved,"RESERVED_RISK")
        notional = _fraction(max_notional,"NOTIONAL")
        order = _fraction(max_order,"ORDER_RISK")
        if order > reserved or type(max_orders) is not int or not 1 <= max_orders <= 10000:
            raise ControlRefused("INVALID_CORE_ALLOCATION")
        def apply(row, listing):
            # Sum of per-core requested risk budgets cannot exceed account equity.
            other = self._db.execute("SELECT max_reserved FROM t12_instances WHERE account_id=? AND instance_id!=?",(row["account_id"],instance_id)).fetchall()
            if reserved + sum((Decimal(x["max_reserved"]) for x in other),Decimal(0)) > 1:
                raise ControlRefused("ACCOUNT_ALLOCATION_OVERBOOKED")
            self._db.execute("UPDATE t12_instances SET max_reserved=?,max_notional=?,max_order=?,max_orders=? WHERE instance_id=?",
                             (str(reserved),str(notional),str(order),max_orders,instance_id))
        return self._mutate(actor_id,instance_id,expected_revision,"SET_ALLOCATION",
                            {"risk":str(reserved),"notional":str(notional),"order":str(order),"count":max_orders},apply)

    def add_binding(self, actor_id: int, instance_id: str, *, provider: str,
                    symbol: str, timeframe: str, now: datetime,
                    expected_revision: int) -> InstanceView:
        if timeframe not in _TIMEFRAMES:
            raise ControlRefused("INVALID_TIMEFRAME")
        if self.catalog is None:
            raise ControlRefused("CATALOG_UNAVAILABLE")
        try:
            metadata = self.catalog.lookup(provider, symbol, now=now)
        except (CatalogRefused, ValueError) as exc:
            raise ControlRefused("CATALOG_UNVERIFIED_OR_STALE") from exc
        if metadata.listing_status is not ListingStatus.OPEN:
            raise ControlRefused("MARKET_SYMBOL_NOT_OPEN")
        if metadata.market not in (Market.CRYPTO, Market.FOREX):
            raise ControlRefused("STAGE12_MARKET_UNSUPPORTED")
        if ((metadata.market is Market.CRYPTO and metadata.origin is not MetadataOrigin.PUBLIC_CONTRACT_RESEARCH)
                or (metadata.market is Market.FOREX and metadata.origin is not MetadataOrigin.MT5_DEMO_OBSERVATION)):
            raise ControlRefused("DATA_SOURCE_MARKET_MISMATCH")
        def apply(row, listing):
            if listing.manifest is None or metadata.market not in listing.manifest.supported_markets:
                raise ControlRefused("CORE_MARKET_NOT_SUPPORTED_OR_NOT_PORTED")
            if self._db.execute("SELECT count(*) AS n FROM t12_bindings WHERE instance_id=?",(instance_id,)).fetchone()["n"] >= 64:
                raise ControlRefused("BINDING_LIMIT_REACHED")
            identity = [instance_id, metadata.market.value, provider, symbol, timeframe]
            binding_id = "bind_" + _hash(_canonical(identity))[:48]
            try:
                self._db.execute("INSERT INTO t12_bindings VALUES(?,?,?,?,?,?,?,?,?)",
                                 (binding_id,instance_id,metadata.market.value,provider,symbol,timeframe,
                                  metadata.timezone,metadata.quote_currency,content_digest(metadata)))
            except sqlite3.IntegrityError as exc:
                raise ControlRefused("DUPLICATE_BINDING") from exc
        return self._mutate(actor_id,instance_id,expected_revision,"ADD_BINDING",
                            {"provider":provider,"symbol":symbol,"timeframe":timeframe},apply)

    def remove_binding(self, actor_id: int, instance_id: str, *, binding_id: str,
                       expected_revision: int) -> InstanceView:
        _identity(binding_id,"BINDING_ID")
        def apply(row, listing):
            count = self._db.execute("DELETE FROM t12_bindings WHERE binding_id=? AND instance_id=?",(binding_id,instance_id)).rowcount
            if count != 1:
                raise ControlRefused("BINDING_NOT_ACCESSIBLE")
            if not self._db.execute("SELECT 1 FROM t12_bindings WHERE instance_id=?",(instance_id,)).fetchone():
                self._db.execute("UPDATE t12_instances SET analysis=0,signals=0,paper=0 WHERE instance_id=?",(instance_id,))
        return self._mutate(actor_id,instance_id,expected_revision,"REMOVE_BINDING",{"binding_id":binding_id},apply)

    def inspect(self, actor_id: int, instance_id: str) -> InstanceView:
        row, listing = self._row(actor_id,instance_id)
        count = self._db.execute("SELECT count(*) FROM t12_bindings WHERE instance_id=?",(instance_id,)).fetchone()[0]
        return InstanceView(instance_id,row["core_id"],listing.name,row["account_id"],row["portfolio_id"],
                            row["revision"],row["created_by"],bool(row["analysis"]),bool(row["signals"]),
                            bool(row["paper"]),row["max_reserved"],row["max_notional"],row["max_order"],row["max_orders"],count)

    def instances(self, actor_id: int) -> tuple[InstanceView, ...]:
        self._auth(actor_id)
        rows=self._db.execute("SELECT instance_id FROM t12_instances WHERE created_by=? ORDER BY instance_id",(actor_id,)).fetchall()
        # Do not inadvertently reveal owner-only items if roles were revoked.
        result=[]
        for r in rows:
            try: result.append(self.inspect(actor_id,r["instance_id"]))
            except ControlRefused: pass
        return tuple(result)

    def bindings(self, actor_id: int, instance_id: str) -> tuple[BindingView, ...]:
        self._row(actor_id, instance_id)
        rows=self._db.execute("SELECT * FROM t12_bindings WHERE instance_id=? ORDER BY market,provider,symbol,timeframe",(instance_id,)).fetchall()
        return tuple(BindingView(instance_id,x["binding_id"],x["market"],x["provider"],x["symbol"],
                                 x["timeframe"],x["timezone"],x["currency"],x["source_digest"]) for x in rows)

    def preview_bindings(self, actor_id: int, instance_id: str, *, now: datetime) -> tuple[CoreBinding, ...]:
        self._require_enabled()
        instance=self.inspect(actor_id,instance_id)
        listing=self._listing(actor_id,instance.core_id)
        if listing.manifest is None or self.catalog is None:
            raise ControlRefused("CORE_ABI_OR_CATALOG_NOT_READY")
        values=[]
        for stored in self.bindings(actor_id,instance_id):
            try: item=self.catalog.lookup(stored.provider,stored.symbol,now=now)
            except CatalogRefused as exc: raise ControlRefused("CATALOG_UNVERIFIED_OR_STALE") from exc
            if (item.listing_status is not ListingStatus.OPEN
                or content_digest(item) != stored.source_digest):
                raise ControlRefused("CATALOG_CHANGED_REVIEW_REQUIRED")
            values.append(CoreBinding(instance_id,stored.binding_id,item.instrument,stored.timeframe))
        return tuple(values)

    def preview_capital(self, actor_id: int, instance_id: str) -> dict:
        """Inert Stage-8-compatible fields; no Stage-8 mutation is performed."""
        s=self.inspect(actor_id,instance_id)
        return {"instance_id":s.instance_id,"core_id":s.core_id,"account_id":s.account_id,
                "portfolio_id":s.portfolio_id,"max_reserved_risk_fraction":s.max_reserved_risk_fraction,
                "max_notional_fraction":s.max_notional_fraction,"max_order_risk_fraction":s.max_order_risk_fraction,
                "max_active_orders":s.max_active_orders,"stage8_activation":False}

    def audit(self, actor_id: int, instance_id: str) -> tuple[dict, ...]:
        self._row(actor_id,instance_id)
        rows=self._db.execute("SELECT revision,actor_id,action,payload_hash,prev_hash,entry_hash FROM t12_audit WHERE instance_id=? ORDER BY seq",(instance_id,)).fetchall()
        return tuple(dict(r) for r in rows)


__all__=["BindingView","ControlRefused","CoreListing","InstanceView","OfflineTradingControlCenter"]
