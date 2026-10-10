"""A9 transport-neutral plugin settings service.

No Telegram handlers, token storage, network checks, private source, broker
operations or automatic plugin installation. The caller MUST authenticate a
user in its own trusted boundary before passing their verified actor ID.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from .plugin_manager import PluginManager, PluginState


class OperatorDenied(PermissionError):
    """Unauthenticated/unapproved settings actor."""


@dataclass(frozen=True, slots=True)
class PluginPanelItem:
    engine_id: str
    engine_version: str
    visibility: str
    markets: tuple[str, ...]
    enabled_for_paper: bool
    revision: int
    metadata_registered: bool
    code_installed: bool
    operational_health: str
    live_connected: bool
    trading_authorized: bool


def _panel_item(s: PluginState) -> PluginPanelItem:
    return PluginPanelItem(
        engine_id=s.engine_id,
        engine_version=s.engine_version,
        visibility=s.visibility,
        markets=tuple(sorted(s.markets)),
        enabled_for_paper=s.enabled,
        revision=s.revision,
        metadata_registered=True,
        code_installed=False,
        operational_health=(
            "PRIVATE_OWNER_NOT_ATTESTED"
            if s.visibility == "private" else
            "PUBLIC_ADAPTER_NOT_PROBED"
        ),
        live_connected=False,
        trading_authorized=False,
    )


class PluginSettingsService:
    """A presentation adapter suitable for a FUTURE authenticated bot UI.

    Constructor takes an explicit allowlist; passing arbitrary user IDs or a
    client-provided 'is_admin' flag is not authorization. Trusted transport
    must obtain actor identity from its own independently verified session.
    """

    def __init__(self, manager: PluginManager, *, operator_ids: frozenset[int]) -> None:
        if (
            not isinstance(operator_ids, frozenset) or not operator_ids
            or any(type(x) is not int or x <= 0 for x in operator_ids)
        ):
            raise ValueError("A9_TRUSTED_OPERATOR_IDS_REQUIRED")
        self._manager = manager
        self._operators = operator_ids

    def _authorize(self, actor_id: int) -> None:
        if type(actor_id) is not int or actor_id not in self._operators:
            raise OperatorDenied("A9_OPERATOR_NOT_AUTHORIZED")

    def inventory(self, actor_id: int) -> tuple[PluginPanelItem, ...]:
        self._authorize(actor_id)
        return tuple(_panel_item(s) for s in self._manager.list())

    def inspect(self, actor_id: int, engine_id: str) -> PluginPanelItem:
        self._authorize(actor_id)
        state = self._manager.get(engine_id)
        if state is None:
            raise ValueError("A9_PLUGIN_UNKNOWN")
        return _panel_item(state)

    def register(
        self, actor_id: int, manifest_bytes: bytes, *, approved_sha256: str
    ) -> PluginPanelItem:
        self._authorize(actor_id)
        return _panel_item(self._manager.register(
            manifest_bytes, approved_sha256=approved_sha256,
        ))

    def set_paper_enabled(
        self, actor_id: int, engine_id: str, *, enabled: bool,
        expected_revision: int,
    ) -> PluginPanelItem:
        self._authorize(actor_id)
        return _panel_item(self._manager.set_enabled(
            engine_id, enabled=enabled, expected_revision=expected_revision,
        ))

    def upgrade(
        self, actor_id: int, manifest_bytes: bytes, *,
        approved_sha256: str, expected_revision: int,
    ) -> PluginPanelItem:
        self._authorize(actor_id)
        return _panel_item(self._manager.replace(
            manifest_bytes, approved_sha256=approved_sha256,
            expected_revision=expected_revision,
        ))

    def unregister(
        self, actor_id: int, engine_id: str, *, expected_revision: int,
    ) -> int:
        self._authorize(actor_id)
        return self._manager.unregister(engine_id, expected_revision=expected_revision)

    def audit(self, actor_id: int, engine_id: str) -> tuple[dict, ...]:
        self._authorize(actor_id)
        return self._manager.audit_history(engine_id)

    def health_report(self, actor_id: int) -> dict:
        """Metadata-only health, NOT live process heartbeat or attestation."""
        self._authorize(actor_id)
        engines = self.inventory(actor_id)
        return {
            "scope": "OFFLINE_METADATA_ONLY",
            "operator_auth_source": "CALLER_MUST_AUTHENTICATE",
            "plugins": [asdict(s) for s in engines],
            "private_engine_attested": False,
            "live_feed_verified": False,
            "telegram_publication_enabled": False,
            "broker_order_execution_enabled": False,
        }
