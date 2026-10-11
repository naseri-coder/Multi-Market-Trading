"""Stage-12 opt-in mount into the EXISTING nonproduction Telegram application.

Never creates a second poller; production application and credentials untouched.
Call only from an independently isolated development entry point.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Collection

from .instrument_registry_v1 import ResearchInstrumentCatalog
from .trading_control_center_v1 import CoreListing, OfflineTradingControlCenter, ControlRefused
from .trading_control_telegram_v1 import TelegramControlPreviewPanel


@dataclass
class DevelopmentControlMount:
    application: object
    center: OfflineTradingControlCenter

    def close(self):
        self.center.close()


def build_stage12_dev_application(*, token: str, state_dir: str | Path,
                                  admin_ids: Collection[int], owner_ids: Collection[int] = (),
                                  listings: Collection[CoreListing] = (),
                                  catalog: ResearchInstrumentCatalog | None = None,
                                  explicitly_enabled: bool = False) -> DevelopmentControlMount:
    """One PTB Application: the existing integrated panel plus Stage-12 preview.

    The caller MUST separately authorize a dedicated nonproduction bot token,
    persistence directory, and any later polling. This function never connects.
    """
    if explicitly_enabled is not True:
        raise ControlRefused("EXPLICIT_NONPRODUCTION_MOUNT_REQUIRED")
    directory = Path(state_dir)
    if directory.is_symlink() or not directory.is_dir():
        raise ControlRefused("EXISTING_DEVELOPMENT_DIRECTORY_REQUIRED")
    # Validate the admin ACL before constructing any Telegram Application.
    center = OfflineTradingControlCenter(directory/"stage12_control_preview.sqlite",
                                         admin_ids=admin_ids, owner_ids=owner_ids,
                                         catalog=catalog, listings=listings, enabled=True)
    try:
        from .bot_admin_app import build_admin_application
        app = build_admin_application(token=token, state_dir=directory,
                                      admin_ids=set(admin_ids), owner_ids=set(owner_ids),
                                      owner_reference=False)
        TelegramControlPreviewPanel(center).register(app)
    except BaseException:
        center.close()
        raise
    return DevelopmentControlMount(app, center)


__all__ = ["DevelopmentControlMount", "build_stage12_dev_application"]
