"""A8 universal plugin descriptor: strictly data-only, no imports or installs.

A SHA-256 pin proves byte equality to an operator-approved descriptor, not
publisher authenticity. Private plugin code MUST NOT be placed in this repo.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass

from .contracts import EngineDescriptor, Market
from .engine_plan import IDENTITY, VERSION

_FIELDS = frozenset({
    "schema_version", "engine_id", "engine_version", "publisher",
    "visibility", "adapter", "abi_version", "markets", "permissions",
})
_PUBLISHER = re.compile(r"[A-Za-z][A-Za-z0-9_.-]{1,79}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_ALLOWED_PERMISSIONS = ("paper_analysis",)


def _unique(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("A8_DUPLICATE_FIELD")
        result[key] = value
    return result


@dataclass(frozen=True, slots=True)
class PluginDescriptor:
    engine_id: str
    engine_version: str
    publisher: str
    visibility: str
    adapter: str
    markets: frozenset[Market]
    digest: str

    def engine_descriptor(self) -> EngineDescriptor:
        return EngineDescriptor(self.engine_id, self.engine_version, self.markets)


def parse_descriptor(raw: bytes, *, approved_sha256: str) -> PluginDescriptor:
    """Validate exact bytes against a separately supplied pinned digest.

    This does NOT cryptographically authenticate a publisher and does NOT
    load, download, provision, execute or authorize any plugin binary.
    """
    if type(raw) is not bytes or not 0 < len(raw) <= 8192:
        raise ValueError("A8_DESCRIPTOR_BYTES_INVALID")
    if type(approved_sha256) is not str or not _DIGEST.fullmatch(approved_sha256):
        raise ValueError("A8_APPROVED_PIN_INVALID")
    digest = hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(digest, approved_sha256):
        raise ValueError("A8_DESCRIPTOR_PIN_MISMATCH")
    try:
        data = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")),
        )
    except (UnicodeError, ValueError) as exc:
        raise ValueError("A8_DESCRIPTOR_JSON_INVALID") from exc
    if not isinstance(data, dict) or set(data) != _FIELDS:
        raise ValueError("A8_DESCRIPTOR_FIELDS_INVALID")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("A8_SCHEMA_VERSION_INVALID")
    if type(data["abi_version"]) is not int or data["abi_version"] != 1:
        raise ValueError("A8_ABI_VERSION_INVALID")
    engine_id = data["engine_id"]
    engine_version = data["engine_version"]
    publisher = data["publisher"]
    if type(engine_id) is not str or not IDENTITY.fullmatch(engine_id):
        raise ValueError("A8_ENGINE_ID_INVALID")
    if type(engine_version) is not str or not VERSION.fullmatch(engine_version):
        raise ValueError("A8_ENGINE_VERSION_INVALID")
    if type(publisher) is not str or not _PUBLISHER.fullmatch(publisher):
        raise ValueError("A8_PUBLISHER_INVALID")
    visibility = data["visibility"]
    adapter = data["adapter"]
    if (
        type(visibility) is not str
        or type(adapter) is not str
        or (visibility, adapter) not in {
            ("public", "in_process"),
            ("private", "external_contract"),
        }
    ):
        raise ValueError("A8_VISIBILITY_ADAPTER_MISMATCH")
    markets = data["markets"]
    if not isinstance(markets, list) or not 1 <= len(markets) <= 4:
        raise ValueError("A8_MARKETS_INVALID")
    if any(type(market) is not str for market in markets):
        raise ValueError("A8_MARKETS_INVALID")
    if len(set(markets)) != len(markets):
        raise ValueError("A8_DUPLICATE_MARKET")
    try:
        supported = frozenset(Market(market) for market in markets)
    except ValueError as exc:
        raise ValueError("A8_UNKNOWN_MARKET") from exc
    if (
        type(data["permissions"]) is not list
        or data["permissions"] != list(_ALLOWED_PERMISSIONS)
    ):
        raise ValueError("A8_PAPER_PERMISSION_ONLY")
    return PluginDescriptor(
        engine_id, engine_version, publisher, visibility, adapter, supported, digest
    )
