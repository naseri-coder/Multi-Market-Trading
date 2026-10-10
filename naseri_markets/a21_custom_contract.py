"""A21 metadata-only CUSTOM engine contract and publication boundary.

The public Multi Market Trading project may describe generic external PAPER
interfaces. It must NEVER package, publish, offer to install, decrypt or load
NY First-Reversal or any private executable. Hash pinning is not licensing.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass

from .contracts import Market
from .engine_plan import IDENTITY, VERSION
from .external_abi import ABI_VERSION, parse_paper_envelope
from .quotes import QuoteOrigin

_FIELDS = frozenset({
    "schema_version", "engine_id", "engine_version", "publisher",
    "markets", "access_policy", "strategy_family", "adapter",
    "abi_version", "distribution", "artifact_policy", "permissions",
    "runtime_mode", "execution_authorized",
})
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_PUBLISHER = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{1,79}\Z")
_POLICIES = frozenset({"public_custom", "owner_only", "commercial_candidate"})
# This product-specific intellectual property is never offered or delivered
# by the public software, EVEN if wrapped in encrypted/obfuscated code.
_RESERVED = frozenset({"nyfirstreversal", "nyfr", "privatenyfrcore",
                       "r0engine"})
_RESERVED_FAMILY = "ny_first_reversal"


class CustomContractRefused(ValueError):
    """No arbitrary binary, marketing label or digest can grant execution."""


def _unique(pairs):
    record = {}
    for key, value in pairs:
        if key in record:
            raise CustomContractRefused("A21_DUPLICATE_FIELD")
        record[key] = value
    return record


def _protected(value: str) -> bool:
    canon = re.sub(r"[^a-z0-9]", "", value.casefold())
    return any(alias in canon for alias in _RESERVED)


@dataclass(frozen=True, slots=True)
class CustomEngineContract:
    engine_id: str
    engine_version: str
    publisher: str
    markets: frozenset[Market]
    access_policy: str
    strategy_family: str
    approved_descriptor_sha256: str
    status: str = "CONTRACT_ONLY_NOT_INSTALLED"
    private_source_received: bool = False
    executable_installed: bool = False
    execution_authorized: bool = False
    live_trading_authorized: bool = False
    commercial_license_issued: bool = False

    @property
    def publicly_discoverable(self) -> bool:
        return self.access_policy == "public_custom"

    @property
    def protected_owner_core(self) -> bool:
        return self.strategy_family == _RESERVED_FAMILY


@dataclass(frozen=True, slots=True)
class PublicCustomListing:
    """Deliberately excludes publisher secrets, owner-only and sales data."""
    engine_id: str
    engine_version: str
    markets: tuple[str, ...]
    contract_status: str = "METADATA_ONLY_NOT_INSTALLABLE"


class CustomContractCatalog:
    """In-memory operator-pinned registration; no persistent or runtime writes.

    Contracts DO NOT invoke PluginManager.enable, A14.install, A18.launch,
    subprocess, network, brokers or a private entry point.
    """

    def __init__(self) -> None:
        self._items: dict[str, CustomEngineContract] = {}

    def register(self, raw: bytes, *, approved_sha256: str) -> CustomEngineContract:
        contract = parse_custom_contract(raw, approved_sha256=approved_sha256)
        existing = self._items.get(contract.engine_id)
        if existing is not None and existing != contract:
            raise CustomContractRefused("A21_IMMUTABLE_ID_COLLISION")
        self._items[contract.engine_id] = contract
        return contract

    def public_listings(self) -> tuple[PublicCustomListing, ...]:
        return tuple(
            PublicCustomListing(item.engine_id, item.engine_version,
                                tuple(sorted(m.value for m in item.markets)))
            for item in sorted(self._items.values(), key=lambda e: e.engine_id)
            if item.publicly_discoverable and not item.protected_owner_core
        )

    def public_lookup(self, engine_id: str) -> PublicCustomListing | None:
        for entry in self.public_listings():
            if entry.engine_id == engine_id:
                return entry
        return None

    def owner_inventory(self) -> tuple[CustomEngineContract, ...]:
        """Local operator diagnostic, NEVER use as a public API/feed."""
        return tuple(sorted(self._items.values(), key=lambda e: e.engine_id))


def parse_custom_contract(raw: bytes, *, approved_sha256: str) -> CustomEngineContract:
    """Strict schema; caller supplies pin independently, not from raw itself.

    Neither this pin nor a parsed document authenticates a publisher, proves
    ownership or issues a license. Owner-commercial distribution is future work.
    """
    if type(raw) is not bytes or not 0 < len(raw) <= 4096:
        raise CustomContractRefused("A21_SMALL_DATA_ONLY_JSON_REQUIRED")
    if type(approved_sha256) is not str or not _DIGEST.fullmatch(approved_sha256):
        raise CustomContractRefused("A21_INDEPENDENT_PIN_REQUIRED")
    digest = hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(digest, approved_sha256):
        raise CustomContractRefused("A21_PIN_MISMATCH")
    try:
        doc = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique,
                         parse_constant=lambda _: (_ for _ in ()).throw(
                             CustomContractRefused("A21_NONFINITE")))
    except (UnicodeError, ValueError) as exc:
        raise CustomContractRefused("A21_INVALID_CONTRACT_JSON") from exc
    if type(doc) is not dict or set(doc) != _FIELDS:
        raise CustomContractRefused("A21_EXACT_METADATA_FIELDS_REQUIRED")
    if type(doc["schema_version"]) is not int or doc["schema_version"] != 1:
        raise CustomContractRefused("A21_SCHEMA_VERSION")
    if type(doc["abi_version"]) is not int or doc["abi_version"] != ABI_VERSION:
        raise CustomContractRefused("A21_EXTERNAL_ABI_MISMATCH")
    name, version, publisher = (doc[k] for k in
                                ("engine_id", "engine_version", "publisher"))
    if type(name) is not str or not IDENTITY.fullmatch(name):
        raise CustomContractRefused("A21_ENGINE_IDENTITY")
    if type(version) is not str or not VERSION.fullmatch(version):
        raise CustomContractRefused("A21_ENGINE_VERSION")
    if type(publisher) is not str or not _PUBLISHER.fullmatch(publisher):
        raise CustomContractRefused("A21_PUBLISHER_LABEL")
    if type(doc["access_policy"]) is not str or doc["access_policy"] not in _POLICIES:
        raise CustomContractRefused("A21_UNKNOWN_ACCESS_POLICY")
    if (type(doc["strategy_family"]) is not str
            or doc["strategy_family"] not in {"generic_custom", _RESERVED_FAMILY}):
        raise CustomContractRefused("A21_UNKNOWN_STRATEGY_FAMILY")
    markets = doc["markets"]
    if (type(markets) is not list or not 1 <= len(markets) <= 4
            or any(type(m) is not str for m in markets)
            or len(set(markets)) != len(markets)):
        raise CustomContractRefused("A21_MARKETS_INVALID")
    try:
        market_set = frozenset(Market(m) for m in markets)
    except ValueError as exc:
        raise CustomContractRefused("A21_MARKETS_UNKNOWN") from exc
    # These are invariant metadata-only controls, not user-tunable switches.
    if (doc["adapter"] != "external_contract"
            or doc["distribution"] != "metadata_only"
            or doc["artifact_policy"] != "no_executable_or_ciphertext"
            or doc["permissions"] != ["paper_analysis"]
            or doc["runtime_mode"] != "replay_or_synthetic"
            or doc["execution_authorized"] is not False):
        raise CustomContractRefused("A21_NO_EXECUTABLE_OR_LIVE_ADMISSION")
    protected = (doc["strategy_family"] == _RESERVED_FAMILY
                 or _protected(name) or _protected(publisher))
    # NY First-Reversal is strictly owner-exclusive for now. No future
    # commercial route is implicitly issued by naming a package "licensed".
    if protected and (doc["access_policy"] != "owner_only"
                      or doc["strategy_family"] != _RESERVED_FAMILY):
        raise CustomContractRefused("A21_PROTECTED_OWNER_EXCLUSIVE")
    if doc["access_policy"] == "public_custom" and protected:
        raise CustomContractRefused("A21_PROTECTED_NEVER_PUBLIC")
    return CustomEngineContract(name, version, publisher, market_set,
                                doc["access_policy"], doc["strategy_family"],
                                digest)


def inspect_custom_paper_fixture(contract: CustomEngineContract, blob: bytes, tick):
    """Validate an injected PAPER envelope using existing A7, never fetch one.

    No strategy instance is constructed; no orders, credentials, remote
    endpoints or filesystem artifacts are supported.
    """
    if not isinstance(contract, CustomEngineContract):
        raise CustomContractRefused("A21_PINNED_CONTRACT_REQUIRED")
    if tick.origin not in (QuoteOrigin.REPLAY, QuoteOrigin.SYNTHETIC):
        raise CustomContractRefused("A21_LIVE_DATA_REFUSED")
    if tick.instrument.market not in contract.markets:
        raise CustomContractRefused("A21_MARKET_OUTSIDE_CONTRACT")
    return parse_paper_envelope(blob, tick, engine_id=contract.engine_id,
                                engine_version=contract.engine_version)
